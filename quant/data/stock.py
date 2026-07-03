"""주식 데이터 제공자 (yfinance 기반) — 미국/국내 공용.

국내 종목은 티커에 접미사를 붙인다:
    삼성전자  -> 005930.KS  (KOSPI)
    카카오게임즈 -> 293490.KQ (KOSDAQ)
미국 종목은 접미사 없이 그대로 사용한다 (예: AAPL, TSLA).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from quant.data.base import DataProvider
from quant.utils.logging import get_logger

log = get_logger("data.stock")

# yfinance interval 매핑
_TF_MAP = {"1d": "1d", "1h": "1h", "1wk": "1wk", "1m": "1m", "5m": "5m", "15m": "15m"}


class StockDataProvider(DataProvider):
    """yfinance로 주식 OHLCV를 가져온다. 실패 시 합성 데이터로 폴백."""

    def __init__(self, market: str = "us_stock"):
        # market: 'us_stock' | 'kr_stock' (문서/폴백 용도)
        self.market = market

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        try:
            import yfinance as yf

            interval = _TF_MAP.get(timeframe, "1d")
            period = None if start else _limit_to_period(limit, interval)
            df = yf.download(
                symbol,
                start=start,
                end=end,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            if df is None or df.empty:
                raise ValueError("빈 결과")
            # yfinance는 MultiIndex 컬럼을 반환할 수 있음
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.rename(columns=str.lower)
            return self._validate(df.tail(limit))
        except Exception as exc:  # noqa: BLE001
            log.warning("%s 주식 데이터 조회 실패(%s). 합성 데이터로 폴백.", symbol, exc)
            from quant.data.synthetic import SyntheticDataProvider

            return SyntheticDataProvider(start_price=70_000.0).get_ohlcv(
                symbol, timeframe, start, end, limit
            )


def _limit_to_period(limit: int, interval: str) -> str:
    """대략적인 period 문자열 추정 (일봉 기준)."""
    if interval.endswith("m") or interval == "1h":
        return "60d"
    days = min(limit + 30, 3650)
    if days > 730:
        return "max"
    return f"{days}d"
