"""합성(가짜) 시세 데이터 제공자.

네트워크가 없거나 결정론적 테스트가 필요할 때 사용한다.
기하 브라운 운동(GBM)으로 가격 경로를 생성한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from quant.data.base import DataProvider

_TIMEFRAME_TO_DELTA = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

# pandas 주기 문자열 (timestamp floor + date_range 용)
_TIMEFRAME_TO_FREQ = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}


class SyntheticDataProvider(DataProvider):
    """GBM 기반 합성 OHLCV 생성기."""

    def __init__(
        self,
        seed: int = 42,
        start_price: float = 100.0,
        annual_drift: float = 0.08,
        annual_vol: float = 0.6,
    ):
        self.seed = seed
        self.start_price = start_price
        self.annual_drift = annual_drift
        self.annual_vol = annual_vol

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        # 심볼별로 다른(그러나 재현 가능한) 시드
        rng = np.random.default_rng(self.seed + (hash(symbol) % 10_000))
        delta = _TIMEFRAME_TO_DELTA.get(timeframe, timedelta(days=1))
        periods_per_year = timedelta(days=365) / delta

        n = int(limit)
        dt = 1.0 / periods_per_year
        mu, sigma = self.annual_drift, self.annual_vol

        # 로그수익률
        shocks = rng.normal(
            (mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), size=n
        )
        close = self.start_price * np.exp(np.cumsum(shocks))

        # OHLC를 종가 기준으로 그럴듯하게 구성
        intrabar = np.abs(rng.normal(0, sigma * np.sqrt(dt) * 0.5, size=n))
        open_ = np.empty(n)
        open_[0] = self.start_price
        open_[1:] = close[:-1]
        high = np.maximum(open_, close) * (1 + intrabar)
        low = np.minimum(open_, close) * (1 - intrabar)
        volume = rng.uniform(1_000, 10_000, size=n)

        # end를 주기 경계로 내림하여, 호출 시각(마이크로초)에 관계없이 여러 종목의
        # 인덱스가 동일한 격자를 공유하도록 한다 (포트폴리오 정렬에 필수).
        freq = _TIMEFRAME_TO_FREQ.get(timeframe, "1D")
        end_ts = pd.Timestamp(end or datetime.utcnow()).floor(freq)
        idx = pd.date_range(end=end_ts, periods=n, freq=freq)

        df = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=idx,
        )
        return self._validate(df)
