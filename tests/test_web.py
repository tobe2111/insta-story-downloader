"""웹 UI 테스트.

폼 렌더링은 표준 라이브러리만으로 동작(pandas 불필요), 백테스트 실행 경로는
pandas가 필요하다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.web.app import (
    MARKETS,
    STRATEGIES,
    read_state,
    render_form,
    render_monitor,
    render_optimize_form,
    render_portfolio_form,
    render_screener_form,
    render_sweep_form,
    run_backtest_html,
    run_optimize_html,
    run_portfolio_html,
    run_screener_html,
    run_sweep_html,
    state_json,
)


def test_render_form_has_controls():
    doc = render_form()
    assert "<form" in doc and 'action="/backtest"' in doc
    assert "<nav" in doc and 'href="/sweep"' in doc   # 조종석 네비게이션
    for s in STRATEGIES:
        assert s in doc
    for m in MARKETS:
        assert m in doc


def test_render_sweep_form():
    doc = render_sweep_form()
    assert "<form" in doc and 'action="/sweep/run"' in doc
    assert "히트맵" in doc and "<nav" in doc


def test_render_optimize_form():
    doc = render_optimize_form()
    assert "<form" in doc and 'action="/optimize/run"' in doc
    assert "워크포워드" in doc and 'href="/optimize"' in doc


def test_run_optimize_html_synthetic():
    doc = run_optimize_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "500",
                             "is_window": "200", "oos_window": "100"})
    assert "워크포워드 결과" in doc and "OOS" in doc and "<nav" in doc


def test_run_optimize_html_unsupported_strategy():
    doc = run_optimize_html({"strategy": "ensemble"})  # 그리드 없는 전략
    assert "최적화 미지원" in doc  # 폼으로 안내


def test_render_portfolio_form():
    doc = render_portfolio_form()
    assert "<form" in doc and 'action="/portfolio/run"' in doc
    assert "포트폴리오" in doc and 'href="/portfolio"' in doc


def test_run_portfolio_html_synthetic():
    doc = run_portfolio_html({"market": "synthetic", "symbols": "A, B, C",
                              "strategy": "momentum", "limit": "200"})
    assert "성과 지표" in doc and "샤프지수" in doc and "<nav" in doc


def test_run_portfolio_html_empty_symbols():
    doc = run_portfolio_html({"market": "synthetic", "symbols": "  "})
    assert "종목을 하나 이상" in doc  # 빈 입력 → 폼으로 안내


def test_render_screener_form():
    doc = render_screener_form()
    assert "<form" in doc and 'action="/screener/run"' in doc
    assert "종목 선별" in doc and "<nav" in doc and 'href="/screener"' in doc


def test_run_screener_no_symbols():
    doc = run_screener_html({"symbols": "  "})
    assert "후보 종목을 하나 이상" in doc


def test_run_screener_no_api_key():
    """FMP 키가 없으면(=재무데이터 없음) 안내 메시지로 폼을 보여준다."""
    import os
    os.environ.pop("FMP_API_KEY", None)
    doc = run_screener_html({"symbols": "AAPL, MSFT", "top_n": "1"})
    assert "FMP_API_KEY" in doc


def test_render_monitor_no_state(tmp_path):
    doc = render_monitor([str(tmp_path / "nope.json")])
    assert "실행 중인" in doc and "<nav" in doc


def test_render_monitor_with_state(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "symbol": "X", "strategy": "s", "mode": "paper",
        "history": [{"time": "t", "equity": 10000 + i, "weight": 0.5, "price": 0}
                    for i in range(4)],
        "positions": [{"symbol": "X", "quantity": 0.1, "avg_price": 100}],
        "orders": [],
    }), encoding="utf-8")
    doc = render_monitor([str(p)])
    assert "라이브 모니터" in doc and "<nav" in doc and "총자산" in doc
    # 실시간 갱신: JS 폴러 + 요소 id, 페이지 meta-refresh 제거
    assert 'id="eqline"' in doc and "fetch(" in doc and "setInterval" in doc
    assert 'http-equiv="refresh"' not in doc
    # 전체 실시간: 포지션·주문 테이블도 JS로 갱신되도록 id 부여
    assert 'id="pos-body"' in doc and 'id="ord-body"' in doc
    assert 'id="kpi-dd"' in doc and 'id="kpi-trades"' in doc
    assert 'id="kpi-acc"' in doc and "방향 정확도" in doc   # 예측 정확도 타일


def test_state_json_reads_file(tmp_path):
    import json
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"symbol": "BTC/USDT", "history": []}), encoding="utf-8")
    assert read_state([str(p)])["symbol"] == "BTC/USDT"
    assert json.loads(state_json([str(p)]))["symbol"] == "BTC/USDT"
    # 파일 없으면 빈 객체
    assert state_json([str(tmp_path / "none.json")]) == "{}"


def test_run_sweep_html_synthetic():
    doc = run_sweep_html({"market": "synthetic", "symbol": "X", "limit": "300"})
    assert "<table" in doc and "hsl(" in doc      # 히트맵 렌더
    assert 'href="/"' in doc                       # 네비게이션


def test_render_form_message():
    assert "테스트경고" in render_form("테스트경고")


def test_run_backtest_html_synthetic():
    doc = run_backtest_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "200"})
    assert "성과 지표" in doc and "샤프지수" in doc
    assert "<nav" in doc  # 조종석 네비게이션
    # "이게 운인가?" 신뢰도 분석(PSR + 몬테카를로)이 포함되어야 한다
    assert "이게 운인가" in doc and "PSR" in doc


def test_run_backtest_html_ensemble():
    doc = run_backtest_html({"market": "synthetic", "strategy": "ensemble",
                             "limit": "150"})
    assert "<svg" in doc


def test_run_backtest_html_bad_limit_defaults():
    # limit이 숫자가 아니어도 기본값으로 처리되어 크래시하지 않아야 한다
    doc = run_backtest_html({"market": "synthetic", "strategy": "rsi",
                             "limit": "abc"})
    assert "성과 지표" in doc


def test_run_backtest_html_escapes_symbol_xss():
    """웹 파라미터(symbol)가 리포트 제목에 이스케이프되어 반사형 XSS가 막힌다."""
    doc = run_backtest_html({"market": "synthetic", "strategy": "ma_cross",
                             "symbol": "<script>alert(1)</script>", "limit": "120"})
    assert "<script>alert(1)</script>" not in doc     # 원본 스크립트 태그 없음
    assert "&lt;script&gt;" in doc                     # 이스케이프됨
