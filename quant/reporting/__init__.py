"""리포팅 계층 — 지연(lazy) 임포트.

리포트/히트맵은 무거운(pandas/numpy) 모듈을 끌어오지만, 대시보드 렌더러는
표준 라이브러리만으로 동작한다. 지연 임포트로 필요한 것만 로드하여, 감시
대시보드 같은 경량 경로가 pandas 없이도 동작하게 한다.
"""
from __future__ import annotations

import importlib

__all__ = [
    "generate_report",
    "build_report_html",
    "generate_dashboard",
    "build_dashboard_html",
    "generate_heatmap",
    "build_heatmap_html",
    "strategy_attribution",
    "attribution_report",
    "ensemble_weight_report",
]

_LAZY = {
    "generate_report": "quant.reporting.html_report",
    "build_report_html": "quant.reporting.html_report",
    "generate_dashboard": "quant.reporting.dashboard",
    "build_dashboard_html": "quant.reporting.dashboard",
    "generate_heatmap": "quant.reporting.heatmap",
    "build_heatmap_html": "quant.reporting.heatmap",
    "strategy_attribution": "quant.reporting.attribution",
    "attribution_report": "quant.reporting.attribution",
    "ensemble_weight_report": "quant.reporting.attribution",
}


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module 'quant.reporting' has no attribute '{name}'")
    return getattr(importlib.import_module(module), name)
