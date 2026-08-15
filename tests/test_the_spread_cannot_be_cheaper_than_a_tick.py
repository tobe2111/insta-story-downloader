"""가정한 슬리피지가 **물리적으로 불가능한 값**이었다 (2026-08-14).

비용 모델은 모든 시장에 슬리피지 0.05%(5bp)를 고정으로 물리고 있었다.
그런데 국내주식은 가격대마다 호가 단위가 정해져 있고, 사자·팔자 호가는
최소 **한 칸** 벌어져 있다 — 한 번 건너뛰는 비용의 하한이 정해져 있다는 뜻이다.

이 저장소 운영 종목의 **실제 체결 가격**(state/paper 장부에서 꺼낸 값)으로
계산한 결과:

    종목            가격         호가단위    스프레드 하한   편도(반)   가정 대비
    삼성전자        236,000원      500원       21.2bp       10.6bp     2.1배
    LG화학          275,500원      500원       18.1bp        9.1bp     1.8배
    KB금융          168,100원      100원        5.9bp        3.0bp     0.6배
    SK하이닉스    1,443,000원    1,000원        6.9bp        3.5bp     0.7배
    KODEX 200        97,570원        5원(ETF)   0.5bp        0.3bp     0.1배

삼성전자·LG화학에서는 **아무리 잘 체결해도 낼 수 없는 비용**으로 백테스트를
돌리고 있었다. 그러면 고회전 전략이 부당하게 유리해지고, 그 전략이 오디션을
이겨 챔피언이 된다 — 감사 180·184가 계속 좁혀 온 '오디션-현실 격차'의 남은
한 조각이다.

여기서 하는 일은 **추정이 아니라 하한**이다. 실제 스프레드는 이보다 넓을 수
있어도 좁을 수는 없다. 그래서 가정을 대체하지 않고 **바닥으로만** 쓴다.

⚠️ ETF는 호가 단위가 다르다(KRX ETF·ETN은 전 가격대 5원). 주식 표를 그대로
   적용하면 KODEX 200에 20배를 물린다 — 구분하지 않으면 고치려던 방향의
   반대편으로 같은 크기의 오류를 만든다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest.costs import CostModel  # noqa: E402
from quant.backtest.tick import krx_tick, spread_floor, tick_size  # noqa: E402
from quant.live.daily import is_etf  # noqa: E402
from quant.markets import AUTO_TARGETS, SYMBOL_INFO  # noqa: E402


# ── 호가 단위 표 (KRX 2023-01 개정) ───────────────────────────

@pytest.mark.parametrize("price,unit", [
    (1_500, 1), (1_999, 1),
    (2_000, 5), (4_999, 5),
    (5_000, 10), (19_999, 10),
    (20_000, 50), (49_999, 50),
    (50_000, 100), (199_999, 100),
    (200_000, 500), (499_999, 500),
    (500_000, 1_000), (1_443_000, 1_000),
])
def test_the_krx_tick_table_is_what_krx_says(price, unit):
    assert krx_tick(price) == unit


def test_an_etf_has_its_own_tick():
    """ETF·ETN은 전 가격대 5원 — 주식 표를 쓰면 20배를 물린다."""
    assert krx_tick(97_570, etf=True) == 5
    assert krx_tick(97_570, etf=False) == 100      # 대조군


# ── 하한이 실제 종목에서 얼마인가 ─────────────────────────────

REAL = [   # 장부에 실제로 남은 체결·호가 가격
    ("kr_stock", "005930.KS", 236_000, 10.6),   # 삼성전자
    ("kr_stock", "051910.KS", 275_500, 9.1),    # LG화학
    ("kr_stock", "105560.KS", 168_100, 3.0),    # KB금융
    ("kr_stock", "000660.KS", 1_443_000, 3.5),  # SK하이닉스
]


@pytest.mark.parametrize("market,symbol,price,bp", REAL)
def test_the_floor_matches_the_hand_calculation(market, symbol, price, bp):
    """손으로 계산한 값과 같은가 — 숫자를 문서와 코드 양쪽에 못박는다."""
    got = spread_floor(market, price, is_etf(market, symbol)) * 1e4
    assert got == pytest.approx(bp, abs=0.05)


def test_the_assumption_was_impossible_for_the_big_two():
    """가정 5bp가 삼성전자·LG화학에서 하한 아래였다 — 그것이 이 작업의 이유다."""
    for market, symbol, price, _ in REAL[:2]:
        cm = CostModel.for_market(market, is_etf=is_etf(market, symbol))
        assert cm.slippage < cm.slippage_floor(price), (
            f"{symbol}: 가정이 하한보다 크다 — 이 검사의 전제가 사라졌다")


def test_the_floor_actually_raises_the_cost():
    """하한이 계산에 **닿는가** — 함수만 맞고 아무도 안 부르면 소용없다."""
    cm = CostModel.for_market("kr_stock")
    with_price = cm.turnover_cost(1.0, price=236_000)
    without = cm.turnover_cost(1.0)
    assert with_price > without
    assert with_price == pytest.approx(cm.fee + spread_floor("kr_stock", 236_000))


# ── 넘치지 않는가 (대조군) ────────────────────────────────────

def test_a_cheap_tick_does_not_lower_the_assumption():
    """하한이지 대체가 아니다 — 가정보다 싸면 가정을 그대로 둔다."""
    cm = CostModel.for_market("kr_stock")
    assert cm.turnover_cost(1.0, price=168_100) == pytest.approx(
        cm.fee + cm.slippage), "하한이 가정을 끌어내렸다"


def test_an_etf_is_not_charged_the_stock_tick():
    """KODEX 200에 주식 표를 물리면 20배다."""
    etf = CostModel.for_market("kr_stock", is_etf=True)
    stock = CostModel.for_market("kr_stock", is_etf=False)
    assert etf.slippage_floor(97_570) < stock.slippage_floor(97_570) / 10
    # ETF는 하한이 가정보다 훨씬 작으므로 비용이 안 변한다(대조군)
    assert etf.turnover_cost(1.0, price=97_570) == pytest.approx(
        etf.fee + etf.slippage)


@pytest.mark.parametrize("market,price", [
    ("crypto", 63_527.0),      # 거래소·페어마다 달라 단정하지 않는다
    ("synthetic", 100.0),
    ("", 100.0),
])
def test_an_unknown_market_gets_no_floor(market, price):
    """모르는 것을 추측해 넣으면 '확실히 이보다 싸지 않다'가 깨진다."""
    assert spread_floor(market, price) == 0.0
    assert tick_size(market, price) is None


@pytest.mark.parametrize("price", [0, -100, float("nan"), float("inf"), None])
def test_a_broken_price_gets_no_floor(price):
    assert spread_floor("kr_stock", price) == 0.0


def test_no_price_means_no_change():
    """가격을 안 주면 예전과 **비트 단위로** 같아야 한다."""
    cm = CostModel.for_market("kr_stock")
    assert cm.turnover_cost(0.3, vol=0.02) == (
        cm.fee + cm.slippage + cm.impact_coef * 0.02) * 0.3


def test_a_model_without_a_market_has_no_floor():
    """직접 만든 CostModel(시장 미지정)은 예전 그대로 — 하위 호환."""
    cm = CostModel(fee=0.001, slippage=0.0005)
    assert cm.slippage_floor(236_000) == 0.0


# ── 배선 ──────────────────────────────────────────────────────

def test_the_engine_passes_the_price_in():
    """엔진이 가격을 안 넘기면 하한은 영영 안 걸린다(감사 229의 교훈)."""
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "backtest" / "engine.py").read_text("utf-8")
    assert src.count("turnover_cost(") == 2, "비용 계산 자리가 늘었다 — 확인 필요"
    assert "price=price" in src and "price=fill" in src


def test_the_measured_model_keeps_the_market_and_the_etf_flag():
    """실측 비용으로 갈아탈 때 시장·ETF 표시를 흘리면 하한이 조용히 사라진다."""
    from quant.live.daily import measured_cost_model
    cm = measured_cost_model("kr_stock", state_dir="/tmp", models_gap=True,
                             symbol="069500.KS")
    assert cm.market == "kr_stock" and cm.is_etf is True
    cm2 = measured_cost_model("kr_stock", state_dir="/tmp", models_gap=True,
                              symbol="005930.KS")
    assert cm2.market == "kr_stock" and cm2.is_etf is False


def test_the_rebuilt_model_after_a_measurement_keeps_the_floor(monkeypatch):
    """**실측이 가정을 넘어 새 객체를 만드는 경로**에서도 하한이 살아 있는가.

    위 검사는 `models_gap=True`(지금 운영 경로)라 이 분기에 닿지 않는다.
    닿지 않는 코드는 아무리 맞아 보여도 확인된 것이 아니다 — 값이 옮겨지는
    자리는 늘 하나씩 흘린다.
    """
    import quant.live.daily as dl

    monkeypatch.setattr(dl, "_measured_roundtrip_cost",
                        lambda market, state_dir: 0.02)   # 왕복 200bp(가정보다 큼)
    cm = dl.measured_cost_model("kr_stock", state_dir="/tmp",
                                models_gap=False, symbol="005930.KS")
    assert cm.slippage > CostModel.for_market("kr_stock").slippage, (
        "실측이 반영되지 않았다 — 이 검사의 전제가 사라졌다")
    assert cm.market == "kr_stock", "새 객체가 시장을 잃었다 — 하한이 사라진다"
    assert cm.slippage_floor(236_000) > 0


def test_every_traded_korean_symbol_is_classified():
    """운영 종목이 전부 ETF/주식으로 분류돼 있는가.

    빠뜨리면 그 종목만 조용히 20배 비싸진다. **아는 것만 세지 않고** 실제
    운영 목록(AUTO_TARGETS)에서 훑는다.
    """
    for market, symbol in AUTO_TARGETS:
        if market != "kr_stock":
            continue
        info = SYMBOL_INFO.get(f"{market}:{symbol}")
        assert info is not None, f"{symbol}: 종목 정보가 없다"
        name = info.get("name", "")
        looks_etf = any(t in name for t in ("KODEX", "TIGER", "ETF", "ETN"))
        assert bool(info.get("etf")) == looks_etf, (
            f"{symbol}({name}): ETF 표시가 이름과 어긋난다 — "
            "표시를 빠뜨리면 호가 단위를 20배로 물린다")
