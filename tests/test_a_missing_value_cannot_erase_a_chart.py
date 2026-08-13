"""값 하나가 없다고 **차트가 통째로 사라지면** 안 된다 (감사 213).

곡선을 그리는 코드가 전부 이렇게 시작하고 있었다:

    lo, hi = float(vals.min()), float(vals.max())
    rng = hi - lo or 1.0

`or 1.0`은 "평평하면 0으로 나누지 말자"는 가드다. 의도는 맞다. 그런데
**NaN은 참이라 그대로 통과한다** — numpy의 `min`은 NaN을 만나면 NaN을
내므로 값 하나만 결측이면 lo·hi·rng가 전부 NaN이 되고, 좌표가 이렇게 나온다:

    <polygon points="0,200 0.0,nan 266.7,nan 533.3,nan 800.0,nan 800,200"

브라우저는 말이 안 되는 좌표를 조용히 무시한다. 오류도 없고 빈 그림도
아니다 — 보는 사람은 "오늘은 데이터가 없나 보다"라고 생각한다. **실패보다
나쁜 종류다.**

이 저장소에서 반복해 나온 두 교훈이 겹친 자리다:
  · 가드가 있다는 것이 막힌다는 뜻은 아니다 (감사 183·198·209)
  · `A or B`에서 A가 숫자면 0·NaN에서 뜻이 달라진다 (감사 183·195·205)

같은 두 줄이 **일곱 곳**에 복사돼 있었다. 계산을 `quant.reporting.scale`
한 곳으로 모았고, 이 파일은 그 계약을 지킨다.
"""

from __future__ import annotations

import ast
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.reporting.scale import axis_span, plot_points  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# ── 범위 계산 ────────────────────────────────────────────────

def test_a_nan_does_not_poison_the_span():
    span = axis_span([100.0, float("nan"), 102.0])
    assert span is not None
    lo, hi, rng = span
    assert (lo, hi) == (100.0, 102.0) and rng == pytest.approx(2.0)
    assert all(math.isfinite(v) for v in span)


def test_an_infinity_is_dropped_too():
    lo, hi, rng = axis_span([1.0, float("inf"), 3.0])
    assert (lo, hi, rng) == (1.0, 3.0, 2.0)


def test_a_flat_series_still_gets_a_usable_range():
    """원래 가드가 지키려던 것 — 0으로 나누지 않는다."""
    lo, hi, rng = axis_span([5.0, 5.0, 5.0])
    assert lo == hi == 5.0 and rng == 1.0


def test_nothing_drawable_says_so_instead_of_faking_a_flat_line():
    """그릴 값이 없으면 None — 0이나 1을 돌려주면 없는 데이터가 생긴다."""
    assert axis_span([float("nan"), float("nan")]) is None
    assert axis_span([]) is None
    assert axis_span([None, "x"]) is None


# ── 좌표 생성 ────────────────────────────────────────────────

def test_missing_bars_are_skipped_not_drawn_as_nan():
    """범위만 고쳐서는 부족했다 — 좌표를 만드는 자리도 결측을 걸러야 한다."""
    pts = plot_points([100.0, float("nan"), 102.0], 800, 200, 100.0, 2.0)
    assert len(pts) == 2, "결측 봉이 좌표로 남았다"
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in pts)


def test_a_missing_bar_is_not_filled_in():
    """없는 값을 0이나 직전 값으로 채우면 없던 사실이 그림에 생긴다."""
    pts = plot_points([10.0, float("nan"), 10.0], 100, 100, 10.0, 1.0)
    ys = [y for _, y in pts]
    assert len(ys) == 2 and len(set(ys)) == 1, (
        "결측 봉을 채워 그렸다 — 폭락이나 '변화 없음'이라는 없던 사실이 생긴다")


# ── 실제 차트 함수들 ─────────────────────────────────────────

def test_the_report_sparkline_survives_a_missing_bar():
    from quant.reporting.html_report import _sparkline

    out = _sparkline(pd.Series([100.0, 101.0, np.nan, 103.0]))
    assert "nan" not in out, "차트가 nan 좌표로 무너졌다 — 조용히 사라진다"
    assert out.count(",") >= 4, "선이 그려지지 않았다"


def test_the_cockpit_sparkline_survives_a_missing_bar():
    from quant.reporting.dashboard import _sparkline

    out = _sparkline([100.0, float("nan"), 102.0])
    assert "nan" not in out


def test_the_cockpit_draws_nothing_when_every_bar_is_missing():
    """그릴 값이 하나도 없으면 **빈 선**이어야 한다.

    가짜 범위를 만들어 평평한 선을 그리면, 보는 사람은 '자산이 그대로'라고
    읽는다 — 실제로는 아무것도 모르는 상태다.
    """
    from quant.reporting.dashboard import _sparkline

    out = _sparkline([float("nan"), float("nan"), float("nan")])
    assert 'points=""' in out, (
        f"값이 없는데 좌표를 그렸다 — {out[:160]}")
    assert "nan" not in out


def test_a_normal_chart_is_still_drawn():
    """대조군 — 결측을 막느라 멀쩡한 차트까지 비우면 아무 소용이 없다."""
    from quant.reporting.html_report import _sparkline

    out = _sparkline(pd.Series([100.0, 105.0, 102.0, 108.0]))
    assert "polyline" in out or "polygon" in out
    assert out.count(",") >= 4 and "nan" not in out


def test_an_all_missing_series_draws_nothing_rather_than_a_lie():
    from quant.reporting.html_report import _sparkline

    assert _sparkline(pd.Series([np.nan, np.nan])) == "<svg></svg>"


def test_the_heatmap_marks_an_unknown_cell_instead_of_colouring_it():
    """색이 안 칠해진 칸은 '중립'으로 읽힌다 — 모르는 것은 모른다고 해야 한다."""
    from quant.reporting.heatmap import _color

    assert "nan" not in _color(float("nan"), 0.0, 1.0)
    assert _color(float("nan"), 0.0, 1.0) != _color(0.5, 0.0, 1.0)
    # 대조군: 멀쩡한 값은 여전히 빨강→초록으로 칠해진다
    assert _color(0.0, 0.0, 1.0) != _color(1.0, 0.0, 1.0)


# ── 형제 찾기 ───────────────────────────────────────────────

def test_nobody_computes_a_chart_range_by_hand_anymore():
    """`hi - lo or 1.0`이 되살아나면 같은 결함이 그 파일에서 다시 자란다.

    한 곳만 고치면 나머지가 계속 무너진다 — 실제로 일곱 곳이었다.
    """
    offenders = []
    for path in sorted((ROOT / "quant").rglob("*.py")):
        if path.name == "scale.py":
            continue
        src = path.read_text("utf-8")
        for node in ast.walk(ast.parse(src)):
            # `<무언가> or <상수>` 꼴에서 왼쪽이 뺄셈이면 범위 계산이다
            if not (isinstance(node, ast.BoolOp)
                    and isinstance(node.op, ast.Or) and len(node.values) == 2):
                continue
            left = node.values[0]
            if isinstance(left, ast.BinOp) and isinstance(left.op, ast.Sub):
                offenders.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} — "
                    f"{ast.unparse(node)}")
    assert not offenders, (
        "차트 범위를 직접 계산하는 자리가 남아 있다 — NaN이 통과해 차트가 "
        "조용히 사라진다. quant.reporting.scale.axis_span을 쓸 것:\n  "
        + "\n  ".join(offenders))
