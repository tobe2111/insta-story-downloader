"""최적화/워크포워드 검증 테스트 (합성 데이터, 결정론적)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.optimize import grid_search, tune_and_validate, walk_forward
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


def test_grid_search_minimizes_lower_is_better(df):
    """변동성처럼 '작을수록 좋은' 목적함수는 최소값을 골라야 한다(방향 버그 수정)."""
    grid = {"fast": [5, 10, 20], "slow": [40, 60, 120]}
    out = grid_search(df, MovingAverageCross, grid, objective="volatility")
    vols = [r["volatility"] for r in out["results"]]
    assert out["best_score"] == min(vols)          # 최대가 아니라 최소
    assert out["best_metrics"].volatility == min(vols)


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


def test_walk_forward_includes_first_oos_bar(df):
    """OOS total_return이 첫 OOS 봉의 수익을 포함해야 한다(누락 회귀 방지).

    equity[0]은 '첫 수익 실현 전' 자본이어야 compute_metrics의
    total_return=eq[-1]/eq[0]-1 이 모든 OOS 봉을 반영한다. 워밍업 수정 이후
    첫 OOS 봉 수익이 실제 값(비영)이 되면서, 선행 자본 점 없이 cumprod만 쓰면
    그 봉이 기준가로 흡수되어 통째로 사라졌었다.
    """
    grid = {"fast": [5, 10], "slow": [40, 60]}
    capital = 10_000.0
    wf = walk_forward(df, MovingAverageCross, grid,
                      is_window=250, oos_window=125, initial_capital=capital)
    eq = wf["equity"]
    # 선행 점: 자본 그대로에서 시작
    assert abs(float(eq.iloc[0]) - capital) < 1e-9
    # total_return == 모든 OOS 수익률의 복리곱 - 1 (첫 봉 포함)
    rets = eq.pct_change().dropna()
    expected = float((1 + rets).prod() - 1.0)
    assert abs(wf["oos_metrics"].total_return - expected) < 1e-12


def test_walk_forward_insufficient_data():
    df = SyntheticDataProvider(seed=2).get_ohlcv("Y", limit=100)
    with pytest.raises(ValueError):
        walk_forward(df, MovingAverageCross, {"fast": [5], "slow": [20]},
                     is_window=250, oos_window=125)


def test_walk_forward_embargo_creates_gap(df):
    """엠바고(퍼징) 갭이 있으면 IS 끝과 OOS 시작 사이에 공백이 생긴다."""
    grid = {"fast": [5, 10], "slow": [40, 60]}
    embargo = 20
    wf = walk_forward(
        df, MovingAverageCross, grid,
        is_window=250, oos_window=125, objective="sharpe", embargo=embargo,
    )
    assert wf["segments"]
    # 첫 구간: is_start 인덱스 0, oos_start 인덱스는 250+embargo 여야 한다
    idx = list(df.index)
    first = wf["segments"][0]
    assert first["is_start"] == str(idx[0])
    assert first["oos_start"] == str(idx[250 + embargo])


def test_tune_and_validate_wraps_walk_forward(df):
    """tune_and_validate는 walk_forward와 동일한 결과 + 정직성 안내문을 반환한다."""
    grid = {"fast": [5, 10], "slow": [40, 60]}
    tuned = tune_and_validate(df, MovingAverageCross, grid,
                              is_window=250, oos_window=125, objective="sharpe")
    wf = walk_forward(df, MovingAverageCross, grid,
                      is_window=250, oos_window=125, objective="sharpe")
    # 새 수학 없음 — 순수 래퍼이므로 구간·성과가 동일해야 한다 (결정론적)
    assert tuned["segments"] == wf["segments"]
    assert tuned["oos_metrics"].sharpe == wf["oos_metrics"].sharpe
    # 정직성 안내문: 튜닝은 워크포워드 루프 안에서만, 수익 보장 아님
    assert "OOS" in tuned["note"] and "룩어헤드" in tuned["note"]


def test_tune_and_validate_passes_kwargs(df):
    """embargo 같은 워크포워드 인자가 그대로 전달된다."""
    tuned = tune_and_validate(df, MovingAverageCross,
                              {"fast": [5], "slow": [40]},
                              is_window=250, oos_window=125, embargo=20)
    idx = list(df.index)
    assert tuned["segments"][0]["oos_start"] == str(idx[250 + 20])


def test_walk_forward_embargo_insufficient_data():
    """엠바고까지 더하면 데이터가 모자랄 때 명확히 실패한다."""
    df = SyntheticDataProvider(seed=3).get_ohlcv("Z", limit=380)
    with pytest.raises(ValueError):
        walk_forward(df, MovingAverageCross, {"fast": [5], "slow": [20]},
                     is_window=250, oos_window=125, embargo=20)
