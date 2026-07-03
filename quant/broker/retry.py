"""주문 견고화 래퍼 (RobustBroker).

어떤 브로커든 감싸서 다음을 추가한다:
    - 일시적 오류(네트워크·레이트리밋) 시 지수 백오프 재시도
    - 수량 라운딩: 최소 주문수량/스텝 미만은 0으로 처리해 거래소 거절 방지
    - 최종 실패 시 알림 전송

실거래는 반드시 실패한다는 전제로 설계해야 한다. 문제는 '언제·어떻게'다.
"""
from __future__ import annotations

import math
import time
from typing import Callable

from quant.broker.base import Broker, Order, Position
from quant.utils.logging import get_logger

log = get_logger("broker.robust")


class RobustBroker(Broker):
    def __init__(
        self,
        inner: Broker,
        retries: int = 3,
        backoff: float = 1.0,
        min_qty: float = 0.0,
        qty_step: float = 0.0,
        notifier=None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.inner = inner
        self.retries = max(1, retries)
        self.backoff = backoff
        self.min_qty = min_qty
        self.qty_step = qty_step
        self.notifier = notifier
        self._sleep = sleep

    # --- 조회는 그대로 위임 ---
    def get_cash(self) -> float:
        return self.inner.get_cash()

    def get_position(self, symbol: str) -> Position:
        return self.inner.get_position(symbol)

    def equity(self, marks: dict) -> float:
        if hasattr(self.inner, "equity"):
            return self.inner.equity(marks)
        cash = self.inner.get_cash()
        return cash + sum(
            self.inner.get_position(s).quantity * p for s, p in marks.items()
        )

    # --- 수량 정규화 ---
    def _round_qty(self, qty: float) -> float:
        if self.qty_step > 0:
            qty = math.floor(qty / self.qty_step) * self.qty_step
        if self.min_qty > 0 and qty < self.min_qty:
            return 0.0
        return qty

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        qty = self._round_qty(quantity)
        if qty <= 0:
            log.info("[ROBUST] %s %s 수량(%.8f)이 최소기준 미만 → 건너뜀",
                     side, symbol, quantity)
            return Order(symbol, side, 0.0, price, status="skipped")

        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self.inner.market_order(symbol, side, qty, price)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= self.retries:
                    break
                wait = self.backoff * (2 ** (attempt - 1))
                log.warning("[ROBUST] 주문 실패(%d/%d): %s — %.1fs 후 재시도",
                            attempt, self.retries, exc, wait)
                self._sleep(wait)

        msg = f"❌ 주문 최종 실패: {side} {symbol} {qty} — {last_exc}"
        log.error(msg)
        if self.notifier is not None:
            self.notifier.send(msg, level="error")
        raise RuntimeError(msg) from last_exc
