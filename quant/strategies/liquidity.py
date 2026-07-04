"""유동성 필터 — 거래대금이 마른 구간에서는 매매하지 않는다.

아무리 좋은 신호라도 거래대금(가격×거래량)이 적은 종목·구간에 큰돈이 들어가면
슬리피지로 손실이 커진다. 최근 평균 거래대금이 기준(min_dollar_vol)에 못 미치면
신규 진입을 막아(관망) 유동성 위험을 줄인다.

룩어헤드 방지: 현재 봉까지의 '과거' 거래대금 이동평균만 사용한다.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class LiquidityFilter(Strategy):
    name = "liquidity"

    def __init__(self, base: Strategy, window: int = 20,
                 min_dollar_vol: float = 0.0):
        """base 신호를 거래대금 조건으로 게이팅한다.

        window        : 거래대금 이동평균 길이
        min_dollar_vol: 이 값 미만이면 매매 금지(관망). 시장에 맞게 설정.
        """
        self.base = base
        self.window = window
        self.min_dollar_vol = min_dollar_vol
        self.allow_short = base.allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        if self.min_dollar_vol <= 0 or "volume" not in df.columns:
            return self._finalize(base_sig, df.index)

        dollar_vol = (df["close"] * df["volume"]).rolling(self.window).mean()
        allowed = (dollar_vol >= self.min_dollar_vol).astype(float)
        # 데이터 부족(NaN) 구간은 진입 보류(0)
        allowed = allowed.where(dollar_vol.notna(), 0.0)
        return self._finalize(base_sig * allowed, df.index)
