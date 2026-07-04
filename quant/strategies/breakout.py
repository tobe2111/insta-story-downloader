"""돈치안 채널 브레이크아웃 전략 (Donchian Breakout).

최근 N봉 최고가를 상향 돌파하면 매수, 최저가를 하향 이탈하면 청산/숏.
'터틀 트레이딩'으로 유명한 추세추종의 정석. 큰 추세를 놓치지 않는 대신
횡보장에서 잦은 손실(whipsaw)이 발생하므로 레짐 필터와 궁합이 좋다.

진입/청산을 별도 채널로 처리하는 상태기계:
    롱 진입 : 종가 > 최근 window봉 최고가
    롱 청산 : 종가 < 최근 exit_window봉 최저가
    숏 진입 : 종가 < 최근 window봉 최저가            (allow_short)
    숏 청산 : 종가 > 최근 exit_window봉 최고가       (allow_short)

룩어헤드 방지: 채널 계산에 현재 봉을 제외(shift)한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class Breakout(Strategy):
    name = "breakout"

    def __init__(self, window: int = 55, exit_window: int = 20, allow_short: bool = False):
        self.window = window
        self.exit_window = exit_window
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        upper = df["high"].rolling(self.window).max().shift(1).to_numpy()
        lower = df["low"].rolling(self.window).min().shift(1).to_numpy()
        exit_low = df["low"].rolling(self.exit_window).min().shift(1).to_numpy()
        exit_high = df["high"].rolling(self.exit_window).max().shift(1).to_numpy()
        close = df["close"].to_numpy()

        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            c = close[i]
            # 1) 보유 중이면 exit 채널로 청산 먼저 확인
            if pos > 0 and not np.isnan(exit_low[i]) and c < exit_low[i]:
                pos = 0.0
            elif pos < 0 and not np.isnan(exit_high[i]) and c > exit_high[i]:
                pos = 0.0
            # 2) 관망 상태면 진입 채널 돌파 확인
            if pos == 0.0:
                if not np.isnan(upper[i]) and c > upper[i]:
                    pos = 1.0
                elif self.allow_short and not np.isnan(lower[i]) and c < lower[i]:
                    pos = -1.0
            out[i] = pos

        return self._finalize(pd.Series(out, index=df.index), df.index)
