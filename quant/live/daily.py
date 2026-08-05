"""매일 1사이클 자동 페이퍼 운용 — 사용자가 아무것도 안 해도 돌아간다.

GitHub Actions가 매일 밤 이 모듈을 실행한다:
    1. 어제까지의 페이퍼 계좌 상태(현금·포지션)를 state/paper/에서 이어받고
    2. 최신 실데이터로 현재 챔피언 전략의 목표 비중을 계산해
    3. 가짜 돈으로 매매한 뒤(수수료 반영)
    4. 자산·적중률 기록을 다시 state/paper/에 저장하고 웹사이트용
       docs/status.json 을 갱신한다 → 사이트만 열어도 매일 결과가 보인다.

⚠️ 이것은 페이퍼(모의) 운용이다 — 실제 돈이 오가지 않으며, 결과가 좋아도
미래 수익을 보장하지 않는다. 목적은 '전략을 방치 상태에서 장기 검증'하는 것.
실거래 전환은 사람이 직접 결정해야 한다(자동으로 실거래를 켜지 않는다).
"""
from __future__ import annotations

import json
import os
import re

from quant.live.retrain import STATE_DIR, champion_spec, champion_strategy
from quant.utils.logging import get_logger

log = get_logger("daily_paper")

START_CASH = 10_000.0

# ── 체결 현실성 규칙 ────────────────────────────────────────────────
# 새벽 판단 시점(KST 05:30)에 실제로 체결 가능한 첫 시점은 시장마다 다르다:
#   코인: 24시간 시장 → 판단 직후 체결 가능(마지막 종가 근사)
#   한국/미국 주식: 장 마감 후 판단 → 다음 세션 '시가'에 체결(개장 갭을
#   그대로 감수한다 — 마감 종가로 즉시 체결 처리하면 실현 불가능한 가격이다)
IMMEDIATE_FILL_MARKETS = {"crypto", "synthetic"}


def _fill_cost(market: str) -> float:
    """편도 체결 비용(수수료+거래세+슬리피지) — 시장별 현실 프리셋."""
    from quant.backtest.costs import CostModel
    cm = CostModel.for_market(market)
    return float(cm.fee + cm.slippage)


def _first_bar_after(df, bar_ts: str):
    """decided_bar 이후 첫 봉의 (타임스탬프, 시가). 없으면 (None, None)."""
    for ix, r in df.iterrows():
        if str(ix) > bar_ts:
            return str(ix), float(r["open"])
    return None, None


# 재현성 해시 — 공용 구현(quant.utils.repro)을 그대로 쓴다
from quant.utils.repro import code_sha as _code_sha
from quant.utils.repro import data_sha256 as _data_sha256
from quant.utils.repro import env_fingerprint as _env_fingerprint

# 회계 기준 버전 — v0.5.0부터 '다음 시가 체결 + 거래세·슬리피지' 기준.
# 이전 기록(종가 즉시 체결)은 재계산하지 않고 그대로 둔다(과거 불변 약속).
# 이 태그로 어느 기준으로 계산된 기록인지 영구히 구분할 수 있다.
ACCOUNTING_VERSION = "next_open_v2"


def _paper_path(market: str, symbol: str, state_dir: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{market}_{symbol}")
    return os.path.join(state_dir, "paper", f"{safe}.json")


def _load_paper(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"cash": START_CASH, "quantity": 0.0, "avg_price": 0.0,
            "last_bar": None, "history": []}


def run_daily_paper(market: str, symbol: str, *, timeframe: str = "1d",
                    lookback: int = 400, state_dir: str = STATE_DIR,
                    require_real_data: bool = True) -> dict:
    """페이퍼 계좌 상태를 이어받아 하루치 사이클을 1회 수행한다(멱등).

    같은 봉에 두 번 실행되면 두 번째는 아무것도 하지 않는다 — 재실행/재시도가
    이중 매매를 만들지 않게 하는 안전장치.
    """
    from quant.broker import PaperBroker
    from quant.broker.base import Position
    from quant.data import get_provider
    from quant.risk import RiskManager
    from quant.robustness.accuracy import directional_accuracy
    from quant.utils.jsonio import atomic_write_json, cap_history

    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=lookback)
    if df.empty:
        raise RuntimeError(f"{market}/{symbol}: 데이터 수신 실패")
    if require_real_data and df.attrs.get("synthetic_fallback"):
        raise RuntimeError(
            f"{market}/{symbol}: 실데이터 수신 실패 → 합성 폴백 감지. "
            "가짜 데이터로 페이퍼 기록을 오염시키지 않도록 중단합니다.")

    path = _paper_path(market, symbol, state_dir)
    st = _load_paper(path)
    last_bar = str(df.index[-1])
    if st.get("last_bar") == last_bar:
        log.info("%s/%s: 같은 봉(%s)에 이미 실행됨 — 건너뜀", market, symbol, last_bar)
        return {"skipped": True, "last_bar": last_bar}

    strategy = champion_strategy(market, symbol, state_dir)
    signals = strategy.generate_signals(df)
    weight = float(RiskManager().size_positions(df, signals).iloc[-1])
    price = float(df["close"].iloc[-1])

    # 오늘 판단의 근거를 사람 말로 — 방송·사이트에 "새벽 판단 기준"으로 표시
    from quant.live.explain import explain_signal
    reason = explain_signal(champion_spec(market, symbol, state_dir), df,
                            weight, getattr(strategy, "_impl", None))

    broker = PaperBroker(cash=float(st["cash"]), fee=_fill_cost(market))
    if abs(float(st.get("quantity", 0.0))) > 0:
        broker._positions[symbol] = Position(       # 어제의 포지션 복원
            symbol, float(st["quantity"]), float(st.get("avg_price", 0.0)))

    fill = None
    # ① 어제 결정의 대기 주문 체결 — 주식은 '다음 세션 시가'에서만 체결된다.
    pending = st.get("pending")
    if pending and pending.get("decided_bar"):
        fbar, fopen = _first_bar_after(df, pending["decided_bar"])
        if fopen is not None:
            eq_open = broker.equity({symbol: fopen})
            broker.target_weight(symbol, float(pending["weight"]), fopen, eq_open)
            fill = {"price": round(fopen, 6), "bar": fbar,
                    "weight": round(float(pending["weight"]), 4),
                    "decided_bar": pending["decided_bar"]}
            st["pending"] = None
    # ② 오늘의 결정 — 코인은 즉시 체결, 주식은 다음 시가 대기열에 올린다
    if market in IMMEDIATE_FILL_MARKETS:
        eq_now = broker.equity({symbol: price})
        broker.target_weight(symbol, weight, price, eq_now)
    else:
        st["pending"] = {"weight": round(weight, 4), "decided_bar": last_bar}

    pos = broker.get_position(symbol)
    equity = broker.equity({symbol: price})

    acc = directional_accuracy(df, signals, window=60)
    record = {
        "date": last_bar[:10], "price": price, "weight": round(weight, 4),
        "equity": round(equity, 2),
        "return_pct": round((equity / START_CASH - 1) * 100, 2),
        "hit_rate": acc.get("hit_rate"),
        "champion": champion_spec(market, symbol, state_dir)["params"],
        "reason": reason,
        # 체결 현실성: 실제 체결(다음 시가) 내역과 비용 반영 여부를 기록
        "fill": fill,
        "fill_cost": round(_fill_cost(market), 6),
        # 재현성: 코드 커밋 + 입력 데이터 해시 — verify로 재검증 가능
        "code_sha": _code_sha(),
        "data_sha256": _data_sha256(df),
        "env": _env_fingerprint(),
        "accounting": ACCOUNTING_VERSION,
    }
    st.update({
        "market": market, "symbol": symbol, "start_cash": START_CASH,
        "cash": broker.get_cash(), "quantity": pos.quantity,
        "avg_price": pos.avg_price, "last_bar": last_bar,
    })
    st["history"] = cap_history(st["history"] + [record])
    atomic_write_json(path, st)

    hr = record["hit_rate"]
    hr_txt = f"{hr:.1%}" if isinstance(hr, float) and hr == hr else "N/A"
    print(f"[{record['date']}] {market}/{symbol} 페이퍼 — 자산 {equity:,.2f} "
          f"({record['return_pct']:+.2f}%) · 비중 {weight:+.2f} · 적중률 {hr_txt}")
    return record


GOAL_KRW = 100_000_000          # 8마일 챌린지 목표 (8만원 → 1억)

# 8마일 챌린지 — 통합 계좌 시작금. 8종목 × 만원 = 8만원 (영화 8 Mile 오마주).
# 개별 종목 계좌는 여전히 각자 만원(START_CASH)으로 참고용 기록을 쌓는다.
PORTFOLIO_START_CASH = 80_000.0


def add_deposit(amount: float, memo: str = "", *, state_dir: str = STATE_DIR,
                date: str | None = None) -> dict:
    """후원 '매칭' 입금 — 통합 계좌의 원금을 늘린다 (8마일 챌린지 · 8만원 → 1억).

    ⚠️ 법적 구조(반드시 유지): 시청자의 후원금 자체를 굴리는 것이 아니다.
    후원은 대가·지분 없는 방송 후원이고, 운영자가 '같은 금액만큼' 가상 계좌
    원금을 늘리는 이벤트다. 이 구조를 바꾸면(타인 자금 운용) 유사수신·무인가
    집합투자 위험이 생긴다.

    모든 입금은 장부(deposits)에 기록되어 git 커밋으로 공개된다 — 수익률
    계산은 원금과 손익을 분리해(TWR) 입금이 실력처럼 보이지 않게 한다.
    """
    from datetime import date as _date

    from quant.utils.jsonio import atomic_write_json

    amount = float(amount)
    if not (0 < amount <= 10_000_000):
        raise ValueError("입금액은 0원 초과 1,000만원 이하여야 합니다.")

    path = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    else:
        st = {"market": "portfolio", "symbol": "ALL",
              "start_cash": PORTFOLIO_START_CASH,
              "cash": PORTFOLIO_START_CASH, "positions": {}, "base_prices": {},
              "last_bar": None, "history": [], "deposits": []}

    entry = {"date": date or _date.today().isoformat(),
             "amount": round(amount, 2), "memo": str(memo)[:80]}
    st.setdefault("deposits", []).append(entry)
    st["cash"] = float(st.get("cash", 0.0)) + amount
    atomic_write_json(path, st)

    principal = (float(st.get("start_cash", PORTFOLIO_START_CASH))
                 + sum(d["amount"] for d in st["deposits"]))
    print(f"💝 매칭 입금 +{amount:,.0f}원 ({entry['memo'] or '메모 없음'}) — "
          f"누적 원금 {principal:,.0f}원 / 목표 {GOAL_KRW:,}원")
    return {"deposit": entry, "principal": principal, "goal": GOAL_KRW}


def time_weighted_return(history: list[dict], deposits: list[dict],
                         start_cash: float = START_CASH) -> float:
    """시간가중 수익률(%) — 입금(원금 증액)의 효과를 제거한 순수 운용 실력.

    일별 구간수익 r_t = (자산_t − 그날 입금액) / 자산_{t−1} − 1 을 연쇄 곱한다.
    입금 날짜가 기록일 사이면 '그 이후 첫 기록일'에 귀속시킨다(보수적).
    """
    if not history:
        return 0.0
    flows: dict[str, float] = {}
    dates = [r["date"] for r in history]
    for d in deposits or []:
        target = next((dt for dt in dates if dt >= d["date"]), None)
        if target is not None:
            flows[target] = flows.get(target, 0.0) + float(d["amount"])
    twr = 1.0
    prev = start_cash
    for r in history:
        eq = float(r["equity"])
        flow = flows.get(r["date"], 0.0)
        if prev > 0:
            twr *= max(0.0, (eq - flow) / prev)
        prev = eq
    return round((twr - 1) * 100, 2)


def random_strategy_percentile(history: list[dict], actual_twr_pct: float,
                               n: int = 1000, seed: str = "rand",
                               cost: float = 0.002) -> float | None:
    """무작위 '순열' 전략 n개의 수익률 분포에서 실제 TWR의 백분위(%)를 잰다.

    조건을 맞춘 무작위(순열 검정): 각 무작위 전략은 실제 기록의 일별 비중
    수열을 그대로 가져다 '순서만' 무작위로 섞어, 같은 지수(record.price) 위에서
    같은 비용을 내며 거래한 것이다. 매매 빈도·포지션 크기 분포가 실제와
    동일하므로, 백분위가 재는 것은 오직 '타이밍 실력'뿐이다 — 조건 없는
    동전 던지기와 비교하면 빈도 차이가 실력처럼 보이는 왜곡이 생긴다.
    반환 75.0 = "무작위 1,000개 중 상위 25%". 기록 2일 미만이면 None.
    시드가 날짜 기반이라 같은 날 재실행 시 같은 값(재현 가능).
    비중이 늘 일정했던 구간에서는 순열이 전부 같아져 백분위가 낮게(우위
    없음으로) 나온다 — 타이밍을 쓰지 않았으니 그것이 정직한 값이다.
    """
    import random as _random

    px, ws = [], []
    for r in history:
        if isinstance(r.get("price"), (int, float)):
            px.append(float(r["price"]))
            w = r.get("weight")
            ws.append(float(w) if isinstance(w, (int, float)) else 0.0)
    if len(px) < 3:
        return None
    rets = [px[i] / px[i - 1] - 1 for i in range(1, len(px))]
    base = ws[:-1]                    # t일 비중이 t→t+1 수익률에 노출된다
    rng = _random.Random(seed)
    finals = []
    for _ in range(n):
        perm = base[:]
        rng.shuffle(perm)
        eq, prev_w = 1.0, 0.0
        for w, r in zip(perm, rets):
            eq *= 1 + w * r
            eq -= eq * cost * abs(w - prev_w)      # 비중 변화분만 비용 지불
            prev_w = w
        finals.append(eq - 1.0)
    actual = actual_twr_pct / 100.0
    beaten = sum(1 for f in finals if f < actual)
    return round(beaten / n * 100, 1)


def run_daily_portfolio(targets=None, *, timeframe: str = "1d",
                        lookback: int = 400, state_dir: str = STATE_DIR,
                        require_real_data: bool = True,
                        use_champions: bool = True,
                        state_file: str = "portfolio_ALL.json") -> dict:
    """통합 8마일 계좌(8만원) — 전 종목에 분산해 한 계좌로 운용한다(실전과 가장 유사).

    각 종목의 챔피언 전략 비중을 종목 수로 나눠(자본 균등 슬라이스) 한
    PaperBroker 계좌에 담는다. 실데이터를 못 받은 종목은 그날 매매하지 않고
    기존 포지션을 유지한다(가짜 데이터로 매매 금지). 멱등: 같은 봉 재실행 무시.
    사이트 벤치마크('그냥 보유')를 위해 균등가중 지수(첫 관측일=100)를 가격으로
    기록한다.
    """
    from quant.broker import PaperBroker
    from quant.broker.base import Position
    from quant.data import get_provider
    from quant.risk import RiskManager
    from quant.utils.jsonio import atomic_write_json, cap_history

    from quant.markets import AUTO_TARGETS
    targets = targets or AUTO_TARGETS

    path = os.path.join(state_dir, "paper", state_file)
    mkt_tag = "portfolio" if use_champions else "portfolio_shadow"
    sym_tag = "ALL" if use_champions else "SHADOW"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    else:
        st = {"market": mkt_tag, "symbol": sym_tag,
              "start_cash": PORTFOLIO_START_CASH,
              "cash": PORTFOLIO_START_CASH, "positions": {}, "base_prices": {},
              "last_bar": None, "history": []}

    risk = RiskManager()
    prices, weights, skipped = {}, {}, []
    opens_after: dict = {}          # key → (체결봉, 시가) — 대기 주문 체결용
    last_bars: dict = {}
    last_dates = []
    pending = st.get("pending") or {}
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            df = get_provider(market).get_ohlcv(symbol, timeframe,
                                                limit=lookback)
            if df.empty or (require_real_data
                            and df.attrs.get("synthetic_fallback")):
                raise RuntimeError("실데이터 없음")
            if use_champions:
                strat = champion_strategy(market, symbol, state_dir)
            else:
                # 섀도 대조군 — 진화 없이 최초 기본 챔피언으로 고정
                from quant.live.retrain import DEFAULT_CHAMPION, build_strategy
                strat = build_strategy(DEFAULT_CHAMPION)
            signals = strat.generate_signals(df)
            weights[key] = float(risk.size_positions(df, signals).iloc[-1])
            prices[key] = float(df["close"].iloc[-1])
            st["base_prices"].setdefault(key, prices[key])
            last_bars[key] = str(df.index[-1])
            last_dates.append(str(df.index[-1])[:10])
            pend = pending.get(key)
            if pend and pend.get("decided_bar"):
                opens_after[key] = _first_bar_after(df, pend["decided_bar"])
        except Exception as exc:  # noqa: BLE001 — 해당 종목만 관망(포지션 유지)
            skipped.append(key)
            log.warning("포트폴리오 %s 스킵: %s", key, exc)
    if not prices:
        raise RuntimeError("포트폴리오: 전 종목 데이터 실패 — 기록하지 않음")

    bar = max(last_dates)
    if st.get("last_bar") == bar:
        log.info("포트폴리오: 같은 봉(%s)에 이미 실행됨 — 건너뜀", bar)
        return {"skipped": True, "last_bar": bar}

    broker = PaperBroker(cash=float(st["cash"]))
    for key, pos in st.get("positions", {}).items():
        if abs(float(pos.get("quantity", 0.0))) > 0:
            broker._positions[key] = Position(
                key, float(pos["quantity"]), float(pos.get("avg_price", 0.0)))
    n = len(targets)

    # ① 대기 주문 체결 — 주식은 결정 다음 세션의 '시가'에서만 체결(개장 갭 감수).
    #    평가 마크는 현재 종가 근사(스킵 종목은 평단가) — 체결가만 시가를 쓴다.
    fills = []
    for key, pend in list(pending.items()):
        fbar, fopen = opens_after.get(key, (None, None))
        if fopen is None:
            continue
        broker.fee = _fill_cost(key.split(":")[0])
        eq_now = broker.equity({**prices, key: fopen})
        broker.target_weight(key, float(pend["weight"]) / n, fopen, eq_now)
        fills.append({"key": key, "price": round(fopen, 6), "bar": fbar,
                      "weight": round(float(pend["weight"]), 4)})
        pending.pop(key, None)

    # ② 오늘의 결정 — 코인은 즉시 체결, 주식은 다음 시가 대기열로
    equity = broker.equity(prices)
    for key, w in weights.items():
        market = key.split(":")[0]
        if market in IMMEDIATE_FILL_MARKETS:
            broker.fee = _fill_cost(market)
            broker.target_weight(key, w / n, prices[key], equity)
        else:
            pending[key] = {"weight": round(w, 4),
                            "decided_bar": last_bars[key]}
    st["pending"] = pending
    equity = broker.equity(prices)

    # 균등가중 지수(첫 관측=100) — 사이트의 '그냥 보유' 벤치마크용
    idx = 100.0 * sum(prices[k] / st["base_prices"][k]
                      for k in prices) / len(prices)
    gross = sum(abs(w) for w in weights.values()) / n
    # 원금(시작금 + 매칭 입금)과 손익을 분리 — 입금이 수익처럼 보이면 안 된다
    principal = (float(st.get("start_cash", PORTFOLIO_START_CASH))
                 + sum(d["amount"] for d in st.get("deposits", [])))
    record = {"date": bar, "price": round(idx, 2), "weight": round(gross, 4),
              "equity": round(equity, 2),
              "return_pct": round((equity / principal - 1) * 100, 2),
              "principal": round(principal, 2),
              "pnl": round(equity - principal, 2),
              "hit_rate": None,
              "fills": fills,                      # 체결 현실성: 시가 체결 내역
              "code_sha": _code_sha(),
              "env": _env_fingerprint(),
              "accounting": ACCOUNTING_VERSION,
              "champion": {"symbols": n, "skipped": skipped}}
    record["twr_pct"] = time_weighted_return(
        st["history"] + [record], st.get("deposits", []),
        start_cash=float(st.get("start_cash", PORTFOLIO_START_CASH)))
    # 무작위 전략 1,000개 분포 대비 백분위 — 바이앤홀드보다 반박이 어려운 기준.
    # 같은 기간·같은 지수·같은 비용으로 '동전 던지기 전략'들을 돌려 우리 TWR가
    # 그 분포의 몇 %에 드는지 잰다(날짜 시드 → 재현 가능).
    record["random_pctile"] = random_strategy_percentile(
        st["history"] + [record], record["twr_pct"], seed=f"rand:{bar}")
    st["positions"] = {
        p.symbol: {"quantity": p.quantity, "avg_price": p.avg_price}
        for p in broker._positions.values() if abs(p.quantity) > 0}
    st.update({"cash": broker.get_cash(), "last_bar": bar})
    st["history"] = cap_history(st["history"] + [record])
    atomic_write_json(path, st)

    print(f"[{bar}] 포트폴리오({n}종목 분산) — 자산 {equity:,.2f} "
          f"({record['return_pct']:+.2f}%) · 총노출 {gross:.0%}"
          + (f" · 스킵 {len(skipped)}종목" if skipped else ""))
    return record


def run_daily_paper_all(targets=None, **kwargs) -> dict:
    """AUTO_TARGETS 전체를 순회 페이퍼 운용한다 — 한 종목 실패가 나머지를 안 막는다.

    전 종목이 실패했을 때만 예외를 올린다(조기 경보). 반환에 성공/실패 요약.
    """
    from quant.markets import AUTO_TARGETS
    targets = targets or AUTO_TARGETS

    ok, failed, records = [], {}, {}
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            records[key] = run_daily_paper(market, symbol, **kwargs)
            ok.append(key)
        except Exception as exc:  # noqa: BLE001
            failed[key] = str(exc)
            log.warning("페이퍼 실패 %s: %s", key, exc)
            print(f"⚠️ {key}: 페이퍼 실패 — {exc}")
    print(f"\n요약: 성공 {len(ok)} · 실패 {len(failed)}"
          + (f" ({', '.join(failed)})" if failed else ""))
    if targets and not ok:
        raise RuntimeError(f"전 종목 페이퍼 실패: {failed}")
    return {"ok": ok, "failed": failed, "records": records}


def weekly_summary(state_dir: str = STATE_DIR, days: int = 7) -> dict:
    """최근 7일(기록 기준) 요약 — 시장별 수익률·최고/최악일·챔피언 교체 이력.

    기준일은 벽시계가 아니라 '기록의 마지막 날짜'다 — 재실행해도 같은 결과가
    나오고(멱등), 데이터가 없는 날을 오늘로 착각하지 않는다.
    """
    from datetime import date, timedelta

    paper_dir = os.path.join(state_dir, "paper")
    files = (sorted(os.listdir(paper_dir))
             if os.path.isdir(paper_dir) else [])
    markets: dict = {}
    anchor: date | None = None
    states = []
    for name in files:
        if not name.endswith(".json"):
            continue
        with open(os.path.join(paper_dir, name), encoding="utf-8") as f:
            st = json.load(f)
        if st.get("history"):
            states.append(st)
            d = date.fromisoformat(st["history"][-1]["date"])
            anchor = d if anchor is None else max(anchor, d)
    if anchor is None:
        return {"period": None, "markets": {}, "swaps": []}
    start = anchor - timedelta(days=days - 1)

    for st in states:
        key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        hist = st["history"]
        window = [r for r in hist if date.fromisoformat(r["date"]) >= start]
        if not window:
            continue
        # 주간 수익 기준점: 창 직전 마지막 기록(없으면 창 첫 기록의 자산)
        idx0 = hist.index(window[0])
        base = hist[idx0 - 1]["equity"] if idx0 > 0 else window[0]["equity"]
        week_ret = (window[-1]["equity"] / base - 1) * 100 if base else 0.0
        days_chg = []
        prev = base
        for r in window:
            if prev:
                days_chg.append((r["date"], (r["equity"] / prev - 1) * 100))
            prev = r["equity"]
        best = max(days_chg, key=lambda x: x[1]) if days_chg else None
        worst = min(days_chg, key=lambda x: x[1]) if days_chg else None
        markets[key] = {
            "week_return_pct": round(week_ret, 2),
            "equity": window[-1]["equity"],
            "total_return_pct": window[-1].get("return_pct"),
            "n_days": len(window),
            "best_day": best and {"date": best[0], "pct": round(best[1], 2)},
            "worst_day": worst and {"date": worst[0], "pct": round(worst[1], 2)},
        }

    swaps = []
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if (rec.get("promoted")
                        and rec.get("asof")
                        and date.fromisoformat(rec["asof"]) >= start):
                    swaps.append({"asof": rec["asof"],
                                  "market": rec.get("market"),
                                  "symbol": rec.get("symbol"),
                                  "champion": rec.get("champion"),
                                  "strategy": rec.get("champion_strategy")})
    return {"period": [str(start), str(anchor)], "markets": markets,
            "swaps": swaps}


def format_weekly(summary: dict) -> str:
    """weekly_summary 결과를 사람이 읽는 한국어 요약으로 만든다(텔레그램/콘솔 공용)."""
    if not summary.get("markets"):
        return "📭 지난주 페이퍼 기록이 없습니다."
    a, b = summary["period"]
    lines = [f"🗓️ 주간 요약 ({a} ~ {b}) — 가상 8마일 챌린지"]
    for key, m in summary["markets"].items():
        sign = "🔺" if m["week_return_pct"] >= 0 else "🔻"
        line = (f"{sign} {key}: 주간 {m['week_return_pct']:+.2f}% · "
                f"자산 {m['equity']:,.0f} (누적 {m['total_return_pct']:+.2f}%)")
        if m.get("worst_day"):
            line += f" · 최악일 {m['worst_day']['date']} {m['worst_day']['pct']:+.2f}%"
        lines.append(line)
    if summary["swaps"]:
        for s in summary["swaps"]:
            lines.append(f"🔁 챔피언 교체: {s['market']}/{s['symbol']} → "
                         f"{s.get('strategy', '')} {s['champion']} ({s['asof']})")
    else:
        lines.append("🏆 챔피언 교체 없음 — 확실히 나은 후보가 없었다는 뜻(정상)")
    lines.append("⚠️ 페이퍼(모의) 운용 — 실제 돈이 아니며 수익 보장이 아닙니다.")
    return "\n".join(lines)


def write_docs_status(state_dir: str = STATE_DIR,
                      docs_path: str = os.path.join("docs", "status.json")) -> dict:
    """state/의 챔피언·페이퍼 기록을 사이트용 status.json 하나로 모은다.

    docs/는 push 때마다 Cloudflare Pages로 자동 배포되므로, 이 파일을 커밋하면
    사용자는 웹사이트만 열어도 매일의 결과를 본다(프로그램 실행 불필요).
    """
    from quant.utils.jsonio import atomic_write_json

    status: dict = {"champions": {}, "paper": {}, "updated": None, "swaps": [],
                    # 유튜브 라이브 주소 — 저장소 변수(QUANT_LIVE_URL)를 설정하면
                    # 사이트에 '라이브 보러가기' 버튼이 자동으로 나타난다
                    "live_url": os.getenv("QUANT_LIVE_URL") or None}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            for line in f.read().splitlines()[-400:]:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("promoted"):
                    # 사이트 차트의 '챔피언 교체' 마커용 — 진화의 서사를 새긴다
                    status["swaps"].append({
                        "date": rec.get("asof"),
                        "key": f"{rec.get('market')}:{rec.get('symbol')}",
                        "strategy": rec.get("champion_strategy")})
    champ_file = os.path.join(state_dir, "champions.json")
    if os.path.exists(champ_file):
        with open(champ_file, encoding="utf-8") as f:
            status["champions"] = json.load(f)

    paper_dir = os.path.join(state_dir, "paper")
    if os.path.isdir(paper_dir):
        for name in sorted(os.listdir(paper_dir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(paper_dir, name), encoding="utf-8") as f:
                st = json.load(f)
            hist = st.get("history", [])
            key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
            # 최대낙폭(MDD) — 수익률만 보여주는 화면은 반쪽짜리 정직이다
            peak, mdd = 0.0, 0.0
            for r in hist:
                eq = float(r.get("equity", 0.0))
                peak = max(peak, eq)
                if peak > 0:
                    mdd = min(mdd, eq / peak - 1)
            status["paper"][key] = {
                "start_cash": st.get("start_cash", START_CASH),
                "equity": (hist[-1]["equity"] if hist else st.get("cash")),
                "return_pct": (hist[-1].get("return_pct") if hist else 0.0),
                "mdd_pct": round(mdd * 100, 2),
                "history": hist[-90:],            # 사이트에는 최근 90일이면 충분
            }
            if st.get("market") == "portfolio":   # 8마일 챌린지(8만원 → 1억) 필드
                deposits = st.get("deposits", [])
                sc = float(st.get("start_cash", PORTFOLIO_START_CASH))
                principal = sc + sum(d["amount"] for d in deposits)
                eq_now = float(status["paper"][key]["equity"] or principal)
                status["paper"][key].update({
                    "goal": GOAL_KRW,
                    "principal": round(principal, 2),
                    "pnl": round(eq_now - principal, 2),
                    "twr_pct": time_weighted_return(hist, deposits,
                                                    start_cash=sc),
                    "deposits": deposits[-30:],
                })
            if hist:
                status["updated"] = max(status["updated"] or "", hist[-1]["date"])

    # 오늘의 시장 브리핑(표시 전용) — 있으면 사이트에도 싣는다
    from quant.live.briefing import load_briefing
    briefing = load_briefing(state_dir)
    if briefing and briefing.get("items"):
        status["briefing"] = briefing

    # 종목 한글 이름·선정 이유 — 사이트가 코드 대신 이름을 보여줄 수 있게
    from quant.markets import SYMBOL_INFO
    status["symbols"] = SYMBOL_INFO

    atomic_write_json(docs_path, status)
    print(f"🌐 사이트 상태 갱신: {docs_path} (마지막 기록 {status['updated']})")
    return status
