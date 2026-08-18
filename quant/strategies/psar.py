"""파라볼릭 SAR 전략 — 사장님이 공유한 차트 자료(2026-08-18)의 계산식 그대로.

    SAR(내일) = SAR(오늘) + α × (EP − SAR(오늘))
    · EP(극값): 매수 구간에서는 그 구간의 신고가, 매도 구간에서는 신저가
    · α(가속변수): 0.02에서 시작, 극값 갱신 때마다 0.02씩 증가, 최대 0.2
    · 캔들이 SAR을 침범하는 순간 구간이 뒤집히고, SAR은 직전 구간의
      극값에서 다시 시작한다

완전히 결정적인 수식이라 이 시스템의 재현성 원칙과 맞는다. 자료의
정직한 경고도 그대로 새겨 둔다: "횡보 및 변동성이 심한 장에서는
신뢰도가 높지 않다" — 그래서 이것은 채택이 아니라 **도전자**다.
횡보장에서 정말 못 버는지는 오디션이 판정한다.

현물 계좌라 매도 구간은 숏이 아니라 관망(0)으로 옮긴다(allow_short
기본 꺼짐 — 기존 전략들과 같은 규칙).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class ParabolicSAR(Strategy):
    name = "psar"

    def __init__(self, af_step: float = 0.02, af_max: float = 0.2,
                 allow_short: bool = False):
        self.af_step = float(af_step)
        self.af_max = float(af_max)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        n = len(df)
        out = np.zeros(n)
        if n < 3:
            return self._finalize(pd.Series(out, index=df.index), df.index)

        # 첫 구간은 둘째 봉의 방향으로 시작한다 — 임의의 씨앗이 필요하고,
        # 자료도 첫 구간의 정의는 관례에 맡긴다. 이후는 전부 수식이다.
        up = high[1] >= high[0]
        sar = low[0] if up else high[0]
        ep = high[1] if up else low[1]
        af = self.af_step
        for i in range(1, n):
            sar = sar + af * (ep - sar)
            if up:
                # 상승 구간의 SAR은 최근 저가들 위로 올라가지 않는다(관례).
                sar = min(sar, low[i - 1], low[max(0, i - 2)])
                if low[i] < sar:                 # 침범 — 매도 구간으로 반전
                    up, sar, ep, af = False, ep, low[i], self.af_step
                elif high[i] > ep:
                    ep, af = high[i], min(self.af_max, af + self.af_step)
            else:
                sar = max(sar, high[i - 1], high[max(0, i - 2)])
                if high[i] > sar:                # 침범 — 매수 구간으로 반전
                    up, sar, ep, af = True, ep, high[i], self.af_step
                elif low[i] < ep:
                    ep, af = low[i], min(self.af_max, af + self.af_step)
            out[i] = 1.0 if up else (-1.0 if self.allow_short else 0.0)

        return self._finalize(pd.Series(out, index=df.index), df.index)
