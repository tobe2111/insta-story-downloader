"""켈트너 채널 브레이크아웃 전략 (Keltner Channel).

EMA 중심선에 ATR(평균실체범위)의 배수로 채널을 만든다. 돈치안(가격 극값)과
달리 ATR로 폭이 정해져 변동성에 자동으로 적응한다 — 조용할 땐 좁고 요동칠 땐
넓어져서 거짓 돌파(whipsaw)를 줄인다. 상단 돌파 시 매수, 하단 이탈 시 청산/숏.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


def average_true_range(df: pd.DataFrame, window: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


class KeltnerBreakout(Strategy):
    name = "keltner"

    def __init__(self, ema_window: int = 20, atr_window: int = 10,
                 mult: float = 2.0, allow_short: bool = False):
        self.ema_window = ema_window
        self.atr_window = atr_window
        self.mult = mult
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ema = df["close"].ewm(span=self.ema_window, adjust=False).mean()
        atr = average_true_range(df, self.atr_window)
        upper = ema + self.mult * atr
        lower = ema - self.mult * atr

        signal = pd.Series(index=df.index, dtype=float)
        signal[df["close"] > upper] = 1.0
        signal[df["close"] < lower] = -1.0
        signal = signal.ffill().fillna(0.0)
        return self._finalize(signal, df.index)
