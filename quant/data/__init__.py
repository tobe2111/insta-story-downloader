"""데이터 계층 — 시장별 제공자를 통일된 인터페이스로 제공."""
from __future__ import annotations

from quant.data.base import DataProvider
from quant.data.cache import CachedDataProvider
from quant.data.crypto import CryptoDataProvider
from quant.data.sentiment import fear_greed_frame, fear_greed_history
from quant.data.stock import StockDataProvider
from quant.data.synthetic import SyntheticDataProvider

__all__ = [
    "DataProvider",
    "CryptoDataProvider",
    "StockDataProvider",
    "SyntheticDataProvider",
    "CachedDataProvider",
    "fear_greed_history",
    "fear_greed_frame",
    "get_provider",
]


def get_provider(market: str, cached: bool = False, cache_dir: str = "data_cache",
                 ttl_seconds: int = 3600, **kwargs) -> DataProvider:
    """시장 이름으로 데이터 제공자를 생성한다.

    market: 'crypto' | 'us_stock' | 'kr_stock' | 'synthetic'
    cached=True 이면 디스크 캐시로 감싸 반복 요청 시 API 재호출을 줄인다.
    """
    market = market.lower()
    if market == "crypto":
        provider: DataProvider = CryptoDataProvider(**kwargs)
    elif market in ("us_stock", "kr_stock", "stock"):
        provider = StockDataProvider(market=market, **kwargs)
    elif market == "synthetic":
        provider = SyntheticDataProvider(**kwargs)
    else:
        raise ValueError(f"알 수 없는 market: {market}")

    if cached:
        return CachedDataProvider(provider, cache_dir=cache_dir, ttl_seconds=ttl_seconds)
    return provider
