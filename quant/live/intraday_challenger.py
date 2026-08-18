"""장중 도전자 — **같은 규칙을 더 자주 돌리면 정말 더 버는가**를 재는 실험.

⚠️ 왜 이 파일이 생겼나 (2026-08-18, 사장님 지시).

    "보조 지표와 여러가지 차트와 다양한 조건을 기준으로 매매하는 건
     만들어뒀잖아. 그걸 보고 실시간으로 매매를 해야지."
    "무조건 수익률이 우선이 되어야 하기 때문에 매매 빈도는 상관없어.
     실시간으로 단타 매매를 하는 퍼포먼스도 보여져야 한다고 생각해."

    맞는 질문이고, 답은 **믿음이 아니라 측정**이어야 한다. 거래를 늘리면
    비용(수수료·슬리피지)은 확실하게 늘고 수익은 불확실하게 늘어난다 —
    장중 빈도가 그 비용을 이기는지는 아무도 모르므로, 여기서 잰다.

⚠️ **이 트랙은 본 계좌와 완전히 분리된다.** 세 가지 봉인:

    ① 자기 장부만 쓴다(state/intraday/). 본 계좌 장부(state/paper)는
       읽지도 쓰지도 않는다 — 90일 공개 측정에 한 글자도 섞이면 그
       측정은 거짓이 된다.
    ② 통화는 USDT 하나다. 원화 환산을 하지 않는다 — 감사 254(통화 혼합
       사고)의 재발 지점을 아예 만들지 않는다. 본 계좌와의 비교는 금액이
       아니라 **퍼센트 수익률**로만 한다.
    ③ 판단 규칙은 여기 다시 적지 않는다(FROZEN_IDEAS ①). 챔피언 스펙과
       비용 모델을 실전 함수에서 **빌려 온다** — 같은 규칙·같은 비용으로
       빈도만 다르게 돌려야 "빈도의 효과"만 분리돼 측정된다.

⚠️ 정직한 한계 (산출물에도 그대로 실린다):

    - 가상 자금이다. 실제 돈이 아니고 체결 호가·유동성을 겪지 않는다.
    - '15분마다'는 예약일 뿐이다. 실측 간격은 회차 기록이 말한다
      (공용 러너는 촘촘한 cron을 크게 민다 — 감사 267 실측 최악 558분).
    - 챔피언 파라미터는 일봉에서 뽑혔다. 1시간봉에 그대로 적용하는 것
      자체가 이 실험의 가설이다 — 검증된 전략이 아니다.
    - 시세를 실데이터로 못 받은 종목은 그 회차를 건너뛰고 그렇게 적는다.
      합성 폴백 시세로 가짜 체결을 만들지 않는다.
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.intraday")

# 운영 중인 코인 5종 — quant.markets의 운영 유니버스와 같은 종목.
UNIVERSE = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

TIMEFRAME = "1h"            # 장중 봉 — 일봉 챔피언 규칙을 이 빈도로 돌린다
LOOKBACK_BARS = 800         # 오디션과 같은 깊이의 창
MIN_BARS = 60               # 이보다 얇으면 판단하지 않는다

START_CASH_USDT = 10_000.0  # 가상 시드(USDT). 본 계좌(원화)와 절대 섞지 않는다.

# 잔돈 매매 금지 — 비용이 우위를 갉아먹는 것을 재는 실험에서, 회차마다
# 몇 달러씩 부스러기 매매를 하면 비용만 쌓이고 신호는 안 바뀐 것이다.
MIN_TRADE_FRAC = 0.005      # 자산의 0.5% 미만 조정은 보류
MIN_TRADE_USDT = 10.0

# 예약 주기(분) — guard.yml의 cron과 같다. 실측은 회차 기록이 말한다.
BOOKED_INTERVAL_MINUTES = 15

ROUNDS_KEEP = 2000          # 회차 기록 보존 개수(15분 간격 약 20일치)
CURVE_KEEP = 500            # 공개 JSON에 싣는 자산 곡선 길이

STATE_FILE = "challenger.json"
KIND = "challenger-experiment"

HONEST_LIMITS = [
    "가상 자금(USDT)입니다 — 실제 돈이 아니고, 실제 호가·유동성을 겪지 않습니다",
    "비용은 실전 오디션과 같은 모델(수수료+슬리피지)로 매 거래에 뺐지만, "
    "실측 체결과 다를 수 있습니다",
    "'15분마다'는 예약일 뿐이며 실제 간격은 실측(observed_gap_minutes)이 "
    "말합니다 — 공용 러너는 예약을 크게 밀 수 있습니다",
    "챔피언 파라미터는 일봉에서 뽑혔습니다 — 1시간봉 적용 자체가 이 실험의 "
    "가설이고, 검증된 전략이 아닙니다",
    "본 계좌(100만 챌린지)와 완전히 분리돼 있고 그 판단에 쓰이지 않습니다 — "
    "비교는 같은 기간 퍼센트 수익률로만 합니다",
]


def _dir(state_dir: str) -> str:
    return os.path.join(state_dir, "intraday")


def _path(state_dir: str) -> str:
    return os.path.join(_dir(state_dir), STATE_FILE)


def load_state(state_dir: str = "state") -> dict:
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, json.JSONDecodeError):
        st = {}
    st.setdefault("cash", START_CASH_USDT)
    st.setdefault("start_cash", START_CASH_USDT)
    st.setdefault("currency", "USDT")
    st.setdefault("positions", {})
    st.setdefault("rounds", [])
    st.setdefault("cost_paid", 0.0)
    return st


def observed_gap_minutes(rounds: list[dict]) -> float | None:
    """회차 기록에서 **실제로 관측된 최악 간격**(분). 못 재면 None.

    guard.py와 같은 원칙 — 설정한 주기가 아니라 일어난 일을 말한다.
    """
    import datetime as dt

    stamps = []
    for r in rounds:
        try:
            stamps.append(dt.datetime.fromisoformat(
                str(r.get("time", "")).replace("Z", "+00:00")))
        except ValueError:
            continue
    if len(stamps) < 2:
        return None
    stamps.sort()
    gaps = [(b - a).total_seconds() / 60.0
            for a, b in zip(stamps, stamps[1:]) if b > a]
    return max(gaps) if gaps else None


def _champion_factory(state_dir: str):
    """챔피언 규칙을 **빌려 오는** 기본 공장 — 재작성하지 않는다."""
    def make(symbol: str):
        from quant.live.retrain import build_strategy, champion_spec
        return build_strategy(champion_spec("crypto", symbol, state_dir))
    return make


def _fetch_real(symbol: str):
    """실데이터 1h봉. 합성 폴백이면 None — 가짜 시세로 체결을 만들지 않는다."""
    from quant.data.crypto import CryptoDataProvider
    df = CryptoDataProvider().get_ohlcv(symbol, timeframe=TIMEFRAME,
                                        limit=LOOKBACK_BARS)
    if df is None or len(df) == 0 or not df.attrs.get("source"):
        return None
    return df


def confirmed_bars(df, now_iso: str):
    """**닫힌 봉만** 남긴다 — 같은 회차를 언제 다시 돌려도 같은 판단.

    ⚠️ 왜 필요한가 (2026-08-18 자체 감사). 거래소는 '지금 만들어지는 중'인
       마지막 봉도 내려준다. 그 봉은 매 순간 바뀌므로, 그것으로 판단하면
       같은 회차를 10분 뒤 재현했을 때 **다른 결정**이 나온다 — 이 저장소의
       재현성 원칙(모든 결정은 값으로 재현 가능)과 정면 충돌한다.
       봉의 시각은 여는 시각이므로, 여는 시각+봉 길이가 지금보다 뒤면
       아직 닫히지 않은 봉이다.
    """
    import datetime as dt

    import pandas as pd

    now = dt.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    if now.tzinfo is not None:
        now = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    keep = (idx + pd.Timedelta(TIMEFRAME)) <= now
    return df[list(keep)]


def hold_baseline_pct(st: dict) -> float | None:
    """같은 종목을 첫 회차 가격에 사서 **그냥 들고만 있었다면** 몇 %인가.

    실험 데이터 안에서만 계산한다(본 계좌 장부를 읽지 않는다). 첫 회차에
    가격이 없던 종목은 비교에서 빠지고, 그 사실은 표본 크기로 드러난다.
    """
    first = st.get("first_prices") or {}
    last = st.get("last_prices") or {}
    rets = [float(last[s]) / float(first[s]) - 1.0
            for s in first if s in last and float(first[s]) > 0]
    if not rets:
        return None
    return round(sum(rets) / len(rets) * 100, 4)


# 판정 기준 — **결과를 보기 전에** 등록한다(2026-08-18). 기준을 나중에
# 정하면 좋은 구간만 골라 "이겼다"고 말하는 유혹이 생기고, 그 순간 이
# 실험은 선택 편향 없는 공개 실험이라는 정체성을 잃는다.
PREREGISTERED_JUDGEMENT = {
    "registered_on": "2026-08-18",
    "min_days": 90,
    # 등록 당일의 정직한 수정 — 숨기지 않고 이 자리에 그대로 공개한다.
    "amended": {
        "on": "2026-08-18",
        "what": "최소 관찰 기간 30일 → 90일",
        "why": "외부 검토 지적: 두 트랙의 성과 차이는 수익률 차이라 "
               "봉 수가 아니라 기간이 지배한다. 30일 신뢰구간은 폭이 넓어 "
               "진짜 우위를 놓칠 확률과 우연을 우위로 읽을 확률이 둘 다 "
               "높다. 첫 기록 반나절 시점(결과가 쌓이기 전)에 고친다 — "
               "지금 고치면 정직한 수정이고 30일 뒤에 고치면 골대 이동이다. "
               "30일 시점에는 중간 참고 판독만 하고 확정 판정은 90일이다.",
    },
    "criteria": [
        "관찰 90일 이상 — 충족 전에는 어떤 승패 판정도 내리지 않는다"
        "(30일 시점은 중간 참고 판독만)",
        "비용을 뺀 누적 수익률이 같은 기간 본 계좌(하루 1회 판단)보다 높다",
        "일별 수익률 차이의 95% 신뢰구간이 0을 배제한다 — 우연으로 "
        "설명되는 차이는 무승부다",
        "실험의 최대 낙폭이 같은 기간 본 계좌의 1.5배를 넘지 않는다 — "
        "수익이 위험을 사서 온 것이면 승리가 아니다",
    ],
    "note": "이 기준은 첫 기록이 쌓이기 전에 등록했고 바꾸지 않는다. "
            "바꿔야 한다면 그 사실과 이유를 이 자리에 함께 공개한다.",
}


def mark_equity(st: dict, prices: dict) -> float:
    """지금 가격으로 잰 자산. 가격을 못 받은 보유분은 **직전 표시 가격**을 쓴다."""
    eq = float(st["cash"])
    last = st.get("last_prices") or {}
    for sym, qty in (st.get("positions") or {}).items():
        px = prices.get(sym, last.get(sym))
        if px:
            eq += float(qty) * float(px)
    return eq


def run_intraday_round(now_iso: str, *, state_dir: str = "state",
                       docs_dir: str = "docs", data: dict | None = None,
                       strategy_factory=None) -> dict:
    """장중 한 회차 — 신호를 다시 재고, 문턱을 넘는 조정만 비용을 물고 체결.

    시각을 인자로 받는 이유: 이 저장소는 숨은 시계 입력을 쓰지 않는다.
    data/strategy_factory 주입은 검사용이다 — 실전 기본값은 실데이터와
    챔피언 규칙이다.
    """
    from quant.live.daily import measured_cost_model

    st = load_state(state_dir)
    factory = strategy_factory or _champion_factory(state_dir)
    cost = measured_cost_model("crypto", state_dir)
    per_side = float(cost.fee + cost.slippage)   # 편도, 회전율 대비

    prices: dict[str, float] = {}
    signals: dict[str, float | None] = {}
    skipped: dict[str, str] = {}
    bar_times: dict[str, str] = {}
    for sym in UNIVERSE:
        df = (data or {}).get(sym) if data is not None else _fetch_real(sym)
        if df is not None:
            # 닫힌 봉만 — 미완성 봉으로 판단하면 회차가 재현 불가능해진다.
            df = confirmed_bars(df, now_iso)
        if df is None or len(df) < MIN_BARS:
            signals[sym] = None
            skipped[sym] = ("실데이터 시세를 받지 못함" if df is None
                            else f"닫힌 봉 부족({len(df)}<{MIN_BARS})")
            continue
        prices[sym] = float(df["close"].iloc[-1])
        bar_times[sym] = str(df.index[-1])       # 재현 지문 — 어느 봉으로 판단했나
        try:
            sig = float(factory(sym).generate_signals(df).iloc[-1])
        except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 회차를 못 죽인다
            signals[sym] = None
            skipped[sym] = f"신호 계산 실패: {exc}"
            continue
        signals[sym] = max(0.0, min(1.0, sig))   # 숏·레버리지 없음

    equity = mark_equity(st, prices)
    # 그냥 보유 기준선 — 첫 회차 가격을 고정해 둔다(실험 데이터 안에서만).
    if prices and not st.get("first_prices"):
        st["first_prices"] = dict(prices)
    # 실전과 같은 킬스위치를 **빌려** 건다(FROZEN_IDEAS ①) — 브레이크 없는
    # 실험 계좌는 폭락장에서 본 계좌와 다른 조건으로 달리게 되고, 그러면
    # 성적 차이가 '빈도의 효과'가 아니라 '브레이크 유무의 효과'가 된다.
    from quant.live.daily import _kill_switch_scale
    from quant.live.ledger_basics import drawdown_from_index
    peak = max(float(st.get("peak_equity") or 0.0), equity)
    st["peak_equity"] = peak
    # 낙폭도 공용 헬퍼로 잰다 — 직접 적으면 언젠가 실전과 갈라진다(감사가
    # 실제로 이 자리를 잡아냈다. 위기 재생 때와 같은 실수, 같은 교훈).
    dd = drawdown_from_index([peak, equity]) if peak > 0 else 0.0
    scale = _kill_switch_scale(float(st.get("risk_scale", 1.0)), dd)
    st["risk_scale"] = scale

    trades: list[dict] = []
    slice_budget = equity / len(UNIVERSE)        # 고정 균등 슬라이스
    for sym in UNIVERSE:
        sig = signals.get(sym)
        px = prices.get(sym)
        if sig is None or not px:
            continue
        cur_qty = float((st["positions"] or {}).get(sym, 0.0))
        delta = slice_budget * sig * scale - cur_qty * px  # 목표 − 현재 (USDT)
        if abs(delta) < max(MIN_TRADE_USDT, MIN_TRADE_FRAC * equity):
            continue
        fee = abs(delta) * per_side
        if delta > 0:
            # 레버리지 금지선 — 현금이 모자라면 살 수 있는 만큼만 산다.
            afford = st["cash"] / (1.0 + per_side)
            if delta > afford:
                delta = afford
                fee = abs(delta) * per_side
            if delta < max(MIN_TRADE_USDT, MIN_TRADE_FRAC * equity):
                continue
        qty = delta / px
        st["cash"] = float(st["cash"]) - delta - fee
        st["positions"][sym] = cur_qty + qty
        if abs(st["positions"][sym]) * px < 1e-6:
            st["positions"].pop(sym, None)
        st["cost_paid"] = float(st["cost_paid"]) + fee
        trades.append({"symbol": sym, "side": "buy" if delta > 0 else "sell",
                       "notional": round(delta, 2), "price": px,
                       "cost": round(fee, 4), "signal": round(sig, 4)})

    equity_after = mark_equity(st, prices)
    last = dict(st.get("last_prices") or {})
    last.update(prices)
    st["last_prices"] = last
    rec = {"time": str(now_iso), "equity": round(equity_after, 2),
           "signals": {k: (round(v, 4) if v is not None else None)
                       for k, v in signals.items()},
           "bar_times": bar_times,               # 재현 지문 — 판단에 쓴 마지막 닫힌 봉
           "trades": trades}
    if scale < 1.0:
        rec["kill_switch"] = {"drawdown": round(dd, 4), "scale": scale}
    if skipped:
        rec["skipped"] = skipped
    st["rounds"] = (st.get("rounds") or [])[-(ROUNDS_KEEP - 1):] + [rec]

    os.makedirs(_dir(state_dir), exist_ok=True)
    from quant.utils.jsonio import atomic_write_json
    atomic_write_json(_path(state_dir), st)
    write_public_report(st, docs_dir=docs_dir)
    verdict = {"time": str(now_iso), "equity": round(equity_after, 2),
               "trades": len(trades), "skipped": len(skipped),
               "cost_paid": round(float(st["cost_paid"]), 2),
               "return_pct": round((equity_after / float(st["start_cash"]) - 1)
                                   * 100, 4)}
    log.info("🏃 장중 도전자 — 자산 %.2f USDT · 체결 %d건 · 건너뜀 %d종목",
             equity_after, len(trades), len(skipped))
    return verdict


def _elapsed_days(rounds: list[dict]) -> float | None:
    """첫 회차부터 마지막 회차까지 며칠 지났나 — 판정 최소 기간의 진도."""
    import datetime as dt

    if len(rounds) < 2:
        return 0.0 if rounds else None
    try:
        a = dt.datetime.fromisoformat(
            str(rounds[0]["time"]).replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(
            str(rounds[-1]["time"]).replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return None
    return round((b - a).total_seconds() / 86400.0, 2)


def write_public_report(st: dict, docs_dir: str = "docs") -> dict:
    """공개용 요약(docs/intraday.json) — 실험 표식과 정직한 한계를 함께 싣는다."""
    rounds = st.get("rounds") or []
    lastr = rounds[-1] if rounds else {}
    eq = float(lastr.get("equity") or st.get("start_cash") or START_CASH_USDT)
    base = float(st.get("start_cash") or START_CASH_USDT)
    trades_total = sum(len(r.get("trades") or []) for r in rounds)
    out = {
        "kind": KIND,
        "label": "장중 도전자 실험 — 가상 자금 · 실제 돈이 아닙니다",
        "currency": st.get("currency", "USDT"),
        "start_cash": base,
        "equity": round(eq, 2),
        "return_pct": round((eq / base - 1) * 100, 4),
        "cost_paid": round(float(st.get("cost_paid") or 0.0), 2),
        "trades_total": trades_total,
        "rounds_total": len(rounds),
        "since": (rounds[0].get("time") if rounds else None),
        "last_time": (lastr.get("time") if rounds else None),
        "booked_interval_minutes": BOOKED_INTERVAL_MINUTES,
        "observed_gap_minutes": observed_gap_minutes(rounds),
        "positions": {k: round(float(v), 8)
                      for k, v in (st.get("positions") or {}).items()},
        "risk_scale": float(st.get("risk_scale", 1.0)),
        "last_skipped": lastr.get("skipped") or {},
        "equity_curve": [[r.get("time"), r.get("equity")]
                         for r in rounds[-CURVE_KEEP:]],
        # 같은 기간 그냥 보유(첫 회차 가격 기준, 균등 분산) — 점수의 기준선.
        "hold_return_pct": hold_baseline_pct(st),
        # 판정 기준 — 결과가 쌓이기 전에 등록했고 바꾸지 않는다.
        "judgement": PREREGISTERED_JUDGEMENT,
        "elapsed_days": _elapsed_days(rounds),
        # 최근 체결 — 숫자만 보여주는 페이지는 장부가 아니다.
        "recent_trades": [
            {"time": r.get("time"), **t}
            for r in rounds for t in (r.get("trades") or [])][-40:],
        "honest_limits": HONEST_LIMITS,
        "rule": "본 계좌 챔피언과 같은 규칙·같은 비용 모델을 1시간봉에 적용 — "
                "빈도의 효과만 분리해 잽니다",
    }
    os.makedirs(docs_dir, exist_ok=True)
    from quant.utils.jsonio import atomic_write_json
    atomic_write_json(os.path.join(docs_dir, "intraday.json"), out)
    return out
