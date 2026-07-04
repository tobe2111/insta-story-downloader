"""거래 원장(trade ledger) 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import (
    Backtester,
    extract_trades,
    trade_stats,
)
from quant.backtest.trades import trades_to_frame
from quant.data import SyntheticDataProvider
from quant.strategies import get_strategy


def test_extract_trades_manual():
    """수동 구성한 자본곡선/포지션에서 라운드트립 2건을 정확히 추출."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    equity = pd.Series([100, 101, 102, 103, 102, 102, 102, 104, 106, 106.0], index=idx)
    positions = pd.Series([0, 1, 1, 1, 0, 0, 1, 1, 1, 0.0], index=idx)

    trades = extract_trades(equity, positions)
    assert len(trades) == 2
    # 거래1: 진입 전 자본 100(index 0) → 청산 실현(index 4) 102 = +2%
    #   (엔진 규약상 마지막 보유봉 index 3의 손익·청산비용은 다음 봉 index 4에
    #    반영되므로 라운드트립 청산 기준은 eq[end+1]이다.)
    assert trades[0].side == "long"
    assert abs(trades[0].return_pct - 0.02) < 1e-9
    assert trades[0].bars_held == 3
    # 거래2: 진입 전 자본 102(index 5) → 청산 실현(index 9) 106 = +3.92%
    assert abs(trades[1].return_pct - (106 / 102 - 1)) < 1e-9
    assert trades[1].bars_held == 3


def test_flip_trade_not_double_counted():
    """롱→숏 직접 전환(플립) 시 전환 봉 손익이 두 거래에 이중 계상되지 않는다.

    positions [+1,+1,-1,-1,0,0], equity [100,101,140,138,150,150]:
      · 롱: eq[0]→eq[2] = +40% (전환 봉 손익 포함, 롱 몫)
      · 숏: 실제 노출 eq[2]→eq[4] = 140→150 ≈ +7.14%
    구버전은 숏 진입기준을 eq[1]=101로 잡아 롱의 +38.6% 봉을 훔쳐 +48.5%로 부풀렸다.
    """
    idx = pd.date_range("2020-01-01", periods=6, freq="D")
    equity = pd.Series([100, 101, 140, 138, 150, 150.0], index=idx)
    positions = pd.Series([1, 1, -1, -1, 0, 0.0], index=idx)
    trades = extract_trades(equity, positions)
    assert len(trades) == 2
    assert trades[0].side == "long" and abs(trades[0].return_pct - 0.40) < 1e-9
    assert trades[1].side == "short"
    assert abs(trades[1].return_pct - (150 / 140 - 1)) < 1e-9
    assert trades[1].return_pct < 0.10       # 이중계상되면 +48.5%가 됨


def test_trade_stats():
    idx = pd.date_range("2020-01-01", periods=6, freq="D")
    equity = pd.Series([100, 110, 110, 99, 99, 99.0], index=idx)
    positions = pd.Series([0, 1, 0, 1, 0, 0.0], index=idx)
    # 거래1: 100→110 = +10%, 거래2: 110→99 = -10%
    stats = trade_stats(extract_trades(equity, positions))
    assert stats["num_trades"] == 2
    assert abs(stats["win_rate"] - 0.5) < 1e-9
    assert stats["avg_win"] > 0 and stats["avg_loss"] < 0
    assert "expectancy" in stats and "profit_factor" in stats


def test_trade_stats_empty():
    stats = trade_stats([])
    assert stats["num_trades"] == 0
    assert stats["expectancy"] == 0.0


def test_result_trades_integration():
    df = SyntheticDataProvider(seed=4).get_ohlcv("T", "1d", limit=300)
    result = Backtester(get_strategy("ma_cross")).run(df)
    trades = result.trades()
    stats = result.trade_stats()
    assert stats["num_trades"] == len(trades)
    assert 0.0 <= stats["win_rate"] <= 1.0
    frame = trades_to_frame(trades)
    if trades:
        assert {"side", "return_pct", "bars_held"} <= set(frame.columns)
