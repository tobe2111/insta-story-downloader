"""체결 확인(포지션 변화) + 장 시간 가드 테스트 (순수 stdlib).

주식 실거래의 두 공백을 닫는다:
  1) 시장가 '접수'를 '체결'로 위조하지 않고, get_position 변화로 실제 체결을 확인.
  2) 닫힌 시장(장 시간 외·주말)에는 주문을 내지 않는다.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker.base import Broker, Order, Position
from quant.broker.retry import RobustBroker
from quant.live.market_hours import is_market_open, market_status


# ── 가짜 주식 브로커: 접수만 응답하고, 포지션은 지연 반영 ────────────────────

class _StockBroker(Broker):
    """시장가를 'accepted'(체결수량 0)로 응답하고, 포지션은 N번째 조회부터 채워진다."""

    def __init__(self, fill_after_polls: int = 1, fill_qty: float | None = None):
        self._pos = 0.0
        self._pending = 0.0
        self._polls = 0
        self._fill_after = fill_after_polls
        self._fill_qty = fill_qty          # None이면 요청 전량 체결
        self.orders = 0

    def get_cash(self) -> float:
        return 1_000_000.0

    def get_position(self, symbol: str) -> Position:
        # accepted 주문이 있으면 fill_after번째 조회에서 포지션에 반영
        if self._pending and self._polls >= self._fill_after:
            got = self._pending if self._fill_qty is None else self._fill_qty
            self._pos += got
            self._pending = 0.0
        self._polls += 1
        return Position(symbol, self._pos, 0.0)

    def market_order(self, symbol, side, quantity, price) -> Order:
        self.orders += 1
        self._pending = quantity if side == "buy" else -quantity
        self._polls = 0                    # 주문 시점부터 폴링 카운트
        return Order(symbol, side, quantity, price,
                     status="accepted", filled_quantity=0.0, order_id="OID1")


def test_confirm_fill_measures_position_delta():
    """접수 응답(체결 0)이어도 포지션이 채워지면 그 변화량을 체결로 인식한다."""
    inner = _StockBroker(fill_after_polls=1)
    rb = RobustBroker(inner, confirm_fills=True, fill_timeout=10.0,
                      fill_poll_interval=0.0, sleep=lambda s: None,
                      partial_retries=0)
    order = rb.market_order("005930", "buy", 10, 70000)
    assert order.status == "filled"
    assert abs(order.filled_quantity - 10.0) < 1e-9
    assert order.order_id == "OID1"
    assert inner.orders == 1               # 중복 주문 없음


def test_confirm_fill_timeout_reports_unfilled_no_duplicate():
    """시간 내 포지션이 안 변하면 미체결로 보고하고, 절대 재주문하지 않는다."""
    inner = _StockBroker(fill_after_polls=999)   # 사실상 체결 안 됨
    ticks = iter([0.0, 1.0, 2.0, 3.0, 99.0])
    rb = RobustBroker(inner, confirm_fills=True, fill_timeout=3.0,
                      fill_poll_interval=0.0, sleep=lambda s: None,
                      now=lambda: next(ticks), partial_retries=2)
    order = rb.market_order("005930", "buy", 10, 70000)
    assert order.status == "unfilled"
    assert order.filled_quantity == 0.0
    assert inner.orders == 1               # 미체결을 재주문으로 이중 집행하지 않음


def test_confirm_fill_partial_then_topup():
    """부분체결(6/10)이 포지션에 잡히면 잔량(4)을 재주문해 채운다."""
    # 첫 주문은 6주만 체결, 두 번째 주문에서 나머지 4주 체결
    class _Partial(_StockBroker):
        def __init__(self):
            super().__init__(fill_after_polls=1)
            self._seq = [6.0, 4.0]

        def market_order(self, symbol, side, quantity, price):
            self.orders += 1
            got = self._seq[min(self.orders - 1, len(self._seq) - 1)]
            self._pending = got if side == "buy" else -got
            self._polls = 0
            return Order(symbol, side, quantity, price,
                         status="accepted", filled_quantity=0.0, order_id="P")

    inner = _Partial()
    rb = RobustBroker(inner, confirm_fills=True, fill_timeout=5.0,
                      fill_poll_interval=0.0, sleep=lambda s: None,
                      partial_retries=2)
    order = rb.market_order("005930", "buy", 10, 70000)
    assert abs(order.filled_quantity - 10.0) < 1e-9
    assert order.status == "filled"
    assert inner.orders == 2               # 잔량 재주문 1회


def test_confirm_fills_off_is_unchanged():
    """confirm_fills=False(기본)면 포지션 폴링을 하지 않는다(기존 동작)."""
    inner = _StockBroker(fill_after_polls=0)
    rb = RobustBroker(inner, confirm_fills=False, partial_retries=0)
    order = rb.market_order("005930", "buy", 10, 70000)
    # 'accepted'는 체결상태가 아니므로 확인 없이는 미체결로 보고(위조 안 함)
    assert order.status == "unfilled"
    assert order.filled_quantity == 0.0


# ── 장 시간 가드 ─────────────────────────────────────────────────────────────

def _utc(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_crypto_always_open():
    # 코인·미지정 시장은 24시간 → 항상 개장
    assert is_market_open("crypto", _utc(2026, 1, 3, 3, 0))   # 토요일 새벽도 OK
    assert is_market_open("synthetic")
    assert is_market_open("unknown_market")


def test_us_stock_regular_hours():
    # 2026-01-05(월) 14:30 UTC = 09:30 ET 개장 직후
    assert is_market_open("us_stock", _utc(2026, 1, 5, 14, 30))
    # 21:00 UTC = 16:00 ET 마감
    assert is_market_open("us_stock", _utc(2026, 1, 5, 21, 0))
    # 21:01 UTC = 16:01 ET → 마감 후
    assert not is_market_open("us_stock", _utc(2026, 1, 5, 21, 1))
    # 13:00 UTC = 08:00 ET → 개장 전
    assert not is_market_open("us_stock", _utc(2026, 1, 5, 13, 0))


def test_kr_stock_regular_hours_and_weekend():
    # 2026-01-05(월) 00:30 UTC = 09:30 KST → 개장
    assert is_market_open("kr_stock", _utc(2026, 1, 5, 0, 30))
    # 06:31 UTC = 15:31 KST → 마감 후(정규장 15:30)
    assert not is_market_open("kr_stock", _utc(2026, 1, 5, 6, 31))
    # 2026-01-03(토) → 주말 휴장
    assert not is_market_open("kr_stock", _utc(2026, 1, 3, 3, 0))


def test_market_status_human_readable():
    s_open = market_status("kr_stock", _utc(2026, 1, 5, 0, 30))
    assert "개장" in s_open
    s_closed = market_status("us_stock", _utc(2026, 1, 3, 3, 0))
    assert "폐장" in s_closed and "공휴일" in s_closed   # 한계 명시
    assert "24시간" in market_status("crypto")
