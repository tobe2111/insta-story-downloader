"""증거금 없는 무제한 공매도가 열려 있었다 (감사 260).

사장님 질문: *"숏도 레버리지도 다 열어줘."*

그 전에 **켤 수 있는 상태인지** 돌려서 확인했고, 셋 다 아니었습니다.

    ① 100만원 계좌에 목표 −500% → **−50,000주 체결 · 현금 599만원**
       (대주 가능 수량도, 증거금도 없다)
    ② 대차료(short_borrow)가 **전 시장 0.0** — 숏을 공짜로 무한정 들고 있다
    ③ 레버리지 관문은 이미 **잠김** — 파산확률 미측정(수익률 표본 3일)

①②를 그대로 두고 숏 전략을 오디션에 올리면 **실제로는 낼 수 없는 성과**로
챔피언이 뽑힙니다. 이 저장소가 반복해서 고쳐 온 '오디션-현실 격차'입니다.

그래서 켜는 것이 아니라 **켤 수 있게** 만듭니다:

    · 매도는 **보유 수량까지만** — 청산은 그대로 자유롭다(덫이 되면 안 된다)
    · 증거금 모델을 주면 그만큼만 열린다(`short_margin`)
    · 대차료를 시장별 보수적 하한으로 채운다 — 숏이 공짜가 아니게 된다

⚠️ 레버리지는 손대지 않았습니다. 관문(`risk/leverage_gate.py`)이 이미
   올바르게 잠그고 있고, 열리려면 **수익률 표본이 쌓여야** 합니다 —
   코드가 아니라 시간의 문제입니다. "모르면 잠긴다"가 그 파일의 원칙입니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest import CostModel  # noqa: E402
from quant.broker import PaperBroker  # noqa: E402


# ── ① 없는 주식을 팔 수 있는가 ───────────────────────────────

def test_a_naked_short_is_refused():
    """실측 그 장면 — 100만원 계좌가 5,000만원어치를 공매도했다."""
    b = PaperBroker(cash=1_000_000)
    b.target_weight("SPY", -5.0, price=100.0, equity=1_000_000)
    assert b.get_position("SPY").quantity == 0.0, "증거금 없이 숏이 열렸다"
    assert any(r.get("reason") == "공매도 한도" for r in b.rejected), (
        "거부했으면서 이유를 안 남겼다 — 조용히 덜 파는 것과 구별이 안 된다")


def test_selling_what_you_hold_is_never_blocked():
    """⚠️ 대조군 — 빠져나오는 길을 막으면 리스크 관리가 아니라 덫이다."""
    b = PaperBroker(cash=1_000_000)
    b.market_order("SPY", "buy", 100, 100.0)
    b.market_order("SPY", "sell", 100, 100.0)
    assert b.get_position("SPY").quantity == 0.0
    assert b.rejected == [], f"청산을 막았다: {b.rejected}"


def test_a_partial_sell_is_clipped_not_dropped():
    """보유 100주인데 150주 매도 → 100주는 팔려야 한다.

    통째로 거부하면 청산이 막히고, 통째로 체결하면 숏이 열린다.
    """
    b = PaperBroker(cash=1_000_000)
    b.market_order("SPY", "buy", 100, 100.0)
    b.market_order("SPY", "sell", 150, 100.0)
    assert b.get_position("SPY").quantity == 0.0, "보유분이 안 팔렸다"
    assert b.rejected and b.rejected[-1]["short_over"] == pytest.approx(50.0)


def test_margin_opens_exactly_as_much_as_it_should():
    """증거금 50%·현금 100만·가격 100 → 20,000주까지."""
    b = PaperBroker(cash=1_000_000, short_margin=0.5)
    b.target_weight("SPY", -5.0, price=100.0, equity=1_000_000)
    assert b.get_position("SPY").quantity == pytest.approx(-20_000.0)


def test_no_margin_means_no_short_at_all():
    """대조군 — 기본값이 '조금 허용'이면 그건 금지가 아니다."""
    b = PaperBroker(cash=1_000_000)
    assert b.short_margin == 0.0
    b.target_weight("SPY", -0.01, price=100.0, equity=1_000_000)
    assert b.get_position("SPY").quantity == 0.0


def test_a_short_is_still_marked_correctly():
    """숏이 열리는 경우, 자산 평가는 정확해야 한다(가격↑ = 손실)."""
    b = PaperBroker(cash=1_000_000, short_margin=0.5)
    b.market_order("SPY", "sell", 5_000, 100.0)
    lo, hi = b.equity({"SPY": 100.0}), b.equity({"SPY": 110.0})
    assert hi < lo, "가격이 올랐는데 숏이 이득으로 잡힌다"
    assert (lo - hi) == pytest.approx(50_000.0, rel=1e-6)


# ── ② 숏이 공짜가 아닌가 ─────────────────────────────────────

@pytest.mark.parametrize("market", ["us_stock", "kr_stock", "crypto"])
def test_holding_a_short_costs_something(market):
    """대차료 0이면 오디션이 '공짜로 무한정 들고 있는' 전략을 뽑는다."""
    assert CostModel.for_market(market).short_borrow > 0.0


def test_the_korean_borrow_is_dearer_than_the_american():
    """개인 대주는 미국 대형주 대차보다 비싸다 — 순서가 뒤집히면 가정이 틀렸다."""
    kr = CostModel.for_market("kr_stock").short_borrow
    us = CostModel.for_market("us_stock").short_borrow
    assert kr > us, f"한국({kr}) ≤ 미국({us})"


def test_the_synthetic_market_stays_free():
    """검증용 합성 시장까지 비용을 얹으면 기존 검사들의 기준이 흔들린다."""
    assert CostModel.for_market("synthetic").short_borrow == 0.0


# ── ③ 레버리지는 잠겨 있는가 ────────────────────────────────

def test_leverage_is_locked_until_ruin_is_measurable():
    """'모르면 잠긴다' — 표본이 모자라면 안전이 아니라 모름이다."""
    from quant.risk.leverage_gate import decide

    d = decide(returns=None, daily_vol=0.01, market="us_stock",
               state_dir="state", requested=3.0)
    assert d.locked, f"표본도 없이 레버리지가 열렸다: {d.allowed}"
    assert "파산확률" in d.describe()


def test_the_hard_cap_is_never_exceeded():
    """계산이 아무리 관대해도 절대 상한이 있어야 한다."""
    from quant.risk.leverage_gate import HARD_CAP, decide

    d = decide(returns=None, daily_vol=1e-9, market="us_stock",
               state_dir="state", requested=999.0)
    assert d.allowed <= HARD_CAP
