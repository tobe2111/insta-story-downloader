"""레짐 필터 — 시장 국면에 따라 매매를 켜고 끈다.

어떤 전략이든 감싸서, '불리한 국면'에서는 강제로 관망(현금)하게 만든다.
경험적으로 최대낙폭을 줄이는 가장 신뢰도 높은 방법 중 하나:

    - 추세 필터: 장기 이동평균 아래(약세장)에서는 롱을 금지.
      2008, 2022 같은 대하락장을 대부분 회피한다.
    - 변동성 필터: 일간 변동성이 임계치를 넘는 패닉 구간에서는 신규 진입 금지.

'돈을 잃지 않는 것'이 복리의 핵심이다. 100을 벌고 -50%를 맞으면 원점이지만,
낙폭을 -20%로 막으면 회복이 훨씬 쉽다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class RegimeFilter(Strategy):
    name = "regime"

    def __init__(
        self,
        base: Strategy,
        trend_window: int = 200,
        use_trend: bool = True,
        vol_window: int = 20,
        max_daily_vol: float | None = None,
    ):
        self.base = base
        self.trend_window = trend_window
        self.use_trend = use_trend
        self.vol_window = vol_window
        self.max_daily_vol = max_daily_vol
        self.allow_short = base.allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        allowed = pd.Series(1.0, index=df.index)

        if self.use_trend:
            ma = df["close"].rolling(self.trend_window).mean()
            # 약세장(장기MA 아래)에서는 롱 금지. 데이터 부족 구간은 진입 보류.
            allowed[(df["close"] < ma) | ma.isna()] = 0.0

        if self.max_daily_vol is not None:
            vol = df["close"].pct_change().rolling(self.vol_window).std()
            allowed[vol > self.max_daily_vol] = 0.0

        filtered = base_sig * allowed
        # 숏은 약세장에서 오히려 허용하고 싶을 수 있으나, 기본은 보수적으로 게이팅
        if self.allow_short:
            filtered = np.where(allowed.values > 0, base_sig.values, 0.0)
            filtered = pd.Series(filtered, index=df.index)
        return self._finalize(filtered, df.index)
