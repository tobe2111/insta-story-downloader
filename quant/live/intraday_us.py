"""미국주식 장중 도전자 — 같은 단타 실험을 미국 정규장에서 (2026-08-19, 사장님 지시).

    "미국주식도 단타 하자. 최대한 이상적으로."

코인 장중 실험(intraday_challenger)과 **같은 골격, 같은 규칙**이다 — 다른
것은 시장의 물리적 조건뿐이고, 그 차이는 전부 코드가 알고 있어야 한다:

    ① 장 시간이 있다. 미국 정규장(뉴욕 09:30~16:00, 주말·공휴일 휴장)
       밖에서는 판단도 체결도 하지 않는다 — 닫힌 장의 마지막 가격으로
       '체결했다'고 적는 것은 실험이 아니라 소설이다.
    ② 통화는 USD 하나다. 원화 환산을 하지 않는다 — 감사 254(통화 혼합
       사고)의 재발 지점을 아예 만들지 않는다. 본 계좌와의 비교는
       퍼센트 수익률로만 한다.
    ③ 같은 봉 멱등. 장이 닫혀 새 봉이 없으면 회차를 쓰지 않는다 —
       밤새 5분마다 같은 숫자를 4,000줄 쌓는 것은 기록이 아니라 소음이다.
    ④ 판단 규칙·체결 규칙·킬스위치는 **빌려 온다**(재작성 금지):
       챔피언 스펙은 retrain의 실전 함수, 체결은 intraday_challenger의
       _execute_targets(같은 함수), 비용은 measured_cost_model("us_stock").
       여기서 갈라지면 '미국장 대 코인장' 비교가 규칙 차이로 오염된다.
    ⑤ 자기 장부만 쓴다(state/intraday/us_*.json). 본 계좌 장부는 읽지도
       쓰지도 않는다.

정직한 한계: 시세 소스(야후)는 지연·결측이 있을 수 있고, 실데이터를 못
받으면 그 종목은 그 회차를 쉰다 — 합성 시세로 가짜 체결을 만들지 않는다.
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.intraday_us")

# 유니버스는 본 계좌의 미국 종목과 같다 — state/universe.json(규칙 선정)을
# 읽고, 없으면 현행 운영 구성으로 폴백한다. 실험이 자기만의 종목을 고르면
# '장중 빈도의 효과'에 '종목 선택의 효과'가 섞인다.
UNIVERSE_FALLBACK = ["SPY", "QQQ", "NVDA", "AAPL", "GOOGL",
                     "GOOG", "MSFT", "AMZN"]

TIMEFRAME = "1h"
# ⚠️ 코인 사다리는 15분·5분 둘 다지만 미국은 **15분까지만** 둔다(2026-08-19).
#    이유는 취향이 아니라 시세 제공자의 물리적 한계다: 코인은 거래소 공개
#    API라 요청이 사실상 무제한이지만, 미국 주식 무료 시세(야후)는 요청을
#    깐깐하게 조인다. 5분 트랙을 넣으면 정규장 6시간 반 동안 종목마다
#    5분마다 부르게 되고, 그러면 차단당해 **매 회차 "시세 못 받음"으로
#    조용히 비는 트랙**이 된다 — 돌지 않는 실험은 실험이 아니다.
#    키가 필요한 정식 소스(예: 브로커 시세 API)를 붙이면 그때 되돌린다.
LADDER_TIMEFRAMES = ["15m"]
LADDER_TIMEFRAMES_KEYED = ["15m", "5m"]   # 공식 시세(알파카) 키가 있을 때
LADDER_ROUNDS_KEEP = 4000
LOOKBACK_BARS = 800
MIN_BARS = 60

# 한 회차가 시세를 기다리는 데 쓸 수 있는 시간(초). 넘으면 남은 종목을
# 포기하고 그렇게 적는다.
#
# ⚠️ 이 실험은 **5분 장중 감시와 같은 작업 안에서** 돈다. 그 작업에는 낙폭
#    킬스위치와 심장박동이 함께 있다. 시세가 느린 날 미국 트랙이 시간을 다
#    쓰면 작업 제한에 걸려 **안전장치까지 같이 죽는다** — 실험이 안전장치를
#    볼모로 잡는 모양이라, 이 저장소가 가장 피해야 할 구조다.
FETCH_BUDGET_SEC = 90.0

START_CASH_USD = 10_000.0              # 가상 시드(USD). 원화와 절대 섞지 않는다.
ROUNDS_KEEP = 2000
CURVE_KEEP = 500

STATE_FILE = "us_challenger.json"
KIND = "us-challenger-experiment"

HONEST_LIMITS = [
    "가상 자금(USD)입니다 — 실제 돈이 아니고, 실제 호가·유동성을 겪지 않습니다",
    "미국 정규장(뉴욕 09:30~16:00) 안에서만 판단·체결합니다 — 장 밖 회차는 "
    "기록 자체가 없습니다",
    "시세 소스(야후)는 지연·결측이 있을 수 있고, 실데이터를 못 받은 종목은 "
    "그 회차를 쉽니다 — 합성 시세로 체결을 만들지 않습니다",
    "챔피언 파라미터는 일봉에서 뽑혔습니다 — 1시간봉 적용 자체가 이 실험의 "
    "가설이고, 검증된 전략이 아닙니다",
    "본 계좌(100만 챌린지)와 완전히 분리돼 있고 그 판단에 쓰이지 않습니다 — "
    "비교는 같은 기간 퍼센트 수익률로만 합니다",
]

# 판정 기준 — **첫 회차가 돌기 전에** 등록한다(코인 트랙과 같은 원칙).
# 원문은 quant.live.prereg의 intraday_us 항목이 정본이고, 여기는 그 원칙의
# 트랙 내 사본이다 — 두 곳이 어긋나면 계약 테스트가 잡는다.
PREREGISTERED_JUDGEMENT = {
    "registered_on": "2026-08-19",
    "min_days": 90,
    "criteria": [
        "관찰 90일 이상 — 충족 전에는 어떤 승패 판정도 내리지 않는다"
        "(30일 시점은 중간 참고 판독만)",
        "비용을 뺀 누적 수익률이 같은 기간 본 계좌(하루 1회 판단)보다 높다",
        "일별 수익률 차이의 95% 신뢰구간이 0을 배제한다 — 우연으로 "
        "설명되는 차이는 무승부다",
        "실험의 최대 낙폭이 같은 기간 본 계좌의 1.5배를 넘지 않는다 — "
        "수익이 위험을 사서 온 것이면 승리가 아니다",
    ],
    "note": "이 기준은 첫 회차가 돌기 전에 등록했고 바꾸지 않는다. "
            "바꿔야 한다면 그 사실과 이유를 사전 등록 원장(prereg)의 "
            "수정 이력에 공개한다.",
}


def ladder_timeframes() -> list[str]:
    """사다리 눈금 — 공식 시세 키가 있으면 5분 트랙을 되돌린다.

    ⚠️ 트랙이 늘고 주는 것은 **판정에 영향을 준다**(다중검정). 그래서
       조용히 바뀌면 안 되고, 공개 JSON이 지금 어떤 눈금으로 돌고 있는지와
       왜 그런지를 함께 싣는다(ladder_note). 사다리는 참고 진단이고 확정
       판정은 1시간 트랙만 한다는 규칙은 그대로다.
    """
    from quant.data.stock import alpaca_configured
    return list(LADDER_TIMEFRAMES_KEYED if alpaca_configured()
                else LADDER_TIMEFRAMES)


def _dir(state_dir: str) -> str:
    return os.path.join(state_dir, "intraday")


def _path(state_dir: str) -> str:
    return os.path.join(_dir(state_dir), STATE_FILE)


def _track_path(state_dir: str, timeframe: str) -> str:
    return os.path.join(_dir(state_dir), f"us_track_{timeframe}.json")


def universe(state_dir: str = "state") -> list[str]:
    """본 계좌의 미국 종목(규칙 선정 유니버스). 못 읽으면 현행 구성 폴백."""
    try:
        with open(os.path.join(state_dir, "universe.json"),
                  encoding="utf-8") as f:
            u = json.load(f)
        syms = [s for m, s in u.get("targets") or [] if m == "us_stock"]
        if syms:
            return syms
    except (OSError, ValueError):
        pass
    return list(UNIVERSE_FALLBACK)


def load_state(state_dir: str = "state") -> dict:
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, json.JSONDecodeError):
        st = {}
    st.setdefault("cash", START_CASH_USD)
    st.setdefault("start_cash", START_CASH_USD)
    st.setdefault("currency", "USD")
    st.setdefault("positions", {})
    st.setdefault("rounds", [])
    st.setdefault("cost_paid", 0.0)
    return st


def _load_track(state_dir: str, timeframe: str) -> dict:
    try:
        with open(_track_path(state_dir, timeframe), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("timeframe", timeframe)
    st.setdefault("cash", START_CASH_USD)
    st.setdefault("start_cash", START_CASH_USD)
    st.setdefault("currency", "USD")
    st.setdefault("positions", {})
    st.setdefault("cost_paid", 0.0)
    st.setdefault("rounds", [])
    st.setdefault("risk_scale", 1.0)
    return st


def _champion_factory(state_dir: str):
    """챔피언 규칙을 **빌려 오는** 기본 공장 — 재작성하지 않는다."""
    def make(symbol: str):
        from quant.live.retrain import build_strategy, champion_spec
        return build_strategy(champion_spec("us_stock", symbol, state_dir))
    return make


def _fetch_real(symbol: str, timeframe: str = TIMEFRAME):
    """실데이터 봉. 합성 폴백이면 None — 가짜 시세로 체결을 만들지 않는다."""
    from quant.data.stock import StockDataProvider
    df = StockDataProvider("us_stock").get_ohlcv(
        symbol, timeframe=timeframe, limit=LOOKBACK_BARS)
    if (df is None or len(df) == 0 or not df.attrs.get("source")
            or df.attrs.get("synthetic_fallback")):
        return None
    return df


def _tf_minutes(timeframe: str) -> int:
    """봉 길이(분). 모르는 눈금은 보수적으로 1분(=항상 새 봉으로 본다)."""
    tf = str(timeframe).strip().lower()
    if tf.endswith("h"):
        return int(tf[:-1] or 1) * 60
    if tf.endswith("m"):
        return int(tf[:-1] or 1)
    if tf.endswith("d"):
        return int(tf[:-1] or 1) * 1440
    return 1


def bar_could_have_closed(st: dict, timeframe: str, now_iso: str) -> bool:
    """직전 회차 이후 **새 봉이 닫혔을 수 있는가** — 아니면 시세를 안 부른다.

    ⚠️ 왜 필요한가(2026-08-19). 장중 감시는 5분마다 돈다. 그런데 1시간
       트랙은 한 시간에 한 번만 새 판단거리가 생긴다 — 나머지 열한 번은
       **같은 봉을 다시 받아** 같은 결론을 내고 버린다. 코인(거래소 공개
       API)에서는 공짜였지만 미국 무료 시세에서는 그 헛걸음이 차단을 부른다.

       마지막으로 판단한 봉의 여는 시각을 안다. 그 다음 봉은 (여는 시각
       + 봉 길이 × 2)에야 닫힌다 — 그 전에는 새로 받을 것이 없다.
       기록이 없으면(첫 회차) 무조건 부른다.
    """
    import datetime as dt

    rounds = st.get("rounds") or []
    if not rounds:
        return True
    bars = rounds[-1].get("bar_times") or {}
    if not bars:
        return True
    try:
        last = max(dt.datetime.fromisoformat(str(b).replace("Z", "+00:00"))
                   for b in bars.values())
    except ValueError:
        return True                      # 못 읽으면 막지 않는다(모름 ≠ 아님)
    if last.tzinfo is not None:
        last = last.astimezone(dt.timezone.utc).replace(tzinfo=None)
    now = _now_dt(now_iso).astimezone(dt.timezone.utc).replace(tzinfo=None)
    return now >= last + dt.timedelta(minutes=2 * _tf_minutes(timeframe))


def _now_dt(now_iso: str):
    import datetime as dt
    now = dt.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now


def _judge_symbols(syms: list[str], now_iso: str, timeframe: str,
                   data: dict | None, factory) -> tuple[dict, dict, dict, dict]:
    """종목별 (가격, 신호, 판단 봉 시각, 건너뜀 사유) — 닫힌 봉만 쓴다."""
    import time

    from quant.live.intraday_challenger import confirmed_bars
    prices: dict[str, float] = {}
    signals: dict[str, float | None] = {}
    bar_times: dict[str, str] = {}
    skipped: dict[str, str] = {}
    dfs: dict[str, object] = {}
    deadline = time.monotonic() + FETCH_BUDGET_SEC
    for sym in syms:
        # 시간 예산 — 안전장치와 한 작업에 살고 있으므로, 느린 날에는
        # 실험이 먼저 물러난다. 물러난 사실은 장부에 남는다(조용한 포기 금지).
        if data is None and time.monotonic() > deadline:
            signals[sym] = None
            skipped[sym] = "시세 대기 시간 초과 — 이 회차는 포기(감시 보호)"
            continue
        df = (data or {}).get(sym) if data is not None \
            else _fetch_real(sym, timeframe=timeframe)
        if df is not None:
            df = confirmed_bars(df, now_iso, timeframe=timeframe)
        if df is None or len(df) < MIN_BARS:
            signals[sym] = None
            skipped[sym] = ("실데이터 시세를 받지 못함" if df is None
                            else f"닫힌 봉 부족({len(df)}<{MIN_BARS})")
            continue
        prices[sym] = float(df["close"].iloc[-1])
        bar_times[sym] = str(df.index[-1])
        dfs[sym] = df
        try:
            sig = float(factory(sym).generate_signals(df).iloc[-1])
        except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 회차를 못 죽인다
            signals[sym] = None
            skipped[sym] = f"신호 계산 실패: {exc}"
            continue
        signals[sym] = max(0.0, min(1.0, sig))   # 숏·레버리지 없음
    return prices, signals, bar_times, skipped, dfs


def _advance_account(st: dict, syms: list[str], prices: dict, signals: dict,
                     per_side: float) -> tuple[float, list]:
    """평가 → 킬스위치(대여) → 체결(대여) — 코인 트랙과 같은 순서·같은 함수."""
    from quant.live.daily import _kill_switch_scale
    from quant.live.intraday_challenger import _execute_targets, mark_equity
    from quant.live.ledger_basics import drawdown_from_index

    equity = mark_equity(st, prices)
    if prices and not st.get("first_prices"):
        st["first_prices"] = dict(prices)
    peak = max(float(st.get("peak_equity") or 0.0), equity)
    st["peak_equity"] = peak
    dd = drawdown_from_index([peak, equity]) if peak > 0 else 0.0
    scale = _kill_switch_scale(float(st.get("risk_scale", 1.0)), dd)
    st["risk_scale"] = scale
    trades = _execute_targets(st, signals, prices, equity, scale, per_side,
                              universe=syms)
    last = dict(st.get("last_prices") or {})
    last.update(prices)
    st["last_prices"] = last
    return mark_equity(st, prices), trades


def run_us_round(now_iso: str, *, state_dir: str = "state",
                 docs_dir: str = "docs", data: dict | None = None,
                 strategy_factory=None, holidays: dict | None = None) -> dict:
    """미국장 한 회차. 장 밖이면 판단도 기록도 하지 않는다.

    data/strategy_factory 주입은 검사용이다 — 실전 기본값은 실데이터와
    챔피언 규칙이다. data는 {심볼: df} + {"15m"/"5m": {심볼: df}} 꼴.
    """
    from quant.live.daily import measured_cost_model
    from quant.live.intraday_challenger import mark_equity
    from quant.live.market_hours import is_market_open
    from quant.utils.jsonio import atomic_write_json

    # ① 장 시간 관문 — 닫힌 장에서 '체결했다'고 적는 순간 실험은 소설이 된다.
    if not is_market_open("us_stock", _now_dt(now_iso), holidays):
        return {"skipped": "미국장 휴장", "time": str(now_iso)}

    st = load_state(state_dir)
    syms = universe(state_dir)
    factory = strategy_factory or _champion_factory(state_dir)
    cost = measured_cost_model("us_stock", state_dir)
    per_side = cost.total_one_way()

    # 새 봉이 닫혔을 수 없으면 시세를 아예 부르지 않는다(요청 절약).
    if data is None and not bar_could_have_closed(st, TIMEFRAME, now_iso):
        return {"skipped": "새 봉 없음 — 시세 요청 생략", "time": str(now_iso)}
    prices, signals, bar_times, skipped, dfs = _judge_symbols(
        syms, now_iso, TIMEFRAME, data, factory)
    if not prices:
        return {"skipped": "판단 재료 없음(실데이터 전무)", "time": str(now_iso)}
    # ② 같은 봉 멱등 — 새 정보가 없으면 회차를 쓰지 않는다(소음 금지).
    last_bars = (st.get("rounds") or [{}])[-1].get("bar_times") or {}
    if bar_times and bar_times == last_bars:
        return {"skipped": "같은 봉 재실행", "time": str(now_iso)}

    equity_after, trades = _advance_account(st, syms, prices, signals,
                                            per_side)
    # 지정가 그림자 — 같은 신호, 다른 체결(코인 트랙과 **같은 함수**).
    # 주식은 호가 간격이 코인과 달라 '기다리는 체결'의 값이 다를 수 있다.
    # 실패해도 본 실험을 막지 않는다 — 부르는 쪽이 예외를 삼킨다.
    shadow_info = None
    try:
        from quant.live.intraday_challenger import _limit_shadow_round
        shadow_info = _limit_shadow_round(
            st, dfs, signals, prices, float(cost.fee),
            float(st.get("risk_scale", 1.0)), now_iso, bar_times,
            universe=syms)
    except Exception as exc:  # noqa: BLE001
        log.warning("미국 지정가 그림자 실패(본 실험 무관): %s", exc)
    rec = {"time": str(now_iso), "equity": round(equity_after, 2),
           "signals": {k: (round(v, 4) if v is not None else None)
                       for k, v in signals.items()},
           "bar_times": bar_times, "trades": trades}
    if float(st.get("risk_scale", 1.0)) < 1.0:
        rec["kill_switch"] = {"scale": float(st["risk_scale"])}
    if shadow_info:
        rec["limit_shadow"] = shadow_info
    if skipped:
        rec["skipped"] = skipped
    st["rounds"] = (st.get("rounds") or [])[-(ROUNDS_KEEP - 1):] + [rec]

    os.makedirs(_dir(state_dir), exist_ok=True)
    atomic_write_json(_path(state_dir), st)

    # ③ 주기 사다리 — 실패해도 본 실험을 막지 않는다.
    try:
        run_us_ladder(now_iso, state_dir=state_dir,
                      data=None if data is None else data,
                      strategy_factory=strategy_factory, holidays=holidays)
    except Exception as exc:  # noqa: BLE001
        log.warning("미국 주기 사다리 실패(본 실험 무관): %s", exc)

    write_public_report(st, docs_dir=docs_dir, state_dir=state_dir)
    verdict = {"time": str(now_iso), "equity": round(equity_after, 2),
               "trades": len(trades), "skipped": len(skipped),
               "cost_paid": round(float(st["cost_paid"]), 2),
               "return_pct": round((equity_after / float(st["start_cash"]) - 1)
                                   * 100, 4)}
    log.info("🇺🇸 미국 장중 도전자 — 자산 %.2f USD · 체결 %d건 · 건너뜀 %d종목",
             equity_after, len(trades), len(skipped))
    return verdict


def run_us_ladder(now_iso: str, *, state_dir: str = "state",
                  data: dict | None = None, strategy_factory=None,
                  holidays: dict | None = None) -> list[dict]:
    """15분·5분 트랙 — 본 트랙과 같은 규칙, 봉 주기만 다르다."""
    from quant.live.daily import measured_cost_model
    from quant.live.market_hours import is_market_open
    from quant.utils.jsonio import atomic_write_json

    if not is_market_open("us_stock", _now_dt(now_iso), holidays):
        return [{"skipped": "미국장 휴장"}]
    syms = universe(state_dir)
    factory = strategy_factory or _champion_factory(state_dir)
    cost = measured_cost_model("us_stock", state_dir)
    per_side = cost.total_one_way()
    out = []
    for tf in ladder_timeframes():
        st = _load_track(state_dir, tf)
        if data is None and not bar_could_have_closed(st, tf, now_iso):
            out.append({"timeframe": tf, "skipped": "새 봉 없음 — 요청 생략"})
            continue
        # 주입 데이터 모드에서는 절대 실데이터로 넘어가지 않는다 — 검사가
        # 몰래 네트워크를 만지는 순간 검사 자체가 재현 불가능해진다.
        prices, signals, bar_times, _sk, _dfs = _judge_symbols(
            syms, now_iso, tf,
            (((data or {}).get(tf) or {}) if data is not None else None),
            factory)
        if not prices:
            out.append({"timeframe": tf, "skipped": "닫힌 봉/데이터 없음"})
            continue
        last_bars = (st.get("rounds") or [{}])[-1].get("bar_times") or {}
        if bar_times and bar_times == last_bars:
            out.append({"timeframe": tf, "skipped": "같은 봉 재실행"})
            continue
        equity_after, trades = _advance_account(st, syms, prices, signals,
                                                per_side)
        rec = {"time": str(now_iso), "equity": round(equity_after, 2),
               "bar_times": bar_times, "trades": trades}
        st["rounds"] = (st.get("rounds") or [])[-(LADDER_ROUNDS_KEEP - 1):] \
            + [rec]
        os.makedirs(_dir(state_dir), exist_ok=True)
        atomic_write_json(_track_path(state_dir, tf), st)
        out.append({"timeframe": tf, "equity": round(equity_after, 2),
                    "trades": len(trades)})
    return out


def ladder_public(state_dir: str = "state") -> list[dict]:
    from quant.live.daily import measured_cost_model
    from quant.live.intraday_challenger import hold_baseline_pct
    out = []
    for tf in ladder_timeframes():
        st = _load_track(state_dir, tf)
        rounds = st.get("rounds") or []
        if not rounds:
            continue
        eq = float(rounds[-1].get("equity") or st["start_cash"])
        out.append({
            "timeframe": tf,
            "equity": round(eq, 2),
            "return_pct": round((eq / float(st["start_cash"]) - 1) * 100, 4),
            "hold_return_pct": hold_baseline_pct(
                st, measured_cost_model("us_stock", state_dir).total_one_way()),
            "trades_total": sum(len(r.get("trades") or []) for r in rounds),
            "cost_paid": round(float(st.get("cost_paid") or 0.0), 2),
            "rounds_total": len(rounds),
            "since": rounds[0].get("time"),
        })
    return out


def _quote_source() -> str:
    """지금 어떤 시세로 도는가 — 키 값이 아니라 **어느 경로인지**만 말한다."""
    from quant.data.stock import ALPACA_FEED, alpaca_configured
    if alpaca_configured():
        return (f"알파카 공식 무료 시세({ALPACA_FEED.upper()} 거래소) — "
                "전체 시장 통합 시세(SIP)가 아니라 일부 거래소 체결이라, "
                "통합 시세와 조금 다를 수 있습니다")
    return ("무료 공개 시세(야후) — 비공식 경로라 요청이 몰리면 막힐 수 "
            "있습니다. 못 받은 종목은 그 회차를 쉽니다")


def _ladder_reason() -> str:
    from quant.data.stock import alpaca_configured
    if alpaca_configured():
        return "공식 시세 키가 있어 5분 트랙까지 돌고 있습니다."
    return ("지금은 15분까지만 돕니다 — 무료 공개 시세로 5분 트랙을 돌리면 "
            "요청이 막혀 오히려 기록이 비기 때문입니다.")


def write_public_report(st: dict, docs_dir: str = "docs",
                        state_dir: str = "state") -> dict:
    """공개용 요약(docs/intraday_us.json) — 실험 표식·정직한 한계를 함께."""
    from quant.live.daily import measured_cost_model
    from quant.live.intraday_challenger import (_shadow_public,
                                                hold_baseline_pct,
                                                observed_gap_minutes)
    rounds = st.get("rounds") or []
    lastr = rounds[-1] if rounds else {}
    eq = float(lastr.get("equity") or st.get("start_cash") or START_CASH_USD)
    base = float(st.get("start_cash") or START_CASH_USD)
    out = {
        "kind": KIND,
        "label": "미국주식 장중 실험 — 가상 자금 · 실제 돈이 아닙니다",
        "currency": st.get("currency", "USD"),
        "start_cash": base,
        "equity": round(eq, 2),
        "return_pct": round((eq / base - 1) * 100, 4),
        "cost_paid": round(float(st.get("cost_paid") or 0.0), 2),
        "trades_total": sum(len(r.get("trades") or []) for r in rounds),
        "rounds_total": len(rounds),
        "since": (rounds[0].get("time") if rounds else None),
        "last_time": (lastr.get("time") if rounds else None),
        "observed_gap_minutes": observed_gap_minutes(rounds),
        "market_hours": "미국 정규장(뉴욕 09:30~16:00)에서만 판단·체결 — "
                        "장 밖 회차는 기록이 없습니다",
        # 어느 시세로 돌고 있는지 — 화면이 지어내지 않게 장부가 말한다.
        "quote_source": _quote_source(),
        "positions": {k: round(float(v), 8)
                      for k, v in (st.get("positions") or {}).items()},
        "risk_scale": float(st.get("risk_scale", 1.0)),
        "last_skipped": lastr.get("skipped") or {},
        "equity_curve": [[r.get("time"), r.get("equity")]
                         for r in rounds[-CURVE_KEEP:]],
        "hold_return_pct": hold_baseline_pct(
                st, measured_cost_model("us_stock", state_dir).total_one_way()),
        "judgement": PREREGISTERED_JUDGEMENT,
        "limit_shadow": _shadow_public(st, lastr),
        "ladder": ladder_public(state_dir),
        "ladder_note": ("주기별 트랙은 같은 전략·같은 체결 규칙에 봉 주기만 "
                        "다릅니다. 트랙 수가 늘면 우연히 좋아 보이는 주기가 "
                        "나올 확률도 늘어납니다 — 판정은 본 실험(1시간)의 "
                        "90일 기준만 유효하고, 사다리는 참고 진단입니다. "
                        + _ladder_reason()),
        "recent_trades": [
            {"time": r.get("time"), **t}
            for r in rounds for t in (r.get("trades") or [])][-40:],
        "honest_limits": HONEST_LIMITS,
        "rule": "본 계좌 미국 챔피언과 같은 규칙·같은 비용 모델을 1시간봉에 "
                "적용 — 빈도의 효과만 분리해 잽니다",
    }
    os.makedirs(docs_dir, exist_ok=True)
    from quant.utils.jsonio import atomic_write_json
    atomic_write_json(os.path.join(docs_dir, "intraday_us.json"), out)
    return out
