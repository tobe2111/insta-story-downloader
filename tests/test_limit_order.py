"""페이퍼 브로커 지정가 주문(부분체결) 시뮬레이션 테스트 (순수 stdlib).

지정가는 봉의 고저가가 지정가를 지나야만 체결되고, fill_fraction으로
부분체결을 흉내낸다. 기존 market_order 동작은 그대로여야 한다(하위 호환).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import PaperBroker


def test_buy_limit_fills_when_low_crosses():
    b = PaperBroker(cash=10_000, fee=0.0)
    o = b.limit_order("X", "buy", 10, limit_price=100, bar_high=110, bar_low=95)
    assert o.status == "filled"
    assert o.filled_quantity == 10.0
    assert b.get_position("X").quantity == 10.0
    assert b.get_position("X").avg_price == 100.0    # 체결가는 지정가(개선 없음)
    assert abs(b.get_cash() - 9_000) < 1e-9


def test_buy_limit_not_filled_when_price_stays_above():
    b = PaperBroker(cash=10_000, fee=0.0)
    o = b.limit_order("X", "buy", 10, limit_price=100, bar_high=120, bar_low=105)
    assert o.status == "open"
    assert o.filled_quantity == 0.0
    assert b.get_position("X").quantity == 0.0
    assert b.get_cash() == 10_000                    # 현금 변화 없음
    assert b.order_log[-1] is o                      # 미체결도 기록은 남긴다


def test_sell_limit_fills_when_high_crosses():
    b = PaperBroker(cash=10_000, fee=0.0)
    b.market_order("X", "buy", 5, 100)
    o = b.limit_order("X", "sell", 5, limit_price=110, bar_high=115, bar_low=99)
    assert o.status == "filled"
    assert b.get_position("X").quantity == 0.0
    assert abs(b.get_cash() - (10_000 - 500 + 550)) < 1e-9


def test_sell_limit_not_filled_when_high_below_limit():
    b = PaperBroker(cash=10_000, fee=0.0)
    b.market_order("X", "buy", 5, 100)
    o = b.limit_order("X", "sell", 5, limit_price=110, bar_high=108, bar_low=99)
    assert o.status == "open"
    assert b.get_position("X").quantity == 5.0       # 포지션 유지


def test_partial_fill_fraction():
    b = PaperBroker(cash=10_000, fee=0.0)
    o = b.limit_order("X", "buy", 10, limit_price=100, bar_high=105, bar_low=95,
                      fill_fraction=0.4)
    assert o.status == "partial"
    assert o.quantity == 10.0                        # 요청 수량은 그대로
    assert abs(o.filled_quantity - 4.0) < 1e-12
    assert abs(b.get_position("X").quantity - 4.0) < 1e-12
    assert abs(b.get_cash() - (10_000 - 400)) < 1e-9  # 체결분만 현금 차감


def test_fill_fraction_is_clamped():
    b = PaperBroker(cash=10_000, fee=0.0)
    o = b.limit_order("X", "buy", 10, limit_price=100, bar_high=105, bar_low=95,
                      fill_fraction=2.5)             # 1.0으로 클램프
    assert o.status == "filled"
    assert o.filled_quantity == 10.0
    o2 = b.limit_order("X", "buy", 10, limit_price=100, bar_high=105, bar_low=95,
                       fill_fraction=-1.0)           # 0.0으로 클램프 → 미체결
    assert o2.status == "open" and o2.filled_quantity == 0.0


def test_limit_fill_accounting_matches_market_order():
    """체결된 지정가는 같은 가격의 시장가와 회계(현금·평단)가 동일해야 한다."""
    a = PaperBroker(cash=10_000, fee=0.001)
    m = PaperBroker(cash=10_000, fee=0.001)
    a.limit_order("X", "buy", 3, limit_price=100, bar_high=101, bar_low=99)
    m.market_order("X", "buy", 3, 100)
    assert abs(a.get_cash() - m.get_cash()) < 1e-9
    assert a.get_position("X").quantity == m.get_position("X").quantity
    assert a.get_position("X").avg_price == m.get_position("X").avg_price


def test_market_order_unchanged_regression():
    """market_order 기본 동작은 지정가 추가와 무관하게 그대로다."""
    b = PaperBroker(cash=10_000, fee=0.0)
    o = b.market_order("X", "buy", 10, 100)
    assert o.status == "filled" and o.filled_quantity == 10.0
    assert b.get_cash() == 9_000
