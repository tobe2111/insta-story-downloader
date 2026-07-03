"""미국주식 실거래 브로커 (Alpaca REST API).

⚠️ 실제 자금이 오갑니다. 반드시 페이퍼 계정(paper=True)으로 충분히 검증 후 사용하세요.
환경변수:
    ALPACA_API_KEY, ALPACA_SECRET
문서: https://docs.alpaca.markets/
"""
from __future__ import annotations

import os

from quant.broker.base import Broker, Order, Position
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
        return float(acct.get("cash", 0.0))

    def get_equity(self) -> float:
        acct = get_json(f"{self.base}/v2/account", self._headers())
        return float(acct.get("equity", 0.0))

    def get_position(self, symbol: str) -> Position:
        try:
            p = get_json(f"{self.base}/v2/positions/{symbol}", self._headers())
            return Position(symbol, float(p.get("qty", 0.0)), float(p.get("avg_entry_price", 0.0)))
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
        filled = float(res.get("filled_avg_price") or price)
        return Order(symbol, side, quantity, filled, status=res.get("status", "accepted"))
