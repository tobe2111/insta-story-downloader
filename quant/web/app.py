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
# Pretendard는 CDN(무료·오픈소스 폰트)에서 받아 어디서나 같은 글꼴로 보이게
# 한다. 오프라인이면 font-display:swap 덕에 시스템 한글 폰트로 조용히 폴백
# — 화면이 깨지거나 기다리는 일은 없다.
_STYLE = """
 :root{color-scheme:dark;
   --bg:#0a0b0e;--bg2:#0e1013;--bg3:#13161b;--fg:#f4f5f7;--muted:#8f96a3;--dim:#5c6370;
   --line:#1e2128;--line-strong:#2a2e37;--accent:#4c7dff;--accent-soft:rgba(76,125,255,.11);
   --ok:#3fb96f;--bad:#e5484d;--warn:#d9a13b;--radius:12px;
   /* 시세 색 — 한국 증권사 관례(상승=빨강, 하락=파랑). 성공/오류(--ok/--bad)와 구분 */
   --up:#f04452;--down:#3182f6;
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
 .pos{color:var(--up)}.neg{color:var(--down)}
 /* 얇은 실시간 시세 바 — 증권사 상단 지수 바처럼 스르륵 흐른다 */
 .tickbar{margin:0 -22px;border-bottom:1px solid var(--line);background:var(--bg2);
   overflow:hidden;white-space:nowrap;height:30px;line-height:30px;font-size:12px;
   font-variant-numeric:tabular-nums}
 .tickbar .tin{display:inline-block;animation:tick 45s linear infinite;will-change:transform}
 .tickbar:hover .tin{animation-play-state:paused}
 @keyframes tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
 .tickbar b{margin:0 5px 0 20px;color:var(--fg);font-weight:650}
 .tickbar .u{color:var(--up)}.tickbar .d{color:var(--down)}
 .tickbar .tag{font-size:10px;color:var(--dim);margin-left:3px}
 @media(max-width:560px){
   .wrap{padding:0 14px 48px}.topbar{margin:0 -14px 6px;padding:0 14px}
   .tickbar{margin:0 -14px}
   .card,form.panel{padding:16px}
   .steps{flex-wrap:wrap}.steps a{flex:1 1 50%;border-bottom:1px solid var(--line)}
 }
"""

# Pretendard 웹폰트 — jsDelivr는 CORS 허용이라 로컬 조종석에서도 로드된다.
# 오프라인 환경에서는 시스템 폰트 폴백(스타일의 font-family 목록)이 그대로 동작.
_FONT = ('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/'
         'pretendard@v1.3.9/dist/web/variable/'
         'pretendardvariable-dynamic-subset.min.css">')

# 전문 금융 차트 엔진 (TradingView Lightweight Charts, Apache-2.0 오픈소스).
# 실제 증권사·거래소가 쓰는 캔들 엔진 — 크로스헤어·가격축·부드러운 갱신.
# 로드 실패(오프라인) 시 기존 SVG 렌더러로 폴백하므로 필수 의존성이 아니다.
_LWC = ('<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/'
        'dist/lightweight-charts.standalone.production.js"></script>')

# 브라우저 탭 아이콘 (외부 파일 없이 data URI) — 랜딩과 같은 심볼
_FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
            '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E'
            '%3Crect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%234c7dff%22/%3E'
            '%3Cpath d=%22M8 22 L14 14 L18 18 L24 9%22 stroke=%22white%22 '
            'stroke-width=%223%22 fill=%22none%22 stroke-linecap=%22round%22 '
            'stroke-linejoin=%22round%22/%3E%3C/svg%3E">')

_NAV_ITEMS = [("/", "백테스트"), ("/portfolio", "포트폴리오"),
              ("/screener", "종목선별"), ("/sweep", "민감도"),
              ("/optimize", "최적화"), ("/validate", "검증"), ("/monitor", "감시"),
              ("/deposit", "입금")]


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


# 얇은 실시간 시세 바 — 페이퍼 계좌의 종목 시세를 증권사 지수 바처럼 흘려보낸다.
# 첫 페인트는 확정 기록(nolive=1, 빠름), 이후 25초마다 실시간가로 갱신.
# 기록이 하나도 없으면(신규 설치) 바를 조용히 숨긴다.
_TICKER_JS = """<script>
(function(){
  var el=document.getElementById('tickbar'); if(!el)return;
  function esc(s){var d=document.createElement('div');d.textContent=String(s);return d.innerHTML}
  function render(d){
    var accs=(d.accounts||[]).filter(function(a){return a.market!=='portfolio'});
    if(!accs.length){el.parentElement.style.display='none';return}
    var lp=d.live_prices||{};
    var items=accs.map(function(a){
      var base=(a.spark_price&&a.spark_price.length)?a.spark_price[a.spark_price.length-1]:null;
      var live=lp[a.key], px=live!=null?live:base;
      if(px==null)return '';
      var chg=(live!=null&&base)?((live/base-1)*100):null;
      var v=(chg!=null?chg:(a.return_pct||0));
      var cls=v>=0?'u':'d', arrow=v>=0?'▲':'▼';
      return '<b>'+esc(a.name||(a.key.split(':')[1]||a.key))+'</b>'
        +Number(px).toLocaleString()
        +' <span class="'+cls+'">'+arrow+' '+(v>=0?'+':'')+v.toFixed(2)+'%</span>'
        +'<span class="tag">'+(live!=null?'실시간':'확정')+'</span>';
    }).join('');
    if(!items){el.parentElement.style.display='none';return}
    el.innerHTML=items+items;   /* 이음새 없는 루프 */
  }
  function tick(first){
    fetch('/api/broadcast'+(first?'?nolive=1':''),{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null})
      .then(function(d){if(d)render(d)}).catch(function(){});
  }
  tick(true); setInterval(function(){tick(false)},25000);
})();
</script>"""


def _page(title: str, body: str, active: str = "") -> str:
    """공통 문서 골격 — 헤더·내비게이션·시세 바·로딩 오버레이·스타일을 한곳에서."""
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>Quant · {html_escape(title)}</title>{_FAVICON}{_FONT}'
            f'<style>{_STYLE}</style></head><body><div class="wrap">\n'
            f'{_nav(active)}\n'
            f'<div class="tickbar"><div class="tin" id="tickbar">&nbsp;</div></div>\n'
            f'{body}\n</div>{_BUSY}{_UX_JS}{_TICKER_JS}</body></html>')


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
      // 손익·낙폭은 **서버가 재서 보낸 값**(s.kpi)을 그대로 쓴다.
      // 여기서 다시 계산하면 안 되는 이유(감사 197): 예전에는 이 자리에서
      //     const pnl = cur/st - 1
      // 를 계산했는데, 그건 **입금을 수익으로 센다** — 8만원 계좌에 92만원을
      // 넣고 95만원이 되면 화면이 "+1087.50%"라고 말했다(실제 -5.00%).
      // 낙폭도 같이 거짓이 된다(입금이 고점을 끌어올려 직전 손실을 지운다).
      // 게다가 이 함수는 5초마다 돌아 서버가 계산한 값을 덮어쓰므로,
      // 조종석만 고쳤다면 화면이 잠깐 맞았다가 조용히 되돌아갔을 것이다.
      // 판정은 ledger_basics.equity_curve_kpis 한 곳에만 둔다.
      // (잘려나간 과거의 seed 처리도 그 함수 안에 있다 — 감사 ㊿.)
      const kpi = (s && s.kpi) || {};
      const cur = (typeof kpi.current === 'number') ? kpi.current : eq[eq.length-1];
      const pnl = Number(kpi.pnl) || 0;
      const dd = Number(kpi.max_drawdown) || 0;
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
    // orders는 스냅샷에서 최근 20건만 실린다 — 누적 건수는 order_count를 쓴다.
    // 예전에는 orders.length를 '거래횟수'로 보여줘 20에서 영원히 멈췄다.
    setTxtSafe('kpi-trades', String((s && typeof s.order_count === 'number')
                                    ? s.order_count : orders.length));
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
    """현재 봇 상태를 JSON 문자열로 반환한다 (/api/state 용). 없으면 '{}'.

    손익·낙폭을 **여기서 재서 함께 보낸다**(감사 197). 브라우저가 자산
    곡선을 받아 스스로 계산하면 입금 보정을 놓친다 — 실제로 놓쳤고, 그
    화면이 5초마다 조종석의 올바른 값을 덮어쓰고 있었다. 판정은 한 곳에서만.
    """
    import json

    st = read_state(state_paths) or {}
    if st:
        from quant.live.ledger_basics import equity_curve_kpis
        st = dict(st)
        st["kpi"] = equity_curve_kpis(st)
    return json.dumps(st, ensure_ascii=False)


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
    """방송·조종석 화면용 현재가 — **원화로 환산해서** 돌려준다.

    ⚠️ 감사 231(2026-08-13): 여기는 감사 212가 안 닿은 채 남아 있었다.
    시세를 **현지 통화 그대로** 돌려주는데, 호출부는 그 값을 원화 장부의
    현금에 그대로 더한다:

        평가 = 현금(원) + 수량 × 달러가격        ← 단위가 섞인다

    실측(오늘 보유 기준): 올바른 평가 1,327,716원 vs 조종석이 내는 값
    371,051원 — 계좌를 **27.9%로 축소**해 보여주고, 그 차이가 그대로
    '실시간 수익률'로 방송된다. 사이트는 감사 212에서 고쳤는데 조종석만
    옛 회계로 남아 있었다(같은 판정을 두 곳에 둔 대가 — 감사 219).

    환율을 못 받으면 해외 종목은 **빼고 돌려준다.** 그러면 호출부의
    `missing` 경로가 걸려 실시간 평가 자체를 만들지 않는다 — 1.0으로
    때우지 않는다는 규칙은 여기서도 같다.

    실패한 종목은 조용히 빠진다(화면은 '확정' 표기로 되돌아간다).
    합성 폴백 가격은 절대 쓰지 않는다 — 방송에 가짜 시세를 내보낼 수 없다.
    """
    import time
    now = time.time()
    if now - _PRICE_CACHE["ts"] < ttl and _PRICE_CACHE["prices"]:
        return _PRICE_CACHE["prices"]
    prices: dict = {}
    try:
        from quant.data import get_provider
        from quant.data.fx import needs_fx, to_krw, usdkrw

        # 환율은 **한 번만** 잡는다 — 종목마다 따로 받으면 같은 화면 안에서
        # 종목별로 다른 환율이 적용된다(감사 212와 같은 이유).
        rate = usdkrw()
        for key in keys:
            market, _, symbol = key.partition(":")
            if market == "portfolio":
                continue
            if needs_fx(market) and rate is None:
                continue                       # 환산 못 하면 값을 만들지 않는다
            try:
                df = get_provider(market).get_ohlcv(symbol, "1d", limit=2)
                if len(df) and not df.attrs.get("synthetic_fallback"):
                    px = to_krw(market, float(df["close"].iloc[-1]), rate)
                    if px is not None:
                        prices[key] = px
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    if prices:
        _PRICE_CACHE.update(ts=now, prices=prices)
    return prices


def _briefing_payload(state_dir: str = "state") -> dict | None:
    """방송용 브리핑 — 저장된 것이 있으면 헤드라인 목록을 돌려준다."""
    try:
        from quant.live.briefing import load_briefing
        b = load_briefing(state_dir)
        return b if b and b.get("items") else None
    except Exception:  # noqa: BLE001
        return None


# 조종석이 시세를 물어볼 워커 주소 — 배포된 사이트와 **같은 판정 사다리**를
# 쓰기 위한 중계다. 환경변수로 바꿀 수 있고, 비우면 기능이 꺼진다.
import os as _os

QUOTES_UPSTREAM = _os.getenv(
    "QUANT_QUOTES_URL", "https://quant.jiwon-1a2.workers.dev/api/quotes")
QUOTES_TIMEOUT = 4.0


def quotes_proxy(query: str) -> str:
    """조종석 → 워커 시세 중계 (판정 로직은 여기에 두지 않는다).

    ⚠️ 왜 중계인가: 한국투자증권·Finnhub 키는 Cloudflare 시크릿에만 있고,
    소스 선택·폴백·라벨 규칙은 워커 한 곳에만 있어야 한다. 같은 규칙을
    파이썬으로 한 벌 더 쓰면 언젠가 두 화면이 다른 값을 말한다(감사 219).

    실패는 **빈 응답**이다 — 조종석은 그때 확정값만 보여준다. 못 받은 것을
    옛 값으로 채워 '실시간'이라 쓰는 것이 감사 229에서 고친 결함이다.
    """
    import json as _json
    import urllib.error
    import urllib.request

    if not QUOTES_UPSTREAM:
        return _json.dumps({"quotes": {}, "off": "QUANT_QUOTES_URL 미설정"})
    url = QUOTES_UPSTREAM + ("?" + query if query else "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "quant-cockpit"})
        with urllib.request.urlopen(req, timeout=QUOTES_TIMEOUT) as r:
            body = r.read(200_000).decode("utf-8", "replace")
        _json.loads(body)                   # 형태 검증 — 쓰레기를 흘려보내지 않는다
        return body
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return _json.dumps({"quotes": {}, "error": str(exc)[:120]})


def broadcast_json(state_dir: str = "state", with_live: bool = True) -> str:
    """방송 화면 데이터(JSON) — 확정 기록 + (가능하면) 실시간 평가 자산.

    '확정'은 매일 새벽 기록된 값, '실시간 평가'는 보유 포지션 × 현재가로
    지금 이 순간을 근사한 값이다. 화면에서 둘을 구분 표기한다(정직성).
    """
    import json
    from pathlib import Path

    accounts = []
    shadow = None                   # 섀도 대조군(진화 없음) — 비교 표시용
    from quant.live.ledger_basics import ledger_files
    # 보관된 옛 장부는 계좌 목록에 넣지 않는다 — 같은 키를 덮어쓴다(감사 212).
    for fp in map(Path, ledger_files(state_dir)):
        try:
            st = json.loads(fp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        # 방송 화면도 사이트·킬스위치와 **같은 기준**을 쓴다.
        # 2026-08-11 감사: 여기만 (a) 배열 순서 그대로 (b) 자산 고점 대비로
        # 낙폭을 계산하고 있었다. 같은 규칙을 세 곳에 복사해 두면 두 곳만
        # 고치게 된다 — 이번이 정확히 그 경우였다. 공용 헬퍼로 통일한다.
        from quant.live.daily import (
            START_CASH, chrono, max_drawdown_from_index, twr_index,
        )
        hist = chrono(st.get("history", []))
        if not hist:
            continue
        if st.get("market") == "portfolio_shadow":
            shadow = {"equity": hist[-1]["equity"], "date": hist[-1].get("date")}
            continue                # 카드에는 안 띄우고 비교 수치로만 쓴다
        mdd = max_drawdown_from_index(twr_index(
            hist, st.get("deposits") or [],
            start_cash=float(st.get("start_cash", START_CASH))))
        from quant.markets import SYMBOL_INFO
        key0 = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        accounts.append({
            "key": key0,
            "name": SYMBOL_INFO.get(key0, {}).get("name"),
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
        if st.get("market") == "portfolio":        # 8마일 챌린지(8만원 → 1억) 필드
            from quant.live.daily import (
                GOAL_KRW, PORTFOLIO_START_CASH, time_weighted_return,
            )
            from quant.live.ledger_basics import (
                _flow_date, pending_deposits, principal_of,
            )
            deposits = st.get("deposits", [])
            sc = float(st.get("start_cash", PORTFOLIO_START_CASH))
            # 자산과 같은 시점의 원금 — 반영 전 입금은 빼고 센다(감사 211).
            # 조종석은 장부보다 자주 열리므로 이 창(입금 직후~다음 배치)에
            # 정확히 걸린다. 실측: 92만원 입금 직후 손익 -920,749원.
            principal = principal_of(sc, deposits)
            a = accounts[-1]
            tail = hist[-60:]
            base_series = []
            for r in tail:
                # 곡선의 기준선도 같은 자로 잰다 — 여기만 날짜로 재면 마지막
                # 점의 기준선과 위 principal이 어긋난다(같은 화면, 다른 원금).
                pr = sc + sum(dd["amount"] for dd in deposits
                              if _flow_date(dd) and _flow_date(dd) <= r["date"])
                base_series.append(round(pr, 2))
            # 낙폭 차트가 쓸 **입금 제거 성장 지수**(감사 224). 원자산으로
            # 그리면 입금이 고점을 끌어올려 그 직전 손실이 그림에서 사라진다 —
            # 감사 197에서 KPI는 고쳤는데 차트 오버레이가 남아 있었다.
            # 계산은 `twr_index` 한 곳에서만 한다(브라우저가 다시 세지 않게).
            from quant.live.ledger_basics import twr_index as _twr
            _idx = _twr(hist, deposits, start_cash=sc)
            a.update({"goal": GOAL_KRW,
                      "spark_twr": [round(x, 6) for x in _idx[-60:]],
                      "principal": round(principal, 2),
                      "pnl": round(float(a["equity"]) - principal, 2),
                      "twr_pct": time_weighted_return(hist, deposits,
                                                      start_cash=sc),
                      "deposits": deposits[-30:],
                      "random_pctile": hist[-1].get("random_pctile"),
                      "spark_base": base_series})
            waiting = pending_deposits(deposits)
            if waiting:
                a["pending_deposits"] = waiting
            # 종목별 보유(수량·평단·평가금액) — 조종석도 사이트와 **같은
            # 출처**로 준실시간 평가를 한다(사장님 2026-08-13: "실제 투자하는
            # 프로그램에서도 마찬가지"). 수량은 장부에서, 가격만 시세에서.
            from quant.live.ledger_basics import holdings_view
            a["holdings"] = holdings_view(st, float(a["equity"]))
            a["cash"] = round(float(st.get("cash") or 0.0)
                              - sum(float(d["amount"]) for d in waiting), 2)
            if hist[-1].get("fx_usdkrw") is not None:
                a["fx_usdkrw"] = hist[-1]["fx_usdkrw"]

    # 종목별 관련 뉴스(표시 전용) — 브리핑에서 해당 종목 항목을 찾아 붙인다
    briefing = _briefing_payload(state_dir)
    if briefing:
        by_sym = {}
        for it in briefing.get("items", []):
            if it.get("sym") and it["sym"] not in by_sym:
                by_sym[it["sym"]] = it
        for a in accounts:
            hit = by_sym.get(a["key"])
            if hit:
                a["news"] = {"title": hit["title"], "source": hit.get("source", "")}

    # ⚠️ 통합 계좌가 **들고 있는 종목**의 시세도 함께 받아야 한다(감사 231).
    #    예전에는 '계좌 키'만 넘겼는데 통합 계좌 키(portfolio:ALL)는 시세가
    #    없으므로 건너뛴다. 그 보유 종목의 가격은 "마침 같은 이름의 종목
    #    계좌가 있어서" 딸려 오던 것이었다 — 그 계좌가 기록이 없어 목록에서
    #    빠지는 날엔 한 종목 때문에 실시간 평가가 통째로 사라진다.
    _want = [a["key"] for a in accounts]
    for a in accounts:
        for k in (a.get("positions") or {}):
            if k not in _want:
                _want.append(k)
    live = _live_prices(_want) if with_live else {}
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
            # 기준: 통합 계좌는 원금(8마일 시작금+입금), 개별 계좌는 시작 만원
            # `or 10000`이면 원금이 **진짜 0**일 때도 10000으로 읽힌다
            # (감사 205 형제). '없음'과 '0'은 다르다 — 0이면 수익률을
            # 만들 수 없으니 만들지 않는다.
            basis = a.get("principal")
            basis = float(basis) if isinstance(basis, (int, float)) else 10000.0
            if basis > 0:
                a["live_return_pct"] = round((le / basis - 1) * 100, 2)
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
        # 섀도 대조군(진화 없음) — "오디션이 실제로 가치를 더하나"의 증거
        "shadow": shadow,
        # 조종석에서 방금 접수된 입금 — 장부 반영 전 '반영 중' 배너용(숫자에는
        # 반영하지 않는다 — 정본은 git 장부).
        "pending": _pending_deposits(),
        # 오늘의 시장 브리핑(표시 전용 — 판단에 사용되지 않음)
        "briefing": briefing,
        "disclaimer": ("본 방송의 계좌는 가상 자금 모의투자이며 실제 돈이 "
                       "아닙니다. 후원금 자체를 운용하지 않으며, 후원과 동일한 "
                       "금액만큼 '가상 원금'을 늘리는 매칭 이벤트입니다"
                       "(대가·지분 없음). 성과는 미래 수익을 보장하지 않으며 "
                       "투자 자문·권유가 아닙니다."),
    }), ensure_ascii=False)


_CANDLE_CACHE: dict = {}


_CHIP_CACHE: dict = {}


def indicator_chips(market: str, symbol: str, state_dir: str = "state",
                    ttl: float = 600.0) -> list[dict]:
    """'챔피언이 실제로 보는' 판단 지표 현재값 칩 — 일봉 기준(라벨에 명시).

    1분봉 위에 일봉 지표를 그리면 거짓이 되므로, 캔들 옆에 '판단 지표(일봉)'
    칩으로 분리해 보여준다. 챔피언 전략의 파라미터를 그대로 써서 계산한다.
    실패 시 빈 목록(방송은 조용히 생략).
    """
    import time
    key = (market, symbol)
    now = time.time()
    cached = _CHIP_CACHE.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]
    chips: list[dict] = []
    try:
        from quant.data import get_provider
        from quant.live.retrain import champion_spec
        df = get_provider(market).get_ohlcv(symbol, "1d", limit=260)
        if not len(df) or df.attrs.get("synthetic_fallback"):
            return []
        close = df["close"]
        spec = champion_spec(market, symbol, state_dir)
        params = spec.get("params", {})
        inner = params.get("inner", {}) if spec["strategy"] == "regime_wrap" else spec
        ip = inner.get("params", {}) if inner else {}

        def ma(n):
            return float(close.rolling(n).mean().iloc[-1])

        # 챔피언 전략별 핵심 지표
        if inner.get("strategy") == "ma_cross" or spec["strategy"] == "ma_cross":
            f_, s_ = int(ip.get("fast", 20)), int(ip.get("slow", 60))
            up = ma(f_) > ma(s_)
            chips.append({"label": f"{f_}일선 {'>' if up else '<'} {s_}일선",
                          "value": "상승 추세" if up else "하락/횡보",
                          "state": "pos" if up else "neg"})
        if inner.get("strategy") == "breakout" or spec["strategy"] == "breakout":
            w_ = int(ip.get("window", 55))
            hi = float(df["high"].rolling(w_).max().iloc[-2])
            px = float(close.iloc[-1])
            chips.append({"label": f"{w_}일 채널 상단", "value": f"{hi:,.0f}",
                          "state": "pos" if px >= hi else "mid"})
        # 공통 판단 재료(ML 피처와 동일 계열) — 항상 표시
        from quant.strategies.rsi import rsi as _rsi
        r = float(_rsi(close, 14).iloc[-1])
        chips.append({"label": "RSI(14)", "value": f"{r:.0f}",
                      "state": "neg" if r > 70 else "pos" if r < 30 else "mid"})
        mom = float(close.pct_change(20).iloc[-1])
        chips.append({"label": "20일 모멘텀", "value": f"{mom:+.1%}",
                      "state": "pos" if mom > 0 else "neg"})
        above = float(close.iloc[-1]) > ma(200)
        chips.append({"label": "200일선(레짐)",
                      "value": "위 · 매매 허용" if above else "아래 · 약세 국면",
                      "state": "pos" if above else "neg"})
        _CHIP_CACHE[key] = (now, chips)
    except Exception:  # noqa: BLE001
        return chips
    return chips


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
            # 6번째 필드 epoch(초) — 전문 차트 엔진(Lightweight Charts)용.
            # 시간축이 없는 인덱스면 None → 클라이언트가 SVG 렌더러로 폴백한다.
            def _epoch(ix):
                try:
                    return int(ix.timestamp())
                except (AttributeError, ValueError, OSError):
                    return None
            candles = [[str(ix)[11:16] or str(ix)[:10],
                        round(float(r["open"]), 6), round(float(r["high"]), 6),
                        round(float(r["low"]), 6), round(float(r["close"]), 6),
                        _epoch(ix)]
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
                # ⚠️ 기록의 `weight`는 **오늘 내린 결정**이다(감사 217·223).
                #    주식은 다음 세션 시가 체결이라, 지금 들고 있는 것은 어제
                #    결정의 결과다. 조종석은 이 값을 **실제 보유 옆에** 붙여
                #    "매수 보유 · 비중 X%"로 찍고 있었다. 실측:
                #        us_stock:META → "매수 보유 · 비중 0%" (실제 1.77주)
                #    보유가 있다고 말하면서 비중은 0이라고 하는, 그 자체로
                #    모순인 문장이다. 잔고를 말하고 결정은 따로 밝힌다.
                _last = hist[-1]
                _hw = _last.get("held_weight")
                if _hw is None:
                    # 옛 기록에는 이 필드가 없다(2026-08-13부터 기록). 짐작하지
                    # 말고 **그 기록의 값으로 직접 센다** — 수량·가격·자산이
                    # 다 거기 있다. 없는 값을 지어내는 것과, 있는 값으로
                    # 계산하는 것은 다르다.
                    _px = _last.get("price")
                    _eq = _last.get("equity")
                    if isinstance(_px, (int, float)) and _eq:
                        _hw = round(qty * float(_px) / float(_eq), 4)
                position["weight"] = _hw
                position["plan"] = _last.get("weight")
        except (ValueError, OSError):
            pass

    out = json.dumps({"key": key, "tf": tf, "candles": candles,
                      "position": position,
                      "chips": indicator_chips(market, symbol, state_dir),
                      "last": candles[-1][4] if candles else None},
                     ensure_ascii=False)
    if candles:
        _CANDLE_CACHE[(key, tf)] = (now, out)
    return out


# ── 조종석 입금 화면 ──────────────────────────────────────────────
# 방송 중 GitHub 앱을 열 필요 없이 프로그램 안에서 바로 매칭 입금을 등록한다.
# 정본 장부는 여전히 GitHub Actions(deposit.yml)가 쓰는 git 커밋이다 — 여기서는
# 그 워크플로를 API로 '눌러줄' 뿐, 로컬에서 숫자를 직접 바꾸지 않는다(조작 불가
# 구조 유지). 접수 직후에는 방송 화면에 '반영 중' 배너만 띄운다.
_DEPOSIT_REPO_DEFAULT = "tobe2111/insta-story-downloader"

# 접수됐지만 아직 git 장부에 안 실린 입금 — /api/broadcast가 배너용으로 읽는다.
_PENDING_DEPOSITS: list[dict] = []
_PENDING_TTL = 15 * 60          # 15분 지나면 배너 후보에서 제외(장부 반영 완료 가정)


def _pending_deposits() -> list[dict]:
    """TTL 안의 접수 목록을 반환하고 오래된 항목은 정리한다."""
    import time
    now = time.time()
    _PENDING_DEPOSITS[:] = [p for p in _PENDING_DEPOSITS
                            if now - p["ts"] < _PENDING_TTL]
    return [{"time": p["time"], "amount": p["amount"], "memo": p["memo"]}
            for p in _PENDING_DEPOSITS[-10:]]


def dispatch_deposit(amount: int, memo: str = "") -> None:
    """GitHub Actions deposit.yml을 API로 실행한다 (workflow_dispatch).

    QUANT_GH_TOKEN: fine-grained PAT (해당 저장소 Actions read/write).
    QUANT_GH_REPO:  owner/repo (기본값은 이 프로젝트 저장소).
    """
    import os as _os

    from quant.utils.http import post_text
    token = _os.environ.get("QUANT_GH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("QUANT_GH_TOKEN이 설정되지 않았습니다.")
    repo = _os.environ.get("QUANT_GH_REPO", _DEPOSIT_REPO_DEFAULT).strip()
    url = (f"https://api.github.com/repos/{repo}"
           "/actions/workflows/deposit.yml/dispatches")
    post_text(url, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "content-type": "application/json",
    }, {"ref": "main", "inputs": {"amount": str(int(amount)), "memo": memo}})


def _deposit_principal() -> tuple[float, float] | None:
    """통합 계좌 원금 (반영된 원금, 접수 총액) — 표시용, 실패 시 None.

    둘이 다를 수 있다(감사 211): 입금은 즉시 현금이 되지만 **자산**은 다음
    새벽 배치가 다시 잰다. 그 사이엔 반영분만 손익 계산에 쓴다. 여기서
    접수 총액만 보여주면 조종석 히어로("원금 8만원")와 이 페이지("현재 원금
    100만원")가 같은 화면에서 서로 다른 원금을 말하게 된다.
    """
    import json as _json
    from pathlib import Path
    fp = Path("state") / "paper" / "portfolio_ALL.json"
    try:
        st = _json.loads(fp.read_text(encoding="utf-8"))
        from quant.live.daily import START_CASH
        from quant.live.ledger_basics import principal_of
        sc = float(st.get("start_cash", START_CASH))
        deps = st.get("deposits", [])
        return (principal_of(sc, deps),
                sc + sum(float(d["amount"]) for d in deps))
    except Exception:  # noqa: BLE001
        return None


_DEPOSIT_LEGAL = ('<div class="hint" style="margin-top:10px">⚠️ 법적 구조: '
                  '후원금 자체를 운용하지 않습니다. 후원과 동일한 금액만큼 '
                  "<b>가상 계좌의 원금</b>을 늘리는 매칭 이벤트이며(대가·지분 "
                  '없음), 모든 입금은 git 커밋 장부로 공개됩니다. 수익률은 '
                  '원금과 분리 계산(TWR)되어 입금이 실력처럼 보이지 않습니다.</div>')


def render_deposit_form(message: str = "") -> str:
    """매칭 입금 폼 — 금액·메모를 조종석에서 바로 입력한다 (pandas 불필요)."""
    import os as _os
    has_token = bool(_os.environ.get("QUANT_GH_TOKEN", "").strip())
    pr = _deposit_principal()
    if pr is None:
        principal_txt = '아직 통합 계좌 기록이 없습니다 (매일 새벽 자동 생성)'
    else:
        applied, committed = pr
        principal_txt = f'현재 원금 <b>{applied:,.0f}원</b> · 목표 1억원'
        if committed > applied:               # 접수됐지만 아직 반영 전
            principal_txt += (f' (접수 {committed:,.0f}원 — 차액 '
                              f'{committed - applied:,.0f}원은 다음 새벽 '
                              '배치에서 자산에 반영됩니다)')
    if has_token:
        setup = ""
    else:
        setup = ("""<div class="errbox"><b>연결 설정이 필요합니다 (최초 1회).</b>
입금 버튼이 GitHub의 입금 워크플로를 대신 눌러주려면 접근 토큰이 필요합니다.
<details><summary>설정 방법 보기</summary><ol style="margin:8px 0 0 18px">
<li>GitHub → Settings → Developer settings → <b>Fine-grained tokens</b> → Generate new token</li>
<li>Repository access: <b>이 저장소만</b> 선택</li>
<li>Permissions → Repository permissions → <b>Actions: Read and write</b></li>
<li>발급된 토큰을 프로그램 폴더의 <code>.env</code> 파일에 한 줄 추가:
<pre>QUANT_GH_TOKEN=github_pat_...</pre></li>
<li>웹 조종석 재시작</li></ol>
<p style="margin-top:8px">토큰 없이도 GitHub 앱/웹 → Actions →
"Deposit (8마일 매칭 입금)" → Run workflow 로 직접 등록할 수 있습니다.</p>
</details></div>""")
    body = f"""<p class="kicker">Deposit</p>
<h1>매칭 입금 (8마일 · 8만원 → 1억)</h1>
<p class="sub">방송 후원이 들어오면 같은 금액만큼 통합 계좌의 <b>가상 원금</b>을
늘립니다. {principal_txt}</p>
{_msg_html(message)}
{setup}
<form action="/deposit/run" method="get" class="panel">
  <div class="row">
    <div><label>입금액(원)</label>
      <input name="amount" type="number" min="1" max="10000000" step="1"
             value="10000" required>
      <div class="hint">1회 최대 1,000만원 — 예: 10000</div></div>
    <div><label>메모 (선택)</label>
      <input name="memo" maxlength="80" placeholder="슈퍼챗 ○○님">
      <div class="hint">장부와 방송 배너에 함께 표시됩니다</div></div>
  </div>
  <button type="submit">입금 등록</button>
  {_DEPOSIT_LEGAL}
</form>"""
    return _page("매칭 입금", body, "/deposit")


def run_deposit_html(params: dict) -> str:
    """입금 접수 처리 — 검증 후 GitHub 워크플로 디스패치, 접수 확인 페이지 반환."""
    import time

    try:
        amount = int(float(str(params.get("amount", "")).replace(",", "")))
    except ValueError:
        return render_deposit_form("입금액이 숫자가 아닙니다 — 예: 10000")
    if not (0 < amount <= 10_000_000):
        return render_deposit_form("입금액은 0원 초과 1,000만원 이하여야 합니다.")
    memo = str(params.get("memo", ""))[:80]

    try:
        dispatch_deposit(amount, memo)
    except RuntimeError as exc:
        if "QUANT_GH_TOKEN" in str(exc):
            return render_deposit_form("")   # 폼 안의 설정 안내가 이유를 설명한다
        return render_deposit_form(f"실행 오류: 입금 등록 요청이 실패했습니다 — {exc}")

    _PENDING_DEPOSITS.append({"ts": time.time(),
                              "time": time.strftime("%H:%M:%S"),
                              "amount": amount, "memo": memo})
    body = f"""<p class="kicker">Deposit</p>
<h1>입금 접수 완료</h1>
<div class="panel">
  <p style="font-size:1.15rem"><b>+{amount:,}원</b>{' · ' + html.escape(memo) if memo else ''}
  — 접수되었습니다.</p>
  <p class="sub" style="margin-top:8px">GitHub의 입금 워크플로가 방금 실행을
  시작했습니다. 보통 <b>1~2분</b> 안에 장부(git 커밋)에 기록되고 사이트와 방송
  화면 원금에 반영됩니다. 방송 화면에는 접수 배너가 먼저 표시됩니다.</p>
  <p style="margin-top:12px"><a href="/deposit">← 입금 화면으로</a></p>
  {_DEPOSIT_LEGAL}
</div>"""
    return _page("입금 접수 완료", body, "/deposit")


# 방송 워터마크 QR — 사이트(8마일 챌린지 기록 페이지)로 가는 다리.
# 오프라인 생성 후 인라인(외부 요청 0). URL 변경 시 재생성 필요.
_QR_VIEWBOX = "0 0 35 35"
_QR_PATH = "M1,1H2V2H1zM2,1H3V2H2zM3,1H4V2H3zM4,1H5V2H4zM5,1H6V2H5zM6,1H7V2H6zM7,1H8V2H7zM11,1H12V2H11zM13,1H14V2H13zM19,1H20V2H19zM23,1H24V2H23zM25,1H26V2H25zM27,1H28V2H27zM28,1H29V2H28zM29,1H30V2H29zM30,1H31V2H30zM31,1H32V2H31zM32,1H33V2H32zM33,1H34V2H33zM1,2H2V3H1zM7,2H8V3H7zM9,2H10V3H9zM10,2H11V3H10zM12,2H13V3H12zM13,2H14V3H13zM14,2H15V3H14zM15,2H16V3H15zM17,2H18V3H17zM18,2H19V3H18zM21,2H22V3H21zM23,2H24V3H23zM25,2H26V3H25zM27,2H28V3H27zM33,2H34V3H33zM1,3H2V4H1zM3,3H4V4H3zM4,3H5V4H4zM5,3H6V4H5zM7,3H8V4H7zM9,3H10V4H9zM11,3H12V4H11zM14,3H15V4H14zM16,3H17V4H16zM17,3H18V4H17zM18,3H19V4H18zM19,3H20V4H19zM22,3H23V4H22zM23,3H24V4H23zM27,3H28V4H27zM29,3H30V4H29zM30,3H31V4H30zM31,3H32V4H31zM33,3H34V4H33zM1,4H2V5H1zM3,4H4V5H3zM4,4H5V5H4zM5,4H6V5H5zM7,4H8V5H7zM9,4H10V5H9zM10,4H11V5H10zM11,4H12V5H11zM12,4H13V5H12zM13,4H14V5H13zM22,4H23V5H22zM25,4H26V5H25zM27,4H28V5H27zM29,4H30V5H29zM30,4H31V5H30zM31,4H32V5H31zM33,4H34V5H33zM1,5H2V6H1zM3,5H4V6H3zM4,5H5V6H4zM5,5H6V6H5zM7,5H8V6H7zM12,5H13V6H12zM13,5H14V6H13zM16,5H17V6H16zM19,5H20V6H19zM24,5H25V6H24zM27,5H28V6H27zM29,5H30V6H29zM30,5H31V6H30zM31,5H32V6H31zM33,5H34V6H33zM1,6H2V7H1zM7,6H8V7H7zM11,6H12V7H11zM14,6H15V7H14zM17,6H18V7H17zM19,6H20V7H19zM21,6H22V7H21zM22,6H23V7H22zM23,6H24V7H23zM25,6H26V7H25zM27,6H28V7H27zM33,6H34V7H33zM1,7H2V8H1zM2,7H3V8H2zM3,7H4V8H3zM4,7H5V8H4zM5,7H6V8H5zM6,7H7V8H6zM7,7H8V8H7zM9,7H10V8H9zM11,7H12V8H11zM13,7H14V8H13zM15,7H16V8H15zM17,7H18V8H17zM19,7H20V8H19zM21,7H22V8H21zM23,7H24V8H23zM25,7H26V8H25zM27,7H28V8H27zM28,7H29V8H28zM29,7H30V8H29zM30,7H31V8H30zM31,7H32V8H31zM32,7H33V8H32zM33,7H34V8H33zM9,8H10V9H9zM12,8H13V9H12zM13,8H14V9H13zM1,9H2V10H1zM7,9H8V10H7zM9,9H10V10H9zM12,9H13V10H12zM14,9H15V10H14zM15,9H16V10H15zM16,9H17V10H16zM18,9H19V10H18zM19,9H20V10H19zM21,9H22V10H21zM23,9H24V10H23zM26,9H27V10H26zM27,9H28V10H27zM30,9H31V10H30zM31,9H32V10H31zM32,9H33V10H32zM3,10H4V11H3zM4,10H5V11H4zM5,10H6V11H5zM8,10H9V11H8zM9,10H10V11H9zM11,10H12V11H11zM12,10H13V11H12zM16,10H17V11H16zM20,10H21V11H20zM21,10H22V11H21zM22,10H23V11H22zM23,10H24V11H23zM24,10H25V11H24zM29,10H30V11H29zM30,10H31V11H30zM31,10H32V11H31zM2,11H3V12H2zM7,11H8V12H7zM8,11H9V12H8zM11,11H12V12H11zM16,11H17V12H16zM17,11H18V12H17zM19,11H20V12H19zM21,11H22V12H21zM22,11H23V12H22zM23,11H24V12H23zM25,11H26V12H25zM29,11H30V12H29zM31,11H32V12H31zM32,11H33V12H32zM4,12H5V13H4zM5,12H6V13H5zM6,12H7V13H6zM8,12H9V13H8zM10,12H11V13H10zM11,12H12V13H11zM13,12H14V13H13zM15,12H16V13H15zM16,12H17V13H16zM21,12H22V13H21zM24,12H25V13H24zM28,12H29V13H28zM29,12H30V13H29zM30,12H31V13H30zM31,12H32V13H31zM2,13H3V14H2zM7,13H8V14H7zM8,13H9V14H8zM10,13H11V14H10zM11,13H12V14H11zM13,13H14V14H13zM14,13H15V14H14zM15,13H16V14H15zM17,13H18V14H17zM18,13H19V14H18zM19,13H20V14H19zM21,13H22V14H21zM22,13H23V14H22zM23,13H24V14H23zM27,13H28V14H27zM33,13H34V14H33zM1,14H2V15H1zM3,14H4V15H3zM6,14H7V15H6zM9,14H10V15H9zM10,14H11V15H10zM11,14H12V15H11zM12,14H13V15H12zM14,14H15V15H14zM15,14H16V15H15zM17,14H18V15H17zM21,14H22V15H21zM22,14H23V15H22zM24,14H25V15H24zM27,14H28V15H27zM28,14H29V15H28zM30,14H31V15H30zM31,14H32V15H31zM32,14H33V15H32zM33,14H34V15H33zM3,15H4V16H3zM4,15H5V16H4zM7,15H8V16H7zM8,15H9V16H8zM10,15H11V16H10zM12,15H13V16H12zM13,15H14V16H13zM15,15H16V16H15zM18,15H19V16H18zM19,15H20V16H19zM20,15H21V16H20zM25,15H26V16H25zM26,15H27V16H26zM27,15H28V16H27zM30,15H31V16H30zM31,15H32V16H31zM32,15H33V16H32zM1,16H2V17H1zM2,16H3V17H2zM3,16H4V17H3zM5,16H6V17H5zM6,16H7V17H6zM8,16H9V17H8zM9,16H10V17H9zM10,16H11V17H10zM13,16H14V17H13zM15,16H16V17H15zM16,16H17V17H16zM19,16H20V17H19zM20,16H21V17H20zM23,16H24V17H23zM25,16H26V17H25zM26,16H27V17H26zM29,16H30V17H29zM30,16H31V17H30zM31,16H32V17H31zM33,16H34V17H33zM1,17H2V18H1zM3,17H4V18H3zM6,17H7V18H6zM7,17H8V18H7zM8,17H9V18H8zM10,17H11V18H10zM11,17H12V18H11zM12,17H13V18H12zM18,17H19V18H18zM19,17H20V18H19zM20,17H21V18H20zM23,17H24V18H23zM24,17H25V18H24zM25,17H26V18H25zM26,17H27V18H26zM28,17H29V18H28zM29,17H30V18H29zM30,17H31V18H30zM33,17H34V18H33zM3,18H4V19H3zM8,18H9V19H8zM9,18H10V19H9zM10,18H11V19H10zM12,18H13V19H12zM13,18H14V19H13zM14,18H15V19H14zM15,18H16V19H15zM16,18H17V19H16zM17,18H18V19H17zM18,18H19V19H18zM19,18H20V19H19zM20,18H21V19H20zM22,18H23V19H22zM24,18H25V19H24zM26,18H27V19H26zM27,18H28V19H27zM30,18H31V19H30zM31,18H32V19H31zM33,18H34V19H33zM2,19H3V20H2zM4,19H5V20H4zM6,19H7V20H6zM7,19H8V20H7zM8,19H9V20H8zM10,19H11V20H10zM11,19H12V20H11zM12,19H13V20H12zM16,19H17V20H16zM17,19H18V20H17zM20,19H21V20H20zM21,19H22V20H21zM24,19H25V20H24zM27,19H28V20H27zM28,19H29V20H28zM30,19H31V20H30zM31,19H32V20H31zM33,19H34V20H33zM4,20H5V21H4zM5,20H6V21H5zM9,20H10V21H9zM11,20H12V21H11zM12,20H13V21H12zM15,20H16V21H15zM16,20H17V21H16zM18,20H19V21H18zM19,20H20V21H19zM20,20H21V21H20zM21,20H22V21H21zM22,20H23V21H22zM25,20H26V21H25zM26,20H27V21H26zM29,20H30V21H29zM30,20H31V21H30zM31,20H32V21H31zM33,20H34V21H33zM1,21H2V22H1zM2,21H3V22H2zM3,21H4V22H3zM7,21H8V22H7zM10,21H11V22H10zM12,21H13V22H12zM13,21H14V22H13zM14,21H15V22H14zM16,21H17V22H16zM17,21H18V22H17zM20,21H21V22H20zM21,21H22V22H21zM22,21H23V22H22zM23,21H24V22H23zM25,21H26V22H25zM26,21H27V22H26zM28,21H29V22H28zM29,21H30V22H29zM30,21H31V22H30zM32,21H33V22H32zM33,21H34V22H33zM1,22H2V23H1zM2,22H3V23H2zM3,22H4V23H3zM4,22H5V23H4zM6,22H7V23H6zM10,22H11V23H10zM11,22H12V23H11zM12,22H13V23H12zM14,22H15V23H14zM17,22H18V23H17zM18,22H19V23H18zM19,22H20V23H19zM21,22H22V23H21zM22,22H23V23H22zM23,22H24V23H23zM24,22H25V23H24zM26,22H27V23H26zM28,22H29V23H28zM29,22H30V23H29zM30,22H31V23H30zM31,22H32V23H31zM1,23H2V24H1zM5,23H6V24H5zM6,23H7V24H6zM7,23H8V24H7zM9,23H10V24H9zM11,23H12V24H11zM13,23H14V24H13zM16,23H17V24H16zM17,23H18V24H17zM18,23H19V24H18zM21,23H22V24H21zM22,23H23V24H22zM25,23H26V24H25zM28,23H29V24H28zM32,23H33V24H32zM1,24H2V25H1zM3,24H4V25H3zM8,24H9V25H8zM10,24H11V25H10zM11,24H12V25H11zM15,24H16V25H15zM19,24H20V25H19zM23,24H24V25H23zM24,24H25V25H24zM26,24H27V25H26zM31,24H32V25H31zM33,24H34V25H33zM1,25H2V26H1zM2,25H3V26H2zM3,25H4V26H3zM4,25H5V26H4zM5,25H6V26H5zM7,25H8V26H7zM10,25H11V26H10zM11,25H12V26H11zM12,25H13V26H12zM14,25H15V26H14zM15,25H16V26H15zM16,25H17V26H16zM20,25H21V26H20zM21,25H22V26H21zM25,25H26V26H25zM26,25H27V26H26zM27,25H28V26H27zM28,25H29V26H28zM29,25H30V26H29zM30,25H31V26H30zM9,26H10V27H9zM10,26H11V27H10zM12,26H13V27H12zM13,26H14V27H13zM16,26H17V27H16zM17,26H18V27H17zM20,26H21V27H20zM21,26H22V27H21zM23,26H24V27H23zM25,26H26V27H25zM29,26H30V27H29zM31,26H32V27H31zM33,26H34V27H33zM1,27H2V28H1zM2,27H3V28H2zM3,27H4V28H3zM4,27H5V28H4zM5,27H6V28H5zM6,27H7V28H6zM7,27H8V28H7zM10,27H11V28H10zM11,27H12V28H11zM15,27H16V28H15zM16,27H17V28H16zM17,27H18V28H17zM19,27H20V28H19zM21,27H22V28H21zM22,27H23V28H22zM24,27H25V28H24zM25,27H26V28H25zM27,27H28V28H27zM29,27H30V28H29zM31,27H32V28H31zM1,28H2V29H1zM7,28H8V29H7zM10,28H11V29H10zM11,28H12V29H11zM12,28H13V29H12zM14,28H15V29H14zM16,28H17V29H16zM20,28H21V29H20zM24,28H25V29H24zM25,28H26V29H25zM29,28H30V29H29zM30,28H31V29H30zM31,28H32V29H31zM32,28H33V29H32zM1,29H2V30H1zM3,29H4V30H3zM4,29H5V30H4zM5,29H6V30H5zM7,29H8V30H7zM10,29H11V30H10zM11,29H12V30H11zM13,29H14V30H13zM14,29H15V30H14zM19,29H20V30H19zM20,29H21V30H20zM22,29H23V30H22zM25,29H26V30H25zM26,29H27V30H26zM27,29H28V30H27zM28,29H29V30H28zM29,29H30V30H29zM30,29H31V30H30zM1,30H2V31H1zM3,30H4V31H3zM4,30H5V31H4zM5,30H6V31H5zM7,30H8V31H7zM10,30H11V31H10zM11,30H12V31H11zM13,30H14V31H13zM14,30H15V31H14zM17,30H18V31H17zM21,30H22V31H21zM23,30H24V31H23zM24,30H25V31H24zM25,30H26V31H25zM26,30H27V31H26zM28,30H29V31H28zM29,30H30V31H29zM30,30H31V31H30zM33,30H34V31H33zM1,31H2V32H1zM3,31H4V32H3zM4,31H5V32H4zM5,31H6V32H5zM7,31H8V32H7zM11,31H12V32H11zM15,31H16V32H15zM17,31H18V32H17zM21,31H22V32H21zM25,31H26V32H25zM28,31H29V32H28zM29,31H30V32H29zM32,31H33V32H32zM33,31H34V32H33zM1,32H2V33H1zM7,32H8V33H7zM10,32H11V33H10zM11,32H12V33H11zM13,32H14V33H13zM15,32H16V33H15zM16,32H17V33H16zM17,32H18V33H17zM20,32H21V33H20zM21,32H22V33H21zM23,32H24V33H23zM28,32H29V33H28zM29,32H30V33H29zM30,32H31V33H30zM31,32H32V33H31zM1,33H2V34H1zM2,33H3V34H2zM3,33H4V34H3zM4,33H5V34H4zM5,33H6V34H5zM6,33H7V34H6zM7,33H8V34H7zM9,33H10V34H9zM11,33H12V34H11zM12,33H13V34H12zM14,33H15V34H14zM18,33H19V34H18zM20,33H21V34H20zM23,33H24V34H23zM25,33H26V34H25zM27,33H28V34H27zM28,33H29V34H28zM30,33H31V34H30zM32,33H33V34H32z"

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
<title>Quant · 방송 모드</title>{_FAVICON}{_FONT}{_LWC}<style>
:root{{color-scheme:dark;--bg:#07080b;--bg2:#0e1013;--fg:#f4f5f7;--muted:#8f96a3;
  --dim:#5c6370;--line:#1e2128;--accent:#4c7dff;
  /* 한국 증권사 색 관례: 상승=빨강, 하락=파랑 (--ok=상승, --bad=하락) */
  --ok:#f04452;--bad:#3182f6;--rec:#e5484d}}
*{{box-sizing:border-box;margin:0}}
body{{font-family:"Pretendard Variable",Pretendard,-apple-system,system-ui,
  "Apple SD Gothic Neo","Malgun Gothic",sans-serif;background:var(--bg);
  color:var(--fg);overflow:hidden;height:100vh;display:flex;flex-direction:column;
  font-variant-numeric:tabular-nums}}
header{{display:flex;align-items:center;gap:16px;padding:14px 30px 6px}}
.logo{{font-weight:800;font-size:20px;letter-spacing:.14em}}
.logo em{{font-style:normal;color:var(--accent)}}
.live{{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--rec);
  font-weight:700}}
.live i{{width:8px;height:8px;border-radius:50%;background:var(--rec);
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
.goal{{margin-top:8px}}
.goal .bar{{height:10px;border-radius:99px;background:var(--bg);border:1px solid var(--line);
  overflow:hidden}}
.goal .fill{{height:100%;background:linear-gradient(90deg,var(--accent),var(--ok));
  border-radius:99px;min-width:3px}}
.goal .lbl{{display:flex;justify-content:space-between;font-size:11.5px;
  color:var(--muted);margin-top:3px}}
.candle{{margin:0 30px 4px;background:var(--bg2);border:1px solid var(--line);
  border-radius:14px;padding:10px 20px 6px;height:274px;display:flex;
  flex-direction:column;transition:height .8s ease}}
/* 장면 전환: 종목 확대 — 캔들을 키우고 카드 그리드를 잠시 접는다 */
body.focus .candle{{height:560px}}
body.focus .grid{{display:none}}
/* 장면 전환: 챌린지 게이지 오버레이 */
#scene{{position:fixed;inset:0;display:none;place-items:center;z-index:40;
  background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);
  text-align:center}}
#scene.show{{display:grid}}
#scene .box{{min-width:720px}}
#scene .t{{font-size:22px;color:var(--muted);font-weight:700;letter-spacing:.06em}}
#scene .v{{font-size:96px;font-weight:800;letter-spacing:-.03em;margin:6px 0}}
#scene .bar{{height:18px;border-radius:99px;background:var(--bg2);
  border:1px solid var(--line);overflow:hidden;margin:18px 0 8px}}
#scene .fill{{height:100%;background:linear-gradient(90deg,var(--accent),var(--ok));
  border-radius:99px}}
#scene .m{{font-size:16px;color:var(--muted)}}
.candle .head{{display:flex;align-items:baseline;gap:12px;font-size:13px;
  color:var(--muted)}}
/* '분석 갱신' 펄스 — 새 데이터 재계산 순간에만 잠깐 나타난다 */
#c-pulse{{font-size:11px;color:var(--accent);opacity:0;font-weight:700}}
#c-pulse.on{{animation:pulse 1.6s ease-out}}
@keyframes pulse{{0%{{opacity:0}}15%{{opacity:1}}100%{{opacity:0}}}}
.candle .sym{{font-size:16px;font-weight:800;color:var(--fg)}}
.candle .px{{font-size:16px;font-weight:700}}
.candle .body{{flex:1;min-height:0}}
.chips{{display:flex;gap:8px;margin:5px 0 3px;flex-wrap:wrap}}
.comment{{font-size:12px;color:var(--muted);margin:2px 0 4px}}
.comment b{{color:var(--fg)}}
#event{{position:fixed;top:64px;left:50%;transform:translate(-50%,-30px);
  background:var(--bg2);border:1px solid var(--accent);border-radius:12px;
  padding:14px 26px;font-size:20px;font-weight:800;z-index:60;opacity:0;
  box-shadow:0 12px 40px -12px rgba(76,125,255,.5);pointer-events:none;
  transition:opacity .4s,transform .4s}}
#event.show{{opacity:1;transform:translate(-50%,0)}}
.wm{{position:fixed;right:26px;bottom:74px;display:flex;align-items:center;gap:10px;
  background:color-mix(in srgb,var(--bg2) 82%,transparent);border:1px solid var(--line);
  border-radius:12px;padding:8px 12px;z-index:40}}
.wm svg{{width:56px;height:56px;background:#fff;border-radius:6px;padding:3px}}
.wm .u{{font-size:12px;color:var(--muted);line-height:1.5}}
.wm .u b{{color:var(--fg);font-size:12.5px}}
.chip{{font-size:11.5px;padding:3px 10px;border-radius:99px;border:1px solid var(--line);
  background:var(--bg);color:var(--muted)}}
.chip b{{color:var(--fg);font-weight:650}}
.chip.pos{{border-color:color-mix(in srgb,var(--ok) 45%,transparent);color:var(--ok)}}
.chip.pos b{{color:var(--ok)}}
.chip.neg{{border-color:color-mix(in srgb,var(--bad) 45%,transparent);color:var(--bad)}}
.chip.neg b{{color:var(--bad)}}
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
<span id="news">8마일 챌린지 — 8만원으로 시작하는 가상 자금 자동 모의투자</span>
<span id="clock">—</span></header>
<div class="hero" id="hero"><div class="nums"><div class="k">불러오는 중…</div></div></div>
<div class="candle" id="candle" style="display:none"><div class="head">
  <span class="sym" id="c-sym">—</span><span id="c-px" class="px">—</span>
  <span id="c-pos"></span>
  <span id="c-pulse">분석 갱신</span>
  <span style="margin-left:auto">실시간 1분봉 · 보조선 <span style="color:var(--accent)">MA20</span>·<span style="color:#d9a13b">MA60</span> — 시세는 실시간, <b>매매 판단은 일봉(하루 1회 새벽)</b></span>
</div><div class="chips" id="c-chips"></div>
<div class="comment" id="c-comment"></div>
<div class="body" id="c-body"></div></div>
<div id="event"></div>
<div id="scene"></div>
<div class="wm"><svg viewBox="{_QR_VIEWBOX}"><path d="{_QR_PATH}" fill="#000"/></svg>
<div class="u"><b>8마일 챌린지 실기록</b><br>quant.jiwon-1a2.workers.dev<br>모의투자 · 수익 보장 아님</div></div>
<div class="grid" id="grid"></div>
<div class="tape"><div class="inner" id="tape">&nbsp;</div></div>
<footer id="disc">⚠️ 모의투자(가짜 돈)입니다 — 실제 돈이 아니며, 수익을 보장하지
않고, 투자 자문·권유가 아닙니다.</footer>
<script>
function esc(s){{const d=document.createElement("div");d.textContent=String(s);return d.innerHTML}}
function won(v){{return Math.round(v).toLocaleString("ko-KR")+"원"}}
function pct(v){{return Math.abs(v)<0.005?"0.00%":(v>=0?"+":"")+Number(v).toFixed(2)+"%"}}
// ±0.005% 미만은 사실상 0 — 빨강/파랑을 칠하지 않는다(중립)
function sgnCls(v){{return v>0.004?"pos":v<-0.004?"neg":""}}
function niceTicks(mn,mx,n){{
  const span=(mx-mn)||1,step0=span/n,mag=Math.pow(10,Math.floor(Math.log10(step0)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(sv=>span/sv<=n)||mag*10;
  const t=[];for(let v=Math.ceil(mn/step)*step;v<=mx;v+=step)t.push(v);return t}}
// 전문 차트: 축·그리드·기준선(10,000) 상하 분할 영역·교체 마커·현재값 태그·드로다운
function proChart(o){{
  const v=o.vals; if(!v||v.length<2) return "";
  const W=o.w,H=o.h,padR=64,padB=o.axes?16:4,padT=6;
  const ddH=o.dd?Math.round(H*0.18):0, mainH=H-ddH-padB-padT;
  const bs=o.baseSeries&&o.baseSeries.length===v.length?o.baseSeries:null;
  // 기준선: 명시값 > 원금 계단선의 시작값 > 만원(개별 계좌 기본)
  const base=o.base||(bs?bs[0]:10000);
  let mn=Math.min(...v,base),mx=Math.max(...v,base);
  if(bs){{mn=Math.min(mn,...bs);mx=Math.max(mx,...bs)}}
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
  // 원금 계단선(입금 반영) — 음영 분할은 입금 점프를 수익처럼 칠하므로 끈다
  if(bs){{
    let step="";
    bs.forEach((bv,i)=>{{const x=X(i),y=Y(bv);
      step+=(i===0?`M${{x}},${{y}}`:`L${{x}},${{Y(bs[i-1])}} L${{x}},${{y}}`)}});
    step+=`L${{X(v.length-1)}},${{Y(bs[bs.length-1])}}`;
    let out2=`<path d="${{step}}" fill="none" stroke="var(--dim)" stroke-width="1.2"
      stroke-dasharray="5 4"/>`;
    const up=v[v.length-1]>=bs[bs.length-1];
    out+=out2+`<polyline points="${{line(v)}}" fill="none"
      stroke="${{up?"var(--ok)":"var(--bad)"}}" stroke-width="2.2"/>`;
    if(o.markers&&o.dates)o.markers.forEach(d=>{{const i=o.dates.indexOf(d);
      if(i>=0)out+=`<path d="M${{X(i)}},${{Y(v[i])-9}} l5,5 -5,5 -5,-5 z" fill="var(--accent)"/>`}});
    if(o.dmarkers&&o.dates)o.dmarkers.forEach(d=>{{
      let i=o.dates.findIndex(dt=>dt>=d); if(i<0)i=o.dates.length-1;
      out+=`<path d="M${{X(i)}},${{Y(v[i])+13}} l5,8 -10,0 z" fill="var(--ok)"/>`}});
    const lx=X(v.length-1),ly=Y(v[v.length-1]);
    out+=`<circle cx="${{lx}}" cy="${{ly}}" r="3.4" fill="${{up?"var(--ok)":"var(--bad)"}}"/>
      <rect x="${{W-padR+2}}" y="${{ly-10}}" width="${{padR-6}}" height="20" rx="5"
        fill="${{up?"var(--ok)":"var(--bad)"}}"/>
      <text x="${{W-padR+(padR-6)/2+2}}" y="${{ly+4}}" font-size="11" font-weight="700"
        fill="#07080b" text-anchor="middle">${{Math.round(v[v.length-1]).toLocaleString()}}</text>`;
    if(o.dd){{const dv=(o.twr&&o.twr.length===v.length)?o.twr:v;
      let peak=dv[0];const dd2=dv.map(x=>{{peak=Math.max(peak,x);return peak?x/peak-1:0}});
      const dmn=Math.min(...dd2,-0.001);
      const DY=val=>H-padB-ddH+( -val/-dmn)*ddH;
      const dline=dd2.map((val,i)=>`${{X(i).toFixed(1)}},${{DY(val).toFixed(1)}}`).join(" ");
      out+=`<path d="M0,${{H-padB-ddH}} L${{dline}} L${{X(v.length-1)}},${{H-padB-ddH}} Z"
        fill="var(--bad)" fill-opacity=".22"/>`}}
    return out+"</svg>"}}
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
  // 매칭 입금 마커 ▲ (원금 증액 시점 — 점프는 후원, 기울기는 실력)
  if(o.dmarkers&&o.dates)o.dmarkers.forEach(d=>{{
    let i=o.dates.findIndex(dt=>dt>=d); if(i<0)i=o.dates.length-1;
    out+=`<path d="M${{X(i)}},${{Y(v[i])+13}} l5,8 -10,0 z" fill="var(--ok)"/>`}});
  // 현재값 점+태그
  const lx=X(v.length-1),ly=Y(v[v.length-1]);
  out+=`<circle cx="${{lx}}" cy="${{ly}}" r="3.4" fill="${{up?"var(--ok)":"var(--bad)"}}">
    <animate attributeName="opacity" values="1;.3;1" dur="1.6s" repeatCount="indefinite"/></circle>
    <rect x="${{W-padR+2}}" y="${{ly-10}}" width="${{padR-6}}" height="20" rx="5"
      fill="${{up?"var(--ok)":"var(--bad)"}}"/>
    <text x="${{W-padR+(padR-6)/2+2}}" y="${{ly+4}}" font-size="11" font-weight="700"
      fill="#07080b" text-anchor="middle">${{Math.round(v[v.length-1]).toLocaleString()}}</text>`;
  // 드로다운 서브차트(수면 아래)
  /* ⚠️ 낙폭은 **입금 제거 성장 지수** 위에서 잰다(감사 224). 원자산으로
     그리면 입금이 고점을 끌어올려 그 직전 손실이 그림에서 사라진다. */
  if(o.dd){{const dv=(o.twr&&o.twr.length===v.length)?o.twr:v;
    let peak=dv[0];const dd=dv.map(x=>{{peak=Math.max(peak,x);return peak?x/peak-1:0}});
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
  const cls=sgnCls(rp);
  const news=a.news?`<div class="reason" style="opacity:.75">관련 뉴스 · ${{esc(a.news.title)}}${{a.news.source?" — "+esc(a.news.source):""}}</div>`:"";
  const label=a.name?`${{esc(a.name)}} <span style="opacity:.6">${{esc(a.key.split(":")[1]||a.key)}}</span>`:esc(a.key);
  return `<div class="card"><div class="k">${{label}} · ${{liveTag}}</div>
    <div><span class="eq2 ${{cls}}">${{won(eq)}}</span>
    <span class="pct2 ${{cls}}">${{pct(rp)}}</span></div>
    <div class="reason">${{a.reason?esc(a.reason):"최대낙폭 "+a.mdd_pct+"%"}}</div>${{news}}
    <div style="height:64px;margin-top:auto">${{proChart({{vals:a.spark,dates:a.spark_dates,w:320,h:58,axes:false}})}}</div></div>`}}
async function tick(first){{
  try{{
    const q=(location.search?location.search+"&":"?")+(first?"nolive=1":"x=1");
    const r=await fetch("/api/broadcast"+q,{{cache:"no-store"}});
    if(!r.ok)return;
    const d=await r.json();
    const accs=d.accounts||[]; if(!accs.length)return;
    const pf=accs.find(a=>a.market==="portfolio");
    const rest=accs.filter(a=>a.market!=="portfolio");
    // 상단 배너 회전 풀 — 재학습 서사 + 시장 브리핑(표시 전용, 참고 명시)
    newsPool=[];
    if(d.news){{newsPool.push(d.news);
      if(d.news.includes("교체"))popEvent(d.news);}}
    (d.briefing&&d.briefing.items||[]).slice(0,6).forEach(b=>newsPool.push(
      `📰 브리핑(참고용·판단 미사용) [${{esc(b.cat)}}] ${{esc(b.title)}}`+
      (b.source?` — ${{esc(b.source)}}`:"")));
    if(newsPool.length&&!newsTimer){{rotateNews();
      newsTimer=setInterval(rotateNews,12000);}}
    const hero=pf||rest[0];
    lastHero=hero;
    if(hero){{
      const eq=hero.live_equity??hero.equity;
      const rp=hero.principal!=null?((eq/hero.principal-1)*100)
              :(hero.live_return_pct??hero.return_pct);
      const cls=sgnCls(rp);
      const mk=(d.swaps||[]).filter(s=>s.key===hero.key).map(s=>s.date);
      const dmk=(hero.deposits||[]).map(x=>x.date);
      // 입금 배너 — 새 입금이 감지되면 사건으로 알린다
      if(hero.deposits&&hero.deposits.length){{
        const lastD=hero.deposits[hero.deposits.length-1];
        popEvent(`💝 후원 매칭 +${{won(lastD.amount)}} ${{lastD.memo?"("+esc(lastD.memo)+")":""}} — 원금 ${{won(hero.principal)}}`);
      }}
      // 조종석 입금 접수 배너 — 장부 반영 전 '반영 중' 상태를 먼저 알린다
      (d.pending||[]).forEach(p=>popEvent(
        `💝 입금 접수 +${{won(p.amount)}} ${{p.memo?"("+esc(p.memo)+")":""}} — 장부 반영 중 (${{p.time}})`));
      let breakdown="", goal="";
      if(hero.principal!=null){{
        const pnl=hero.live_equity!=null?(hero.live_equity-hero.principal):hero.pnl;
        breakdown=`<div class="meta">원금(매칭 포함) <b>${{won(hero.principal)}}</b> ·
          운용 손익 <b class="${{sgnCls(pnl)}}">${{(pnl>=0?"+":"")+won(Math.abs(pnl)).replace("원","")}}원</b>
          · 실력 지표(TWR) <b class="${{sgnCls(hero.twr_pct)}}">${{pct(hero.twr_pct)}}</b>${{
          hero.random_pctile!=null?` · 무작위 1,000개 중 상위 <b>${{(100-hero.random_pctile).toFixed(0)}}%</b>`:""}}${{
          d.shadow?` · 진화 없이 고정이었다면 <b>${{won(d.shadow.equity)}}</b>`:""}}</div>`;
        const ratio=Math.min(1,eq/hero.goal);
        goal=`<div class="goal"><div class="bar"><div class="fill" style="width:${{Math.max(0.3,ratio*100)}}%"></div></div>
          <div class="lbl"><span>8마일 챌린지 · 8만원 → 1억</span><span>${{(ratio*100).toFixed(3)}}% · 목표 1억원</span></div></div>`;
      }}
      document.getElementById("hero").innerHTML=
        `<div class="nums"><div class="k">${{hero.market==="portfolio"?"통합 분산 계좌":esc(hero.key)}}
          · ${{hero.live_equity!=null?"실시간 평가":"확정 "+esc(hero.date||"")}}</div>
        <div class="eq ${{cls}}">${{won(eq)}}</div>
        <div class="pct ${{cls}}">${{pct(rp)}} <span class="meta">${{hero.principal!=null?"원금 대비":"시작 10,000원"}}</span></div>
        ${{breakdown}}${{goal}}
        <div class="meta" style="margin-top:4px">최대낙폭 ${{hero.mdd_pct}}% · ─ 전략 ┄ 그냥 보유 ◆ 교체 ▲ 입금</div></div>
        <div class="chartwrap">${{proChart({{vals:hero.spark,dates:hero.spark_dates,
          baseSeries:hero.spark_base,
          w:1280,h:170,axes:true,dd:true,twr:hero.spark_twr,markers:mk,dmarkers:dmk,
          bench:(hero.spark_price&&hero.spark_price[0])?hero.spark_price.map(p=>((hero.spark_base&&hero.spark_base[0])||10000)*p/hero.spark_price[0]):null}})}}</div>`;
    }}
    // 통합 계좌 신고가 감지(실시간 평가 기준, 래칫)
    if(pf){{
      const eqNow=pf.live_equity??pf.equity;
      const prevPeak=Math.max(peakEquity,...(pf.spark||[0]));
      if(peakEquity&&eqNow>prevPeak&&eqNow>(pf.principal||10000))
        popEvent(`📈 통합 계좌 신고가! ${{won(eqNow)}}`);
      peakEquity=Math.max(prevPeak,eqNow);
    }}
    document.getElementById("grid").innerHTML=rest.map(card).join("");
    rest.forEach(a=>{{if(a.name)nameByKey[a.key]=a.name}});
    cKeys=rest.filter(a=>a.market==="crypto").map(a=>a.key)
      .concat(rest.filter(a=>a.market!=="crypto").map(a=>a.key));
    // 티커 테이프 — 실시간가(가능 시) 또는 확정 기록
    const items=rest.map(a=>{{
      const lp=(d.live_prices||{{}})[a.key];
      const base=a.spark_price&&a.spark_price.length?a.spark_price[a.spark_price.length-1]:null;
      let chg=null; if(lp&&base)chg=(lp/base-1)*100;
      const px=lp??base;
      const v=(chg??a.return_pct)||0;
      const c=v>0.004?"var(--ok)":v<-0.004?"var(--bad)":"var(--muted)";
      const arrow=v>0.004?"▲":v<-0.004?"▼":"·";
      return `<b>${{esc(a.name||a.key.split(":")[1]||a.key)}}</b>`+
        (px?`${{Number(px).toLocaleString()}} `:"")+
        `<span style="color:${{c}}">${{arrow}} ${{pct(chg??a.return_pct)}}</span>`}}).join("");
    document.getElementById("tape").innerHTML=items+items;   // 이음새 없는 루프
    if(d.disclaimer)document.getElementById("disc").textContent="⚠️ "+d.disclaimer;
  }}catch(e){{}}
}}
let cKeys=[],cIdx=0;
const nameByKey={{}};   // 종목코드 → 한글 이름 (캔들 헤더 등 표시용)
// 장면 자동 전환 — 90초 주기: 기본 → 종목 확대(18초) → 챌린지 게이지(10초).
// 라이브가 한 화면에 머물지 않게 한다. 데이터가 없으면 조용히 건너뛴다.
let lastHero=null;
function showGoalScene(){{
  if(!lastHero||lastHero.principal==null)return;
  const eq=lastHero.live_equity??lastHero.equity;
  const ratio=Math.min(1,eq/lastHero.goal);
  const el=document.getElementById("scene");
  el.innerHTML=`<div class="box"><div class="t">8마일 챌린지 · 8만원 → 1억</div>
    <div class="v ${{eq>=lastHero.principal?"pos":"neg"}}">${{won(eq)}}</div>
    <div class="m">원금(매칭 포함) ${{won(lastHero.principal)}} · 실력 지표(TWR) ${{pct(lastHero.twr_pct)}}</div>
    <div class="bar"><div class="fill" style="width:${{Math.max(0.4,ratio*100)}}%"></div></div>
    <div class="m">${{(ratio*100).toFixed(3)}}% · 목표 1억원</div></div>`;
  el.classList.add("show");
  setTimeout(()=>el.classList.remove("show"),10000);
}}
function sceneLoop(){{
  if(!lastHero)return;
  document.body.classList.add("focus");
  setTimeout(()=>{{document.body.classList.remove("focus");showGoalScene();}},18000);
}}
setInterval(sceneLoop,90000);
// 상단 배너 회전 — 재학습 소식과 브리핑 헤드라인을 번갈아 보여준다
let newsPool=[],newsIdx=0,newsTimer=null;
function rotateNews(){{
  if(!newsPool.length)return;
  const el=document.getElementById("news");
  el.innerHTML=newsPool[newsIdx%newsPool.length];
  newsIdx++;}}
// 이벤트 배너 — 챔피언 교체·계좌 신고가 같은 '사건'을 몇 초간 크게
const seenEvents=new Set();let peakEquity=0;
function popEvent(text){{
  if(seenEvents.has(text))return; seenEvents.add(text);
  const el=document.getElementById("event");
  el.textContent=text; el.classList.add("show");
  setTimeout(()=>el.classList.remove("show"),7000);
}}
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
      const code=key.split(":")[1]||key;
      document.getElementById("c-sym").textContent=
        nameByKey[key]?nameByKey[key]+" · "+code:code;
      const last=d.candles[d.candles.length-1],prev=d.candles[0];
      const chg=(last[4]/prev[1]-1)*100,cls=chg>=0;
      const px=document.getElementById("c-px");
      px.textContent=Number(last[4]).toLocaleString()+" ("+pct(chg)+")";
      px.style.color=cls?"var(--ok)":"var(--bad)";
      document.getElementById("c-pos").textContent=
        d.position?(d.position.side
          +(d.position.weight!=null?" · 보유 "+(d.position.weight*100).toFixed(1)+"%":"")
          +(d.position.plan!=null&&d.position.weight!=null
              &&Math.abs(d.position.plan-d.position.weight)>0.005
            ?" → "+(d.position.plan*100).toFixed(1)+"% 예정":"")):"관망 (현금)";
      document.getElementById("c-chips").innerHTML=(d.chips&&d.chips.length)
        ?`<span class="chip" style="border-style:dashed">판단 지표 · 일봉 기준</span>`+
          d.chips.map(c=>`<span class="chip ${{c.state==="pos"?"pos":c.state==="neg"?"neg":""}}">${{esc(c.label)}} <b>${{esc(c.value)}}</b></span>`).join("")
        :"";
      // 장중 상황 코멘트 — '판단'이 아니라 '현재 상태 서술'임을 명시
      let cm="";
      if(d.position&&d.position.avg_price){{
        const dv=(last[4]/d.position.avg_price-1)*100;
        cm=`현재가가 진입가 대비 <b class="${{dv>=0?"pos":"neg"}}">${{pct(dv)}}</b>`;
      }}else{{cm="현재 무포지션(현금) — 시세만 관찰 중";}}
      const regime=(d.chips||[]).find(c=>c.label.includes("레짐"));
      if(regime)cm+=` · 레짐 ${{esc(regime.value)}}`;
      document.getElementById("c-comment").innerHTML=
        `<b>장중 상황</b> (판단 아님 · 다음 판단은 내일 새벽 5시): ${{cm}}`;
      renderCandles(key,d);
      return;
    }}catch(e){{}}
  }}
}}
// 전문 차트 엔진(TradingView Lightweight Charts, 오픈소스) — 크로스헤어·
// 가격축·부드러운 갱신. CDN 로드 실패(오프라인)나 epoch 없는 데이터면
// 기존 SVG 렌더러로 조용히 폴백한다.
let lwc=null,lwcSeries=null,lwcKey=null,lwcLine=null,lwcMa20=null,lwcMa60=null;
function renderCandles(key,d){{
  try{{renderCandlesLwc(key,d)}}catch(e){{   // 엔진 오류 시 SVG로 안전 폴백
    if(lwc){{try{{lwc.remove()}}catch(_e){{}};lwc=null;lwcSeries=null;lwcKey=null}}
    document.getElementById("c-body").innerHTML=candleChart(d);
  }}
}}
function renderCandlesLwc(key,d){{
  const body=document.getElementById("c-body");
  const ok=window.LightweightCharts&&d.candles[0]&&d.candles[0][5]!=null;
  if(!ok){{if(lwc){{lwc.remove();lwc=null;lwcSeries=null;lwcKey=null}}
    body.innerHTML=candleChart(d);return}}
  if(!lwc){{
    body.innerHTML="";
    lwc=LightweightCharts.createChart(body,{{
      autoSize:true,
      layout:{{background:{{type:"solid",color:"transparent"}},textColor:"#8f96a3",
        fontFamily:"Pretendard Variable,Pretendard,sans-serif",fontSize:11}},
      grid:{{vertLines:{{color:"rgba(140,150,165,.07)"}},
        horzLines:{{color:"rgba(140,150,165,.07)"}}}},
      rightPriceScale:{{borderVisible:false}},
      timeScale:{{borderVisible:false,timeVisible:true,secondsVisible:false}},
      crosshair:{{mode:0}},
      localization:{{locale:"ko-KR",
        priceFormatter:p=>Number(p).toLocaleString("ko-KR")}}}});
    lwcSeries=lwc.addCandlestickSeries({{
      upColor:"#f04452",downColor:"#3182f6",borderUpColor:"#f04452",
      borderDownColor:"#3182f6",wickUpColor:"#f04452",wickDownColor:"#3182f6"}});
    // 모델이 보는 보조선 — 1분봉 이동평균(표시용). '실시간 분석 중' 연출의
    // 정직한 재료: 실제 데이터로 매 갱신마다 다시 계산된다.
    lwcMa20=lwc.addLineSeries({{color:"#4c7dff",lineWidth:1,
      priceLineVisible:false,lastValueVisible:false}});
    lwcMa60=lwc.addLineSeries({{color:"#d9a13b",lineWidth:1,
      priceLineVisible:false,lastValueVisible:false}});
  }}
  lwcSeries.setData(d.candles.map(k=>({{time:k[5],open:k[1],high:k[2],low:k[3],close:k[4]}})));
  const ma=(n)=>{{const out=[];let s=0;
    d.candles.forEach((k,i)=>{{s+=k[4];if(i>=n)s-=d.candles[i-n][4];
      if(i>=n-1)out.push({{time:k[5],value:s/n}})}});return out}};
  lwcMa20.setData(ma(20)); lwcMa60.setData(ma(60));
  if(lwcLine){{lwcSeries.removePriceLine(lwcLine);lwcLine=null}}
  if(d.position&&d.position.avg_price)
    lwcLine=lwcSeries.createPriceLine({{price:d.position.avg_price,color:"#4c7dff",
      lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,
      axisLabelVisible:true,title:"진입가"}});
  if(lwcKey!==key){{lwc.timeScale().fitContent();lwcKey=key}}
  // '분석 갱신' 펄스 — 새 데이터로 다시 계산했음을 시각적으로 알린다
  const pulse=document.getElementById("c-pulse");
  if(pulse){{pulse.classList.remove("on");void pulse.offsetWidth;pulse.classList.add("on")}}
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
