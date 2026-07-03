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


def test_ml_gradient_boosting_and_vote():
    """추가 모델(gb·soft-voting 앙상블)도 경계 안에서 동작한다."""
    for kind in ("gb", "vote"):
        sig = MLStrategy(model=kind, train_window=200,
                         retrain_every=50).generate_signals(_DF)
        assert sig.abs().max() <= 1.0 + 1e-9
        assert sig.index.equals(_DF.index)


def test_ml_proba_sizing_is_graded():
    """확신도 사이징(proba)은 0/1 이분법이 아니라 중간값도 나온다."""
    sig = MLStrategy(model="rf", train_window=200, sizing="proba").generate_signals(_DF)
    traded = sig[sig != 0].abs()
    # 최소한 하나는 풀포지션(1.0)이 아닌 부분 포지션이어야 '그라데이션'이다
    assert (traded < 0.999).any()
    assert sig.max() <= 1.0 + 1e-9 and sig.min() >= 0.0 - 1e-9


def test_ml_binary_sizing_is_full_or_flat():
    """binary 모드는 풀포지션(1.0) 또는 관망(0)만 낸다."""
    sig = MLStrategy(train_window=200, sizing="binary").generate_signals(_DF)
    uniq = set(round(float(v), 6) for v in sig.unique())
    assert uniq <= {0.0, 1.0}


def test_ml_short_allows_negative():
    """allow_short=True면 하락 확신 시 음(-) 비중도 낸다."""
    sig = MLStrategy(model="logreg", train_window=200,
                     allow_short=True, threshold=0.52).generate_signals(_DF)
    assert sig.min() < 0.0            # 숏 포지션이 최소 한 번은 나와야 한다
    assert sig.abs().max() <= 1.0 + 1e-9


def test_ml_importances_recorded():
    """학습 후 피처 중요도(또는 계수)가 기록되어 해석 가능해야 한다."""
    from quant.strategies.ml import FEATURE_NAMES

    strat = MLStrategy(model="rf", train_window=200)
    strat.generate_signals(_DF)
    assert strat.last_importances_ is not None
    assert set(strat.last_importances_) == set(FEATURE_NAMES)
