"""브로커가 없는 돈을 만들어내지 않는가 (2026-08-14 감사 233).

`PaperBroker`는 8마일 챌린지의 **모든 기록이 나오는 곳**이다. 자산·수익률·
낙폭·킬스위치·사이트·SNS 캡션이 전부 이 클래스의 현금과 보유 위에 쌓인다.
그런데 이 클래스는 **자기가 들고 있는 돈을 한 번도 확인하지 않았다.**

실제로 돌려 본 결과(고치기 전):

    수량 NaN          → 현금 nan · 보유 nan
    가격 inf          → 현금 -inf
    가격 -50 매수     → **현금이 늘고 보유도 늘었다**   (공짜 자산)
    수량 -10 매수     → 공매도가 됐다                    (방향 뒤집힘)
    수량 0            → 아무 일도 안 했는데 '체결' 1건
    100만원으로 500만원어치 매수 → 그냥 체결. 현금 -400만원

첫 줄이 가장 나쁘다. 계좌가 NaN이 되면 낙폭도 NaN이 되고, 킬스위치는
`낙폭 < 문턱`을 NaN으로 비교해 **항상 False** — 브레이크가 조용히 풀린다.
감사 198이 잡은 것과 똑같은 모양이고, 그때는 안전장치 쪽을 고쳤지만
**돈을 들고 있는 쪽은 그대로였다.**

`base.safe_amount`·`base.normalize_side`가 이미 이 판정을 갖고 있었다.
실거래 브로커들만 쓰고 페이퍼는 안 쓰고 있었다 — 감사 192(방향)·199(잔고
필드)와 같은 '형제 찾기' 계열의 빠뜨림이다.

지키는 계약:
  · 수량·가격이 **양의 유한수**가 아니면 돈을 움직이지 않는다(예외)
  · 현금보다 큰 **매수**는 거부한다 — 이자 없는 신용거래를 하지 않는다
  · **매도는 막지 않는다** — 빠져나오는 길을 막으면 덫이 된다
  · 거부·미체결은 **체결로 기록되지 않는다**
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import PaperBroker  # noqa: E402


# ── 오염된 입력은 돈을 움직이지 못한다 ────────────────────────

BAD_QTY = [float("nan"), float("inf"), float("-inf"), -10.0, 0.0]
BAD_PX = [float("nan"), float("inf"), float("-inf"), -50.0, 0.0]


@pytest.mark.parametrize("qty", BAD_QTY)
def test_a_broken_quantity_never_moves_cash(qty):
    b = PaperBroker(cash=1000.0)
    with pytest.raises(ValueError):
        b.market_order("X", "buy", qty, 50.0)
    assert b.get_cash() == 1000.0
    assert b.get_position("X").quantity == 0.0
    assert b.order_log == [], "돈이 안 움직였는데 주문이 기록됐다"


@pytest.mark.parametrize("px", BAD_PX)
def test_a_broken_price_never_moves_cash(px):
    b = PaperBroker(cash=1000.0)
    with pytest.raises(ValueError):
        b.market_order("X", "buy", 10.0, px)
    assert b.get_cash() == 1000.0
    assert b.get_position("X").quantity == 0.0


def test_a_nan_never_reaches_the_ledger():
    """NaN 하나가 계좌 전체를 감염시키던 자리 — 킬스위치까지 죽는다."""
    b = PaperBroker(cash=1000.0)
    b.market_order("X", "buy", 10.0, 50.0)
    with pytest.raises(ValueError):
        b.market_order("X", "buy", float("nan"), 50.0)
    assert math.isfinite(b.get_cash())
    assert math.isfinite(b.equity({"X": 50.0}))
    assert math.isfinite(b.get_position("X").quantity)


def test_a_negative_price_does_not_pay_you_to_buy():
    """대조군이 아니라 사고 재현 — 음수 종가가 들어오면 자산이 늘었다."""
    b = PaperBroker(cash=1000.0)
    with pytest.raises(ValueError):
        b.market_order("X", "buy", 10.0, -50.0)
    assert b.get_cash() == 1000.0, "매수했는데 현금이 늘었다"


def test_a_negative_quantity_does_not_flip_the_side():
    """`buy -10`이 공매도가 되던 자리 — 방향(감사 192)과 같은 계열이다."""
    b = PaperBroker(cash=1000.0)
    with pytest.raises(ValueError):
        b.market_order("X", "buy", -10.0, 50.0)
    assert b.get_position("X").quantity == 0.0


# ── 현금 한도 ─────────────────────────────────────────────────

def test_you_cannot_buy_what_you_cannot_pay_for():
    """100만원 계좌가 500만원어치를 사던 자리."""
    b = PaperBroker(cash=1_000_000.0, fee=0.001)
    o = b.market_order("X", "buy", 100.0, 50_000.0)   # 500만원어치
    assert o.status == "rejected"
    assert o.filled_quantity == 0.0
    assert b.get_cash() == 1_000_000.0, "거부했는데 현금이 움직였다"
    assert b.get_position("X").quantity == 0.0
    assert b.rejected and b.rejected[0]["symbol"] == "X"


def test_an_affordable_buy_still_fills():
    """대조군 — 막는 것만 검사하면 '전부 막는' 코드도 통과한다."""
    b = PaperBroker(cash=1_000_000.0, fee=0.001)
    o = b.market_order("X", "buy", 10.0, 50_000.0)    # 50만원어치
    assert o.status == "filled"
    assert b.get_position("X").quantity == 10.0
    assert b.get_cash() == pytest.approx(1_000_000.0 - 500_000.0 * 1.001)
    assert b.rejected == []


def test_the_fee_is_inside_the_limit_not_outside():
    """수수료까지 낼 수 있어야 산다 — 현금이 -1원이 되는 것도 신용거래다."""
    b = PaperBroker(cash=100_000.0, fee=0.01)
    o = b.market_order("X", "buy", 1.0, 100_000.0)    # 원금은 딱 맞지만 수수료 1천원
    assert o.status == "rejected"
    assert b.get_cash() == 100_000.0


def test_spending_the_whole_account_is_allowed():
    """대조군 — 수수료까지 딱 맞으면 사야 한다(1원 차이로 못 사면 안 된다)."""
    b = PaperBroker(cash=101_000.0, fee=0.01)
    assert b.market_order("X", "buy", 1.0, 100_000.0).status == "filled"
    assert b.get_cash() == pytest.approx(0.0, abs=1e-6)


def test_selling_is_never_blocked_by_the_cash_limit():
    """빠져나오는 길은 **현금 한도**로 막지 않는다.

    ⚠️ 2026-08-16(감사 260) 이후 이 검사는 계좌를 `short_margin`으로 세운다.
       막는 주체가 둘로 갈렸기 때문이다 — **현금 한도**(이 파일의 주제)는
       예나 지금이나 매도를 막지 않고, **공매도 한도**(새 관문)가 보유를
       넘어서는 매도만 본다. 현금 0원이어도 담보 없이 숏이 열리던 것이
       바로 그 관문이 막는 것이고, 여기서 확인할 것은 아니다.
    """
    b = PaperBroker(cash=1_000.0, short_margin=0.5)
    o = b.market_order("S", "sell", 10.0, 50.0)
    assert o.status == "filled"
    assert b.get_cash() > 1_000.0            # 매도 대금이 들어왔다
    assert b.get_position("S").quantity == -10.0


def test_the_cash_limit_and_the_short_limit_are_different_guards():
    """대조군 — 현금이 없어서 막힌 것과 빌릴 수 없어서 막힌 것은 다르다.

    둘을 같은 이유로 적으면 "왜 안 팔렸나"에 장부가 틀린 답을 한다.
    """
    b = PaperBroker(cash=0.0)                       # 담보도 보유도 없다
    o = b.market_order("S", "sell", 10.0, 50.0)
    assert o.status == "rejected"
    assert b.rejected[-1].get("reason") == "공매도 한도"
    assert "need" not in b.rejected[-1], "현금 부족으로 잘못 적었다"


def test_liquidating_a_position_works_with_no_cash():
    """현금 0원이어도 보유를 팔 수 있어야 한다 — 덫을 만들지 않는다."""
    b = PaperBroker(cash=1000.0, fee=0.0)
    b.market_order("X", "buy", 20.0, 50.0)            # 현금 0
    assert b.get_cash() == pytest.approx(0.0)
    assert b.market_order("X", "sell", 20.0, 50.0).status == "filled"
    assert b.get_position("X").quantity == 0.0


def test_margin_can_be_turned_on_deliberately():
    """켜는 길은 남겨 둔다 — 다만 **기본값이 아니다**.

    안전 기본값의 반대는 '기능 삭제'가 아니다. 레버리지를 실험하려면
    명시적으로 켜면 되고, 그 사실이 코드에 남는다.
    """
    b = PaperBroker(cash=1000.0, allow_margin=True)
    assert b.market_order("X", "buy", 100.0, 50.0).status == "filled"
    assert b.get_cash() < 0


# ── 거부·미체결은 체결이 아니다 ────────────────────────────────

def test_a_rejected_limit_order_is_not_relabelled_as_filled():
    """지정가 경로가 거부를 '전량 체결'로 덮어쓰던 자리."""
    b = PaperBroker(cash=100.0, fee=0.0)
    o = b.limit_order("X", "buy", 100.0, 50.0, bar_high=60.0, bar_low=40.0)
    assert o.status == "rejected"
    assert o.filled_quantity == 0.0
    assert b.get_cash() == 100.0


def test_an_unfilled_limit_order_stays_open():
    """대조군 — 지정가에 안 닿으면 'open'이고, 돈은 그대로다."""
    b = PaperBroker(cash=100_000.0)
    o = b.limit_order("X", "buy", 1.0, 40.0, bar_high=60.0, bar_low=50.0)
    assert o.status == "open"
    assert b.get_cash() == 100_000.0


def test_a_partial_limit_fill_is_labelled_partial():
    """대조군 — 정상 부분체결은 그대로 동작해야 한다."""
    b = PaperBroker(cash=100_000.0, fee=0.0)
    o = b.limit_order("X", "buy", 10.0, 50.0, bar_high=60.0, bar_low=40.0,
                      fill_fraction=0.5)
    assert o.status == "partial"
    assert o.quantity == 10.0 and o.filled_quantity == 5.0
    assert b.get_position("X").quantity == 5.0


# ── 장부가 주문 로그를 그대로 베끼지 않는가 ────────────────────

def test_the_ledger_only_records_orders_that_moved_money():
    """`daily.py`가 주문 로그를 상태 확인 없이 체결 내역으로 쓰던 자리.

    돈이 한 푼도 안 움직인 주문이 "오늘 얼마에 샀다"로 장부에 남으면,
    그 줄은 사이트 거래내역·SNS 캡션·체결비용 표본으로 그대로 흘러간다.
    """
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "daily.py").read_text("utf-8")
    i = src.index('for o in getattr(broker, "order_log", [])')
    window = src[i:i + 800]
    assert '"filled", "partial"' in window, (
        "주문 로그를 체결 내역으로 옮기면서 상태를 안 본다 — "
        "미체결·거부가 '오늘 산 것'으로 기록된다")


def test_the_account_survives_a_full_cycle():
    """회계 항등식 — 한 사이클 뒤에도 자산이 손익만큼만 움직였는가.

    개별 가드가 다 맞아도 합쳐서 틀릴 수 있다. 값으로 확인한다.
    """
    b = PaperBroker(cash=1_000_000.0, fee=0.001)
    b.market_order("A", "buy", 5.0, 100_000.0)        # 50만원 + 500원
    b.market_order("A", "sell", 5.0, 110_000.0)       # 55만원 - 550원
    # 손익 = 5만원 - 수수료(500 + 550)
    assert b.get_cash() == pytest.approx(1_000_000.0 + 50_000.0 - 1_050.0)
    assert b.get_position("A").quantity == 0.0
    assert b.get_position("A").avg_price == 0.0
    assert b.equity({"A": 110_000.0}) == pytest.approx(b.get_cash())
