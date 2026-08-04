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

# 사람이 읽는 한글 라벨 — 값(value)은 코드명 그대로 유지하고 표시만 바꾼다.
# 비전문가에게 ma_cross·us_stock 같은 코드명은 첫 화면에서 이탈하는 장벽이다.
STRATEGY_LABELS = {
    "ma_cross": "이동평균 교차 · 추세추종",
    "momentum": "모멘텀 · 추세추종",
    "mean_reversion": "평균회귀 · 되돌림 매수",
    "rsi": "RSI 과매도 반등",
    "breakout": "채널 돌파 · 추세추종",
    "macd": "MACD 히스토그램",
    "keltner": "켈트너 채널 돌파",
    "stochastic": "스토캐스틱",
    "ml": "머신러닝 · 상승확률 예측",
    "ensemble": "앙상블 · 여러 전략 결합",
    "champion": "챔피언 · 야간 재학습 1위",
    "regime_wrap": "레짐 필터 · 약세장 자동 관망",
}
MARKET_LABELS = {
    "synthetic": "모의 데이터 · 연습용",
    "crypto": "코인 (암호화폐)",
    "us_stock": "미국주식",
    "kr_stock": "국내주식",
}


def _opts(values, labels=None) -> str:
    """<option> 목록 — value는 코드명, 표시는 '한글 라벨 (코드명)'."""
    out = []
    for v in values:
        lab = (labels or {}).get(v)
        text = f"{lab} ({v})" if lab else v
        out.append(f'<option value="{html_escape(v)}">{html_escape(text)}</option>')
    return "".join(out)


def html_escape(s) -> str:
    return html.escape(str(s), quote=True)

# 랜딩 페이지(docs/index.html)와 같은 디자인 토큰 — 절제된 다크 핀테크 톤.
# Pretendard는 사용자 PC에 설치돼 있으면 쓰고, 없으면 시스템 한글 폰트로 폴백
# (로컬 오프라인 도구라 웹폰트를 받지 않는다).
_STYLE = """
 :root{color-scheme:dark;
   --bg:#0a0b0e;--bg2:#0e1013;--bg3:#13161b;--fg:#f4f5f7;--muted:#8f96a3;--dim:#5c6370;
   --line:#1e2128;--line-strong:#2a2e37;--accent:#4c7dff;--accent-soft:rgba(76,125,255,.11);
   --ok:#3fb96f;--bad:#e5484d;--warn:#d9a13b;--radius:12px;
   --mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace;
   --shadow:0 1px 2px rgba(0,0,0,.25),0 8px 28px -12px rgba(0,0,0,.45)}
 @media(prefers-color-scheme:light){:root{color-scheme:light;
   --bg:#fcfcfd;--bg2:#f5f6f9;--bg3:#fff;--fg:#101318;
   --muted:#5a626e;--dim:#8a919d;--line:#e7e9ee;--line-strong:#d8dbe2;
   --accent:#2f5fe0;--accent-soft:rgba(47,95,224,.08);
   --shadow:0 1px 2px rgba(16,19,24,.05),0 8px 24px -14px rgba(16,19,24,.14)}}
 *{box-sizing:border-box;min-width:0}
 html{scrollbar-gutter:stable}
 body{font-family:"Pretendard Variable",Pretendard,-apple-system,system-ui,"Segoe UI",
   "Apple SD Gothic Neo","Malgun Gothic",sans-serif;margin:0;
   background:var(--bg);color:var(--fg);line-height:1.65;font-size:14px;
   -webkit-font-smoothing:antialiased}
 .wrap{max-width:800px;margin:0 auto;padding:0 22px 64px}
 .kicker{font-size:11px;font-weight:700;letter-spacing:.14em;color:var(--accent);
   text-transform:uppercase;margin:30px 0 4px}
 h1{font-size:22px;font-weight:800;letter-spacing:-.022em;margin:0 0 6px}
 h2{font-size:14px;font-weight:700;letter-spacing:-.01em;margin:28px 0 10px;
   display:flex;align-items:center;gap:8px}
 h2::after{content:"";flex:1;height:1px;background:var(--line)}
 p.sub,.sub{color:var(--muted);font-size:13.5px;margin:0 0 4px;max-width:60ch}
 label{display:block;margin:0 0 6px;font-size:12px;font-weight:650;color:var(--muted)}
 .hint{font-size:11.5px;color:var(--dim);margin-top:5px}
 input,select{width:100%;padding:10px 12px;border-radius:9px;border:1px solid var(--line-strong);
   background:var(--bg);color:inherit;font-size:13.5px;
   transition:border-color .15s,box-shadow .15s}
 select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%238f96a3' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
   background-repeat:no-repeat;background-position:right 12px center;padding-right:30px}
 input:focus,select:focus{outline:none;border-color:var(--accent);
   box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 20%,transparent)}
 button{margin-top:6px;padding:12px 22px;border:0;border-radius:10px;
   background:var(--accent);color:#fff;font-size:13.5px;font-weight:700;cursor:pointer;
   font-family:inherit;letter-spacing:-.01em;
   transition:filter .15s,transform .05s;width:100%}
 button:hover{filter:brightness(1.08)}button:active{transform:translateY(1px)}
 .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
   gap:14px;margin:0 0 16px}
 .card,form.panel{background:var(--bg3);border:1px solid var(--line);
   border-radius:var(--radius);padding:20px;margin:14px 0;box-shadow:var(--shadow)}
 .warn{position:relative;color:var(--muted);font-size:12.5px;margin-top:22px;
   background:var(--bg2);padding:11px 14px 11px 16px;border-radius:var(--radius);
   border:1px solid var(--line);border-left:3px solid var(--warn);line-height:1.6}
 .danger{margin:14px 0;padding:13px 16px;border-radius:var(--radius);font-size:13px;
   background:color-mix(in srgb,var(--bad) 9%,var(--bg2));
   border:1px solid color-mix(in srgb,var(--bad) 38%,transparent);color:var(--fg)}
 .danger b{color:var(--bad)}
 .errbox{margin:14px 0;padding:13px 16px;border-radius:var(--radius);font-size:13px;
   background:var(--bg2);border:1px solid var(--line-strong);
   border-left:3px solid var(--bad)}
 .errbox details{margin-top:6px}
 .errbox summary{cursor:pointer;color:var(--dim);font-size:12px}
 .errbox pre{margin:8px 0 0;font-size:11.5px;color:var(--muted);white-space:pre-wrap}
 a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
 .topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);
   backdrop-filter:blur(10px);border-bottom:1px solid var(--line);margin:0 -22px 6px;
   padding:0 22px}
 nav{display:flex;align-items:center;gap:2px;font-size:13px;overflow-x:auto;
   height:52px;scrollbar-width:none}
 nav::-webkit-scrollbar{display:none}
 nav .logo{font-weight:800;font-size:13.5px;letter-spacing:.13em;color:var(--fg);
   margin-right:16px;white-space:nowrap}
 nav .logo em{font-style:normal;color:var(--accent)}
 nav a{white-space:nowrap;padding:6px 11px;border-radius:8px;font-weight:550;
   color:var(--muted);transition:background .15s,color .15s}
 nav a:hover{background:var(--bg2);color:var(--fg);text-decoration:none}
 nav a.on{color:var(--fg);background:var(--accent-soft);font-weight:650}
 .steps{display:flex;gap:0;margin:16px 0 4px;border:1px solid var(--line);
   border-radius:var(--radius);overflow:hidden;background:var(--bg3)}
 .steps a{flex:1;padding:10px 8px;text-align:center;font-size:12px;color:var(--muted);
   border-right:1px solid var(--line);line-height:1.45}
 .steps a:last-child{border-right:0}
 .steps a:hover{background:var(--bg2);text-decoration:none;color:var(--fg)}
 .steps b{display:block;font-size:12.5px;color:var(--fg);letter-spacing:-.01em}
 .steps .num{display:inline-block;font-size:10.5px;color:var(--accent);font-weight:700;
   margin-bottom:1px}
 table{width:100%;border-collapse:collapse;font-size:13px;
   font-variant-numeric:tabular-nums}
 th{color:var(--muted);font-weight:600;font-size:12px}
 th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right}
 th:first-child,td:first-child{text-align:left}
 tr:last-child td{border-bottom:0}
 .tablewrap{overflow-x:auto;margin:8px -4px 0;padding:0 4px}
 pre,code{font-family:var(--mono)}
 code{font-size:.92em;background:var(--bg2);border:1px solid var(--line);
   border-radius:5px;padding:1px 5px}
 form{margin-top:8px}
 #busy{position:fixed;inset:0;display:none;place-items:center;z-index:50;
   background:color-mix(in srgb,var(--bg) 72%,transparent);backdrop-filter:blur(3px)}
 #busy.show{display:grid}
 #busy .box{background:var(--bg3);border:1px solid var(--line);border-radius:14px;
   padding:26px 34px;text-align:center;box-shadow:var(--shadow)}
 #busy .spin{width:26px;height:26px;margin:0 auto 12px;border-radius:50%;
   border:3px solid var(--line-strong);border-top-color:var(--accent);
   animation:spin .8s linear infinite}
 @keyframes spin{to{transform:rotate(360deg)}}
 #busy p{margin:0;font-size:13.5px}
 #busy .sub{font-size:12px;color:var(--muted);margin-top:4px}
 @media(max-width:560px){
   .wrap{padding:0 14px 48px}.topbar{margin:0 -14px 6px;padding:0 14px}
   .card,form.panel{padding:16px}
   .steps{flex-wrap:wrap}.steps a{flex:1 1 50%;border-bottom:1px solid var(--line)}
 }
"""

# 브라우저 탭 아이콘 (외부 파일 없이 data URI) — 랜딩과 같은 심볼
_FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
            '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E'
            '%3Crect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%234c7dff%22/%3E'
            '%3Cpath d=%22M8 22 L14 14 L18 18 L24 9%22 stroke=%22white%22 '
            'stroke-width=%223%22 fill=%22none%22 stroke-linecap=%22round%22 '
            'stroke-linejoin=%22round%22/%3E%3C/svg%3E">')

_NAV_ITEMS = [("/", "백테스트"), ("/portfolio", "포트폴리오"),
              ("/screener", "종목선별"), ("/sweep", "민감도"),
              ("/optimize", "최적화"), ("/validate", "검증"), ("/monitor", "감시")]


def _nav(active: str = "") -> str:
    on = ' class="on"'
    links = "".join(
        f'<a href="{p}"{on if p == active else ""}>{t}</a>'
        for p, t in _NAV_ITEMS)
    return ('<div class="topbar"><nav><span class="logo">QUANT<em>.</em></span>'
            + links + "</nav></div>")


_NAV = _nav()   # 외부 생성 문서(리포트/대시보드)에 주입할 때 쓰는 기본 내비게이션

# 실행 버튼 → 결과까지 수 초~수십 초 걸린다(ML은 20~30초). 표시가 없으면
# 사용자는 멈춘 줄 알고 닫는다 — 폼 제출 시 오버레이를 띄우고 중복 제출을 막는다.
_UX_JS = """<script>
document.addEventListener('submit',function(e){
  var f=e.target; if(!(f instanceof HTMLFormElement)) return;
  var b=document.getElementById('busy'); if(b) b.classList.add('show');
  var btn=f.querySelector('button[type=submit],button:not([type])');
  if(btn){btn.disabled=true;btn.style.opacity=.6;}
},true);
window.addEventListener('pageshow',function(){
  var b=document.getElementById('busy'); if(b) b.classList.remove('show');
});
</script>"""

_BUSY = ('<div id="busy"><div class="box"><div class="spin"></div>'
         '<p>계산 중입니다…</p>'
         '<p class="sub">머신러닝 전략은 20~30초 걸릴 수 있어요. 창을 닫지 마세요.</p>'
         '</div></div>')


def _page(title: str, body: str, active: str = "") -> str:
    """공통 문서 골격 — 헤더·내비게이션·로딩 오버레이·스타일을 한곳에서."""
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>Quant · {html_escape(title)}</title>{_FAVICON}'
            f'<style>{_STYLE}</style></head><body><div class="wrap">\n'
            f'{_nav(active)}\n{body}\n</div>{_BUSY}{_UX_JS}</body></html>')


def _msg_html(message: str) -> str:
    """오류/안내 메시지 박스 — 개발자용 원문은 접어서 보여준다."""
    if not message:
        return ""
    if message.startswith(("실행 오류", "모니터 로드 오류")):
        return ('<div class="errbox"><b>문제가 발생해 실행하지 못했습니다.</b> '
                '입력값(종목·봉 개수)을 확인하고 다시 시도해 주세요. 반복되면 '
                '네트워크나 데이터 소스 문제일 수 있습니다.'
                f'<details><summary>자세한 오류 내용</summary>'
                f'<pre>{html.escape(message)}</pre></details></div>')
    return f'<div class="errbox">{html.escape(message)}</div>'


def _fallback_banner(*dfs) -> str:
    """실데이터 수신 실패 → 합성 폴백으로 계산된 결과임을 화면에 명시한다.

    CLI에는 이 경고가 있는데 웹에 없으면, 사용자가 가짜 데이터 백테스트를
    진짜 성과로 믿게 된다 — 이 제품에서 가장 위험한 종류의 침묵이다.
    """
    if any(getattr(df, "attrs", {}).get("synthetic_fallback") for df in dfs):
        return ('<div class="danger"><b>⚠️ 주의: 이 결과는 실데이터가 아닙니다.</b> '
                '시세 서버에서 실데이터를 받지 못해 <b>모의(합성) 데이터</b>로 계산된 '
                '결과입니다. 인터넷 연결과 데이터 소스를 확인한 뒤 다시 실행하세요 — '
                '이 화면의 수익률로 어떤 판단도 하지 마세요.</div>')
    return ""


# 올바른 사용 순서 안내 — 첫 화면에서 길을 잃지 않게 한다(README에만 있던 흐름).
_STEPS = ('<div class="steps">'
          '<a href="/"><span class="num">1단계</span><b>백테스트</b>과거로 감 잡기</a>'
          '<a href="/validate"><span class="num">2단계</span><b>검증</b>과최적화 걸러내기</a>'
          '<a href="/monitor"><span class="num">3단계</span><b>페이퍼</b>가짜 돈 실전 연습</a>'
          '<a href="/monitor"><span class="num">4단계</span><b>실전</b>소액부터, 직접 결정</a>'
          '</div>')

ALLOCATIONS = ["inverse_vol", "equal", "hrp"]

# 워크포워드 최적화가 지원하는 전략과 파라미터 격자 — CLI validate와 단일 출처
# (quant.markets)를 공유한다. quant.markets는 의존성 0이라 pandas 없는 폼 렌더도 안전.
from quant.markets import STRATEGY_GRIDS as _OPT_GRIDS


def render_form(message: str = "") -> str:
    """백테스트 실행 폼 페이지를 반환한다 (pandas 불필요)."""
    # champion = 야간 재학습이 뽑은 현재 챔피언(시장·종목별) — 백테스트 폼 전용.
    # 종목선별 등 다른 폼에는 넣지 않는다(종목마다 챔피언이 달라 의미가 없다).
    body = f"""<p class="kicker">Backtest</p>
<h1>백테스트</h1>
<p class="sub">과거 데이터로 전략을 돌려 성과를 확인합니다. 처음이라면 시장을
'모의 데이터'로 두고 감부터 잡아보세요 — 인터넷 없이도 됩니다.</p>
{_STEPS}
{_msg_html(message)}
<form action="/backtest" method="get" class="panel">
  <div class="row">
    <div><label>시장</label><select name="market">{_opts(MARKETS, MARKET_LABELS)}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT">
      <div class="hint">코인: BTC/USDT · 미국주식: AAPL, SPY</div></div>
  </div>
  <div class="row">
    <div><label>전략</label>
      <select name="strategy">{_opts(STRATEGIES + ["champion"], STRATEGY_LABELS)}</select></div>
    <div><label>타임프레임</label><input name="timeframe" value="1d">
      <div class="hint">1d=일봉 · 1h=시간봉</div></div>
    <div><label>봉 개수</label><input name="limit" value="500">
      <div class="hint">일봉 500개 ≈ 2년</div></div>
  </div>
  <button type="submit">백테스트 실행</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다. 실거래 전 반드시 검증하세요.</p>"""
    return _page("백테스트", body, "/")


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
    if strategy_name == "champion":
        from quant.live.retrain import champion_strategy
        strategy = champion_strategy(market, symbol)
    elif strategy_name == "ensemble":
        strategy = default_ensemble()
    else:
        strategy = get_strategy(strategy_name)
    result = Backtester(strategy, periods_per_year=ppy).run(df)

    label = STRATEGY_LABELS.get(strategy_name, strategy_name)
    body = build_report_html(result, title=f"{label} · {symbol}")
    # 상단 내비게이션 + 합성 폴백 경고(가짜 데이터 결과를 진짜로 믿지 않게)
    body = body.replace("<h1>", _NAV + "\n" + _fallback_banner(df) + "<h1>", 1)
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


def champions_html(state_dir: str = "state") -> str:
    """야간 재학습 챔피언 현황 카드 (기록이 없으면 빈 문자열). pandas 불필요."""
    import json
    from pathlib import Path

    fp = Path(state_dir) / "champions.json"
    if not fp.exists():
        return ""
    try:
        champions = json.loads(fp.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ""
    if not champions:
        return ""

    # 최근 결정 이유(있으면) — 시장별 마지막 기록
    reasons: dict[str, dict] = {}
    hist = Path(state_dir) / "retrain_history.jsonl"
    if hist.exists():
        try:
            for line in hist.read_text(encoding="utf-8").splitlines()[-50:]:
                rec = json.loads(line)
                reasons[f"{rec.get('market')}:{rec.get('symbol')}"] = rec
        except (ValueError, OSError):
            pass

    rows = []
    for key, c in champions.items():
        rec = reasons.get(key, {})
        strat = STRATEGY_LABELS.get(c.get("strategy", ""), c.get("strategy", ""))
        params = html.escape(json.dumps(c.get("params", {}), ensure_ascii=False))
        badge = ("🔁 어젯밤 교체" if rec.get("promoted")
                 else f"🏆 유지 (교체 {c.get('promotions', 0)}회)")
        rows.append(
            f"<tr><td>{html.escape(key)}</td><td>{badge}</td>"
            f"<td style='font-size:12px'><b>{html.escape(strat)}</b> {params}</td>"
            f"<td style='font-size:12px;color:var(--muted)'>"
            f"{html.escape(str(rec.get('reason', ''))[:90])}</td></tr>")
    return (
        '<div class="card"><b>야간 자동 재학습 — 챔피언/챌린저</b>'
        '<p class="sub" style="font-size:12.5px;margin:6px 0 4px">매일 밤 새 데이터로 '
        '후보들을 학습시켜 현재 챔피언과 2단계 검증(선발전→결승전)으로 대결시키고, '
        '확실히 이긴 후보만 교체합니다. 챔피언이 오래 안 바뀌는 것이 정상입니다.</p>'
        '<div class="tablewrap">'
        '<table><tr><th>시장</th><th>상태</th><th>챔피언 설정</th><th>최근 결정</th></tr>'
        + "".join(rows) + "</table></div></div>")


def render_monitor(state_paths=None) -> str:
    """실행 중인 봇의 상태(state.json)를 읽어 감시 대시보드를 렌더한다 (pandas 불필요).

    차트는 /api/state를 5초마다 폴링해 페이지 새로고침 없이 갱신된다.
    """
    from quant.reporting import build_dashboard_html

    state = read_state(state_paths)

    if state is None:
        body = f"""<p class="kicker">Monitor</p>
<h1>봇 감시</h1>
<p class="sub">실행 중인 페이퍼/실거래 세션이 없습니다.</p>
<div class="card">
<b>페이퍼(가짜 돈) 봇 시작하기</b>
<p class="sub" style="margin:6px 0 8px">윈도우는 <code>learn.bat</code> 더블클릭,
또는 터미널에서:</p>
<pre style="font-size:12px;overflow-x:auto;margin:0">python -m quant learn</pre>
<p class="hint">봇이 상태 파일을 쓰기 시작하면 이 페이지에 자산·포지션·주문이
실시간으로 나타납니다.</p>
</div>
{champions_html()}"""
        return _page("감시", body, "/monitor")

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
    doc = doc.replace("</body>", champions_html() + "</body>", 1)
    return doc.replace("</body>", _MONITOR_JS + "</body>", 1)


ALLOCATION_LABELS = {
    "inverse_vol": "변동성 역가중 · 안정적 배분",
    "equal": "동일 비중",
    "hrp": "계층적 리스크 패리티 (HRP)",
}


def render_portfolio_form(message: str = "") -> str:
    """다중 종목 포트폴리오 백테스트 폼 (pandas 불필요)."""
    body = f"""<p class="kicker">Portfolio</p>
<h1>포트폴리오 백테스트</h1>
<p class="sub">여러 종목에 분산투자해 변동성을 낮춥니다. 종목은 쉼표로 구분하세요.</p>
{_msg_html(message)}
<form action="/portfolio/run" method="get" class="panel">
  <div class="row">
    <div><label>시장</label><select name="market">{_opts(MARKETS, MARKET_LABELS)}</select></div>
    <div><label>종목 (쉼표 구분)</label>
      <input name="symbols" value="BTC/USDT, ETH/USDT, SOL/USDT"></div>
  </div>
  <div class="row">
    <div><label>전략</label><select name="strategy">{_opts(STRATEGIES, STRATEGY_LABELS)}</select></div>
    <div><label>배분 방식</label>
      <select name="allocation">{_opts(ALLOCATIONS, ALLOCATION_LABELS)}</select></div>
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="500"></div>
  </div>
  <button type="submit">포트폴리오 백테스트</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.</p>"""
    return _page("포트폴리오", body, "/portfolio")


def render_screener_form(message: str = "") -> str:
    """종목 선별(팩터 스크리너) 폼 페이지 (pandas 불필요)."""
    body = f"""<p class="kicker">Screener</p>
<h1>종목 선별 (팩터 스크리너)</h1>
<p class="sub">관심 종목을 넣으면 재무 팩터(밸류·퀄리티)로 상위 종목을 자동
선별합니다. 미국주식 티커 권장(FMP 기준). 환경변수 <code>FMP_API_KEY</code> 필요.</p>
{_msg_html(message)}
<form action="/screener/run" method="get" class="panel">
  <div class="row"><div><label>후보 종목 (쉼표 구분)</label>
    <input name="symbols" value="AAPL, MSFT, GOOGL, META, NVDA, TSLA"></div></div>
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
<p class="warn">⚠️ 팩터 프리미엄은 수년씩 부진할 수 있습니다. 선별 결과를 맹신하지 마세요.</p>"""
    return _page("종목선별", body, "/screener")


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
    body = f"""<p class="kicker">Screener</p>
<h1>선별 결과</h1>
<p class="sub">선택된 종목: <b>{html.escape(picked)}</b></p>
<div class="card"><div class="tablewrap">
<table><tr><th>종목</th><th>PER</th><th>PBR</th><th>ROE</th><th>선택·비중</th></tr>
{rows}</table></div></div>
<p class="sub" style="font-size:12px">이 종목들을 포트폴리오 탭에 넣어 백테스트/운용하세요.
팩터 랭킹은 '후보 중 상대 비교'일 뿐 미래 수익 보장이 아닙니다.</p>"""
    return _page("선별 결과", body, "/screener")


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

    alloc_label = ALLOCATION_LABELS.get(allocation, allocation)
    body = build_report_html(result, title=f"포트폴리오 · {len(symbols)}종목 ({alloc_label})")
    return body.replace("<h1>",
                        _NAV + "\n" + _fallback_banner(*data.values()) + "<h1>", 1)


def render_optimize_form(message: str = "") -> str:
    """워크포워드 최적화 폼 (pandas 불필요)."""
    body = f"""<p class="kicker">Walk-forward</p>
<h1>워크포워드 최적화</h1>
<p class="sub">과거 구간(IS)에서 최적 파라미터를 찾고, <b>보지 않은 미래 구간(OOS)</b>에서
검증합니다. IS와 OOS 성적 격차가 크면 과최적화예요.</p>
{_msg_html(message)}
<form action="/optimize/run" method="get" class="panel">
  <div class="row">
    <div><label>시장</label><select name="market">{_opts(MARKETS, MARKET_LABELS)}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT"></div>
    <div><label>전략</label><select name="strategy">{_opts(list(_OPT_GRIDS), STRATEGY_LABELS)}</select></div>
  </div>
  <div class="row">
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="800"></div>
    <div><label>학습(IS) 길이</label><input name="is_window" value="250"></div>
    <div><label>검증(OOS) 길이</label><input name="oos_window" value="125"></div>
  </div>
  <button type="submit">최적화 실행</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.</p>"""
    return _page("최적화", body, "/optimize")


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

    label = STRATEGY_LABELS.get(strategy_name, strategy_name)
    body = f"""<p class="kicker">Walk-forward</p>
<h1>워크포워드 결과 · {html.escape(label)} · {html.escape(symbol)}</h1>
{_fallback_banner(df)}
<div class="card">
<p>IS(학습) 샤프: <b>{is_sharpe:.2f}</b> → OOS(검증) 샤프: <b>{oos_sharpe:.2f}</b></p>
<p>판정: {verdict}</p>
</div>
<div class="card">
<b>OOS(진짜 성과) 지표</b>
<pre style="font-size:12px;white-space:pre;overflow-x:auto">{html.escape(m.pretty())}</pre>
</div>
<div class="card">
<b>구간별 (IS 최적 파라미터 → OOS 성적)</b>
<div class="tablewrap"><table>
<tr><th>OOS 시작</th><th>파라미터</th><th>IS샤프</th><th>OOS샤프</th><th>OOS수익</th></tr>
{seg_rows}</table></div>
</div>
<p class="warn">⚠️ OOS(보지 않은 미래) 성적이 실전에서 기대할 수 있는 진짜 성과에 가깝습니다.
IS만 화려하면 그 전략은 과최적화된 것입니다.</p>"""
    return _page("최적화 결과", body, "/optimize")


def render_validate_form(message: str = "") -> str:
    """과최적화 검증 3종(워크포워드+DSR·PBO·CPCV) 폼 (pandas 불필요).

    전략 선택지는 CLI validate와 같은 기본 그리드(_OPT_GRIDS)를 가진
    전략으로 제한한다 — 그리드가 없으면 검증할 조합 자체가 없다.
    """

    body = f"""<p class="kicker">Validation</p>
<h1>과최적화 검증 (워크포워드+DSR · PBO · CPCV)</h1>
<p class="sub">"이 전략을 믿어도 되는가"를 세 가지 과최적화 탐지 도구로 한 화면에서
확인합니다. 셋 다 <b>탐지</b> 도구입니다 — 통과가 곧 수익은 아닙니다.</p>
{_msg_html(message)}
<form action="/validate/run" method="get" class="panel">
  <div class="row">
    <div><label>시장</label><select name="market">{_opts(MARKETS, MARKET_LABELS)}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT"></div>
    <div><label>전략</label><select name="strategy">{_opts(list(_OPT_GRIDS), STRATEGY_LABELS)}</select></div>
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
다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.</p>"""
    return _page("검증", body, "/validate")


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

    label = STRATEGY_LABELS.get(strategy_name, strategy_name)
    body = f"""<p class="kicker">Validation</p>
<h1>검증 결과 · {html.escape(label)} · {html.escape(symbol)} ({len(df)}봉)</h1>
<p class="sub">그리드: {html.escape(str(grid))}</p>
{_fallback_banner(df)}
{boxes}
<p class="warn">⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다.
다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.</p>"""
    return _page("검증 결과", body, "/validate")


def render_sweep_form(message: str = "") -> str:
    """파라미터 민감도 스윕 폼 페이지 (pandas 불필요)."""
    body = f"""<p class="kicker">Sensitivity</p>
<h1>파라미터 민감도 히트맵</h1>
<p class="sub">이동평균 교차(단기×장기)의 성과 지형을 그립니다.
넓은 초록 고원=견고, 외딴 점=과최적화.</p>
{_msg_html(message)}
<form action="/sweep/run" method="get" class="panel">
  <div class="row">
    <div><label>시장</label><select name="market">{_opts(MARKETS, MARKET_LABELS)}</select></div>
    <div><label>종목</label><input name="symbol" value="BTC/USDT"></div>
  </div>
  <div class="row">
    <div><label>타임프레임</label><input name="timeframe" value="1d"></div>
    <div><label>봉 개수</label><input name="limit" value="800"></div>
    <div><label>목표 지표</label><input name="objective" value="sharpe"></div>
  </div>
  <button type="submit">히트맵 생성</button>
</form>
<p class="warn">⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.</p>"""
    return _page("민감도 스윕", body, "/sweep")


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


# ── 방송 모드 (/broadcast) — 유튜브 라이브 송출용 전용 화면 ────────────────

_PRICE_CACHE: dict = {"ts": 0.0, "prices": {}}


def _live_prices(keys, ttl: float = 45.0) -> dict:
    """방송 화면용 현재가 — TTL 캐시로 데이터 소스 호출을 절제한다.

    실패한 종목은 조용히 빠진다(방송 화면은 '지연' 표기로 정직하게 처리).
    합성 폴백 가격은 절대 쓰지 않는다 — 방송에 가짜 시세를 내보낼 수는 없다.
    """
    import time
    now = time.time()
    if now - _PRICE_CACHE["ts"] < ttl and _PRICE_CACHE["prices"]:
        return _PRICE_CACHE["prices"]
    prices: dict = {}
    try:
        from quant.data import get_provider
        for key in keys:
            market, _, symbol = key.partition(":")
            if market == "portfolio":
                continue
            try:
                df = get_provider(market).get_ohlcv(symbol, "1d", limit=2)
                if len(df) and not df.attrs.get("synthetic_fallback"):
                    prices[key] = float(df["close"].iloc[-1])
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    if prices:
        _PRICE_CACHE.update(ts=now, prices=prices)
    return prices


def broadcast_json(state_dir: str = "state", with_live: bool = True) -> str:
    """방송 화면 데이터(JSON) — 확정 기록 + (가능하면) 실시간 평가 자산.

    '확정'은 매일 새벽 기록된 값, '실시간 평가'는 보유 포지션 × 현재가로
    지금 이 순간을 근사한 값이다. 화면에서 둘을 구분 표기한다(정직성).
    """
    import json
    from pathlib import Path

    accounts = []
    paper_dir = Path(state_dir) / "paper"
    files = sorted(paper_dir.glob("*.json")) if paper_dir.is_dir() else []
    for fp in files:
        try:
            st = json.loads(fp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        hist = st.get("history", [])
        if not hist:
            continue
        peak, mdd = 0.0, 0.0
        for r in hist:
            eq = float(r.get("equity", 0.0))
            peak = max(peak, eq)
            if peak > 0:
                mdd = min(mdd, eq / peak - 1)
        accounts.append({
            "key": f"{st.get('market', '?')}:{st.get('symbol', '?')}",
            "market": st.get("market"),
            "equity": hist[-1]["equity"],
            "return_pct": hist[-1].get("return_pct", 0.0),
            "mdd_pct": round(mdd * 100, 2),
            "date": hist[-1].get("date"),
            "reason": hist[-1].get("reason"),       # 새벽 판단 근거(사람 말)
            "spark": [r["equity"] for r in hist[-60:]],
            "spark_dates": [r.get("date") for r in hist[-60:]],
            "spark_price": [r.get("price") for r in hist[-60:]],
            "cash": st.get("cash"),
            "quantity": st.get("quantity"),
            "positions": st.get("positions"),      # 포트폴리오 계좌 전용
        })

    live = _live_prices([a["key"] for a in accounts]) if with_live else {}
    for a in accounts:
        le = None
        if a["market"] == "portfolio" and a.get("positions"):
            # 포지션이 비어 있으면 실시간 계산을 하지 않는다 — 현금만으로
            # '실시간 평가'를 만들면 확정 기록과 어긋난 숫자가 방송에 나간다.
            vals, missing = [], False
            for key, pos in a["positions"].items():
                p = live.get(key)
                if p is None:
                    missing = True
                    break
                vals.append(float(pos.get("quantity", 0.0)) * p)
            if not missing and a.get("cash") is not None:
                le = float(a["cash"]) + sum(vals)
        elif a.get("cash") is not None and a.get("quantity") is not None:
            p = live.get(a["key"])
            if p is not None:
                le = float(a["cash"]) + float(a["quantity"]) * p
        if le is not None:
            a["live_equity"] = round(le, 2)
            a["live_return_pct"] = round((le / 10000 - 1) * 100, 2)
        a.pop("cash", None); a.pop("quantity", None); a.pop("positions", None)

    # 어젯밤 재학습 서사 — 방송 상단 '오늘의 소식' 배너와 차트 마커용
    swaps, news = [], ""
    hist_file = Path(state_dir) / "retrain_history.jsonl"
    if hist_file.exists():
        recs = []
        for line in hist_file.read_text(encoding="utf-8").splitlines()[-400:]:
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass
        swaps = [{"date": r.get("asof"),
                  "key": f"{r.get('market')}:{r.get('symbol')}",
                  "strategy": r.get("champion_strategy")}
                 for r in recs if r.get("promoted")]
        if recs:
            last_day = max(r.get("asof", "") for r in recs)
            day_recs = [r for r in recs if r.get("asof") == last_day]
            promoted = [f"{r.get('symbol')}→{r.get('champion_strategy')}"
                        for r in day_recs if r.get("promoted")]
            if promoted:
                news = (f"🔁 어젯밤 재학습({last_day}): 챔피언 교체 "
                        + ", ".join(promoted))
            else:
                news = (f"🌙 어젯밤 재학습({last_day}): {len(day_recs)}종목 대결 "
                        "— 전원 챔피언 유지 (확실히 나은 후보 없음, 정상)")

    from quant.utils.jsonio import sanitize
    return json.dumps(sanitize({
        "accounts": accounts,
        "news": news,
        "swaps": swaps,
        "live_prices": live,
        "live_available": bool(live),
        "disclaimer": ("본 방송의 계좌는 가상 자금 10,000원 모의투자이며 실제 "
                       "돈이 아닙니다. 과거·현재 성과는 미래 수익을 보장하지 "
                       "않으며, 본 방송은 투자 자문·권유가 아닙니다."),
    }), ensure_ascii=False)


_CANDLE_CACHE: dict = {}


def candles_json(key: str, tf: str = "1m", limit: int = 90,
                 state_dir: str = "state", ttl: float = 12.0) -> str:
    """방송용 실시간 캔들(1분봉) — 거래소에서 직접 받아 TTL 캐시로 반환한다.

    ⚠️ 전략의 매매 판단은 일봉(하루 1회)이다. 이 캔들은 '보여주기 위한 실시간
    시세'이며 화면에도 그렇게 라벨링한다. 합성 폴백 시세는 절대 내보내지
    않는다 — 방송에 가짜 캔들을 그릴 수는 없다(빈 응답이 정직하다).
    """
    import json
    import re
    import time
    from pathlib import Path

    market, _, symbol = key.partition(":")
    now = time.time()
    cached = _CANDLE_CACHE.get((key, tf))
    if cached and now - cached[0] < ttl:
        return cached[1]

    candles = []
    try:
        from quant.data import get_provider
        df = get_provider(market).get_ohlcv(symbol, tf, limit=limit)
        if len(df) and not df.attrs.get("synthetic_fallback"):
            candles = [[str(ix)[11:16] or str(ix)[:10],
                        round(float(r["open"]), 6), round(float(r["high"]), 6),
                        round(float(r["low"]), 6), round(float(r["close"]), 6)]
                       for ix, r in df.tail(limit).iterrows()]
    except Exception:  # noqa: BLE001
        pass

    # 보유 정보(진입가·방향) 오버레이용 — 페이퍼 상태에서 읽는다
    position = None
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{market}_{symbol}")
    fp = Path(state_dir) / "paper" / f"{safe}.json"
    if fp.exists():
        try:
            st = json.loads(fp.read_text(encoding="utf-8"))
            qty = float(st.get("quantity", 0.0))
            if abs(qty) > 0:
                position = {"quantity": qty,
                            "avg_price": float(st.get("avg_price", 0.0)),
                            "side": "매수 보유" if qty > 0 else "매도 보유"}
            hist = st.get("history", [])
            if hist and position is not None:
                position["weight"] = hist[-1].get("weight")
        except (ValueError, OSError):
            pass

    out = json.dumps({"key": key, "tf": tf, "candles": candles,
                      "position": position,
                      "last": candles[-1][4] if candles else None},
                     ensure_ascii=False)
    if candles:
        _CANDLE_CACHE[(key, tf)] = (now, out)
    return out


def render_broadcast() -> str:
    """유튜브 라이브 송출용 전체 화면 대시보드 (OBS 브라우저 소스 1920×1080).

    구성: 상단 '오늘의 소식' 배너(어젯밤 재학습 서사) → 히어로 전문 차트
    (통합 계좌, 축·그리드·기준선 분할·교체 마커·드로다운) → 종목 카드
    (각각 새벽 판단 근거 한 줄) → 하단 흐르는 시세바(티커 테이프) → 고지.
    판단 근거는 '새벽 기준'으로 시점을 명시한다 — 장중에 근거가 바뀌는
    것처럼 보이게 하지 않는다(정직성).
    """
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant · 방송 모드</title>{_FAVICON}<style>
:root{{color-scheme:dark;--bg:#07080b;--bg2:#0e1013;--fg:#f4f5f7;--muted:#8f96a3;
  --dim:#5c6370;--line:#1e2128;--accent:#4c7dff;--ok:#3fb96f;--bad:#e5484d}}
*{{box-sizing:border-box;margin:0}}
body{{font-family:"Pretendard Variable",Pretendard,-apple-system,system-ui,
  "Apple SD Gothic Neo","Malgun Gothic",sans-serif;background:var(--bg);
  color:var(--fg);overflow:hidden;height:100vh;display:flex;flex-direction:column;
  font-variant-numeric:tabular-nums}}
header{{display:flex;align-items:center;gap:16px;padding:14px 30px 6px}}
.logo{{font-weight:800;font-size:20px;letter-spacing:.14em}}
.logo em{{font-style:normal;color:var(--accent)}}
.live{{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--bad);
  font-weight:700}}
.live i{{width:8px;height:8px;border-radius:50%;background:var(--bad);
  animation:blink 1.4s infinite}}
@keyframes blink{{50%{{opacity:.25}}}}
#news{{font-size:14px;color:var(--muted);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;flex:1}}
#clock{{font-size:15px;color:var(--muted)}}
.hero{{margin:4px 30px;background:var(--bg2);border:1px solid var(--line);
  border-radius:14px;padding:14px 20px 8px;display:flex;gap:26px}}
.hero .nums{{min-width:300px}}
.k{{font-size:12.5px;color:var(--muted);font-weight:650}}
.eq{{font-size:44px;font-weight:800;letter-spacing:-.02em;line-height:1.2}}
.pct{{font-size:20px;font-weight:700}}
.pos{{color:var(--ok)}}.neg{{color:var(--bad)}}
.meta{{font-size:12px;color:var(--muted);margin-top:2px}}
.hero .chartwrap{{flex:1;min-width:0}}
.candle{{margin:0 30px 4px;background:var(--bg2);border:1px solid var(--line);
  border-radius:14px;padding:10px 20px 6px;height:274px;display:flex;
  flex-direction:column}}
.candle .head{{display:flex;align-items:baseline;gap:12px;font-size:13px;
  color:var(--muted)}}
.candle .sym{{font-size:16px;font-weight:800;color:var(--fg)}}
.candle .px{{font-size:16px;font-weight:700}}
.candle .body{{flex:1;min-height:0}}
.grid{{flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:10px;
  padding:8px 30px;overflow:hidden}}
.card{{background:var(--bg2);border:1px solid var(--line);border-radius:12px;
  padding:10px 14px 6px;display:flex;flex-direction:column;min-height:0}}
.card .eq2{{font-size:20px;font-weight:800}}
.card .pct2{{font-size:13px;font-weight:700}}
.reason{{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.45;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden}}
.tape{{background:#0b0d11;border-top:1px solid var(--line);overflow:hidden;
  white-space:nowrap;padding:7px 0;font-size:14px}}
.tape .inner{{display:inline-block;animation:scroll 40s linear infinite}}
@keyframes scroll{{from{{transform:translateX(0)}}to{{transform:translateX(-50%)}}}}
.tape b{{margin:0 6px 0 22px;color:var(--fg)}}
footer{{background:#141313;border-top:1px solid var(--line);color:#e9b6b6;
  font-size:13px;padding:8px 30px;font-weight:600}}
svg text{{font-family:inherit}}
</style></head><body>
<header><span class="logo">QUANT<em>.</em></span>
<span class="live"><i></i>LIVE</span>
<span id="news">만원 챌린지 — 가상 자금 자동 모의투자</span>
<span id="clock">—</span></header>
<div class="hero" id="hero"><div class="nums"><div class="k">불러오는 중…</div></div></div>
<div class="candle" id="candle" style="display:none"><div class="head">
  <span class="sym" id="c-sym">—</span><span id="c-px" class="px">—</span>
  <span id="c-pos"></span>
  <span style="margin-left:auto">실시간 1분봉 — 시세는 실시간, <b>매매 판단은 일봉(하루 1회 새벽)</b></span>
</div><div class="body" id="c-body"></div></div>
<div class="grid" id="grid"></div>
<div class="tape"><div class="inner" id="tape">&nbsp;</div></div>
<footer id="disc">⚠️ 모의투자(가짜 돈)입니다 — 실제 돈이 아니며, 수익을 보장하지
않고, 투자 자문·권유가 아닙니다.</footer>
<script>
function esc(s){{const d=document.createElement("div");d.textContent=String(s);return d.innerHTML}}
function won(v){{return Math.round(v).toLocaleString("ko-KR")+"원"}}
function pct(v){{return (v>=0?"+":"")+Number(v).toFixed(2)+"%"}}
function niceTicks(mn,mx,n){{
  const span=(mx-mn)||1,step0=span/n,mag=Math.pow(10,Math.floor(Math.log10(step0)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(sv=>span/sv<=n)||mag*10;
  const t=[];for(let v=Math.ceil(mn/step)*step;v<=mx;v+=step)t.push(v);return t}}
// 전문 차트: 축·그리드·기준선(10,000) 상하 분할 영역·교체 마커·현재값 태그·드로다운
function proChart(o){{
  const v=o.vals; if(!v||v.length<2) return "";
  const W=o.w,H=o.h,padR=64,padB=o.axes?16:4,padT=6;
  const ddH=o.dd?Math.round(H*0.18):0, mainH=H-ddH-padB-padT;
  const base=o.base||10000;
  let mn=Math.min(...v,base),mx=Math.max(...v,base);
  if(o.bench){{mn=Math.min(mn,...o.bench);mx=Math.max(mx,...o.bench)}}
  const sp=(mx-mn)||1;
  const X=i=>i/(v.length-1)*(W-padR);
  const Y=val=>padT+(1-(val-mn)/sp)*mainH;
  const line=a=>a.map((val,i)=>`${{X(i).toFixed(1)}},${{Y(val).toFixed(1)}}`).join(" ");
  let out=`<svg viewBox="0 0 ${{W}} ${{H}}" style="width:100%;height:100%" preserveAspectRatio="none">`;
  // 그리드+우측 가격축
  if(o.axes){{niceTicks(mn,mx,4).forEach(t=>{{
    out+=`<line x1="0" y1="${{Y(t)}}" x2="${{W-padR}}" y2="${{Y(t)}}" stroke="var(--line)" stroke-width="1"/>
      <text x="${{W-padR+8}}" y="${{Y(t)+4}}" font-size="11" fill="var(--dim)">${{Math.round(t).toLocaleString()}}</text>`}});
    // 하단 시간축: 월 경계
    if(o.dates){{let pm="";o.dates.forEach((d,i)=>{{const m=(d||"").slice(0,7);
      if(m&&m!==pm){{pm=m;if(i>0)out+=`<text x="${{X(i)}}" y="${{H-3}}" font-size="10" fill="var(--dim)">${{m.slice(5)}}월</text>`}}}})}}}}
  // 기준선 상하 분할 영역
  const yb=Y(base), gid="g"+Math.floor(Math.random()*1e9);
  out+=`<defs><linearGradient id="${{gid}}u" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="var(--ok)" stop-opacity=".28"/>
    <stop offset="1" stop-color="var(--ok)" stop-opacity="0"/></linearGradient>
    <linearGradient id="${{gid}}d" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0" stop-color="var(--bad)" stop-opacity=".28"/>
    <stop offset="1" stop-color="var(--bad)" stop-opacity="0"/></linearGradient>
    <clipPath id="${{gid}}cu"><rect x="0" y="0" width="${{W-padR}}" height="${{yb}}"/></clipPath>
    <clipPath id="${{gid}}cd"><rect x="0" y="${{yb}}" width="${{W-padR}}" height="${{H-yb}}"/></clipPath></defs>`;
  const area=`M0,${{yb}} L`+line(v)+` L${{X(v.length-1)}},${{yb}} Z`;
  out+=`<path d="${{area}}" fill="url(#${{gid}}u)" clip-path="url(#${{gid}}cu)"/>
    <path d="${{area}}" fill="url(#${{gid}}d)" clip-path="url(#${{gid}}cd)"/>
    <line x1="0" y1="${{yb}}" x2="${{W-padR}}" y2="${{yb}}" stroke="var(--dim)"
      stroke-width="1" stroke-dasharray="5 4"/>`;
  // 벤치마크(그냥 보유) 점선
  if(o.bench)out+=`<polyline points="${{line(o.bench)}}" fill="none" stroke="var(--dim)"
    stroke-width="1.4" stroke-dasharray="4 4"/>`;
  // 본선
  const up=v[v.length-1]>=base;
  out+=`<polyline points="${{line(v)}}" fill="none" stroke="${{up?"var(--ok)":"var(--bad)"}}" stroke-width="2.2"/>`;
  // 챔피언 교체 마커 ◆
  if(o.markers&&o.dates)o.markers.forEach(d=>{{const i=o.dates.indexOf(d);
    if(i>=0)out+=`<path d="M${{X(i)}},${{Y(v[i])-9}} l5,5 -5,5 -5,-5 z" fill="var(--accent)"/>`}});
  // 현재값 점+태그
  const lx=X(v.length-1),ly=Y(v[v.length-1]);
  out+=`<circle cx="${{lx}}" cy="${{ly}}" r="3.4" fill="${{up?"var(--ok)":"var(--bad)"}}">
    <animate attributeName="opacity" values="1;.3;1" dur="1.6s" repeatCount="indefinite"/></circle>
    <rect x="${{W-padR+2}}" y="${{ly-10}}" width="${{padR-6}}" height="20" rx="5"
      fill="${{up?"var(--ok)":"var(--bad)"}}"/>
    <text x="${{W-padR+(padR-6)/2+2}}" y="${{ly+4}}" font-size="11" font-weight="700"
      fill="#07080b" text-anchor="middle">${{Math.round(v[v.length-1]).toLocaleString()}}</text>`;
  // 드로다운 서브차트(수면 아래)
  if(o.dd){{let peak=v[0];const dd=v.map(x=>{{peak=Math.max(peak,x);return peak?x/peak-1:0}});
    const dmn=Math.min(...dd,-0.001);
    const DY=val=>H-padB-ddH+( -val/-dmn)*ddH;
    const dline=dd.map((val,i)=>`${{X(i).toFixed(1)}},${{DY(val).toFixed(1)}}`).join(" ");
    out+=`<path d="M0,${{H-padB-ddH}} L${{dline}} L${{X(v.length-1)}},${{H-padB-ddH}} Z"
      fill="var(--bad)" fill-opacity=".22"/>
      <text x="2" y="${{H-padB-ddH+11}}" font-size="9.5" fill="var(--dim)">낙폭</text>`}}
  return out+"</svg>"}}
function card(a){{
  const eq=a.live_equity??a.equity, rp=a.live_return_pct??a.return_pct;
  const liveTag=a.live_equity!=null?"실시간 평가":"확정 "+esc(a.date||"");
  const cls=rp>=0?"pos":"neg";
  return `<div class="card"><div class="k">${{esc(a.key)}} · ${{liveTag}}</div>
    <div><span class="eq2 ${{cls}}">${{won(eq)}}</span>
    <span class="pct2 ${{cls}}">${{pct(rp)}}</span></div>
    <div class="reason">${{a.reason?"🧭 "+esc(a.reason):"최대낙폭 "+a.mdd_pct+"%"}}</div>
    <div style="flex:1;min-height:0;margin-top:2px">${{proChart({{vals:a.spark,dates:a.spark_dates,w:320,h:58,axes:false}})}}</div></div>`}}
async function tick(first){{
  try{{
    const q=(location.search?location.search+"&":"?")+(first?"nolive=1":"x=1");
    const r=await fetch("/api/broadcast"+q,{{cache:"no-store"}});
    if(!r.ok)return;
    const d=await r.json();
    const accs=d.accounts||[]; if(!accs.length)return;
    const pf=accs.find(a=>a.market==="portfolio");
    const rest=accs.filter(a=>a.market!=="portfolio");
    if(d.news)document.getElementById("news").textContent=d.news;
    const hero=pf||rest[0];
    if(hero){{
      const eq=hero.live_equity??hero.equity, rp=hero.live_return_pct??hero.return_pct;
      const cls=rp>=0?"pos":"neg";
      const mk=(d.swaps||[]).filter(s=>s.key===hero.key).map(s=>s.date);
      document.getElementById("hero").innerHTML=
        `<div class="nums"><div class="k">${{hero.market==="portfolio"?"📦 통합 분산 계좌 (8종목)":esc(hero.key)}}
          · ${{hero.live_equity!=null?"실시간 평가":"확정 "+esc(hero.date||"")}}</div>
        <div class="eq ${{cls}}">${{won(eq)}}</div>
        <div class="pct ${{cls}}">${{pct(rp)}} <span class="meta">시작 10,000원</span></div>
        <div class="meta">최대낙폭 ${{hero.mdd_pct}}% · ─ 전략 ┄ 그냥 보유 ◆ 챔피언 교체</div></div>
        <div class="chartwrap">${{proChart({{vals:hero.spark,dates:hero.spark_dates,
          w:1280,h:170,axes:true,dd:true,markers:mk,
          bench:(hero.spark_price&&hero.spark_price[0])?hero.spark_price.map(p=>10000*p/hero.spark_price[0]):null}})}}</div>`;
    }}
    document.getElementById("grid").innerHTML=rest.map(card).join("");
    cKeys=rest.filter(a=>a.market==="crypto").map(a=>a.key)
      .concat(rest.filter(a=>a.market!=="crypto").map(a=>a.key));
    // 티커 테이프 — 실시간가(가능 시) 또는 확정 기록
    const items=rest.map(a=>{{
      const lp=(d.live_prices||{{}})[a.key];
      const base=a.spark_price&&a.spark_price.length?a.spark_price[a.spark_price.length-1]:null;
      let chg=null; if(lp&&base)chg=(lp/base-1)*100;
      const px=lp??base;
      const c=(chg??a.return_pct)>=0?"var(--ok)":"var(--bad)";
      const arrow=(chg??a.return_pct)>=0?"▲":"▼";
      return `<b>${{esc(a.key.split(":")[1]||a.key)}}</b>`+
        (px?`${{Number(px).toLocaleString()}} `:"")+
        `<span style="color:${{c}}">${{arrow}} ${{pct(chg??a.return_pct)}}</span>`}}).join("");
    document.getElementById("tape").innerHTML=items+items;   // 이음새 없는 루프
    if(d.disclaimer)document.getElementById("disc").textContent="⚠️ "+d.disclaimer;
  }}catch(e){{}}
}}
let cKeys=[],cIdx=0;
function candleChart(d){{
  const c=d.candles; if(!c||c.length<5) return "";
  const W=1560,H=200,padR=70,padB=14;
  let mn=Math.min(...c.map(x=>x[3])),mx=Math.max(...c.map(x=>x[2]));
  if(d.position&&d.position.avg_price){{mn=Math.min(mn,d.position.avg_price);mx=Math.max(mx,d.position.avg_price)}}
  const sp=(mx-mn)||1,mainH=H-padB-4;
  const N=c.length,cw=(W-padR)/N,bw=Math.max(2,cw*0.62);
  const Y=v=>4+(1-(v-mn)/sp)*mainH;
  let out=`<svg viewBox="0 0 ${{W}} ${{H}}" style="width:100%;height:100%" preserveAspectRatio="none">`;
  niceTicks(mn,mx,4).forEach(t=>{{out+=`<line x1="0" y1="${{Y(t)}}" x2="${{W-padR}}" y2="${{Y(t)}}"
    stroke="var(--line)"/><text x="${{W-padR+8}}" y="${{Y(t)+4}}" font-size="11"
    fill="var(--dim)">${{t.toLocaleString()}}</text>`}});
  c.forEach((k,i)=>{{
    const [t,o,h,l,cl]=k,x=i*cw+cw/2,up=cl>=o;
    const col=up?"var(--ok)":"var(--bad)";
    out+=`<line x1="${{x}}" y1="${{Y(h)}}" x2="${{x}}" y2="${{Y(l)}}" stroke="${{col}}" stroke-width="1"/>
      <rect x="${{x-bw/2}}" y="${{Y(Math.max(o,cl))}}" width="${{bw}}"
      height="${{Math.max(1,Math.abs(Y(o)-Y(cl)))}}" fill="${{col}}"/>`;
    if(i%15===0)out+=`<text x="${{x}}" y="${{H-2}}" font-size="10" fill="var(--dim)"
      text-anchor="middle">${{t}}</text>`}});
  // 진입가 라인(보유 시)
  if(d.position&&d.position.avg_price>=mn&&d.position.avg_price<=mx){{
    const yv=Y(d.position.avg_price);
    out+=`<line x1="0" y1="${{yv}}" x2="${{W-padR}}" y2="${{yv}}" stroke="var(--accent)"
      stroke-width="1.2" stroke-dasharray="6 4"/>
      <text x="4" y="${{yv-4}}" font-size="10.5" fill="var(--accent)">진입가 ${{d.position.avg_price.toLocaleString()}}</text>`}}
  // 현재가 태그
  const last=c[c.length-1][4],ly=Y(last),lu=last>=c[c.length-1][1];
  out+=`<line x1="0" y1="${{ly}}" x2="${{W-padR}}" y2="${{ly}}" stroke="var(--dim)"
    stroke-width="0.7" stroke-dasharray="2 3"/>
    <rect x="${{W-padR+2}}" y="${{ly-10}}" width="${{padR-6}}" height="20" rx="5"
    fill="${{lu?"var(--ok)":"var(--bad)"}}"/>
    <text x="${{W-padR+(padR-6)/2+2}}" y="${{ly+4}}" font-size="11" font-weight="700"
    fill="#07080b" text-anchor="middle">${{last.toLocaleString()}}</text>`;
  return out+"</svg>"}}
async function candleTick(rotate){{
  if(!cKeys.length)return;
  if(rotate)cIdx=(cIdx+1)%cKeys.length;
  for(let n=0;n<cKeys.length;n++){{
    const key=cKeys[(cIdx+n)%cKeys.length];
    try{{
      const r=await fetch("/api/candles?key="+encodeURIComponent(key)+
        (location.search?"&"+location.search.slice(1):""),{{cache:"no-store"}});
      if(!r.ok)continue;
      const d=await r.json();
      if(!d.candles||d.candles.length<5)continue;   // 장 마감 등 → 다음 종목
      cIdx=(cIdx+n)%cKeys.length;
      const el=document.getElementById("candle");el.style.display="flex";
      document.getElementById("c-sym").textContent=key.split(":")[1]||key;
      const last=d.candles[d.candles.length-1],prev=d.candles[0];
      const chg=(last[4]/prev[1]-1)*100,cls=chg>=0;
      const px=document.getElementById("c-px");
      px.textContent=Number(last[4]).toLocaleString()+" ("+pct(chg)+")";
      px.style.color=cls?"var(--ok)":"var(--bad)";
      document.getElementById("c-pos").textContent=
        d.position?("🧭 "+d.position.side+(d.position.weight!=null?" · 비중 "+Math.round(d.position.weight*100)+"%":"")):"관망 (현금)";
      document.getElementById("c-body").innerHTML=candleChart(d);
      return;
    }}catch(e){{}}
  }}
}}
setInterval(tick,15000);tick(true).then(()=>tick());
// 캔들 첫 성공까지 2초 간격 재시도(첫 로딩 레이스 방지), 이후 15초 갱신
let cReady=false;
async function candleBoot(){{
  if(cReady)return;
  await candleTick(false);
  if(document.getElementById("candle").style.display==="flex"){{cReady=true;return}}
  setTimeout(candleBoot,2000);
}}
setTimeout(candleBoot,600);
setInterval(()=>candleTick(false),15000);
setInterval(()=>candleTick(true),45000);
setTimeout(()=>candleTick(false),800);
setInterval(()=>{{document.getElementById("clock").textContent=new Date().toLocaleString("ko-KR")}},1000);
</script></body></html>"""
