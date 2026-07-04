"""멀티 타임프레임 확인 + 유동성 필터 래퍼 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.strategies import (
    LiquidityFilter,
    MultiTimeframeFilter,
    get_strategy,
)

_DF = SyntheticDataProvider(seed=21).get_ohlcv("MTF", "1d", limit=420)


def test_mtf_bounded_and_gates():
    """MTF 필터는 경계 안에서 동작하고 신호를 '줄이기만' 한다(게이팅)."""
    base = get_strategy("ma_cross")
    mtf = MultiTimeframeFilter(get_strategy("ma_cross"), htf="W", trend_window=8)
    b = base.generate_signals(_DF)
    m = mtf.generate_signals(_DF)
    assert m.index.equals(_DF.index)
    assert m.abs().max() <= 1.0 + 1e-9
    # 게이팅은 신호를 0으로만 만드므로 활성 봉 수가 늘어나지 않는다
    assert int((m != 0).sum()) <= int((b != 0).sum())


def test_mtf_no_lookahead():
    """MTF: 미래를 잘라도 과거 신호가 바뀌지 않는다(직전 완성봉만 사용)."""
    cut = 320
    full = MultiTimeframeFilter(get_strategy("momentum"), htf="W").generate_signals(_DF)
    trunc = MultiTimeframeFilter(get_strategy("momentum"), htf="W").generate_signals(
        _DF.iloc[:cut])
    # 상위봉 경계 효과를 피해 여유(버퍼)를 두고 비교
    a = full.iloc[:cut - 10].to_numpy()
    c = trunc.iloc[:cut - 10].to_numpy()
    assert np.allclose(a, c, atol=1e-9), "MTF가 미래 상위봉을 참조함"


def test_liquidity_zero_threshold_is_passthrough():
    """min_dollar_vol=0 이면 base 신호를 그대로 통과시킨다."""
    base = get_strategy("rsi")
    liq = LiquidityFilter(get_strategy("rsi"), min_dollar_vol=0.0)
    assert np.allclose(base.generate_signals(_DF).to_numpy(),
                       liq.generate_signals(_DF).to_numpy(), atol=1e-12)


def test_liquidity_high_threshold_blocks_all():
    """거래대금 기준이 매우 높으면 전부 관망(0)한다."""
    liq = LiquidityFilter(get_strategy("momentum"), min_dollar_vol=1e18)
    sig = liq.generate_signals(_DF)
    assert (sig == 0).all()


def test_liquidity_moderate_gates():
    """중간 기준: 경계 안에서 동작하고 신호를 줄이기만 한다."""
    base = get_strategy("momentum")
    dv_median = float((_DF["close"] * _DF["volume"]).rolling(20).mean().median())
    liq = LiquidityFilter(get_strategy("momentum"), min_dollar_vol=dv_median)
    b = base.generate_signals(_DF)
    m = liq.generate_signals(_DF)
    assert m.abs().max() <= 1.0 + 1e-9
    assert int((m != 0).sum()) <= int((b != 0).sum())
