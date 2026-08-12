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
        """현금 + 평가액. marks: {symbol: 현재가}

        ⚠️ **marks에 없는 종목은 매입가로 평가된다** — 즉 "산 뒤로 한 푼도
           안 움직였다"고 치는 것이다. 편해 보이지만 위험한 기본값이라
           호출자는 반드시 전 보유 종목의 시세를 채워 넘겨야 한다.

           실제로 그러지 못한 자리가 있었다(감사 152). 포트폴리오 배치는
           데이터를 못 받은 종목을 prices에서 빼는데 포지션은 그대로
           복원했고, 그 결과 그 종목의 손익이 통째로 0이 됐다. 그 자산이
           장부의 수익률·킬스위치가 읽는 낙폭·사이트 TWR로 흘러가므로,
           **폭락한 종목이 하필 그날 데이터 장애를 만나면 손실이 사라지고
           브레이크도 안 걸린다.** 지금은 호출자가 마지막으로 알던 시장가로
           채우고 그 사실을 장부(stale_marks)에 남긴다.
        """
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

    def limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        limit_price: float,
        bar_high: float,
        bar_low: float,
        fill_fraction: float = 1.0,
    ) -> Order:
        """지정가 주문 시뮬레이션 — 봉의 고저가가 지정가를 지나야만 체결된다.

        체결 조건 (보수적 근사):
            매수: bar_low  <= limit_price  (가격이 지정가 이하로 내려왔을 때)
            매도: bar_high >= limit_price  (가격이 지정가 이상으로 올라갔을 때)
        체결가는 항상 limit_price로 가정한다(가격 개선 없음 — 낙관 방지).
        fill_fraction(0~1)으로 부분체결을 흉내낸다: 지정가에 닿았다고 전량
        체결된다는 보장이 없기 때문이다(호가 순서·물량은 시뮬레이션 불가).

        ⚠️ 실제 체결은 호가창 깊이·주문 순서에 좌우되며 이 근사는 그것을
           대체하지 못한다. 미체결 주문은 status='open'으로 반환만 하고
           다음 봉으로 이월하지 않는다(호출자가 재주문 여부를 결정).
        """
        crossed = (bar_low <= limit_price) if side == "buy" \
            else (bar_high >= limit_price)
        frac = min(1.0, max(0.0, fill_fraction))
        filled = quantity * frac if crossed else 0.0

        if filled <= 0.0:
            order = Order(symbol, side, quantity, limit_price,
                          status="open", filled_quantity=0.0)
            self.order_log.append(order)
            if len(self.order_log) > _ORDER_LOG_CAP:
                del self.order_log[:-_ORDER_LOG_CAP]
            log.info("[PAPER] %s %s %.6f @ %.2f 지정가 미체결",
                     side.upper(), symbol, quantity, limit_price)
            return order

        # 회계는 market_order와 동일 경로 재사용(현금·평단 일관성 유지).
        order = self.market_order(symbol, side, filled, limit_price)
        order.quantity = quantity                      # 주문 수량은 요청 수량으로
        order.filled_quantity = filled
        order.status = "filled" if frac >= 1.0 else "partial"
        return order
