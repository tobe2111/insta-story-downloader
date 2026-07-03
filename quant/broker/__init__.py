from quant.broker.base import Broker, Order, Position
from quant.broker.paper import PaperBroker

__all__ = ["Broker", "Order", "Position", "PaperBroker", "get_broker"]


def get_broker(mode: str = "paper", **kwargs) -> Broker:
    """mode: 'paper' | 'crypto_live'"""
    if mode == "paper":
        return PaperBroker(**kwargs)
    if mode == "crypto_live":
        from quant.broker.crypto_live import CryptoLiveBroker

        return CryptoLiveBroker(**kwargs)
    raise ValueError(f"알 수 없는 broker mode: {mode}")
