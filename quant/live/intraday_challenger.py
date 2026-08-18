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
# 주기 사다리(2026-08-18, 사장님 "최대한 이상적으로") — 최적 주기를 사람이
# 고르지 않고 **나란히 돌려서 곡선이 고르게** 한다. 같은 전략·같은 브레이크·
# 같은 체결 규칙(_execute_targets)에 봉 주기만 다르다. 트랙이 늘수록 우연한
# 승자가 나올 확률도 늘어난다 — 공개 리포트가 그 사실을 함께 말한다.
# 5분보다 빠른 주기는 이 인프라(크론 배치)에서 판단 간격을 보장할 수 없어
# 사다리에 넣지 않는다 — 넣으면 '측정'이 아니라 '장식'이 된다.
LADDER_TIMEFRAMES = ["15m", "5m"]
LADDER_ROUNDS_KEEP = 4000
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


def _fetch_real(symbol: str, timeframe: str = TIMEFRAME):
    """실데이터 봉. 합성 폴백이면 None — 가짜 시세로 체결을 만들지 않는다."""
    from quant.data.crypto import CryptoDataProvider
    df = CryptoDataProvider().get_ohlcv(symbol, timeframe=timeframe,
                                        limit=LOOKBACK_BARS)
    if df is None or len(df) == 0 or not df.attrs.get("source"):
        return None
    return df


def confirmed_bars(df, now_iso: str, timeframe: str = TIMEFRAME):
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
    keep = (idx + pd.Timedelta(timeframe)) <= now
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


def _execute_targets(st: dict, signals: dict, prices: dict,
                     equity: float, scale: float, per_side: float) -> list:
    """목표 비중 → 체결 — 본 트랙과 주기 사다리가 **같은 규칙을 한 곳**에서 쓴다.

    여기서 갈라지면 주기 비교가 체결 규칙 비교로 오염된다. 시장가 즉시
    체결 + 편도 비용(수수료+슬리피지), 레버리지 금지, 최소 조정 문턱.
    """
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
    return trades


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
    dfs: dict[str, object] = {}          # 지정가 그림자의 체결 판정 재료
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
        dfs[sym] = df
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
    # 지정가 그림자 — 같은 신호, 다른 체결. 실패해도 본 실험을 막지 않는다.
    shadow_info = None
    try:
        shadow_info = _limit_shadow_round(st, dfs, signals, prices,
                                          float(cost.fee), scale, now_iso,
                                          bar_times)
    except Exception as exc:  # noqa: BLE001
        log.warning("지정가 그림자 실패(본 실험 무관): %s", exc)
    # 주기 사다리 — 15분·5분 트랙. 실패해도 본 실험을 막지 않는다.
    try:
        run_ladder(now_iso, state_dir=state_dir,
                   data=None if data is None else {},
                   strategy_factory=strategy_factory)
    except Exception as exc:  # noqa: BLE001
        log.warning("주기 사다리 실패(본 실험 무관): %s", exc)
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
    if shadow_info:
        rec["limit_shadow"] = shadow_info
    if skipped:
        rec["skipped"] = skipped
    st["rounds"] = (st.get("rounds") or [])[-(ROUNDS_KEEP - 1):] + [rec]

    os.makedirs(_dir(state_dir), exist_ok=True)
    from quant.utils.jsonio import atomic_write_json
    atomic_write_json(_path(state_dir), st)
    write_public_report(st, docs_dir=docs_dir, state_dir=state_dir)
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


def _limit_shadow_round(st: dict, dfs: dict, signals: dict, prices: dict,
                        fee_only: float, scale: float, now_iso: str,
                        bar_times: dict) -> dict | None:
    """지정가 그림자 계좌 — 같은 신호, 다른 체결 (실험 속 실험, 2026-08-18).

    본 실험은 판단 봉 종가에 시장가(수수료+슬리피지)로 즉시 체결한다.
    이 그림자는 활성화 순간 본 계좌를 **그대로 복제**한 뒤, 같은 신호로
    판단 봉 종가에 지정가를 걸고 다음 닫힌 봉들이 그 가격에 닿아야만
    체결한다(매수: 저가≤지정가 · 매도: 고가≥지정가). 체결되면 슬리피지
    없이 수수료만 문다 — 그 대가는 **못 사는 위험**(미체결)이다.

    복제에서 출발하므로 이후 두 곡선의 차이는 순수하게 체결 방식의 효과다.
    판정(90일)은 본 실험의 것이고, 이 그림자는 체결 비교의 재료일 뿐이다.
    그림자 실패가 본 실험을 막으면 안 된다 — 부르는 쪽이 예외를 삼킨다.
    """
    sh = st.get("limit_shadow")
    if sh is None:
        # 활성화 — 본 계좌 복제. 이 시점부터 갈라지는 것만 잰다.
        eq0 = float(st.get("cash", 0.0)) + sum(
            float(q) * float(prices.get(sym, 0.0))
            for sym, q in (st.get("positions") or {}).items())
        sh = {"since": str(now_iso), "start_equity": round(eq0, 2),
              "cash": float(st.get("cash", 0.0)),
              "positions": dict(st.get("positions") or {}),
              "pending": {}, "cost_paid": 0.0,
              "filled_total": 0, "unfilled_total": 0}
        st["limit_shadow"] = sh

    filled = 0
    # ① 대기 주문 체결 판정 — 주문을 낸 봉 **이후의 닫힌 봉**들만 본다.
    for sym, od in list((sh.get("pending") or {}).items()):
        df = dfs.get(sym)
        if df is None or sym not in prices:
            continue
        after = df[[str(i) > str(od.get("placed_bar", "")) for i in df.index]]
        if len(after) == 0:
            continue
        limit = float(od["limit"])
        notional = float(od["notional"])
        if od["side"] == "buy" and float(after["low"].min()) <= limit:
            fee = notional * fee_only
            if notional + fee > sh["cash"]:            # 레버리지 금지
                notional = max(0.0, sh["cash"] / (1.0 + fee_only))
                fee = notional * fee_only
            if notional > 0:
                sh["cash"] -= notional + fee
                sh["positions"][sym] = (float(sh["positions"].get(sym, 0.0))
                                        + notional / limit)
                sh["cost_paid"] += fee
                filled += 1
            sh["pending"].pop(sym, None)
        elif od["side"] == "sell" and float(after["high"].max()) >= limit:
            qty = min(notional / limit,
                      float(sh["positions"].get(sym, 0.0)))
            if qty > 0:
                got = qty * limit
                fee = got * fee_only
                sh["cash"] += got - fee
                sh["positions"][sym] = float(sh["positions"].get(sym, 0.0)) - qty
                if abs(sh["positions"][sym]) * limit < 1e-6:
                    sh["positions"].pop(sym, None)
                sh["cost_paid"] += fee
                filled += 1
            sh["pending"].pop(sym, None)

    # ② 안 닿은 주문은 취소하고(취소-재주문), 지금 신호로 다시 건다.
    cancelled = len(sh.get("pending") or {})
    sh["unfilled_total"] = int(sh.get("unfilled_total", 0)) + cancelled
    sh["filled_total"] = int(sh.get("filled_total", 0)) + filled
    sh["pending"] = {}
    eq = float(sh["cash"]) + sum(float(q) * float(prices.get(sym, 0.0))
                                 for sym, q in sh["positions"].items())
    if eq > 0:
        budget = sh["cash"]                  # 대기 매수 합계가 현금을 못 넘게
        slice_budget = eq / len(UNIVERSE)
        for sym in UNIVERSE:
            sig = signals.get(sym)
            px = prices.get(sym)
            if sig is None or not px:
                continue
            cur = float(sh["positions"].get(sym, 0.0))
            delta = slice_budget * sig * scale - cur * px
            if abs(delta) < max(MIN_TRADE_USDT, MIN_TRADE_FRAC * eq):
                continue
            if delta > 0:
                afford = budget / (1.0 + fee_only)
                if delta > afford:
                    delta = afford
                if delta < max(MIN_TRADE_USDT, MIN_TRADE_FRAC * eq):
                    continue
                budget -= delta * (1.0 + fee_only)
            sh["pending"][sym] = {"side": "buy" if delta > 0 else "sell",
                                  "limit": px, "notional": round(abs(delta), 2),
                                  "placed_bar": bar_times.get(sym, "")}
    return {"equity": round(eq, 2), "filled": filled, "cancelled": cancelled,
            "pending": len(sh["pending"])}


def _track_path(state_dir: str, timeframe: str) -> str:
    return os.path.join(_dir(state_dir), f"track_{timeframe}.json")


def _load_track(state_dir: str, timeframe: str) -> dict:
    try:
        with open(_track_path(state_dir, timeframe), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("timeframe", timeframe)
    st.setdefault("cash", START_CASH_USDT)
    st.setdefault("start_cash", START_CASH_USDT)
    st.setdefault("positions", {})
    st.setdefault("cost_paid", 0.0)
    st.setdefault("rounds", [])
    st.setdefault("risk_scale", 1.0)
    return st


def run_ladder(now_iso: str, *, state_dir: str = "state",
               data: dict | None = None, strategy_factory=None) -> list[dict]:
    """주기 사다리 — 15분·5분 봉 트랙을 본 트랙과 같은 규칙으로 1회씩 돈다.

    본 트랙(1h)의 판정을 오염시키지 않는 독립 실험 계좌들이다. 부르는 쪽이
    예외를 삼킨다 — 사다리 실패가 본 실험을 막으면 안 된다.
    크론이 5분보다 늦게 돌면 5분 트랙은 봉을 건너뛴다 — 그 실측 간격은
    회차 기록(시각)이 그대로 말한다(숨기지 않는다).
    """
    from quant.live.daily import _kill_switch_scale, measured_cost_model
    from quant.live.ledger_basics import drawdown_from_index
    from quant.utils.jsonio import atomic_write_json

    factory = strategy_factory or _champion_factory(state_dir)
    cost = measured_cost_model("crypto", state_dir)
    per_side = float(cost.fee + cost.slippage)
    out = []
    for tf in LADDER_TIMEFRAMES:
        st = _load_track(state_dir, tf)
        prices: dict[str, float] = {}
        signals: dict[str, float | None] = {}
        bar_times: dict[str, str] = {}
        for sym in UNIVERSE:
            df = ((data or {}).get(tf, {}) or {}).get(sym) if data is not None \
                else _fetch_real(sym, timeframe=tf)
            if df is not None:
                df = confirmed_bars(df, now_iso, timeframe=tf)
            if df is None or len(df) < MIN_BARS:
                signals[sym] = None
                continue
            prices[sym] = float(df["close"].iloc[-1])
            bar_times[sym] = str(df.index[-1])
            try:
                sig = float(factory(sym).generate_signals(df).iloc[-1])
            except Exception:  # noqa: BLE001
                signals[sym] = None
                continue
            signals[sym] = max(0.0, min(1.0, sig))
        if not prices:
            # 한 종목도 판단 재료가 없다 — 빈 회차를 장부에 쓰지 않는다.
            out.append({"timeframe": tf, "skipped": "닫힌 봉/데이터 없음"})
            continue
        # 같은 봉으로 이미 판단했으면 이 트랙은 이번 회차를 쉰다(멱등) —
        # 5분 트랙이 15분 크론에서 세 번 같은 봉을 매매하는 것을 막는다.
        last_bars = (st.get("rounds") or [{}])[-1].get("bar_times") or {}
        if bar_times and bar_times == last_bars:
            out.append({"timeframe": tf, "skipped": "같은 봉 재실행"})
            continue
        equity = mark_equity(st, prices)
        if prices and not st.get("first_prices"):
            st["first_prices"] = dict(prices)
        peak = max(float(st.get("peak_equity") or 0.0), equity)
        st["peak_equity"] = peak
        dd = drawdown_from_index([peak, equity]) if peak > 0 else 0.0
        scale = _kill_switch_scale(float(st.get("risk_scale", 1.0)), dd)
        st["risk_scale"] = scale
        trades = _execute_targets(st, signals, prices, equity, scale, per_side)
        equity_after = mark_equity(st, prices)
        rec = {"time": str(now_iso), "equity": round(equity_after, 2),
               "bar_times": bar_times, "trades": trades}
        st["rounds"] = (st.get("rounds") or [])[-(LADDER_ROUNDS_KEEP - 1):] + [rec]
        os.makedirs(_dir(state_dir), exist_ok=True)
        atomic_write_json(_track_path(state_dir, tf), st)
        out.append({"timeframe": tf, "equity": round(equity_after, 2),
                    "trades": len(trades)})
    return out


def ladder_public(state_dir: str = "state") -> list[dict]:
    """주기 사다리의 공개 요약 — 주기별 수익률·보유 기준·비용을 나란히."""
    out = []
    for tf in LADDER_TIMEFRAMES:
        st = _load_track(state_dir, tf)
        rounds = st.get("rounds") or []
        if not rounds:
            continue
        eq = float(rounds[-1].get("equity") or st["start_cash"])
        out.append({
            "timeframe": tf,
            "equity": round(eq, 2),
            "return_pct": round((eq / float(st["start_cash"]) - 1) * 100, 4),
            "hold_return_pct": hold_baseline_pct(st),
            "trades_total": sum(len(r.get("trades") or []) for r in rounds),
            "cost_paid": round(float(st.get("cost_paid") or 0.0), 2),
            "rounds_total": len(rounds),
            "since": rounds[0].get("time"),
        })
    return out


def _shadow_public(st: dict, lastr: dict) -> dict | None:
    """지정가 그림자의 공개 요약 — 본 실험과 나란히 읽히는 비교 숫자."""
    sh = st.get("limit_shadow")
    if not sh:
        return None
    rec = (lastr.get("limit_shadow") or {})
    eq = rec.get("equity")
    base = float(sh.get("start_equity") or 0.0)
    return {
        "since": sh.get("since"),
        "start_equity": base,
        "equity": eq,
        "return_pct_since": (round((float(eq) / base - 1) * 100, 4)
                             if eq and base > 0 else None),
        "cost_paid": round(float(sh.get("cost_paid") or 0.0), 2),
        "filled_total": int(sh.get("filled_total") or 0),
        "unfilled_total": int(sh.get("unfilled_total") or 0),
        "note": ("같은 신호·지정가 체결 복제 계좌 — 슬리피지를 아끼는 대신 "
                 "미체결 위험을 집니다. 본 실험과의 자산 차이가 체결 방식의 "
                 "효과입니다."),
    }


def write_public_report(st: dict, docs_dir: str = "docs",
                        state_dir: str = "state") -> dict:
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
        # 지정가 그림자(2026-08-18) — 같은 신호를 지정가로만 체결한 복제
        # 계좌. 활성화 순간 본 실험을 복제했으므로 두 자산의 차이가 곧
        # 체결 방식의 효과다. 지정가는 슬리피지를 아끼는 대신 못 사는
        # 위험(미체결)을 진다 — 어느 쪽이 이기는지는 곡선이 답한다.
        "limit_shadow": _shadow_public(st, lastr),
        # 주기 사다리 — 트랙이 많을수록 우연한 승자 확률도 커진다는 사실을
        # 숫자와 함께 싣는다(다중검정 정직성 — 오디션과 같은 원칙).
        "ladder": ladder_public(state_dir),
        "ladder_note": ("주기별 트랙은 같은 전략·같은 체결 규칙에 봉 주기만 "
                        "다릅니다. 트랙 수가 늘면 우연히 좋아 보이는 주기가 "
                        "나올 확률도 늘어납니다 — 판정은 본 실험(1시간)의 "
                        "90일 기준만 유효하고, 사다리는 참고 진단입니다."),
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
