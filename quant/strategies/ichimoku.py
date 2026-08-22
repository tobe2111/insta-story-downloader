"""일목균형표 전략 — 사장님이 공유한 차트 자료(2026-08-18)의 괘선 정의 그대로.

엘리엇 파동과 달리 일목균형표는 **전부 수식**이다 — 그래서 재현 가능하고
이 시스템에 들어올 수 있다:

    전환선   = (최근 9일 최고가 + 최근 9일 최저가) / 2
    기준선   = (최근 26일 최고가 + 최근 26일 최저가) / 2
    선행스팬1 = (전환선 + 기준선) / 2 를 26일 앞에 기입
    선행스팬2 = (최근 52일 최고가 + 최저가) / 2 를 26일 앞에 기입
    구름     = 선행스팬 1·2 사이 영역

매매 규칙은 자료의 "긍정적인 신호 정리"를 짝지어 옮겼다:
    진입: 전환선이 기준선 위(호전)이고 종가가 구름 위
    청산: 전환선이 기준선 아래로 역전되거나 종가가 구름 아래로 이탈

구름은 26일 **앞에** 기입되므로, 오늘 종가와 비교하는 구름은 26일 전에
계산된 값이다 — 선행스팬을 뒤로 밀어(shift) 그대로 재현했고, 미래
값을 미리 보는 자리가 없다. 시간론·형보론처럼 수식이 아닌 부분은
옮기지 않았다(옮기면 반쪽 왜곡이 된다).

이 전략도 **도전자로만** 들어간다 — 유명하다는 이유로 심사를 건너뛰지
않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class IchimokuStrategy(Strategy):
    name = "ichimoku"

    def __init__(self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52,
                 shift: int = 26, allow_short: bool = False):
        self.tenkan = int(tenkan)
        self.kijun = int(kijun)
        self.senkou_b = int(senkou_b)
        self.shift = int(shift)
        self.allow_short = allow_short

    @staticmethod
    def _mid(df: pd.DataFrame, n: int) -> pd.Series:
        return (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2.0

    def cloud(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """오늘 자리에서 **보이는** 구름(위·아래).

        검사에서 숫자로 확인할 수 있게 밖으로 뺐다(2026-08-19). 예전에는
        구름이 generate_signals 안에만 있어서, 검사가 "소스에 shift가
        있나"를 글자로 훑는 수밖에 없었다 — 선행스팬 두 줄 중 하나에서만
        shift를 빼도 나머지 한 줄 덕분에 그 글자 검사는 통과했다.
        """
        tenkan = self._mid(df, self.tenkan)
        kijun = self._mid(df, self.kijun)
        # 선행스팬은 26일 앞에 기입된다 — 오늘 자리에서 보이는 구름은
        # 26일 전에 계산된 값이므로 shift(+26)로 뒤로 민다.
        span_a = ((tenkan + kijun) / 2.0).shift(self.shift)
        span_b = self._mid(df, self.senkou_b).shift(self.shift)
        both = pd.concat([span_a, span_b], axis=1)
        return both.max(axis=1), both.min(axis=1)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        tenkan = self._mid(df, self.tenkan)
        kijun = self._mid(df, self.kijun)
        top, bot = self.cloud(df)
        cloud_top = top.to_numpy()
        cloud_bot = bot.to_numpy()
        t = tenkan.to_numpy()
        k = kijun.to_numpy()
        c = df["close"].to_numpy()

        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            if np.isnan(cloud_top[i]) or np.isnan(k[i]):
                out[i] = pos
                continue
            bullish = t[i] > k[i]                # 호전(전환선이 기준선 위)
            above = c[i] > cloud_top[i]          # 종가가 구름 위
            below = c[i] < cloud_bot[i]          # 종가가 구름 아래
            if pos == 0.0 and bullish and above:
                pos = 1.0
            elif pos > 0 and (not bullish or below):
                pos = 0.0
            out[i] = pos

        return self._finalize(pd.Series(out, index=df.index), df.index)
