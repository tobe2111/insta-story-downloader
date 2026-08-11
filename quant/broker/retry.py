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
        confirm_fills: bool = False,
        fill_timeout: float = 0.0,
        fill_poll_interval: float = 1.0,
        now: Callable[[], float] = time.time,
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
        # 체결 확인(주식용): 주식 시장가는 접수 후 체결까지 시차가 있어 접수 응답만으로는
        # 실제 체결 수량을 알 수 없다. 브로커가 알려준 체결이 0이면, '이미 테스트된'
        # get_position만으로 주문 전후 포지션 변화를 측정해 실제 체결을 확인한다
        # (추측성 주문조회 엔드포인트를 늘리지 않는다). fill_timeout 안에서
        # fill_poll_interval마다 확인하고, 시간 내 안 채워지면 미체결로 보고한다.
        self.confirm_fills = confirm_fills
        self.fill_timeout = max(0.0, fill_timeout)
        self.fill_poll_interval = max(0.1, fill_poll_interval)
        self._now = now

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
        last_order_id = ""
        # 첫 주문 + 부분체결 시 잔량 재주문(partial_retries회까지)
        for _ in range(self.partial_retries + 1):
            want = self._round_qty(qty - filled_total)
            if want <= 0 or not self.spec.is_tradeable(want, price):
                break
            # 체결 확인용: 제출 직전 포지션(변화량으로 실제 체결을 측정).
            base_qty = self._safe_pos(symbol) if self.confirm_fills else None
            order = self._submit_with_retry(symbol, side, want, price)
            last_order_id = getattr(order, "order_id", "") or last_order_id
            got = self._filled_of(order, want)
            # 접수는 됐지만 체결 수량 미상(주식 시장가 등)이면 포지션 변화로 확인.
            if (self.confirm_fills and got <= 0 and base_qty is not None
                    and order.status not in ("skipped", "rejected", "unfilled")):
                got = self._confirm_by_position(symbol, side, want, base_qty)
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
        return Order(symbol, side, qty, price, status=status,
                     filled_quantity=filled_total, order_id=last_order_id)

    def _safe_pos(self, symbol: str) -> float | None:
        try:
            return self.inner.get_position(symbol).quantity
        except Exception:  # noqa: BLE001
            return None

    def _confirm_by_position(self, symbol: str, side: str, want: float,
                             base_qty: float) -> float:
        """주문 후 포지션 변화를 fill_timeout 동안 폴링해 실제 체결 수량을 측정한다.

        오직 get_position(모든 브로커가 구현·테스트됨)만 사용한다. 매수는 포지션
        증가, 매도는 감소가 정상이며, 관측된 변화량을 want로 상한한다. 시간 내
        변화가 없으면 0(미체결)을 반환한다 — 접수 응답을 체결로 위조하지 않는다.
        """
        deadline = self._now() + self.fill_timeout
        best = 0.0
        while True:
            now_qty = self._safe_pos(symbol)
            if now_qty is not None:
                delta = now_qty - base_qty
                signed = delta if side == "buy" else -delta
                best = max(best, min(signed, want))
                if best >= want * (1 - 1e-6):
                    return best
            if self._now() >= deadline:
                return max(0.0, best)
            self._sleep(self.fill_poll_interval)

    def _submit_with_retry(self, symbol: str, side: str, qty: float, price: float) -> Order:
        """오류 발생 시 지수 백오프로 재시도. 최종 실패 시 알림 후 예외.

        ⚠️ 시장가 주문은 멱등하지 않다. 응답이 타임아웃돼도 거래소에는 이미 체결됐을
        수 있으므로, 무턱대고 재주문하면 이중 체결(2배 노출)이 된다. 재시도 전에
        잔고를 조회해 '주문이 이미 반영됐는지' 확인하고, 반영됐으면 재주문하지 않고
        체결로 간주한다.

        ⚠️ 잔고 조회조차 실패해 **확인이 불가능하면 재주문하지 않는다**(감사 55).
           예전에는 이 경우 '기존처럼 재시도'했다. 그 재시도는 정확히 이 함수가
           막으려던 도박이다 — 확인할 수 없는 상태에서 비멱등 주문을 다시 내는
           것. 두 결과의 무게가 다르다: 재주문을 안 해서 놓친 진입은 다음 봉에
           다시 잡을 수 있지만, 실거래에서 2배가 된 포지션은 되돌릴 수 없다.
           대신 최종 실패로 크게 알린다 — 사장님이 계좌를 직접 확인해야 한다.
        """
        # 제출 전 기준 포지션(중복 감지용). 조회 실패 시 None → 확인 불가.
        try:
            base_qty = self.inner.get_position(symbol).quantity
        except Exception:  # noqa: BLE001
            base_qty = None

        last_exc: Exception | None = None
        remaining = qty
        landed_before = 0.0        # 실패한 시도들이 이미 체결시킨 누계
        unverified = False         # 잔고 확인 불가로 재주문을 포기했는가
        for attempt in range(1, self.retries + 1):
            try:
                order = self.inner.market_order(symbol, side, remaining, price)
                if landed_before <= 0:
                    return order
                # 이미 일부가 체결된 상태에서 잔량만 재주문했다 — 상위
                # 부분체결 루프가 잔량만 체결된 줄 알고 또 주문하지 않도록
                # **누계**로 보고한다(이 합산을 빠뜨리면 초과 체결이 된다).
                got = self._filled_of(order, remaining)
                total = min(qty, landed_before + got)
                return Order(symbol, side, qty, price,
                             status=getattr(order, "status", "filled"),
                             filled_quantity=total,
                             order_id=getattr(order, "order_id", ""))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # 재시도 전, 주문이 이미 (부분이라도) 체결됐는지 잔고로 확인.
                # ⚠️ 예전에는 '전량 체결됐는가'만 보고 아니면 **원래 수량 전부**를
                #    재주문했다. 60%만 체결된 채 응답이 끊긴 경우 나머지 40%가
                #    아니라 100%를 다시 사서 총 160%가 된다(2026-08-11 감사).
                #    이중 체결을 막으려고 만든 장치가 부분 체결에서는 오히려
                #    초과 체결을 만드는 구조였다. 이제 '남은 수량'만 재주문한다.
                landed = self._landed_qty(symbol, side, base_qty)
                if landed is None:
                    # 체결 여부를 확인할 수 없다. 여기서 재주문하는 것이 바로
                    # 이 장치가 막으려던 도박이다 — 확인 불가 상태에서 비멱등
                    # 주문을 다시 내는 것. 멈추고 크게 알린다.
                    log.error("[ROBUST] 잔고 조회 불가 — 주문이 체결됐는지 확인할 수 "
                              "없어 재주문하지 않습니다. 계좌를 직접 확인하세요.")
                    unverified = True
                    break
                if landed >= qty * (1 - 1e-3):
                    log.warning("[ROBUST] 응답은 실패했으나 잔고상 전량 체결 확인 → "
                                "재주문 생략(이중 체결 방지)")
                    return Order(symbol, side, qty, price,
                                 status="filled", filled_quantity=qty)
                if landed > 0:
                    landed_before = landed
                    remaining = max(0.0, qty - landed)
                    log.warning("[ROBUST] 부분 체결 감지(%.6f/%.6f) → 남은 %.6f만 "
                                "재주문", landed, qty, remaining)
                    if remaining <= qty * 1e-3:
                        return Order(symbol, side, landed, price,
                                     status="filled", filled_quantity=landed)
                if attempt >= self.retries:
                    break
                wait = self.backoff * (2 ** (attempt - 1))
                log.warning("[ROBUST] 주문 실패(%d/%d): %s — %.1fs 후 재시도",
                            attempt, self.retries, exc, wait)
                self._sleep(wait)

        msg = f"❌ 주문 최종 실패: {side} {symbol} {qty} — {last_exc}"
        if unverified:
            msg += ("\n⚠️ 잔고를 조회할 수 없어 이 주문이 체결됐는지 확인하지 "
                    "못했습니다. 이중 체결을 피하려고 재주문하지 않았습니다 — "
                    "거래소 계좌에서 실제 보유를 직접 확인해 주세요.")
        log.error(msg)
        if self.notifier is not None:
            self.notifier.send(msg, level="error")
        raise RuntimeError(msg) from last_exc

    def _landed_qty(self, symbol: str, side: str,
                    base_qty: float | None) -> float | None:
        """직전 실패 주문이 실제로 얼마나 체결됐는지 잔고 변화로 잰다.

        base_qty(제출 전 수량)를 알 수 없거나 지금 잔고를 못 읽으면 **None**
        (판정 불가)을 돌려준다. 0.0(= '아무것도 체결 안 됐음을 확인')과 반드시
        구분해야 한다 — 예전에는 둘 다 0.0이라, 확인 실패가 '미체결 확인'으로
        읽혀 전량 재주문으로 이어졌다(감사 55).
        조회 시점상: 타임아웃 실패는 대체로 수십 초가 걸려, 그 사이 브로커의
        잔고 캐시(짧은 TTL)도 만료돼 최신 잔고를 받는다.

        '전량인가'가 아니라 '얼마인가'를 재는 이유: 부분 체결 뒤 전량을
        재주문하면 초과 체결이 된다(2026-08-11 감사에서 발견).
        """
        if base_qty is None:
            return None
        try:
            now_qty = self.inner.get_position(symbol).quantity
        except Exception:  # noqa: BLE001
            return None
        delta = now_qty - base_qty
        signed = delta if side == "buy" else -delta   # 매수는 증가, 매도는 감소가 정상
        return max(0.0, signed)
