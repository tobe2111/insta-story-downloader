"""ADX 추세강도 필터 (Average Directional Index).

ADX는 '추세가 얼마나 강한가'를 0~100으로 나타낸다(방향은 무관). 추세추종 전략은
횡보장에서 거짓 신호로 손실을 보는데, ADX가 임계치(기본 25) 이상일 때만 매매하도록
게이팅하면 그런 구간을 피할 수 있다. 어떤 전략이든 감싸서 쓴다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.strategies.keltner import average_true_range


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX(추세강도) 시계열을 계산한다."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr = average_true_range(df, period).replace(0, np.nan)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean().fillna(0.0)


class ADXFilter(Strategy):
    name = "adx_filter"

    def __init__(self, base: Strategy, period: int = 14, min_adx: float = 25.0):
        self.base = base
        self.period = period
        self.min_adx = min_adx
        self.allow_short = base.allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        strength = adx(df, self.period)
        allowed = (strength >= self.min_adx).astype(float)  # 추세 강할 때만 매매
        return self._finalize(base_sig * allowed, df.index)
