"""최적화/워크포워드 검증 테스트 (합성 데이터, 결정론적)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.optimize import grid_search, walk_forward
from quant.strategies import MovingAverageCross


@pytest.fixture
def df():
    return SyntheticDataProvider(seed=11).get_ohlcv("OPT", "1d", limit=700)


def test_grid_search_finds_best(df):
    grid = {"fast": [5, 10, 20], "slow": [40, 60, 120]}
    out = grid_search(df, MovingAverageCross, grid, objective="sharpe")
    assert out["best_params"] is not None
    assert set(out["best_params"]) == {"fast", "slow"}
    # 유효하지 않은 조합(fast>=slow)은 제외되어야 함
    assert out["best_params"]["fast"] < out["best_params"]["slow"]
    assert len(out["results"]) > 0


def test_grid_search_skips_invalid():
    """fast >= slow 조합은 예외 없이 건너뛴다."""
    df = SyntheticDataProvider(seed=1).get_ohlcv("X", limit=200)
    grid = {"fast": [50], "slow": [10]}  # 전부 invalid
    out = grid_search(df, MovingAverageCross, grid)
    assert out["best_params"] is None
    assert out["results"] == []


def test_walk_forward(df):
    grid = {"fast": [5, 10], "slow": [40, 60]}
    wf = walk_forward(
        df, MovingAverageCross, grid,
        is_window=250, oos_window=125, objective="sharpe",
    )
    assert wf["segments"], "검증 구간이 생성되어야 함"
    assert (wf["equity"] > 0).all()
    for seg in wf["segments"]:
        assert seg["params"]["fast"] < seg["params"]["slow"]
    # OOS 지표는 계산 가능해야 함
    assert wf["oos_metrics"].max_drawdown <= 0.0


def test_walk_forward_insufficient_data():
    df = SyntheticDataProvider(seed=2).get_ohlcv("Y", limit=100)
    with pytest.raises(ValueError):
        walk_forward(df, MovingAverageCross, {"fast": [5], "slow": [20]},
                     is_window=250, oos_window=125)
