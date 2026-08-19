"""슈퍼트렌드 — ATR 밴드 래칫 추세 추종 (일일 수집 라운드, 2026-08-19).

출처: 트레이딩뷰 공식 지표 문서의 공개 수식(수식 자체는 저작권 대상이
아니며 구현은 이 저장소가 직접 작성했다). 가격 중심(hl2)에서 ATR×배수만큼
띄운 밴드를 **래칫**(추세 방향으로만 조이고 절대 되풀리지 않음)으로
관리하고, 종가가 반대 밴드를 넘으면 추세가 뒤집힌다.

기존 링과 무엇이 다른가(중복 검토):
    · PSAR — 가속 계수로 조여드는 점 궤적. 슈퍼트렌드는 변동성(ATR)
      비례 밴드라 조임 속도가 시장 변동성을 따라간다.
    · 터틀/돌파 — N일 고저가 돌파. 슈퍼트렌드는 밴드가 가격을 따라
      래칫으로 끌려오는 추격 손절선에 가깝다.
    · 볼린저 — 표준편차 밴드(평균회귀 용례). 슈퍼트렌드는 추세 유지 장치.

수식(공개 문서 그대로):
    hl2 = (high + low) / 2
    basicUpper = hl2 + mult × ATR(period)      # ATR은 와일더 평활(RMA)
    basicLower = hl2 - mult × ATR(period)
    finalUpper = basicUpper < 직전 finalUpper 또는 직전 종가 > 직전 finalUpper
                 ? basicUpper : 직전 finalUpper           # 하향 래칫
    finalLower = basicLower > 직전 finalLower 또는 직전 종가 < 직전 finalLower
                 ? basicLower : 직전 finalLower           # 상향 래칫
    추세: 직전이 상승이면 종가 < finalLower일 때만 하락 전환(반대도 대칭)

ATR 워밍업('모름') 구간은 관망 — 감사 206의 규칙. 미래 봉은 과거 판정을
바꾸지 못한다(모든 재료가 과거·현재 봉뿐). 도전자로만 서고, 채택은
오디션이 결정한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class SuperTrendStrategy(Strategy):
    name = "supertrend"

    def __init__(self, period: int = 10, mult: float = 3.0,
                 allow_short: bool = False):
        self.period = int(period)
        self.mult = float(mult)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        h = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        c = df["close"].to_numpy(dtype=float)
        n = len(df)
        out = np.zeros(n)
        if n < self.period + 2:
            return self._finalize(pd.Series(out, index=df.index), df.index)

        prev_c = np.concatenate([[c[0]], c[:-1]])
        tr = np.maximum(h - low,
                        np.maximum(np.abs(h - prev_c), np.abs(low - prev_c)))
        # 와일더 평활(RMA) — 트레이딩뷰 ATR과 같은 정의. 완전 결정적.
        atr = pd.Series(tr).ewm(alpha=1.0 / self.period,
                                adjust=False).mean().to_numpy()

        hl2 = (h + low) / 2.0
        up_f = np.nan       # finalUpper
        lo_f = np.nan       # finalLower
        trend_up = False    # ATR이 서기 전에는 판정하지 않는다(관망)
        for i in range(n):
            if i < self.period:                    # 워밍업 — '모름'은 보류
                continue
            bu = hl2[i] + self.mult * atr[i]
            bl = hl2[i] - self.mult * atr[i]
            if np.isnan(up_f):                     # 첫 판정 봉 — 밴드 초기화
                up_f, lo_f = bu, bl
                trend_up = c[i] > up_f
            else:
                # 래칫 — 밴드는 추세 방향으로만 조여든다. 이 두 줄이 이
                # 지표의 정체다: 되풀리는 밴드는 추격 손절선이 아니다.
                up_f = bu if (bu < up_f or c[i - 1] > up_f) else up_f
                lo_f = bl if (bl > lo_f or c[i - 1] < lo_f) else lo_f
                if trend_up:
                    trend_up = c[i] >= lo_f        # 하단을 깨야만 하락 전환
                else:
                    trend_up = c[i] > up_f         # 상단을 넘어야 상승 전환
            if trend_up:
                out[i] = 1.0
            elif self.allow_short:
                out[i] = -1.0
        return self._finalize(pd.Series(out, index=df.index), df.index)
