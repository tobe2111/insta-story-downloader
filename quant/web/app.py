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

# 랜딩 페이지(docs/index.html)와 같은 디자인 토큰 — 절제된 다크 핀테크 톤.
# Pretendard는 사용자 PC에 설치돼 있으면 쓰고, 없으면 시스템 한글 폰트로 폴백
# (로컬 오프라인 도구라 웹폰트를 받지 않는다).
_STYLE = """
 :root{color-scheme:dark;
   --bg:#0a0b0e;--bg2:#0e1013;--fg:#f4f5f7;--muted:#8f96a3;--dim:#5c6370;
   --line:#1e2128;--line-strong:#2a2e37;--accent:#4c7dff;
   --ok:#3fb96f;--bad:#e5484d;--warn:#d9a13b;--radius:10px;
   --mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace}
 @media(prefers-color-scheme:light){:root{color-scheme:light;
   --bg:#fcfcfd;--bg2:#f4f5f8;--fg:#101318;
   --muted:#5a626e;--dim:#8a919d;--line:#e7e9ee;--line-strong:#d8dbe2;--accent:#2f5fe0}}
 *{box-sizing:border-box;min-width:0}
 body{font-family:"Pretendard Variable",Pretendard,-apple-system,system-ui,"Segoe UI",
   "Apple SD Gothic Neo","Malgun Gothic",sans-serif;margin:0;
   background:var(--bg);color:var(--fg);line-height:1.6;font-size:14px;
   -webkit-font-smoothing:antialiased}
 .wrap{max-width:780px;margin:0 auto;padding:20px 20px 56px}
 h1{font-size:20px;font-weight:750;letter-spacing:-.02em;margin:22px 0 6px}
 h2{font-size:15px;font-weight:700;letter-spacing:-.01em;margin:26px 0 10px}
 p.sub,.sub{color:var(--muted);font-size:13px;margin:0 0 4px}
 label{display:block;margin:14px 0 6px;font-size:12px;font-weight:600;color:var(--muted)}
 input,select{width:100%;padding:9px 12px;border-radius:8px;border:1px solid var(--line-strong);
   background:var(--bg2);color:inherit;font-size:13.5px;
   transition:border-color .15s,box-shadow .15s}
 input:focus,select:focus{outline:none;border-color:var(--accent);
   box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}
 button{margin-top:22px;padding:11px 20px;border:0;border-radius:9px;
   background:var(--fg);color:var(--bg);font-size:13.5px;font-weight:700;cursor:pointer;
   transition:opacity .15s,transform .05s;width:100%}
 button:hover{opacity:.88}button:active{transform:translateY(1px)}
 .row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:120px}
 .card{background:var(--bg2);border:1px solid var(--line);border-radius:var(--radius);
   padding:16px 18px;margin:14px 0}
 .warn{position:relative;color:var(--muted);font-size:12.5px;margin-top:22px;
   background:var(--bg2);padding:11px 14px 11px 16px;border-radius:var(--radius);
   border:1px solid var(--line-strong);border-left:3px solid var(--warn)}
 a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
 nav{display:flex;align-items:center;gap:2px;margin:0 0 8px;padding:10px 0;font-size:13px;
   overflow-x:auto;border-bottom:1px solid var(--line)}
 nav .logo{font-weight:800;font-size:13.5px;letter-spacing:.12em;color:var(--fg);
   margin-right:14px;white-space:nowrap}
 nav .logo em{font-style:normal;color:var(--accent)}
 nav a{white-space:nowrap;padding:6px 10px;border-radius:7px;font-weight:550;
   color:var(--muted);transition:background .15s,color .15s}
 nav a:hover{background:var(--bg2);color:var(--fg);text-decoration:none}
 table{width:100%;border-collapse:collapse;font-size:13px}
 pre,code{font-family:var(--mono)}
 form{margin-top:8px}
"""

# 브라우저 탭 아이콘 (외부 파일 없이 data URI) — 랜딩과 같은 심볼
_FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
            '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E'
            '%3Crect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%234c7dff%22/%3E'
            '%3Cpath d=%22M8 22 L14 14 L18 18 L24 9%22 stroke=%22white%22 '
            'stroke-width=%223%22 fill=%22none%22 stroke-linecap=%22round%22 '
            'stroke-linejoin=%22round%22/%3E%3C/svg%3E">')

_NAV = ('<nav><span class="logo">QUANT<em>.</em></span>'
        '<a href="/">백테스트</a>'
        '<a href="/portfolio">포트폴리오</a>'
        '<a href="/screener">종목선별</a>'
        '<a href="/sweep">민감도</a>'
        '<a href="/optimize">최적화</a>'
        '<a href="/validate">검증</a>'
        '<a href="/monitor">감시</a></nav>')

ALLOCATIONS = ["inverse_vol", "equal", "hrp"]

# 워크포워드 최적화가 지원하는 전략과 파라미터 격자 — CLI validate와 단일 출처
# (quant.markets)를 공유한다. quant.markets는 의존성 0이라 pandas 없는 폼 렌더도 안전.
from quant.markets import STRATEGY_GRIDS as _OPT_GRIDS


def render_form(message: str = "") -> str:
    """백테스트 실행 폼 페이지를 반환한다 (pandas 불필요)."""
    strat_opts = "".join(f'<option value="{s}">{s}</option>' for s in STRATEGIES)
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 백테스트</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>백테스트</h1>
<p class="sub">시장·종목·전략을 고르고 실행하면 성과 리포트가 나옵니다. 처음이라면
<code>synthetic</code>(모의 데이터)로 감을 잡아보세요.</p>
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
        '<p style="font-size:12px;color:var(--muted)">신뢰구간 하단(5%)이 0 근처거나 '
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
      setTxt('kpi-pnl', (pnl>=0?'+':'')+(pnl*100).toFixed(2)+'%', pnl>=0?'#3fb96f':'#e5484d');
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
      || '<tr><td colspan="3" style="color:var(--muted)">보유 포지션 없음</td></tr>'; }
    // 주문 테이블 재구성 (최근 15건)
    const ob=document.getElementById('ord-body');
    if(ob){ ob.innerHTML = orders.slice(-15).reverse().map(o=>
      `<tr><td>${_esc((o.side||'').toUpperCase())}</td><td>${_esc(o.symbol)}</td><td>${_num(o.quantity,6)}</td><td>${_num(o.price,2)}</td><td>${_esc(o.status)}</td></tr>`).join('')
      || '<tr><td colspan="5" style="color:var(--muted)">주문 내역 없음</td></tr>'; }
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

    # 'learn' CLI 기본 상태 파일(autolearn_state.json)도 후보에 넣는다. 이게 빠져
    # 있으면 python -m quant learn 이 쓰는 상태를 감시 탭이 못 읽어 화면이 빈다.
    candidates = state_paths or [
        "results/multi_state.json",
        "results/state.json",
        "results/autolearn_state.json",
    ]
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
<title>Quant · 감시</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>봇 감시</h1>
<p style="color:var(--muted);font-size:14px">실행 중인 페이퍼/실거래 세션이 없습니다.</p>
<p style="font-size:13px">먼저 봇을 실행하세요:</p>
<pre style="font-size:12px">python examples/run_live.py --paper --market crypto --symbol BTC/USDT</pre>
<p style="font-size:13px;color:var(--muted)">봇이 <code>results/state.json</code>을 쓰면
이 페이지에 자산·포지션·주문이 나타납니다.</p>
</div></body></html>""")

    doc = build_dashboard_html(state)
    doc = doc.replace("<header>", _NAV + "\n<header>", 1)  # 조종석 네비게이션
    # 페이지 전체 새로고침(meta refresh) 제거 → JS로 부드럽게 실시간 갱신
    doc = doc.replace('<meta http-equiv="refresh" content="30">', "")
    doc = doc.replace(
        "</header>",
        '</header><p class="sub" style="font-size:12px;color:var(--muted)">'
        '<span style="color:var(--ok)">●</span> 실시간 (5초 갱신) · 마지막: <span id="rt-time">—</span></p>', 1)

    # 확장 상태 배지 — 새 리스크/운영 필드가 상태에 있으면 표시한다(없으면 생략).
    badges = []
    corr = state.get("avg_correlation")
    if isinstance(corr, (int, float)):
        # 위기 국면에서 상관이 1로 수렴하면 분산 효과가 사라진다(경고 임계 0.7)
        color = "#f87171" if corr >= 0.7 else "#94a3b8"
        badges.append(f'<span style="color:{color}">🔗 평균상관 {corr:.2f}'
                      + (" ⚠️ 분산 효과 약화" if corr >= 0.7 else "") + "</span>")
    err = state.get("last_error")
    if err:
        badges.append(f'<span style="color:#f87171">⚠️ 마지막 오류: '
                      f'{html.escape(str(err)[:120])}</span>')
    if state.get("kill_switch_halted"):
        badges.append('<span style="color:#f87171">🛑 일일 손실 킬스위치 발동 — '
                      '다음 UTC 일까지 매매 중단</span>')
    if badges:
        doc = doc.replace(
            '<span id="rt-time">—</span></p>',
            '<span id="rt-time">—</span> · ' + " · ".join(badges) + "</p>", 1)
    return doc.replace("</body>", _MONITOR_JS + "</body>", 1)


def render_portfolio_form(message: str = "") -> str:
    """다중 종목 포트폴리오 백테스트 폼 (pandas 불필요)."""
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    strat_opts = "".join(f'<option value="{s}">{s}</option>' for s in STRATEGIES)
    alloc_opts = "".join(f'<option value="{a}">{a}</option>' for a in ALLOCATIONS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 포트폴리오</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>포트폴리오 백테스트</h1>
<p style="color:var(--muted);font-size:13px">여러 종목에 분산투자해 변동성을 낮춥니다.
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


def render_screener_form(message: str = "") -> str:
    """종목 선별(팩터 스크리너) 폼 페이지 (pandas 불필요)."""
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 종목선별</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>종목 선별 (팩터 스크리너)</h1>
<p style="color:var(--muted);font-size:13px">관심 종목을 넣으면 재무 팩터(밸류·퀄리티)로
상위 종목을 자동 선별합니다. 미국주식 티커 권장(FMP 기준). 환경변수
<code>FMP_API_KEY</code> 필요.</p>
{msg}
<form action="/screener/run" method="get">
  <div><label>후보 종목 (쉼표 구분)</label>
    <input name="symbols" value="AAPL, MSFT, GOOGL, META, NVDA, TSLA"></div>
  <div class="row">
    <div><label>선택 개수 (top N)</label><input name="top_n" value="3"></div>
    <div><label>팩터</label>
      <select name="factors">
        <option value="value_quality">밸류+퀄리티 (PER↓·PBR↓·ROE↑)</option>
        <option value="value">밸류 (PER↓·PBR↓)</option>
        <option value="quality">퀄리티 (ROE↑)</option>
      </select></div>
  </div>
  <button type="submit">선별 실행</button>
</form>
<p class="warn">⚠️ 팩터 프리미엄은 수년씩 부진할 수 있습니다. 선별 결과를 맹신하지 마세요.</p>
</div></body></html>"""


_FACTOR_PRESETS = {
    "value_quality": {"pe": -1.0, "pb": -1.0, "roe": 1.0},
    "value": {"pe": -1.0, "pb": -1.0},
    "quality": {"roe": 1.0},
}


_MAX_SYMBOLS = 50   # 한 요청당 종목 수 상한 (자원 고갈 DoS 방지)


def _parse_symbols(raw: str, upper: bool = False) -> list[str]:
    """콤마 구분 종목 문자열을 파싱한다 — 중복 제거 + 최대 _MAX_SYMBOLS개로 제한.

    상한이 없으면 심볼 수가 무제한이라, 로컬 웹서버라도 한 요청으로 수만 개
    종목의 백테스트를 강제해 메모리/CPU를 고갈시킬 수 있다(합성 데이터는 네트워크
    제한도 없다). 여기서 잘라 방어한다.
    """
    seen: list[str] = []
    for s in raw.split(","):
        s = s.strip()
        if not s:
            continue
        if upper:
            s = s.upper()
        if s not in seen:
            seen.append(s)
        if len(seen) >= _MAX_SYMBOLS:
            break
    return seen


def run_screener_html(params: dict) -> str:
    """관심 종목을 팩터로 선별해 결과 표 HTML을 반환한다 (FMP 키 필요)."""
    raw = params.get("symbols", "")
    symbols = _parse_symbols(raw, upper=True)   # 종목 수 상한(자원 고갈 방지)
    if not symbols:
        return render_screener_form("후보 종목을 하나 이상 입력하세요.")
    try:
        top_n = max(1, int(params.get("top_n", 3)))
    except (TypeError, ValueError):
        top_n = 3
    factors = _FACTOR_PRESETS.get(params.get("factors", "value_quality"),
                                  _FACTOR_PRESETS["value_quality"])

    from quant.portfolio import screen_symbols

    result = screen_symbols(symbols, factors=factors, top_n=top_n)
    ratios = result["ratios"]
    weights = result["weights"]
    if not ratios:
        return render_screener_form(
            "재무 데이터를 받지 못했습니다. FMP_API_KEY 환경변수를 확인하세요 "
            "(무료 키: financialmodelingprep.com).")

    def _fmt(v):
        return "-" if v is None else f"{v:.2f}"

    rows = "".join(
        f'<tr><td>{html.escape(sym)}</td>'
        f'<td>{_fmt(r.get("pe"))}</td><td>{_fmt(r.get("pb"))}</td>'
        f'<td>{_fmt(r.get("roe"))}</td>'
        f'<td>{"✅ " + format(weights[sym], ".0%") if sym in weights else "-"}</td></tr>'
        for sym, r in ratios.items()
    )
    picked = ", ".join(weights) or "(선별된 종목 없음)"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 선별 결과</title>{_FAVICON}<style>{_STYLE}
 table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}}
 th,td{{border:1px solid #334155;padding:6px 8px;text-align:right}}
 th:first-child,td:first-child{{text-align:left}}</style></head>
<body><div class="wrap">{_NAV}
<h1>선별 결과</h1>
<p style="font-size:14px">선택된 종목: <b>{html.escape(picked)}</b></p>
<table><tr><th>종목</th><th>PER</th><th>PBR</th><th>ROE</th><th>선택·비중</th></tr>
{rows}</table>
<p style="font-size:12px;color:var(--muted);margin-top:10px">이 종목들을 포트폴리오 탭에
넣어 백테스트/운용하세요. 팩터 랭킹은 '후보 중 상대 비교'일 뿐 미래 수익 보장이 아닙니다.</p>
</div></body></html>"""


def run_portfolio_html(params: dict) -> str:
    """다중 종목 포트폴리오 백테스트를 실행하고 리포트 HTML을 반환한다 (pandas 필요)."""
    market = params.get("market", "synthetic")
    raw = params.get("symbols", "A, B, C")
    symbols = _parse_symbols(raw)      # 종목 수 상한(자원 고갈 방지)
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
<title>Quant · 최적화</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>워크포워드 최적화</h1>
<p style="color:var(--muted);font-size:13px">과거 구간(IS)에서 최적 파라미터를 찾고,
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
    ) or '<tr><td colspan="5" style="color:var(--muted)">검증 구간 없음</td></tr>'

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 최적화 결과</title>{_FAVICON}<style>{_STYLE}
 table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}}
 th,td{{padding:6px 8px;border-bottom:1px solid #334155;text-align:left}}
 .box{{background:#111c30;border:1px solid #334155;border-radius:10px;padding:16px;margin-top:14px}}
 @media(prefers-color-scheme:light){{.box{{background:#fff}}}}
</style></head><body><div class="wrap">
{_NAV}
<h1>워크포워드 결과 · {html.escape(strategy_name)} · {html.escape(symbol)}</h1>
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


def render_validate_form(message: str = "") -> str:
    """과최적화 검증 3종(워크포워드+DSR·PBO·CPCV) 폼 (pandas 불필요).

    전략 선택지는 CLI validate와 같은 기본 그리드(_OPT_GRIDS)를 가진
    전략으로 제한한다 — 그리드가 없으면 검증할 조합 자체가 없다.
    """

    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    strat_opts = "".join(f'<option value="{s}">{s}</option>' for s in _OPT_GRIDS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 검증</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>과최적화 검증 (워크포워드+DSR · PBO · CPCV)</h1>
<p style="color:var(--muted);font-size:13px">"이 전략을 믿어도 되는가"를 세 가지
과최적화 탐지 도구로 한 화면에서 확인합니다. 셋 다 <b>탐지</b> 도구입니다 —
통과가 곧 수익은 아닙니다.</p>
{msg}
<form action="/validate/run" method="get">
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
  <button type="submit">검증 3종 실행</button>
</form>
<p class="warn">⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다.
다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.</p>
</div></body></html>"""


def run_validate_html(params: dict) -> str:
    """검증 3종을 실행하고 결과를 HTML로 렌더한다 (pandas 필요).

    CLI _cmd_validate와 같은 하부 조각(walk_forward·pbo·cpcv)과 같은 한국어
    리포트 문자열(pbo_report·cpcv_report)을 재사용하고 <pre>로 감싼다.
    단계별 ValueError(데이터 부족 등)는 그 단계만 '건너뜀'으로 표시한다.
    """

    market = params.get("market", "synthetic")
    symbol = params.get("symbol", "DEMO")
    timeframe = params.get("timeframe", "1d")
    strategy_name = params.get("strategy", "ma_cross")
    grid = _OPT_GRIDS.get(strategy_name)
    if not grid:
        return render_validate_form(
            f"'{strategy_name}'는 검증 미지원 전략입니다 "
            f"(기본 그리드 지원: {', '.join(_OPT_GRIDS)}).")
    try:
        limit = max(200, min(5000, int(params.get("limit", 800))))
        is_window = max(50, int(params.get("is_window", 250)))
        oos_window = max(20, int(params.get("oos_window", 125)))
    except (TypeError, ValueError):
        limit, is_window, oos_window = 800, 250, 125

    # 유효 입력 확인 후에만 무거운(pandas) 모듈을 임포트
    from quant.data import get_provider
    from quant.optimize import cpcv, cpcv_report, walk_forward
    from quant.robustness import param_returns_matrix, pbo, pbo_report
    from quant.strategies import get_strategy

    strategy_cls = type(get_strategy(strategy_name))
    ppy = 365 if market in ("crypto", "synthetic") else 252
    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=limit)

    sections: list[tuple[str, str]] = []

    # 1) 워크포워드 + DSR (다중검정 보정 샤프 신뢰도)
    try:
        wf = walk_forward(df, strategy_cls, grid, is_window=is_window,
                          oos_window=oos_window, embargo=5,
                          periods_per_year=ppy)
        m = wf["oos_metrics"]
        wf_text = (
            f"OOS 샤프 {m.sharpe:.2f} · 총수익 {m.total_return:.2%} · "
            f"최대낙폭 {m.max_drawdown:.2%} · 구간 {len(wf['segments'])}개\n"
            f"DSR(시행 {wf['n_trials']}회 보정): {wf['dsr']:.2f} "
            + ("— 실력 가능성" if wf["dsr"] >= 0.95 else "— 운일 수 있음(0.95 미만)"))
    except ValueError as exc:
        wf_text = f"건너뜀: {exc}"
    sections.append(("[1/3] 워크포워드 (롤링 IS→OOS) + DSR", wf_text))

    # 2) PBO — IS 1등이 OOS에서 동전던지기인지
    try:
        mat = param_returns_matrix(df, strategy_cls, grid, periods_per_year=ppy)
        pbo_text = pbo_report(pbo(mat, n_blocks=10))
    except ValueError as exc:
        pbo_text = f"건너뜀: {exc}"
    sections.append(("[2/3] PBO (백테스트 과적합 확률)", pbo_text))

    # 3) CPCV — 여러 OOS 경로의 분포
    try:
        cv = cpcv(df, strategy_cls, grid, n_groups=6, n_test=2, embargo=5,
                  periods_per_year=ppy)
        cpcv_text = cpcv_report(cv)
    except ValueError as exc:
        cpcv_text = f"건너뜀: {exc}"
    sections.append(("[3/3] CPCV (다중 OOS 경로 분포)", cpcv_text))

    boxes = "".join(
        f'<h2>{html.escape(title)}</h2><div class="card">'
        f'<pre style="font-size:12.5px;white-space:pre-wrap;overflow-x:auto;'
        f'margin:0">{html.escape(text)}</pre></div>'
        for title, text in sections)

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 검증 결과</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>검증 결과 · {html.escape(strategy_name)} · {html.escape(symbol)} ({len(df)}봉)</h1>
<p class="sub">그리드: {html.escape(str(grid))}</p>
{boxes}
<p class="warn">⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다.
다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.</p>
</div></body></html>"""


def render_sweep_form(message: str = "") -> str:
    """파라미터 민감도 스윕 폼 페이지 (pandas 불필요)."""
    market_opts = "".join(f'<option value="{m}">{m}</option>' for m in MARKETS)
    msg = f'<p class="warn">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 민감도 스윕</title>{_FAVICON}<style>{_STYLE}</style></head><body><div class="wrap">
{_NAV}
<h1>파라미터 민감도 히트맵</h1>
<p style="color:var(--muted);font-size:13px">이동평균 교차(단기×장기)의 성과 지형을 그립니다.
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
