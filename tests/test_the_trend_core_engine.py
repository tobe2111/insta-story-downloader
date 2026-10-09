"""추세 코어 엔진(감사 335) — 규칙이 미래를 안 보고, 비용을 빼고, 스위치로만 켜진다."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from quant.portfolio import trend_core as T


def _prices(n=600, drift=0.001, seed=1, start="2022-01-03"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n))), index=idx)


# ── 규칙 ──────────────────────────────────────────────────────────
def test_the_score_never_looks_at_tomorrow():
    p = _prices()
    full = T.trend_score(p)
    cut = T.trend_score(p.iloc[:400])
    pd.testing.assert_series_equal(full.iloc[:400], cut, check_names=False)


def test_a_downtrend_goes_to_cash_not_short():
    up, down = _prices(drift=0.002, seed=2), _prices(drift=-0.002, seed=3)
    closes = pd.DataFrame({"us_stock:SPY": up, "us_stock:EWJ": down})
    w = T.target_weights(closes).iloc[-1]
    assert w["us_stock:EWJ"] == 0.0 and w["us_stock:SPY"] > 0
    assert (T.target_weights(closes) >= 0).all().all()


def test_no_leverage_and_the_asset_cap_hold():
    closes = pd.DataFrame({f"us_stock:A{i}": _prices(drift=0.002, seed=i)
                           for i in range(6)})
    for name in T.VARIANTS:
        w = T.target_weights(closes, T.variant_config(name))
        assert (w.sum(axis=1) <= 1.0 + 1e-9).all(), name
        assert (w.max(axis=1) <= T.ASSET_CAP + 1e-9).all(), name


def test_crypto_gets_a_real_risk_share():
    """HRP가 BTC에 0.07%를 주던 자리 — 코인은 자산군 하나로서 위험 몫을 받는다."""
    closes = pd.DataFrame({
        "crypto:BTC/USDT": _prices(drift=0.003, seed=5) ** 1.0,
        "us_stock:TLT": _prices(drift=0.0005, seed=6),
        "us_stock:SPY": _prices(drift=0.001, seed=7)})
    w = T.target_weights(closes).iloc[-1]
    assert w["crypto:BTC/USDT"] > 0.02


# ── 체결·비용 ────────────────────────────────────────────────────
def test_targets_fill_next_day_and_costs_are_charged():
    closes = pd.DataFrame({"us_stock:SPY": _prices(drift=0.002)})
    free = T.simulate(closes, {"us_stock:SPY": 0.0}, T.TrendConfig(rebalance="D"))
    paid = T.simulate(closes, {"us_stock:SPY": 0.01}, T.TrendConfig(rebalance="D"))
    assert paid.cost.sum() > 0 and paid.equity.iloc[-1] < free.equity.iloc[-1]
    # 첫 거래는 목표가 처음 생긴 다음 날에 난다
    tgt = T.target_weights(closes, T.TrendConfig(rebalance="D"))
    first_t = tgt.index[(tgt.iloc[:, 0] > 0).values.argmax()]
    first_trade = paid.turnover.index[(paid.turnover > 0).values.argmax()]
    assert first_trade > first_t


def test_the_band_skips_tiny_changes_but_never_a_close():
    closes = pd.DataFrame({"us_stock:SPY": _prices(drift=0.002)})
    loose = T.simulate(closes, {}, T.TrendConfig(rebalance="D", band=0.0))
    tight = T.simulate(closes, {}, T.TrendConfig(rebalance="D", band=0.05))
    assert tight.turnover.sum() < loose.turnover.sum()


def test_business_day_alignment_never_backfills_before_listing():
    a = _prices(start="2022-01-03")
    b = _prices(start="2023-01-02", seed=9)
    c = T.align_business_days({"x:A": a, "x:B": b})
    assert c["x:B"][: "2022-12-30"].isna().all()


# ── 엔진 스위치 ─────────────────────────────────────────────────
def _run(tmp_path, engine):
    from quant.live.daily import run_daily_portfolio
    d = str(tmp_path)
    if engine:
        (tmp_path / "engine.json").write_text(json.dumps(engine), "utf-8")
    return run_daily_portfolio([("synthetic", "A"), ("synthetic", "B")],
                               lookback=400, state_dir=d,
                               require_real_data=False)


def test_without_the_switch_the_champions_decide(tmp_path):
    rec = _run(tmp_path, None)
    assert rec.get("engine") is None


def test_with_the_switch_the_trend_core_decides(tmp_path):
    rec = _run(tmp_path, {"engine": "trend_core", "variant": "risk12"})
    eng = rec.get("engine")
    assert eng and eng["name"] == "trend_core" and eng["variant"] == "risk12"
    assert 0.0 <= eng["gross"] <= 1.0


def test_a_broken_engine_falls_back_instead_of_going_to_cash(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "target_weights",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    rec = _run(tmp_path, {"engine": "trend_core", "variant": "risk12"})
    assert rec.get("engine") is None
