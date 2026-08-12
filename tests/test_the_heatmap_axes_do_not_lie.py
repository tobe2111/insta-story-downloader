"""민감도 히트맵의 **축이 거짓말하지 않는가** (감사 158).

히트맵은 "넓은 초록 고원 = 견고, 외딴 초록 점 = 과최적화"를 눈으로 보는
도구다. 사장님이 이 그림을 보고 파라미터를 고른다. 그래서 그림이 축을
바꿔 그리면 **틀린 파라미터를 고르게 된다** — 계산은 다 맞는데.

전치(transpose)는 조용하다. 정사각 격자에서는 모양이 그럴듯해 보이고,
값도 전부 '진짜 계산된 값'이라 이상해 보이지 않는다. 눈으로는 못 잡는다.

그래서 **정답을 아는 격자**로 못 박는다. x축과 y축의 길이를 다르게 두고
(3×2), 각 칸의 값이 어느 파라미터 조합에서 나온 것인지 직접 확인한다.

빈칸도 같은 문제다. `fast >= slow`처럼 성립하지 않는 조합은 None이어야
한다. 0.0으로 채우면 히트맵에 **'성과 0인 유효한 조합'**으로 그려져,
없는 지형이 있는 것처럼 보인다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.engine import Backtester  # noqa: E402
from quant.optimize import sensitivity_grid, tune_and_validate  # noqa: E402
from quant.strategies.moving_average import MovingAverageCross  # noqa: E402

N = 300
IDX = pd.date_range("2024-01-01", periods=N, freq="D")
X_VALUES = [5, 10, 20]          # fast — 열(가로)
Y_VALUES = [40, 80]             # slow — 행(세로).  3×2 → 전치되면 모양부터 깨진다


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(2)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.01, N)))
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1e6}, index=IDX)


def _grid():
    return sensitivity_grid(_frame(), MovingAverageCross,
                            "fast", X_VALUES, "slow", Y_VALUES)


# ── 격자의 모양과 좌표 ────────────────────────────────────────


def test_the_grid_is_rows_by_y_and_columns_by_x():
    g = _grid()
    assert len(g) == len(Y_VALUES), (
        f"행이 {len(g)}개 — y축({len(Y_VALUES)}개)이어야 한다. 전치됐다")
    assert all(len(row) == len(X_VALUES) for row in g), (
        f"열 길이 {[len(r) for r in g]} — x축({len(X_VALUES)}개)이어야 한다")


def test_every_cell_matches_the_backtest_of_its_own_coordinates():
    """칸 하나하나가 **그 좌표의 조합**으로 돌린 결과여야 한다.

    이게 이 파일의 핵심이다. 축을 바꿔 넣거나 행·열을 뒤집으면 값은
    여전히 '진짜 계산된 값'이라 그림만 봐서는 절대 못 잡는다.
    """
    df = _frame()
    g = _grid()
    for i, slow in enumerate(Y_VALUES):
        for j, fast in enumerate(X_VALUES):
            want = float(Backtester(
                MovingAverageCross(fast=fast, slow=slow)).run(df).metrics.sharpe)
            assert g[i][j] is not None, f"(fast={fast}, slow={slow})가 빈칸이다"
            assert abs(g[i][j] - want) < 1e-9, (
                f"격자[{i}][{j}] = {g[i][j]:.4f} 인데 "
                f"(fast={fast}, slow={slow})의 실제 샤프는 {want:.4f} — "
                "축이 뒤바뀌었거나 행·열이 전치됐다")


def test_the_cells_are_not_all_the_same():
    """대조군 — 값이 전부 같으면 위 검사가 전치를 못 잡는다."""
    vals = [v for row in _grid() for v in row if v is not None]
    assert len(set(round(v, 6) for v in vals)) > 1, (
        f"격자 값이 전부 같다: {vals} — 이 데이터로는 축 검사가 헛돈다")


# ── 성립하지 않는 조합 ────────────────────────────────────────


def test_impossible_combinations_stay_empty_not_zero():
    """fast >= slow는 만들 수 없는 조합이다 — 0이 아니라 빈칸이어야 한다.

    0으로 채우면 히트맵에 '성과 0인 유효 조합'으로 그려진다. 없는 지형이
    있는 것처럼 보이고, 색 스케일까지 그쪽으로 끌려간다.
    """
    g = sensitivity_grid(_frame(), MovingAverageCross,
                         "fast", [5, 20, 60], "slow", [20, 40])
    # (fast=20, slow=20)과 (fast=60, slow=20/40)은 성립하지 않는다
    assert g[0][1] is None, f"fast=20, slow=20이 값 {g[0][1]}을 가진다"
    assert g[0][2] is None and g[1][2] is None, (
        f"fast=60 조합이 채워졌다: {g[0][2]}, {g[1][2]}")
    assert g[0][0] is not None and g[1][0] is not None, (
        "성립하는 조합까지 비었다 — 이 검사가 헛돈다")


# ── 튜닝 진입점 ───────────────────────────────────────────────


def test_the_tuning_entry_point_really_walks_forward():
    """`tune_and_validate`의 존재 이유는 **전체 데이터 튜닝을 막는 것**이다.

    그리드서치로 바꿔치기하면 성과는 좋아 보이고(미래를 봤으니) 검사는
    조용하다 — 그래서 '구간이 실제로 나뉘었는가'를 직접 본다.
    """
    got = tune_and_validate(_frame(), MovingAverageCross,
                            {"fast": [5, 10], "slow": [40, 80]},
                            is_window=120, oos_window=40)
    assert got["segments"], (
        "워크포워드 구간이 하나도 없다 — 전체 데이터로 한 번에 튜닝했다")
    assert len(got["segments"]) >= 2, f"구간이 {len(got['segments'])}개뿐"
    assert "note" in got and "룩어헤드" in got["note"]


def test_the_honesty_note_is_not_just_decoration():
    """안내문이 말하는 성질이 실제로 지켜지는가 — 문구와 동작이 같아야 한다."""
    from quant.optimize.tuning import HONESTY_NOTE

    assert "IS" in HONESTY_NOTE and "OOS" in HONESTY_NOTE
    got = tune_and_validate(_frame(), MovingAverageCross,
                            {"fast": [5, 10], "slow": [40, 80]},
                            is_window=120, oos_window=40)
    # 각 구간의 OOS는 그 구간의 IS 뒤에 와야 한다(겹치면 룩어헤드다)
    for seg in got["segments"]:
        if {"is_end", "oos_start"} <= set(seg):
            assert str(seg["oos_start"]) >= str(seg["is_end"]), seg
