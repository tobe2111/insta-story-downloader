"""'그냥 보유'도 후보다 · 선물 엔진도 기계가 고른다 (감사 344).

사장님(2026-10-11): "모두 진행해. 수수료도 생각을 했어야지."
실측: 코인 단타가 비용 전 +5.9%를 벌고 비용 6.1%로 −0.2% — 같은 기간 코인
보유 +33.7%. 사고팔기를 거의 안 하는 후보가 링에 없으면 기계는 그것을 못 고른다.
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

from quant.portfolio import engine_select as E  # noqa: E402
from quant.portfolio import trend_core as T  # noqa: E402


def _closes(keys, n=420, drift=0.0006, seed=11, late=None):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-06-03", periods=n)
    out = {}
    for i, k in enumerate(keys):
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n))), index=idx)
        if late and k in late:
            s.iloc[:late[k]] = np.nan
        out[k] = s
    return T.align_business_days(out)


# ── ① 그냥 보유 ───────────────────────────────────────────────────

def test_hold_is_equal_money_in_whatever_is_listed():
    c = _closes(["a", "b", "c", "d"], late={"d": 200})
    w = E.hold_weights(c)
    assert w.iloc[100].tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3, 0.0])
    assert w.iloc[-1].tolist() == pytest.approx([0.25] * 4)
    assert (w.sum(axis=1) <= 1.0 + 1e-12).all(), "보유 후보가 빚을 냈다"


def test_sixty_forty_renormalizes_until_both_are_listed():
    c = _closes(["us_stock:SPY", "us_stock:IEF", "x"], late={"us_stock:IEF": 150})
    w = E.fixed_weights(c, {"us_stock:SPY": 0.6, "us_stock:IEF": 0.4})
    assert w.iloc[100]["us_stock:SPY"] == pytest.approx(1.0)
    assert w.iloc[-1]["us_stock:SPY"] == pytest.approx(0.6)
    assert w.iloc[-1]["us_stock:IEF"] == pytest.approx(0.4)
    assert w["x"].abs().sum() == 0


def test_the_hold_candidates_are_in_the_ring_with_labels():
    for n in ("hold40", "holdw", "6040"):
        assert n in E.ALL_NAMES and n in E.LABELS
    assert E.switch_threshold(len(E.ALL_NAMES)) > E.switch_threshold(11), (
        "후보가 늘었는데 갈아타기 문턱이 그대로다")


def test_hold40_stays_in_the_40_and_holdw_takes_the_broad_list():
    core = ["us_stock:SPY", "us_stock:IEF", "kr_stock:069500.KS"]
    c = _closes(core + ["us_stock:XLK", "us_stock:SMH"])
    h40, _ = E.candidate_targets(c, "hold40", core_keys=set(core))
    hw, _ = E.candidate_targets(c, "holdw", core_keys=set(core))
    assert h40.iloc[-1][["us_stock:XLK", "us_stock:SMH"]].abs().sum() == 0
    assert hw.iloc[-1].tolist() == pytest.approx([0.2] * 5)


def test_holding_costs_far_less_than_trading():
    c = _closes(["a", "b", "c", "d", "e"], n=600)
    cost = {k: 0.003 for k in c.columns}
    hold = T.simulate(c, cost, E.candidate_config("hold40"), targets=E.hold_weights(c))
    xs, cfg = E.candidate_targets(c, "xs12")
    trade = T.simulate(c, cost, cfg, targets=xs)
    assert hold.cost.sum() < trade.cost.sum()


# ── ② 선물 엔진 선택 ─────────────────────────────────────────────

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]


def test_futures_candidates_hold_and_cash():
    c = _closes(COINS)
    hold, cfg = E.fut_targets(c, "fut_hold")
    assert hold.iloc[-1].sum() == pytest.approx(1.0), "코인 보유는 1배(빚 없음)"
    assert cfg.carry_annual == T.FUTURES_CARRY, "선물로 들고 있으면 펀딩을 낸다"
    cash, _ = E.fut_targets(c, "fut_cash")
    assert cash.abs().sum().sum() == 0
    trend, tcfg = E.fut_targets(c, "fut_long20")
    assert tcfg.carry_annual == T.FUTURES_CARRY


def test_the_futures_choice_is_used_only_when_valid():
    st = {"futures": {"active": "fut_hold", "asof": "2026-10-09",
                      "gate": {"pass": True}}}
    assert E.fut_active_choice(st, "2026-10-12") == "fut_hold"
    assert E.fut_active_choice(st, "2026-11-30") is None, "주간 잡이 멈춰도 옛 선택을 쓴다"
    bad = {"futures": {**st["futures"], "gate": {"pass": False}}}
    assert E.fut_active_choice(bad, "2026-10-12") is None
    assert E.fut_active_choice({"futures": {**st["futures"], "active": "x"}},
                               "2026-10-12") is None


def _fake_provider(monkeypatch, closes):
    class P:
        def get_ohlcv(self, sym, *a, **k):
            return pd.DataFrame({"close": closes[sym]})
    monkeypatch.setattr("quant.data.get_provider", lambda m: P())


def test_the_futures_track_follows_the_machine(monkeypatch, tmp_path):
    from quant.live import futures_challenger as F
    c = _closes(COINS)
    _fake_provider(monkeypatch, {k: c[k] for k in COINS})
    (tmp_path / "engine.json").write_text(json.dumps({"futures_variant": "fut_long20"}))
    prices = {k: float(c[k].iloc[-1]) for k in COINS}
    last = str(c.index[-1].date())
    (tmp_path / E.SELECT_FILE).write_text(json.dumps(
        {"futures": {"active": "fut_cash", "asof": last, "gate": {"pass": True}}}))
    out = F._futures_core(str(tmp_path), COINS, prices)
    assert out["variant"] == "fut_cash" and out["selected_by"] == "engine_select"
    assert out["gross"] == 0, "현금을 골랐는데 포지션을 잡았다"
    (tmp_path / E.SELECT_FILE).write_text(json.dumps(
        {"futures": {"active": "fut_cash", "asof": "2020-01-03", "gate": {"pass": True}}}))
    out = F._futures_core(str(tmp_path), COINS, prices)
    assert out["variant"] == "fut_long20" and out["selected_by"] == "engine.json"


def test_the_futures_page_says_who_picked_and_what():
    html = (ROOT / "docs" / "futures.html").read_text("utf-8")
    assert "d.engine.selected_by" in html
    assert "fut_cash" in html and "fut_hold" in html, (
        "보유·현금이 뽑혀도 화면이 '추세추종'이라고 말한다")
    js = (ROOT / "docs" / "assets" / "engine-select.js").read_text("utf-8")
    assert "es.futures" in js
    i18n = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")
    for v in list(E.FUT_LABELS.values()) + [E.LABELS[n] for n in ("hold40", "holdw", "6040")]:
        assert f'"{v}":' in i18n, v
