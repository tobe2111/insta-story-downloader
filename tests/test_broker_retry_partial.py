"""재시도 경로 계약 검사 — 부분 체결 뒤 전량 재주문 금지.

배경(2026-08-11 감사): 시장가 주문은 멱등하지 않다. 응답이 타임아웃돼도
거래소에는 이미 체결됐을 수 있어, RobustBroker는 재시도 전에 잔고로
'이미 체결됐는가'를 확인한다. 그런데 확인 기준이 **전량 체결**뿐이었다.
60%만 체결된 채 응답이 끊기면 나머지 40%가 아니라 100%를 다시 주문해
총 160%가 된다 — 이중 체결을 막으려던 장치가 부분 체결에서는 오히려
초과 체결을 만드는 구조였다.

핵심 계약:
  ① 전량 체결 확인 시 재주문하지 않는다(기존 동작 유지)
  ② 부분 체결이면 **남은 수량만** 재주문한다
  ③ 잔여가 무시할 만큼 작으면 체결로 마감한다
  ④ 잔고 조회 실패로 판정 불가면 기존처럼 재시도한다
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker.base import Order, Position  # noqa: E402
from quant.broker.retry import RobustBroker  # noqa: E402


class _Flaky:
    """첫 N회는 예외를 던지고, 그 사이 잔고는 landed만큼 늘어나는 브로커."""

    def __init__(self, fail_times, landed_after_fail=0.0, pos_raises=False):
        self.fail_times = fail_times
        self.landed = landed_after_fail
        self.pos_raises = pos_raises
        self.qty_now = 0.0
        self.submitted: list[float] = []

    def get_cash(self):
        return 1_000_000.0

    def get_position(self, symbol):
        if self.pos_raises:
            raise RuntimeError("잔고 조회 실패")
        return Position(symbol, self.qty_now, 0.0)

    def market_order(self, symbol, side, quantity, price):
        self.submitted.append(quantity)
        if self.fail_times > 0:
            self.fail_times -= 1
            self.qty_now += self.landed          # 응답은 끊겼지만 체결은 됐다
            raise RuntimeError("timeout")
        self.qty_now += quantity
        return Order(symbol, side, quantity, price,
                     status="filled", filled_quantity=quantity)


def _robust(inner):
    return RobustBroker(inner, retries=3, backoff=0.0,
                        sleep=lambda s: None)


def test_full_fill_is_not_reordered():
    inner = _Flaky(fail_times=1, landed_after_fail=100.0)
    out = _robust(inner).market_order("X", "buy", 100.0, 10.0)
    assert out.status == "filled" and out.filled_quantity == 100.0
    assert inner.submitted == [100.0]          # 재주문 없음
    assert inner.qty_now == 100.0              # 이중 체결 없음


def test_partial_fill_reorders_only_the_remainder():
    """이 테스트가 잡는 사고: 60 체결 후 100을 재주문해 160이 되는 것."""
    inner = _Flaky(fail_times=1, landed_after_fail=60.0)
    out = _robust(inner).market_order("X", "buy", 100.0, 10.0)
    assert inner.submitted == [100.0, 40.0], "남은 40만 재주문해야 한다"
    assert inner.qty_now == pytest.approx(100.0)   # 총 100 — 초과 없음
    assert out.status == "filled"


def test_tiny_remainder_is_closed_out():
    inner = _Flaky(fail_times=1, landed_after_fail=99.99999)
    out = _robust(inner).market_order("X", "buy", 100.0, 10.0)
    assert len(inner.submitted) == 1
    assert out.filled_quantity == pytest.approx(100.0, rel=1e-4)


def test_sell_side_uses_decrease_as_landed():
    inner = _Flaky(fail_times=1, landed_after_fail=0.0)
    inner.qty_now = 100.0
    # 매도는 잔고가 줄어야 체결 — landed를 음수 증가로 흉내
    inner.landed = -60.0
    out = _robust(inner).market_order("X", "sell", 100.0, 10.0)
    assert inner.submitted == [100.0, 40.0]
    assert out.status == "filled"


def test_unknown_balance_falls_back_to_plain_retry():
    inner = _Flaky(fail_times=1, landed_after_fail=0.0, pos_raises=True)
    out = _robust(inner).market_order("X", "buy", 100.0, 10.0)
    assert inner.submitted == [100.0, 100.0]   # 판정 불가 → 기존대로 재시도
    assert out.status == "filled"


def test_final_failure_still_raises():
    inner = _Flaky(fail_times=99, landed_after_fail=0.0)
    with pytest.raises(RuntimeError):
        _robust(inner).market_order("X", "buy", 100.0, 10.0)
