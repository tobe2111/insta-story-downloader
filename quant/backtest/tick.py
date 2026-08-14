"""호가 단위(틱) — **이보다 싸게 체결될 수는 없다**.

⚠️ 왜 필요한가(2026-08-14). 비용 모델은 모든 시장에 슬리피지 **0.05%(5bp)**
를 고정으로 물리고 있었다. 그런데 국내주식은 가격대마다 호가 단위가 정해져
있고, 사자·팔자 호가는 **최소 한 칸** 벌어져 있다. 즉 한 번 건너뛰는 데
드는 비용의 하한이 물리적으로 정해져 있다.

이 저장소 운영 종목의 실제 가격으로 계산한 결과:

    종목            가격        호가단위   스프레드 하한   편도(반)   가정 5bp 대비
    삼성전자        236,000원     500원      21.2bp       10.6bp      2.1배
    LG화학          275,500원     500원      18.1bp        9.1bp      1.8배
    KODEX 200        97,570원       5원(ETF)  0.5bp        0.3bp      0.1배
    KB금융          168,100원     100원       5.9bp        3.0bp      0.6배
    SK하이닉스    1,443,000원   1,000원       6.9bp        3.5bp      0.7배

삼성전자·LG화학에서 **가정이 물리적으로 불가능한 값**이다. 아무리 잘 체결해도
낼 수 없는 비용으로 백테스트를 돌리면 고회전 전략이 부당하게 유리해지고,
그 전략이 오디션을 이겨 챔피언이 된다. 이 저장소가 감사 180·184에서 계속
좁혀 온 '오디션-현실 격차'의 남은 한 조각이다.

여기서 하는 일은 **추정이 아니라 하한**이다. 실제 스프레드는 이보다 넓을 수
있고(유동성이 얕은 종목·장 초반), 좁을 수는 없다. 그래서 가정을 대체하지 않고
**바닥으로만** 쓴다 — 가정이 하한보다 크면 가정을 그대로 둔다.

출처: KRX 호가가격단위(2023-01 개정). ETF·ETN은 전 가격대 5원으로 별도다 —
표를 그대로 적용하면 KODEX 200에 20배를 물리게 되므로 구분해야 한다.
"""
from __future__ import annotations

import math

# KRX 주식 호가가격단위 (2023-01-30 개정). (미만 가격, 단위)
KRX_STOCK_TICKS: tuple[tuple[float, float], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
    (math.inf, 1_000),
)
KRX_ETF_TICK = 5.0        # ETF·ETN은 전 가격대 5원
US_TICK = 0.01            # 미국주식 최소 호가($0.01). 서브페니는 다루지 않는다


def krx_tick(price: float, etf: bool = False) -> float:
    """그 가격대의 KRX 호가 단위(원)."""
    if etf:
        return KRX_ETF_TICK
    for hi, unit in KRX_STOCK_TICKS:
        if price < hi:
            return float(unit)
    return float(KRX_STOCK_TICKS[-1][1])


def tick_size(market: str, price: float, etf: bool = False) -> float | None:
    """그 시장·가격의 호가 단위. 모르는 시장이면 None(하한 없음).

    코인은 거래소·페어마다 달라 여기서 단정하지 않는다 — 모르면 하한을
    만들지 않는다. 이 모듈의 값은 '확실히 이보다 싸지 않다'여야 하므로,
    모르는 것을 추측해 넣으면 그 성질이 깨진다.
    """
    if not isinstance(price, (int, float)) or not math.isfinite(price) \
            or price <= 0:
        return None
    m = (market or "").lower()
    if m == "kr_stock":
        return krx_tick(float(price), etf)
    if m == "us_stock":
        return US_TICK
    return None


def spread_floor(market: str, price: float, etf: bool = False) -> float:
    """**편도** 슬리피지의 하한 = 호가 한 칸의 절반 ÷ 가격.

    한 칸을 건너뛰는 데 드는 비용이 스프레드이고, 사고팔아 왕복하면 그
    스프레드를 한 번 문다. 편도 기준으로는 절반이다.

    모르는 시장·이상한 가격이면 0 — **하한이 없다는 뜻이지 비용이 0이라는
    뜻이 아니다.** 위 `tick_size`가 None을 주는 경우와 같은 규약이다.
    """
    t = tick_size(market, price, etf)
    if t is None:
        return 0.0
    return (t / 2.0) / float(price)
