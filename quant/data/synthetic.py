"""합성(가짜) 시세 데이터 제공자.

네트워크가 없거나 결정론적 테스트가 필요할 때 사용한다.
기하 브라운 운동(GBM)으로 가격 경로를 생성한다.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd


def _symbol_seed(symbol: str) -> int:
    """심볼 문자열을 결정론적 정수로 매핑한다.

    파이썬 내장 hash()는 PYTHONHASHSEED 때문에 프로세스마다 값이 달라져
    '재현 가능한' 합성 데이터라는 보장을 깨뜨린다. blake2b로 고정한다.
    """
    digest = hashlib.blake2b(symbol.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % 10_000

from quant.data.base import DataProvider

# 타임프레임 → (봉 길이, pandas 주기 문자열).
#
# ⚠️ **한 dict로 모은다**(감사 203). 예전에는 `_TIMEFRAME_TO_DELTA`와
#    `_TIMEFRAME_TO_FREQ` 둘로 나뉘어 있었고, 한쪽에만 키를 추가하면 조용히
#    갈라진다(㉞). 실제로 **둘 다 `30m`을 빠뜨리고 있었다** — `barclock`은
#    30분봉을 아는데 여기만 몰라서, `--timeframe 30m`을 주면 **아무 말 없이
#    일봉**이 나왔다. 합성은 폴백 경로라, 진짜 시세가 죽은 날 30분봉 전략이
#    일봉을 30분봉인 줄 알고 받는다.
_TIMEFRAMES: dict[str, tuple[timedelta, str]] = {
    "1m": (timedelta(minutes=1), "1min"),
    "5m": (timedelta(minutes=5), "5min"),
    "15m": (timedelta(minutes=15), "15min"),
    "30m": (timedelta(minutes=30), "30min"),
    "1h": (timedelta(hours=1), "1h"),
    "4h": (timedelta(hours=4), "4h"),
    "1d": (timedelta(days=1), "1D"),
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
        # 심볼별로 다른(그러나 재현 가능한) 시드 — 프로세스 간 결정론 보장
        rng = np.random.default_rng(self.seed + _symbol_seed(symbol))
        # ⚠️ **모르는 타임프레임을 일봉으로 떨어뜨리지 않는다**(감사 203).
        #    예전에는 `.get(timeframe, timedelta(days=1))`이라, `30m`이든
        #    오타든 **아무 말 없이 일봉**이 돌아왔다. 받는 쪽은 요청한
        #    타임프레임이라고 믿고 ATR·변동성·라벨을 만든다 — 24배 긴 봉으로.
        #    합성은 폴백 경로라 하필 진짜 시세가 죽은 날 이 일이 벌어진다.
        #    '모름'은 기본값이 아니다(감사 195와 같은 규칙).
        if timeframe not in _TIMEFRAMES:
            raise ValueError(
                f"합성 제공자가 모르는 타임프레임: {timeframe!r} "
                f"(지원: {', '.join(sorted(_TIMEFRAMES))}). 조용히 일봉으로 "
                f"바꾸면 요청한 것과 다른 길이의 봉을 받게 됩니다.")
        delta, freq = _TIMEFRAMES[timeframe]
        periods_per_year = timedelta(days=365) / delta

        n = int(limit)
        if n <= 0:
            raise ValueError(f"봉 수는 1 이상이어야 합니다(받은 값: {limit!r})")
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
