"""주문 방향 판정이 브로커마다 흩어져 있었다 (감사 192).

감사 182에서 국내 실거래 브로커 둘(키움·KIS)에 이 검사를 넣었다.

    api_id = TR_BUY if side == "buy" else TR_SELL     # ← 모르는 방향 = 매도

정확히 `"buy"`가 아닌 **무엇이든** 조용히 매도가 된다. 그때 두 곳을 고치고
끝냈는데, **같은 모양이 두 곳 더 있었다.**

    quant/broker/paper.py   signed = quantity if side == "buy" else -quantity
    quant/broker/retry.py   signed = delta    if side == "buy" else -delta

`paper.py`는 **8마일 챌린지의 모든 기록이 나오는 브로커**다. 여기서 방향이
뒤집히면 장부·사이트·방송이 전부 그 위에 쌓인다. `retry.py`는 체결 확인이
증감 방향을 그 분기로 정하므로, 확인 로직까지 반대로 돈다.

파일마다 복사해 넣으면 다음에 또 한 곳을 빠뜨린다. 판정을
`quant/broker/base.normalize_side()` 하나로 모으고 **여섯 브로커가 전부
그걸 부르게** 했다(㉞ '같은 판정을 두 곳에서 쓰면 언젠가 갈라진다').

대소문자·공백은 받아 준다 — 기본값이 파괴적인 쪽이면 안 될 뿐이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.base import normalize_side  # noqa: E402
from quant.broker.paper import PaperBroker  # noqa: E402

BAD = ["long", "매수", "", "sel", "b", "SELL_ALL", "Buy!", None, 1]


# ── 공용 판정 ─────────────────────────────────────────────────


@pytest.mark.parametrize("bad", BAD)
def test_an_unknown_direction_is_refused(bad):
    with pytest.raises(ValueError, match="주문 방향"):
        normalize_side(bad)


@pytest.mark.parametrize("given,want", [
    ("buy", "buy"), ("sell", "sell"), ("BUY", "buy"), ("Sell", "sell"),
    (" buy ", "buy"), ("SELL", "sell"),
])
def test_the_two_real_directions_pass_through(given, want):
    """대조군 — 전부 거절하면 아무 주문도 못 낸다."""
    assert normalize_side(given) == want


# ── 페이퍼 브로커: 모든 기록이 나오는 자리 ────────────────────


@pytest.mark.parametrize("bad", ["long", "매수", "", "sel"])
def test_the_paper_broker_never_turns_an_unknown_side_into_a_sell(bad):
    b = PaperBroker(cash=10_000.0, fee=0.0)
    with pytest.raises(ValueError, match="주문 방향"):
        b.market_order("X", bad, 10, 100.0)
    assert b.get_position("X").quantity == 0.0, "거절해야 할 주문이 체결됐다"
    assert b.get_cash() == 10_000.0, "거절했는데 현금이 움직였다"
    assert b.order_log == [], "거절한 주문이 장부에 남았다"


def test_upper_case_buy_is_a_buy_not_a_sell():
    """예전에는 'BUY'가 **매도**로 나갔다 — 사는 줄 알고 팔린다."""
    b = PaperBroker(cash=10_000.0, fee=0.0)
    b.market_order("X", "BUY", 10, 100.0)
    assert b.get_position("X").quantity == 10.0
    assert b.get_cash() == 9_000.0


def test_a_normal_buy_and_sell_still_settle_correctly():
    """대조군 — 정규화를 넣느라 회계가 틀어지면 안 된다."""
    b = PaperBroker(cash=10_000.0, fee=0.0)
    b.market_order("X", "buy", 10, 100.0)
    b.market_order("X", "sell", 4, 110.0)
    pos = b.get_position("X")
    assert pos.quantity == 6.0
    assert pos.avg_price == 100.0, "부분 청산인데 평단이 바뀌었다"
    assert b.get_cash() == pytest.approx(9_000.0 + 440.0)


def test_a_limit_order_checks_the_side_before_deciding_it_crossed():
    """지정가는 방향에 따라 체결 조건이 정반대다 — 뒤집히면 안 닿아도 체결된다."""
    b = PaperBroker(cash=10_000.0, fee=0.0)
    with pytest.raises(ValueError, match="주문 방향"):
        b.limit_order("X", "long", 10, 100.0, bar_high=120.0, bar_low=110.0)

    # 대조군: 매수 지정가 100인데 저가가 110 → 안 닿았으므로 미체결
    o = b.limit_order("X", "buy", 10, 100.0, bar_high=120.0, bar_low=110.0)
    assert o.status == "open" and o.filled_quantity == 0.0
    # 저가가 지정가를 지나면 체결
    o2 = b.limit_order("X", "BUY", 10, 100.0, bar_high=120.0, bar_low=95.0)
    assert o2.status == "filled" and o2.filled_quantity == 10.0


def test_an_upper_case_buy_does_not_borrow_the_sell_crossing_rule():
    """⚠️ 이 봉이 핵심이다 — 매수로는 **안 닿았고** 매도로는 닿는다.

    저가 110 > 지정가 100 이므로 매수는 미체결이어야 한다. 그런데 방향을
    정규화하지 않으면 `"BUY" == "buy"`가 거짓이라 **매도 규칙**(고가 ≥ 지정가)
    으로 판정하고, 고가 120 ≥ 100 이라 **닿지도 않은 지정가가 체결된다.**

    소문자로만 검사하면 이 차이가 안 드러난다(감사 192에서 변이를 놓쳤다) —
    회계는 `market_order`가 다시 정규화해 맞춰 주기 때문에 겉으로는 멀쩡하다.
    갈라지는 것은 **체결 여부** 하나뿐이다.
    """
    b = PaperBroker(cash=10_000.0, fee=0.0)
    o = b.limit_order("X", "BUY", 10, 100.0, bar_high=120.0, bar_low=110.0)
    assert o.status == "open" and o.filled_quantity == 0.0, (
        f"저가 110 > 지정가 100인데 매수가 체결됐다 — 매도 규칙으로 판정했다: {o}")
    assert b.get_position("X").quantity == 0.0


# ── 흩어지지 않았는가 (드리프트 가드) ─────────────────────────


def test_every_broker_routes_its_side_through_the_one_judgement():
    """새 브로커가 자기 방식으로 방향을 읽으면 조용히 무방비가 된다."""
    import re

    bro = ROOT / "quant" / "broker"
    offenders = []
    for fp in sorted(bro.glob("*.py")):
        if fp.name in ("base.py", "specs.py", "__init__.py"):
            continue
        code = "\n".join(ln for ln in fp.read_text("utf-8").splitlines()
                         if not ln.lstrip().startswith("#"))
        if not re.search(r'side\s*==\s*"buy"', code):
            continue                      # 방향으로 갈라지지 않는 파일
        if "normalize_side(side)" not in code:
            offenders.append(fp.name)
    assert not offenders, (
        f"방향으로 갈라지면서 공용 판정을 안 지나는 브로커: {offenders}\n"
        "  → quant.broker.base.normalize_side()를 부를 것")
