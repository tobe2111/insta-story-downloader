"""엔진 후보도 기계가 만든다 — 한 칸 변이 · 같은 관문 · 누적 시도로 문턱 상승 (2026-11-10 감사 368)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from quant.portfolio import engine_select as E


@pytest.fixture(autouse=True)
def _clean_registry():
    before_c, before_l = dict(E.CANDIDATES), dict(E.LABELS)
    yield
    E.CANDIDATES.clear(); E.CANDIDATES.update(before_c)
    E.LABELS.clear(); E.LABELS.update(before_l)


def _closes(n=700, k=10, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2014-01-01", periods=n)
    r = rng.normal(0.0003, 0.01, (n, k))
    return pd.DataFrame(100 * np.exp(np.cumsum(r, 0)), index=idx,
                        columns=[f"us_stock:A{i}" for i in range(k)])


def _one_knob_apart(name, base):
    a, b = E.candidate_config(name).__dict__, E.candidate_config(base).__dict__
    return [k for k in a if a[k] != b[k]]


def test_mutants_move_one_knob_one_step_and_are_deterministic():
    m1 = E.mutate_engine("notional50", seed="2026-11-06")
    m2 = E.mutate_engine("notional50", seed="2026-11-06")
    assert m1.keys() == m2.keys() and len(m1) == E.N_MUTANTS
    E.register_mutants(m1)
    for name, spec in m1.items():
        assert name.startswith(E.MUTANT_PREFIX) and spec["parent"] == "notional50"
        diff = _one_knob_apart(name, "notional50")
        assert len(diff) == 1, diff
        axis = diff[0]
        vals = E.MUTATION_AXES[axis]
        new, old = getattr(E.candidate_config(name), axis), getattr(
            E.candidate_config("notional50"), axis)
        assert new in vals
        if old in vals:
            assert abs(vals.index(new) - vals.index(old)) == 1, "한 칸보다 멀리 갔다"
        assert "자동 변이" in spec["label"]


def test_a_mutant_never_duplicates_an_existing_candidate():
    fixed = {json.dumps(E.candidate_config(c).__dict__, sort_keys=True, default=str)
             + E.universe_of(c) + E.CANDIDATES[c]["kind"]
             for c in E.CANDIDATES if E.CANDIDATES[c]["kind"] in E.AXES_BY_KIND}
    for seed in ("a", "b", "c", "d"):
        for base in ("risk12", "notional50", "xs12", "mvo12"):
            for name, spec in E.mutate_engine(base, seed=seed).items():
                E.register_mutants({name: spec})
                key = (json.dumps(E.candidate_config(name).__dict__, sort_keys=True,
                                  default=str) + E.universe_of(name) + spec["kind"])
                assert key not in fixed, f"{base}의 변이가 기존 후보와 같다"


def test_unmutable_engines_breed_from_the_baseline():
    for base in ("hold40", "6040", "mlrank", E.TOP2):
        m = E.mutate_engine(base, seed="x")
        assert m and all(s["parent"] == E.BASELINE for s in m.values())


def test_a_registered_mutant_can_be_followed_tomorrow(tmp_path):
    m = E.mutate_engine("notional50", seed="2026-11-06")
    name = next(iter(m))
    st = {"active": name, "asof": "2026-11-06", "gate": {"pass": True},
          "mutants": m}
    (tmp_path / E.SELECT_FILE).write_text(json.dumps(st), "utf-8")
    E.CANDIDATES.pop(name, None)
    assert not E.is_known(name)
    loaded = E.load_state(str(tmp_path))
    assert E.is_known(name) and E.active_choice(loaded, "2026-11-09") == name
    t = E.targets_today(_closes(), name)
    assert t["target_day"] and sum(t["weights"].values()) >= 0


def test_the_registry_refuses_strangers():
    E.register_mutants({"risk12": {"kind": "trend", "variant": "risk20"},
                        "mut-bad": {"kind": "hold", "variant": "risk12"},
                        "mut-x": "nope"})
    assert E.CANDIDATES["risk12"]["variant"] == "risk12", "고정 후보를 덮어썼다"
    assert "mut-bad" not in E.CANDIDATES and "mut-x" not in E.CANDIDATES


def test_more_trials_raise_the_bar():
    idx = pd.bdate_range("2020-01-01", periods=E.WINDOW + 10)
    rng = np.random.default_rng(1)
    rets = pd.DataFrame({"notional50": rng.normal(0.0002, 0.005, len(idx)),
                         "risk12": rng.normal(0.0012, 0.005, len(idx))}, index=idx)
    a = E.choose(rets, idx[-1], "notional50")
    b = E.choose(rets, idx[-1], "notional50", n_family=300)
    assert b["t_needed"] > a["t_needed"] >= E.T_SWITCH


def test_the_weekly_job_breeds_and_counts_across_weeks(tmp_path, monkeypatch):
    """주간 잡을 두 주 돌린다 — 변이가 장부에 남고, 누적 시도가 쌓이고, 문턱이 따라 오른다."""
    import scripts.engine_select_run as R
    import scripts.multi_sleeve_research as MS

    c = _closes(n=1400, k=10)
    frames = {col: pd.DataFrame({"close": c[col]}) for col in c.columns}
    monkeypatch.setattr(R, "_universe", lambda: list(c.columns))
    monkeypatch.setattr(R, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(R, "OUT", str(tmp_path / E.SELECT_FILE))
    monkeypatch.setattr(MS, "fetch_broad", lambda: (_ for _ in ()).throw(RuntimeError("no net")))
    monkeypatch.setattr(R, "_run_futures", lambda cur, prev: None)
    monkeypatch.setattr(R, "_ml_targets", lambda *a: {})
    # 무거운 후보(ML·최적화)는 빼고 돈다 — 이 검사가 보는 것은 배선이다.
    keep = {k: v for k, v in E.CANDIDATES.items() if v["kind"] in ("trend", "xs", "blend")}
    monkeypatch.setattr(E, "CANDIDATES", keep)

    def fetch(_u, c=c):
        return {k: c[k].dropna() for k in c.columns}
    monkeypatch.setattr(R, "fetch_all", fetch)
    R.main()
    w1 = json.loads((tmp_path / E.SELECT_FILE).read_text("utf-8"))
    assert w1["mutant_trials"] == E.N_MUTANTS and len(w1["mutation"]["made"]) == E.N_MUTANTS
    assert all(n in w1["candidates"] for n in w1["mutation"]["made"]), "변이가 링에 안 섰다"
    assert set(w1["mutation"]["made"]) <= set(w1["mutants"])
    t1 = w1["rule"]["t_switch"]

    c2 = _closes(n=1405, k=10)
    monkeypatch.setattr(R, "fetch_all", lambda _u, c=c2: {k: c[k].dropna() for k in c.columns})
    R.main()
    w2 = json.loads((tmp_path / E.SELECT_FILE).read_text("utf-8"))
    assert w2["mutant_trials"] == 2 * E.N_MUTANTS, "누적 시도를 안 셌다"
    assert w2["rule"]["t_switch"] >= t1
    assert w2["rule"]["n_family"] > w1["rule"]["n_family"]
    if w2["active"].startswith(E.MUTANT_PREFIX):
        assert w2["active"] in w2["mutants"], "변이를 골라 놓고 명세를 안 남겼다 — 내일 못 따른다"
