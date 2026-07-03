"""평균회귀 전략 (Bollinger Band Mean Reversion).

가격이 이동평균 대비 표준편차의 z배 이상 벗어나면 곧 평균으로 돌아온다고
가정한다. 하단 밴드 이탈 시 매수, 중심선 복귀 시 청산.
횡보장에서 유리하고 강한 추세장에서 불리하다 (모멘텀과 상호보완적).
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class MeanReversion(Strategy):
    name = "mean_reversion"

    def __init__(self, window: int = 20, z: float = 2.0, allow_short: bool = False):
        self.window = window
        self.z = z
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma = df["close"].rolling(self.window).mean()
        std = df["close"].rolling(self.window).std()
        upper = ma + self.z * std
        lower = ma - self.z * std

        signal = pd.Series(index=df.index, dtype=float)
        signal[df["close"] < lower] = 1.0   # 과매도 -> 매수
        signal[df["close"] > upper] = -1.0  # 과매수 -> 숏/청산
        signal[(df["close"] >= ma) & (signal.shift().fillna(0) > 0)] = 0.0
        # 중심선 복귀 시 롱 청산, 나머지는 직전 상태 유지
        signal = signal.ffill().fillna(0.0)
        return self._finalize(signal, df.index)
