"""RobustBroker 재시도/라운딩 테스트 (순수 stdlib — pandas 불필요)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# quant.broker 패키지는 pandas를 import하지 않으므로 일반 import로 충분하다.
from quant.broker import base, retry  # noqa: E402


class _FlakyBroker(base.Broker):
    """앞의 fail_times번은 실패하고 그 다음 성공하는 가짜 브로커."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0
        self._pos = base.Position("X", 0.0, 0.0)

    def get_cash(self):
        return 1000.0

    def get_position(self, symbol):
        return self._pos

    def market_order(self, symbol, side, quantity, price):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("일시적 오류")
        return base.Order(symbol, side, quantity, price, status="filled")


def test_retry_eventually_succeeds():
    inner = _FlakyBroker(fail_times=2)
    rb = retry.RobustBroker(inner, retries=3, backoff=0.0, sleep=lambda s: None)
    order = rb.market_order("X", "buy", 1.0, 100.0)
    assert order.status == "filled"
    assert inner.calls == 3  # 2번 실패 + 1번 성공


def test_retry_gives_up_and_raises():
    inner = _FlakyBroker(fail_times=99)
    sent = []

    class N:
        def send(self, msg, level="info"):
            sent.append((msg, level))

    rb = retry.RobustBroker(inner, retries=3, backoff=0.0,
                            notifier=N(), sleep=lambda s: None)
    try:
        rb.market_order("X", "buy", 1.0, 100.0)
        assert False, "예외가 발생해야 함"
    except RuntimeError:
        pass
    assert inner.calls == 3
    assert sent and sent[0][1] == "error"  # 최종 실패 알림 전송


def test_qty_rounding_skips_tiny():
    inner = _FlakyBroker(fail_times=0)
    rb = retry.RobustBroker(inner, min_qty=0.01, sleep=lambda s: None)
    order = rb.market_order("X", "buy", 0.005, 100.0)  # 최소수량 미만
    assert order.status == "skipped"
    assert inner.calls == 0  # 실제 주문 안 나감


def test_qty_step_floor():
    inner = _FlakyBroker(fail_times=0)
    rb = retry.RobustBroker(inner, qty_step=0.1, sleep=lambda s: None)
    order = rb.market_order("X", "buy", 0.37, 100.0)
    assert abs(order.quantity - 0.3) < 1e-9  # 0.1 스텝으로 내림
