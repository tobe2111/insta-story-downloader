"""단타냐 그냥 보유냐 — **기계가 고르는 운용 계좌** (감사 345).

사장님(2026-10-11): *"코인 단타 부분인데 손해 금액이 더 크네"* →
*"그냥 결과적으로 수익을 최대한 만들면 되는거야."*

실측(코인 1시간봉, 8/18~10/11): 매도 139건 중 이익 +2,099 · 손실 −1,346 ·
수수료 607 → 자산 −0.2%. 같은 기간 같은 코인을 그냥 들고 있었다면 +33.7%.
첫 주(+994)를 빼면 8/31 이후 6주 중 4주가 손실이 이익보다 컸다.

■ 무엇을 하나

  장중 실험 계좌(1시간봉 ML 단타)는 **그대로 둔다** — 사전 등록된 90일
  실험이고(판정일 11월 중순), 결과를 보고 규칙을 바꾸면 그 실험은 무효다.

  대신 옆에 **운용 계좌**를 하나 더 굴린다(같은 시드, 같은 종목, 같은 비용,
  같은 킬스위치). 이 계좌가 매일 한 번 두 방식 중 하나를 고른다.

    · trade — 실험 계좌와 같은 신호로 사고판다.
    · hold  — 종목마다 같은 금액을 들고 있는다. 비중이 밴드(5%p) 밖으로
              벗어날 때만 고쳐 잡는다(회전이 거의 없다).

  고르는 것은 사람이 아니다. 최근 90일(있는 만큼, 최소 20일) **수수료 뺀
  일수익의 차이**를 t로 재고, 엔진 선택기(감사 341)와 같은 문턱을 넘을 때만
  갈아탄다. 갈아탄 뒤 14일은 그대로 둔다 — 순위가 조금 바뀔 때마다 갈아타면
  수수료만 낸다.

■ 정직한 한계

  · 보유 쪽 일수익은 그날 종가의 **균등 평균**이다(매일 균등으로 맞춘 가정).
    실제 보유 계좌는 비중이 표류한다 — 비교용 근사다.
  · 단타 쪽 일수익은 실험 계좌의 장부(회차 자산)다. 실험 계좌는 첫 주에 크게
    벌었으므로, 창이 그 주를 포함하는 동안은 단타가 덜 불리하게 보인다.
  · 결과가 좋은 쪽을 고르는 규칙은 **과거에 강한 쪽**을 고른다. 내일도
    그렇다는 보장은 없다. 그래서 문턱과 최소 유지 기간을 둔다.
"""
from __future__ import annotations

import math

MODES = ("trade", "hold")
LABELS = {"trade": "단타(1시간봉 신호대로 사고팔기)",
          "hold": "그냥 보유(종목마다 같은 금액)"}
DEFAULT_MODE = "trade"           # 지금까지 하던 것 — 바꾸려면 기계가 이겨야 한다
WINDOW_DAYS = 90
MIN_DAYS = 20
MIN_HOLD_DAYS = 14
HOLD_BAND = 0.05                 # 보유 모드: 종목 비중이 목표에서 5%p 벗어날 때만
HISTORY_KEEP = 400


def t_switch() -> float:
    """엔진 선택기의 문턱을 빌린다(후보 2개 → 1.35). 여기서 따로 정하면 편의다."""
    from quant.portfolio.engine_select import switch_threshold
    return switch_threshold(len(MODES))


def _utc_dates(times) -> list:
    import pandas as pd
    return list(pd.to_datetime(list(times), utc=True).date)


def trade_daily_returns(rounds: list[dict]):
    """실험 계좌의 하루 마지막 자산 → 일수익.

    ⚠️ 장부의 시각은 `+00:00`과 `+09:00`이 섞여 있다 — 글자로 정렬하면 그날
    마지막 자산을 잘못 고른다(감사 331). 시각으로 바꿔 UTC 날짜로 묶는다.
    """
    import pandas as pd
    pts = [(r.get("time"), r.get("equity")) for r in rounds or []
           if r.get("time") and r.get("equity") is not None]
    if len(pts) < 2:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    ts = pd.to_datetime([p[0] for p in pts], utc=True)
    s = pd.Series([float(p[1]) for p in pts], index=ts).sort_index()
    daily = s.groupby(s.index.date).last()
    daily.index = pd.to_datetime(daily.index)
    return daily.pct_change().dropna()


def hold_daily_returns(daily_closes: dict):
    """종목별 일봉 종가 → 균등 평균 일수익(그날 값이 있는 종목끼리)."""
    import pandas as pd
    cols = {}
    for sym, df in (daily_closes or {}).items():
        if df is None or len(df) < 2:
            continue
        close = df["close"] if hasattr(df, "columns") else df
        idx = pd.DatetimeIndex(close.index)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        c = pd.Series(close.values, index=idx).astype(float)
        c = c.groupby(c.index.normalize()).last()
        cols[sym] = c.pct_change()
    if not cols:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return pd.DataFrame(cols).mean(axis=1, skipna=True).dropna()


def decide(op: dict, trade, hold, today: str) -> dict:
    """오늘의 운용 방식. 하루 한 번만 정한다(같은 날 다시 부르면 그대로)."""
    import datetime as dt

    import pandas as pd
    cur = op.get("mode") if op.get("mode") in MODES else DEFAULT_MODE
    if op.get("decided_on") == today and op.get("decision"):
        return op["decision"]
    both = (hold.rename("hold").to_frame()
            .join(trade.rename("trade"), how="inner")).dropna()
    # 오늘은 아직 안 끝난 날이다 — 넣으면 같은 날 다시 재현했을 때 답이 바뀐다.
    both.index = pd.to_datetime(both.index)
    both = both[both.index < pd.Timestamp(today)]
    both = both.iloc[-WINDOW_DAYS:]
    n = len(both)
    out = {"date": today, "incumbent": cur, "choice": cur, "n_days": n,
           "t": None, "t_needed": round(t_switch(), 3),
           "hold_pct": None, "trade_pct": None}
    if n:
        out["hold_pct"] = round((float((1 + both["hold"]).prod()) - 1) * 100, 3)
        out["trade_pct"] = round((float((1 + both["trade"]).prod()) - 1) * 100, 3)
    if n < MIN_DAYS:
        out["reason"] = "not_enough_days"
        return out
    d = both["hold"] - both["trade"]
    sd = float(d.std(ddof=1))
    t = float(d.mean()) / (sd / math.sqrt(n)) if sd > 0 else 0.0
    out["t"] = round(t, 3)
    other = "hold" if cur == "trade" else "trade"
    edge = t if other == "hold" else -t      # 다른 쪽이 앞서는 정도
    since = op.get("mode_since")
    if since:
        held = (dt.date.fromisoformat(today) - dt.date.fromisoformat(since)).days
        if held < MIN_HOLD_DAYS:
            out["reason"] = "min_hold"
            return out
    if edge >= out["t_needed"]:
        out["choice"] = other
        out["reason"] = "switch"
    else:
        out["reason"] = "keep"
    return out


def new_account(start_cash: float, today: str, currency: str) -> dict:
    return {"since": today, "start_cash": float(start_cash),
            "cash": float(start_cash), "currency": currency,
            "positions": {}, "avg_cost": {}, "cost_paid": 0.0,
            "peak_equity": float(start_cash), "risk_scale": 1.0,
            "mode": DEFAULT_MODE, "mode_since": None,
            "decided_on": None, "decision": None, "switches": [],
            "history": []}


def continue_from(st: dict, today: str) -> dict:
    """실험 계좌의 **지금 상태 그대로** 이어받는다(사장님 2026-10-11:
    "왜 0에서 시작하는거야? 계속 이어서 하면 되잖아").

    현금·보유·평단·낸 비용·고점을 복사하고, 시작 자금과 시작일도 실험 계좌의
    것을 쓴다 — 그래서 수익률·낙폭이 8/18부터 끊김 없이 이어진다. 지난 곡선은
    실험 계좌의 하루 마지막 자산으로 채운다(그때는 단타였으므로 mode=trade).
    ⚠️ 복사이지 공유가 아니다 — 이후 두 계좌는 따로 움직인다.
    """
    import copy

    import pandas as pd
    start = float(st.get("start_cash") or 10_000.0)
    op = new_account(start, today, str(st.get("currency") or "USDT"))
    for k in ("cash", "positions", "avg_cost", "cost_paid", "peak_equity",
              "risk_scale", "last_prices"):
        if st.get(k) is not None:
            op[k] = copy.deepcopy(st[k])
    rounds = [r for r in st.get("rounds") or []
              if r.get("time") and r.get("equity") is not None]
    if rounds:
        ts = pd.to_datetime([r["time"] for r in rounds], utc=True)
        s = pd.Series(range(len(rounds)), index=ts).sort_index()
        last_of_day = s.groupby(s.index.date).last()
        op["since"] = str(s.index[0].date())
        op["history"] = [
            {"time": rounds[i]["time"], "equity": float(rounds[i]["equity"]),
             "mode": "trade", "trades": len(rounds[i].get("trades") or []),
             "cost": 0.0, "inherited": True}
            for i in last_of_day.values][-(HISTORY_KEEP - 1):]
    op["inherited_from_experiment"] = today
    return op


def hold_signals(op: dict, prices: dict, equity: float, scale: float,
                 universe: list[str]) -> dict:
    """보유 모드의 목표 — 종목마다 같은 금액. 밴드 안이면 건드리지 않는다(None)."""
    slice_budget = equity / len(universe) if universe else 0.0
    out = {}
    for sym in universe:
        px = prices.get(sym)
        if not px or slice_budget <= 0:
            out[sym] = None
            continue
        cur = float((op.get("positions") or {}).get(sym, 0.0)) * float(px)
        target = slice_budget * scale
        out[sym] = None if abs(target - cur) < HOLD_BAND * equity else 1.0
    return out


def advance(op: dict, *, mode_signals: dict, prices: dict, per_side: float,
            universe: list[str], now_iso: str) -> dict:
    """운용 계좌 한 회차 — 실험 계좌와 **같은 체결 함수·같은 킬스위치**."""
    from quant.live.daily import _kill_switch_scale
    from quant.live.intraday_challenger import _execute_targets, mark_equity
    from quant.live.ledger_basics import drawdown_from_index

    equity = mark_equity(op, prices)
    peak = max(float(op.get("peak_equity") or 0.0), equity)
    op["peak_equity"] = peak
    dd = drawdown_from_index([peak, equity]) if peak > 0 else 0.0
    scale = _kill_switch_scale(float(op.get("risk_scale", 1.0)), dd)
    op["risk_scale"] = scale
    if op.get("mode") == "hold":
        sig = hold_signals(op, prices, equity, scale, universe)
    else:
        sig = mode_signals
    trades = _execute_targets(op, sig, prices, equity, scale, per_side,
                              universe=universe)
    last = dict(op.get("last_prices") or {})
    last.update(prices)
    op["last_prices"] = last
    after = mark_equity(op, prices)
    op["history"] = (op.get("history") or [])[-(HISTORY_KEEP - 1):] + [
        {"time": str(now_iso), "equity": round(after, 2),
         "mode": op.get("mode"), "trades": len(trades),
         "cost": round(sum(t.get("cost", 0.0) for t in trades), 4)}]
    return {"equity": round(after, 2), "trades": trades}


def utc_day(now_iso: str) -> str:
    import pandas as pd
    ts = pd.Timestamp(str(now_iso))
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return str(ts.date())


def needs_decision(st: dict, now_iso: str) -> bool:
    """오늘 아직 안 정했나 — 일봉 시세는 이때만 받는다(회차마다 받지 않는다)."""
    return (st.get("operated") or {}).get("decided_on") != utc_day(now_iso)


def step(st: dict, *, today: str, now_iso: str, prices: dict, signals: dict,
         per_side: float, universe: list[str], daily_closes: dict) -> dict:
    """정하고(하루 한 번) → 굴린다(매 회차). 실험 계좌 `st` 안에 `operated`로 산다."""
    op = st.get("operated")
    if not op:
        op = continue_from(st, today)
        st["operated"] = op
    if op.get("decided_on") != today:
        dec = decide(op, trade_daily_returns(st.get("rounds") or []),
                     hold_daily_returns(daily_closes), today)
        if dec["choice"] != op.get("mode"):
            op["switches"] = (op.get("switches") or [])[-49:] + [
                {"on": today, "from": op.get("mode"), "to": dec["choice"],
                 "t": dec.get("t")}]
            op["mode"] = dec["choice"]
            op["mode_since"] = today
        op["decision"] = dec
        op["decided_on"] = today
    return advance(op, mode_signals=signals, prices=prices, per_side=per_side,
                   universe=universe, now_iso=now_iso)


def public(st: dict) -> dict | None:
    """공개 자료 탑재용 — 지금 방식 · 근거 · 성적 · 낸 비용."""
    op = st.get("operated")
    if not op:
        return None
    hist = op.get("history") or []
    eq = float(hist[-1]["equity"]) if hist else float(op["start_cash"])
    base = float(op.get("start_cash") or 0.0) or 1.0
    from quant.live.ledger_basics import drawdown_from_index
    peak, worst = base, 0.0
    for h in hist:
        peak = max(peak, float(h["equity"]))
        worst = min(worst, drawdown_from_index([peak, float(h["equity"])]))
    return {"since": op.get("since"), "mode": op.get("mode"),
            "mode_label": LABELS.get(op.get("mode"), op.get("mode")),
            "mode_since": op.get("mode_since"),
            "decision": op.get("decision"), "switches": op.get("switches") or [],
            "start_cash": base, "equity": round(eq, 2),
            "return_pct": round((eq / base - 1) * 100, 4),
            "cost_paid": round(float(op.get("cost_paid") or 0.0), 2),
            "mdd_pct": round(worst * 100, 2),
            "inherited_from_experiment": op.get("inherited_from_experiment"),
            "positions": {k: round(float(v), 8)
                          for k, v in (op.get("positions") or {}).items()},
            "rule": {"window_days": WINDOW_DAYS, "min_days": MIN_DAYS,
                     "min_hold_days": MIN_HOLD_DAYS, "hold_band": HOLD_BAND,
                     "t_switch": round(t_switch(), 3)}}
