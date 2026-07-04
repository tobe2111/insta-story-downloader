"""미국주식 실거래 브로커 (Alpaca REST API).

⚠️ 실제 자금이 오갑니다. 반드시 페이퍼 계정(paper=True)으로 충분히 검증 후 사용하세요.
환경변수:
    ALPACA_API_KEY, ALPACA_SECRET
문서: https://docs.alpaca.markets/
"""
from __future__ import annotations

import os

from quant.broker.base import Broker, Order, Position, safe_amount
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
        try:
            p = get_json(f"{self.base}/v2/positions/{symbol}", self._headers())
            return Position(symbol,
                            safe_amount(p.get("qty", 0.0), allow_negative=True),
                            safe_amount(p.get("avg_entry_price", 0.0)))
        except RuntimeError:
            # 포지션 없음 → 404
            return Position(symbol, 0.0, 0.0)

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
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
        return Order(symbol, side, quantity, filled,
                     status=status, filled_quantity=filled_qty)
