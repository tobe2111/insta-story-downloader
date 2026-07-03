"""암호화폐 데이터 제공자 (ccxt 기반)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.crypto")


class CryptoDataProvider(DataProvider):
    """ccxt를 통해 거래소 OHLCV를 가져온다 (기본: 바이낸스).

    ccxt 미설치 또는 네트워크 오류 시 SyntheticDataProvider로 폴백한다.
    """

    def __init__(self, exchange: str = "binance", api_key: str = "", secret: str = ""):
        self.exchange_id = exchange
        self._client = None
        try:
            import ccxt  # noqa: F401

            klass = getattr(ccxt, exchange)
            self._client = klass(
                {"apiKey": api_key, "secret": secret, "enableRateLimit": True}
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("ccxt 초기화 실패(%s). 합성 데이터로 폴백합니다.", exc)

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        if self._client is None:
            return self._fallback(symbol, timeframe, start, end, limit)
        try:
            since = int(start.timestamp() * 1000) if start else None
            raw = self._client.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since, limit=limit
            )
            df = pd.DataFrame(
                raw, columns=["ts", "open", "high", "low", "close", "volume"]
            )
            df.index = pd.to_datetime(df["ts"], unit="ms")
            return self._validate(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s 시세 조회 실패(%s). 합성 데이터로 폴백.", symbol, exc)
            return self._fallback(symbol, timeframe, start, end, limit)

    @staticmethod
    def _fallback(symbol, timeframe, start, end, limit) -> pd.DataFrame:
        from quant.data.synthetic import SyntheticDataProvider

        return SyntheticDataProvider().get_ohlcv(
            symbol, timeframe, start, end, limit
        )
