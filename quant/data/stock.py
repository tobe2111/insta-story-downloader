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
            # ⚠️ start '또는' end가 주어지면 범위 모드다. period를 함께 넘기면
            # yfinance가 period를 우선해 start/end를 무시하고 '최근 limit봉'을 주는데,
            # end만 준 워크포워드 요청에서는 요청한 컷오프 이후(미래) 봉이 섞여
            # 룩어헤드가 된다. 범위 모드에선 period를 반드시 None으로 둔다.
            range_mode = start is not None or end is not None
            period = None if range_mode else _limit_to_period(limit, interval)
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
            if range_mode:
                # 범위 모드: 방어적으로 end 이후 봉을 잘라낸다(룩어헤드 차단).
                if end is not None:
                    df = df[df.index <= _align_ts(pd.Timestamp(end), df.index)]
            else:
                # period 모드에서만 최근 limit봉으로 자른다.
                df = df.tail(limit)
            return self._validate(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s 주식 데이터 조회 실패(%s). 합성 데이터로 폴백.", symbol, exc)
            from quant.data.synthetic import SyntheticDataProvider

            return SyntheticDataProvider(start_price=70_000.0).get_ohlcv(
                symbol, timeframe, start, end, limit
            )


def _align_ts(ts: pd.Timestamp, index: pd.Index) -> pd.Timestamp:
    """비교용 타임스탬프를 인덱스의 시간대에 맞춘다(intraday는 tz-aware일 수 있음)."""
    tz = getattr(index, "tz", None)
    if tz is not None and ts.tzinfo is None:
        return ts.tz_localize(tz)
    return ts


def _limit_to_period(limit: int, interval: str) -> str:
    """대략적인 period 문자열 추정 (일봉 기준)."""
    if interval.endswith("m") or interval == "1h":
        return "60d"
    days = min(limit + 30, 3650)
    if days > 730:
        return "max"
    return f"{days}d"
