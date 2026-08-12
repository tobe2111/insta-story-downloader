"""멀티 타임프레임 확인 필터 — 상위 시간봉 추세와 일치할 때만 매매한다.

단일 시간봉 신호는 상위 추세를 거스르는 '역추세 진입'을 자주 낸다. 상위
시간봉(예: 일봉 전략이면 주봉)의 추세 방향과 일치하는 신호만 남기면 승률과
신호 품질이 개선되는 경우가 많다.

룩어헤드 방지: 상위 시간봉 값은 '직전에 완성된 봉'만 사용한다(shift). 진행
중인 상위 봉(미래 정보 포함)은 절대 쓰지 않는다.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class MultiTimeframeFilter(Strategy):
    name = "mtf"

    def __init__(self, base: Strategy, htf: str = "W", trend_window: int = 10):
        """base 신호를 상위 시간봉(htf) 추세로 게이팅한다.

        htf         : pandas resample 규칙 (예: 'W' 주봉, '4H', 'M' 월봉)
        trend_window: 상위 시간봉에서 추세를 판정할 이동평균 길이
        """
        self.base = base
        self.htf = htf
        self.trend_window = trend_window
        self.allow_short = base.allow_short

    def _htf_uptrend(self, close: pd.Series) -> pd.Series:
        """상위 시간봉 상승추세 여부(1/0)를 하위 인덱스에 정렬해 반환한다.

        ⚠️ 예전에는 `resample(htf)` 뒤에 `shift(1)`을 걸었다(감사 166).
           의도는 맞았지만 **지연이 두 배가 됐다.** pandas의 기본 라벨
           위치가 규칙마다 다르기 때문이다:

               'W' · 'ME'  →  label='right'  (봉이 끝나는 날에 라벨)
               '4h' 등 일중 →  label='left'   (봉이 시작하는 시각에 라벨)

           그래서 규칙에 따라 **반대 방향으로** 틀렸다.

           ① 오른쪽 라벨(주봉·월봉)은 이미 '완성 시각'이라, 거기에 shift를
              더하면 상위 봉 하나를 통째로 더 기다린다. 실측(주봉·추세
              3주, 어느 월요일에 폭등):

                  올바른 반응    폭등 7일 뒤
                  실제 반응     폭등 13일 뒤   ← 한 주를 더 쉰다

              이 필터는 **게이트**다. 꺼져 있는 동안 하위 전략의 롱이 전부
              0으로 지워지므로, 새 추세마다 한 주를 더 놓친다는 뜻이다.

           ② 왼쪽 라벨(일중)은 반대로 **미래를 본다.** 00:00~03:00 봉을
              '00:00'이라 부르는데, 그 봉의 종가는 03:00에야 정해진다.
              shift(1)를 한 번 걸어도 그 어긋남이 남는다. 실측(4h 봉,
              02:00에 폭등):

                  기본 라벨   첫 롱 00:00   ← 폭등 **2시간 전**
                  고친 뒤     첫 롱 04:00

              게이트가 오르기 직전에 미리 열리는 것은 백테스트 성적을
              공짜로 올려 준다 — 실전에서는 절대 못 하는 일이다.

           고침: 라벨 위치를 규칙에 맡기지 말고 오른쪽으로 **명시**한다.
           그러면 라벨 시각 = 그 봉이 완성되는 시각이 되어, 아래 ffill이
           저절로 '지금까지 완성된 마지막 상위 봉'을 집는다. shift는 필요
           없어진다. 덤으로 **진행 중인 봉은 라벨이 미래**라서 ffill이
           절대 닿지 못한다 — 룩어헤드가 구조적으로 불가능해진다.
        """
        htf_close = (close.resample(self.htf, label="right", closed="right")
                     .last().dropna())
        htf_ma = htf_close.rolling(self.trend_window).mean()
        up = (htf_close > htf_ma).astype(float)
        return up.reindex(close.index, method="ffill").fillna(0.0)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        up = self._htf_uptrend(df["close"])

        pos = base_sig.copy()
        # 상위 추세가 상승이 아니면 롱 금지, 하락이 아니면(=상승이면) 숏 금지
        pos[(base_sig > 0) & (up <= 0.0)] = 0.0
        pos[(base_sig < 0) & (up >= 1.0)] = 0.0
        return self._finalize(pos, df.index)
