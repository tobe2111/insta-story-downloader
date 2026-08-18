"""듀얼 스러스트 (Dual Thrust) — 마이클 챌렉(1980년대)의 공개 수식 그대로.

2026-08-18 자동 자료 수집 라운드(사장님 승인: "수집 주기적으로 해")에서
수집. 공개 문서(QuantConnect 전략 라이브러리, fmzquant/strategies 등)에
수식이 완전히 공개된 결정적 전략이라 재현성 원칙과 맞는다. 제품 추출기는
"규칙 대목은 있으나 문장 형식이 아니다"라고 정직하게 반려했으므로,
터틀·차트북 3종과 같은 경로로 수식을 직접 옮기고 검사로 봉인한다.

규칙 (공개 수식 그대로):
    Range   = max(HH − LC, HC − LL)     ← 직전 N일(현재 봉 제외)
              HH=고가 최고, LC=종가 최저, HC=종가 최고, LL=저가 최저
    매수선  = 당일 시가 + K1 × Range
    청산선  = 당일 시가 − K2 × Range
    종가가 매수선 위로 돌파하면 매수, 청산선 아래로 이탈하면 정리.
    K1 < K2면 매수가 어려워지고, K1 > K2면 쉬워진다(공개 문서의 설명).

터틀(N일 최고가 채널 돌파)과 다른 점: 기준이 **당일 시가**이고 돌파 폭이
최근 변동 범위(Range)로 스케일된다 — 채널 위치가 아니라 "오늘 하루가
평소 범위보다 얼마나 세게 움직였나"를 본다.

이 틀에서 다른 점(정직하게):
    · 원문은 반전 시스템(숏 전환)이지만 현물 계좌라 숏은 관망(0)이다.
    · Range 계산은 현재 봉을 제외(shift)한다 — 룩어헤드 방지.
    · Range가 0이면(완전 평탄) 신호를 내지 않는다 — 0 위의 어떤 틱도
      '돌파'가 되는 잡음 신호를 막는다(psar 평탄 시장 감사와 같은 계열).

이 전략은 **도전자로만** 들어간다. 채택은 오디션 심사가 결정한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class DualThrustStrategy(Strategy):
    name = "dual_thrust"

    def __init__(self, window: int = 4, k1: float = 0.5, k2: float = 0.5,
                 allow_short: bool = False):
        self.window = int(window)
        self.k1 = float(k1)
        self.k2 = float(k2)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        w = self.window
        hh = df["high"].rolling(w).max().shift(1)
        lc = df["close"].rolling(w).min().shift(1)
        hc = df["close"].rolling(w).max().shift(1)
        ll = df["low"].rolling(w).min().shift(1)
        rng = np.maximum((hh - lc).to_numpy(), (hc - ll).to_numpy())
        open_ = df["open"].to_numpy()
        close = df["close"].to_numpy()
        buy_line = open_ + self.k1 * rng
        sell_line = open_ - self.k2 * rng

        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            if not np.isfinite(rng[i]) or rng[i] <= 0.0:
                # 워밍업 구간이거나 완전 평탄 시장 — 범위가 없으면 "범위를
                # 넘었다"는 판단 자체가 성립하지 않는다. 잡음을 신호로
                # 승격시키지 않는다.
                out[i] = 0.0
                pos = 0.0
                continue
            if close[i] > buy_line[i]:
                pos = 1.0
            elif close[i] < sell_line[i]:
                pos = -1.0 if self.allow_short else 0.0
            out[i] = pos

        return self._finalize(pd.Series(out, index=df.index), df.index)
