"""이동평균 교차 전략 (Moving Average Crossover).

단기 이동평균이 장기 이동평균을 상향 돌파하면 매수, 하향 돌파하면 청산.
추세추종(trend-following)의 가장 고전적인 형태.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class MovingAverageCross(Strategy):
    name = "ma_cross"

    def __init__(self, fast: int = 20, slow: int = 60, allow_short: bool = False):
        if fast >= slow:
            raise ValueError("fast는 slow보다 작아야 합니다.")
        self.fast = fast
        self.slow = slow
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_ma = df["close"].rolling(self.fast).mean()
        slow_ma = df["close"].rolling(self.slow).mean()
        signal = pd.Series(0.0, index=df.index)
        signal[fast_ma > slow_ma] = 1.0
        signal[fast_ma < slow_ma] = -1.0
        return self._finalize(signal, df.index)
