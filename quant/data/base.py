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
# 가격 컬럼 — 이게 비면 그 봉은 못 쓴다. 거래량은 없어도 봉은 유효하다.
# 지수(^VIX·^TNX)와 환율(KRW=X)은 거래량 자체가 없는 계열이다(감사 163).
PRICE_COLUMNS = ["open", "high", "low", "close"]


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
        # ⚠️ **가격이 없는 봉만 버린다**(감사 163). 예전에는 `dropna()`로
        #    다섯 컬럼 중 하나라도 비면 그 봉을 통째로 지웠다. 그런데
        #    거래량이 없는 계열이 실제로 있다 — 지수(^VIX·^VIX3M·^TNX)와
        #    환율(KRW=X)이 그렇고, 이 시스템은 그 넷을 전부 받는다.
        #
        #    실측(거래량만 없는 120봉 지수 계열):
        #        _validate 통과 후 0봉 · 그런데 source="yfinance"로 '성공'
        #        보조 소스도 안 거치고, 합성 폴백 표식도 안 붙는다
        #
        #    가격이 멀쩡한 봉을 거래량 때문에 지우면 시계열에 구멍이 나고,
        #    그 구멍을 건너뛴 수익률이 하루치인 척 라벨·사이징에 들어간다.
        #    거래량 결측은 그냥 NaN으로 남긴다 — 아래가 다 견딘다:
        #      · 유동성 필터  : dollar_vol NaN → 진입 보류(보수적)
        #      · 시장충격 비용: isfinite 검사에 걸려 0 (컬럼 없을 때와 동일)
        #      · ML 피처      : vol_z가 fillna(0.0)로 흡수
        #    없는 값을 0으로 지어내면 '거래량 0(거래정지)'과 구별이 사라진다.
        return df.dropna(subset=PRICE_COLUMNS)
