from quant.broker.base import Broker, Order, Position
from quant.broker.paper import PaperBroker
from quant.broker.retry import RobustBroker
from quant.broker.specs import MarketSpec, from_ccxt_market

__all__ = [
    "Broker", "Order", "Position", "PaperBroker", "RobustBroker",
    "MarketSpec", "from_ccxt_market", "get_broker",
]


def get_broker(mode: str = "paper", **kwargs) -> Broker:
    """mode: 'paper' | 'crypto_live' | 'us_live' | 'kr_live'

    실거래 브로커는 각각 환경변수로 API 키를 주입해야 한다.
    """
    if mode == "paper":
        return PaperBroker(**kwargs)
    if mode == "crypto_live":
        from quant.broker.crypto_live import CryptoLiveBroker

        return CryptoLiveBroker(**kwargs)
    if mode == "us_live":
        from quant.broker.us_live import AlpacaBroker

        return AlpacaBroker(**kwargs)
    if mode == "kr_live":
        from quant.broker.kr_live import KISBroker

        return KISBroker(**kwargs)
    raise ValueError(f"알 수 없는 broker mode: {mode}")
