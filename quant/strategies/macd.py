"""MACD 추세 전략.

MACD선(단기EMA - 장기EMA)이 시그널선을 상향 교차하면 매수, 하향 교차하면
청산/숏. 이동평균 교차의 EMA 버전으로 반응이 조금 더 빠르다.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class MACD(Strategy):
    name = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9,
                 allow_short: bool = False):
        if fast >= slow:
            raise ValueError("fast는 slow보다 작아야 합니다.")
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ema_fast = df["close"].ewm(span=self.fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()

        out = pd.Series(0.0, index=df.index)
        out[macd_line > signal_line] = 1.0
        out[macd_line < signal_line] = -1.0
        return self._finalize(out, df.index)
