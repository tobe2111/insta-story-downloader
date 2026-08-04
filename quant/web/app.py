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
