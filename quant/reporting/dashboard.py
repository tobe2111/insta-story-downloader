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

# ledger_basics는 표준 라이브러리만 쓴다 — 이 파일의 "의존성 0" 성질이
# 유지된다. 그 가벼움이 이 판정을 공유할 수 있게 해 준 조건이다(감사 197).
from quant.live.ledger_basics import equity_curve_kpis


def _sparkline(values: Sequence[float], width: int = 760, height: int = 180,
               color: str = "#4c7dff", fill: bool = True, elem_id: str = "") -> str:
    vals = [float(v) for v in values]
    idattr = f' id="{elem_id}"' if elem_id else ""
    if len(vals) < 2:
        return ('<svg viewBox="0 0 760 180" width="100%" height="180">'
                f'<polyline{idattr} points="" fill="none" stroke="{color}" '
                'stroke-width="2.5" /></svg>'
                '<div style="color:#8f96a3;padding:6px 0;font-size:12px">데이터 수집 중…</div>')
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
        f'<polyline{idattr} points="{line}" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linejoin="round" /></svg>'
    )


def _kpi(label: str, value: str, tone: str = "", vid: str = "") -> str:
    color = {"pos": "#3fb96f", "neg": "#e5484d", "": "var(--fg)"}[tone]
    idattr = f' id="{vid}"' if vid else ""
    return (f'<div class="kpi"><div class="kpi-label">{html.escape(label)}</div>'
            f'<div class="kpi-val"{idattr} style="color:{color}">'
            f'{html.escape(value)}</div></div>')


def generate_dashboard(state: dict, path: str | Path) -> Path:
    """트레이딩 상태 스냅샷을 HTML 대시보드로 저장하고 경로를 반환한다."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_dashboard_html(state), encoding="utf-8")
    return out


def build_dashboard_html(state: dict) -> str:
    """트레이딩 상태 스냅샷을 HTML 문자열로 렌더링한다 (파일 저장·웹 공용)."""
    history = state.get("history", [])
    equity = [h.get("equity", 0.0) for h in history]
    symbol = state.get("symbol", "-")
    strategy = state.get("strategy", "-")
    mode = state.get("mode", "paper")

    # 잘려나간 과거의 요약(fold_history) — history는 상한(HISTORY_CAP)에 걸려
    # 앞이 잘린다. 이 요약이 없으면 총손익은 '잘린 시점 이후 손익'이 되고,
    # 최대낙폭은 가장 아팠던 구간이 밀려나는 순간 저절로 좋아진다. 시간이
    # 지나면 스스로 개선되는 위험 지표는 지표가 아니라 위안이다(감사 ㊿).
    summ = state.get("history_summary") or {}
    dropped = int(summ.get("dropped") or 0)
    # 손익·낙폭 판정은 `ledger_basics.equity_curve_kpis` 한 곳에서만 한다
    # (감사 197). 예전에는 여기와 감시 탭 JS가 각자 `cur / start - 1.0`을
    # 계산했고, 둘 다 **입금을 수익으로 셌다**(실측 +1087.50%). 게다가 JS는
    # 5초마다 이 화면의 값을 덮어쓰므로, 여기만 고쳤다면 화면이 잠깐
    # 맞았다가 조용히 틀린 값으로 되돌아갔을 것이다.
    _k = equity_curve_kpis(state)
    cur, pnl, max_dd = _k["current"], _k["pnl"], _k["max_drawdown"]

    last_weight = history[-1].get("weight", 0.0) if history else 0.0
    # 방향 예측 정확도(최근 우선, 없으면 전체) — 자동학습 상태에만 존재할 수 있음
    last = history[-1] if history else {}
    acc = last.get("recent_hit_rate")
    if acc is None or acc != acc:              # None 또는 NaN이면 전체값으로
        acc = last.get("hit_rate")
    acc_txt = f"{acc:.1%}" if isinstance(acc, (int, float)) and acc == acc else "N/A"
    orders = state.get("orders", [])
    # 단일 종목("position": dict) 또는 다중 종목("positions": list) 모두 지원
    positions = state.get("positions")
    if positions is None:
        single = state.get("position", {})
        positions = [single] if single else []

    kpis = "".join([
        _kpi("총자산", f"{cur:,.2f}", vid="kpi-equity"),
        _kpi("손익 (PnL)", f"{pnl:+.2%}", "pos" if pnl >= 0 else "neg", vid="kpi-pnl"),
        _kpi("최대낙폭", f"{max_dd:.2%}", "neg" if max_dd < 0 else "", vid="kpi-dd"),
        _kpi("현재 목표비중", f"{last_weight:+.0%}", vid="kpi-weight"),
        _kpi("방향 정확도", acc_txt, vid="kpi-acc"),
        # orders는 스냅샷에 최근 20건만 실린다 — 누적 건수는 order_count.
        _kpi("거래횟수",
             f"{int(state.get('order_count', len(orders)))}", vid="kpi-trades"),
    ])

    pos_row = "".join(
        f'<tr><td>{html.escape(str(p.get("symbol", "-")))}</td>'
        f'<td>{p.get("quantity", 0):.6f}</td>'
        f'<td>{p.get("avg_price", 0):,.2f}</td></tr>'
        for p in positions if p
    ) or '<tr><td colspan="3" style="color:var(--muted)">보유 포지션 없음</td></tr>'

    order_rows = "".join(
        f'<tr><td>{html.escape(str(o.get("side","")).upper())}</td>'
        f'<td>{html.escape(str(o.get("symbol","")))}</td>'
        f'<td>{o.get("quantity",0):.6f}</td>'
        f'<td>{o.get("price",0):,.2f}</td>'
        f'<td>{html.escape(str(o.get("status","")))}</td></tr>'
        for o in reversed(orders[-15:])
    ) or '<tr><td colspan="5" style="color:var(--muted)">주문 내역 없음</td></tr>'

    mode_badge = ('<span class="badge live">실거래</span>' if mode != "paper"
                  else '<span class="badge">페이퍼</span>')

    # 그래프에는 최근 구간만 그려진다는 사실을 숨기지 않는다 — KPI(손익·낙폭)는
    # 전 기간 기준이고 그래프만 잘려 있다는 차이를 화면에 적어 둔다.
    chart_note = ""
    if dropped:
        chart_note = (f'<div style="color:var(--muted);font-size:11.5px;'
                      f'padding-top:6px">그래프는 최근 {len(equity):,}개 시점만 '
                      f'표시합니다(앞의 {dropped:,}개는 저장 상한으로 생략). '
                      f'위의 손익·최대낙폭은 전 기간 기준입니다.</div>')

    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>퀀트 라이브 모니터 · {html.escape(symbol)}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E%3Crect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%234c7dff%22/%3E%3Cpath d=%22M8 22 L14 14 L18 18 L24 9%22 stroke=%22white%22 stroke-width=%223%22 fill=%22none%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22/%3E%3C/svg%3E">
<style>
 :root{{color-scheme:dark;
   --bg:#0a0b0e;--card:#0e1013;--fg:#f4f5f7;--muted:#8f96a3;--line:#1e2128;
   --line-strong:#2a2e37;--accent:#4c7dff;--ok:#3fb96f;--bad:#e5484d;--warn:#d9a13b}}
 @media(prefers-color-scheme:light){{:root{{color-scheme:light;
   --bg:#fcfcfd;--card:#f4f5f8;--fg:#101318;
   --muted:#5a626e;--line:#e7e9ee;--line-strong:#d8dbe2;--accent:#2f5fe0}}}}
 *{{box-sizing:border-box;min-width:0}} body{{margin:0;background:var(--bg);color:var(--fg);
   font-family:"Pretendard Variable",Pretendard,-apple-system,system-ui,"Segoe UI",
   "Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.6;
   -webkit-font-smoothing:antialiased}}
 .wrap{{max-width:960px;margin:0 auto;padding:20px}}
 nav{{display:flex;align-items:center;gap:2px;margin:0 0 14px;padding:0 0 10px;font-size:13px;
   overflow-x:auto;border-bottom:1px solid var(--line)}}
 nav .logo{{font-weight:800;font-size:13.5px;letter-spacing:.12em;color:var(--fg);
   margin-right:14px;white-space:nowrap}}
 nav .logo em{{font-style:normal;color:var(--accent)}}
 nav a{{white-space:nowrap;padding:6px 10px;border-radius:7px;font-weight:550;
   color:var(--muted);text-decoration:none;transition:background .15s,color .15s}}
 nav a:hover{{background:var(--card);color:var(--fg)}}
 header{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
 h1{{font-size:18px;margin:0;font-weight:750;letter-spacing:-.02em}}
 .sub{{color:var(--muted);font-size:13px}}
 .badge{{margin-left:auto;font-size:11.5px;font-weight:600;padding:4px 12px;
   color:var(--muted);border:1px solid var(--line-strong);border-radius:999px}}
 .badge.live{{color:var(--bad);border-color:var(--bad)}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;
   background:var(--line);border:1px solid var(--line);border-radius:12px;
   overflow:hidden;margin-bottom:16px}}
 .kpi{{background:var(--card);padding:14px 16px}}
 .kpi-label{{color:var(--muted);font-size:11.5px;margin-bottom:5px;font-weight:600}}
 .kpi-val{{font-size:21px;font-weight:750;letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
 .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}}
 .card h2{{font-size:11.5px;color:var(--muted);margin:0 0 10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th,td{{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}}
 th{{color:var(--muted);font-weight:600}} .foot{{color:var(--warn);font-size:12px}}
 .over{{overflow-x:auto}}
</style></head><body><div class="wrap">
<header>
  <h1>퀀트 라이브 모니터</h1>
  <span class="sub">{html.escape(symbol)} · {html.escape(strategy)} 전략</span>
  {mode_badge}
</header>
<div class="kpis">{kpis}</div>
<div class="card"><h2>자본 추이 (Equity)</h2>{_sparkline(equity, color="#3fb96f" if pnl>=0 else "#e5484d", elem_id="eqline")}{chart_note}</div>
<div class="card"><h2>현재 포지션</h2><div class="over"><table>
  <tr><th>종목</th><th>수량</th><th>평균단가</th></tr>
  <tbody id="pos-body">{pos_row}</tbody></table></div></div>
<div class="card"><h2>최근 주문</h2><div class="over"><table>
  <tr><th>방향</th><th>종목</th><th>수량</th><th>체결가</th><th>상태</th></tr>
  <tbody id="ord-body">{order_rows}</tbody></table></div></div>
<p class="foot">⚠️ 30초마다 자동 새로고침. 과거·현재 성과는 미래 수익을 보장하지 않습니다.</p>
</div></body></html>"""
    return doc
