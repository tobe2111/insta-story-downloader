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


def _run_all(closes, fx, core_keys=None, names=None, n_family=None, mutants=None):
    """후보마다 시뮬레이션 + 선택 규칙 재생.

    core_keys: 40종목 열. 주면 40종목 후보는 그 열만, 넓은 목록 후보는 전부를
    본다(실계좌와 같은 규칙). None이면 모든 후보가 받은 열 전부를 본다
    (생존 편향 점검용 — 같은 규칙을 넓은 목록에서 돌린 쌍둥이).
    """
    cost = one_way_costs(closes.columns)
    fx_keys = {c for c in closes.columns if c.startswith("us_stock:")}
    results = {}
    for name in (names or E.CANDIDATES):
        tgt, cfg = E.candidate_targets(closes, name, core_keys=core_keys)
        results[name] = T.simulate(closes, cost, cfg, targets=tgt,
                                   fx_keys=fx_keys, fx_cost=fx)
        print(f"  · {name} 끝")
    # 감사 370 — 부모와 하는 일이 같은 변이는 빼고, 시도 수에서도 뺀다.
    noop = E.noop_mutants(results, mutants or {})
    for n in noop:
        results.pop(n)
        print(f"  · {n} — 부모와 하는 일이 같아 뺐다")
    if n_family is not None:
        n_family -= len(noop)
    # 상위 둘 섞기(감사 343 ③) — 위 후보들의 결과로 만든다(월 1회 짝 재선정).
    top2, pair = E.build_top2(results, cost, fx_keys=fx_keys, fx_cost=fx)
    results[E.TOP2] = top2
    print(f"  · {E.TOP2} 끝 — 지금 짝 {pair}")
    meta = E.meta_backtest(results, cost, fx_keys=fx_keys, fx_cost=fx,
                           n_family=n_family)
    return results, meta, pair


def _ml_targets(closes, core_keys, names):
    out = {}
    for n in names:
        if E.CANDIDATES.get(n, {}).get("kind") != "ml":
            continue
        try:
            tgt, cfg = E.candidate_targets(closes, n, core_keys=core_keys)
            day = E.target_day(tgt.index, cfg.rebalance)
            row = tgt.loc[day].fillna(0.0)
            out[n] = {"target_day": str(day.date()),
                      "trained_through": str(closes.index[-1].date()),
                      "weights": {k: round(float(v), 6) for k, v in row.items() if v}}
        except Exception as exc:  # noqa: BLE001 — 없으면 매일 배치가 기준 엔진으로 돈다
            print(f"  ✗ {n} 학습 목표 실패: {exc}")
    return out


def _run_futures(cur, prev):
    """선물 트랙의 후보 넷(감사 344 ②) — 코인만, 실측 편도 + 펀딩."""
    frames = {k: v for k, v in cur.items() if k.startswith("crypto:")}
    if not frames:
        print("  ✗ 코인 시세 없음 — 선물 선택 못 함")
        return None
    closes = T.align_business_days(frames)
    cost = one_way_costs(closes.columns)
    results = {}
    for name in E.FUT_CANDIDATES:
        tgt, cfg = E.fut_targets(closes, name)
        results[name] = T.simulate(closes, cost, cfg, targets=tgt)
        print(f"  · {name} 끝")
    # 선물 후보는 규칙 1판 그대로다(감사 356 — 2판의 낙폭 −20%는 본 계좌의 위험 선호).
    meta = E.meta_backtest(results, cost, start=E.FUT_JUDGE_START,
                           baseline=E.FUT_BASELINE, floor=E.MDD_FLOOR)
    g = E.gate(meta, results, start=E.FUT_JUDGE_START, baseline=E.FUT_BASELINE,
               floor=E.MDD_FLOOR)
    pf = (prev or {}).get("futures") or {}
    incumbent = pf.get("active") if pf.get("active") in E.FUT_CANDIDATES else E.FUT_BASELINE
    rets = pd.DataFrame({n: r.equity.pct_change() for n, r in results.items()})
    fridays = rets.index[rets.index.weekday == 4]
    day = fridays[-1] if len(fridays) else rets.index[-1]
    held = None
    if pf.get("since_switch"):
        held = int(((rets.index > pd.Timestamp(pf["since_switch"]))
                    & (rets.index <= day)).sum())
    dec = E.choose(rets, day, incumbent, held_days=held, floor=E.MDD_FLOOR)
    if g["pass"]:
        active = dec["choice"]
    else:
        active = E.FUT_BASELINE
        dec["reason"] = "gate_failed"
    switched = active != incumbent
    cands = {}
    for n, r in results.items():
        yrs = len(r.equity) / T.PERIODS
        cands[n] = {"label": E.FUT_LABELS[n], "window": dec["table"].get(n),
                    "judge": T.stats(r.equity[E.FUT_JUDGE_START:]),
                    "cost_pct_yr": round(float(r.cost.sum()) / yrs * 100, 3)}
    out = {"asof": str(day.date()), "active": active,
           "active_label": E.FUT_LABELS[active], "previous": incumbent,
           "switched": switched,
           "since_switch": str(day.date()) if switched else pf.get("since_switch"),
           "decision": dec, "gate": g, "candidates": cands,
           "rule": {"judge_start": E.FUT_JUDGE_START,
                    "funding_annual": T.FUTURES_CARRY,
                    "t_switch": E.switch_threshold(len(results))}}
    print("\n=== 감사 344 — 선물 엔진 선택 ===")
    for n, c in cands.items():
        w, j = c["window"] or {}, c["judge"] or {}
        print(f"{n:12s} 3년 {w.get('cagr')}% · 낙폭 {w.get('mdd')}% | 2022~ 연 "
              f"{j.get('cagr')}% · 샤프 {j.get('sharpe')} · 낙폭 {j.get('mdd')}% · "
              f"비용 {c['cost_pct_yr']}%/년")
    ms = g["selector"] or {}
    print(f"선택기(2022~) 연 {ms.get('cagr')}% · 낙폭 {ms.get('mdd')}% vs 기준 "
          f"{(g['baseline'] or {}).get('cagr')}% → {'통과' if g['pass'] else '미달'} · "
          f"{incumbent} → {active} ({dec['reason']}, t={dec['t']})")
    return out


def main():
    print("40종목 장기 시세 —")
    cur = fetch_all(_universe())
    core_keys = set(cur)
    fx = fx_spread(STATE_DIR)
    # 넓은 ETF 목록(감사 342·343) — 넓은 목록 후보의 재료이자 생존 편향
    # 점검의 재료다. 못 받으면 넓은 목록 후보는 **못 쟀다**로 빠지고(40종목
    # 위에서 돌리면 이름만 다른 같은 후보가 된다), 점검도 못 쟀다로 적는다.
    broad = {}
    try:
        from scripts.multi_sleeve_research import fetch_broad
        print("넓은 ETF 목록 —")
        broad = fetch_broad()
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ 넓은 목록 실패 — 넓은 목록 후보·점검 못 함: {exc}")
    closes = T.align_business_days({**broad, **cur})

    prev = _load(OUT) or {}
    eng = _load(os.path.join(STATE_DIR, "engine.json")) or {}
    # 감사 368 — 지난주까지의 변이를 후보 표에 올리고(지금 엔진이 변이일 수 있다),
    # 이번 주 변이를 지금 엔진에서 새로 만든다.
    E.register_mutants(prev.get("mutants"))
    incumbent = prev.get("active") or eng.get("variant") or E.BASELINE
    if not E.is_known(incumbent):
        incumbent = E.BASELINE
    # 감사 371 — 변이는 **결정 금요일 하나에 한 번**만 만든다. 이 잡은 토요일 예약
    # 말고도 코드가 main에 머지될 때마다 돈다(2026-11-09~10 사흘에 세 번). 돌 때마다
    # 새로 만들면 '매주 2개'가 '실행마다 2개'가 되고 시도 수가 실행 횟수를 따라 큰다.
    fri = closes.index[closes.index.weekday == 4]
    for_day = str((fri[-1] if len(fri) else closes.index[-1]).date())
    pm = prev.get("mutation") or {}
    if pm.get("for_day") == for_day:
        mutants = {n: dict(E.CANDIDATES[n], label=E.LABELS.get(n, n))
                   for n in pm.get("made") or [] if n in E.CANDIDATES}
        trials = int(prev.get("mutant_trials") or 0)
        print(f"이번 결정일({for_day}) 변이는 이미 만들었다 — 다시 쓴다(시도 수 그대로)")
    else:
        mutants = E.mutate_engine(incumbent, seed=for_day, born=for_day)
        E.register_mutants(mutants)
        trials = int(prev.get("mutant_trials") or 0) + len(mutants)
    fixed = [n for n in E.CANDIDATES if not n.startswith(E.MUTANT_PREFIX)]
    names = fixed + ([incumbent] if incumbent.startswith(E.MUTANT_PREFIX) else []) \
        + list(mutants)
    names = [n for n in dict.fromkeys(names) if broad or E.universe_of(n) == "core"]
    # 갈아타기 문턱의 가족 크기 = 고정 후보 + 상위 둘 + 지금까지 만든 변이 전부.
    n_family = len([n for n in names if not n.startswith(E.MUTANT_PREFIX)]) + 1 + trials
    print(f"자동 변이 {len(mutants)}개(기반 {incumbent}) · 누적 변이 {trials} · "
          f"문턱 t ≥ {E.switch_threshold(n_family)}")
    results, meta, top2_pair = _run_all(closes, fx, core_keys=core_keys, names=names,
                                        n_family=n_family, mutants=mutants)
    noop = [m for m in mutants if m not in results]
    noop_labels = {m: E.LABELS.get(m, m) for m in noop}
    for m in noop:
        mutants.pop(m)
        E.CANDIDATES.pop(m, None)
        E.LABELS.pop(m, None)
    trials -= len(noop)
    n_family -= len(noop)
    names = [n for n in names if n not in noop]
    wide = None
    if broad:
        print("생존 편향 점검(모든 후보를 넓은 목록에서) —")
        w_results, w_meta, _ = _run_all(closes, fx, core_keys=None, names=names,
                                        n_family=n_family)
        wide = {"results": w_results, "meta": w_meta}
    g = E.gate(meta, results, wide=wide)
    rets = pd.DataFrame({n: r.equity.pct_change() for n, r in results.items()})
    fridays = rets.index[rets.index.weekday == 4]
    day = fridays[-1] if len(fridays) else rets.index[-1]
    held = None
    if prev.get("since_switch"):
        held = int(((rets.index > pd.Timestamp(prev["since_switch"]))
                    & (rets.index <= day)).sum())
    dec = E.choose(rets, day, incumbent, held_days=held, n_family=n_family)
    w_rets = (pd.DataFrame({n: r.equity.pct_change()
                            for n, r in wide["results"].items()})
              if wide else None)
    dec = E.confirm_wide(dec, w_rets, day)
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
                    "cost_pct_yr": round(float(r.cost.sum()) / yrs * 100, 3),
                    "wide_judge": (T.stats(wide["results"][n].equity[E.JUDGE_START:])
                                   if wide else None)}
    out = {"registered_on": E.REGISTERED_ON,
           "asof": str(day.date()),
           "data_end": str(closes.index[-1].date()),
           "active": active, "active_label": E.LABELS[active],
           "top2_pair": top2_pair,
           "previous": incumbent, "switched": switched,
           "since_switch": since_switch,
           "decision": dec, "gate": g,
           "candidates": cands,
           "switches_recent": meta["switches"][-10:],
           # 감사 368 — 지금 엔진이 변이면 그 명세와 이번 주 변이를 남긴다(따를 수 있게).
           "mutants": {n: {**E.CANDIDATES[n], "label": E.LABELS[n]}
                       for n in ([active] if active.startswith(E.MUTANT_PREFIX) else [])
                       + ([incumbent] if incumbent.startswith(E.MUTANT_PREFIX) else [])
                       + list(mutants) if n in E.CANDIDATES},
           "mutant_trials": trials,
           "mutation": {"base": incumbent, "made": list(mutants),
                        "noop": noop_labels, "for_day": for_day,
                        "axes": E.MUTATION_AXES, "per_week": E.N_MUTANTS},
           "rule": {"window_days": E.WINDOW, "min_hold_days": E.MIN_HOLD,
                    "t_switch": E.switch_threshold(n_family),
                    "n_candidates": len(results), "n_family": n_family,
                    "mdd_floor_pct": E.STABLE_MDD * 100,
                    "mdd_scope": "3년 창 + 그날까지의 전 기간 · 40종목과 넓은 목록 둘 다",
                    "baseline": E.BASELINE, "version": E.RULE_VERSION,
                    "version_on": E.RULE_V2_ON,
                    "objective": "cagr_net"},
           "cost_basis": {"fx_spread": fx, "one_way": "measured_cost_model"},
           "futures": _run_futures(cur, prev),
           # 감사 362 — ML 후보는 매일 배치가 학습할 수 없다(400봉). 여기서 긴 역사로
           # 학습한 그 달의 목표를 남기고, 매일 배치·그림자가 그대로 따른다.
           "ml_targets": _ml_targets(closes, core_keys, names)}

    print(f"\n=== 감사 341·342·356 — 엔진 자동 선택 ({out['asof']}) ===")
    print(f"{'후보':12s} {'3년 연수익%':>10s} {'3년 낙폭%':>9s} {'2016~ 연수익%':>12s} "
          f"{'샤프':>5s} {'낙폭%':>7s}")
    for n, c in cands.items():
        w, j = c["window"] or {}, c["judge"] or {}
        print(f"{n:12s} {str(w.get('cagr')):>10s} {str(w.get('mdd')):>9s} "
              f"{j.get('cagr', 0):12.2f} {j.get('sharpe', 0):5.2f} {j.get('mdd', 0):7.2f}")
    ms = g["selector"] or {}
    print(f"선택기(2016~) 연수익 {ms.get('cagr')}% · 샤프 {ms.get('sharpe')} · "
          f"낙폭 {ms.get('mdd')}% · 갈아탐 {g['switches']}회")
    if g.get("wide"):
        wm, wb = g["wide"]["selector"] or {}, g["wide"]["baseline"] or {}
        print(f"넓은 목록(2016~) 선택기 연수익 {wm.get('cagr')}% · 낙폭 {wm.get('mdd')}% "
              f"vs 기준 {wb.get('cagr')}% → {'통과' if g['wide']['pass'] else '미달'}")
        for n, c in cands.items():
            j = c["wide_judge"] or {}
            print(f"  넓은 {n:12s} 연수익 {j.get('cagr')}% · 샤프 {j.get('sharpe')} · "
                  f"낙폭 {j.get('mdd')}%")
    else:
        print("넓은 목록 점검: 못 쟀다(자료 없음)")
    print(f"→ 관문 {'통과' if g['pass'] else '미달 — 기준선 유지'} · "
          f"지금 엔진 {incumbent} → {active} ({dec['reason']}, t={dec['t']})")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("ENGINE_SELECT_RESULT: " + json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
