"""파라미터 민감도 히트맵 (순수 stdlib, 인라인 HTML/CSS — 의존성 0).

2D 그리드(예: 단기MA × 장기MA에 대한 샤프지수)를 색으로 그린다.
    - 넓은 초록 고원  → 견고함(robust). 파라미터가 조금 틀려도 성과 유지.
    - 외딴 초록 점    → 과최적화. 그 값에서만 반짝, 실전에서 무너짐.

matplotlib 없이 색상 보간(HSL: 빨강→노랑→초록)으로 렌더링한다.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Sequence


def _color(value: float, lo: float, hi: float) -> str:
    """lo~hi 범위의 값을 빨강(낮음)→노랑→초록(높음) HSL 색으로."""
    rng = (hi - lo) or 1.0
    t = max(0.0, min(1.0, (value - lo) / rng))
    hue = 120 * t  # 0=빨강, 120=초록
    return f"hsl({hue:.0f} 65% 45%)"


def build_heatmap_html(
    x_values: Sequence,
    y_values: Sequence,
    grid: Sequence[Sequence[float | None]],
    x_label: str = "x",
    y_label: str = "y",
    objective: str = "sharpe",
    title: str = "파라미터 민감도 히트맵",
) -> str:
    """히트맵을 HTML 문자열로 렌더링한다 (웹서버·파일 저장 공용)."""
    flat = [v for row in grid for v in row if v is not None]
    lo, hi = (min(flat), max(flat)) if flat else (0.0, 1.0)
    best = max(flat) if flat else None

    header = "".join(f"<th>{html.escape(str(x))}</th>" for x in x_values)
    body = ""
    for i, y in enumerate(y_values):
        cells = ""
        for j in range(len(x_values)):
            v = grid[i][j] if j < len(grid[i]) else None
            if v is None:
                cells += '<td class="na">·</td>'
            else:
                bg = _color(v, lo, hi)
                mark = " ★" if v == best else ""
                cells += (f'<td style="background:{bg}" title="{y_label}={y}, '
                          f'{x_label}={x_values[j]}">{v:.2f}{mark}</td>')
        body += f"<tr><th>{html.escape(str(y))}</th>{cells}</tr>"

    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#0b1220;color:#e2e8f0}}
 @media(prefers-color-scheme:light){{body{{background:#f8fafc;color:#0f172a}}}}
 .wrap{{max-width:960px;margin:0 auto;padding:24px}}
 h1{{font-size:18px}} .sub{{color:#94a3b8;font-size:13px;margin-bottom:16px}}
 .scroll{{overflow-x:auto}}
 table{{border-collapse:collapse;margin-top:8px}}
 td,th{{padding:8px 10px;text-align:center;font-variant-numeric:tabular-nums;font-size:13px}}
 td{{color:#0b1220;font-weight:600;min-width:52px}}
 th{{color:#94a3b8;font-weight:600}}
 td.na{{background:#334155;color:#64748b}}
 .axis{{color:#94a3b8;font-size:12px;margin-top:6px}}
 .legend{{display:flex;align-items:center;gap:8px;margin-top:14px;font-size:12px;color:#94a3b8}}
 .bar{{height:12px;width:200px;border-radius:6px;
   background:linear-gradient(90deg,hsl(0 65% 45%),hsl(60 65% 45%),hsl(120 65% 45%))}}
</style></head><body><div class="wrap">
<h1>{html.escape(title)}</h1>
<div class="sub">세로축: <b>{html.escape(y_label)}</b> · 가로축: <b>{html.escape(x_label)}</b>
 · 값: <b>{html.escape(objective)}</b> · ★ = 최고값</div>
<div class="scroll"><table>
<tr><th></th>{header}</tr>
{body}
</table></div>
<div class="axis">→ 가로축: {html.escape(x_label)}</div>
<div class="legend"><span>낮음</span><span class="bar"></span><span>높음 ({html.escape(objective)})</span></div>
<p class="sub" style="margin-top:18px">💡 넓은 초록 고원 = 견고함. 외딴 초록 점 = 과최적화 위험.
과거 성과는 미래를 보장하지 않습니다.</p>
</div></body></html>"""
    return doc


def generate_heatmap(
    x_values: Sequence,
    y_values: Sequence,
    grid: Sequence[Sequence[float | None]],
    x_label: str = "x",
    y_label: str = "y",
    objective: str = "sharpe",
    title: str = "파라미터 민감도 히트맵",
    path: str | Path = "results/heatmap.html",
) -> Path:
    """히트맵을 HTML 파일로 저장하고 경로를 반환한다."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build_heatmap_html(x_values, y_values, grid, x_label, y_label, objective, title),
        encoding="utf-8")
    return out
