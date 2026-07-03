"""거래 비용 모델 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester, CostModel
from quant.data import SyntheticDataProvider


def test_turnover_cost_base_and_impact():
    cm = CostModel(fee=0.001, slippage=0.0005, impact_coef=0.5)
    assert abs(cm.turnover_cost(1.0, vol=0.0) - 0.0015) < 1e-12
    # 변동성이 있으면 슬리피지가 커진다
    assert cm.turnover_cost(1.0, vol=0.02) > cm.turnover_cost(1.0, vol=0.0)


def test_holding_cost_short_and_funding():
    cm = CostModel(short_borrow=0.001, funding=0.0002)
    assert cm.holding_cost(1.0) == pytest.approx(0.0002)    # 롱: 펀딩만
    assert cm.holding_cost(-1.0) == pytest.approx(0.0012)   # 숏: 펀딩+차입
    assert cm.holding_cost(0.0) == 0.0


def test_default_backtester_matches_flat_cost():
    """cost_model 미지정 시 기존 fee/slippage와 동일 결과(하위 호환)."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("C", "1d", limit=300)
    a = Backtester(_ma(), fee=0.001, slippage=0.0005).run(df)
    b = Backtester(_ma(), cost_model=CostModel(fee=0.001, slippage=0.0005)).run(df)
    assert np.allclose(a.equity.to_numpy(), b.equity.to_numpy())


def test_funding_reduces_equity():
    """펀딩비가 있으면 보유 전략의 최종 자본이 낮아진다."""
    df = SyntheticDataProvider(seed=8).get_ohlcv("C", "1d", limit=300)
    free = Backtester(_ma(), cost_model=CostModel(fee=0.0, slippage=0.0)).run(df)
    costly = Backtester(
        _ma(), cost_model=CostModel(fee=0.0, slippage=0.0, funding=0.001)).run(df)
    assert costly.equity.iloc[-1] < free.equity.iloc[-1]


def _ma():
    from quant.strategies import MovingAverageCross
    return MovingAverageCross(fast=10, slow=30)
