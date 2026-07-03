"""데이터 계층 — 시장별 제공자를 통일된 인터페이스로 제공."""
from __future__ import annotations

from quant.data.base import DataProvider
from quant.data.crypto import CryptoDataProvider
from quant.data.stock import StockDataProvider
from quant.data.synthetic import SyntheticDataProvider

__all__ = [
    "DataProvider",
    "CryptoDataProvider",
    "StockDataProvider",
    "SyntheticDataProvider",
    "get_provider",
]


def get_provider(market: str, **kwargs) -> DataProvider:
    """시장 이름으로 데이터 제공자를 생성한다.

    market: 'crypto' | 'us_stock' | 'kr_stock' | 'synthetic'
    """
    market = market.lower()
    if market == "crypto":
        return CryptoDataProvider(**kwargs)
    if market in ("us_stock", "kr_stock", "stock"):
        return StockDataProvider(market=market, **kwargs)
    if market == "synthetic":
        return SyntheticDataProvider(**kwargs)
    raise ValueError(f"알 수 없는 market: {market}")
