"""평균회귀 전략 (Bollinger Band Mean Reversion).

가격이 이동평균 대비 표준편차의 z배 이상 벗어나면 곧 평균으로 돌아온다고
가정한다. 하단 밴드 이탈 시 매수, 중심선 복귀 시 청산.
횡보장에서 유리하고 강한 추세장에서 불리하다 (모멘텀과 상호보완적).

포지션은 경로 의존적(진입 후 중심선 복귀까지 보유)이므로 명시적 상태머신으로
구현한다 — 벡터화된 밴드-터치 방식은 '중심선 청산'을 제대로 표현하지 못한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class MeanReversion(Strategy):
    name = "mean_reversion"

    def __init__(self, window: int = 20, z: float = 2.0, allow_short: bool = False):
        self.window = window
        self.z = z
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        ma = close.rolling(self.window).mean()
        std = close.rolling(self.window).std()
        upper = ma + self.z * std
        lower = ma - self.z * std

        c = close.to_numpy()
        m = ma.to_numpy()
        up = upper.to_numpy()
        lo = lower.to_numpy()

        position = 0
        out = np.zeros(len(df))
        for i in range(len(df)):
            if np.isnan(m[i]):
                out[i] = 0.0
                continue
            if position == 0:
                if c[i] < lo[i]:
                    position = 1            # 과매도 → 매수
                elif c[i] > up[i] and self.allow_short:
                    position = -1           # 과매수 → 숏
            elif position == 1 and c[i] >= m[i]:
                position = 0                # 중심선 복귀 → 롱 청산
            elif position == -1 and c[i] <= m[i]:
                position = 0                # 중심선 복귀 → 숏 청산
            out[i] = float(position)

        return self._finalize(pd.Series(out, index=df.index), df.index)
