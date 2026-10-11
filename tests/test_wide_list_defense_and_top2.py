"""넓은 목록 매매 · 하락장 방어 · 상위 둘 섞기 (감사 343).

사장님(2026-10-11): "모두 진행해 3번까지 순서대로".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import daily as D  # noqa: E402
from quant.live import engine_shadow as S  # noqa: E402
from quant.portfolio import engine_select as E  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402

CORE = ["us_stock:SPY", "us_stock:IEF", "kr_stock:069500.KS", "us_stock:GLD",
        "crypto:BTC/USDT"]
EXTRA = ["us_stock:XLK", "us_stock:SMH", "us_stock:EWY", "us_stock:TLT"]


def _closes(n=420, spy_drift=0.0008, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-06-03", periods=n)
    out = {}
    for i, k in enumerate(CORE + EXTRA):
        d = spy_drift if k == "us_stock:SPY" else 0.0004 * (i + 1)
        out[k] = pd.Series(100 * np.exp(np.cumsum(rng.normal(d, 0.01, n))), index=idx)
    return out


# ── ① 넓은 목록 ────────────────────────────────────────────────────

def test_core_candidates_ignore_the_extra_etfs_and_wide_ones_use_them():
    c = T.align_business_days(_closes())
    core_t, _ = E.candidate_targets(c, "xs12", core_keys=set(CORE))
    wide_t, _ = E.candidate_targets(c, "xs12w", core_keys=set(CORE))
    assert (core_t[EXTRA].abs().sum().sum()) == 0, "40종목 후보가 넓은 ETF를 샀다"
    assert (wide_t[EXTRA].abs().sum().sum()) > 0, "넓은 목록 후보가 넓은 ETF를 안 본다"
    assert list(core_t.columns) == list(c.columns)


def test_the_extra_keys_are_the_wide_list_minus_the_core():
    keys = E.wide_extra_keys(["us_stock:SPY", "us_stock:QQQ"])
    assert "us_stock:SPY" not in keys and "us_stock:XLK" in keys
    assert set(keys) | {"us_stock:SPY", "us_stock:QQQ"} >= set(E.WIDE_KEYS)


def test_the_daily_engine_buys_extras_only_for_a_wide_engine(tmp_path):
    (tmp_path / "engine.json").write_text(json.dumps({"engine": "trend_core",
                                                      "variant": "risk12"}))
    closes = _closes()
    weights = {k: 0.0 for k in CORE}
    last = str(pd.bdate_range("2024-06-03", periods=420)[-1].date())
    for name, buys_extra in (("xs12", False), ("xs12w", True)):
        (tmp_path / E.SELECT_FILE).write_text(json.dumps(
            {"active": name, "asof": last, "gate": {"pass": True}}))
        out = D._core_targets(str(tmp_path), closes, weights)
        got = sum(abs(out["weights"].get(k, 0.0)) for k in EXTRA)
        assert (got > 0) == buys_extra, name


def test_extras_stay_out_of_the_old_system_inputs():
    """넓은 ETF가 weights·rets_map에 끼면 사전 등록 실험의 재료가 바뀐다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    block = src[src.index("extra_keys: list = []"):src.index('raise RuntimeError("포트폴리오: 전 종목 데이터 실패')]
    assert "weights[" not in block and "rets_map[" not in block
    assert "trade_keys = list(weights) + [k for k in extra_keys if k not in weights]" in src
    assert "for key in sorted(trade_keys, key=_sell_first):" in src
    assert "extra_skipped[key]" in block and "skipped.append" not in block, (
        "엔진 전용 종목 장애가 운용 명단 결손 경보와 섞였다")


# ── ② 하락장 방어 ──────────────────────────────────────────────────

def test_the_market_filter_backs_off_in_a_falling_market():
    c = T.align_business_days(_closes(spy_drift=-0.004))
    f = E.market_filter(c)
    assert float(f.iloc[-1]) == 0.0, "시장이 모든 기간에서 내렸는데 필터가 안 걸렸다"
    plain, _ = E.candidate_targets(c, "xs12", core_keys=set(CORE))
    guarded, _ = E.candidate_targets(c, "xs12f", core_keys=set(CORE))
    assert guarded.iloc[-1].abs().sum() == 0 and plain.iloc[-1].abs().sum() > 0


def test_an_unmeasured_market_is_not_treated_as_falling():
    c = T.align_business_days({k: v for k, v in _closes().items()
                               if k != "us_stock:SPY"})
    assert (E.market_filter(c) == 1.0).all()


# ── 후보가 늘면 문턱이 오른다 ──────────────────────────────────────

def test_more_candidates_raise_the_switch_bar():
    assert E.switch_threshold(6) == E.T_SWITCH
    assert E.switch_threshold(3) == E.T_SWITCH, "후보가 적다고 문턱이 내려갔다"
    assert E.switch_threshold(11) > E.switch_threshold(7) > E.T_SWITCH
    n = len(E.ALL_NAMES)
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=E.WINDOW + 10)
    base = rng.normal(0.0002, 0.01, len(idx))
    cols = {f"c{i}": base + rng.normal(0, 0.0001, len(idx)) for i in range(n - 2)}
    r = pd.DataFrame({"risk12": base, "xs12": base + 0.00045
                      + rng.normal(0, 0.002, len(idx)), **cols}, index=idx)
    dec = E.choose(r, idx[-1], "risk12")
    assert dec["t_needed"] == E.switch_threshold(r.shape[1])


# ── ③ 상위 둘 섞기 ────────────────────────────────────────────────

def _res(daily, idx, w):
    eq = pd.Series((1 + daily).cumprod(), index=idx)
    return T.TrendResult(equity=eq, returns=eq.pct_change(),
                         weights=pd.DataFrame(w, index=idx),
                         turnover=eq * 0, cost=eq * 0, gross=eq * 0)


def test_top2_picks_the_two_best_and_earns_half_of_each():
    idx = pd.bdate_range("2020-01-01", periods=E.WINDOW + 120)
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.005, len(idx))
    res = {"a": _res(0.0010 + noise, idx, {"us_stock:SPY": 1.0}),
           "b": _res(0.0008 + noise, idx, {"us_stock:QQQ": 1.0}),
           "c": _res(-0.0002 + noise, idx, {"kr_stock:069500.KS": 1.0})}
    top, pair = E.build_top2(res, {"us_stock:SPY": 0.001, "us_stock:QQQ": 0.001})
    assert sorted(pair) == ["a", "b"]
    last = idx[-1]
    w = top.weights.loc[last]
    assert w["us_stock:SPY"] == pytest.approx(0.5) and w["us_stock:QQQ"] == pytest.approx(0.5)
    r = top.equity.pct_change().loc[last]
    expect = 0.5 * res["a"].equity.pct_change().loc[last] + 0.5 * res["b"].equity.pct_change().loc[last]
    assert r == pytest.approx(expect, abs=1e-12)
    assert top.cost.sum() > 0, "짝을 처음 잡을 때 비용을 안 뗐다"


def test_top2_repicks_only_once_a_month():
    idx = pd.bdate_range("2026-01-01", "2026-03-31")
    days = sorted(E._repick_days(idx))
    assert [d.month for d in days] == [1, 2, 3]
    assert all(d.weekday() == 4 for d in days)


def test_top2_today_is_half_of_each_and_needs_a_pair(tmp_path):
    c = T.align_business_days(_closes())
    a = E.targets_today(c, "xs12", core_keys=set(CORE))
    b = E.targets_today(c, "risk12", core_keys=set(CORE))
    t = E.targets_today(c, E.TOP2, core_keys=set(CORE),
                        state={"top2_pair": ["xs12", "risk12"]})
    for k in CORE:
        assert t["weights"][k] == pytest.approx(0.5 * a["weights"][k] + 0.5 * b["weights"][k])
    with pytest.raises(ValueError):
        E.targets_today(c, E.TOP2, core_keys=set(CORE), state={})
    st = {"active": E.TOP2, "asof": "2026-10-09", "gate": {"pass": True}}
    assert E.active_choice(st, "2026-10-10") is None, "짝 없는 top2를 따랐다"
    assert E.active_choice({**st, "top2_pair": ["xs12", "risk12"]}, "2026-10-10") == E.TOP2


def test_shadows_run_top2_only_when_the_pair_is_known(tmp_path):
    c = _closes()
    marks = {k: float(v.iloc[-1]) for k, v in c.items()}
    r = S.run_engine_shadow(bar="2026-10-09", closes_map=c,
                            weights={k: 0.0 for k in CORE}, marks=marks,
                            active=None, state_dir=str(tmp_path))
    assert E.TOP2 not in r["arms"]
    (tmp_path / E.SELECT_FILE).write_text(json.dumps({"top2_pair": ["xs12", "risk12"]}))
    r = S.run_engine_shadow(bar="2026-10-12", closes_map=c,
                            weights={k: 0.0 for k in CORE}, marks=marks,
                            active=None, state_dir=str(tmp_path))
    assert E.TOP2 in r["arms"] and "xs12w" in r["arms"]


def test_every_name_has_a_screen_label():
    assert set(E.ALL_NAMES) <= set(E.LABELS)
    js = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")
    missing = [v for v in E.LABELS.values() if f'"{v}":' not in js]
    assert not missing, f"영어 없는 후보 이름: {missing}"
