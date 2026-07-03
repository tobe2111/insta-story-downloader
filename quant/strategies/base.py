"""전략 공통 인터페이스.

전략은 OHLCV DataFrame을 받아 '목표 포지션 비중(target position)'을
계산하여 반환한다. 값의 의미:
    +1.0  = 자본의 100% 롱(매수)
     0.0  = 현금(관망)
    -1.0  = 자본의 100% 숏(매도)  (숏 미지원 시장에서는 0으로 클립)

실제 주문 수량/금액은 리스크 계층에서 결정한다. 전략은 '방향과 강도'만 담당.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """모든 전략의 기반 클래스."""

    name: str = "base"
    allow_short: bool = False

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """OHLCV -> 목표 포지션 비중 Series (index는 df와 동일)."""
        raise NotImplementedError

    def _finalize(self, signal: pd.Series, index: pd.Index) -> pd.Series:
        """신호를 정규화한다: 결측 채우기 + 숏 클립 + [-1,1] 범위."""
        signal = signal.reindex(index).ffill().fillna(0.0)
        if not self.allow_short:
            signal = signal.clip(lower=0.0)
        return signal.clip(-1.0, 1.0).rename("target")
