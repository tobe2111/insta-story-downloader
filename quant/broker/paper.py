"""페이퍼 트레이딩 브로커 — 실제 돈 없이 주문을 시뮬레이션한다.

실거래 전 반드시 이 단계에서 전략이 의도대로 동작하는지 확인할 것.
"""
from __future__ import annotations

from quant.broker.base import Broker, Order, Position
from quant.utils.logging import get_logger

log = get_logger("broker.paper")


class PaperBroker(Broker):
    def __init__(self, cash: float = 10_000.0, fee: float = 0.001):
        self._cash = cash
        self.fee = fee
        self._positions: dict[str, Position] = {}
        self.order_log: list[Order] = []

    def get_cash(self) -> float:
        return self._cash

    def get_position(self, symbol: str) -> Position:
        return self._positions.get(symbol, Position(symbol, 0.0, 0.0))

    def equity(self, marks: dict[str, float]) -> float:
        """현금 + 평가액. marks: {symbol: 현재가}"""
        val = self._cash
        for sym, p in self._positions.items():
            val += p.quantity * marks.get(sym, p.avg_price)
        return val

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        cost = quantity * price
        fee = cost * self.fee
        pos = self.get_position(symbol)

        if side == "buy":
            self._cash -= cost + fee
            new_qty = pos.quantity + quantity
            new_avg = (
                (pos.avg_price * pos.quantity + cost) / new_qty if new_qty else 0.0
            )
            self._positions[symbol] = Position(symbol, new_qty, new_avg)
        else:  # sell
            self._cash += cost - fee
            new_qty = pos.quantity - quantity
            self._positions[symbol] = Position(
                symbol, new_qty, pos.avg_price if new_qty else 0.0
            )

        order = Order(symbol, side, quantity, price)
        self.order_log.append(order)
        log.info("[PAPER] %s %s %.6f @ %.2f (현금: %.2f)",
                 side.upper(), symbol, quantity, price, self._cash)
        return order
