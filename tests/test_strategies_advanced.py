"""확장 전략(RSI/브레이크아웃/MACD) + 앙상블 + 레짐 필터 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider
import numpy as np

from quant.strategies import (
    AdaptiveEnsemble,
    Breakout,
    MeanReversion,
    MovingAverageCross,
    RSIReversion,
    RegimeFilter,
    StrategyEnsemble,
    adaptive_ensemble,
    default_ensemble,
    get_strategy,
    list_strategies,
)


@pytest.fixture
def df():
    return SyntheticDataProvider(seed=5).get_ohlcv("ADV", "1d", limit=500)


@pytest.mark.parametrize("name", ["rsi", "breakout", "macd", "keltner", "stochastic"])
def test_new_strategies_registered(df, name):
    assert name in list_strategies()
    sig = get_strategy(name).generate_signals(df)
    assert sig.index.equals(df.index)
    assert sig.max() <= 1.0 and sig.min() >= -1.0


def test_ensemble_runs_and_bounded(df):
    ens = StrategyEnsemble([MovingAverageCross(), Breakout(), RSIReversion()])
    sig = ens.generate_signals(df)
    assert sig.abs().max() <= 1.0 + 1e-9
    result = Backtester(ens).run(df)
    assert (result.equity > 0).all()


def test_ensemble_weight_validation():
    with pytest.raises(ValueError):
        StrategyEnsemble([MovingAverageCross()], weights=[1.0, 2.0])
    with pytest.raises(ValueError):
        StrategyEnsemble([])


def test_default_ensemble(df):
    result = Backtester(default_ensemble()).run(df)
    assert (result.equity > 0).all()


def test_adaptive_ensemble_runs_and_bounded(df):
    ens = AdaptiveEnsemble(
        [MovingAverageCross(), Breakout(), RSIReversion()], lookback=40)
    sig = ens.generate_signals(df)
    assert sig.index.equals(df.index)
    assert sig.abs().max() <= 1.0 + 1e-9
    assert (Backtester(ens).run(df).equity > 0).all()


def test_adaptive_ensemble_single_equals_base(df):
    """전략이 하나뿐이면 가중치가 항상 1 → 원본 신호와 동일해야 한다."""
    base = MovingAverageCross(fast=10, slow=30)
    ens = AdaptiveEnsemble([base], lookback=30)
    assert (ens.generate_signals(df).fillna(0.0)
            == base.generate_signals(df).fillna(0.0)).all()


def test_adaptive_ensemble_helper(df):
    assert (Backtester(adaptive_ensemble(lookback=30)).run(df).equity > 0).all()


def test_adaptive_ensemble_empty_raises():
    with pytest.raises(ValueError):
        AdaptiveEnsemble([])


def test_ensemble_inverse_vol_bounded(df):
    """리스크 패리티(역변동성) 가중도 경계 안에서 동작하고 인덱스를 보존한다."""
    ens = StrategyEnsemble(
        [MovingAverageCross(), Breakout(), RSIReversion()],
        weighting="inverse_vol", vol_lookback=40)
    sig = ens.generate_signals(df)
    assert sig.index.equals(df.index)
    assert sig.abs().max() <= 1.0 + 1e-9
    assert (Backtester(ens).run(df).equity > 0).all()


def test_ensemble_weights_sum_to_one_inverse_vol(df):
    """역변동성 가중이라도 두 전략 결합 신호는 개별 신호 범위를 벗어나지 않는다."""
    a, b = MovingAverageCross(), MeanReversion()
    ens = StrategyEnsemble([a, b], weighting="inverse_vol")
    sig = ens.generate_signals(df)
    lo = pd.concat([a.generate_signals(df), b.generate_signals(df)], axis=1).min(axis=1)
    hi = pd.concat([a.generate_signals(df), b.generate_signals(df)], axis=1).max(axis=1)
    # 가중평균은 항상 [min, max] 사이 (합=1인 볼록결합)
    assert (sig <= hi + 1e-9).all() and (sig >= lo - 1e-9).all()


def test_adaptive_ensemble_sharpe_softmax_bounded(df):
    """Sharpe 점수 + 소프트맥스 + 리스크패리티 조합이 경계 안에서 동작한다."""
    ens = AdaptiveEnsemble(
        [MovingAverageCross(), Breakout(), RSIReversion(), MeanReversion()],
        lookback=40, score="sharpe", method="softmax", risk_parity=True)
    sig = ens.generate_signals(df)
    assert sig.abs().max() <= 1.0 + 1e-9
    assert (Backtester(ens).run(df).equity > 0).all()


def test_adaptive_ensemble_proportional_return_mode(df):
    """구식 비례배분(return·proportional·리스크패리티 off)도 여전히 동작한다."""
    ens = AdaptiveEnsemble(
        [MovingAverageCross(), RSIReversion()], lookback=40,
        score="return", method="proportional", risk_parity=False)
    sig = ens.generate_signals(df)
    assert sig.abs().max() <= 1.0 + 1e-9


def test_mean_reversion_enters_low_exits_at_mean():
    """하단밴드 이탈 시 진입하고, 중심선 복귀 시 청산되는지 검증(청산 로직 회귀 테스트)."""
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    price = np.full(n, 100.0)
    price[30:35] = 80.0    # 급락 → 하단밴드 이탈 → 롱 진입
    price[35:] = 105.0     # 평균 위로 복귀 → 청산
    d = pd.DataFrame({"open": price, "high": price, "low": price,
                      "close": price, "volume": 1.0}, index=idx)

    sig = MeanReversion(window=20).generate_signals(d)
    assert (sig.iloc[30:35] > 0).any()   # 급락 구간에서 롱 진입
    assert sig.iloc[-1] == 0.0           # 평균 복귀 후 청산되어 관망


def test_adx_filter_reduces_exposure(df):
    """ADX 필터를 씌우면 (추세 강할 때만 매매) 노출이 원본 이하가 되어야 한다."""
    from quant.strategies import ADXFilter, MovingAverageCross

    base = MovingAverageCross(fast=10, slow=30)
    filtered = ADXFilter(base, period=14, min_adx=25)
    base_exp = (base.generate_signals(df) != 0).mean()
    filt_exp = (filtered.generate_signals(df) != 0).mean()
    assert filt_exp <= base_exp + 1e-9
    # 백테스트도 정상 동작
    assert (Backtester(filtered).run(df).equity > 0).all()


def test_adx_in_range(df):
    from quant.strategies.adx import adx
    a = adx(df, 14)
    assert a.index.equals(df.index)
    assert (a >= 0).all() and a.max() <= 100.0 + 1e-6


def test_regime_filter_reduces_exposure(df):
    """레짐 필터를 씌우면 노출 시간이 원본보다 늘지 않아야 한다(게이팅)."""
    base = MovingAverageCross(fast=10, slow=30)
    filtered = RegimeFilter(base, trend_window=100, use_trend=True)

    base_exposure = (base.generate_signals(df) != 0).mean()
    filt_exposure = (filtered.generate_signals(df) != 0).mean()
    assert filt_exposure <= base_exposure + 1e-9


def test_regime_filter_blocks_bear_market():
    """장기MA 아래(약세)에서는 롱 신호가 0으로 게이팅된다."""
    n = 250
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    # 지속 하락 → 항상 장기MA 아래
    price = pd.Series(range(n, 0, -1), index=idx, dtype=float) + 100
    d = pd.DataFrame({"open": price, "high": price * 1.01, "low": price * 0.99,
                      "close": price, "volume": 1.0}, index=idx)

    class AlwaysLong:
        name = "long"
        allow_short = False

        def generate_signals(self, x):
            return pd.Series(1.0, index=x.index, name="target")

    filtered = RegimeFilter(AlwaysLong(), trend_window=50, use_trend=True)
    sig = filtered.generate_signals(d)
    # 하락장이므로 대부분의 구간에서 롱이 차단되어야 한다
    assert (sig == 0).mean() > 0.5
