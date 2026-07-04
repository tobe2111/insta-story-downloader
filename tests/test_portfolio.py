"""포트폴리오 백테스트 테스트 (합성 데이터, 결정론적)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.portfolio import PortfolioBacktester, list_schemes
from quant.portfolio.allocation import equal_weight, hrp, inverse_vol
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
    for fn in (equal_weight, inverse_vol, hrp):
        w = fn(returns, signals, 30)
        gross = w.abs().sum(axis=1)
        # 활성 종목이 있을 때 배분 합은 1을 넘지 않아야 한다
        assert gross.max() <= 1.0 + 1e-9


def test_single_symbol_portfolio(data):
    """종목 1개짜리 포트폴리오도 정상 동작."""
    bt = PortfolioBacktester(strategy=get_strategy("ma_cross"), allocation="equal")
    result = bt.run({"A": data["A"]})
    assert (result.equity > 0).all()


def test_hrp_no_lookahead(data):
    """HRP 가중은 과거 window만 사용 → 미래를 잘라도 과거 가중이 안 변한다."""
    import numpy as np
    import pandas as pd

    prices = pd.DataFrame({s: d["close"] for s, d in data.items()}).dropna()
    returns = prices.pct_change().fillna(0.0)
    signals = pd.DataFrame(1.0, index=prices.index, columns=prices.columns)  # 항상 활성
    cut = 300
    full = hrp(returns, signals, window=30, rebalance=21)
    trunc = hrp(returns.iloc[:cut], signals.iloc[:cut], window=30, rebalance=21)
    a = full.iloc[:cut - 1].to_numpy()
    b = trunc.iloc[:cut - 1].to_numpy()
    assert np.allclose(a, b, atol=1e-9), "HRP가 미래 데이터를 참조함"


def test_hrp_weights_bounded_and_active(data):
    """HRP는 롱온리 합≤1, 워밍업 후엔 실제로 배분이 일어난다."""
    import pandas as pd

    prices = pd.DataFrame({s: d["close"] for s, d in data.items()}).dropna()
    returns = prices.pct_change().fillna(0.0)
    signals = pd.DataFrame(1.0, index=prices.index, columns=prices.columns)
    w = hrp(returns, signals, window=40, rebalance=21)
    gross = w.abs().sum(axis=1)
    assert gross.max() <= 1.0 + 1e-9
    assert gross.iloc[60:].max() > 0.5          # 워밍업 후 자본이 실제 배분됨
    assert (w >= -1e-9).all().all()             # 롱온리(신호가 모두 +1)
