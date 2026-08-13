"""원/달러 환산 — **계좌의 단위를 하나로** (감사 212).

무엇이 문제였나 (2026-08-13, 잔고 표를 만들다 드러남):

통합 계좌의 자산은 `현금 + Σ(수량 × 가격)`으로 계산되는데, 그 '가격'이
시장마다 **다른 통화**였다:

    삼성전자   239,500   ← 진짜 원화
    S&P500 ETF    772   ← 달러인데 원화처럼 더해졌다
    비트코인   63,576   ← USDT인데 원화처럼 더해졌다

그래서 "S&P500 ETF 12.25주 = 9,466원"이라는 줄이 장부에 남았다. 실제로
그 12주는 1,300만원어치다. 수익률은 **내부적으로는** 일관돼서(모든 계산이
같은 왜곡을 겪으므로) 지금까지 드러나지 않았지만, 두 가지가 사실이 아니다:

  ① **자산 79,251'원'은 진짜 원화 금액이 아니다.** 단위가 섞인 합계다.
  ② **환위험이 통째로 빠져 있다.** 원화 투자자가 미국 주식을 들면 원/달러가
     움직이는 만큼 손익이 난다. 이 장부에는 그 손익이 존재하지 않았다.
     원화가 10% 절상되면 실제로는 10%를 잃는데 화면은 아무 말도 안 한다.

여기서 고치는 방식: **체결·평가 가격만** 원화로 환산한다. 신호는 현지
통화 시계열 그대로 낸다(전략 동작을 바꾸지 않는다). 그러면 환율 변동이
매일의 재평가를 통해 자산에 그대로 흘러들어 — 즉 환위험이 장부에 잡힌다.

⚠️ **실패했을 때 1.0을 쓰면 안 된다.** 그것이 바로 지금 고치는 상태다.
환율을 모르면 모른다고 말하고 그날 판단을 멈추는 것이 맞다. 조용한
폴백은 이 저장소에서 반복해서 사고를 냈다(감사 102·152·198·205).
"""

from __future__ import annotations

from quant.utils.logging import get_logger

log = get_logger("fx")

# 이미 원화로 표시되는 시장 — 환산하면 오히려 틀린다.
KRW_MARKETS = frozenset({"kr_stock", "upbit"})

# 달러(USD·USDT)로 표시되는 시장 — 환산 대상.
USD_MARKETS = frozenset({"us_stock", "crypto"})

# 합성·모의 시장은 통화 개념이 없다. 환산도 하지 않고 막지도 않는다.
UNITLESS_MARKETS = frozenset({"synthetic"})

# 상식 범위. 원/달러가 이 밖으로 나오면 그것은 환율이 아니라 사고다
# (뒤집힌 계열이면 0.0007, 단위가 틀리면 1.4 같은 값이 온다).
FX_MIN, FX_MAX = 500.0, 5_000.0

_MEMO: dict[str, float | None] = {}


def usdkrw(fetch=None, *, refresh: bool = False) -> float | None:
    """최근 원/달러 종가. **모르면 None** — 절대 1.0으로 대신하지 않는다.

    합성 폴백은 거절한다(`_bench_close`가 이미 걸러낸다). 값이 상식 범위를
    벗어나도 거절한다 — 계열이 뒤집혀 오면 자산이 100만 배 틀어진다.
    """
    if not refresh and "usdkrw" in _MEMO:
        return _MEMO["usdkrw"]
    rate = None
    try:
        from quant.data.crossasset import _bench_close

        s = _bench_close("us_stock", "KRW=X", limit=30, fetch=fetch)
        if s is not None:
            s = s.dropna()
            if len(s):
                rate = float(s.iloc[-1])
    except Exception as exc:  # noqa: BLE001 — 아래에서 None으로 처리된다
        log.warning("원/달러 조회 실패: %s", exc)
        rate = None
    if rate is not None and not (FX_MIN <= rate <= FX_MAX):
        log.warning("원/달러 %.4f 는 상식 범위(%s~%s) 밖 — 환율로 쓰지 않는다",
                    rate, FX_MIN, FX_MAX)
        rate = None
    if rate is None:
        # ⚠️ **실패는 기억하지 않는다.** 기억하면 한 번의 일시적 장애가 그
        #    프로세스 내내 남는다 — `live` 루프는 며칠씩 돌기 때문에, 잠깐
        #    끊긴 것 때문에 해외 종목이 영영 멈춘다. 성공만 캐시한다.
        log.warning("원/달러를 확인하지 못했습니다 — 해외 종목을 원화로 "
                    "환산할 수 없습니다. 1.0으로 대신하지 않습니다.")
        return None
    _MEMO["usdkrw"] = rate
    return rate


def needs_fx(market: str) -> bool:
    """이 시장의 가격을 원화로 환산해야 하는가."""
    return market in USD_MARKETS


def to_krw(market: str, price: float, rate: float | None) -> float | None:
    """현지 통화 가격 → 원화. 환산이 필요한데 환율이 없으면 None.

    None은 "이 종목은 오늘 값을 매길 수 없다"는 뜻이다. 부르는 쪽이
    그 종목을 빼거나 그날을 건너뛰어야 한다 — 0이나 원가격으로 때우면
    바로 지금 고치고 있는 그 결함이 된다.
    """
    p = float(price)
    if not needs_fx(market):
        return p
    if rate is None:
        return None
    return p * float(rate)
