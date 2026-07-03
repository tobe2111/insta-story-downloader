"""암호화폐 실거래 브로커 (ccxt 기반).

⚠️ 실제 자금이 오가는 코드입니다. API 키에는 반드시 '출금 권한을 제외'하고,
   소액으로 충분히 검증한 뒤 사용하세요. 키는 환경변수로만 주입하세요.
"""
from __future__ import annotations

import os

from quant.broker.base import Broker, Order, Position
from quant.utils.logging import get_logger

log = get_logger("broker.crypto_live")


class CryptoLiveBroker(Broker):
    def __init__(self, exchange: str = "binance", quote: str = "USDT"):
        self.quote = quote
        try:
            import ccxt
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("실거래에는 ccxt가 필요합니다: pip install ccxt") from exc

        api_key = os.getenv("EXCHANGE_API_KEY", "")
        secret = os.getenv("EXCHANGE_SECRET", "")
        if not api_key or not secret:
            raise RuntimeError(
                "환경변수 EXCHANGE_API_KEY / EXCHANGE_SECRET 가 필요합니다."
            )
        self.client = getattr(ccxt, exchange)(
            {"apiKey": api_key, "secret": secret, "enableRateLimit": True}
        )

    def get_cash(self) -> float:
        bal = self.client.fetch_balance()
        return float(bal.get("free", {}).get(self.quote, 0.0))

    def get_position(self, symbol: str) -> Position:
        base = symbol.split("/")[0]
        bal = self.client.fetch_balance()
        qty = float(bal.get("total", {}).get(base, 0.0))
        return Position(symbol, qty, 0.0)

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        log.warning("[LIVE] %s %s %.6f @ ~%.2f 실제 주문 전송", side.upper(), symbol, quantity, price)
        result = self.client.create_order(symbol, "market", side, quantity)
        filled_price = float(result.get("average") or price)
        return Order(symbol, side, quantity, filled_price, status=result.get("status", "unknown"))
