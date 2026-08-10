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

import numpy as np

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

# 무행동 밴드 — 목표 비중이 어제 대비 5%p 미만으로만 달라졌으면 리밸런싱을
# 생략한다. 확률·변동성의 미세한 흔들림이 만드는 잔조정은 기대수익 0에
# 왕복 수수료만 확정 지불하는 거래다. 청산(비중 0)은 밴드와 무관하게 실행.
REBALANCE_BAND = 0.05


def _risk_for(market: str):
    """시장별 연율화 계수를 반영한 RiskManager — 코인 365일, 주식 252거래일.

    연율화가 틀리면 변동성 타깃팅 배율이 주식에서 약 20% 어긋난다(√(365/252)).
    """
    from quant.risk import RiskManager
    from quant.risk.manager import RiskConfig
    ppy = 365 if market in ("crypto", "synthetic") else 252
    # vol_model="har": 후행 변동성 대신 HAR-RV 예측(50/50 수축)으로 사이징 —
    # 변동성 군집의 초입에서 먼저 비중을 줄인다(수익 장치가 아니라 복리 방어).
    return RiskManager(RiskConfig(periods_per_year=ppy, vol_model="har"))


def _last_proba(strategy) -> float | None:
    """전략(래퍼 포함)에서 마지막 봉의 ML 예측확률을 꺼낸다. 없으면 None.

    핫리로드 래퍼(_impl)·레짐/이벤트 래퍼(base)를 재귀로 벗겨 가며 찾는다 —
    기록된 확률은 설명 문장·신뢰도 곡선과 '같은 숫자'여야 한다(사후 검증 가능).
    """
    seen = 0
    while strategy is not None and seen < 6:
        p = getattr(strategy, "last_proba_", None)
        if p is not None:
            return float(p)
        strategy = getattr(strategy, "_impl", None) or getattr(
            strategy, "base", None)
        seen += 1
    return None


def _drift_psi(df) -> float | None:
    """최근 60일 수익률 분포의 PSI(기준: 그 이전 ~250일) — 레짐 이탈 감지.

    0.25 이상이면 '학습 시점과 시장이 달라졌다'는 경고 신호로 기록·알림한다.
    표본 부족이면 None(계산불가를 0으로 위장하지 않는다).
    """
    try:
        from quant.robustness import psi
        rets = df["close"].pct_change().dropna()
        if len(rets) < 130:
            return None
        recent = rets.iloc[-60:]
        ref = rets.iloc[-310:-60]
        v = psi(list(ref), list(recent))
        return round(float(v), 4) if v == v else None
    except Exception:  # noqa: BLE001 — 감시 실패가 본류를 막으면 안 된다
        return None


def _paper_path(market: str, symbol: str, state_dir: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{market}_{symbol}")
    return os.path.join(state_dir, "paper", f"{safe}.json")


def _all_paper_histories(state_dir: str) -> list:
    """전 종목 페이퍼 장부의 history 목록 — 확률대 적중률의 합산 표본 재료.

    종목별 25건 축적에는 한 달 이상 걸리므로, 그때까지는 전 종목 합산으로
    표본을 조기 확보한다(이질성 트레이드오프는 해설 문구에 명시). 포트폴리오
    통합 계좌 파일은 종목 확률이 없으므로 제외. 실패는 빈 목록(해설 재료일
    뿐 — 실패가 기록을 막으면 안 된다).
    """
    import glob as _glob
    out = []
    for pth in sorted(_glob.glob(os.path.join(state_dir, "paper", "*.json"))):
        if "portfolio" in os.path.basename(pth).lower():
            continue
        try:
            with open(pth, encoding="utf-8") as f:
                h = json.load(f).get("history")
            if isinstance(h, list) and h:
                out.append(h)
        except (OSError, ValueError):
            continue
    return out


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
    from quant.robustness.accuracy import directional_accuracy
    from quant.utils.jsonio import atomic_write_json, cap_history

    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=lookback)
    if df.empty:
        raise RuntimeError(f"{market}/{symbol}: 데이터 수신 실패")
    if require_real_data and df.attrs.get("synthetic_fallback"):
        raise RuntimeError(
            f"{market}/{symbol}: 실데이터 수신 실패 → 합성 폴백 감지. "
            "가짜 데이터로 페이퍼 기록을 오염시키지 않도록 중단합니다.")
    if market == "crypto":
        # 펀딩비 컬럼 — ML의 x_funding 피처 재료(실패 시 조용히 생략)
        from quant.data.funding import attach_funding
        df = attach_funding(df, symbol)
        from quant.data.openinterest import attach_open_interest
        df = attach_open_interest(df, symbol)
    if market == "kr_stock":
        from quant.data.krx import attach_krx_flows
        df = attach_krx_flows(df, symbol)
    from quant.data.crossasset import attach_cross_asset
    df = attach_cross_asset(df, market, symbol)

    path = _paper_path(market, symbol, state_dir)
    st = _load_paper(path)
    last_bar = str(df.index[-1])
    if st.get("last_bar") == last_bar:
        log.info("%s/%s: 같은 봉(%s)에 이미 실행됨 — 건너뜀", market, symbol, last_bar)
        return {"skipped": True, "last_bar": last_bar}

    strategy = champion_strategy(market, symbol, state_dir)
    signals = strategy.generate_signals(df)
    weight = float(_risk_for(market).size_positions(df, signals).iloc[-1])
    price = float(df["close"].iloc[-1])

    # 실적 가드 — 발표 ±1일 창에서는 비중 절반(미국 주식만). 발표일 갭 위험은
    # 하루짜리 방향 모델의 엣지가 가장 약한 지점이다. 쓴 캘린더는 state에
    # 캐시되고 발동 내역은 기록에 남는다(재현성·투명성).
    earnings_guard = None
    if market == "us_stock" and abs(weight) > 0:
        from datetime import date as _edate
        from quant.data.earnings import earnings_guard_factor
        ef, edate = earnings_guard_factor(
            symbol, _edate.fromisoformat(str(df.index[-1])[:10]),
            state_dir=state_dir)
        if edate and ef < 1.0:
            weight = float(weight * ef)
            earnings_guard = {"date": edate, "factor": ef}

    # 부분 켈리 상한 — 이 종목의 OOS(페이퍼) 통계가 30일 이상 쌓이면
    # ½켈리로 최대 비중을 제한한다(과대 베팅의 복리 벌칙 방어).
    kelly_cap = _kelly_cap_from_history(st.get("history") or [])
    if kelly_cap < 1.0:
        weight = float(np.clip(weight, -kelly_cap, kelly_cap))

    # 오늘 판단의 근거를 사람 말로 — 방송·사이트에 "새벽 판단 기준"으로 표시.
    # 원비중(위험 조절 전)과 이 종목 장부(확률대 과거 적중률), 전 종목 합산
    # 장부(종목 표본 25건 미달 시 폴백)를 함께 넘겨 상세 해설을 만든다.
    from quant.live.explain import explain_signal
    reason = explain_signal(champion_spec(market, symbol, state_dir), df,
                            weight, getattr(strategy, "_impl", None),
                            raw_weight=float(signals.iloc[-1]),
                            history=st.get("history") or [],
                            pooled_history=_all_paper_histories(state_dir))
    if earnings_guard:
        reason += (f" · 🛡 실적 가드: 발표({earnings_guard['date']}) 임박 → "
                   "비중 절반")
    # 의회(혼합) 운용 중이면 구성을 함께 — 리더 설명 + 의석 비중
    try:
        from quant.live.parliament import parliament_summary
        from quant.live.retrain import _key, load_champions
        entry = load_champions(state_dir).get(_key(market, symbol))
        ps = parliament_summary(entry) if entry else None
        if ps:
            reason += f" · 🏛 의회 운용: {ps}"
    except Exception:  # noqa: BLE001 — 표기 실패가 기록을 막으면 안 된다
        pass

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
            broker.target_weight(symbol, float(pending["weight"]), fopen,
                                 eq_open, rebalance_band=REBALANCE_BAND)
            fill = {"price": round(fopen, 6), "bar": fbar,
                    "weight": round(float(pending["weight"]), 4),
                    "decided_bar": pending["decided_bar"]}
            st["pending"] = None
    # ② 오늘의 결정 — 코인은 즉시 체결, 주식은 다음 시가 대기열에 올린다
    if market in IMMEDIATE_FILL_MARKETS:
        eq_now = broker.equity({symbol: price})
        broker.target_weight(symbol, weight, price, eq_now,
                             rebalance_band=REBALANCE_BAND)
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
        # 예측확률(ML 챔피언일 때) — 신뢰도 곡선("60%라고 한 날 실제 적중률")과
        # 설명 문장 대조의 원천 숫자. 서술은 이 숫자에서 기계 생성된다.
        "prob_up": _last_proba(strategy),
        # 드리프트 감시 — 최근 60일 수익률 분포가 기준 분포에서 벗어난 정도
        "drift_psi": _drift_psi(df),
        # 실적 가드 발동 흔적(발동 없으면 None) — 왜 비중이 절반인지의 답
        "earnings_guard": earnings_guard,
        # 부분 켈리 상한(1.0=비개입) — OOS 통계가 비중을 제한한 흔적
        "kelly_cap": round(kelly_cap, 4) if kelly_cap < 1.0 else None,
    }
    # 확률 보정 준비(표시 전용) — '보정 어긋남'이 표본 30건 이상에서 통계로
    # 확정된 확률대에 한해 경험 보정값을 병기한다. 사이징에는 개입하지 않음.
    try:
        from quant.live.calibration_guard import recalibrated_prob
        adj, active = recalibrated_prob(
            record["prob_up"], _all_paper_histories(state_dir))
        if active:
            record["prob_up_cal"] = round(float(adj), 4)
    except Exception:  # noqa: BLE001 — 보정 준비 실패가 기록을 막으면 안 된다
        pass
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


def _generation_info(state_dir: str) -> dict | None:
    """현재 구조 세대(피처셋 태그)의 관찰 일수 — 90일 시계를 숨기지 않는다.

    구조(피처·모델·사이징)가 바뀔 때마다 성과 통계의 시계는 사실상 0으로
    리셋된다. 이 사실을 사이트에 명시해, 과거 세대의 기록이 현재 구조의
    실적처럼 읽히는 착시를 막는다. since = 재학습 장부에서 현재 피처셋
    태그가 처음 등장한 날(기록 전이면 오늘 = 0일차).
    """
    try:
        import datetime as _dt
        from quant.strategies.ml import FEATURE_SET
        path = os.path.join(state_dir, "retrain_history.jsonl")
        since = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    if r.get("feature_set") == FEATURE_SET:
                        a = str(r.get("asof", ""))[:10]
                        if len(a) == 10 and (since is None or a < since):
                            since = a
        today = _dt.date.today()
        if since is None:
            since = today.isoformat()
        days = (today - _dt.date.fromisoformat(since)).days
        return {"feature_set": FEATURE_SET, "since": since,
                "days": max(0, days), "target_days": 90}
    except Exception:  # noqa: BLE001 — 표시 재료일 뿐
        return None


def _generation_archive(state: dict, since: str) -> dict | None:
    """통합 계좌 기록을 '이전 구조 / 현재 구조'로 갈라 각각의 TWR을 낸다.

    판정 시계의 짝: 세대 시작일(since) 이전 기록은 다른 구조의 실적이다.
    합산 수익률 하나로 보여주면 이전 세대의 성과가 현 구조의 실적처럼
    읽힌다 — 구간별 일수·TWR을 분리해 그 착시를 마저 없앤다.
    입금(매칭)은 날짜로 해당 구간에 귀속시켜 TWR 왜곡을 막는다.
    """
    try:
        hist = state.get("history") or []
        if not hist:
            return None
        i0 = next((i for i, r in enumerate(hist)
                   if str(r.get("date", "")) >= since), len(hist))
        prev_hist, cur_hist = hist[:i0], hist[i0:]
        if not prev_hist:
            return None                    # 전 기록이 현 세대 — 분리할 게 없다
        deposits = state.get("deposits") or []
        sc = float(state.get("start_cash", PORTFOLIO_START_CASH))
        prev_dep = [d for d in deposits if str(d.get("date", "")) < since]
        cur_dep = [d for d in deposits if str(d.get("date", "")) >= since]
        cur_start = float(prev_hist[-1].get("equity") or sc)
        out = {
            "prev_days": len(prev_hist),
            "prev_twr_pct": time_weighted_return(prev_hist, prev_dep,
                                                 start_cash=sc),
            "cur_days": len(cur_hist),
            "cur_twr_pct": (time_weighted_return(cur_hist, cur_dep,
                                                 start_cash=cur_start)
                            if cur_hist else 0.0),
        }
        return out
    except Exception:  # noqa: BLE001 — 표시 재료일 뿐
        return None


def _kelly_cap_from_history(history: list, fraction: float = 0.5,
                            floor: float = 0.25, min_days: int = 30) -> float:
    """페이퍼 장부(OOS)의 보유일 수익 통계로 부분 켈리 '상한'을 만든다.

    보유일(그날 비중≠0)의 다음날 자산 수익으로 승률·평균손익을 추정해
    ½켈리를 계산하고 [floor, 1.0]로 클립한다. 표본 min_days 미만이면
    1.0(비개입) — 잡음 통계 위의 켈리는 수학의 탈을 쓴 도박이다.
    인샘플 백테스트가 아니라 실제 페이퍼 기록이라 켈리의 전제(OOS)에 맞다.
    엣지 추정이 음수여도 floor 밑으로는 안 내린다 — '걸지 마라'의 판정은
    켈리가 아니라 오디션·킬스위치의 몫이다(역할 분리).
    """
    try:
        rets = []
        for a, b in zip(history, history[1:]):
            if abs(float(a.get("weight") or 0.0)) > 0:
                ea = float(a.get("equity") or 0.0)
                eb = float(b.get("equity") or 0.0)
                if ea > 0 and eb > 0:
                    rets.append(eb / ea - 1.0)
        if len(rets) < min_days:
            return 1.0
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r < 0]
        if not wins or not losses:
            return 1.0
        from quant.risk import kelly_fraction
        k = kelly_fraction(len(wins) / len(rets),
                           sum(wins) / len(wins), sum(losses) / len(losses))
        return float(max(floor, min(1.0, fraction * k)))
    except Exception:  # noqa: BLE001 — 상한 계산 실패 = 비개입(1.0)
        return 1.0


def _regime_breakdown(history: list, window: int = 20) -> dict | None:
    """레짐별 성과 분해 — 챔피언이 '어떤 장'에서 벌고 잃었는지의 정직한 답.

    레짐 정의: 장부의 균등가중 지수(price)가 최근 window일 이동평균 위(상승
    국면)/아래(하락 국면). 각 국면에서의 우리 일별 수익을 복리로 합산한다.
    상승장에서만 벌었다면 그건 시장 베타지 엣지가 아닐 수 있다 — 그 구분을
    데이터로 보여주는 게 목적이다. 표본 부족(window+5일 미만)이면 None.
    """
    try:
        rows = [(str(r.get("date")), float(r.get("price") or 0),
                 float(r.get("equity") or 0)) for r in history
                if r.get("price") and r.get("equity")]
        if len(rows) < window + 5:
            return None
        out = {"up": {"days": 0, "ret_pct": 1.0},
               "down": {"days": 0, "ret_pct": 1.0}}
        prices = [p for _, p, _ in rows]
        for i in range(window, len(rows)):
            ma = sum(prices[i - window:i]) / window
            regime = "up" if prices[i] >= ma else "down"
            prev_eq, eq = rows[i - 1][2], rows[i][2]
            if prev_eq > 0:
                out[regime]["days"] += 1
                out[regime]["ret_pct"] *= eq / prev_eq
        for v in out.values():
            v["ret_pct"] = round((v["ret_pct"] - 1) * 100, 2)
        out["window"] = window
        return out
    except Exception:  # noqa: BLE001 — 표시 재료일 뿐(실패가 기록을 막으면 안 된다)
        return None


def _hrp_slices(rets_map: dict, n_total: int) -> dict | None:
    """HRP(계층적 리스크 패리티) 슬라이스 — ERC의 상위 호환(추정 오차에 강함).

    데이터 준비 규약은 ERC와 동일(40일 이상 공통 표본, 2종목 이상). 가용
    종목들의 총 예산(k/n_total)을 HRP 비율로 나누고 과집중 상한(3/n_total)을
    적용한다. 퇴화 시 None — 호출자는 ERC → 균등 순으로 폴백한다.
    """
    import pandas as pd
    try:
        cols = {}
        for key, s in rets_map.items():
            s = s.dropna()
            if len(s) >= 40:
                s.index = pd.DatetimeIndex(s.index).normalize()
                cols[key] = s[~s.index.duplicated()]
        if len(cols) < 2:
            return None
        R = pd.DataFrame(cols).dropna()
        if len(R) < 40:
            return None
        from quant.live.hrp import hrp_weights
        w = hrp_weights(R)
        if not w:
            return None
        budget = len(R.columns) / n_total
        cap = 3.0 / n_total
        return {c: min(float(budget * wi), cap) for c, wi in w.items()}
    except Exception:  # noqa: BLE001
        return None


def _erc_slices(rets_map: dict, n_total: int) -> dict | None:
    """공분산 기반 위험기여도 균등(ERC) 슬라이스 — 자본 균등(1/n)의 상위 호환.

    비트코인 만원과 은행주 만원은 위험 기여가 5~10배 다르다 — 종목별 변동성만
    보는 것도 부족하다(위험자산은 같이 움직인다). 최근 90일 수익률의 공분산에서
    각 종목의 위험 기여가 같아지는 비중을 반복법으로 구해, 가용 종목들의 총
    예산(k/n_total)을 그 비율로 나눈다. 슬라이스 상한 3/n_total(집중 방지).
    표본이 부족하거나 계산이 퇴화하면 None — 호출자는 균등 배분으로 폴백한다.
    """
    import pandas as pd
    try:
        cols = {}
        for key, s in rets_map.items():
            s = s.dropna()
            if len(s) >= 40:
                s.index = pd.DatetimeIndex(s.index).normalize()
                cols[key] = s[~s.index.duplicated()]
        if len(cols) < 2:
            return None
        R = pd.DataFrame(cols).dropna()
        if len(R) < 40:
            return None
        cov = R.cov().values
        k = len(R.columns)
        w = np.ones(k) / k
        for _ in range(300):
            rc = w * (cov @ w)                 # 위험 기여
            if not np.isfinite(rc).all() or rc.sum() <= 0:
                return None
            w = w * np.sqrt(rc.mean() / np.maximum(rc, 1e-16))
            w = np.clip(w, 1e-6, None)
            w = w / w.sum()
        budget = len(R.columns) / n_total      # 가용 종목 수만큼의 자본 예산
        raw = {c: float(budget * wi) for c, wi in zip(R.columns, w)}
        cap = 3.0 / n_total                    # 한 종목 과집중 방지
        capped = {c: min(v, cap) for c, v in raw.items()}
        return capped
    except Exception:  # noqa: BLE001 — 배분 실패가 매매를 막으면 안 된다(균등 폴백)
        return None


def _xsec_tilt(weights: dict, lo: float = 0.75, hi: float = 1.25) -> dict:
    """횡단면 확신도 틸트 — 같은 위험예산 안에서 고확신 종목으로 자본을 기울인다.

    지금까지 배분(ERC)은 '위험'만 보고 종목을 나눴다 — 챔피언이 A는 확신
    100%, B는 확신 60%라고 말해도 두 종목의 자본 예산은 같았다. 이 틸트는
    각 챔피언의 |목표비중|(확신도)을 종목 간 '순위'로 바꿔 [lo, hi] 배수로
    매핑한다(꼴찌 lo배, 1등 hi배). 순위를 쓰는 이유: 종목마다 전략·보정이
    달라 확신도의 절대값은 비교 불가능하지만 순서는 비교 가능하다.
    동률은 평균 순위 — 유니버스 나열 순서가 배분을 좌우하면 안 된다.
    활성(|w|>0) 종목이 2개 미만이면 순위가 무의미하므로 전부 1.0.
    ⚠️ 이것은 '검증된 알파'가 아니라 배분 규칙이다. 배수는 호출자가 총예산
    보존으로 재정규화하며, 그날의 배수가 장부(xsec_tilt)에 남아 사후 검증
    가능하다. 확신도가 무정보라면 장기적으로 균등 배분과 다르지 않다.
    """
    active = {k: abs(float(w)) for k, w in weights.items() if abs(float(w)) > 0}
    if len(active) < 2:
        return {k: 1.0 for k in weights}
    order = sorted(active, key=lambda k: (active[k], k))   # 결정적 정렬
    n = len(order)
    # 동률 그룹에 평균 순위 부여
    rank: dict = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and active[order[j + 1]] == active[order[i]]:
            j += 1
        mean_rank = (i + j) / 2.0
        for kk in order[i:j + 1]:
            rank[kk] = mean_rank
        i = j + 1
    out = {}
    for k in weights:
        if k in rank:
            out[k] = lo + (hi - lo) * rank[k] / (n - 1)
        else:
            out[k] = 1.0                       # 관망 종목은 틸트 무의미(비중 0)
    return out


def _kill_switch_scale(prev: float, dd: float) -> float:
    """자동 킬스위치 — 낙폭 단계별 노출 축소와 '단계적' 복귀(히스테리시스).

    낙폭 -25% 이하: 전량 관망(0) · -15% 이하: 노출 절반(0.5).
    복귀는 한 번에 안 한다: 0 → (낙폭 -15% 안쪽 회복) 0.5 → (-10% 안쪽) 1.0.
    성과가 무너질 때 스스로 물러나는 규칙이 있다는 것 자체가
    '실전에 쓸 수 있는 시스템'의 증명이다.
    """
    if dd <= -0.25:
        return 0.0
    if dd <= -0.15:
        return 0.5 if prev > 0.0 else 0.0
    if dd <= -0.10:
        return max(0.5, prev) if prev >= 0.5 else 0.5
    return 1.0


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

    prices, weights, skipped = {}, {}, []
    opens_after: dict = {}          # key → (체결봉, 시가) — 대기 주문 체결용
    last_bars: dict = {}
    last_dates = []
    rets_map: dict = {}             # key → 최근 90일 수익률 — 위험 배분 재료
    earnings_guards: dict = {}      # key → 발표일 — 실적 가드 발동 흔적
    pending = st.get("pending") or {}
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            df = get_provider(market).get_ohlcv(symbol, timeframe,
                                                limit=lookback)
            if df.empty or (require_real_data
                            and df.attrs.get("synthetic_fallback")):
                raise RuntimeError("실데이터 없음")
            if market == "crypto":
                from quant.data.funding import attach_funding
                df = attach_funding(df, symbol)
                from quant.data.openinterest import attach_open_interest
                df = attach_open_interest(df, symbol)
            if market == "kr_stock":
                from quant.data.krx import attach_krx_flows
                df = attach_krx_flows(df, symbol)
            from quant.data.crossasset import attach_cross_asset
            df = attach_cross_asset(df, market, symbol)
            if use_champions:
                strat = champion_strategy(market, symbol, state_dir)
            else:
                # 섀도 대조군 — 진화 없이 최초 기본 챔피언으로 고정
                from quant.live.retrain import DEFAULT_CHAMPION, build_strategy
                strat = build_strategy(DEFAULT_CHAMPION)
            signals = strat.generate_signals(df)
            weights[key] = float(
                _risk_for(market).size_positions(df, signals).iloc[-1])
            # 실적 가드(미국 주식) — 발표 ±1일 창에서 비중 절반, 흔적 기록
            if market == "us_stock" and abs(weights[key]) > 0:
                from datetime import date as _edate

                from quant.data.earnings import earnings_guard_factor
                ef, edate = earnings_guard_factor(
                    symbol, _edate.fromisoformat(str(df.index[-1])[:10]),
                    state_dir=state_dir)
                if edate and ef < 1.0:
                    weights[key] = float(weights[key] * ef)
                    earnings_guards[key] = edate
            # 부분 켈리 상한 — 이 종목 개별 페이퍼 장부(OOS)의 통계 사용
            kcap = _kelly_cap_from_history(
                _load_paper(_paper_path(market, symbol, state_dir))
                .get("history") or [])
            if kcap < 1.0:
                weights[key] = float(np.clip(weights[key], -kcap, kcap))
            rets_map[key] = df["close"].pct_change().iloc[-90:]
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

    # 운영 설정(어드민 대시보드) — 일시정지·노출 배수. 파일이 없으면 정상 운용.
    from quant.utils.settings import load_settings
    settings = load_settings()
    paused = bool(settings["trading_paused"])
    if paused:
        # 신규 매매 중단: 보유 포지션은 유지하되 대기 주문은 폐기한다.
        # 폐기 이유 — 며칠 뒤 재개 시 '결정 당시 다음 시가'는 이미 과거라,
        # 그때 체결하면 옛 가격으로 사는 회계 왜곡(사실상 룩어헤드)이 된다.
        log.warning("⏸ 어드민 일시정지 — 신규 매매 중단, 대기 주문 %d건 폐기",
                    len(pending))
        pending = {}

    # ① 대기 주문 체결 — 주식은 결정 다음 세션의 '시가'에서만 체결(개장 갭 감수).
    #    평가 마크는 현재 종가 근사(스킵 종목은 평단가) — 체결가만 시가를 쓴다.
    fills = []
    for key, pend in list(pending.items()):
        fbar, fopen = opens_after.get(key, (None, None))
        if fopen is None:
            continue
        broker.fee = _fill_cost(key.split(":")[0])
        eq_now = broker.equity({**prices, key: fopen})
        sl = float(pend.get("slice") or (1.0 / n))   # 결정 당시의 ERC 슬라이스
        broker.target_weight(key, float(pend["weight"]) * sl, fopen, eq_now,
                             rebalance_band=REBALANCE_BAND / n)
        fills.append({"key": key, "price": round(fopen, 6), "bar": fbar,
                      "weight": round(float(pend["weight"]), 4),
                      "type": "시가"})           # 결정 다음 세션 시가 체결
        pending.pop(key, None)

    # ② 오늘의 결정 — 코인은 즉시 체결, 주식은 다음 시가 대기열로
    equity = broker.equity(prices)

    # 자동 킬스위치 — 계좌 낙폭 단계별 노출 축소·단계 복귀(히스테리시스).
    # 낙폭은 자산 고점 대비라 매칭 입금이 있으면 약간 보수적으로(빨리 회복한
    # 것처럼) 왜곡되지만, 입금은 드물고 방향은 안전한 쪽이다.
    peak_eq = max([float(r.get("equity", 0.0)) for r in st["history"]]
                  + [equity, 1e-9])
    drawdown = equity / peak_eq - 1
    risk_scale = _kill_switch_scale(float(st.get("risk_scale", 1.0)), drawdown)
    st["risk_scale"] = risk_scale
    if risk_scale < 1.0:
        log.warning("킬스위치: 낙폭 %.1f%% → 노출 %.0f%%로 제한",
                    drawdown * 100, risk_scale * 100)
    # 어드민 노출 배수·일시정지 — 킬스위치와 곱으로 적용(더 보수적인 쪽).
    # 기록되는 risk_scale(킬스위치 상태)은 유지하고 실효 노출만 줄인다.
    eff_scale = risk_scale * float(settings["exposure_scale"])
    if paused:
        eff_scale = 0.0

    # 위험 배분 슬라이스 — HRP(상관 추정 오차에 강함) → ERC → 균등 폴백 사다리
    hrp = _hrp_slices(rets_map, n)
    erc = None if hrp else _erc_slices(rets_map, n)
    slices = hrp or erc or {k: 1.0 / n for k in weights}
    alloc_method = "hrp" if hrp else ("erc" if erc else "equal")
    # 횡단면 확신도 틸트 — ERC(위험만 봄) 위에 '챔피언 확신도 순위'를 곱해
    # 자본을 고확신 종목으로 기울인다. 총예산 보존 재정규화 후 과집중 상한
    # (3/n)을 다시 적용한다(상한 초과분은 재분배하지 않고 버림 — 보수적).
    tilt = _xsec_tilt(weights)
    budget = sum(slices.get(k, 1.0 / n) for k in weights)
    tilted = {k: slices.get(k, 1.0 / n) * tilt.get(k, 1.0) for k in weights}
    tot = sum(tilted.values())
    if budget > 0 and tot > 0:
        cap = 3.0 / n
        slices = {k: min(v * budget / tot, cap) for k, v in tilted.items()}
    n_orders_before = len(getattr(broker, "order_log", []))
    for key, w in weights.items():
        market = key.split(":")[0]
        sl = slices.get(key, 1.0 / n)
        eff = w * eff_scale                    # 킬스위치×어드민 배수 반영 비중
        if paused:
            continue                           # 일시정지: 신규 주문 없음(포지션 유지)
        if market in IMMEDIATE_FILL_MARKETS:
            broker.fee = _fill_cost(market)
            # 밴드도 슬라이스 크기에 비례 — 종목 간 공평
            broker.target_weight(key, eff * sl, prices[key], equity,
                                 rebalance_band=REBALANCE_BAND / n)
        else:
            pending[key] = {"weight": round(eff, 4), "slice": round(sl, 5),
                            "decided_bar": last_bars[key]}
    st["pending"] = pending
    # 코인 즉시 체결 내역 — "오늘 얼마에 사고팔았나"를 사이트가 보여줄 재료.
    # 주식 시가 체결(fills 위쪽)과 함께 그날 기록에 남는다.
    for o in getattr(broker, "order_log", [])[n_orders_before:]:
        fills.append({"key": o.symbol, "price": round(float(o.price), 6),
                      "bar": last_bars.get(o.symbol, ""),
                      "side": o.side, "type": "즉시"})
    equity = broker.equity(prices)

    # 균등가중 지수(첫 관측=100) — 사이트의 '그냥 보유' 벤치마크용
    idx = 100.0 * sum(prices[k] / st["base_prices"][k]
                      for k in prices) / len(prices)
    gross = sum(abs(w) * eff_scale * slices.get(k, 1.0 / n)
                for k, w in weights.items())
    # 원금(시작금 + 매칭 입금)과 손익을 분리 — 입금이 수익처럼 보이면 안 된다
    principal = (float(st.get("start_cash", PORTFOLIO_START_CASH))
                 + sum(d["amount"] for d in st.get("deposits", [])))
    record = {"date": bar, "price": round(idx, 2), "weight": round(gross, 4),
              "equity": round(equity, 2),
              "return_pct": round((equity / principal - 1) * 100, 2),
              "principal": round(principal, 2),
              "pnl": round(equity - principal, 2),
              "hit_rate": None,
              "fills": fills,                      # 체결 현실성: 시가·즉시 체결 내역
              # 예약 주문 — 오늘 새벽 결정됐고 '다음 장 시가'에 체결될 것들.
              # 사이트가 "내일 뭘 얼마나 살 예정인가"를 보여줄 재료.
              "pending_next_open": {k: round(float(p["weight"])
                                             * float(p.get("slice") or 1.0 / n), 4)
                                    for k, p in pending.items()},
              "code_sha": _code_sha(),
              "env": _env_fingerprint(),
              "accounting": ACCOUNTING_VERSION,
              # 킬스위치·배분의 흔적 — 그날 왜 노출이 줄었는지 장부로 남는다
              "risk_scale": risk_scale,
              # 어드민 개입의 흔적 — 일시정지·노출 배수는 숨기지 않고 기록한다
              "paused": paused,
              "exposure_scale": float(settings["exposure_scale"]),
              "drawdown_pct": round(drawdown * 100, 2),
              "alloc": {k: round(v, 4) for k, v in slices.items()},
              "alloc_method": alloc_method,   # hrp | erc | equal — 폴백 흔적
              # 실적 가드 발동 종목(있을 때만) — 발표 임박으로 비중 절반
              "earnings_guard": earnings_guards or None,
              # 횡단면 확신도 틸트 배수 — 그날 왜 이 종목에 더 실렸는지의 흔적
              "xsec_tilt": {k: round(v, 3) for k, v in tilt.items()},
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
    auditions = {"runs": 0, "candidates": 0, "promoted": 0}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not rec.get("asof"):
                    continue
                try:
                    in_window = date.fromisoformat(rec["asof"]) >= start
                except ValueError:
                    continue
                if not in_window:
                    continue
                # 이번 주 오디션 통계 — 몇 명이 도전해 몇 명이 승격했나
                auditions["runs"] += 1
                auditions["candidates"] += int(rec.get("n_candidates") or 0)
                if rec.get("promoted"):
                    auditions["promoted"] += 1
                    swaps.append({"asof": rec["asof"],
                                  "market": rec.get("market"),
                                  "symbol": rec.get("symbol"),
                                  "champion": rec.get("champion"),
                                  "strategy": rec.get("champion_strategy")})

    # 시스템 건강 — 수익률 밖의 상태(판정 시계·체결 가정·킬스위치)를 함께.
    # 주간 요약은 "이번 주 시스템 건강 보고서"다 — 숫자 자랑이 아니라.
    health: dict = {"auditions": auditions}
    gen = _generation_info(state_dir)
    if gen:
        health["generation"] = gen
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            health["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 건강 항목 실패가 요약을 막으면 안 된다
        pass
    for st in states:
        if st.get("market") == "portfolio" and st.get("history"):
            last = st["history"][-1]
            rs = last.get("risk_scale")
            if rs is not None and float(rs) < 1.0:
                health["killswitch"] = {
                    "risk_scale": float(rs),
                    "drawdown_pct": last.get("drawdown_pct")}
    return {"period": [str(start), str(anchor)], "markets": markets,
            "swaps": swaps, "health": health}


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

    # 시스템 건강 보고 — 수익률 밖의 상태를 사이트 안 열어도 알 수 있게
    h = summary.get("health") or {}
    g = h.get("generation")
    if g:
        lines.append(f"🕰 판정 시계: 구조 {g['feature_set']} 관찰 "
                     f"{g['days']}일차/{g['target_days']}일 — 시계가 다 돌기 "
                     f"전의 수익률은 판정 근거가 아닙니다")
    a = h.get("auditions")
    if a and a["runs"]:
        lines.append(f"🎭 오디션: 이번 주 {a['runs']}회 · 후보 "
                     f"{a['candidates']}명 중 승격 {a['promoted']}회")
    fc = h.get("fill_check")
    if fc:
        for mk, r in (fc.get("markets") or {}).items():
            mark = " ⚠️ 가정 초과(백테스트 낙관 의심)" if r["optimistic"] else ""
            lines.append(f"🧾 체결 검증 {mk}: 불리 갭 평균 "
                         f"{r['mean_adverse_bp']:+.1f}bp vs 가정 "
                         f"{r['assumed_bp']:.1f}bp (표본 {r['n']}건){mark}")
    ks = h.get("killswitch")
    if ks:
        lines.append(f"🛡 킬스위치 발동 중: 노출 {ks['risk_scale'] * 100:.0f}%"
                     + (f" (낙폭 {ks['drawdown_pct']}%)"
                        if ks.get("drawdown_pct") is not None else ""))
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
                    "retrain_recent": [],
                    # 유튜브 라이브 주소 — 저장소 변수(QUANT_LIVE_URL)를 설정하면
                    # 사이트에 '라이브 보러가기' 버튼이 자동으로 나타난다
                    "live_url": os.getenv("QUANT_LIVE_URL") or None}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for line in lines[-400:]:
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
        for line in lines[-120:]:
            # 탈락자 아카이브 — 몇 명이 도전해 몇 명이 떨어졌는지 그대로 공개.
            # 다중검정 정직성(운 좋은 승자를 얼마나 걸렀는가)의 시각화 재료.
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            status["retrain_recent"].append({
                "asof": rec.get("asof"),
                "key": f"{rec.get('market')}:{rec.get('symbol')}",
                "promoted": bool(rec.get("promoted")),
                "n_candidates": rec.get("n_candidates"),
                "trials_total": rec.get("trials_total")})
    champ_file = os.path.join(state_dir, "champions.json")
    if os.path.exists(champ_file):
        with open(champ_file, encoding="utf-8") as f:
            status["champions"] = json.load(f)

    paper_dir = os.path.join(state_dir, "paper")
    pf_state = None                       # 통합 계좌 원본(세대별 분해 재료)
    if os.path.isdir(paper_dir):
        for name in sorted(os.listdir(paper_dir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(paper_dir, name), encoding="utf-8") as f:
                st = json.load(f)
            if st.get("market") == "portfolio":
                pf_state = st
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
                rb = _regime_breakdown(hist)
                if rb:                             # 레짐별 성과 분해(투명성)
                    status["paper"][key]["regime_breakdown"] = rb
            if hist:
                status["updated"] = max(status["updated"] or "", hist[-1]["date"])

    # 오늘의 시장 브리핑(표시 전용) — 있으면 사이트에도 싣는다
    from quant.live.briefing import load_briefing
    briefing = load_briefing(state_dir)
    if briefing and briefing.get("items"):
        status["briefing"] = briefing

    # 오늘의 거시(FRED, 표시 전용) — 키 없으면 조용히 생략
    try:
        from quant.live.macro_brief import macro_summary
        m = macro_summary()
        if m:
            status["macro"] = m
    except Exception:  # noqa: BLE001 — 브리핑 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 판정 시계 — 현재 구조 세대의 관찰 일수(구조가 바뀌면 0일부터 다시)
    gen = _generation_info(state_dir)
    if gen:
        # 세대별 기록 아카이브 — 이전 구조 기록을 현 구조 실적과 분리(착시 제거)
        if pf_state:
            arch = _generation_archive(pf_state, gen["since"])
            if arch:
                gen["archive"] = arch
        status["generation"] = gen

    # 체결 가정 검증(표시 전용) — 실측 개장 갭 vs 백테스트 슬리피지 가정.
    # 실측이 가정보다 불리하면 그 사실이 그대로 사이트에 공개된다.
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            status["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 검증 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 종목 한글 이름·선정 이유 — 사이트가 코드 대신 이름을 보여줄 수 있게
    from quant.markets import SYMBOL_INFO
    status["symbols"] = SYMBOL_INFO

    atomic_write_json(docs_path, status)
    print(f"🌐 사이트 상태 갱신: {docs_path} (마지막 기록 {status['updated']})")

    # 플래그 파수꾼 — 새로 켜진 자기 고발 플래그(낙관 의심·보정 어긋남·
    # 판정 시계)를 알림 채널(디스코드 등)로도 발송한다. 이미 켜진 건 조용.
    try:
        from quant.live.flag_watch import check_and_notify_flags
        new_flags = check_and_notify_flags(status, state_dir)
        if new_flags:
            print(f"🚩 새 플래그 알림 발송: {', '.join(new_flags)}")
    except Exception:  # noqa: BLE001 — 알림 실패가 사이트 갱신을 막으면 안 된다
        pass
    return status
