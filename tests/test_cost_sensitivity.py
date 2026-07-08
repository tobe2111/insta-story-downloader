"""손익분기 비용 분석 테스트 — 고회전 전략이 비용을 못 이기는지 폭로하는 도구.

핵심 검증: 수수료가 오르면 총수익이 단조 감소하고(거래하는 전략 기준),
손익분기 수수료가 알려진 구간 안에 있으며, 수수료 0에서도 손실이면 플래그가
서고, 리포트가 정직한 문구를 담는지.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest.cost_sensitivity import (
    break_even_cost,
    cost_sensitivity_report,
    cost_sweep,
)
from quant.data import SyntheticDataProvider
from quant.strategies import MovingAverageCross


def _df(seed: int = 7, n: int = 400) -> pd.DataFrame:
    return SyntheticDataProvider(seed=seed).get_ohlcv("BE", "1d", limit=n)


def _factory():
    return MovingAverageCross(fast=5, slow=20)


def test_cost_sweep_monotonic():
    """수수료가 오르면 총수익은 낮거나 같아진다(거래하는 전략)."""
    df = _df()
    fees = [0.0, 0.0005, 0.001, 0.002, 0.005]
    sweep = cost_sweep(df, _factory, fees)
    assert [r["fee"] for r in sweep] == fees
    # 실제로 회전이 있는 전략인지 먼저 확인(회전 0이면 단조성 검증 의미 없음)
    assert sweep[-1]["num_trades"] > 0
    rets = [r["total_return"] for r in sweep]
    for lo, hi in zip(rets, rets[1:]):
        assert hi <= lo + 1e-12


def test_break_even_between_bounds():
    """손익분기 수수료는 0 이상 hi 이하이며, 수익 나는 전략이면 base>0."""
    df = _df()
    be = break_even_cost(df, _factory, hi=0.02)
    if not be["unprofitable_at_zero"]:
        assert be["base_return_at_zero_fee"] > 0.0
        assert 0.0 <= be["break_even_fee"] <= 0.02
        # 손익분기 근처에서 실제로 총수익이 0을 가로지르는지 교차 확인
        if not be["capped"]:
            fee = be["break_even_fee"]
            lo = cost_sweep(df, _factory, [max(0.0, fee * 0.5)])[0]["total_return"]
            hi = cost_sweep(df, _factory, [fee * 1.5])[0]["total_return"]
            assert lo >= hi                     # 단조: 낮은 수수료가 더 높은 수익
            assert lo >= -1e-6 and hi <= 1e-6   # 0을 사이에 둔다


def test_break_even_turnover_reported():
    df = _df()
    be = break_even_cost(df, _factory)
    assert be["turnover_per_bar"] >= 0.0
    assert set(be) >= {
        "break_even_fee", "base_return_at_zero_fee", "turnover_per_bar",
        "unprofitable_at_zero", "capped",
    }


def test_zero_cost_unprofitable_flag():
    """수수료 0에서도 손실인 전략 → break_even_fee=0.0, 플래그 True."""
    # 수익률을 통제하기 위해 아래로 표류하는 하락장을 만든다.
    df = SyntheticDataProvider(
        seed=3, annual_drift=-0.5, annual_vol=0.6
    ).get_ohlcv("DOWN", "1d", limit=400)

    def factory():
        return MovingAverageCross(fast=5, slow=20)

    be = break_even_cost(df, factory)
    if be["base_return_at_zero_fee"] <= 0.0:
        assert be["unprofitable_at_zero"] is True
        assert be["break_even_fee"] == 0.0


def test_report_contains_key_phrases():
    df = _df()
    sweep = cost_sweep(df, _factory, [0.0, 0.001, 0.005])
    be = break_even_cost(df, _factory)
    text = cost_sensitivity_report(sweep, be)
    assert "손익분기" in text
    assert "환상" in text or "엣지" in text
    assert "보장" in text


def test_report_unprofitable_case_phrasing():
    """수수료 0에서도 손실인 경우 리포트가 '엣지가 없다'는 취지를 담는다."""
    df = _df()
    fake_be = {
        "break_even_fee": 0.0,
        "base_return_at_zero_fee": -0.1,
        "turnover_per_bar": 0.5,
        "unprofitable_at_zero": True,
        "capped": False,
    }
    text = cost_sensitivity_report([], fake_be)
    assert "엣지" in text and "보장" in text
