"""실거래도 **페이퍼와 같은 엔진**을 따른다 (감사 340).

2026-10-10 페이퍼 계좌는 추세 코어로 바뀌었는데, 실거래 집행기는 여전히
종목별 챔피언 신호를 불렀다. 실거래를 켜는 날 화면·장부와 **다른 전략**이
실제 돈으로 돌았을 것이다.
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

from quant.live import daily_live as DL  # noqa: E402


class _Broker:
    def __init__(self, cash=1_000_000.0):
        self.cash = cash
        self.orders: list = []

    def get_cash(self):
        return self.cash

    def get_position(self, symbol):
        return type("P", (), {"quantity": 0.0, "avg_price": 0.0})()

    def market_order(self, symbol, side, quantity, price):
        from quant.broker.base import Order
        self.orders.append({"symbol": symbol, "notional": float(quantity) * float(price)})
        return Order(symbol, side, float(quantity), float(price),
                     status="filled", filled_quantity=float(quantity))


def _frame(seed, drift):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=400)
    close = pd.Series(1000 * np.exp(np.cumsum(rng.normal(drift, 0.01, 400))), index=idx)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1e6}, index=idx)


def _run(monkeypatch, tmp_path, engine: bool):
    if engine:
        (tmp_path / "engine.json").write_text(
            json.dumps({"engine": "trend_core", "variant": "risk12"}))
    frames = {"005930.KS": _frame(1, 0.002), "SPY": _frame(2, 0.002)}
    monkeypatch.setattr("quant.data.get_provider", lambda m: type("P", (), {
        "get_ohlcv": lambda self, sym, *a, **k: frames[sym].copy()})())
    monkeypatch.setattr("quant.universe.active_targets",
                        lambda *a, **k: [("kr_stock", "005930.KS"),
                                         ("us_stock", "SPY")])
    called = []

    def champ(*a, **k):
        called.append(a)

        class S:
            name = "fixed"
            allow_short = False

            def generate_signals(self, df):
                return pd.Series(1.0, index=df.index)
        return S()

    monkeypatch.setattr(DL, "champion_strategy", champ)
    monkeypatch.setattr("quant.data.krx.attach_krx_flows", lambda d, s: d)
    monkeypatch.setattr("quant.data.crossasset.attach_cross_asset", lambda d, m, s: d)
    broker = _Broker()
    out = DL.run_daily_live([("kr_stock", "005930.KS")], paper=True,
                            state_dir=str(tmp_path), broker=broker)
    return out, broker, called


def test_with_the_engine_on_live_does_not_ask_the_old_champion(monkeypatch, tmp_path):
    out, broker, called = _run(monkeypatch, tmp_path, engine=True)
    assert not called, "엔진이 켜졌는데 실거래가 옛 챔피언 신호를 불렀다"
    eng = out["engine"]
    assert eng and eng["name"] == "trend_core"
    w = out["decisions"]["005930.KS"]
    assert w > 0
    assert broker.orders, "엔진 목표가 있는데 주문이 안 나갔다"
    assert sum(o["notional"] for o in broker.orders) == pytest.approx(
        w * 1_000_000, rel=0.02), "엔진 비중은 계좌 전체 자산 기준이다"


def test_the_share_live_cannot_buy_is_written_down(monkeypatch, tmp_path):
    """미국·코인 몫은 이 계좌가 못 산다 — 국내 몫을 키워 채우지 않고 적는다."""
    out, _, _ = _run(monkeypatch, tmp_path, engine=True)
    eng = out["engine"]
    assert eng["uncovered"] > 0, "못 사는 몫이 장부에 없다"
    assert out["decisions"]["005930.KS"] <= eng["covered"] + 1e-9, (
        "국내 몫을 키워 미국 몫을 채웠다 — 검증하지 않은 다른 전략이다")


def test_without_the_engine_the_old_path_still_runs(monkeypatch, tmp_path):
    out, _, called = _run(monkeypatch, tmp_path, engine=False)
    assert called and out["engine"] is None


def test_the_advisories_name_the_three_decisions(tmp_path):
    (tmp_path / "engine.json").write_text(json.dumps({"engine": "trend_core"}))
    lines = DL.live_advisories(str(tmp_path))
    text = " ".join(lines)
    assert "국내 종목만" in text and "fx_spread" in text and "ISA" in text
