"""민감도 히트맵 생성 테스트 (순수 stdlib)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "heatmap_mod",
    str(Path(__file__).resolve().parent.parent / "quant" / "reporting" / "heatmap.py"),
)
heatmap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(heatmap)


def test_heatmap_written(tmp_path):
    grid = [[0.5, 1.2, 0.9], [1.0, 1.8, 1.1], [0.3, 0.7, 0.4]]
    out = heatmap.generate_heatmap(
        x_values=[5, 10, 20], y_values=[50, 100, 200], grid=grid,
        x_label="fast", y_label="slow", objective="sharpe",
        path=tmp_path / "h.html",
    )
    assert out.exists()
    doc = out.read_text(encoding="utf-8")
    assert "<table" in doc
    assert "hsl(" in doc          # 색상 보간 적용
    assert "★" in doc             # 최고값 표시 (1.8)
    assert "fast" in doc and "slow" in doc


def test_heatmap_handles_none(tmp_path):
    """유효하지 않은 조합(None)이 있어도 크래시 없이 렌더."""
    grid = [[None, 1.0], [0.5, None]]
    out = heatmap.generate_heatmap(
        x_values=[1, 2], y_values=[3, 4], grid=grid, path=tmp_path / "n.html",
    )
    doc = out.read_text(encoding="utf-8")
    assert "·" in doc  # None 셀 표시


def test_heatmap_color_bounds():
    lo, hi = 0.0, 2.0
    assert "120" in heatmap._color(2.0, lo, hi)  # 최고 → 초록(hue 120)
    assert heatmap._color(0.0, lo, hi).startswith("hsl(0")  # 최저 → 빨강(hue 0)


def test_heatmap_best_marker_follows_objective_direction():
    """★ 최고값 마커가 목적함수 방향을 따른다(sharpe=max, volatility=min)."""
    grid = [[0.10, 0.80]]
    up = heatmap.build_heatmap_html([1, 2], [1], grid, objective="sharpe")
    assert "0.80 ★" in up and "0.10 ★" not in up      # 클수록 좋음 → 0.80
    down = heatmap.build_heatmap_html([1, 2], [1], grid, objective="volatility")
    assert "0.10 ★" in down and "0.80 ★" not in down   # 작을수록 좋음 → 0.10
    # 색도 반전: 좋은 셀(0.10)이 초록(hue 120)에 매핑된다
    import re
    assert re.search(r"hsl\(120 65% 45%\)\"[^<]*>0\.10", down)
    assert re.search(r"hsl\(0 65% 45%\)\"[^<]*>0\.80", down)
