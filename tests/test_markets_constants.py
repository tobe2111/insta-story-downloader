"""공용 시장 상수(quant.markets)의 정합성 테스트 — 단일 출처가 실제로
다른 곳과 어긋나지 않는지 고정한다(중복 정의 드리프트 방지의 마지막 안전망).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.markets import (
    LIVE_BROKER_FOR_MARKET,
    SCHEDULED_MARKETS,
    STRATEGY_GRIDS,
)


def test_markets_module_is_dependency_free():
    """quant.markets 는 pandas/numpy 없이 임포트돼야 한다(폼 렌더 경로 안전)."""
    import importlib
    import quant.markets as m
    importlib.reload(m)   # 임포트가 성공하면 통과(무거운 의존 없음)
    assert isinstance(m.STRATEGY_GRIDS, dict)


def test_cli_and_web_share_same_grids():
    """CLI validate와 웹 최적화가 '같은 객체'의 그리드를 쓴다(드리프트 불가)."""
    from quant import cli
    from quant.web import app
    assert cli._VALIDATE_GRIDS is STRATEGY_GRIDS
    assert app._OPT_GRIDS is STRATEGY_GRIDS


def test_scheduled_markets_have_live_brokers():
    """장 시간 가드 대상 시장(주식)은 모두 실거래 브로커 매핑이 있어야 한다."""
    for m in SCHEDULED_MARKETS:
        assert m in LIVE_BROKER_FOR_MARKET


def test_grid_keys_are_real_strategies():
    """STRATEGY_GRIDS의 키가 실제 등록된 전략이고, 파라미터명이 생성자와 일치한다."""
    import inspect

    from quant.strategies import get_strategy, list_strategies

    for name, grid in STRATEGY_GRIDS.items():
        assert name in list_strategies(), f"미등록 전략: {name}"
        params = inspect.signature(type(get_strategy(name)).__init__).parameters
        for key in grid:
            assert key in params, f"{name} 그리드의 '{key}'가 생성자에 없음"


def test_tradingview_ips_are_unique_and_valid():
    """공식 IP 목록에 중복이 없고 형식이 유효하다."""
    import ipaddress

    from quant.live.webhook import TRADINGVIEW_IPS
    assert len(TRADINGVIEW_IPS) == 4
    for ip in TRADINGVIEW_IPS:
        ipaddress.ip_address(ip)   # 잘못된 형식이면 ValueError
