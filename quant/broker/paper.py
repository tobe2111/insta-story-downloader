"""페이퍼 트레이딩 브로커 — 실제 돈 없이 주문을 시뮬레이션한다.

실거래 전 반드시 이 단계에서 전략이 의도대로 동작하는지 확인할 것.
"""
from __future__ import annotations

from quant.broker.base import (
    Broker,
    Order,
    Position,
    normalize_side,
    safe_amount,
)
from quant.utils.logging import get_logger

log = get_logger("broker.paper")

_ORDER_LOG_CAP = 1000   # 무한 실행 시 메모리 누수 방지(최근 주문만 유지)
_DUST = 1e-9            # 부동소수 잔여수량 임계 — 이하이면 완전 청산으로 간주


def _positive(value, what: str) -> float:
    """주문의 수량·가격 — **양의 유한수가 아니면 돈을 움직이지 않는다**.

    ⚠️ 없을 때 어떤 일이 벌어지는지 실제로 돌려 봤다(2026-08-14 감사 233):

        수량 NaN   → 현금 nan · 보유 nan
        가격 inf   → 현금 -inf
        가격 -50   → **매수했는데 현금이 늘고 보유도 늘었다**
        수량 -10   → 매수가 공매도가 됐다

    첫 줄이 가장 나쁘다. 계좌가 NaN이 되면 자산·수익률·낙폭이 전부 NaN이 되고,
    킬스위치는 `낙폭 < 문턱`을 NaN으로 비교해 **항상 False** — 즉 브레이크가
    조용히 풀린다(감사 198이 잡은 것과 똑같은 모양이다). 게다가 이 계좌는
    8마일 챌린지의 모든 기록이 나오는 곳이라, 한 번 오염되면 장부·사이트·
    SNS가 전부 그 위에 쌓인다.

    `base.safe_amount`가 이미 이 판정을 갖고 있었다 — 실거래 브로커들만 쓰고
    **정작 돈을 들고 있는 페이퍼 브로커는 안 쓰고 있었다.** 같은 계열의
    빠뜨림이 감사 192(방향)·199(잔고 필드)에도 있었다.

    거부가 아니라 **예외**인 이유: 여기까지 온 NaN은 상위 어딘가가 고장났다는
    뜻이고, 조용히 건너뛰면 그 고장이 다음 날도 그대로 돈다. 배치가 죽으면
    아무것도 기록되지 않고(원자적 쓰기라 계좌는 그대로다) 실패 경보가 폰으로
    간다. 조용히 틀린 계좌보다 시끄러운 실패가 낫다.
    """
    v = safe_amount(value, default=-1.0)      # nan·inf·음수 → -1.0
    if v <= 0.0:
        raise ValueError(f"{what}이(가) 양의 유한수가 아니다: {value!r}")
    return v


class PaperBroker(Broker):
    def __init__(self, cash: float = 10_000.0, fee: float = 0.001,
                 allow_margin: bool = False, short_margin: float = 0.0):
        self._cash = cash
        self.fee = fee
        # 신규·추가 **공매도**에 필요한 증거금 비율(|숏 노출| 대비).
        # 0(기본) = 공매도 금지 — 매도는 **보유 수량까지만** 체결된다.
        #
        # ⚠️ 왜 기본이 금지인가 (2026-08-16 실측, 감사 260).
        #    이 클래스는 매도를 전혀 막지 않았다. "빠져나오는 길을 막으면
        #    덫이 된다"는 옳은 이유였지만, 그 구멍으로 **증거금 없는 무제한
        #    공매도**가 열려 있었다:
        #
        #        100만원 계좌에 목표 -500% → -50,000주 체결 · 현금 599만원
        #
        #    실전에는 없는 계좌다. 대주 가능 수량도, 증거금도, 대차료도 없다
        #    (short_borrow가 전 시장 0.0이었다). 이 상태로 숏 전략을 오디션에
        #    올리면 **실제로는 낼 수 없는 성과**로 챔피언이 뽑힌다 — 이 저장소가
        #    반복해서 고쳐 온 '오디션-현실 격차' 그 자체다.
        #
        #    청산은 그대로 자유롭다. 막는 것은 **보유를 넘어서는 매도**뿐이다.
        self.short_margin = max(0.0, float(short_margin))
        self._positions: dict[str, Position] = {}
        self.order_log: list[Order] = []
        # 현금보다 큰 매수를 허용할 것인가. 기본은 **아니다** — 아래 참고.
        self.allow_margin = bool(allow_margin)
        self.rejected: list[dict] = []     # 현금이 모자라 거부한 주문들

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

    def _log_order(self, order: Order) -> None:
        """주문 기록 한 자리 — 캡 처리를 세 곳에 복사해 두지 않는다."""
        self.order_log.append(order)
        if len(self.order_log) > _ORDER_LOG_CAP:       # 무한 성장 방지
            del self.order_log[:-_ORDER_LOG_CAP]

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        side = normalize_side(side)   # 모르는 방향이 매도가 되면 안 된다(감사 192)
        quantity = _positive(quantity, "주문 수량")   # 감사 233
        price = _positive(price, "체결 가격")
        cost = quantity * price
        fee = cost * self.fee

        # ── 현금 한도 — 없는 돈으로 사지 않는다 (2026-08-14 감사 233) ──
        #
        # 실측: 100만원 계좌로 500만원어치를 사면 **그냥 체결됐다.** 현금
        # -400만원. 이자도 없고 증거금도 없는 신용거래다. 페이퍼 성적이
        # 그만큼 낙관적으로 나오고, 그 숫자가 사이트·SNS로 나간다.
        #
        # 지금 운영 경로는 세 겹으로 막혀 있다 — 레버리지 금지선
        # (MAX_GROSS_EXPOSURE), 매수 수수료 버퍼(base.rebalance_to_weight),
        # 매도 우선 순서(daily.py). 셋 다 **다른 모듈**에 있고, 정작 현금을
        # 들고 있는 이 클래스는 아무것도 확인하지 않았다. 이 저장소가
        # 반복해서 당한 모양이라(감사 198·192·199) 값을 가진 자리에 둔다.
        #
        # 매도는 막지 않는다 — 공매도는 현금을 늘리고, 빠져나오는 길을
        # 막으면 리스크 관리가 아니라 덫이 된다(같은 이유로 잔돈 청산도
        # 막지 않는다).
        if side == "buy" and not self.allow_margin \
                and cost + fee > self._cash + _DUST:
            order = Order(symbol, side, quantity, price,
                          status="rejected", filled_quantity=0.0)
            self._log_order(order)
            self.rejected.append({"symbol": symbol, "need": cost + fee,
                                  "cash": self._cash})
            # 조용히 안 사면 계좌가 이유 없이 작아진다 — 소리를 낸다.
            log.error("[PAPER] 현금 부족으로 거부: %s 매수 %.6f @ %.2f "
                      "(필요 %.2f · 보유현금 %.2f)",
                      symbol, quantity, price, cost + fee, self._cash)
            return order

        pos = self.get_position(symbol)
        old_qty, old_avg = pos.quantity, pos.avg_price

        # ── 공매도 한도 — 없는 주식을 팔지 않는다 (감사 260) ──────────
        # 청산(보유 범위 안의 매도)은 그대로 통과한다. 보유를 **넘어서는**
        # 매도만 증거금을 본다. 증거금 모델이 없으면(기본) 보유까지로 자른다.
        if side == "sell":
            allowance = max(0.0, old_qty)          # 팔 수 있는 보유 수량
            if self.short_margin > 0.0:
                # |숏 노출| × 증거금비율 ≤ 현금. 현금이 담보다.
                allowance += max(0.0, self._cash) / (price * self.short_margin)
            if quantity > allowance + _DUST:
                cut = quantity - allowance
                self.rejected.append({"symbol": symbol, "short_over": cut,
                                      "allowance": allowance,
                                      "reason": "공매도 한도"})
                log.error("[PAPER] 공매도 한도 초과: %s 매도 %.6f 중 %.6f만 "
                          "체결 가능(보유·증거금 기준) — 초과분 %.6f 거부",
                          symbol, quantity, allowance, cut)
                quantity = allowance
                if quantity <= _DUST:
                    order = Order(symbol, side, 0.0, price,
                                  status="rejected", filled_quantity=0.0)
                    self._log_order(order)
                    return order
                cost = quantity * price
                fee = cost * self.fee

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
        self._log_order(order)
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
        side = normalize_side(side)
        crossed = (bar_low <= limit_price) if side == "buy" \
            else (bar_high >= limit_price)
        frac = min(1.0, max(0.0, fill_fraction))
        filled = quantity * frac if crossed else 0.0

        if filled <= 0.0:
            order = Order(symbol, side, quantity, limit_price,
                          status="open", filled_quantity=0.0)
            self._log_order(order)
            log.info("[PAPER] %s %s %.6f @ %.2f 지정가 미체결",
                     side.upper(), symbol, quantity, limit_price)
            return order

        # 회계는 market_order와 동일 경로 재사용(현금·평단 일관성 유지).
        order = self.market_order(symbol, side, filled, limit_price)
        order.quantity = quantity                      # 주문 수량은 요청 수량으로
        # ⚠️ 거부된 주문을 '체결'로 덮어쓰지 않는다(감사 233). 예전에는
        #    아래 두 줄이 무조건 실행돼서, 현금 부족으로 돈이 한 푼도 안
        #    움직인 주문이 장부에 **전량 체결**로 남을 뻔했다.
        if order.status == "rejected":
            return order
        order.filled_quantity = filled
        order.status = "filled" if frac >= 1.0 else "partial"
        return order
