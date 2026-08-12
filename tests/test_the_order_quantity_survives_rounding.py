"""눈금에 딱 맞는 수량이 한 칸 깎여 나갔다 (감사 164).

거래소는 수량을 아무렇게나 못 받는다. 최소 단위(lot/step)가 있고, 그 배수로
내려서 보내야 한다. `MarketSpec.round_qty`가 그 일을 한다.

    qty = math.floor(qty / self.qty_step) * self.qty_step

정확히 나누어떨어지는 수량이 **한 칸 깎인다.** 부동소수 나눗셈 때문이다.

    0.3 / 0.1 == 2.9999999999999996   →  floor 2  →  0.2

실측(스텝 0.1):

    0.3  → 0.2     33.3% 덜 주문
    0.7  → 0.6     14.3% 덜 주문
    8.2  → 8.1      1.2% 덜 주문
    (스텝 0.0001) 0.0003 → 0.0002    33.3%

바로 뒤에 `round(qty, 12)`가 있지만 아무 소용이 없다 — 이미 깎인 뒤다.

가장 아픈 곳은 **청산**이다. 0.3개를 전부 팔라고 지시해도 0.2개만 나가고
0.1개가 그대로 남는다. 손절·킬스위치가 "정리했다"고 말한 뒤에도 포지션이
살아 있다는 뜻이다.

──────────────────────────────────────────────────────────────
같은 파일의 두 번째 결함 — precision을 값만 보고 추측했다

    if isinstance(prec, float) and 0 < prec < 1:   ← 1.0 이상이면 버린다
        return prec
    return 0.0                                     ← '제약 없음'

ccxt는 거래소 모드에 따라 이 칸을 다른 뜻으로 채운다.

    TICK_SIZE      : 값이 곧 단위 (0.001 · 1.0 · 10.0)
    DECIMAL_PLACES : 값이 소수 자릿수 (3 → 0.001)

그리고 **주요 거래소는 전부 TICK_SIZE다** — binance·okx·bybit·upbit·
coinbase를 ccxt 4.5.70에서 확인했다. 단위가 1 이상인 시장(정수 단위로만
살 수 있는 종목)이 조용히 '제약 없음'이 됐고, 하필 그쪽이 라운딩이 제일
중요한 시장이다. 이제 거래소의 `precisionMode`를 넘겨받아 추측하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.base import Order, Position  # noqa: E402
from quant.broker.retry import RobustBroker  # noqa: E402
from quant.broker.specs import (  # noqa: E402
    DECIMAL_PLACES,
    TICK_SIZE,
    MarketSpec,
    from_ccxt_market,
)

# 정확히 나누어떨어지는데 깎여 나가던 것들
EXACT = [(0.3, 0.1), (0.7, 0.1), (8.2, 0.1), (0.29, 0.01), (0.0003, 0.0001),
         (1.3, 0.1), (2.9, 0.1)]


# ── 눈금에 맞는 수량은 그대로 나가야 한다 ─────────────────────


@pytest.mark.parametrize("qty,step", EXACT)
def test_a_quantity_on_the_grid_is_not_shaved_off(qty, step):
    got = MarketSpec(qty_step=step).round_qty(qty)
    assert got == pytest.approx(qty, abs=step * 1e-9), (
        f"{qty}는 스텝 {step}의 정확한 배수인데 {got}가 나왔다 — "
        f"{100 * (qty - got) / qty:.1f}% 덜 주문한다")


@pytest.mark.parametrize("qty,step,want", [(0.35, 0.1, 0.3), (0.99, 0.1, 0.9),
                                           (3.7, 1.0, 3.0), (77.0, 10.0, 70.0)])
def test_a_quantity_between_the_grid_is_still_rounded_down(qty, step, want):
    """대조군 — 내림은 유지돼야 한다. 올림하면 있는 돈보다 많이 주문한다."""
    assert MarketSpec(qty_step=step).round_qty(qty) == pytest.approx(want)


def test_below_the_minimum_is_still_zero():
    """대조군 — 최소수량 미만은 0이어야 한다(보내 봐야 거절당한다)."""
    assert MarketSpec(min_qty=1.0, qty_step=1.0).round_qty(0.6) == 0.0


def test_no_step_means_no_rounding():
    """대조군 — 규격을 모르면 손대지 않는다."""
    assert MarketSpec().round_qty(0.123456789) == pytest.approx(0.123456789)


def test_an_order_exactly_at_the_minimum_notional_is_allowed():
    """0.29 * 100.0 == 28.999999999999996 — 딱 최소금액인데 미달로 읽힌다.

    (0.3 * 10.0은 3.0000000000000004로 **위로** 새기 때문에 이 검사가 헛돈다.
     아래로 새는 곱을 골라야 한다.)
    """
    assert 0.29 * 100.0 < 29.0, "이 곱이 아래로 안 새면 검사가 헛돈다"
    assert MarketSpec(min_notional=29.0).is_tradeable(0.29, 100.0), (
        "정확히 최소금액인 주문을 부동소수 오차로 건너뛴다")
    assert not MarketSpec(min_notional=29.0).is_tradeable(0.28, 100.0), (
        "진짜로 미달인 주문은 여전히 걸러야 한다")


# ── 청산이 끝까지 가는가 (배선) ───────────────────────────────


class _FakeExchange:
    """규격을 알려주고, 주문받은 수량을 그대로 기록하는 가짜 거래소."""

    def __init__(self, spec: MarketSpec, held: float):
        self.spec, self.held, self.sent = spec, held, []

    def get_cash(self) -> float:
        return 1_000_000.0

    def get_position(self, symbol: str) -> Position:
        return Position(symbol, self.held, 100.0)

    def market_spec(self, symbol: str) -> MarketSpec:
        return self.spec

    def market_order(self, symbol, side, quantity, price) -> Order:
        self.sent.append(quantity)
        self.held -= quantity if side == "sell" else -quantity
        return Order(symbol, side, quantity, price, status="filled",
                     filled_quantity=quantity)


def test_closing_a_position_actually_closes_it():
    """감사 164의 본체 — 0.3개를 전부 팔라고 했는데 0.2개만 나가던 자리."""
    ex = _FakeExchange(MarketSpec(qty_step=0.1), held=0.3)
    RobustBroker(ex, retries=1).market_order("ETH/USDT", "sell", 0.3, 3000.0)

    assert ex.sent == [pytest.approx(0.3)], (
        f"청산 지시 0.3개인데 {ex.sent}가 나갔다")
    assert ex.held == pytest.approx(0.0, abs=1e-9), (
        f"청산했는데 {ex.held}개가 남아 있다 — "
        "손절·킬스위치가 '정리했다'고 말한 뒤에도 포지션이 살아 있다는 뜻이다")


def test_a_partial_target_is_still_rounded_down_through_the_broker():
    """대조군 — 브로커를 지나도 내림은 살아 있어야 한다."""
    ex = _FakeExchange(MarketSpec(qty_step=0.1), held=1.0)
    RobustBroker(ex, retries=1).market_order("ETH/USDT", "sell", 0.35, 3000.0)
    assert ex.sent == [pytest.approx(0.3)], ex.sent


def test_an_integer_lot_market_gets_an_integer_order():
    """정수 단위 시장(SHIB·PEPE류)에 3.7개를 보내면 거절당한다."""
    ex = _FakeExchange(MarketSpec(min_qty=1.0, qty_step=1.0), held=10.0)
    RobustBroker(ex, retries=1).market_order("SHIB/USDT", "sell", 3.7, 1.0)
    assert ex.sent == [pytest.approx(3.0)], ex.sent


# ── precision을 추측하지 않는가 ───────────────────────────────


def _spec(amount, mode=None) -> MarketSpec:
    return from_ccxt_market({"precision": {"amount": amount}, "limits": {}}, mode)


def test_a_tick_size_of_one_is_a_real_constraint():
    """이것이 두 번째 결함 — 단위 1.0이 '제약 없음'으로 사라졌다."""
    assert _spec(1.0, TICK_SIZE).qty_step == 1.0, (
        "정수 단위 시장의 스텝이 사라졌다 — 3.7개를 그대로 보내 거절당한다")
    assert _spec(10.0, TICK_SIZE).qty_step == 10.0


def test_tick_size_and_decimal_places_are_read_differently():
    """같은 값 3이 모드에 따라 다른 뜻이다 — 추측하면 안 되는 이유."""
    assert _spec(3, TICK_SIZE).qty_step == 3.0
    assert _spec(3, DECIMAL_PLACES).qty_step == pytest.approx(0.001)


def test_a_small_tick_still_works():
    """대조군 — 원래 되던 것이 깨지면 안 된다."""
    assert _spec(0.001, TICK_SIZE).qty_step == pytest.approx(0.001)
    assert _spec(8, DECIMAL_PLACES).qty_step == pytest.approx(1e-8)


def test_junk_precision_is_treated_as_no_constraint():
    """모르는 값으로 규격을 지어내면 멀쩡한 주문까지 막는다."""
    for junk in (None, "", "abc", {}, True, -1):
        assert _spec(junk, TICK_SIZE).qty_step == 0.0, junk


def test_a_numeric_string_is_still_understood():
    assert _spec("0.001", TICK_SIZE).qty_step == pytest.approx(0.001)
    assert _spec("3", DECIMAL_PLACES).qty_step == pytest.approx(0.001)


def test_the_limits_are_still_read():
    """대조군 — precision만 고치다 limits를 흘리면 안 된다."""
    s = from_ccxt_market({"precision": {"amount": 0.1},
                          "limits": {"amount": {"min": 0.5},
                                     "cost": {"min": 10.0}}}, TICK_SIZE)
    assert (s.min_qty, s.qty_step, s.min_notional) == (0.5, 0.1, 10.0)


class _FakeCcxt:
    """precisionMode를 알려주는 가짜 ccxt 클라이언트."""

    def __init__(self, mode, amount):
        self.precisionMode = mode
        self.markets = {"BTC/USDT": {"precision": {"amount": amount},
                                     "limits": {}}}


def test_the_exchange_mode_is_actually_passed_in():
    """배선 검사 — 규격을 읽는 곳이 거래소 모드를 함께 넘기는가.

    ⚠️ 여기서 `"precisionMode" in src`로 쓰면 안 된다. 부품이 고쳐졌는지가
       아니라 **배선이 그 부품에 모드를 주는지**를 봐야 한다(㉑). 같은 값
       3을 두 모드로 읽혀서 답이 갈리는지로 본다 — 모드를 안 넘기면 두
       경우가 같은 답을 낸다.
    """
    from quant.broker.crypto_live import CryptoLiveBroker

    def _step_of(mode):
        b = CryptoLiveBroker(client=_FakeCcxt(mode, 3))
        return b.market_spec("BTC/USDT").qty_step

    assert _step_of(TICK_SIZE) == 3.0, (
        "거래소가 TICK_SIZE라고 말했는데 3을 소수 자릿수로 읽는다")
    assert _step_of(DECIMAL_PLACES) == pytest.approx(0.001)


def test_an_exchange_that_hides_its_mode_still_gets_a_spec():
    """대조군 — 모드를 모른다고 규격을 통째로 버리면 안 된다."""
    from quant.broker.crypto_live import CryptoLiveBroker

    class _NoMode:
        markets = {"BTC/USDT": {"precision": {"amount": 0.001}, "limits": {}}}

    spec = CryptoLiveBroker(client=_NoMode()).market_spec("BTC/USDT")
    assert spec.qty_step == pytest.approx(0.001)
