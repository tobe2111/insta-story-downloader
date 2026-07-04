"""펀딩비 실데이터(fetch/align) + CostModel funding_series 훅 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester, CostModel
from quant.data import SyntheticDataProvider
from quant.data.funding import align_funding_to_bars, fetch_funding_history


# ------------------------- fetch: graceful 폴백 -------------------------

def test_fetch_unknown_exchange_falls_back_to_empty():
    """ccxt 미설치·미지원 거래소·네트워크 오류 → 예외 없이 빈 Series."""
    s = fetch_funding_history("BTC/USDT:USDT", exchange="없는거래소_xyz")
    assert isinstance(s, pd.Series)
    assert s.empty


# ------------------------- align_funding_to_bars -------------------------

def _bars(n: int = 5) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=n, freq="1D")


def test_align_assigns_event_to_next_bar():
    bars = _bars(5)
    # 1/2 06:00 정산 이벤트 → 1/3 봉(정산 이후 첫 봉)에 반영돼야 룩어헤드가 없다
    f = pd.Series([0.0001], index=pd.DatetimeIndex([pd.Timestamp("2026-01-02 06:00")]))
    out = align_funding_to_bars(f, bars)
    assert out.loc["2026-01-03"] == pytest.approx(0.0001)
    assert out.drop(pd.Timestamp("2026-01-03")).eq(0.0).all()


def test_align_event_exactly_on_bar_stays_on_that_bar():
    bars = _bars(5)
    f = pd.Series([0.0002], index=pd.DatetimeIndex([pd.Timestamp("2026-01-02")]))
    out = align_funding_to_bars(f, bars)
    assert out.loc["2026-01-02"] == pytest.approx(0.0002)


def test_align_sums_multiple_events_per_bar_and_drops_future():
    bars = _bars(3)   # 1/1 ~ 1/3
    f = pd.Series(
        [0.0001, 0.0002, 0.5],
        index=pd.DatetimeIndex([
            pd.Timestamp("2026-01-01 08:00"),   # → 1/2 봉
            pd.Timestamp("2026-01-01 16:00"),   # → 1/2 봉 (합산)
            pd.Timestamp("2026-01-09"),          # 마지막 봉 이후 → 버림
        ]))
    out = align_funding_to_bars(f, bars)
    assert out.loc["2026-01-02"] == pytest.approx(0.0003)
    assert out.sum() == pytest.approx(0.0003)    # 미래 이벤트는 포함 안 됨


def test_align_empty_inputs():
    out = align_funding_to_bars(pd.Series(dtype=float), _bars(3))
    assert out.eq(0.0).all() and len(out) == 3


# ------------------------- CostModel funding_series -------------------------

def test_holding_cost_uses_series_with_sign():
    idx = _bars(3)
    fs = pd.Series([0.0, 0.001, -0.002], index=idx)
    cm = CostModel(funding=0.05, funding_series=fs)   # 시리즈가 고정치를 대체
    assert cm.holding_cost(1.0, ts=idx[1]) == pytest.approx(0.001)    # 롱 지불
    assert cm.holding_cost(-1.0, ts=idx[1]) == pytest.approx(-0.001)  # 숏 수취
    assert cm.holding_cost(1.0, ts=idx[2]) == pytest.approx(-0.002)   # 음수 펀딩=롱 수취
    # 시리즈에 없는 타임스탬프는 0 (안전 기본값)
    assert cm.holding_cost(1.0, ts=pd.Timestamp("2030-01-01")) == 0.0


def test_holding_cost_default_fixed_rate_unchanged():
    """funding_series 미지정이면 기존 고정 보수치 그대로(하위 호환)."""
    cm = CostModel(funding=0.0002, short_borrow=0.001)
    assert cm.holding_cost(1.0) == pytest.approx(0.0002)
    assert cm.holding_cost(-1.0) == pytest.approx(0.0012)


def test_backtest_with_funding_series_runs_and_costs_long():
    """양(+) 펀딩 시리즈를 붙이면 롱 전략 자본이 무비용 대비 낮아진다."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("C", "1d", limit=300)
    fs = pd.Series(0.0005, index=df.index)           # 매 봉 롱 지불
    from quant.strategies import MovingAverageCross
    free = Backtester(MovingAverageCross(fast=10, slow=30),
                      cost_model=CostModel(fee=0.0, slippage=0.0)).run(df)
    paid = Backtester(MovingAverageCross(fast=10, slow=30),
                      cost_model=CostModel(fee=0.0, slippage=0.0,
                                           funding_series=fs)).run(df)
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
    assert np.isfinite(paid.equity.to_numpy()).all()
