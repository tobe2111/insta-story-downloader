"""모멘텀 전략 (Time-series Momentum).

과거 lookback 기간의 수익률이 양(+)이면 매수, 음(-)이면 청산/숏.
"오르던 것은 계속 오른다"는 추세 지속성에 베팅한다. 학계에서 가장 견고하게
검증된 이례현상(anomaly) 중 하나지만, 추세 전환 구간에서 손실이 발생한다.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class Momentum(Strategy):
    name = "momentum"

    def __init__(self, lookback: int = 90, threshold: float = 0.0, allow_short: bool = False):
        self.lookback = lookback
        self.threshold = threshold
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        past_return = df["close"].pct_change(self.lookback)
        signal = pd.Series(0.0, index=df.index)
        signal[past_return > self.threshold] = 1.0
        signal[past_return < -self.threshold] = -1.0
        return self._finalize(signal, df.index)
