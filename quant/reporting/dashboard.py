"""라이브 모니터링 대시보드 생성기 (순수 표준 라이브러리, 의존성 0).

실시간 트레이딩 상태(state) 스냅샷을 받아 자체 완결형 HTML 대시보드로
렌더링한다. 자본 추이, 손익, 현재 포지션, 최근 주문을 한눈에 보여준다.
pandas/numpy가 없어도 동작하므로 가벼운 모니터링 서버에서도 쓸 수 있다.

state 형식(quant.live.LiveTrader.snapshot() 참고):
    {
      "symbol": "BTC/USDT", "strategy": "ensemble", "mode": "paper",
      "history": [{"time": "...", "price": 1.0, "weight": 0.5, "equity": 10000.0}, ...],
      "position": {"symbol": "...", "quantity": 0.1, "avg_price": 100.0},
      "orders": [{"symbol": "...", "side": "buy", "quantity": 1.0, "price": 100.0, "status": "filled"}, ...]
    }
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Sequence


def _sparkline(values: Sequence[float], width: int = 760, height: int = 180,
               color: str = "#2563eb", fill: bool = True) -> str:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return '<div style="color:#94a3b8;padding:24px 0">데이터 수집 중…</div>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = [
        (i / (n - 1) * width, height - (v - lo) / rng * height)
        for i, v in enumerate(vals)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = ""
    if fill:
        area = (f'<polygon points="0,{height} {line} {width},{height}" '
                f'fill="{color}" fill-opacity="0.12" />')
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'preserveAspectRatio="none">{area}'
        f'<polyline points="{line}" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linejoin="round" /></svg>'
    )


def _kpi(label: str, value: str, tone: str = "") -> str:
    color = {"pos": "#16a34a", "neg": "#dc2626", "": "var(--fg)"}[tone]
    return (f'<div class="kpi"><div class="kpi-label">{html.escape(label)}</div>'
            f'<div class="kpi-val" style="color:{color}">{html.escape(value)}</div></div>')


def generate_dashboard(state: dict, path: str | Path) -> Path:
    """트레이딩 상태 스냅샷을 HTML 대시보드로 저장하고 경로를 반환한다."""
    history = state.get("history", [])
    equity = [h.get("equity", 0.0) for h in history]
    symbol = state.get("symbol", "-")
    strategy = state.get("strategy", "-")
    mode = state.get("mode", "paper")

    if equity:
        start, cur = equity[0], equity[-1]
        pnl = cur / start - 1.0 if start else 0.0
        peak = start
        max_dd = 0.0
        for e in equity:
            peak = max(peak, e)
            max_dd = min(max_dd, e / peak - 1.0 if peak else 0.0)
    else:
        cur = pnl = max_dd = 0.0

    last_weight = history[-1].get("weight", 0.0) if history else 0.0
    orders = state.get("orders", [])
    pos = state.get("position", {})

    kpis = "".join([
        _kpi("총자산", f"{cur:,.2f}"),
        _kpi("손익 (PnL)", f"{pnl:+.2%}", "pos" if pnl >= 0 else "neg"),
        _kpi("최대낙폭", f"{max_dd:.2%}", "neg" if max_dd < 0 else ""),
        _kpi("현재 목표비중", f"{last_weight:+.0%}"),
        _kpi("거래횟수", f"{len(orders)}"),
    ])

    pos_row = (
        f'<tr><td>{html.escape(str(pos.get("symbol", "-")))}</td>'
        f'<td>{pos.get("quantity", 0):.6f}</td>'
        f'<td>{pos.get("avg_price", 0):,.2f}</td></tr>'
    ) if pos else '<tr><td colspan="3" style="color:#94a3b8">보유 포지션 없음</td></tr>'

    order_rows = "".join(
        f'<tr><td>{html.escape(str(o.get("side","")).upper())}</td>'
        f'<td>{html.escape(str(o.get("symbol","")))}</td>'
        f'<td>{o.get("quantity",0):.6f}</td>'
        f'<td>{o.get("price",0):,.2f}</td>'
        f'<td>{html.escape(str(o.get("status","")))}</td></tr>'
        for o in reversed(orders[-15:])
    ) or '<tr><td colspan="5" style="color:#94a3b8">주문 내역 없음</td></tr>'

    mode_badge = ("🔴 실거래" if mode != "paper" else "📝 페이퍼")

    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>퀀트 라이브 모니터 · {html.escape(symbol)}</title>
<style>
 :root{{--bg:#f1f5f9;--card:#fff;--fg:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb}}
 @media(prefers-color-scheme:dark){{:root{{--bg:#0b1220;--card:#111c30;--fg:#e2e8f0;--muted:#94a3b8;--line:#243244;--accent:#60a5fa}}}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);
   font-family:system-ui,-apple-system,'Segoe UI',sans-serif}}
 .wrap{{max-width:960px;margin:0 auto;padding:20px}}
 header{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
 h1{{font-size:19px;margin:0}} .sub{{color:var(--muted);font-size:13px}}
 .badge{{margin-left:auto;font-size:12px;padding:4px 10px;border:1px solid var(--line);border-radius:999px}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}}
 .kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
 .kpi-label{{color:var(--muted);font-size:12px;margin-bottom:6px}}
 .kpi-val{{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}}
 .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}}
 .card h2{{font-size:13px;color:var(--muted);margin:0 0 10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th,td{{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}}
 th{{color:var(--muted);font-weight:600}} .foot{{color:#b45309;font-size:12px}}
 .over{{overflow-x:auto}}
</style></head><body><div class="wrap">
<header>
  <h1>퀀트 라이브 모니터</h1>
  <span class="sub">{html.escape(symbol)} · {html.escape(strategy)} 전략</span>
  <span class="badge">{mode_badge}</span>
</header>
<div class="kpis">{kpis}</div>
<div class="card"><h2>자본 추이 (Equity)</h2>{_sparkline(equity, color="#16a34a" if pnl>=0 else "#dc2626")}</div>
<div class="card"><h2>현재 포지션</h2><div class="over"><table>
  <tr><th>종목</th><th>수량</th><th>평균단가</th></tr>{pos_row}</table></div></div>
<div class="card"><h2>최근 주문</h2><div class="over"><table>
  <tr><th>방향</th><th>종목</th><th>수량</th><th>체결가</th><th>상태</th></tr>{order_rows}</table></div></div>
<p class="foot">⚠️ 30초마다 자동 새로고침. 과거·현재 성과는 미래 수익을 보장하지 않습니다.</p>
</div></body></html>"""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
