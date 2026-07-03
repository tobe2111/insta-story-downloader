"""웹 UI 테스트.

폼 렌더링은 표준 라이브러리만으로 동작(pandas 불필요), 백테스트 실행 경로는
pandas가 필요하다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.web.app import MARKETS, STRATEGIES, render_form, run_backtest_html


def test_render_form_has_controls():
    doc = render_form()
    assert "<form" in doc and 'action="/backtest"' in doc
    for s in STRATEGIES:
        assert s in doc
    for m in MARKETS:
        assert m in doc


def test_render_form_message():
    assert "테스트경고" in render_form("테스트경고")


def test_run_backtest_html_synthetic():
    doc = run_backtest_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "200"})
    assert "성과 지표" in doc and "샤프지수" in doc
    assert 'href="/"' in doc  # 다시 실행 링크


def test_run_backtest_html_ensemble():
    doc = run_backtest_html({"market": "synthetic", "strategy": "ensemble",
                             "limit": "150"})
    assert "<svg" in doc


def test_run_backtest_html_bad_limit_defaults():
    # limit이 숫자가 아니어도 기본값으로 처리되어 크래시하지 않아야 한다
    doc = run_backtest_html({"market": "synthetic", "strategy": "rsi",
                             "limit": "abc"})
    assert "성과 지표" in doc
