"""터틀 트레이딩 (Turtle Trading) — 리처드 데니스의 공개 규칙 그대로.

⚠️ 왜 이 파일이 생겼나 (2026-08-18, 사장님 제안).

    "터틀의 방식, 터틀 트레이딩 전략 참고하는 것도 좋을 것 같은데"

    좋은 제안이다 — 터틀은 규칙이 **완전히 공개된 결정적** 전략이라
    "모든 결정은 재현 가능해야 한다"는 이 저장소와 궁합이 가장 좋다.
    1983년 리처드 데니스가 "트레이더는 길러질 수 있다"를 증명하려고
    일반인에게 규칙을 가르쳐 실계좌를 맡긴 실험에서 나왔다.

규칙 (사장님이 주신 정리 그대로):
    ① 진입: 직전 종가가 N1일(기본 20) 최고가를 돌파하면 매수
    ② 청산: N2일(기본 10) 최저가 이탈
    ③ 손절: 진입가 − 2×ATR — 터틀의 '영혼'인 N값 손절

이 틀에서 다른 점(정직하게):
    · 원조 터틀의 1% 리스크 포지션 사이징·피라미딩은 여기 없다 — 크기
      결정은 이 시스템의 위험 계층(변동성 타깃·킬스위치)이 **모든 전략에
      공통으로** 담당한다. 전략이 크기까지 정하면 킬스위치와 싸운다.
    · 숏은 기본 꺼짐 — 현물 계좌에는 숏이 없다.
    · 채널·ATR 계산은 현재 봉을 제외(shift)한다 — 룩어헤드 방지.

이 전략은 **도전자로만** 들어간다. 챔피언이 되려면 다른 후보와 똑같이
선발전·결승전(홀드아웃)·검증 3종을 통과해야 한다 — 전설이라는 이유로
심사를 건너뛰면 이 제품의 앞뒤가 안 맞는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
# ATR은 켈트너의 것을 빌린다 — 같은 계산을 두 곳에 적으면 갈라진다.
from quant.strategies.keltner import average_true_range


class TurtleStrategy(Strategy):
    name = "turtle"

    def __init__(self, entry_window: int = 20, exit_window: int = 10,
                 atr_window: int = 20, stop_mult: float = 2.0,
                 allow_short: bool = False):
        self.entry_window = int(entry_window)
        self.exit_window = int(exit_window)
        self.atr_window = int(atr_window)
        self.stop_mult = float(stop_mult)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        upper = df["high"].rolling(self.entry_window).max().shift(1).to_numpy()
        exit_low = df["low"].rolling(self.exit_window).min().shift(1).to_numpy()
        atr = average_true_range(df, self.atr_window).shift(1).to_numpy()
        close = df["close"].to_numpy()

        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        stop = np.nan               # 진입 시점에 고정되는 2N 손절선
        for i in range(n):
            c = close[i]
            if pos > 0:
                # 청산 먼저 — ② 10일 최저 이탈 또는 ③ 2N 손절.
                hit_channel = (not np.isnan(exit_low[i])) and c < exit_low[i]
                hit_stop = (not np.isnan(stop)) and c < stop
                if hit_channel or hit_stop:
                    pos, stop = 0.0, np.nan
            if pos == 0.0 and not np.isnan(upper[i]) and c > upper[i]:
                pos = 1.0
                # 손절선은 **진입 시점의 ATR**로 고정 — 매 봉 다시 재면
                # 변동성이 줄어들 때 손절선이 몰래 따라 올라온다.
                stop = (c - self.stop_mult * atr[i]
                        if not np.isnan(atr[i]) else np.nan)
            out[i] = pos

        return self._finalize(pd.Series(out, index=df.index), df.index)
