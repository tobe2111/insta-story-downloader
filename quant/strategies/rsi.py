"""RSI 평균회귀 전략.

RSI(상대강도지수)가 과매도(기본 30) 아래면 매수, 과매수(기본 70) 위면
청산/숏. 횡보·조정 구간에서 유효하며, 브레이크아웃 전략과 상관이 낮아
앙상블에 넣으면 분산 효과가 좋다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


class RSIReversion(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70,
                 allow_short: bool = False):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        r = rsi(df["close"], self.period)
        signal = pd.Series(index=df.index, dtype=float)
        signal[r < self.oversold] = 1.0
        signal[r > self.overbought] = -1.0
        signal[(r >= 50) & (r <= self.overbought)] = 0.0  # 중립 복귀 시 청산
        signal = signal.ffill().fillna(0.0)
        return self._finalize(signal, df.index)
