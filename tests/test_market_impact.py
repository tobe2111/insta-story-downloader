"""시장충격(제곱근 법칙) 비용 모델 테스트.

핵심 검증: 기본값(market_impact_coef=0)이면 기존 백테스트와 완전히 동일하고,
켰을 때만 참여율(participation)의 제곱근에 비례해 비용이 늘어난다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester, CostModel
from quant.data import SyntheticDataProvider


def _ma():
    from quant.strategies import MovingAverageCross
    return MovingAverageCross(fast=10, slow=30)


def test_impact_off_by_default_is_zero():
    cm = CostModel()
    assert cm.market_impact_coef == 0.0
    assert cm.market_impact_cost(1.0, 10_000, 5_000) == 0.0


def test_impact_sqrt_law_math():
    cm = CostModel(market_impact_coef=0.1)
    # participation = (0.5 × 10,000) / 20,000 = 0.25 → 비용 = 0.1×√0.25×0.5
    got = cm.market_impact_cost(turnover=0.5, equity=10_000, dollar_volume=20_000)
    assert got == pytest.approx(0.1 * math.sqrt(0.25) * 0.5)


def test_impact_grows_with_participation():
    """같은 회전율이라도 봉 거래대금이 얇을수록(참여율↑) 비용이 커진다."""
    cm = CostModel(market_impact_coef=0.1)
    thick = cm.market_impact_cost(0.5, 10_000, 1_000_000)
    thin = cm.market_impact_cost(0.5, 10_000, 10_000)
    assert thin > thick > 0.0


def test_impact_participation_capped():
    """거래대금보다 큰 주문도 participation_cap에서 폭주가 멈춘다."""
    cm = CostModel(market_impact_coef=0.1, participation_cap=1.0)
    at_cap = cm.market_impact_cost(1.0, 1_000_000, 1_000)   # 참여율 >> 1
    assert at_cap == pytest.approx(0.1 * 1.0 * 1.0)          # √1 × turnover 1


def test_impact_missing_volume_returns_zero():
    """거래대금 정보가 없으면 0(과소추정) — 예외를 던지지 않는다."""
    cm = CostModel(market_impact_coef=0.1)
    assert cm.market_impact_cost(0.5, 10_000, None) == 0.0
    assert cm.market_impact_cost(0.5, 10_000, 0.0) == 0.0
    assert cm.market_impact_cost(0.5, 10_000, float("nan")) == 0.0


def test_backtest_unchanged_when_impact_off():
    """market_impact_coef=0(기본)이면 기존 결과와 완전히 동일(하위 호환)."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("C", "1d", limit=300)
    a = Backtester(_ma(), cost_model=CostModel(fee=0.001, slippage=0.0005)).run(df)
    b = Backtester(_ma(), cost_model=CostModel(
        fee=0.001, slippage=0.0005, market_impact_coef=0.0)).run(df)
    assert np.allclose(a.equity.to_numpy(), b.equity.to_numpy())


def test_backtest_impact_reduces_equity():
    """시장충격을 켜면 (거래가 있는 한) 최종 자본이 낮아진다."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("C", "1d", limit=300)
    free = Backtester(_ma(), cost_model=CostModel(fee=0.0, slippage=0.0)).run(df)
    hit = Backtester(_ma(), cost_model=CostModel(
        fee=0.0, slippage=0.0, market_impact_coef=0.1)).run(df)
    assert hit.equity.iloc[-1] < free.equity.iloc[-1]


def test_backtest_without_volume_column_still_runs():
    """volume 컬럼이 없어도 충격 비용 0으로 안전하게 돌아간다."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("C", "1d", limit=200)
    df = df.drop(columns=["volume"])
    res = Backtester(_ma(), cost_model=CostModel(
        fee=0.0, slippage=0.0, market_impact_coef=0.1)).run(df)
    base = Backtester(_ma(), cost_model=CostModel(fee=0.0, slippage=0.0)).run(df)
    assert np.allclose(res.equity.to_numpy(), base.equity.to_numpy())
