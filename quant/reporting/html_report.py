"""백테스트 결과를 자체 완결형 HTML 리포트로 저장한다 (외부 라이브러리 불필요).

자본곡선과 낙폭(drawdown)을 인라인 SVG로 그리므로 matplotlib 없이도 동작한다.
브라우저로 열면 성과 지표와 차트를 한눈에 볼 수 있다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
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


def _overlay(strategy: pd.Series, benchmark: pd.Series,
             width: int = 800, height: int = 200) -> str:
    """전략 자본곡선과 벤치마크를 같은 축에 겹쳐 그린다 (공유 스케일)."""
    a = strategy.to_numpy(dtype=float)
    b = benchmark.to_numpy(dtype=float)
    if len(a) < 2:
        return "<svg></svg>"
    lo = min(float(a.min()), float(b.min()))
    hi = max(float(a.max()), float(b.max()))
    rng = hi - lo or 1.0

    def _poly(vals):
        n = len(vals)
        return " ".join(
            f"{i / (n - 1) * width:.1f},{height - (v - lo) / rng * height:.1f}"
            for i, v in enumerate(vals)
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="none" style="max-width:100%">'
        f'<polyline points="{_poly(b)}" fill="none" stroke="#94a3b8" '
        f'stroke-width="1.5" stroke-dasharray="5 4" />'
        f'<polyline points="{_poly(a)}" fill="none" stroke="#2563eb" '
        f'stroke-width="2" /></svg>'
    )


def _price_marker_chart(df, positions, width: int = 760, height: int = 200) -> str:
    """가격 곡선 위에 매매 시점(🟢진입 / 🔴청산) 마커를 그린다."""
    close = df["close"].to_numpy(dtype=float)
    pos = positions.reindex(df.index).fillna(0.0).to_numpy()
    n = len(close)
    if n < 2:
        return "<svg></svg>"
    lo, hi = float(close.min()), float(close.max())
    rng = (hi - lo) or 1.0

    def _x(i):
        return i / (n - 1) * width

    def _y(i):
        return height - (close[i] - lo) / rng * height

    line = " ".join(f"{_x(i):.1f},{_y(i):.1f}" for i in range(n))
    markers = []
    for i in range(1, n):
        prev, cur = pos[i - 1], pos[i]
        if cur != 0 and prev == 0:            # 신규 진입
            markers.append(f'<circle cx="{_x(i):.1f}" cy="{_y(i):.1f}" r="3.2" '
                           'fill="#16a34a" />')
        elif cur == 0 and prev != 0:          # 청산
            markers.append(f'<circle cx="{_x(i):.1f}" cy="{_y(i):.1f}" r="3.2" '
                           'fill="#dc2626" />')
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'preserveAspectRatio="none"><polyline points="{line}" fill="none" '
        f'stroke="#64748b" stroke-width="1.4" />{"".join(markers)}</svg>'
    )


def generate_report(result: BacktestResult, path: str | Path,
                    title: str = "백테스트 리포트") -> Path:
    """BacktestResult를 HTML 파일로 저장하고 경로를 반환한다."""
    out = Path(path)
    out.write_text(build_report_html(result, title), encoding="utf-8")
    return out


def build_report_html(result: BacktestResult, title: str = "백테스트 리포트") -> str:
    """BacktestResult를 HTML 문자열로 렌더링한다 (웹서버·파일 저장 공용)."""
    m = result.metrics
    equity = result.equity
    drawdown = equity / equity.cummax() - 1.0

    if result.benchmark is not None:
        equity_svg = _overlay(equity, result.benchmark)
        legend = ('<p style="font-size:12px;color:#64748b;margin:8px 0 0">'
                  '<span style="color:#2563eb">━</span> 전략   '
                  '<span style="color:#94a3b8">╌</span> 매수후보유</p>')
    else:
        equity_svg = _sparkline(equity, color="#2563eb")
        legend = ""

    metric_rows = _metric_rows(m)
    if result.benchmark is not None:
        verdict = "초과 ✅" if result.excess_return >= 0 else "하회 ⚠️"
        metric_rows += [
            ("매수후보유", f"{result.benchmark_return:.2%}"),
            ("초과수익", f"{result.excess_return:.2%}  {verdict}"),
        ]
    rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in metric_rows
    )

    # 거래 단위 통계 (기대값 등)
    ts = result.trade_stats()
    tpf = "∞" if not np.isfinite(ts["profit_factor"]) else f"{ts['profit_factor']:.2f}"
    trade_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in [
        ("거래횟수", f"{ts['num_trades']}"),
        ("거래 승률", f"{ts['win_rate']:.2%}"),
        ("평균 이익", f"{ts['avg_win']:.2%}"),
        ("평균 손실", f"{ts['avg_loss']:.2%}"),
        ("기대값(거래당)", f"{ts['expectancy']:.2%}"),
        ("거래 이익팩터", tpf),
        ("평균 보유(봉)", f"{ts['avg_bars_held']:.1f}"),
    ])
    price_chart = _price_marker_chart(result.df, result.positions)
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
<div class="card">{equity_svg}{legend}</div>
<h2>가격 & 매매 시점</h2>
<div class="card">{price_chart}
<p style="font-size:12px;color:#64748b;margin:8px 0 0">
<span style="color:#16a34a">●</span> 진입   <span style="color:#dc2626">●</span> 청산</p></div>
<h2>낙폭 (Drawdown)</h2>
<div class="card">{_sparkline(drawdown, color="#dc2626")}</div>
<h2>성과 지표</h2>
<div class="card"><table>{rows}</table></div>
<h2>거래 통계 (Trade-level)</h2>
<div class="card"><table>{trade_rows}</table></div>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다. 몬테카를로 신뢰구간과
워크포워드 검증을 함께 확인하세요.</p>
</div></body></html>"""
    return html


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
        ("이익팩터", "∞" if not np.isfinite(m.profit_factor) else f"{m.profit_factor:.2f}"),
        ("거래횟수", f"{m.num_trades}"),
        ("시장노출", f"{m.exposure:.2%}"),
    ]
