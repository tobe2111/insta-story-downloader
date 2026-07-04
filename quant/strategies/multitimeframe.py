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
        """상위 시간봉 상승추세 여부(1/0)를 하위 인덱스에 정렬해 반환한다."""
        htf_close = close.resample(self.htf).last().dropna()
        htf_ma = htf_close.rolling(self.trend_window).mean()
        up = (htf_close > htf_ma).astype(float)
        # 직전에 '완성된' 상위 봉만 사용 → 진행 중인 봉의 미래 정보 차단
        up = up.shift(1)
        return up.reindex(close.index, method="ffill").fillna(0.0)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        up = self._htf_uptrend(df["close"])

        pos = base_sig.copy()
        # 상위 추세가 상승이 아니면 롱 금지, 하락이 아니면(=상승이면) 숏 금지
        pos[(base_sig > 0) & (up <= 0.0)] = 0.0
        pos[(base_sig < 0) & (up >= 1.0)] = 0.0
        return self._finalize(pos, df.index)
