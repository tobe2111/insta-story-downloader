"""가치 닻 — 자기 역사 대비 저평가 구간에서만 보유하는 도전자 (2026-08-19).

사장님이 주신 KIS API 가치투자 사례의 채택. 원 사례는 재무제표로 종목을
**고르는** 크로스섹션 가치투자인데, 이 시스템의 오디션은 종목별 계좌
구조라 그대로 옮길 수 없다. 그래서 같은 발상을 이 구조에 맞게 옮겼다:
"이 종목이 **자기 자신의 역사 대비** 싼 구간에서만 산다."

재료: KRX가 매일 공표하는 PBR(주가/장부가치) — attach_krx_value가 붙이는
val_pbr 컬럼(도전자 전용, 챔피언 동결 무관). PBR이 과거 추적 창의 하위
분위수(기본 40%) 아래면 보유(1), 아니면 관망(0).

정직한 한계:
    · 가치는 느린 신호다 — 몇 달씩 같은 판정이 이어지는 게 정상이고,
      그래서 단기 오디션에서는 챔피언과 신호가 같아 무효 후보(inert)로
      빠지는 날이 많을 것이다. 그건 실패가 아니라 이 전략의 성격이다.
    · 저PBR가 곧 오르는 이유는 아니다(가치 함정). 채택은 언제나처럼
      오디션이 결정하고, 여기서는 재료만 정직하게 제공한다.
    · 재무 데이터가 없는 시장(코인·미국)은 언제나 관망 — supply_som과
      같은 규약("재료가 없는 곳에서는 의견이 없다").
분위수 창은 전부 과거(당일 제외 — shift(1)) — 룩어헤드 없음.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy

VALUE_COL = "val_pbr"


class ValueAnchor(Strategy):
    name = "value_anchor"

    def __init__(self, quantile: float = 0.4, lookback: int = 500,
                 min_obs: int = 120, allow_short: bool = False):
        self.quantile = float(quantile)
        self.lookback = int(lookback)
        self.min_obs = int(min_obs)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        if VALUE_COL not in df.columns:
            # 재무 데이터가 없는 시장 — 의견 없음(관망).
            return self._finalize(pd.Series(0.0, index=df.index), df.index)
        pbr = pd.to_numeric(df[VALUE_COL], errors="coerce")
        thr = pbr.shift(1).rolling(self.lookback,
                                   min_periods=self.min_obs).quantile(
                                       self.quantile)
        # '모름'(워밍업·결측)은 보류 — NaN 비교는 False라 자동으로 관망이
        # 되지만, 규칙을 명시해 둔다(감사 206의 교훈: 모름 통과 금지).
        sig = ((pbr < thr) & pbr.notna() & thr.notna()).astype(float)
        return self._finalize(sig, df.index)
