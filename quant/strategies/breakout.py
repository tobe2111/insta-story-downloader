"""돈치안 채널 브레이크아웃 전략 (Donchian Breakout).

최근 N봉 최고가를 상향 돌파하면 매수, 최저가를 하향 이탈하면 청산/숏.
'터틀 트레이딩'으로 유명한 추세추종의 정석. 큰 추세를 놓치지 않는 대신
횡보장에서 잦은 손실(whipsaw)이 발생하므로 레짐 필터와 궁합이 좋다.

룩어헤드 방지: 채널 계산에 현재 봉을 제외(shift)한다.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class Breakout(Strategy):
    name = "breakout"

    def __init__(self, window: int = 55, exit_window: int = 20, allow_short: bool = False):
        self.window = window
        self.exit_window = exit_window
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        upper = df["high"].rolling(self.window).max().shift(1)
        lower = df["low"].rolling(self.window).min().shift(1)
        exit_low = df["low"].rolling(self.exit_window).min().shift(1)

        signal = pd.Series(index=df.index, dtype=float)
        signal[df["close"] > upper] = 1.0
        signal[df["close"] < lower] = -1.0
        # 롱 보유 중 exit 채널 이탈 시 청산
        signal[df["close"] < exit_low] = 0.0
        signal = signal.ffill().fillna(0.0)
        return self._finalize(signal, df.index)
