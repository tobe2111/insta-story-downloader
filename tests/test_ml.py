"""ML 전략 테스트 (scikit-learn 필요 — CI에서 설치)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider
from quant.strategies import MLStrategy, get_strategy, list_strategies

_DF = SyntheticDataProvider(seed=6).get_ohlcv("ML", "1d", limit=500)


def test_ml_registered_and_bounded():
    assert "ml" in list_strategies()
    sig = get_strategy("ml").generate_signals(_DF)
    assert sig.index.equals(_DF.index)
    assert sig.max() <= 1.0 + 1e-9 and sig.min() >= -1.0 - 1e-9


def test_ml_no_signal_before_training():
    """학습 창(train_window) 이전에는 신호가 0 — 룩어헤드 없음의 방증."""
    sig = MLStrategy(train_window=250).generate_signals(_DF)
    assert (sig.iloc[:250] == 0).all()


def test_ml_backtest_runs():
    result = Backtester(MLStrategy(model="logreg", train_window=200)).run(_DF)
    assert (result.equity > 0).all()


def test_ml_random_forest():
    sig = MLStrategy(model="rf", train_window=200,
                     retrain_every=50).generate_signals(_DF)
    assert sig.abs().max() <= 1.0 + 1e-9


def test_ml_short_data_no_trade():
    """데이터가 train_window보다 짧으면 학습을 못 해 전부 관망(0)."""
    short = SyntheticDataProvider(seed=1).get_ohlcv("S", "1d", limit=100)
    sig = MLStrategy(train_window=250).generate_signals(short)
    assert (sig == 0).all()
