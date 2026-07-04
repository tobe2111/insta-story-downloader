"""페이퍼 트레이딩 브로커 — 실제 돈 없이 주문을 시뮬레이션한다.

실거래 전 반드시 이 단계에서 전략이 의도대로 동작하는지 확인할 것.
"""
from __future__ import annotations

from quant.broker.base import Broker, Order, Position
from quant.utils.logging import get_logger

log = get_logger("broker.paper")

_ORDER_LOG_CAP = 1000   # 무한 실행 시 메모리 누수 방지(최근 주문만 유지)
_DUST = 1e-9            # 부동소수 잔여수량 임계 — 이하이면 완전 청산으로 간주


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
        old_qty, old_avg = pos.quantity, pos.avg_price

        # 현금: 매수는 비용+수수료 차감, 매도는 대금-수수료 가산(자금 보존).
        if side == "buy":
            self._cash -= cost + fee
            signed = quantity
        else:
            self._cash += cost - fee
            signed = -quantity

        new_qty = old_qty + signed
        if abs(new_qty) < _DUST:          # 부동소수 먼지 제거 → 완전 청산으로 스냅
            new_qty = 0.0

        # 진입가(avg_price)는 방향을 고려해야 한다. 롱 가정으로만 계산하던 기존
        # 로직은 숏 진입(avg=0)·플립(옛 롱 평단 유지)·부분 커버(무의미한 평단)에서
        # 틀렸고, 이 값이 equity()의 미표시 마크로 쓰여 자산을 왜곡했다.
        if new_qty == 0.0:
            new_avg = 0.0                                      # 전량 청산
        elif old_qty == 0.0 or (new_qty > 0) != (old_qty > 0):
            new_avg = price                                    # 신규 진입 또는 방향 전환(플립)
        elif abs(new_qty) > abs(old_qty):
            new_avg = (old_avg * old_qty + price * signed) / new_qty  # 같은 방향 증가 → 가중평균
        else:
            new_avg = old_avg                                  # 같은 방향 축소(부분 청산/커버) → 유지

        self._positions[symbol] = Position(symbol, new_qty, new_avg)

        order = Order(symbol, side, quantity, price, status="filled",
                      filled_quantity=quantity)
        self.order_log.append(order)
        if len(self.order_log) > _ORDER_LOG_CAP:       # 무한 성장 방지
            del self.order_log[:-_ORDER_LOG_CAP]
        log.info("[PAPER] %s %s %.6f @ %.2f (현금: %.2f)",
                 side.upper(), symbol, quantity, price, self._cash)
        return order
