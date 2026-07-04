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
        r = rsi(df["close"], self.period).to_numpy()

        # 진입/청산을 포지션 방향에 맞춰 처리하는 상태기계.
        # (기존 무상태 벡터 로직은 청산 구간이 [50,overbought] 뿐이라, 숏은 RSI가
        #  과매수선(70) 아래로 조금만 내려가도 즉시 청산되고 롱만 중심선(50)까지
        #  보유하는 비대칭이 있었다. stochastic·mean_reversion과 동일하게 롱은
        #  RSI≥50, 숏은 RSI≤50에서 대칭으로 청산한다.)
        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            v = r[i]
            if pos == 0.0:
                if v < self.oversold:
                    pos = 1.0
                elif self.allow_short and v > self.overbought:
                    pos = -1.0
            elif pos > 0 and v >= 50:      # 롱: 중심선 복귀 시 청산
                pos = 0.0
            elif pos < 0 and v <= 50:      # 숏: 중심선 복귀 시 청산(대칭)
                pos = 0.0
            out[i] = pos
        return self._finalize(pd.Series(out, index=df.index), df.index)
