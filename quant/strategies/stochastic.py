"""스토캐스틱 오실레이터 전략 (Stochastic Oscillator).

최근 N봉 고저 범위에서 종가의 위치(%K)를 0~100으로 나타낸다. 과매도(기본 20)
아래면 매수, 과매수(기본 80) 위면 청산/숏. RSI와 비슷한 평균회귀 계열이지만
고저 범위를 쓰므로 성격이 조금 다르다 — 앙상블 분산에 보탬이 된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class Stochastic(Strategy):
    name = "stochastic"

    def __init__(self, k_period: int = 14, d_period: int = 3,
                 oversold: float = 20, overbought: float = 80,
                 allow_short: bool = False):
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        low_n = df["low"].rolling(self.k_period).min()
        high_n = df["high"].rolling(self.k_period).max()
        rng = (high_n - low_n).replace(0, np.nan)
        k = 100 * (df["close"] - low_n) / rng
        d = k.rolling(self.d_period).mean().fillna(50.0).to_numpy()  # %D로 부드럽게

        # 진입/청산을 포지션 방향에 맞춰 처리하는 상태기계.
        # (기존의 무상태 벡터 로직은 청산 구간이 [50,overbought] 뿐이라, 숏은
        #  %D가 80 아래로 조금만 내려가도 즉시 청산되고 롱만 중심선까지 보유하는
        #  비대칭이 있었다. 롱은 %D≥50, 숏은 %D≤50에서 대칭으로 청산한다.)
        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            v = d[i]
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
