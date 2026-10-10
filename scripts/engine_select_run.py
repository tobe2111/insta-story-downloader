"""매주 엔진을 고른다 — `quant/portfolio/engine_select.py`의 규칙 그대로 (감사 341).

GitHub Actions(`engine-select.yml`)에서 돈다 — 매일 배치는 400봉만 받으므로
3년 창과 2016년 이후 검증을 할 수 없고, 이 컨테이너는 시세 서버에 못 닿는다.

결과는 `state/engine_select.json`에 쓰고(main에서만 커밋), 로그에
`ENGINE_SELECT_RESULT:` 한 줄 JSON으로도 찍는다.
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, ".")

from quant.live.tax_kr import fx_spread  # noqa: E402
from quant.portfolio import engine_select as E  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402
from scripts.trend_core_research import (  # noqa: E402
    fetch_all, one_way_costs, _universe)

STATE_DIR = "state"
OUT = os.path.join(STATE_DIR, E.SELECT_FILE)


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main():
    print("40종목 장기 시세 —")
    closes = T.align_business_days(fetch_all(_universe()))
    cost = one_way_costs(closes.columns)
    fx_keys = {c for c in closes.columns if c.startswith("us_stock:")}
    fx = fx_spread(STATE_DIR)
    results = {}
    for name in E.CANDIDATES:
        tgt, cfg = E.candidate_targets(closes, name)
        results[name] = T.simulate(closes, cost, cfg, targets=tgt,
                                   fx_keys=fx_keys, fx_cost=fx)
        print(f"  · {name} 끝")
    meta = E.meta_backtest(results, cost, fx_keys=fx_keys, fx_cost=fx)
    g = E.gate(meta, results)

    prev = _load(OUT) or {}
    eng = _load(os.path.join(STATE_DIR, "engine.json")) or {}
    incumbent = prev.get("active") or eng.get("variant") or E.BASELINE
    if incumbent not in E.CANDIDATES:
        incumbent = E.BASELINE
    rets = pd.DataFrame({n: r.equity.pct_change() for n, r in results.items()})
    fridays = rets.index[rets.index.weekday == 4]
    day = fridays[-1] if len(fridays) else rets.index[-1]
    held = None
    if prev.get("since_switch"):
        held = int(((rets.index > pd.Timestamp(prev["since_switch"]))
                    & (rets.index <= day)).sum())
    dec = E.choose(rets, day, incumbent, held_days=held)
    if g["pass"]:
        active = dec["choice"]
    else:
        active = E.BASELINE
        dec["reason"] = "gate_failed"
    switched = active != incumbent
    since_switch = str(day.date()) if switched else prev.get("since_switch")

    cands = {}
    for n, r in results.items():
        yrs = len(r.equity) / T.PERIODS
        cands[n] = {"label": E.LABELS[n],
                    "window": dec["table"].get(n),
                    "judge": T.stats(r.equity[E.JUDGE_START:]),
                    "cost_pct_yr": round(float(r.cost.sum()) / yrs * 100, 3)}
    out = {"registered_on": E.REGISTERED_ON,
           "asof": str(day.date()),
           "data_end": str(closes.index[-1].date()),
           "active": active, "active_label": E.LABELS[active],
           "previous": incumbent, "switched": switched,
           "since_switch": since_switch,
           "decision": dec, "gate": g,
           "candidates": cands,
           "switches_recent": meta["switches"][-10:],
           "rule": {"window_days": E.WINDOW, "min_hold_days": E.MIN_HOLD,
                    "t_switch": E.T_SWITCH, "mdd_floor_pct": E.MDD_FLOOR * 100,
                    "objective": "cagr_net"},
           "cost_basis": {"fx_spread": fx, "one_way": "measured_cost_model"}}

    print(f"\n=== 감사 341 — 엔진 자동 선택 ({out['asof']}) ===")
    print(f"{'후보':12s} {'3년 연수익%':>10s} {'3년 낙폭%':>9s} {'2016~ 연수익%':>12s} "
          f"{'샤프':>5s} {'낙폭%':>7s}")
    for n, c in cands.items():
        w, j = c["window"] or {}, c["judge"] or {}
        print(f"{n:12s} {str(w.get('cagr')):>10s} {str(w.get('mdd')):>9s} "
              f"{j.get('cagr', 0):12.2f} {j.get('sharpe', 0):5.2f} {j.get('mdd', 0):7.2f}")
    ms = g["selector"] or {}
    print(f"선택기(2016~) 연수익 {ms.get('cagr')}% · 샤프 {ms.get('sharpe')} · "
          f"낙폭 {ms.get('mdd')}% · 갈아탐 {g['switches']}회")
    print(f"→ 관문 {'통과' if g['pass'] else '미달 — 기준선 유지'} · "
          f"지금 엔진 {incumbent} → {active} ({dec['reason']}, t={dec['t']})")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("ENGINE_SELECT_RESULT: " + json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
