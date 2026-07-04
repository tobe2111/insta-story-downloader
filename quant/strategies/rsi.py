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
    out = 100 - 100 / (1 + rs)
    # 손실이 전혀 없는 구간(loss=0)의 정통 RSI는 100(최대 과매수)이다.
    # rs=NaN이 되어 그대로 fillna(50)하면 강한 상승 구간을 '중립'으로 오판하므로,
    # loss==0 & gain>0 인 곳은 100으로 채운 뒤 나머지(워밍업)만 50으로 채운다.
    out = out.mask((loss == 0) & (gain > 0), 100.0)
    return out.fillna(50.0)


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
