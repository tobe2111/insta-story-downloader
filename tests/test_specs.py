"""거래소 규격(MarketSpec) 테스트 (순수 stdlib)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker.specs import MarketSpec, from_ccxt_market


def test_round_qty_step_and_min():
    spec = MarketSpec(min_qty=0.001, qty_step=0.001)
    assert abs(spec.round_qty(0.00567) - 0.005) < 1e-9   # 0.001 스텝 내림
    assert spec.round_qty(0.0005) == 0.0                 # 최소수량 미만 → 0


def test_round_price_tick():
    spec = MarketSpec(price_tick=0.5)
    assert spec.round_price(101.3) == 101.5   # 가장 가까운 틱
    assert spec.round_price(101.2) == 101.0


def test_is_tradeable_min_notional():
    spec = MarketSpec(min_notional=10.0)
    assert spec.is_tradeable(1.0, 20.0) is True    # 20달러 ≥ 10
    assert spec.is_tradeable(0.1, 20.0) is False   # 2달러 < 10
    assert spec.is_tradeable(0.0, 100.0) is False  # 수량 0


def test_from_ccxt_market_decimals():
    market = {
        "limits": {"amount": {"min": 0.0001}, "cost": {"min": 10.0}},
        "precision": {"amount": 3, "price": 2},  # 소수 자릿수 표기
    }
    spec = from_ccxt_market(market)
    assert spec.min_qty == 0.0001
    assert abs(spec.qty_step - 0.001) < 1e-12
    assert abs(spec.price_tick - 0.01) < 1e-12
    assert spec.min_notional == 10.0


def test_from_ccxt_market_step_form():
    market = {
        "limits": {"amount": {"min": 0.01}},
        "precision": {"amount": 0.01, "price": 0.5},  # 스텝 표기(실수)
    }
    spec = from_ccxt_market(market)
    assert abs(spec.qty_step - 0.01) < 1e-12
    assert abs(spec.price_tick - 0.5) < 1e-12
