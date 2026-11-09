"""ML 종목 순위 엔진 — 미래를 안 보고, 실계좌와 검증이 같은 모델이다 (2026-11-09 감사 362)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.portfolio import engine_select as E
from quant.portfolio import ml_rank as M


def _closes(n=252 * 7, k=12, seed=0, signal=False):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0003, 0.01, (n, k))
    idx = pd.bdate_range("2012-01-02", periods=n)
    if signal:
        # 지난 63일 수익이 높았던 자산이 다음 날도 조금 더 번다 — 배울 것이 있는 세계.
        c = 100 * np.exp(np.cumsum(r, axis=0))
        for t in range(64, n):
            m = c[t - 1] / c[t - 64] - 1
            r[t] += 0.002 * np.sign(m - np.median(m))
            c[t] = c[t - 1] * np.exp(r[t])
    c = 100 * np.exp(np.cumsum(r, axis=0))
    return pd.DataFrame(c, index=idx, columns=[f"us_stock:S{i}" for i in range(k)])


def test_cutting_the_future_does_not_change_the_past():
    c = _closes()
    full = M.ml_weights(c)
    cut = c.index[1300]
    part = M.ml_weights(c.loc[:cut])
    me = [d for d in M.month_ends(c.index) if d < cut - pd.Timedelta(days=31)]
    d = me[-1]
    assert np.allclose(full.loc[:d].values, part.loc[:d].values), "미래 자료가 과거 비중을 바꿨다"


def test_nothing_is_held_before_three_years_of_answers():
    c = _closes()
    w = M.ml_weights(c)
    first = w.index[w.sum(axis=1) > 0][0]
    me = M.month_ends(c.index)
    assert first >= me[M.MIN_TRAIN_MONTHS], "3년치 정답이 쌓이기 전에 담았다"


def test_it_learns_when_there_is_something_to_learn():
    c = _closes(signal=True, seed=3)
    sc = M.scores(c).dropna(how="all")
    px = c.loc[sc.index]
    fwd = (px.shift(-1) / px - 1)
    ic = [sc.loc[d].corr(fwd.loc[d], method="spearman") for d in sc.index[:-1]]
    assert np.nanmean(ic) > 0.05, f"배울 것이 있는 세계에서 못 배웠다(IC {np.nanmean(ic):.3f})"


def test_the_live_account_follows_the_weekly_trained_targets():
    c = _closes(n=400)                         # 매일 배치처럼 짧은 역사
    st = {"ml_targets": {"mlrank": {"target_day": "2013-07-31", "trained_through": "x",
                                    "weights": {"us_stock:S1": 0.3}}}}
    t = E.targets_today(c, "mlrank", None, st)
    assert t["weights"]["us_stock:S1"] == 0.3 and t["target_day"] == "2013-07-31"
    t2 = E.targets_today(c, "mlrank", None, {})
    assert t2.get("fallback") and "기준 엔진" in t2["fallback"], "학습 목표가 없는데 조용히 현금이 됐다"


def test_the_ml_candidates_stand_in_the_ring():
    for n in ("mlrank", "mlrankw"):
        assert n in E.ALL_NAMES and n in E.LABELS
    assert E.candidate_config("mlrank").rebalance == "M"
