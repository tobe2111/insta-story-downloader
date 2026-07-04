"""백테스트 핵심 로직 테스트 (합성 데이터, 결정론적)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider, get_provider
from quant.risk import RiskConfig, RiskManager
from quant.strategies import get_strategy, list_strategies


@pytest.fixture
def df():
    return SyntheticDataProvider(seed=7).get_ohlcv("TEST", "1d", limit=400)


def test_synthetic_data_shape(df):
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 400
    assert df.index.is_monotonic_increasing
    assert not df.isna().any().any()
    # high >= low, high >= close, low <= close 정합성
    assert (df["high"] >= df["low"]).all()
    assert (df["high"] >= df["close"]).all()
    assert (df["low"] <= df["close"]).all()


def test_synthetic_is_deterministic():
    a = SyntheticDataProvider(seed=1).get_ohlcv("X", limit=50)
    b = SyntheticDataProvider(seed=1).get_ohlcv("X", limit=50)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("name", list_strategies())
def test_all_strategies_run(df, name):
    strat = get_strategy(name)
    bt = Backtester(strat, initial_capital=10_000.0)
    result = bt.run(df)
    # 자본곡선은 항상 양수여야 한다 (파산 방지 로직 없이도 신호 기반)
    assert (result.equity > 0).all()
    assert len(result.equity) == len(df)
    # 목표비중은 [-1, 1] 범위
    assert result.positions.abs().max() <= 1.0 + 1e-9


def test_signal_range(df):
    for name in list_strategies():
        sig = get_strategy(name).generate_signals(df)
        assert sig.max() <= 1.0 and sig.min() >= -1.0
        assert sig.index.equals(df.index)


def test_no_lookahead_flat_signal(df):
    """항상 0 신호면 자본은 변하지 않아야 한다 (비용 제외)."""
    class Flat:
        name = "flat"
        allow_short = False

        def generate_signals(self, d):
            return pd.Series(0.0, index=d.index, name="target")

    bt = Backtester(Flat(), initial_capital=1000.0)
    result = bt.run(df)
    assert np.isclose(result.equity.iloc[-1], 1000.0)


def test_stop_loss_triggers():
    """급락 데이터에서 손절이 발동해 손실이 제한되는지 확인."""
    # 꾸준히 하락하는 가격
    n = 100
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    price = np.linspace(100, 50, n)
    df = pd.DataFrame(
        {"open": price, "high": price * 1.001, "low": price * 0.999,
         "close": price, "volume": 1.0},
        index=idx,
    )

    class AlwaysLong:
        name = "long"
        allow_short = False

        def generate_signals(self, d):
            return pd.Series(1.0, index=d.index, name="target")

    risk = RiskManager(RiskConfig(sizing="fixed", stop_loss=0.1))
    bt = Backtester(AlwaysLong(), risk, initial_capital=1000.0)
    result = bt.run(df)
    # 손절이 있으면 -50% 하락을 그대로 맞지 않고 청산되어야 한다
    assert result.metrics.max_drawdown > -0.5


def test_trailing_stop_protects_profit():
    """트레일링 스톱이 고점 이익을 지켜 낙폭을 줄이는지 검증."""
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    price = np.concatenate([np.linspace(100, 150, 30), np.linspace(150, 100, 30)])
    d = pd.DataFrame({"open": price, "high": price, "low": price,
                      "close": price, "volume": 1.0}, index=idx)

    class AlwaysLong:
        name = "long"
        allow_short = False

        def generate_signals(self, x):
            return pd.Series(1.0, index=x.index, name="target")

    def run(trailing):
        risk = RiskManager(RiskConfig(sizing="fixed", stop_loss=None,
                                      trailing_stop=trailing))
        return Backtester(AlwaysLong(), risk, fee=0.0, slippage=0.0).run(d)

    no_trail = run(None)
    trailed = run(0.1)
    # 고점(150) 부근에서 이익을 잠가 최종 자본이 더 높고 낙폭이 완화되어야 한다
    assert trailed.equity.iloc[-1] > no_trail.equity.iloc[-1]
    assert trailed.metrics.max_drawdown > no_trail.metrics.max_drawdown


def test_benchmark_buy_and_hold(df):
    """매수후보유 벤치마크와 초과수익이 올바르게 계산되는지 검증."""
    result = Backtester(get_strategy("ma_cross")).run(df)
    assert result.benchmark is not None
    expected = df["close"].iloc[-1] / df["close"].iloc[0] - 1.0
    assert abs(result.benchmark_return - expected) < 1e-9
    assert abs(result.excess_return
               - (result.metrics.total_return - result.benchmark_return)) < 1e-12
    assert "매수후보유" in result.summary()


def test_profit_factor_computation():
    """이익팩터 = 총이익/총손실 계산 검증."""
    from quant.backtest.metrics import compute_metrics

    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    returns = pd.Series([0.0, 0.1, -0.05, 0.2, -0.05], index=idx)
    positions = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0], index=idx)
    equity = (1 + returns).cumprod() * 100
    m = compute_metrics(equity, returns, positions, 365)
    # gross_win = 0.1+0.2 = 0.3, gross_loss = 0.05+0.05 = 0.1 → PF = 3.0
    assert abs(m.profit_factor - 3.0) < 1e-9
    assert "이익팩터" in m.pretty()


def test_profit_factor_nonnegative(df):
    m = Backtester(get_strategy("ma_cross")).run(df).metrics
    assert m.profit_factor >= 0.0


def test_sortino_finite_for_uniform_losses():
    """균일한 손실이어도 하방편차>0 → 소르티노가 0이 아니어야 한다(버그 수정).

    구버전은 음수 수익의 표준편차(평균차감)를 써서, 손실이 모두 같으면 분모가 0이
    되어 '하방위험 없음(소르티노=0)'으로 오판했다.
    """
    from quant.backtest.metrics import compute_metrics

    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    returns = pd.Series([-0.01, -0.01, -0.01, 0.01], index=idx)  # 손실 우세, 균일
    equity = (1 + returns).cumprod() * 100
    m = compute_metrics(equity, returns, pd.Series(1.0, index=idx), 365)
    assert m.sortino < 0.0        # 음의 유한값 (구버전은 0)


def test_compute_metrics_positions_alignment_flag():
    """결정시점 포지션(True)과 이미 정렬된 포지션(False)이 같은 승률을 준다.

    False 경로가 없으면 포트폴리오/워크포워드가 이중 시프트되어 승률·이익팩터가
    한 봉씩 어긋난다(버그 수정 검증).
    """
    from quant.backtest.metrics import compute_metrics

    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    returns = pd.Series([0.0, 0.1, -0.05, 0.0], index=idx)
    equity = (1 + returns).cumprod() * 100
    decision = pd.Series([1.0, 1.0, 0.0, 0.0], index=idx)   # 결정시점
    realized = pd.Series([0.0, 1.0, 1.0, 0.0], index=idx)   # = decision.shift(1)
    a = compute_metrics(equity, returns, decision, 365, positions_are_decision_time=True)
    b = compute_metrics(equity, returns, realized, 365, positions_are_decision_time=False)
    assert a.win_rate == b.win_rate == 0.5
    assert a.profit_factor == b.profit_factor


def test_win_rate_aligns_return_to_prior_position():
    """수익은 직전 봉 포지션으로 실현된다 — 승률·이익팩터가 한 봉 시프트로
    정렬되는지 검증(off-by-one 버그 수정).

    held[1]=1 이 bar2의 +20%를 벌었다. 시프트 없이 positions 그대로 쓰면 bar1
    (수익 0)만 활성으로 봐 승률 0·이익팩터 0으로 오판한다.
    """
    from quant.backtest.metrics import compute_metrics

    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    returns = pd.Series([0.0, 0.0, 0.2, 0.0], index=idx)
    positions = pd.Series([0.0, 1.0, 0.0, 0.0], index=idx)   # held: bar1에만 보유
    equity = (1 + returns).cumprod() * 100
    m = compute_metrics(equity, returns, positions, 365)
    assert m.win_rate == 1.0                      # 활성 봉(bar2)은 +20% → 승
    assert m.profit_factor == float("inf")        # 손실 봉 없음


def test_result_to_csv(df, tmp_path):
    """백테스트 결과 CSV 내보내기 검증."""
    result = Backtester(get_strategy("ma_cross")).run(df)
    out = result.to_csv(tmp_path / "result.csv")
    loaded = pd.read_csv(out)
    assert {"time", "equity", "returns", "position", "benchmark"} <= set(loaded.columns)
    assert len(loaded) == len(df)


def test_metrics_sane(df):
    bt = Backtester(get_strategy("ma_cross"), initial_capital=10_000.0)
    m = bt.run(df).metrics
    assert 0.0 <= m.exposure <= 1.0
    assert 0.0 <= m.win_rate <= 1.0
    assert m.max_drawdown <= 0.0
    assert m.num_trades >= 0


def test_get_provider_fallback():
    # 네트워크 없이도 crypto/stock 제공자가 데이터를 반환(폴백)
    for market in ("crypto", "us_stock", "kr_stock", "synthetic"):
        prov = get_provider(market)
        d = prov.get_ohlcv("BTC/USDT" if market == "crypto" else "AAPL", limit=60)
        assert len(d) > 0


def test_dd_throttle_default_off_unchanged(df):
    """dd_throttle 기본(off)은 기존 결과와 완전히 동일해야 한다(하위호환)."""
    base = Backtester(get_strategy("momentum")).run(df)
    same = Backtester(get_strategy("momentum"), dd_throttle=False).run(df)
    assert np.allclose(base.equity.to_numpy(), same.equity.to_numpy(), atol=1e-9)


def test_dd_throttle_runs_bounded_and_engages(df):
    """자산곡선 트로틀: 안전하게 동작하고 실제로 개입해 결과가 달라진다."""
    base = Backtester(get_strategy("momentum")).run(df)
    thr = Backtester(get_strategy("momentum"),
                     dd_throttle=True, dd_window=10, dd_cut=0.0).run(df)
    assert (thr.equity > 0).all()
    assert thr.positions.abs().max() <= 1.0 + 1e-9
    # dd_cut=0 이면 낙폭 국면에서 익스포저를 0으로 → 자산 경로가 달라져야 한다
    assert not np.allclose(thr.equity.to_numpy(), base.equity.to_numpy())
