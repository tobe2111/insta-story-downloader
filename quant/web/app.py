"""웹 UI의 페이지 렌더링/요청 처리 로직 (표준 라이브러리만 사용).

무거운 quant/pandas 임포트는 백테스트를 실제로 실행할 때만(지연 임포트) 일어나므로,
폼 페이지 자체는 pandas 없이도 렌더링·테스트할 수 있다.
"""
from __future__ import annotations

import html

# 폼 셀렉트용 (pandas 임포트를 피하려고 하드코딩; strategies 레지스트리와 일치)
STRATEGIES = ["ma_cross", "momentum", "mean_reversion", "rsi", "breakout",
              "macd", "keltner", "stochastic", "ml", "ensemble"]
MARKETS = ["synthetic", "crypto", "us_stock", "kr_stock"]

_STYLE = """
 body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#0b1220;color:#e2e8f0}
 @media(prefers-color-scheme:light){body{background:#f8fafc;color:#0f172a}}
 .wrap{max-width:720px;margin:0 auto;padding:28px}
 h1{font-size:20px} label{display:block;margin:14px 0 4px;font-size:13px;color:#94a3b8}
 input,select{width:100%;padding:9px 10px;border-radius:8px;border:1px solid #334155;
   background:transparent;color:inherit;font-size:14px}
 button{margin-top:20px;padding:11px 18px;border:0;border-radius:8px;background:#2563eb;
   color:#fff;font-size:14px;font-weight:600;cursor:pointer}
 .row{display:flex;gap:12px}.row>div{flex:1}
 .warn{color:#b45309;font-size:12px;margin-top:20px}
 a{color:#60a5fa}
 nav{display:flex;gap:16px;margin-bottom:18px;font-size:14px;
   border-bottom:1px solid #334155;padding-bottom:10px}
 nav a{text-decoration:none;font-weight:600}
"""

_NAV = ('<nav><a href="/">📊 백테스트</a>'
        '<a href="/portfolio">📦 포트폴리오</a>'
        '<a href="/sweep">🔥 민감도 스윕</a>'
        '<a href="/optimize">⚙️ 최적화</a>'
        '<a href="/monitor">📺 감시</a></nav>')

ALLOCATIONS = ["inverse_vol", "equal"]

# 워크포워드 최적화가 지원하는 전략과 파라미터 격자
_OPT_GRIDS = {
    "ma_cross": {"fast": [5, 10, 20], "slow": [40, 60, 120]},
    "momentum": {"lookback": [30, 60, 90, 120]},
    "rsi": {"period": [7, 14, 21]},
    "mean_reversion": {"window": [10, 20, 30], "z": [1.5, 2.0, 2.5]},
    "macd": {"fast": [8, 12], "slow": [21, 26]},
    "keltner": {"ema_window": [10, 20], "atr_window": [10, 14], "mult": [1.5, 2.0, 2.5]},
    "stochastic": {"k_period": [10, 14], "oversold": [20, 25], "overbought": [75, 80]},
    "ml": {"model": ["logreg", "gb"], "threshold": [0.53, 0.57]},
}


def render_form(message: str = "") -> str:
    """백테스트 실행 폼 페이지를 반환한다 (pandas 불필요)."""
    strat_opts = "".join(f'<option value="{s}">{s}</option>' for s in STRATEGIES)
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 백테스트</title><style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>📈 Quant 백테스트</h1>
<p style="color:#94a3b8;font-size:13px">시장·종목·전략을 고르고 실행하면 성과 리포트가 나옵니다.</p>
{msg}
<form action="/backtest" method="get">
  <div class="row">
    <div><label>시장</label><select name="market">{market_opts}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT"></div>
  </div>
  <div class="row">
    <div><label>전략</label><select name="strategy">{strat_opts}</select></div>
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="500"></div>
  </div>
  <button type="submit">백테스트 실행</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다. 실거래 전 반드시 검증하세요.</p>
</div></body></html>"""


def run_backtest_html(params: dict) -> str:
    """폼 파라미터로 백테스트를 실행하고 리포트 HTML을 반환한다 (pandas 필요)."""
    # 지연 임포트 — 폼 렌더링 경로가 pandas에 의존하지 않도록
    from quant.backtest import Backtester
    from quant.data import get_provider
    from quant.reporting import build_report_html
    from quant.strategies import default_ensemble, get_strategy

    market = params.get("market", "synthetic")
    symbol = params.get("symbol", "DEMO")
    timeframe = params.get("timeframe", "1d")
    strategy_name = params.get("strategy", "ma_cross")
    try:
        limit = max(50, min(5000, int(params.get("limit", 500))))
    except (TypeError, ValueError):
        limit = 500

    ppy = 365 if market in ("crypto", "synthetic") else 252
    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=limit)
    strategy = default_ensemble() if strategy_name == "ensemble" \
        else get_strategy(strategy_name)
    result = Backtester(strategy, periods_per_year=ppy).run(df)

    body = build_report_html(result, title=f"{strategy_name} · {symbol}")
    body = body.replace("<h1>", _NAV + "\n<h1>", 1)   # 상단 네비게이션
    # "이게 운인가?" 분석(몬테카를로 신뢰구간 + 확률적 샤프)을 리포트에 주입
    robustness = _robustness_html(result.returns, ppy)
    return body.replace("</div></body>", robustness + "</div></body>", 1)


def _robustness_html(returns, ppy: int) -> str:
    """몬테카를로 신뢰구간 + PSR 카드 HTML (실패 시 빈 문자열)."""
    try:
        from quant.robustness import (
            bootstrap_metrics,
            probabilistic_sharpe_ratio,
            summarize,
        )
        dist = bootstrap_metrics(returns, n_sims=500, periods_per_year=ppy)
        psr = probabilistic_sharpe_ratio(returns, 0.0)
    except Exception:  # noqa: BLE001
        return ""
    verdict = ("높음 ✅" if psr >= 0.95 else "보통 ⚠️" if psr >= 0.75 else "낮음 🚨")
    table = html.escape(summarize(dist))
    return (
        '<h2>이게 운인가? (신뢰도 분석)</h2>'
        '<div class="card">'
        f'<p style="font-size:13px">참 샤프가 0보다 클 확률 (PSR): '
        f'<b>{psr:.1%}</b> — 신뢰도 {verdict}</p>'
        f'<pre style="font-size:12px;overflow-x:auto;white-space:pre">{table}</pre>'
        '<p style="font-size:12px;color:#94a3b8">신뢰구간 하단(5%)이 0 근처거나 '
        'PSR이 낮으면 이 성과는 운일 수 있습니다.</p></div>'
    )


# 실시간: /api/state를 주기적으로 폴링해 페이지 새로고침 없이 전 요소 갱신
_MONITOR_JS = """<script>
function _esc(s){const d=document.createElement('div');d.textContent=String(s==null?'':s);return d.innerHTML;}
function _num(v,f){return (Number(v)||0).toLocaleString(undefined,{minimumFractionDigits:f,maximumFractionDigits:f});}
async function _tick(){
  try{
    const r = await fetch('/api/state', {cache:'no-store'});
    if(!r.ok) return;
    const s = await r.json();
    const h = (s && s.history) || [];
    const eq = h.map(x => (x.equity||0));
    if(eq.length >= 2){
      const W=760,H=180, lo=Math.min(...eq), hi=Math.max(...eq), rng=(hi-lo)||1;
      const pts = eq.map((v,i)=>`${(i/(eq.length-1)*W).toFixed(1)},${(H-(v-lo)/rng*H).toFixed(1)}`).join(' ');
      const line = document.getElementById('eqline'); if(line) line.setAttribute('points', pts);
      const cur=eq[eq.length-1], st=eq[0], pnl=st? cur/st-1:0;
      let peak=st, dd=0; for(const v of eq){ peak=Math.max(peak,v); dd=Math.min(dd, peak? v/peak-1:0); }
      const setTxt=(id,txt,col)=>{const el=document.getElementById(id); if(el){el.textContent=txt; if(col)el.style.color=col;}};
      setTxt('kpi-equity', _num(cur,2));
      setTxt('kpi-pnl', (pnl>=0?'+':'')+(pnl*100).toFixed(2)+'%', pnl>=0?'#16a34a':'#dc2626');
      setTxt('kpi-dd', (dd*100).toFixed(2)+'%');
      const lw=(h[h.length-1]||{}).weight||0; setTxt('kpi-weight', (lw>=0?'+':'')+Math.round(lw*100)+'%');
    }
    // 방향 예측 정확도(최근 우선) — 자동학습 상태에 존재
    const last = h[h.length-1] || {};
    let acc = last.recent_hit_rate;
    if(acc==null || isNaN(acc)) acc = last.hit_rate;
    setTxtSafe('kpi-acc', (acc==null||isNaN(acc))?'N/A':(acc*100).toFixed(1)+'%');
    const orders = (s && s.orders) || [];
    setTxtSafe('kpi-trades', String(orders.length));
    // 포지션 테이블 재구성
    const pos = (s && (s.positions || (s.position? [s.position]:[]))) || [];
    const pb=document.getElementById('pos-body');
    if(pb){ pb.innerHTML = pos.filter(p=>p&&p.quantity).map(p=>
      `<tr><td>${_esc(p.symbol)}</td><td>${_num(p.quantity,6)}</td><td>${_num(p.avg_price,2)}</td></tr>`).join('')
      || '<tr><td colspan="3" style="color:#94a3b8">보유 포지션 없음</td></tr>'; }
    // 주문 테이블 재구성 (최근 15건)
    const ob=document.getElementById('ord-body');
    if(ob){ ob.innerHTML = orders.slice(-15).reverse().map(o=>
      `<tr><td>${_esc((o.side||'').toUpperCase())}</td><td>${_esc(o.symbol)}</td><td>${_num(o.quantity,6)}</td><td>${_num(o.price,2)}</td><td>${_esc(o.status)}</td></tr>`).join('')
      || '<tr><td colspan="5" style="color:#94a3b8">주문 내역 없음</td></tr>'; }
    const t=document.getElementById('rt-time'); if(t) t.textContent = new Date().toLocaleTimeString();
  }catch(e){}
}
function setTxtSafe(id,txt){const el=document.getElementById(id); if(el) el.textContent=txt;}
setInterval(_tick, 5000); _tick();
</script>"""


def read_state(state_paths=None):
    """봇 상태 파일을 읽어 dict로 반환한다 (없으면 None). pandas 불필요."""
    import json
    from pathlib import Path

    candidates = state_paths or ["results/multi_state.json", "results/state.json"]
    for p in candidates:
        fp = Path(p)
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return None


def state_json(state_paths=None) -> str:
    """현재 봇 상태를 JSON 문자열로 반환한다 (/api/state 용). 없으면 '{}'."""
    import json

    return json.dumps(read_state(state_paths) or {}, ensure_ascii=False)


def render_monitor(state_paths=None) -> str:
    """실행 중인 봇의 상태(state.json)를 읽어 감시 대시보드를 렌더한다 (pandas 불필요).

    차트는 /api/state를 5초마다 폴링해 페이지 새로고침 없이 갱신된다.
    """
    from quant.reporting import build_dashboard_html

    state = read_state(state_paths)

    if state is None:
        return (f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 감시</title><style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>📺 봇 감시</h1>
<p style="color:#94a3b8;font-size:14px">실행 중인 페이퍼/실거래 세션이 없습니다.</p>
<p style="font-size:13px">먼저 봇을 실행하세요:</p>
<pre style="font-size:12px">python examples/run_live.py --paper --market crypto --symbol BTC/USDT</pre>
<p style="font-size:13px;color:#94a3b8">봇이 <code>results/state.json</code>을 쓰면
이 페이지에 자산·포지션·주문이 나타납니다.</p>
</div></body></html>""")

    doc = build_dashboard_html(state)
    doc = doc.replace("<header>", _NAV + "\n<header>", 1)  # 조종석 네비게이션
    # 페이지 전체 새로고침(meta refresh) 제거 → JS로 부드럽게 실시간 갱신
    doc = doc.replace('<meta http-equiv="refresh" content="30">', "")
    doc = doc.replace(
        "</header>",
        '</header><p class="sub" style="font-size:12px;color:#94a3b8">'
        '🟢 실시간 (5초 갱신) · 마지막: <span id="rt-time">—</span></p>', 1)
    return doc.replace("</body>", _MONITOR_JS + "</body>", 1)


def render_portfolio_form(message: str = "") -> str:
    """다중 종목 포트폴리오 백테스트 폼 (pandas 불필요)."""
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    strat_opts = "".join(f'<option value="{s}">{s}</option>' for s in STRATEGIES)
    alloc_opts = "".join(f'<option value="{a}">{a}</option>' for a in ALLOCATIONS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 포트폴리오</title><style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>📦 포트폴리오 백테스트</h1>
<p style="color:#94a3b8;font-size:13px">여러 종목에 분산투자해 변동성을 낮춥니다.
종목은 쉼표로 구분하세요.</p>
{msg}
<form action="/portfolio/run" method="get">
  <div class="row">
    <div><label>시장</label><select name="market">{market_opts}</select></div>
    <div><label>종목 (쉼표 구분)</label><input name="symbols" value="BTC/USDT, ETH/USDT, SOL/USDT"></div>
  </div>
  <div class="row">
    <div><label>전략</label><select name="strategy">{strat_opts}</select></div>
    <div><label>배분 방식</label><select name="allocation">{alloc_opts}</select></div>
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="500"></div>
  </div>
  <button type="submit">포트폴리오 백테스트</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.</p>
</div></body></html>"""


def run_portfolio_html(params: dict) -> str:
    """다중 종목 포트폴리오 백테스트를 실행하고 리포트 HTML을 반환한다 (pandas 필요)."""
    market = params.get("market", "synthetic")
    raw = params.get("symbols", "A, B, C")
    symbols = [s.strip() for s in raw.split(",") if s.strip()]
    timeframe = params.get("timeframe", "1d")
    strategy_name = params.get("strategy", "momentum")
    allocation = params.get("allocation", "inverse_vol")
    try:
        limit = max(50, min(5000, int(params.get("limit", 500))))
    except (TypeError, ValueError):
        limit = 500
    if not symbols:
        return render_portfolio_form("종목을 하나 이상 입력하세요.")

    # 유효 입력 확인 후에만 무거운(pandas) 모듈을 임포트
    from quant.data import get_provider
    from quant.portfolio import PortfolioBacktester
    from quant.reporting import build_report_html
    from quant.strategies import default_ensemble, get_strategy

    ppy = 365 if market in ("crypto", "synthetic") else 252
    provider = get_provider(market)
    data = {s: provider.get_ohlcv(s, timeframe, limit=limit) for s in symbols}
    strategy = default_ensemble() if strategy_name == "ensemble" \
        else get_strategy(strategy_name)
    result = PortfolioBacktester(
        strategy=strategy, allocation=allocation, periods_per_year=ppy).run(data)

    body = build_report_html(result, title=f"포트폴리오 · {len(symbols)}종목 ({allocation})")
    return body.replace("<h1>", _NAV + "\n<h1>", 1)


def render_optimize_form(message: str = "") -> str:
    """워크포워드 최적화 폼 (pandas 불필요)."""
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    strat_opts = "".join(f'<option value="{s}">{s}</option>' for s in _OPT_GRIDS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 최적화</title><style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>⚙️ 워크포워드 최적화</h1>
<p style="color:#94a3b8;font-size:13px">과거 구간(IS)에서 최적 파라미터를 찾고,
<b>보지 않은 미래 구간(OOS)</b>에서 검증합니다. IS와 OOS 성적 격차가 크면 과최적화예요.</p>
{msg}
<form action="/optimize/run" method="get">
  <div class="row">
    <div><label>시장</label><select name="market">{market_opts}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT"></div>
    <div><label>전략</label><select name="strategy">{strat_opts}</select></div>
  </div>
  <div class="row">
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="800"></div>
    <div><label>학습(IS) 길이</label><input name="is_window" value="250"></div>
    <div><label>검증(OOS) 길이</label><input name="oos_window" value="125"></div>
  </div>
  <button type="submit">최적화 실행</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.</p>
</div></body></html>"""


def run_optimize_html(params: dict) -> str:
    """워크포워드 최적화를 실행하고 IS vs OOS 비교 HTML을 반환한다 (pandas 필요)."""
    market = params.get("market", "synthetic")
    symbol = params.get("symbol", "DEMO")
    timeframe = params.get("timeframe", "1d")
    strategy_name = params.get("strategy", "ma_cross")
    objective = "sharpe"
    if strategy_name not in _OPT_GRIDS:
        return render_optimize_form(f"'{strategy_name}'는 최적화 미지원 전략입니다.")
    try:
        limit = max(200, min(5000, int(params.get("limit", 800))))
        is_window = max(50, int(params.get("is_window", 250)))
        oos_window = max(20, int(params.get("oos_window", 125)))
    except (TypeError, ValueError):
        limit, is_window, oos_window = 800, 250, 125

    from quant.data import get_provider
    from quant.optimize import grid_search, walk_forward
    from quant.strategies import (
        MACD,
        KeltnerBreakout,
        MeanReversion,
        MLStrategy,
        Momentum,
        MovingAverageCross,
        RSIReversion,
        Stochastic,
    )

    classes = {"ma_cross": MovingAverageCross, "momentum": Momentum,
               "rsi": RSIReversion, "mean_reversion": MeanReversion, "macd": MACD,
               "keltner": KeltnerBreakout, "stochastic": Stochastic, "ml": MLStrategy}
    cls = classes[strategy_name]
    grid = _OPT_GRIDS[strategy_name]
    ppy = 365 if market in ("crypto", "synthetic") else 252
    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=limit)

    if is_window + oos_window > len(df):
        return render_optimize_form(
            f"데이터({len(df)}봉)가 IS+OOS({is_window + oos_window})보다 짧습니다.")

    gs = grid_search(df, cls, grid, objective=objective, periods_per_year=ppy)
    wf = walk_forward(df, cls, grid, is_window=is_window, oos_window=oos_window,
                      objective=objective, periods_per_year=ppy)
    m = wf["oos_metrics"]

    is_sharpe = gs["best_score"]
    oos_sharpe = m.sharpe
    if oos_sharpe >= is_sharpe * 0.6:
        verdict = ("<b style='color:#16a34a'>✅ 견고</b> — OOS가 IS와 비슷하게 유지됨")
    elif oos_sharpe > 0:
        verdict = ("<b style='color:#b45309'>⚠️ 주의</b> — OOS가 IS보다 크게 낮음 "
                   "(과최적화 가능성)")
    else:
        verdict = ("<b style='color:#dc2626'>🚨 과최적화</b> — OOS 성적이 무너짐. "
                   "이 전략은 실전에서 위험")

    seg_rows = "".join(
        f"<tr><td>{html.escape(seg['oos_start'][:10])}</td>"
        f"<td>{html.escape(str(seg['params']))}</td>"
        f"<td>{seg['is_sharpe']}</td><td>{seg['oos_sharpe']}</td>"
        f"<td>{seg['oos_return']:+.2%}</td></tr>"
        for seg in wf["segments"]
    ) or '<tr><td colspan="5" style="color:#94a3b8">검증 구간 없음</td></tr>'

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 최적화 결과</title><style>{_STYLE}
 table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}}
 th,td{{padding:6px 8px;border-bottom:1px solid #334155;text-align:left}}
 .box{{background:#111c30;border:1px solid #334155;border-radius:10px;padding:16px;margin-top:14px}}
 @media(prefers-color-scheme:light){{.box{{background:#fff}}}}
</style></head><body><div class="wrap">
{_NAV}
<h1>⚙️ 워크포워드 결과 · {html.escape(strategy_name)} · {html.escape(symbol)}</h1>
<div class="box">
<p>IS(학습) 샤프: <b>{is_sharpe:.2f}</b> → OOS(검증) 샤프: <b>{oos_sharpe:.2f}</b></p>
<p>판정: {verdict}</p>
</div>
<div class="box">
<b>OOS(진짜 성과) 지표</b>
<pre style="font-size:12px;white-space:pre;overflow-x:auto">{html.escape(m.pretty())}</pre>
</div>
<div class="box">
<b>구간별 (IS 최적 파라미터 → OOS 성적)</b>
<div style="overflow-x:auto"><table>
<tr><th>OOS 시작</th><th>파라미터</th><th>IS샤프</th><th>OOS샤프</th><th>OOS수익</th></tr>
{seg_rows}</table></div>
</div>
<p class="warn">⚠️ OOS(보지 않은 미래) 성적이 실전에서 기대할 수 있는 진짜 성과에 가깝습니다.
IS만 화려하면 그 전략은 과최적화된 것입니다.</p>
</div></body></html>"""


def render_sweep_form(message: str = "") -> str:
    """파라미터 민감도 스윕 폼 페이지 (pandas 불필요)."""
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 민감도 스윕</title><style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>🔥 파라미터 민감도 히트맵</h1>
<p style="color:#94a3b8;font-size:13px">이동평균 교차(단기×장기)의 성과 지형을 그립니다.
넓은 초록 고원=견고, 외딴 점=과최적화.</p>
{msg}
<form action="/sweep/run" method="get">
  <div class="row">
    <div><label>시장</label><select name="market">{market_opts}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT"></div>
  </div>
  <div class="row">
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="800"></div>
    <div><label>목표 지표</label><input name="objective" value="sharpe"></div>
  </div>
  <button type="submit">히트맵 생성</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.</p>
</div></body></html>"""


def run_sweep_html(params: dict) -> str:
    """민감도 스윕을 실행하고 히트맵 HTML을 반환한다 (pandas 필요)."""
    from quant.data import get_provider
    from quant.optimize import sensitivity_grid
    from quant.reporting import build_heatmap_html
    from quant.strategies import MovingAverageCross

    market = params.get("market", "synthetic")
    symbol = params.get("symbol", "DEMO")
    timeframe = params.get("timeframe", "1d")
    objective = params.get("objective", "sharpe")
    try:
        limit = max(100, min(5000, int(params.get("limit", 800))))
    except (TypeError, ValueError):
        limit = 800

    ppy = 365 if market in ("crypto", "synthetic") else 252
    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=limit)
    fast, slow = [5, 10, 15, 20, 30, 40], [50, 60, 80, 100, 150, 200]
    grid = sensitivity_grid(df, MovingAverageCross, "fast", fast, "slow", slow,
                            objective=objective, periods_per_year=ppy)
    heat = build_heatmap_html(fast, slow, grid, x_label="단기 MA", y_label="장기 MA",
                              objective=objective, title=f"MA 민감도 · {symbol}")
    return heat.replace("<h1", _NAV + "\n<h1", 1)
