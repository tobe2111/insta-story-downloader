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
            qty = math.floor(qty / self.qty_step) * self.qty_step
            # 부동소수 오차 정리
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
        if self.min_notional > 0 and qty * price < self.min_notional:
            return False
        return True


def from_ccxt_market(market: dict) -> MarketSpec:
    """ccxt exchange.markets[symbol] dict로부터 MarketSpec을 생성한다.

    거래소마다 precision 표기가 (소수 자릿수 / 스텝) 으로 다르므로 best-effort로 해석.
    """
    limits = market.get("limits", {}) or {}
    precision = market.get("precision", {}) or {}

    def _step(prec) -> float:
        if prec is None:
            return 0.0
        # 정수면 소수 자릿수, 실수(<1)면 스텝으로 간주
        if isinstance(prec, int):
            return 10.0 ** (-prec)
        if isinstance(prec, float) and 0 < prec < 1:
            return prec
        return 0.0

    return MarketSpec(
        min_qty=float((limits.get("amount", {}) or {}).get("min") or 0.0),
        qty_step=_step(precision.get("amount")),
        price_tick=_step(precision.get("price")),
        min_notional=float((limits.get("cost", {}) or {}).get("min") or 0.0),
    )
