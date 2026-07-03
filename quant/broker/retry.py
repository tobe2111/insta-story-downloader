"""주문 견고화 래퍼 (RobustBroker).

어떤 브로커든 감싸서 다음을 추가한다:
    - 일시적 오류(네트워크·레이트리밋) 시 지수 백오프 재시도
    - 거래소 규격(MarketSpec) 기반 수량 라운딩 + 최소금액 검사
    - 부분체결(partial fill) 추적 → 잔량 자동 재주문
    - 최종 실패 시 알림 전송

실거래는 반드시 실패한다는 전제로 설계해야 한다. 문제는 '언제·어떻게'다.
"""
from __future__ import annotations

import math
import time
from typing import Callable

from quant.broker.base import Broker, Order, Position
from quant.broker.specs import MarketSpec
from quant.utils.logging import get_logger

log = get_logger("broker.robust")

_FILLED_STATES = {"filled", "closed", "done", "ok"}


class RobustBroker(Broker):
    def __init__(
        self,
        inner: Broker,
        retries: int = 3,
        backoff: float = 1.0,
        min_qty: float = 0.0,
        qty_step: float = 0.0,
        spec: MarketSpec | None = None,
        min_notional: float = 0.0,
        partial_retries: int = 2,
        notifier=None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.inner = inner
        self.retries = max(1, retries)
        self.backoff = backoff
        # spec이 주어지면 우선, 아니면 개별 파라미터로 임시 spec 구성
        self.spec = spec or MarketSpec(
            min_qty=min_qty, qty_step=qty_step, min_notional=min_notional
        )
        self.partial_retries = max(0, partial_retries)
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
        return self.spec.round_qty(qty)

    @staticmethod
    def _filled_of(order: Order, want: float) -> float:
        """주문 결과에서 실제 체결 수량을 추정한다."""
        fq = getattr(order, "filled_quantity", 0.0) or 0.0
        if fq > 0:
            return min(fq, want)
        return want if order.status in _FILLED_STATES else 0.0

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        qty = self._round_qty(quantity)
        if qty <= 0 or not self.spec.is_tradeable(qty, price):
            log.info("[ROBUST] %s %s 수량(%.8f)이 규격 미만 → 건너뜀",
                     side, symbol, quantity)
            return Order(symbol, side, 0.0, price, status="skipped", filled_quantity=0.0)

        filled_total = 0.0
        # 첫 주문 + 부분체결 시 잔량 재주문(partial_retries회까지)
        for _ in range(self.partial_retries + 1):
            want = self._round_qty(qty - filled_total)
            if want <= 0 or not self.spec.is_tradeable(want, price):
                break
            order = self._submit_with_retry(symbol, side, want, price)
            got = self._filled_of(order, want)
            filled_total += got
            if got >= want * (1 - 1e-9):
                break  # 완전 체결
            if got <= 0:
                break  # 체결 실패 — 무한루프 방지
            if self.notifier is not None:
                self.notifier.send(
                    f"부분체결: {symbol} {got:.6f}/{want:.6f} — 잔량 재주문", "warning"
                )

        if filled_total >= qty * (1 - 1e-9):
            status = "filled"
        elif filled_total > 0:
            status = "partial"
        else:
            status = "unfilled"
        return Order(symbol, side, qty, price, status=status, filled_quantity=filled_total)

    def _submit_with_retry(self, symbol: str, side: str, qty: float, price: float) -> Order:
        """오류 발생 시 지수 백오프로 재시도. 최종 실패 시 알림 후 예외."""
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
