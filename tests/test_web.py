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
    render_validate_form,
    run_backtest_html,
    run_optimize_html,
    run_portfolio_html,
    run_screener_html,
    run_sweep_html,
    run_validate_html,
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


def test_render_validate_form():
    """검증 폼 렌더링 (pandas 불필요 — quant.cli는 argparse만 쓰는 경량 모듈)."""
    doc = render_validate_form()
    assert "<form" in doc and 'action="/validate/run"' in doc
    assert "<nav" in doc and 'href="/validate"' in doc     # 네비게이션에 검증 탭
    # CLI validate와 같은 기본 그리드 지원 전략만 선택지로 노출
    from quant.cli import _VALIDATE_GRIDS
    for s in _VALIDATE_GRIDS:
        assert s in doc
    for field in ("market", "symbol", "timeframe", "limit",
                  "is_window", "oos_window"):
        assert f'name="{field}"' in doc
    assert "보장되지 않습니다" in doc            # 정직성 푸터


def test_run_validate_html_synthetic():
    """검증 3종 실행 경로 (pandas 필요 — CI). 합성 시장 + 기본 그리드."""
    doc = run_validate_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "500",
                             "is_window": "250", "oos_window": "125"})
    assert "검증 결과" in doc and "<nav" in doc
    assert "워크포워드" in doc and "PBO" in doc and "CPCV" in doc
    assert "<pre" in doc                        # 한국어 리포트 문자열을 <pre>로
    assert "보장되지 않습니다" in doc            # 정직성 푸터


def test_run_validate_html_unsupported_strategy():
    doc = run_validate_html({"strategy": "ensemble"})   # 기본 그리드 없는 전략
    assert "검증 미지원" in doc                  # 폼으로 안내


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


def test_parse_symbols_caps_and_dedupes():
    """종목 수가 상한(_MAX_SYMBOLS)으로 제한되고 중복이 제거된다(자원 고갈 방지)."""
    from quant.web.app import _parse_symbols, _MAX_SYMBOLS
    many = ",".join(f"S{i}" for i in range(10_000))
    out = _parse_symbols(many)
    assert len(out) == _MAX_SYMBOLS               # 수만 개 → 상한으로 잘림
    # 중복 제거 + upper 옵션
    assert _parse_symbols("aapl, aapl , msft", upper=True) == ["AAPL", "MSFT"]
    assert _parse_symbols("  ") == []


def test_web_token_gate():
    """QUANT_WEB_TOKEN이 설정되면 토큰 없는 요청을 401로 막는다(노출 시 인증)."""
    import os
    from urllib.parse import urlparse
    from quant.web import server

    h = server.QuantHandler.__new__(server.QuantHandler)   # __init__ 우회

    class _Hdr(dict):
        def get(self, k, d=""):
            return dict.get(self, k, d)
    h.headers = _Hdr()

    os.environ.pop("QUANT_WEB_TOKEN", None)
    assert h._authorized(urlparse("/backtest?x=1"))        # 토큰 미설정 → 허용

    os.environ["QUANT_WEB_TOKEN"] = "sekret"
    try:
        assert not h._authorized(urlparse("/backtest"))              # 토큰 없음 → 거부
        assert h._authorized(urlparse("/backtest?token=sekret"))     # 일치 → 허용
        assert not h._authorized(urlparse("/backtest?token=nope"))   # 불일치 → 거부
        assert h._authorized(urlparse("/health"))                    # health는 항상 허용
    finally:
        os.environ.pop("QUANT_WEB_TOKEN", None)
