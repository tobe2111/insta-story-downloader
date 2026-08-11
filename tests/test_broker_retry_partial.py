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
  ④ 잔고 조회 실패로 판정 불가면 **재주문하지 않고** 크게 실패한다
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


def test_unverifiable_fill_is_never_reordered():
    """잔고를 못 읽으면 재주문하지 않고 크게 실패한다 (감사 55).

    예전 계약은 '판정 불가면 기존처럼 재시도'였다. 그런데 그 재시도가
    정확히 이 장치가 막으려던 도박이다 — 확인할 수 없는 상태에서 비멱등
    시장가 주문을 다시 내는 것. 첫 주문이 실제로 체결됐다면 실거래 포지션이
    2배가 되고, 그건 되돌릴 수 없다. 놓친 진입은 다음 봉에 다시 잡을 수
    있으니 두 결과의 무게가 다르다.
    """
    inner = _Flaky(fail_times=1, landed_after_fail=0.0, pos_raises=True)
    with pytest.raises(RuntimeError) as err:
        _robust(inner).market_order("X", "buy", 100.0, 10.0)
    assert inner.submitted == [100.0]              # 재주문 없음
    assert "직접 확인" in str(err.value)            # 사장님이 계좌를 봐야 한다


def test_landed_qty_distinguishes_zero_from_unknown():
    """0.0('아무것도 안 됐음을 확인')과 None('확인 불가')은 다른 값이다."""
    ok = _robust(_Flaky(fail_times=0))
    assert ok._landed_qty("X", "buy", 0.0) == 0.0        # 확인됨: 변화 없음
    assert ok._landed_qty("X", "buy", None) is None      # 제출 전 잔고 미상
    blind = _robust(_Flaky(fail_times=0, pos_raises=True))
    assert blind._landed_qty("X", "buy", 0.0) is None    # 지금 잔고 못 읽음


def test_final_failure_still_raises():
    inner = _Flaky(fail_times=99, landed_after_fail=0.0)
    with pytest.raises(RuntimeError):
        _robust(inner).market_order("X", "buy", 100.0, 10.0)
