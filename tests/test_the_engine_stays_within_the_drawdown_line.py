"""본 계좌 엔진은 낙폭 선을 지킨 후보 중에서만 고른다 (2026-11-09 감사 356).

사장님: 안정형 기본 + 기계 개선. 1판(최근 3년 수익률 1등)이 10/9에 고른 상대
강세(2016~ 낙폭 −25.8%)가 다음 한 달 후보 14개 중 끝에서 두 번째였다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.portfolio import engine_select as E


def _frame(n=E.WINDOW + 300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    calm = rng.normal(0.0002, 0.003, n)
    return pd.DataFrame({E.BASELINE: calm, "steady": calm + 0.0004,
                         "wild": calm + 0.0010}, index=idx)


def _crash_long_ago(r, col):
    """3년 창 **밖**(그 이전)에 −40% 급락 — 3년 창만 보면 안 보인다."""
    early = r.index[50]
    r.loc[early:early + pd.Timedelta(days=40), col] = -0.02
    return r


def test_a_crash_outside_the_3_year_window_still_disqualifies():
    r = _crash_long_ago(_frame(), "wild")
    dec = E.choose(r, r.index[-1], E.BASELINE)
    row = dec["table"]["wild"]
    assert row["mdd"] / 100 > E.STABLE_MDD, "3년 창 안에서는 멀쩡해 보여야 이 검사가 뜻이 있다"
    assert row["mdd_long"] / 100 < E.STABLE_MDD
    assert "wild" not in dec["eligible"] and dec.get("best") != "wild"


def test_an_unstable_incumbent_leaves_at_once_without_a_t_test():
    r = _crash_long_ago(_frame(), "wild")
    dec = E.choose(r, r.index[-1], "wild", held_days=1)
    assert dec["reason"] == "incumbent_unstable"
    assert dec["choice"] in dec["eligible"], "자격 없는 엔진에서 자격 없는 엔진으로 갔다"


def test_leaving_also_checks_the_wide_list():
    r = _crash_long_ago(_frame(), "wild")
    dec = E.choose(r, r.index[-1], "wild")
    w = _crash_long_ago(_frame(seed=1), dec["choice"])     # 넓은 목록에서는 그 후보가 무너졌다
    out = E.confirm_wide(dict(dec), w, w.index[-1])
    assert out["choice"] == E.BASELINE and out["reason"] == "incumbent_unstable_to_baseline"


def test_futures_keep_the_first_rule():
    """선물 후보는 1판 — 2판의 −20%는 본 계좌의 위험 선호다."""
    r = _crash_long_ago(_frame(), "wild")
    dec = E.choose(r, r.index[-1], E.BASELINE, floor=E.MDD_FLOOR)
    assert dec["rule_version"] == 1 and "wild" in dec["eligible"]


def test_the_gate_uses_the_stable_line_and_the_reasons_reach_the_screen():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "docs" / "assets" / "engine-select.js").read_text("utf-8")
    for code in ("incumbent_unstable", "incumbent_unstable_to_baseline", "none_stable"):
        assert f'"{code}":' in js
    assert "w.mdd_long" in js and "rl.version === 2" in js
    import inspect
    assert "floor: float = STABLE_MDD" in inspect.getsource(E.gate)


def test_the_stable_engine_also_runs_on_the_broad_list_and_monthly():
    """감사 358 — 안정형 엔진의 넓은 목록판·월 1회판이 링에 선다(손으로 주기를 안 바꾼다)."""
    from quant.portfolio import trend_core as T
    for n in ("risk12w", "notional50w", "notional50m", "notional50wm"):
        assert n in E.ALL_NAMES and n in E.LABELS
    assert E.universe_of("notional50w") == "wide" and E.universe_of("notional50m") == "core"
    assert E.candidate_config("notional50m").rebalance == "M"
    assert E.candidate_config("notional50").rebalance == T.TrendConfig().rebalance
    assert E.switch_threshold(len(E.ALL_NAMES)) > E.switch_threshold(15), "후보가 늘었는데 문턱이 그대로다"


def test_the_first_rule_still_refuses_a_pathological_drawdown():
    """선물 후보(1판)도 최근 3년 낙폭이 −40%보다 나쁜 후보는 안 고른다."""
    r = _frame()
    late = r.index[-300]
    r.loc[late:late + pd.Timedelta(days=60), "wild"] = -0.02
    r.iloc[-200:, 2] += 0.01
    dec = E.choose(r, r.index[-1], E.BASELINE, floor=E.MDD_FLOOR)
    assert dec["table"]["wild"]["mdd"] / 100 < E.MDD_FLOOR
    assert "wild" not in dec["eligible"]
