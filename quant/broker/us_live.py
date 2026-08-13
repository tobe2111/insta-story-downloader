"""미국주식 실거래 브로커 (Alpaca REST API).

⚠️ 실제 자금이 오갑니다. 반드시 페이퍼 계정(paper=True)으로 충분히 검증 후 사용하세요.
환경변수:
    ALPACA_API_KEY, ALPACA_SECRET
문서: https://docs.alpaca.markets/
"""
from __future__ import annotations

import os

from quant.broker.base import Broker, Order, Position, safe_amount, normalize_side
from quant.broker.specs import MarketSpec
from quant.utils.http import get_json, post_json
from quant.utils.logging import get_logger

log = get_logger("broker.us_live")


class AlpacaBroker(Broker):
    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"

    def __init__(self, paper: bool = True):
        self.base = self.PAPER_URL if paper else self.LIVE_URL
        self.key = os.getenv("ALPACA_API_KEY", "")
        self.secret = os.getenv("ALPACA_SECRET", "")
        if not self.key or not self.secret:
            raise RuntimeError("환경변수 ALPACA_API_KEY / ALPACA_SECRET 가 필요합니다.")
        if not paper:
            log.warning("⚠️ Alpaca 실거래(LIVE) 모드입니다. 실제 자금이 사용됩니다.")

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "content-type": "application/json",
        }

    def get_cash(self) -> float:
        acct = get_json(f"{self.base}/v2/account", self._headers())
        # 현금은 음수가 정상일 수 있다(마진 차입 계좌). 0으로 깎으면 자산이
        # 과대평가돼 과대 주문이 나가므로 음수를 허용한다.
        return safe_amount(acct.get("cash", 0.0), allow_negative=True)

    def get_equity(self) -> float:
        acct = get_json(f"{self.base}/v2/account", self._headers())
        return safe_amount(acct.get("equity", 0.0))

    def equity(self, marks: dict | None = None) -> float:
        """총자산 — 브로커/래퍼가 찾는 공통 이름(marks는 무시, 계좌값이 정답).

        MultiTrader·RobustBroker는 hasattr(broker, "equity")로 총자산을 찾는다.
        이 메서드가 없으면 Alpaca의 권위있는 계좌 평가액 대신 현금+수량*가격으로
        재구성해버리므로, 동일 개념을 같은 이름으로 노출해 일관성을 맞춘다.
        """
        return self.get_equity()

    def get_position(self, symbol: str) -> Position:
        """보유 포지션 조회. 실제로 '없을 때'만 0주를 반환한다.

        ⚠️ 예전에는 `except RuntimeError: return Position(symbol, 0, 0)`이었다
           (감사 55). 주석은 "포지션 없음 → 404"라고 적혀 있었지만, get_json은
           401(토큰 만료)·429(요청 제한)·500(알파카 장애)·타임아웃도 전부 같은
           RuntimeError로 던진다. 실거래 계좌에서 그 전부가 '0주 보유'로
           읽히면, 상위 로직은 목표 비중만큼 **다시 사서** 포지션이 두 배가
           된다. 오늘 이미 브로커 재시도에서 같은 형태의 초과 체결을 잡았다.

           404만 '없음'이다. 나머지는 모르는 것이므로 그대로 올려보낸다 —
           호출부가 '모름'을 보고 매매를 건너뛸 수 있어야 한다.
        """
        try:
            p = get_json(f"{self.base}/v2/positions/{symbol}", self._headers())
            return Position(symbol,
                            safe_amount(p.get("qty", 0.0), allow_negative=True),
                            safe_amount(p.get("avg_entry_price", 0.0)))
        except RuntimeError as exc:
            if getattr(exc, "status", None) == 404:
                return Position(symbol, 0.0, 0.0)     # 진짜로 보유 없음
            raise

    def market_spec(self, symbol: str) -> MarketSpec:
        """미국주식 주문 규격 — 소수점 주 허용, 1달러 하한 (감사 148).

        Alpaca는 소수점 주(fractional share)를 지원하므로 정수 내림이 없다.
        따라서 min_qty·qty_step은 0(제한 없음)이고, 대신 **금액 하한**을 둔다.

        min_notional 1.0은 거래소 규칙이라기보다 **우리가 두는 하한**이다.
        1달러어치 주문은 체결돼도 수수료·스프레드가 기대수익을 넘어서고,
        무엇보다 20종목에 나눈 예산이 그 수준이라면 문제는 주문이 아니라
        유니버스다 — 조용히 사지 말고 걸러서 이유를 남기는 편이 낫다.
        """
        return MarketSpec(min_notional=1.0)

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        side = normalize_side(side)   # 알파카가 거절하기 전에 우리가 먼저 막는다(감사 192)
        body = {
            "symbol": symbol,
            "qty": round(quantity, 6),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        log.warning("[ALPACA] %s %s %.6f 주문 전송", side.upper(), symbol, quantity)
        res = post_json(f"{self.base}/v2/orders", self._headers(), body)
        status = res.get("status", "accepted")
        # 시장가라도 POST 응답은 흔히 status="accepted"·filled_qty=0으로 즉시
        # 돌아오고 체결은 비동기다. 여기서 미체결을 '전량 체결'로 꾸며내면
        # 상위 로직이 주문 완료로 오판해 중복 주문·잘못된 사이징을 낸다. 실제
        # 응답 값만 신뢰하고, 체결 정보가 없으면 0으로 보고한다(호출측이 상태로
        # 미체결을 구분할 수 있게).
        def _num(key: str, default: float) -> float:
            v = res.get(key)
            if v in (None, ""):
                return default
            # 체결 수량·체결가에 inf/nan/음수가 섞이면 상위 사이징이 오염된다.
            # 다른 경로(잔고·포지션)와 동일하게 safe_amount로 거른다.
            return safe_amount(v, default=default)

        filled_qty = _num("filled_qty", 0.0)
        # 체결가는 체결이 있을 때만 의미가 있다. 없으면 참고용으로 주문가를 둔다.
        filled = _num("filled_avg_price", price if filled_qty > 0 else 0.0)
        return Order(symbol, side, quantity, filled, status=status,
                     filled_quantity=filled_qty, order_id=str(res.get("id", "")))
