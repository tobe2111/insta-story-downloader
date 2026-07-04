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
            # 거래소 타임스탬프는 UTC epoch(ms) 기준이다. naive datetime을
            # start.timestamp()로 바꾸면 로컬 시간대가 섞여 since가 어긋나므로,
            # 시간대 정보가 없으면 UTC로 간주해 변환한다.
            since = None
            if start is not None:
                ts = pd.Timestamp(start)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                since = int(ts.timestamp() * 1000)
            raw = self._client.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since, limit=limit
            )
            df = pd.DataFrame(
                raw, columns=["ts", "open", "high", "low", "close", "volume"]
            )
            # unit="ms"는 거래소 epoch(UTC)를 그대로 tz-naive 타임스탬프로 만든다.
            df.index = pd.to_datetime(df["ts"], unit="ms")
            # end가 지정되면 그 이후 봉은 잘라낸다(fetch_ohlcv는 since만 지원).
            # 인덱스는 naive-UTC이므로, end가 tz-aware여도 naive-UTC로 맞춰 비교한다
            # (안 맞추면 'naive vs aware' TypeError → 조용한 합성 폴백이 난다).
            if end is not None:
                end_ts = pd.Timestamp(end)
                if end_ts.tzinfo is not None:
                    end_ts = end_ts.tz_convert("UTC").tz_localize(None)
                df = df[df.index <= end_ts]
            return self._validate(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s 시세 조회 실패(%s). 합성 데이터로 폴백.", symbol, exc)
            return self._fallback(symbol, timeframe, start, end, limit)

    @staticmethod
    def _fallback(symbol, timeframe, start, end, limit) -> pd.DataFrame:
        from quant.data.synthetic import SyntheticDataProvider

        df = SyntheticDataProvider().get_ohlcv(
            symbol, timeframe, start, end, limit
        )
        # '진짜 시세가 아니라 폴백'임을 표식한다. 이 표식이 없으면
        # CachedDataProvider가 더미 데이터를 실제 거래소 키로 디스크에 저장해,
        # 네트워크가 복구된 뒤에도 TTL 동안 가짜 시세를 계속 재사용한다.
        df.attrs["synthetic_fallback"] = True
        return df
