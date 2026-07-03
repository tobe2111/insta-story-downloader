"""포트폴리오 백테스트 테스트 (합성 데이터, 결정론적)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.portfolio import PortfolioBacktester, list_schemes
from quant.portfolio.allocation import equal_weight, inverse_vol
from quant.strategies import get_strategy


@pytest.fixture
def data():
    prov = SyntheticDataProvider(seed=3)
    return {s: prov.get_ohlcv(s, "1d", limit=400) for s in ["A", "B", "C", "D"]}


@pytest.mark.parametrize("scheme", list_schemes())
def test_portfolio_runs(data, scheme):
    bt = PortfolioBacktester(
        strategy=get_strategy("momentum"), allocation=scheme, initial_capital=10_000.0
    )
    result = bt.run(data)
    assert (result.equity > 0).all()
    assert len(result.equity) > 0


def test_gross_exposure_capped(data):
    """총 노출이 max_gross를 (룩어헤드 보정 후) 초과하지 않아야 한다."""
    bt = PortfolioBacktester(
        strategy=get_strategy("momentum"), allocation="equal", max_gross=1.0
    )
    result = bt.run(data)
    # position = held(=shift된 weights)의 절대합. 1.0을 크게 넘지 않아야 함
    assert result.positions.max() <= 1.0 + 1e-9


def test_allocation_weights_normalized(data):
    close = {s: d["close"] for s, d in data.items()}
    import pandas as pd

    prices = pd.DataFrame(close).dropna()
    returns = prices.pct_change().fillna(0.0)
    signals = pd.DataFrame(
        {s: get_strategy("momentum").generate_signals(data[s]).reindex(prices.index).ffill().fillna(0.0)
         for s in data}
    )
    for fn in (equal_weight, inverse_vol):
        w = fn(returns, signals, 30)
        gross = w.abs().sum(axis=1)
        # 활성 종목이 있을 때 배분 합은 1을 넘지 않아야 한다
        assert gross.max() <= 1.0 + 1e-9


def test_single_symbol_portfolio(data):
    """종목 1개짜리 포트폴리오도 정상 동작."""
    bt = PortfolioBacktester(strategy=get_strategy("ma_cross"), allocation="equal")
    result = bt.run({"A": data["A"]})
    assert (result.equity > 0).all()
