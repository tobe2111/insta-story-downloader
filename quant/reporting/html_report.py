"""백테스트 결과를 자체 완결형 HTML 리포트로 저장한다 (외부 라이브러리 불필요).

자본곡선과 낙폭(drawdown)을 인라인 SVG로 그리므로 matplotlib 없이도 동작한다.
브라우저로 열면 성과 지표와 차트를 한눈에 볼 수 있다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant.backtest.engine import BacktestResult


def _sparkline(series: pd.Series, width: int = 800, height: int = 200,
               color: str = "#2563eb", fill: bool = True) -> str:
    vals = series.to_numpy(dtype=float)
    if len(vals) < 2:
        return "<svg></svg>"
    lo, hi = float(vals.min()), float(vals.max())
    rng = hi - lo or 1.0
    n = len(vals)
    pts = [
        (i / (n - 1) * width, height - (v - lo) / rng * height)
        for i, v in enumerate(vals)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = ""
    if fill:
        area = (
            f'<polygon points="0,{height} {line} {width},{height}" '
            f'fill="{color}" fill-opacity="0.12" />'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="none" style="max-width:100%">'
        f"{area}"
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" />'
        f"</svg>"
    )


def generate_report(result: BacktestResult, path: str | Path,
                    title: str = "백테스트 리포트") -> Path:
    """BacktestResult를 HTML 파일로 저장하고 경로를 반환한다."""
    m = result.metrics
    equity = result.equity
    drawdown = equity / equity.cummax() - 1.0

    rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in _metric_rows(m)
    )
    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
 .wrap{{max-width:900px;margin:0 auto;padding:24px}}
 h1{{font-size:20px}} h2{{font-size:15px;color:#475569;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;font-size:14px}}
 td{{padding:6px 10px;border-bottom:1px solid #e2e8f0}}
 td:first-child{{color:#64748b}} td:last-child{{text-align:right;font-variant-numeric:tabular-nums}}
 .card{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-top:12px}}
 .warn{{color:#b45309;font-size:13px;margin-top:20px}}
 @media(prefers-color-scheme:dark){{body{{background:#0f172a;color:#e2e8f0}}
  .card{{background:#1e293b;border-color:#334155}} td{{border-color:#334155}}}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<h2>자본곡선 (Equity Curve)</h2>
<div class="card">{_sparkline(equity, color="#2563eb")}</div>
<h2>낙폭 (Drawdown)</h2>
<div class="card">{_sparkline(drawdown, color="#dc2626")}</div>
<h2>성과 지표</h2>
<div class="card"><table>{rows}</table></div>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다. 몬테카를로 신뢰구간과
워크포워드 검증을 함께 확인하세요.</p>
</div></body></html>"""

    out = Path(path)
    out.write_text(html, encoding="utf-8")
    return out


def _metric_rows(m) -> list[tuple[str, str]]:
    return [
        ("총수익률", f"{m.total_return:.2%}"),
        ("CAGR", f"{m.cagr:.2%}"),
        ("변동성(연)", f"{m.volatility:.2%}"),
        ("샤프지수", f"{m.sharpe:.2f}"),
        ("소르티노", f"{m.sortino:.2f}"),
        ("최대낙폭", f"{m.max_drawdown:.2%}"),
        ("칼마지수", f"{m.calmar:.2f}"),
        ("승률", f"{m.win_rate:.2%}"),
        ("거래횟수", f"{m.num_trades}"),
        ("시장노출", f"{m.exposure:.2%}"),
    ]
