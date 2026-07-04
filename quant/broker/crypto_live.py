"""암호화폐 실거래 브로커 (ccxt 기반 — 100+ 거래소 범용).

ccxt의 통일 인터페이스를 쓰므로 거래소만 바꾸면 대부분의 거래소에서 동작한다.
국내(업비트·빗썸·코인원·코빗)와 해외(바이낸스·바이비트·OKX·바이겟 등) 모두 지원.

⚠️ 실제 자금이 오가는 코드입니다. API 키에는 반드시 '출금 권한을 제외'하고,
   소액으로 충분히 검증한 뒤 사용하세요. 키는 환경변수로만 주입하세요.

환경변수:
    EXCHANGE_API_KEY, EXCHANGE_SECRET            (필수)
    EXCHANGE_PASSWORD                            (OKX·KuCoin·Coinbase·Bitget 등 패스프레이즈 필요 거래소)
    EXCHANGE_QUOTE                               (정산통화, 기본 USDT. 업비트/빗썸은 KRW)
"""
from __future__ import annotations

import os

from quant.broker.base import Broker, Order, Position
from quant.utils.logging import get_logger

log = get_logger("broker.crypto_live")

# 참고용 목록(문서/안내). 실제 지원 여부는 설치된 ccxt 버전이 결정한다.
KOREAN_EXCHANGES = ["upbit", "bithumb", "coinone", "korbit"]
# 패스프레이즈(password)가 필요한 대표 거래소들
PASSPHRASE_EXCHANGES = {"okx", "kucoin", "coinbase", "coinbasepro", "bitget", "kucoinfutures"}


def available_exchanges() -> list[str]:
    """설치된 ccxt가 지원하는 거래소 id 목록(없으면 빈 목록)."""
    try:
        import ccxt
        return list(ccxt.exchanges)
    except Exception:  # noqa: BLE001  # pragma: no cover
        return []


class CryptoLiveBroker(Broker):
    def __init__(self, exchange: str = "binance", quote: str | None = None,
                 client=None, params: dict | None = None):
        self.exchange = exchange
        self.quote = quote or os.getenv("EXCHANGE_QUOTE") or (
            "KRW" if exchange in KOREAN_EXCHANGES else "USDT")
        # client 주입 시 ccxt 초기화를 건너뛴다 (테스트/커스텀 클라이언트용)
        if client is not None:
            self.client = client
            return
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
        cfg = {"apiKey": api_key, "secret": secret, "enableRateLimit": True}
        # 일부 거래소는 패스프레이즈가 필요하다
        password = os.getenv("EXCHANGE_PASSWORD", "")
        if password:
            cfg["password"] = password
        elif exchange in PASSPHRASE_EXCHANGES:
            log.warning("%s 는 보통 EXCHANGE_PASSWORD(패스프레이즈)가 필요합니다.", exchange)
        if params:
            cfg.update(params)
        if not hasattr(__import__("ccxt"), exchange):
            raise ValueError(f"ccxt가 모르는 거래소: {exchange}. "
                             f"available_exchanges()로 확인하세요.")
        self.client = getattr(ccxt, exchange)(cfg)

    def get_cash(self) -> float:
        bal = self.client.fetch_balance()
        return float(bal.get("free", {}).get(self.quote, 0.0))

    def get_position(self, symbol: str) -> Position:
        base = symbol.split("/")[0]
        bal = self.client.fetch_balance()
        qty = float(bal.get("total", {}).get(base, 0.0))
        return Position(symbol, qty, 0.0)

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        log.warning("[LIVE:%s] %s %s %.6f @ ~%.2f 실제 주문 전송",
                    self.exchange, side.upper(), symbol, quantity, price)
        result = self.client.create_order(symbol, "market", side, quantity)
        status = result.get("status", "unknown")
        # 미체결(open)·부분체결을 전량 체결로 꾸며내지 않는다. 거래소가 알려준
        # 값만 신뢰하고, 체결 수량이 없으면 0으로 보고한다(us_live와 동일한 규약).
        # 그래야 RobustBroker가 잔량 재주문/중복 여부를 정확히 판단한다.
        raw_filled = result.get("filled")
        filled_qty = float(raw_filled) if raw_filled not in (None, "") else 0.0
        raw_avg = result.get("average")
        filled_price = float(raw_avg) if raw_avg not in (None, "") else (
            price if filled_qty > 0 else 0.0)
        return Order(symbol, side, quantity, filled_price,
                     status=status, filled_quantity=filled_qty)
