"""볼린저밴드 전략 — 사장님이 공유한 차트 자료(2026-08-18)의 규칙 그대로.

자료가 적은 두 가지 활용법을 각각 전략으로 옮겼다(mode로 선택):

    ① reversion(박스권): "볼린저밴드 하단에서 매수하고 상단에서 매도"
    ② squeeze(수축 돌파): "수축 후 시세가 상방으로 분출되며 상단을
       돌파한다면 급등의 신호로, 일반적으로 매수 신호"
       — 청산은 자료의 같은 절: "중앙선을 하방 이탈하면 매도 시그널"

밴드 정의도 자료 그대로: 20일 이동평균 ± 2×표준편차(N=20, K=2).
계산에 현재 봉을 포함하면 자기 종가로 자기 밴드를 만드는 미세한
룩어헤드가 생기므로 밴드는 직전 봉까지로 만든다(shift).

이 전략은 **도전자로만** 들어간다 — 자료에 실렸다는 이유로 심사를
건너뛰지 않는다. 이기면 챔피언이 된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class BollingerStrategy(Strategy):
    name = "bollinger"

    def __init__(self, window: int = 20, k: float = 2.0,
                 mode: str = "reversion", allow_short: bool = False):
        if mode not in ("reversion", "squeeze"):
            raise ValueError(f"모르는 mode: {mode} (reversion|squeeze)")
        self.window = int(window)
        self.k = float(k)
        self.mode = mode
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        mid = close.rolling(self.window).mean().shift(1)
        sd = close.rolling(self.window).std().shift(1)
        upper = (mid + self.k * sd).to_numpy()
        lower = (mid - self.k * sd).to_numpy()
        mid_np = mid.to_numpy()
        c = close.to_numpy()

        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            if np.isnan(mid_np[i]):
                out[i] = pos
                continue
            if self.mode == "reversion":
                # ① 하단 이탈에서 매수, 상단 도달에서 청산 — 박스권 왕복.
                if pos == 0.0 and c[i] < lower[i]:
                    pos = 1.0
                elif pos > 0 and c[i] > upper[i]:
                    pos = 0.0
            else:
                # ② 상단 돌파에서 매수, 중앙선 하방 이탈에서 청산.
                if pos == 0.0 and c[i] > upper[i]:
                    pos = 1.0
                elif pos > 0 and c[i] < mid_np[i]:
                    pos = 0.0
            out[i] = pos

        return self._finalize(pd.Series(out, index=df.index), df.index)
