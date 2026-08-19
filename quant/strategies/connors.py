"""코너스 RSI(2) — 추세 안에서만 눌림을 사는 고전 규칙 (2026-08-19 수집 라운드).

래리 코너스가 공개한 단기 평균회귀 규칙이다. 세 줄로 끝난다:

    ① 장기 추세 위에서만 산다        — 종가 > 200일 이동평균
    ② 아주 짧은 RSI가 극단이면 산다  — RSI(2) < 10
    ③ 짧은 이평 위로 오면 판다       — 종가 > 5일 이동평균

⚠️ 왜 이 규칙을 따로 두는가 (중복 검토, 2026-08-19).

    이 저장소에는 이미 RSI 반전(rsi)과 레짐 필터(regime_wrap, 200일선)가
    있고, 오디션 링은 챔피언에 `regime_wrap(trend_window=200)`을 씌운
    도전자를 매일 만든다. 그러니 ①②는 기존 부품의 조합으로 표현된다.

    표현되지 않는 것은 ③이다. 기존 RSI 반전의 청산은 **RSI 중심선(50)
    복귀**이고, 코너스의 청산은 **가격이 5일선 위로 복귀**다 — 지표가
    아니라 가격이 판단 기준이라 같은 진입에서도 나가는 시점이 다르다.
    같은 신호를 내는 후보였다면 오디션의 무효 후보 탐지가 걸러 낼 것이고,
    그 판정도 기록에 남는다. 여기서 미리 단정하지 않는다.

⚠️ 이 규칙은 **미국 지수 일봉**에서 널리 검증됐다고 알려져 있지만, 그
   '알려짐' 자체가 생존 편향의 후보다(잘 된 규칙만 회자된다). 그래서
   여기서도 돈을 받지 않는다 — 오디션이 이 저장소의 종목·기간에서
   챔피언을 이기는지 재고, 이기지 못하면 채택되지 않는다.

정직한 한계: 롱 전용이다(원문도 롱 편향). 진입 문턱을 넘어도 5일선 위로
못 오면 계속 들고 있으므로, 하락 추세 초입에서는 손실이 길어질 수 있다 —
그 위험은 본 계좌의 킬스위치·손절 가드가 별도로 맡는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.strategies.rsi import rsi


class ConnorsRSI2(Strategy):
    name = "connors_rsi2"

    def __init__(self, rsi_period: int = 2, entry: float = 10.0,
                 exit_ma: int = 5, trend_window: int = 200):
        self.rsi_period = int(rsi_period)
        self.entry = float(entry)
        self.exit_ma = int(exit_ma)
        self.trend_window = int(trend_window)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        r = rsi(close, self.rsi_period).to_numpy()
        trend = close.rolling(self.trend_window).mean().to_numpy()
        short = close.rolling(self.exit_ma).mean().to_numpy()
        px = close.to_numpy()

        out = np.zeros(len(df))
        pos = 0.0
        for i in range(len(df)):
            # 워밍업(이평 미정)은 관망 — '모름'을 '조건 충족'으로 읽지 않는다.
            warm = not (trend[i] == trend[i] and short[i] == short[i]
                        and r[i] == r[i])
            if warm:
                pos = 0.0
            elif pos == 0.0:
                # 추세 위 + 단기 과매도에서만 산다(두 조건 모두).
                if px[i] > trend[i] and r[i] < self.entry:
                    pos = 1.0
            elif px[i] > short[i]:      # 가격이 단기선 위로 복귀하면 나간다
                pos = 0.0
            out[i] = pos
        return pd.Series(out, index=df.index)
