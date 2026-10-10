"""엔진이 바뀐 날 · 생존 편향 점검 · 후보 그림자 계좌 (감사 342).

사장님(2026-10-10): "모두 진행해" — 엔진 선택(감사 341)의 후속 셋.
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


# ── ① 엔진이 바뀐 날의 대기 주문 ─────────────────────────────────────

def test_the_engine_that_placed_the_orders_is_remembered_or_inferred():
    assert D._pending_engine({"pending_engine": "risk12"}) == "risk12"
    # 칸이 생기기 전의 주문 — 마지막 기록의 엔진으로 추정한다
    st = {"history": [{"date": "2026-10-09", "engine": {"variant": "risk12"}}]}
    assert D._pending_engine(st) == "risk12"
    st = {"history": [{"date": "2026-10-08", "engine": None}]}
    assert D._pending_engine(st) == "champions"
    # 엔진 칸 자체가 없던 옛 기록 — 모르면 안 버린다
    assert D._pending_engine({"history": [{"date": "2026-09-01"}]}) is None
    assert D._pending_engine({}) is None


def test_the_daily_run_drops_old_engine_orders_and_says_so():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "was = _pending_engine(st)" in src
    assert "if was is not None and was != now_name:" in src
    assert 'st["pending_engine"] = (core["variant"] if core is not None else "champions")' in src
    assert '"pending_dropped": pending_dropped' in src, "버린 사실이 장부에 안 남는다"
    js = (ROOT / "docs" / "assets" / "cash-waterfall.js").read_text("utf-8")
    assert "pending_dropped" in js, "버린 사실이 화면에 안 나온다"


def test_the_live_and_shadow_target_day_are_one_rule():
    idx = pd.bdate_range("2026-09-01", "2026-10-14")
    assert E.target_day(idx, "W-FRI") == pd.Timestamp("2026-10-09")
    assert E.target_day(idx, "M") == pd.Timestamp("2026-09-30")
    assert E.target_day(idx, "D") == idx[-1]
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "day = E.target_day(tgt.index, cfg.rebalance)" in src


# ── ② 생존 편향 점검 — 넓은 ETF 목록에서도 이겨야 ───────────────────

def _wide(edge):
    rng = np.random.default_rng(1)
    n = E.WINDOW + 20
    idx = pd.bdate_range("2020-01-01", periods=n)
    base = rng.normal(0.0002, 0.01, n)
    return pd.DataFrame({"risk12": base, "xs12": base + edge}, index=idx)


def test_a_switch_that_only_wins_on_the_hand_picked_list_is_held_back():
    w = _wide(edge=-0.0005)
    dec = {"reason": "switch", "choice": "xs12", "incumbent": "risk12"}
    out = E.confirm_wide(dict(dec), w, w.index[-1])
    assert out["choice"] == "risk12" and out["reason"] == "not_robust"
    w = _wide(edge=0.0005)
    out = E.confirm_wide(dict(dec), w, w.index[-1])
    assert out["choice"] == "xs12" and out["reason"] == "switch"


def test_unmeasured_wide_list_is_written_down_not_treated_as_failure():
    dec = {"reason": "switch", "choice": "xs12", "incumbent": "risk12"}
    out = E.confirm_wide(dict(dec), None, "2026-10-09")
    assert out["choice"] == "xs12" and out["wide"] is None


def _res(cagr_daily):
    idx = pd.bdate_range("2015-01-01", periods=900)
    eq = pd.Series((1 + cagr_daily) ** np.arange(1, 901), index=idx)
    return T.TrendResult(equity=eq, returns=eq.pct_change(), weights=pd.DataFrame(index=idx),
                         turnover=eq * 0, cost=eq * 0, gross=eq * 0)


def test_the_gate_also_needs_the_wide_list():
    results = {"risk12": _res(0.0001)}
    meta = {"stats": T.stats(_res(0.0003).equity["2016-01-01":]), "switches": []}
    assert E.gate(meta, results)["pass"]
    bad = {"results": {"risk12": _res(0.0004)},
           "meta": {"stats": T.stats(_res(0.0002).equity["2016-01-01":]), "switches": []}}
    g = E.gate(meta, results, wide=bad)
    assert not g["pass"] and g["wide"]["pass"] is False


# ── ③ 후보 그림자 계좌 ──────────────────────────────────────────────

def _closes(n=420):
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2024-06-03", periods=n)
    out = {}
    for i, k in enumerate(["us_stock:SPY", "us_stock:IEF", "kr_stock:069500.KS",
                           "us_stock:GLD", "crypto:BTC/USDT"]):
        out[k] = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0006 * (i + 1), 0.01, n))),
                           index=idx)
    return out


def _run(tmp_path, closes, bar, marks):
    return S.run_engine_shadow(bar=bar, closes_map=closes,
                               weights={k: 0.0 for k in closes}, marks=marks,
                               active="xs12", state_dir=str(tmp_path))


def test_shadows_advance_once_per_bar_and_never_backwards(tmp_path):
    c = _closes()
    m1 = {k: float(v.iloc[-1]) for k, v in c.items()}
    r1 = _run(tmp_path, c, "2026-10-09", m1)
    assert set(r1["arms"]) == set(E.CANDIDATES)
    assert all(a["equity"] < S.START for a in r1["arms"].values()
               if a["gross"] > 0), "첫날 매수 비용을 안 뗐다"
    again = _run(tmp_path, c, "2026-10-09", m1)
    assert again == r1, "같은 봉을 두 번 셌다"
    assert _run(tmp_path, c, "2026-10-08", m1) is None, "과거로 가는 봉을 썼다"


def test_shadow_returns_follow_held_weights_and_prices(tmp_path):
    c = _closes()
    m1 = {k: float(v.iloc[-1]) for k, v in c.items()}
    r1 = _run(tmp_path, c, "2026-10-09", m1)
    st = json.loads((tmp_path / S.FILE).read_text())
    held = st["arms"]["risk12"]["held"]
    m2 = {k: p * (1.10 if k == "us_stock:SPY" else 1.0) for k, p in m1.items()}
    r2 = _run(tmp_path, c, "2026-10-12", m2)
    expect = held.get("us_stock:SPY", 0.0) * 0.10
    assert r2["arms"]["risk12"]["day_ret"] == pytest.approx(expect, abs=1e-6)
    assert r1["arms"]["risk12"]["equity"] != r2["arms"]["risk12"]["equity"] or expect == 0


def test_the_band_and_liquidation_rules_match_the_simulation():
    held = {"a": 0.30, "b": 0.10}
    new = S.rebalance(held, {"a": 0.31, "c": 0.20})
    assert new["a"] == 0.30, "밴드 안의 차이를 고쳤다"
    assert "b" not in new, "목표 0인 자리를 청산하지 않았다"
    assert new["c"] == 0.20


def test_fx_is_charged_only_on_the_net_dollar_flow():
    held = {"us_stock:SPY": 0.3}
    new = {"us_stock:QQQ": 0.3, "kr_stock:069500.KS": 0.1}
    assert S.fx_cost(held, new, 0.0025) == 0.0, "달러 자산끼리 갈아탄 몫에 환전 비용"
    assert S.fx_cost({}, {"us_stock:SPY": 0.4}, 0.0025) == pytest.approx(0.001)


def test_the_shadows_reach_the_screen():
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["engine_shadow"] = engine_shadow_public(state_dir)' in daily
    assert "run_engine_shadow(" in daily
    js = (ROOT / "docs" / "assets" / "engine-select.js").read_text("utf-8")
    assert "engine_shadow" in js
