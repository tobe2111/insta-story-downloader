"""거래소 주문 규격(MarketSpec) — 수량/가격을 거래소 규칙에 맞게 정규화.

거래소마다 최소주문수량·수량 스텝·가격 틱·최소 주문금액이 다르다. 이를
지키지 않으면 주문이 거절된다. MarketSpec은 이 규칙을 캡슐화하고, ccxt의
market 정보에서 자동으로 생성할 수 있다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class MarketSpec:
    min_qty: float = 0.0        # 최소 주문 수량
    qty_step: float = 0.0       # 수량 최소 단위 (lot size)
    price_tick: float = 0.0     # 가격 최소 단위 (tick size)
    min_notional: float = 0.0   # 최소 주문 금액 (수량 × 가격)

    def round_qty(self, qty: float) -> float:
        """수량을 스텝 단위로 내림하고, 최소수량 미만이면 0으로 만든다."""
        if self.qty_step > 0:
            n = qty / self.qty_step
            # ⚠️ **눈금에 딱 맞는 수량이 한 칸 깎여 나갔다**(감사 164).
            #    부동소수 나눗셈은 정확히 나누어떨어지는 값도 살짝 아래로
            #    만든다. 0.3 / 0.1 == 2.9999999999999996 이라
            #    floor → 2 → 0.2. **33%를 덜 주문한다.**
            #
            #    실측(스텝 0.1): 0.3→0.2  0.7→0.6  8.2→8.1
            #        (스텝 0.0001): 0.0003→0.0002
            #
            #    청산 주문에서 이러면 포지션이 안 닫힌다 — 0.3 코인을 팔라고
            #    했는데 0.2만 팔고 0.1이 그대로 남는다. 뒤의 round(qty, 12)는
            #    이미 깎인 뒤라 아무것도 되돌리지 못한다.
            #
            #    눈금에 사실상 붙어 있으면 그 눈금으로 본다. 내림 자체는
            #    유지한다 — 있는 돈보다 많이 주문하면 안 되기 때문이다.
            nearest = round(n)
            if math.isclose(n, nearest, rel_tol=1e-9, abs_tol=1e-9):
                n = nearest
            qty = math.floor(n) * self.qty_step
            # 곱셈에서 다시 생기는 오차 정리 (3 * 0.1 == 0.30000000000000004)
            qty = round(qty, 12)
        if self.min_qty > 0 and qty < self.min_qty:
            return 0.0
        return max(qty, 0.0)

    def round_price(self, price: float) -> float:
        """가격을 틱 단위로 반올림한다 (지정가 주문용)."""
        if self.price_tick > 0:
            return round(round(price / self.price_tick) * self.price_tick, 12)
        return price

    def is_tradeable(self, qty: float, price: float) -> bool:
        """최소 주문금액 등 규격을 만족하는지 검사한다."""
        if qty <= 0:
            return False
        # 딱 최소금액인 주문을 부동소수 때문에 놓치지 않도록 아주 작은 여유.
        # (0.3 * 10.0 == 2.9999999999999996 < 3.0)
        if self.min_notional > 0 and qty * price < self.min_notional * (1 - 1e-9):
            return False
        return True


# ccxt의 precisionMode 상수 — 값만 옮겨 적는다(여기서 ccxt를 import하지 않는다).
DECIMAL_PLACES = 2
SIGNIFICANT_DIGITS = 3
TICK_SIZE = 4


def _step(prec, mode: int | None = None) -> float:
    """precision 한 칸을 '최소 단위'로 해석한다.

    ⚠️ ccxt는 이 칸을 거래소 모드에 따라 **다른 뜻으로** 채운다(감사 164).

        TICK_SIZE      : 값이 곧 단위다        0.001 · 1.0 · 10.0
        DECIMAL_PLACES : 값이 소수 자릿수다    3 → 0.001

    예전에는 모드를 안 받고 `0 < prec < 1`인 실수만 단위로 인정했다.
    그래서 **단위가 1 이상이면 조용히 '제약 없음'(0.0)이 됐다.** 하필
    그쪽이 라운딩이 제일 중요한 시장이다 — 정수 단위로만 살 수 있는
    종목(SHIB·PEPE류, 계약 상품)에 3.7개를 주문하면 거절당한다.

    실측(정수 단위 시장):
        precision {'amount': 1.0}  →  qty_step 0.0  →  3.7이 3.7로 통과

    그리고 주요 거래소는 전부 TICK_SIZE다 — binance·okx·bybit·upbit·
    coinbase 다섯 개를 ccxt 4.5.70에서 확인했다. 즉 이 경로가 기본이다.
    """
    if prec is None or isinstance(prec, bool):
        return 0.0
    if isinstance(prec, str):                 # 거래소 원본 필드가 문자열인 경우
        text = prec.strip()
        try:
            prec = int(text) if text.lstrip("+-").isdigit() else float(text)
        except ValueError:
            return 0.0
    if not isinstance(prec, (int, float)):
        return 0.0

    if mode == TICK_SIZE:
        return float(prec) if prec > 0 else 0.0
    if mode == DECIMAL_PLACES:
        return 10.0 ** (-int(prec)) if prec >= 0 else 0.0
    if mode == SIGNIFICANT_DIGITS:
        return 0.0        # 유효숫자 모드는 고정 단위로 환산할 수 없다

    # 모드 미상 — ccxt는 TICK_SIZE에서만 실수를 준다는 사실로 추정한다.
    if isinstance(prec, float):
        return prec if prec > 0 else 0.0
    return 10.0 ** (-prec) if prec >= 0 else 0.0


def from_ccxt_market(market: dict, precision_mode: int | None = None) -> MarketSpec:
    """ccxt exchange.markets[symbol] dict로부터 MarketSpec을 생성한다.

    precision_mode: 거래소의 `exchange.precisionMode`. 넘기면 추측하지 않는다.
    """
    limits = market.get("limits", {}) or {}
    precision = market.get("precision", {}) or {}

    return MarketSpec(
        min_qty=float((limits.get("amount", {}) or {}).get("min") or 0.0),
        qty_step=_step(precision.get("amount"), precision_mode),
        price_tick=_step(precision.get("price"), precision_mode),
        min_notional=float((limits.get("cost", {}) or {}).get("min") or 0.0),
    )
