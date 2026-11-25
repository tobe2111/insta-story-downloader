"""감사 385 — 위험 한도는 그대로, 좋은 엔진을 **덜 담아** 한도 안에 넣는다.

지키는 것:
1. 담는 비율(scale)만큼 목표 비중이 줄고 나머지는 현금이다(빚은 안 낸다).
2. 같은 엔진의 덜 담은 판은 낙폭이 그만큼 작다(행동으로 확인).
3. 담는 비율·추세 기간은 변이 축이다 — 기계가 흔든다. 그리고 하는 일이 다르면
   중복 열쇠도 다르다(같으면 변이가 '이미 재 본 것'으로 버려진다).
"""
import json

import numpy as np
import pandas as pd

from quant.portfolio import engine_select as E
from quant.portfolio import trend_core as T


def _market(n=900):
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(3)
    cols = {}
    for i, k in enumerate(["us_stock:SPY", "us_stock:QQQ", "us_stock:IEF",
                           "us_stock:GLD", "us_stock:XLE"]):
        r = 0.0003 * (i + 1) + rng.normal(0, 0.01, n)
        r[500:560] -= 0.01                       # 급락 구간
        cols[k] = 100 * np.cumprod(1 + r)
    return pd.DataFrame(cols, index=idx)


def test_scale_shrinks_weights_and_keeps_the_rest_in_cash():
    closes = _market()
    full, _ = E.candidate_targets(closes, "mvo12")
    part, _ = E.candidate_targets(closes, "mvo12s60")
    assert np.allclose(part.values, 0.6 * full.values)
    assert (part.sum(axis=1) <= 0.6 + 1e-9).all()


def test_scaled_engine_loses_less_in_a_crash():
    closes = _market()
    out = {}
    for n in ("mvo12", "mvo12s60"):
        tgt, cfg = E.candidate_targets(closes, n)
        eq = T.simulate(closes, {}, cfg, targets=tgt).equity
        out[n] = float((eq / eq.cummax() - 1).min())
    assert out["mvo12s60"] > out["mvo12"]


def test_scale_and_lookbacks_are_mutation_axes():
    for kind in ("trend", "mvo", "blend"):
        assert "scale" in E.AXES_BY_KIND[kind]
        assert "lookbacks" in E.AXES_BY_KIND[kind]
    assert "scale" in E.AXES_BY_KIND["xs"]
    assert E.config_key("mvo12") != E.config_key("mvo12s80")


def test_mutants_that_move_scale_or_lookbacks_survive_a_json_round_trip():
    made = {}
    for seed in range(30):
        made.update(E.mutate_engine("mvo12s80", seed=str(seed), n=2))
    axes = {s["label"].rsplit(" · ", 1)[-1].split(" ")[0] for s in made.values()}
    assert {"scale", "lookbacks"} & axes
    E.register_mutants(made)
    for name, spec in made.items():
        back = json.loads(json.dumps(spec))
        E.CANDIDATES["__rt__"] = back
        try:
            assert E.config_key("__rt__") == E.config_key(name)
        finally:
            E.CANDIDATES.pop("__rt__", None)
    for n in list(made):
        E.CANDIDATES.pop(n, None)
        E.LABELS.pop(n, None)


def test_new_candidates_are_labelled_and_counted():
    from scripts.managed_futures_research import TRIAL_LEDGER
    counted = set(sum(TRIAL_LEDGER.values(), []))
    for n in ("mvo12s80", "mvo12s60"):
        assert n in E.LABELS and n in counted
