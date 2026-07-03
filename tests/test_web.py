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
    render_form,
    render_monitor,
    render_sweep_form,
    run_backtest_html,
    run_sweep_html,
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


def test_render_monitor_no_state(tmp_path):
    doc = render_monitor([str(tmp_path / "nope.json")])
    assert "실행 중인" in doc and "<nav" in doc


def test_render_monitor_with_state(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "symbol": "X", "strategy": "s", "mode": "paper",
        "history": [{"time": "t", "equity": 10000, "weight": 0.5, "price": 0}],
        "positions": [{"symbol": "X", "quantity": 0.1, "avg_price": 100}],
        "orders": [],
    }), encoding="utf-8")
    doc = render_monitor([str(p)])
    assert "라이브 모니터" in doc and "<nav" in doc and "총자산" in doc


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
