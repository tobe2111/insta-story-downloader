"""선물 운용 계좌 — 엔진 그대로 / 코인 그냥 보유 / 현금 중 **기계가 고른다** (감사 346).

사장님(2026-10-11): "모두 진행해" — 단타 운용 계좌(감사 345)와 같은 장치를
선물 트랙에도.

선물 실험 계좌는 −12%다(8/23~10/11). 주간 선택기(감사 344)는 2022년 이후
**장기 시뮬레이션**만 보고 엔진을 고르므로, 실제 장부가 계속 잃어도 그 사실이
선택에 들어가지 않는다. 이 계좌는 **실제 장부의 최근 성적**으로 고른다.

■ 방식 셋

  · follow — 선물 실험 계좌를 그대로 따라간다. 일수익은 그 장부의 하루 마지막
             자산에서 나온다(수수료·펀딩·청산 전부 뺀 실제 값).
  · hold   — 코인 다섯을 같은 금액으로 1배 롱. 일수익 = 그날 종가 변화의 균등
             평균 − 펀딩(연 `FUTURES_CARRY`, 매일 같은 몫).
  · cash   — 아무것도 안 함. 일수익 0(이자도 안 셈 — 근거 없는 숫자를 안 넣는다).

  고르는 규칙은 단타 운용 계좌와 **같은 함수**다(`intraday_mode.decide` — 최근
  90일, 최소 20일, 오늘 제외, 엔진 선택기 문턱, 14일 최소 유지).

■ 이 계좌는 **배분 장부**다(체결 장부가 아니다)

  매 회차 주문을 내지 않고, 하루가 끝날 때마다 그날 고른 방식의 일수익을
  자산에 곱한다. 갈아타는 날에는 옛 방식을 정리하고 새 방식을 여는 비용을
  편도 실측 비용 × (옛 노출 + 새 노출)로 뗀다 — 겹치는 몫을 빼지 않으므로
  보수적이다.

■ 정직한 한계

  · hold의 펀딩은 실측 계열이 아니라 연 10.95%를 매일 같은 몫으로 뗀 근사다.
  · 자산은 **하루 한 번**(어제 종가 기준) 갱신된다. 장중 움직임은 안 보인다.
  · 시작은 0이 아니라 선물 실험 계좌의 지난 곡선을 이어받는다(그때는 follow).
"""
from __future__ import annotations

import datetime as dt

from quant.live import intraday_mode as IM

MODES = ("follow", "hold", "cash")
DEFAULT_MODE = "follow"
LABELS = {"follow": "선물 엔진 그대로 따라가기",
          "hold": "코인 그냥 보유(1배, 펀딩 냄)",
          "cash": "현금(아무것도 안 함)"}
HISTORY_KEEP = 400


def _daily_rounds(rounds: list[dict]):
    """회차 → (일별 마지막 자산, 일별 마지막 가격표). 시각은 시각으로 정렬한다."""
    import pandas as pd
    rows = [r for r in rounds or [] if r.get("at") and r.get("equity") is not None]
    if not rows:
        empty = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        return empty, pd.DataFrame()
    ts = pd.to_datetime([r["at"] for r in rows], utc=True)
    eq = pd.Series([float(r["equity"]) for r in rows], index=ts).sort_index()
    eq_d = eq.groupby(eq.index.date).last()
    eq_d.index = pd.to_datetime(eq_d.index)
    px = pd.DataFrame([r.get("prices") or {} for r in rows], index=ts).sort_index()
    px_d = px.groupby(px.index.date).last()
    px_d.index = pd.to_datetime(px_d.index)
    return eq_d, px_d


def daily_series(rounds: list[dict]) -> dict:
    """방식마다 수수료·펀딩 뺀 일수익."""
    from quant.portfolio.trend_core import FUTURES_CARRY
    eq_d, px_d = _daily_rounds(rounds)
    follow = eq_d.pct_change().dropna()
    if len(px_d) > 1:
        hold = px_d.astype(float).pct_change().mean(axis=1, skipna=True).dropna()
        hold = hold - FUTURES_CARRY / 365.0
    else:
        hold = follow.iloc[:0]
    cash = follow * 0.0
    return {"follow": follow, "hold": hold, "cash": cash}


def _exposure(mode: str, rounds: list[dict]) -> float:
    if mode == "cash":
        return 0.0
    if mode == "hold":
        return 1.0
    last = (rounds or [{}])[-1]
    try:
        return abs(float(last.get("gross_exposure") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def continue_from(st: dict, today: str) -> dict:
    """선물 실험 계좌의 지난 곡선을 이어받는다(그때는 follow였다)."""
    eq_d, _ = _daily_rounds(st.get("rounds") or [])
    base = float(st.get("start_cash") or 10_000.0)
    done = eq_d[eq_d.index < dt.datetime.fromisoformat(today)]
    equity = float(done.iloc[-1]) if len(done) else base
    hist = [{"date": str(i.date()), "equity": round(float(v), 4), "mode": "follow",
             "inherited": True} for i, v in done.items()][-HISTORY_KEEP:]
    return {"since": str(eq_d.index[0].date()) if len(eq_d) else today,
            "start_cash": base, "equity": equity,
            "peak": max([base] + [h["equity"] for h in hist]),
            "mode": DEFAULT_MODE, "mode_since": None, "decided_on": None,
            "decision": None, "switches": [], "cost_paid": 0.0,
            "applied_through": str(done.index[-1].date()) if len(done) else None,
            "history": hist, "inherited_from_experiment": today}


def step(st: dict, *, now_iso: str, per_side: float) -> dict:
    """하루가 바뀐 첫 회차에 — 지난날의 수익을 곱하고, 오늘의 방식을 정한다."""
    import pandas as pd
    today = IM.utc_day(now_iso)
    op = st.get("operated")
    if not op:
        op = continue_from(st, today)
        st["operated"] = op
    if op.get("decided_on") == today:
        return op
    rounds = st.get("rounds") or []
    series = daily_series(rounds)
    # ① 끝난 날들의 수익을 곱한다 — 그날 들고 있던 방식으로.
    after = op.get("applied_through")
    cur = series.get(op["mode"])
    for day in pd.date_range(
            (pd.Timestamp(after) + pd.Timedelta(days=1)) if after else pd.Timestamp(today),
            pd.Timestamp(today) - pd.Timedelta(days=1), freq="D"):
        r = float(cur.get(day, 0.0)) if cur is not None else 0.0
        if r != r:          # NaN — 그날 재료가 없으면 0으로 두되 기록에 남긴다
            r = 0.0
        op["equity"] = float(op["equity"]) * (1.0 + r)
        op["peak"] = max(float(op.get("peak") or 0.0), op["equity"])
        op["applied_through"] = str(day.date())
        op["history"] = (op.get("history") or [])[-(HISTORY_KEEP - 1):] + [
            {"date": str(day.date()), "equity": round(op["equity"], 4),
             "mode": op["mode"], "day_ret": round(r, 6)}]
    # ② 오늘의 방식 — 단타 운용 계좌와 같은 규칙.
    dec = IM.decide(op, series, today, modes=MODES, default=DEFAULT_MODE)
    if dec["choice"] != op["mode"]:
        cost = per_side * (_exposure(op["mode"], rounds) + _exposure(dec["choice"], rounds))
        paid = float(op["equity"]) * cost
        op["equity"] = float(op["equity"]) - paid
        op["cost_paid"] = float(op.get("cost_paid") or 0.0) + paid
        op["switches"] = (op.get("switches") or [])[-49:] + [
            {"on": today, "from": op["mode"], "to": dec["choice"],
             "t": dec.get("t"), "cost": round(paid, 4)}]
        op["mode"], op["mode_since"] = dec["choice"], today
    op["decision"], op["decided_on"] = dec, today
    return op


def public(st: dict) -> dict | None:
    from quant.live.ledger_basics import drawdown_from_index
    op = st.get("operated")
    if not op:
        return None
    base = float(op.get("start_cash") or 0.0) or 1.0
    eq = float(op.get("equity") or base)
    peak, worst = base, 0.0
    for h in op.get("history") or []:
        peak = max(peak, float(h["equity"]))
        worst = min(worst, drawdown_from_index([peak, float(h["equity"])]))
    dec = op.get("decision") or {}
    return {"since": op.get("since"), "mode": op.get("mode"),
            "mode_label": LABELS.get(op.get("mode"), op.get("mode")),
            "mode_since": op.get("mode_since"), "decision": dec,
            "switches": op.get("switches") or [],
            "start_cash": base, "equity": round(eq, 2),
            "return_pct": round((eq / base - 1) * 100, 4),
            "cost_paid": round(float(op.get("cost_paid") or 0.0), 2),
            "mdd_pct": round(worst * 100, 2),
            "as_of": op.get("applied_through"),
            "inherited_from_experiment": op.get("inherited_from_experiment"),
            "rule": {"window_days": IM.WINDOW_DAYS, "min_days": IM.MIN_DAYS,
                     "min_hold_days": IM.MIN_HOLD_DAYS,
                     "t_switch": dec.get("t_needed") or round(IM.t_switch(len(MODES)), 3),
                     "modes": dict(LABELS)}}
