"""데이터 제공자 공통 인터페이스.

모든 제공자는 동일한 형태의 OHLCV DataFrame을 반환한다:
    index : pandas.DatetimeIndex (UTC 권장)
    columns: ['open', 'high', 'low', 'close', 'volume']
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class DataProvider(ABC):
    """OHLCV 데이터를 제공하는 추상 기반 클래스."""

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """symbol 의 OHLCV 데이터를 반환한다."""
        raise NotImplementedError

    @staticmethod
    def _validate(df: pd.DataFrame) -> pd.DataFrame:
        """반환 직전 형식을 검증/정규화한다."""
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"OHLCV 컬럼 누락: {missing}")
        df = df[OHLCV_COLUMNS].copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.dropna()
