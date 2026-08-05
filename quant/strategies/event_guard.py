"""이벤트 가드 — FOMC 등 알려진 거시 이벤트 날에는 위험을 줄인다.

어떤 전략이든 감싸서, 이벤트 창(발표일 ± pad_days)에는 신호 크기를
factor 배로 줄인다(기본 0 = 관망). 이벤트 날짜는 몇 년 치가 미리 공개되어
있어 결정적·재현 가능하고, 그래서 과거 검증이 가능하다 — 이 필터는
챔피언/챌린저 관문을 통과할 때만 챔피언이 된다(강제 적용이 아니다).

레짐 필터(regime.py)와 같은 철학: 수익을 올리는 장치가 아니라, 예고된
변동성 이벤트에서 큰 손실을 피하는 장치다.
"""
from __future__ import annotations

import pandas as pd

from quant.events import event_dates
from quant.strategies.base import Strategy


class EventGuard(Strategy):
    name = "event_guard"

    def __init__(self, base: Strategy, pad_days: int = 1, factor: float = 0.0):
        self.base = base
        self.pad_days = int(pad_days)
        # factor ∈ [0,1]: 0=이벤트 창 완전 관망, 0.5=비중 절반 등
        self.factor = min(1.0, max(0.0, float(factor)))
        self.allow_short = base.allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        guarded = event_dates(self.pad_days)
        scale = pd.Series(
            [self.factor if getattr(ix, "date", lambda: None)() in guarded
             else 1.0 for ix in df.index],
            index=df.index)
        return self._finalize(sig * scale, df.index)
