"""탐색과 그림이 같은 방향을 보는가 (감사 177).

`grid_search`는 파라미터 조합을 전부 백테스트해 **가장 좋은 것**을 고르고,
`build_heatmap_html`은 같은 결과에 색을 칠하고 ★를 붙인다. 둘이 '좋다'의
방향을 다르게 알면, 그림은 **최악의 조합에 ★와 초록색**을 붙여 사람을
정반대로 유도한다.

그래서 방향 정의는 `quant/objective.py` 한 곳에 있다.

    LOWER_IS_BETTER = frozenset({"volatility"})

전수조사에서 셋(objective·grid·heatmap)을 같은 눈으로 훑었다.
**결함은 못 찾았다.** 확인한 것:

  · grid와 heatmap이 **같은 출처**를 임포트한다(각자 하드코딩하지 않는다)
  · 방향이 뒤집히는 지표(volatility)에서 둘의 답이 실제로 일치한다
  · `max_drawdown`이 집합에 없는 이유가 성립한다 — **음수로 저장**되므로
    "클수록(0에 가까울수록) 좋다"가 맞다. 실측 -0.3333로 확인했다.
    (양수 크기로 저장돼 있었다면 최악을 최적으로 고르고 있었을 것이다.)

이 파일들에는 방향에 대한 변이 항목이 없었다 — 부호를 뒤집어도 스위트가
초록이었다. 계약을 고정해 둔다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.metrics import compute_metrics  # noqa: E402
from quant.objective import LOWER_IS_BETTER  # noqa: E402
from quant.reporting.heatmap import build_heatmap_html  # noqa: E402


# ── 방향 정의가 한 곳에서 온다 ────────────────────────────────


def test_grid_and_heatmap_share_one_source_of_truth():
    """각자 하드코딩하면 새 지표를 추가할 때 한쪽만 고쳐 ★가 어긋난다."""
    for mod in ("quant/optimize/grid.py", "quant/reporting/heatmap.py"):
        src = (ROOT / mod).read_text("utf-8")
        assert "from quant.objective import LOWER_IS_BETTER" in src, mod


def test_the_objective_module_stays_dependency_free():
    """heatmap은 순수 stdlib이라 pandas를 끌어오면 임포트가 깨진다."""
    src = (ROOT / "quant" / "objective.py").read_text("utf-8")
    assert "import pandas" not in src and "import numpy" not in src


def test_drawdown_is_stored_negative_so_higher_is_better():
    """`max_drawdown`을 집합에서 뺀 근거 자체를 못 박는다.

    양수 크기로 저장되기 시작하면 탐색이 **가장 아팠던 조합**을 최적으로
    고른다. 그때 이 검사가 깨져서 알려 준다.
    """
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    eq = pd.Series([100.0, 120.0, 80.0, 90.0, 130.0], index=idx)
    m = compute_metrics(eq, eq.pct_change().fillna(0.0),
                        pd.Series([1.0] * 5, index=idx), periods_per_year=365)
    assert m.max_drawdown == pytest.approx(-1 / 3), m.max_drawdown
    assert "max_drawdown" not in LOWER_IS_BETTER


def test_volatility_is_the_one_that_flips():
    assert "volatility" in LOWER_IS_BETTER
    for higher_better in ("sharpe", "sortino", "calmar", "cagr", "total_return"):
        assert higher_better not in LOWER_IS_BETTER, higher_better


# ── ★가 실제 최적을 가리키는가 ────────────────────────────────


X = [5, 10]            # fast
Y = [20, 40]           # slow
SHARPE = [[0.5, 1.2],  # slow=20 행: fast=5 → 0.5, fast=10 → 1.2
          [1.9, 0.8]]  # slow=40 행
VOL = [[0.40, 0.25],
       [0.11, 0.33]]
GRIDS = {"sharpe": SHARPE, "volatility": VOL}


def _starred(objective: str) -> set[str]:
    doc = build_heatmap_html(X, Y, GRIDS[objective], "fast", "slow", objective)
    out = set()
    for cell in doc.split("<td")[1:]:
        if "★" in cell:
            out.add(cell.split(">", 1)[1].split("★")[0].strip())
    return out


def test_the_star_marks_the_highest_when_higher_is_better():
    assert _starred("sharpe") == {"1.90"}, _starred("sharpe")


def test_the_star_marks_the_lowest_when_lower_is_better():
    """이 한 줄이 뒤집히면 그림이 최악의 조합을 추천한다."""
    assert _starred("volatility") == {"0.11"}, _starred("volatility")


def test_the_heatmap_labels_both_axes():
    """축 이름이 없으면 어느 쪽이 fast인지 알 수 없다(감사 158과 같은 계열)."""
    doc = build_heatmap_html(X, Y, SHARPE, "fast", "slow", "sharpe")
    assert "fast" in doc and "slow" in doc


def test_an_empty_grid_does_not_crash():
    """대조군 — 조합이 하나도 안 만들어지는 그리드도 있다."""
    assert isinstance(build_heatmap_html([], [], [], "fast", "slow", "sharpe"), str)


# ── 탐색이 같은 답을 내는가 ───────────────────────────────────


def _hue(objective: str, value: float) -> float:
    """그 값이 칠해진 색의 색상값(0=빨강 … 120=초록)을 뽑는다."""
    doc = build_heatmap_html(X, Y, GRIDS[objective], "fast", "slow", objective)
    for cell in doc.split("<td")[1:]:
        if f">{value:.2f}" in cell:
            return float(cell.split("hsl(")[1].split(" ")[0])
    raise AssertionError(f"{value} 셀을 못 찾았다")


@pytest.mark.parametrize("objective,best,worst", [
    ("sharpe", 1.90, 0.50),        # 클수록 좋다
    ("volatility", 0.11, 0.40),    # 작을수록 좋다
])
def test_the_good_end_is_green_in_both_directions(objective, best, worst):
    """⚠️ ★만 검사하면 **색 반전**을 놓친다(실제로 변이가 통과했다).

    ★는 최적 한 칸에만 붙지만, 색은 모든 칸에 칠해진다. 색 방향이 뒤집히면
    ★는 제자리인데 **주변이 전부 반대로 칠해져** 눈으로는 정반대로 읽힌다.
    """
    assert _hue(objective, best) > 100, (
        f"{objective}의 최적값이 초록이 아니다(hue {_hue(objective, best):.0f})")
    assert _hue(objective, worst) < 20, (
        f"{objective}의 최악값이 빨강이 아니다(hue {_hue(objective, worst):.0f})")


# ── 탐색이 같은 답을 내는가 (진짜 grid_search로) ──────────────


def test_the_search_really_minimises_a_lower_is_better_objective():
    """⚠️ 여기서 로직을 **재현**하면 안 된다.

    처음에 grid_search의 부호 반전을 손으로 옮겨 적어 검사했더니, 그 줄을
    지우는 변이가 그대로 통과했다 — 내 사본을 검사한 것이지 코드를 검사한
    게 아니었다. 진짜 함수를 부른다.
    """
    from quant.data.synthetic import SyntheticDataProvider
    from quant.optimize.grid import grid_search
    from quant.strategies import MovingAverageCross

    df = SyntheticDataProvider(seed=7).get_ohlcv("T", "1d", limit=220)
    grid = {"fast": [5, 20], "slow": [40, 90]}

    low = grid_search(df, MovingAverageCross, grid, objective="volatility")
    vols = [r["volatility"] for r in low["results"]]
    assert len(vols) >= 2, "조합이 하나뿐이면 방향을 볼 수 없다"
    assert low["best_score"] == pytest.approx(min(vols)), (
        f"변동성을 최소화해야 하는데 {low['best_score']:.4f}를 골랐다 "
        f"(최소 {min(vols):.4f} / 최대 {max(vols):.4f})")

    high = grid_search(df, MovingAverageCross, grid, objective="sharpe")
    sharpes = [r["sharpe"] for r in high["results"]]
    assert high["best_score"] == pytest.approx(max(sharpes))


def test_the_search_reports_the_raw_score_not_the_flipped_one():
    """부호를 뒤집어 비교하되, 보고하는 값은 원본이어야 한다."""
    from quant.data.synthetic import SyntheticDataProvider
    from quant.optimize.grid import grid_search
    from quant.strategies import MovingAverageCross

    df = SyntheticDataProvider(seed=7).get_ohlcv("T", "1d", limit=220)
    got = grid_search(df, MovingAverageCross, {"fast": [5, 20], "slow": [40]},
                      objective="volatility")
    assert got["best_score"] > 0, "변동성이 음수로 보고된다(부호 반전이 새어 나감)"
