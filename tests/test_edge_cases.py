"""극단 입력 스트레스 테스트 — 퇴화(degenerate) 데이터로 전 계층을 굴려 런타임
크래시(ZeroDivision·AttributeError·NaN 전파·인덱스 오류)를 잡는다.

'정상 데이터'만 테스트하면 놓치는 버그들: 변동성 0(종가 고정), 단조 상승/하락,
아주 짧은 시계열, 급등/급락 스파이크, 초반 결측. 각 케이스는 '깔끔히 동작'하거나
'의도된 ValueError'여야 하며, 예기치 못한 예외가 나면 실패한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.backtest.metrics import compute_metrics
from quant.backtest.trades import extract_trades, trade_stats
from quant.portfolio import PortfolioBacktester
from quant.portfolio.allocation import get_scheme
from quant.robustness import bootstrap_metrics
from quant.strategies import get_strategy, list_strategies


def _frame(prices: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    p = np.asarray(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p * 1.001, "low": p * 0.999,
                         "close": p, "volume": 1.0}, index=idx)


# 퇴화 프레임들 (충분히 길게 300봉 — ML 등 롱 윈도우 전략도 워밍업 통과)
_N = 300
FLAT = _frame(np.full(_N, 100.0))                              # 변동성 0
UP = _frame(np.linspace(100, 300, _N))                        # 단조 상승
DOWN = _frame(np.linspace(300, 100, _N))                      # 단조 하락
SPIKE = _frame(np.concatenate([np.full(_N - 1, 100.0), [1e6]]))  # 마지막 봉 급등

_DEGENERATE = {"flat": FLAT, "up": UP, "down": DOWN, "spike": SPIKE}


@pytest.mark.parametrize("name", list_strategies())
@pytest.mark.parametrize("case", list(_DEGENERATE))
def test_strategy_signals_survive_degenerate(name, case):
    """모든 전략이 퇴화 데이터에서 크래시 없이 [-1,1] 신호를 낸다."""
    df = _DEGENERATE[case]
    sig = get_strategy(name).generate_signals(df)
    assert sig.index.equals(df.index)
    assert not sig.isna().any(), f"{name}/{case}: 신호에 NaN"
    assert sig.max() <= 1.0 + 1e-9 and sig.min() >= -1.0 - 1e-9


@pytest.mark.parametrize("name", list_strategies())
@pytest.mark.parametrize("case", list(_DEGENERATE))
def test_backtest_survives_degenerate(name, case):
    """백테스트 엔진(+기본 vol_target 리스크)이 퇴화 데이터에서 크래시하지 않고
    파산 없이(자본>0) 완주한다. 변동성 0 케이스는 최근 수정(레버리지 폭주 방지)도 검증."""
    df = _DEGENERATE[case]
    result = Backtester(get_strategy(name)).run(df)
    assert (result.equity > 0).all(), f"{name}/{case}: 자본이 0 이하로"
    assert np.isfinite(result.equity.to_numpy()).all(), f"{name}/{case}: 자본에 inf/nan"
    assert result.positions.abs().max() <= 1.0 + 1e-9


def test_backtest_short_series_ok():
    """아주 짧은(5봉) 시계열도 크래시 없이 처리된다."""
    df = _frame(np.array([100, 101, 99, 102, 98.0]))
    for name in list_strategies():
        if name == "ml":
            continue  # ML은 최소 학습 표본이 필요 — 짧은 구간은 관망(별도 테스트)
        result = Backtester(get_strategy(name)).run(df)
        assert (result.equity > 0).all()


def test_backtest_empty_raises_clean():
    """빈 데이터는 '깔끔한' ValueError여야 한다(예기치 못한 크래시 금지)."""
    with pytest.raises(ValueError):
        Backtester(get_strategy("ma_cross")).run(_frame(np.array([])))


def test_metrics_degenerate_series():
    """성과지표가 퇴화 수익률에서 크래시하지 않고 유한값을 낸다."""
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    for rets in ([0.0] * 5, [-0.01] * 5, [0.02] * 5, [0.0, 0.0, 0.0, 0.0, 0.0]):
        r = pd.Series(rets, index=idx)
        eq = (1 + r).cumprod() * 100
        pos = pd.Series(1.0, index=idx)
        m = compute_metrics(eq, r, pos, 365)
        for v in (m.sharpe, m.sortino, m.cagr, m.max_drawdown, m.volatility):
            assert np.isfinite(v), f"{rets}: 지표에 inf/nan ({v})"


def test_trades_degenerate_positions():
    """거래 추출이 항상-보유/항상-관망/즉시-플립에서 크래시하지 않는다."""
    idx = pd.date_range("2020-01-01", periods=6, freq="D")
    eq = pd.Series([100, 101, 102, 103, 104, 105.0], index=idx)
    for pos in ([0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1],
                [1, -1, 1, -1, 1, -1], [0, 1, -1, 0, 1, 0.0]):
        stats = trade_stats(extract_trades(eq, pd.Series(pos, index=idx, dtype=float)))
        assert stats["num_trades"] >= 0
        assert np.isfinite(stats["expectancy"])


@pytest.mark.parametrize("scheme", ["equal", "inverse_vol", "hrp"])
def test_allocation_degenerate(scheme):
    """자산배분이 단일종목/동일종목/변동성0에서 크래시하지 않고 유한 비중을 낸다."""
    idx = pd.date_range("2020-01-01", periods=80, freq="D")
    fn = get_scheme(scheme)
    # 동일한 두 종목(상관 1, 공분산 특이) + 변동성 0 종목
    same = pd.Series(np.linspace(100, 120, 80), index=idx)
    flat = pd.Series(100.0, index=idx)
    returns = pd.DataFrame({"A": same, "B": same, "C": flat}).pct_change().fillna(0.0)
    signals = pd.DataFrame(1.0, index=idx, columns=["A", "B", "C"])
    w = fn(returns, signals, 30)
    assert np.isfinite(w.to_numpy()).all(), f"{scheme}: 비중에 inf/nan"


def test_single_symbol_portfolio():
    """단일 종목 포트폴리오도 크래시 없이 동작한다."""
    from quant.data import SyntheticDataProvider
    prov = SyntheticDataProvider(seed=3)
    data = {"X": prov.get_ohlcv("X", "1d", limit=120)}
    pb = PortfolioBacktester(get_strategy("momentum"), allocation="inverse_vol")
    result = pb.run(data)
    assert (result.equity > 0).all()


def test_bootstrap_tiny_returns():
    """몬테카를로가 아주 짧은 수익률에서도 유한 분포를 낸다."""
    r = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.0, -0.03, 0.01])
    dist = bootstrap_metrics(r, n_sims=100, seed=1)
    for key in ("sharpe", "cagr", "total_return", "max_drawdown"):
        assert np.isfinite(dist[key]).all(), f"{key}: inf/nan 포함"


def test_ml_flat_data_no_crash():
    """ML 전략이 변동성 0(단일 라벨 클래스) 데이터에서 학습 불가여도 크래시 없이 관망."""
    sig = get_strategy("ml").generate_signals(FLAT)
    assert not sig.isna().any()
    assert (sig == 0).all()      # 학습 불가 → 전 구간 관망
