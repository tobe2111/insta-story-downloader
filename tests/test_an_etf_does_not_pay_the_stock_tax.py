"""한국 ETF는 증권거래세를 안 낸다 — 그런데 우리는 물리고 있었다.

2026-09-03, 사장님 승인으로 "놀고 있는 현금"에 넣을 파킹 상품을 재던 중
발견했다. 증권거래세는 **주권 양도**에 붙는 세금이고 ETF는 수익증권이라
매도 시 비과세인데, 비용 표가 **시장만 보고** 세금을 물리고 있었다.

    운용 중인 한국 12종목 중 **6종목이 ETF**다
    (KODEX 200 · 나스닥100 · 금 · 국고채10년 · 화장품 · 종합채권).
    이들이 내지 않는 세금을 왕복 15bp씩 내고 있었다.
    실측: 지금까지 체결 3건 · 금액 417,440원 → 더 낸 돈 313원(자산의 0.031%).

■ 금액이 작은데 왜 고치는가

이 값은 **세 곳으로 흘러간다.** 금액은 오늘 작지만 경로가 넓다:

  ① 페이퍼 브로커의 실제 체결 수수료 → 장부 손익이 실제와 달라진다.
  ② **리밸런스 밴드가 비용에 비례한다** → 비싸게 잡으면 밴드가 넓어져
     기계가 고쳐 잡아야 할 자리를 안 고친다.
  ③ 오디션이 고회전 한국 후보를 부당하게 떨어뜨린다.

방향이 '보수적'이라 늦게 잡혔다. 그런데 **보수적인 것과 옳은 것은 다르다** —
이 저장소가 반복해서 잡아 온 병(선언과 실제의 불일치)의 다른 얼굴이다.

■ 여기서 지키는 약속

  ① ETF는 거래세를 안 낸다. 주식은 낸다. 둘이 같은 값이면 검사가 죽는다.
  ② **시장은 그대로 남는다** — 호가 단위(틱) 하한이 시장을 보고 계산되므로,
     ETF 프리셋으로 갈아타면서 market을 잃으면 다른 안전장치가 조용히 꺼진다.
  ③ 종목을 모르면 **주식으로 본다**(비싼 쪽 = 보수적). 새 ETF를 넣고 표시를
     빠뜨려도 조용히 싸지지 않는다.
  ④ 미국·코인은 이 변경에 영향받지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.costs import CostModel  # noqa: E402
from quant.live.daily import (  # noqa: E402
    _fill_cost, cost_basis_bp, is_etf, measured_cost_model,
    rebalance_band_basis,
)

# 증권거래세(매도 0.15%)를 편도로 나눈 값 — 이 표가 ETF에 물리던 몫이다.
TAX_ONE_WAY = 0.00075


# ── ① ETF는 세금을 안 낸다 ────────────────────────────────────────────
def test_a_korean_etf_is_cheaper_than_a_korean_stock():
    etf = CostModel.for_market("kr_stock", is_etf=True)
    stock = CostModel.for_market("kr_stock", is_etf=False)
    assert etf.total_one_way() < stock.total_one_way(), (
        "ETF와 주식 비용이 같다 — 거래세 면제가 반영되지 않았다")
    gap = stock.total_one_way() - etf.total_one_way()
    assert gap == pytest.approx(TAX_ONE_WAY), (
        f"차이가 거래세({TAX_ONE_WAY})가 아니라 {gap} — 다른 것이 같이 바뀌었다")


def test_the_etf_still_pays_the_brokerage_fee():
    """면제되는 것은 **세금**이지 수수료가 아니다 — 0으로 만들면 안 된다."""
    etf = CostModel.for_market("kr_stock", is_etf=True)
    assert etf.fee > 0 and etf.slippage > 0, etf


# ── ② 시장을 잃으면 다른 안전장치가 꺼진다 ───────────────────────────
def test_switching_to_the_etf_preset_keeps_the_market():
    """호가 단위 하한은 **시장**을 보고 계산된다.

    프리셋 열쇠를 'kr_stock_etf'로 갈아타면서 market까지 그 이름이 되면,
    틱 표를 못 찾아 하한이 조용히 0이 된다 — 낼 수 없는 비용으로 백테스트가
    돌고, 고회전 전략이 부당하게 유리해진다(감사 2026-08-14와 같은 병).
    """
    etf = CostModel.for_market("kr_stock", is_etf=True)
    assert etf.market == "kr_stock", etf.market
    assert etf.is_etf is True
    # 하한이 실제로 살아 있는가 — KODEX 200 가격대에서 0이 아니어야 한다.
    assert etf.slippage_floor(97570.0) > 0, "틱 하한이 죽었다"


def test_the_short_borrow_survives_the_switch():
    a = CostModel.for_market("kr_stock", is_etf=False).short_borrow
    b = CostModel.for_market("kr_stock", is_etf=True).short_borrow
    assert b == a > 0, (a, b)


# ── ③ 모르면 비싼 쪽(주식)으로 본다 ──────────────────────────────────
def test_an_unmarked_symbol_is_treated_as_a_stock():
    """새 ETF를 넣고 표시를 빠뜨려도 **조용히 싸지지 않는다.**"""
    assert is_etf("kr_stock", None) is False
    assert is_etf("kr_stock", "999999.KS") is False
    assert _fill_cost("kr_stock") == _fill_cost("kr_stock", "005930.KS")


@pytest.mark.parametrize("market", ["us_stock", "crypto"])
def test_other_markets_are_untouched(market):
    assert (CostModel.for_market(market, is_etf=True).total_one_way()
            == CostModel.for_market(market, is_etf=False).total_one_way()), (
        f"{market}에는 한국 거래세가 없는데 값이 갈렸다")


# ── ④ 실제로 운용 중인 ETF가 싼값을 받는가 (행동 검사) ───────────────
_KR_ETFS = ["069500.KS", "133690.KS", "132030.KS",
            "148070.KS", "228790.KS", "273130.KS"]


@pytest.mark.parametrize("symbol", _KR_ETFS)
def test_a_live_korean_etf_actually_gets_the_exemption(symbol):
    """표가 아니라 **운용 종목**으로 확인한다 — 분류가 빠지면 여기서 죽는다."""
    assert is_etf("kr_stock", symbol) is True, f"{symbol}이 ETF로 분류돼 있지 않다"
    assert _fill_cost("kr_stock", symbol) < _fill_cost("kr_stock", "005930.KS")


def test_the_audition_charges_the_same_corrected_cost():
    """오디션도 같은 값을 물어야 한다 — 갈리면 링과 계좌가 다른 세계가 된다."""
    a = measured_cost_model("kr_stock", "state", symbol="069500.KS")
    b = measured_cost_model("kr_stock", "state", symbol="005930.KS")
    assert a.total_one_way() < b.total_one_way(), (a.fee, b.fee)


# ── ⑤ 밴드도 같은 값을 읽는다 ────────────────────────────────────────
def test_the_band_reads_the_symbol_not_just_the_market():
    """밴드는 **비용에 비례**한다 — 종목을 안 보면 교정이 여기서 끊긴다.

    ⚠️ 실측 표본이 문턱을 넘으면 실측이 이기고, 그때는 ETF와 주식이 한
       표본에 섞여 구분이 사라진다. 그건 결함이 아니라 표본의 성질이므로
       (실측은 실측이다) 여기서는 **종목이 전달되는지**를 못 박는다.
    """
    basis = rebalance_band_basis("kr_stock", "state", "069500.KS")
    assert basis["symbol"] == "069500.KS", basis
    import inspect

    from quant.live import daily as D
    src = inspect.getsource(D._champion_band_rel)
    assert "_rebalance_band_rel(market, state_dir, _s)" in src, (
        "체결기가 밴드를 물을 때 종목을 안 넘긴다 — 교정이 여기서 끊긴다")


# ── ⑥ 공개 자료가 두 값을 함께 말한다 ───────────────────────────────
def test_the_published_cost_basis_says_both():
    """한 숫자로 적으면 둘 중 하나는 반드시 거짓말이 된다."""
    cb = cost_basis_bp("state")
    assert cb["kr_stock_etf"] is not None and cb["kr_stock"] is not None
    assert cb["kr_stock_etf"] < cb["kr_stock"], cb


# ── ⑦ 체결기가 실제로 종목별 값을 쓴다 (배선 검사) ──────────────────
def test_every_fill_path_passes_the_symbol():
    """비용 교정이 표에만 있고 체결에 안 닿으면 장부는 그대로 틀린다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    for call in ('fee=_fill_cost(market, symbol))',
                 'broker.fee = _fill_cost(*key.split(":", 1))'):
        assert call in src, f"체결 경로가 종목을 안 넘긴다: {call}"
    # 시장만 넘기는 옛 호출이 남아 있으면 그 자리만 조용히 옛값을 쓴다.
    assert '_fill_cost(key.split(":")[0])' not in src
    assert '_fill_cost(k.split(":")[0])' not in src
