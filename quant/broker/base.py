"""브로커 공통 인터페이스.

페이퍼 트레이딩과 실거래가 동일한 인터페이스를 구현하므로,
실행 코드를 바꾸지 않고 --paper / --live 만 전환할 수 있다.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


def safe_amount(value, default: float = 0.0, allow_negative: bool = False) -> float:
    """거래소/API 응답에서 읽은 금액·수량을 안전하게 float로 변환한다.

    inf·nan·(기본적으로) 음수는 거부하고 default를 반환한다. 잘못되거나 악의적인
    잔고·체결·가격 값이 자금 계산(equity=cash+수량*가격 → 주문 수량)을 오염시켜
    'inf 수량 주문'이나 NaN 비교 오류를 일으키는 것을 막는다.
    allow_negative=True 는 숏 포지션 수량처럼 음수가 정상인 경우에만 쓴다.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    if v < 0 and not allow_negative:
        return default
    return v


@dataclass
class Order:
    symbol: str
    side: str        # 'buy' | 'sell'
    quantity: float
    price: float     # 체결가(추정)
    status: str = "filled"
    filled_quantity: float = 0.0  # 실제 체결 수량 (부분체결 추적용)


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_price: float


class Broker(ABC):
    @abstractmethod
    def get_cash(self) -> float:
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        ...

    @abstractmethod
    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        ...

    def target_weight(
        self, symbol: str, weight: float, price: float, equity: float
    ) -> Order | None:
        """현재 포지션을 목표 비중(weight)에 맞추도록 주문을 낸다.

        weight: -1.0 ~ 1.0 (자본 대비 목표 노출)
        price:  현재가
        equity: 총 자산 (현금 + 평가액)
        """
        if price <= 0:
            return None
        fee = getattr(self, "fee", 0.0) or 0.0
        target_qty = (weight * equity) / price
        current = self.get_position(symbol).quantity
        delta = target_qty - current
        # 수수료 버퍼는 '롱 노출을 늘리는 매수'에만 적용한다: 풀 비중(weight≈1)에서
        # 비용+수수료가 현금을 초과해 '음수 현금'이 되는 것을 막는다. 숏(weight<0)이나
        # 포지션 축소(delta<0)에까지 (1+fee)로 나누면 목표만 왜곡돼(숏 과소진입·축소
        # 과다) 현금 문제도 없는데 사이징이 틀어진다. fee 속성이 있는 브로커(페이퍼)에만
        # 반영되고, 실거래 브로커는 fee=0으로 무영향(거래소가 잔고를 검증한다).
        if fee > 0 and weight > 0 and delta > 0:
            target_qty = (weight * equity) / (price * (1.0 + fee))
            delta = target_qty - current
        if abs(delta * price) < 1e-6:
            return None  # 조정 불필요
        side = "buy" if delta > 0 else "sell"
        return self.market_order(symbol, side, abs(delta), price)
