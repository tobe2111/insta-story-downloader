"""거래소 주문 규격이 **실제로 걸리는가** (감사 139).

`quant/broker/specs.py`에는 `MarketSpec`(최소수량·수량스텝·최소금액)과
ccxt 시장 정보에서 그것을 만들어 주는 `from_ccxt_market()`이 있다. 잘
만들어져 있고 단위 검사도 있었다.

그런데 **`from_ccxt_market()`을 부르는 곳이 저장소에 한 곳도 없었다.**
CLI는 RobustBroker를 이렇게 만든다.

    broker = RobustBroker(inner, retries=3, backoff=2.0, confirm_fills=...)

spec도, min_qty·qty_step·min_notional도 안 준다 → 전부 기본값 0.0 →
**규격 검사가 통째로 꺼진 상태.** 감사 135(제공자가 적어 둔 소스를 아무도
안 읽음)와 같은 계열이다 — 만들어 놓고 배선하지 않은 장치.

실전 전환 시 무슨 일이 나는가. 8만원을 20종목에 나누면 종목당 약
4,000원(≈$2.9)인데 주요 코인 거래소의 최소 주문금액은 보통 $5~10이다.
미리 걸러내지 못하니 주문을 보냈다가 거절당하고, 재시도 3회까지 같은
실패를 반복한다. 수량 스텝(BTC 0.00001 등)도 마찬가지다.

고침: 규격을 주입받지 않았으면 RobustBroker가 **주문 직전에 브로커에게
그 종목 규격을 묻는다**(`market_spec(symbol)`). 코인 브로커는 ccxt의
시장 정보로 답한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.base import Broker, Order, Position  # noqa: E402
from quant.broker.retry import RobustBroker  # noqa: E402
from quant.broker.specs import MarketSpec  # noqa: E402


class _Inner(Broker):
    """규격을 알려 주는 브로커 — 실제 거래소 어댑터가 하는 일."""

    def __init__(self, spec=None):
        self.sent: list = []
        self._spec = spec

    def market_spec(self, symbol: str):
        return self._spec

    def get_cash(self) -> float:
        return 100_000.0

    def get_position(self, symbol: str) -> Position:
        return Position(symbol, 0.0, 0.0)

    def market_order(self, symbol, side, quantity, price) -> Order:
        self.sent.append((symbol, side, quantity))
        return Order(symbol, side, quantity, price,
                     status="closed", filled_quantity=quantity)


# ── 최소 주문금액 ─────────────────────────────────────────────


def test_an_order_below_the_exchange_minimum_never_leaves_the_house():
    """$5 최소인 거래소에 $2.9 주문을 보내지 않는다 — 거절될 것을 안다."""
    inner = _Inner(MarketSpec(min_notional=5.0))
    b = RobustBroker(inner, retries=1, sleep=lambda s: None)
    order = b.market_order("BTC/USDT", "buy", 0.0000456, 63_656.0)  # ≈$2.9
    assert order.status == "skipped", f"규격 미만인데 주문이 나갔다: {order}"
    assert inner.sent == [], f"거래소로 실제 전송됐다: {inner.sent}"


def test_an_order_above_the_minimum_still_goes(tmp_path):
    """대조군 — 규격을 만족하면 그대로 나가야 한다(가드가 덫이 되면 안 된다)."""
    inner = _Inner(MarketSpec(min_notional=5.0))
    b = RobustBroker(inner, retries=1, sleep=lambda s: None)
    order = b.market_order("BTC/USDT", "buy", 0.001, 63_656.0)      # ≈$64
    assert order.status != "skipped", f"살 수 있는데 막았다: {order}"
    assert inner.sent, "규격을 만족하는데 주문이 안 나갔다"


# ── 수량 스텝 ─────────────────────────────────────────────────


def test_the_quantity_is_floored_to_the_exchange_step():
    inner = _Inner(MarketSpec(qty_step=0.001, min_notional=1.0))
    b = RobustBroker(inner, retries=1, sleep=lambda s: None)
    b.market_order("BTC/USDT", "buy", 0.0019, 63_656.0)
    assert inner.sent, "주문이 안 나갔다"
    sent_qty = inner.sent[0][2]
    assert abs(sent_qty - 0.001) < 1e-12, (
        f"수량 스텝(0.001)에 맞춰 내림하지 않았다: {sent_qty}")


# ── 배선 자체 ─────────────────────────────────────────────────


def test_the_broker_is_asked_for_the_spec_when_none_was_injected():
    """주입이 없으면 **물어본다** — 이 물음이 없어서 감사 139가 생겼다."""
    asked: list = []

    class _Asking(_Inner):
        def market_spec(self, symbol):
            asked.append(symbol)
            return MarketSpec(min_notional=5.0)

    inner = _Asking()
    RobustBroker(inner, retries=1, sleep=lambda s: None).market_order(
        "ETH/USDT", "buy", 0.00001, 3_000.0)
    assert asked == ["ETH/USDT"], (
        f"브로커에게 규격을 묻지 않았다(물음 기록: {asked})")


def test_an_injected_spec_wins():
    """명시적으로 준 규격이 최우선 — 테스트·수동 지정이 무시되면 안 된다."""
    class _Lax(_Inner):
        def market_spec(self, symbol):
            return MarketSpec()          # 거래소는 제한 없다고 답한다

    inner = _Lax()
    b = RobustBroker(inner, retries=1, sleep=lambda s: None,
                     min_notional=1_000.0)
    order = b.market_order("ETH/USDT", "buy", 0.001, 3_000.0)   # $3
    assert order.status == "skipped", "주입한 규격이 무시됐다"


def test_a_broker_without_specs_still_trades():
    """규격을 모르는 브로커여도 매매는 계속된다 — 몰라서 멈추지는 않는다."""
    class _Silent(Broker):
        def __init__(self):
            self.sent = []

        def get_cash(self):
            return 1000.0

        def get_position(self, symbol):
            return Position(symbol, 0.0, 0.0)

        def market_order(self, symbol, side, quantity, price):
            self.sent.append(quantity)
            return Order(symbol, side, quantity, price, status="closed",
                         filled_quantity=quantity)

    inner = _Silent()
    b = RobustBroker(inner, retries=1, sleep=lambda s: None)
    assert b.market_order("X", "buy", 0.5, 10.0).status != "skipped"
    assert inner.sent == [0.5]


def test_a_failing_spec_lookup_does_not_block_the_order():
    """규격 조회가 터져도 주문은 나간다 — 조회 실패가 매매를 막으면 안 된다."""
    class _Boom(_Inner):
        def market_spec(self, symbol):
            raise RuntimeError("거래소 응답 없음")

    inner = _Boom()
    b = RobustBroker(inner, retries=1, sleep=lambda s: None)
    assert b.market_order("X/Y", "buy", 1.0, 10.0).status != "skipped"
    assert inner.sent


def test_the_crypto_adapter_answers_the_question():
    """코인 어댑터가 ccxt 시장 정보로 규격을 만들어 주는가."""
    from quant.broker.crypto_live import CryptoLiveBroker

    class _Client:
        markets = {"BTC/USDT": {
            "limits": {"amount": {"min": 0.0001}, "cost": {"min": 5.0}},
            "precision": {"amount": 0.00001},
        }}

    b = CryptoLiveBroker(client=_Client())
    spec = b.market_spec("BTC/USDT")
    assert spec is not None, "규격을 만들지 못했다"
    assert spec.min_notional == 5.0, spec
    assert b.market_spec("NOPE/USDT") is None, "없는 종목에 규격을 지어낸다"
