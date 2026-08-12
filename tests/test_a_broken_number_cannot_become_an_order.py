"""망가진 숫자가 그대로 주문이 됐다 (감사 167).

`Broker.target_weight`은 **숫자가 주문이 되는 마지막 자리**다. 목표 비중과
현재가, 총자산을 받아 주문 수량을 계산하고 곧바로 `market_order`를 부른다.
페이퍼·실거래·웹훅·새벽 배치가 전부 이 문을 지난다.

그 문에 유한성 검사가 없었다.

    if price <= 0:
        return None          # ← NaN은 못 막는다. `NaN <= 0`은 False다.
    ...
    side = "buy" if delta > 0 else "sell"    # ← `NaN > 0`도 False

두 개의 False가 겹치면서, 망가진 숫자가 **조용히 '매도'로 떨어진다.** 실측:

    price  = NaN   →  ('sell', nan, nan)
    equity = NaN   →  ('sell', nan)
    weight = NaN   →  ('sell', nan)
    equity = inf   →  ('buy',  inf)

이 파일 맨 위에는 `safe_amount`가 있다. 독스트링에 이렇게 적혀 있다 —
"'inf 수량 주문'이나 NaN 비교 오류를 일으키는 것을 막는다". 정확히 이 일을
하라고 만든 함수인데, **정작 주문을 만드는 함수는 쓰지 않고 있었다.**
브로커 어댑터들(코인·국내·미국)은 잔고·체결을 읽을 때 성실히 통과시키는데,
그 값들이 모여 주문이 되는 자리에서는 아무도 안 물었다. 감사 135(제공자가
적은 출처를 아무도 안 읽음)와 같은 계열 — 부품은 있고 배선이 없다.

──────────────────────────────────────────────────────────────
정직하게 — 오늘 이 값들이 NaN이 되는 경로는 못 찾았다

· 전략 신호는 `_finalize`에서 `fillna(0)` + 클립을 지난다.
· 시세는 감사 163 뒤로 가격 결측 봉이 제거된다.
· `exposure_scale`은 설정 로더가 [0,1]로 클램프한다.
· 웹훅 페이로드의 price/close는 `p > 0` 검사를 지난다(NaN은 False라 탈락).

다만 웹훅의 **시세 헬퍼 폴백**만 그 검사가 빠져 있어 함께 고쳤다. 나머지는
'지금 새는 곳'이 아니라 **마지막 관문에 잠금장치가 없던 것**이다. 관문의
값어치는 평소에 아무 일도 안 하는 데 있다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.base import Broker, Order, Position  # noqa: E402
from quant.live.webhook import WebhookExecutor  # noqa: E402

NAN = float("nan")
INF = float("inf")


class _Spy(Broker):
    """브로커로 실제로 내려간 주문을 그대로 기록한다."""

    def __init__(self, held: float = 0.0):
        self.held = held
        self.sent: list[tuple[str, float, float]] = []

    def get_cash(self) -> float:
        return 1_000_000.0

    def get_position(self, symbol: str) -> Position:
        return Position(symbol, self.held, 100.0)

    def equity(self, marks) -> float:
        return 1_000_000.0

    def market_order(self, symbol, side, quantity, price) -> Order:
        self.sent.append((side, quantity, price))
        return Order(symbol, side, quantity, price)


BROKEN = [
    ("price", dict(weight=0.5, price=NAN, equity=1e6)),
    ("equity", dict(weight=0.5, price=100.0, equity=NAN)),
    ("weight", dict(weight=NAN, price=100.0, equity=1e6)),
    ("price=inf", dict(weight=0.5, price=INF, equity=1e6)),
    ("equity=inf", dict(weight=0.5, price=100.0, equity=INF)),
    ("weight=inf", dict(weight=INF, price=100.0, equity=1e6)),
]


@pytest.mark.parametrize("label,kw", BROKEN, ids=[b[0] for b in BROKEN])
def test_a_non_finite_input_never_reaches_the_exchange(label, kw):
    """⚠️ **반드시 포지션을 들고 검사해야 한다.**

    처음엔 보유 0으로 검사했는데, 그러면 `price=inf`일 때 목표수량이 0이
    되어 `delta`도 0 — 아래쪽 '수량 유한성' 검사가 대신 잡아 버린다. 그래서
    입력 검사를 통째로 지워도 검사가 통과했다(변이를 놓쳤다).

    보유가 있으면 갈린다: `price=inf` → 목표수량 0 → **전량 매도**인데
    수량은 50으로 **유한하다.** 아래 검사로는 절대 못 잡는다.
    """
    b = _Spy(held=50.0)
    order = b.target_weight("BTC/USDT", **kw)
    assert b.sent == [], f"{label}이(가) 망가졌는데 주문이 나갔다: {b.sent}"
    assert order is None


def test_an_infinite_price_does_not_liquidate_the_position():
    """위 검사의 핵심 사례를 따로 못 박는다.

    가격이 inf면 '목표 수량 0'으로 계산돼 보유분 전량이 매도로 나간다.
    수량 자체는 멀쩡한 숫자라서 수량 검사로는 안 걸린다 — 입력에서 막아야 한다.
    """
    b = _Spy(held=50.0)
    b.target_weight("BTC/USDT", weight=0.5, price=INF, equity=1e6)
    assert b.sent == [], (
        f"가격이 inf인데 보유분을 청산했다: {b.sent}")


def test_a_broken_number_does_not_quietly_become_a_sell():
    """NaN이 하필 '매도'가 되는 이유를 못 박는다.

    `NaN > 0`이 False라 `else` 가지로 떨어진다. 즉 값이 망가지면 시스템이
    **조용히 청산 주문을 내는 쪽**으로 기운다 — 가장 나쁜 실패 방향이다.
    """
    b = _Spy(held=50.0)
    b.target_weight("BTC/USDT", weight=0.5, price=NAN, equity=1e6)
    assert not any(side == "sell" for side, _, _ in b.sent), b.sent


def test_an_overflow_in_the_division_is_caught_too():
    """입력이 전부 유한해도 나눗셈이 넘칠 수 있다."""
    b = _Spy()
    b.target_weight("BTC/USDT", weight=1.0, price=1e-300, equity=1e308)
    assert b.sent == [], b.sent


# ── 대조군: 멀쩡한 주문은 그대로 나가야 한다 ──────────────────


def test_a_normal_order_still_goes_through():
    b = _Spy()
    b.target_weight("BTC/USDT", weight=0.5, price=100.0, equity=1_000_000.0)
    assert b.sent == [("buy", pytest.approx(5000.0), 100.0)], b.sent


def test_liquidation_is_never_blocked():
    """가장 중요한 대조군 — 빠져나오는 길을 막으면 덫이 된다.

    청산은 리밸런싱 밴드와도 무관하게 항상 나가야 한다.
    """
    b = _Spy(held=50.0)
    b.target_weight("X", weight=0.0, price=100.0, equity=1e6,
                    rebalance_band=0.5)
    assert b.sent == [("sell", pytest.approx(50.0), 100.0)], (
        f"청산 지시가 막혔다: {b.sent}")


def test_the_rebalance_band_still_skips_small_adjustments():
    """대조군 — 밴드가 죽으면 회전율이 폭증한다."""
    b = _Spy(held=50.0)
    b.target_weight("X", weight=0.005, price=100.0, equity=1e6,
                    rebalance_band=0.02)
    assert b.sent == [], b.sent


def test_a_zero_or_negative_price_is_still_refused():
    """대조군 — 원래 있던 검사가 사라지면 안 된다."""
    for bad in (0.0, -100.0):
        b = _Spy()
        b.target_weight("X", weight=0.5, price=bad, equity=1e6)
        assert b.sent == [], (bad, b.sent)


# ── 웹훅의 시세 헬퍼 폴백 ─────────────────────────────────────


def _webhook(price_fn) -> tuple[WebhookExecutor, _Spy]:
    b = _Spy()
    return WebhookExecutor(b, price_fn=price_fn), b


def test_a_price_helper_returning_nan_is_refused():
    """페이로드 경로에는 `> 0` 검사가 있었는데 헬퍼 폴백에만 없었다."""
    ex, b = _webhook(lambda s: NAN)
    res = ex.execute({"symbol": "BTC/USDT", "action": "long"})
    assert res["ok"] is False and b.sent == [], (res, b.sent)


def test_a_nan_in_the_payload_was_already_refused():
    """대조군 — 페이로드 쪽은 원래 막고 있었다. 그 검사를 지키는지 본다."""
    ex, b = _webhook(None)
    res = ex.execute({"symbol": "BTC/USDT", "action": "long", "price": "nan"})
    assert res["ok"] is False and b.sent == [], (res, b.sent)


def test_a_healthy_price_helper_still_trades():
    """대조군 — 헬퍼가 멀쩡하면 주문은 나가야 한다."""
    ex, b = _webhook(lambda s: 250.0)
    res = ex.execute({"symbol": "BTC/USDT", "action": "long"})
    assert res["ok"] is True and b.sent, (res, b.sent)
    assert b.sent[0][0] == "buy"
