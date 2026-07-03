"""확률적/디플레이티드 샤프 지수 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.robustness import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)

# 양의 기대수익을 가진 결정론적 수익률 시퀀스
_R = pd.Series([0.01, -0.004, 0.012, -0.002, 0.008, 0.011, -0.003, 0.009] * 12)


def test_psr_in_range_and_positive():
    psr = probabilistic_sharpe_ratio(_R, 0.0)
    assert 0.0 <= psr <= 1.0
    assert psr > 0.5   # 양의 샤프 → 참 샤프>0 확률 과반


def test_psr_higher_benchmark_lowers_confidence():
    low = probabilistic_sharpe_ratio(_R, 0.0)
    high = probabilistic_sharpe_ratio(_R, 0.3)
    assert high <= low


def test_deflated_penalizes_more_trials():
    d1 = deflated_sharpe_ratio(_R, n_trials=1)
    d50 = deflated_sharpe_ratio(_R, n_trials=50)
    d500 = deflated_sharpe_ratio(_R, n_trials=500)
    assert d1 >= d50 >= d500        # 시행이 많을수록 기준↑ → 신뢰도↓
    assert all(0.0 <= x <= 1.0 for x in (d1, d50, d500))


def test_deflated_n1_equals_psr():
    d1 = deflated_sharpe_ratio(_R, n_trials=1)
    psr = probabilistic_sharpe_ratio(_R, 0.0)
    assert abs(d1 - psr) < 1e-9


def test_expected_max_sharpe_grows_with_trials():
    a = expected_max_sharpe(10, 0.1)
    b = expected_max_sharpe(1000, 0.1)
    assert b > a > 0.0


def test_short_series_returns_zero():
    assert deflated_sharpe_ratio(pd.Series([0.01, 0.02]), n_trials=5) == 0.0
