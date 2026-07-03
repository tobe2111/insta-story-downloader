"""웹 UI의 페이지 렌더링/요청 처리 로직 (표준 라이브러리만 사용).

무거운 quant/pandas 임포트는 백테스트를 실제로 실행할 때만(지연 임포트) 일어나므로,
폼 페이지 자체는 pandas 없이도 렌더링·테스트할 수 있다.
"""
from __future__ import annotations

import html

# 폼 셀렉트용 (pandas 임포트를 피하려고 하드코딩; strategies 레지스트리와 일치)
STRATEGIES = ["ma_cross", "momentum", "mean_reversion", "rsi", "breakout",
              "macd", "keltner", "ensemble"]
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
        '<a href="/sweep">🔥 민감도 스윕</a></nav>')


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
