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
        # 시간대 정규화 — 모든 제공자 출력을 'UTC tz-naive'로 통일한다.
        # 제공자마다 tz-aware(yfinance 분봉)/tz-naive(크립토·합성·일봉·거시·심리)로
        # 제각각인데, 이를 섞어 조인(포트폴리오·멀티트레이더)하면 빈 결과나
        # TypeError로 '조용히 거래가 멈추는' 버그가 난다. 여기서 하나로 맞춰 그
        # 클래스의 버그를 원천 차단한다(분봉 CSV 캐시의 tz 왕복 불안정도 방지).
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.dropna()
