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

    def __init__(self, base: Strategy, pad_days: int = 1, factor: float = 0.0,
                 include_minor: bool = False):
        self.base = base
        self.pad_days = int(pad_days)
        # factor ∈ [0,1]: 0=이벤트 창 완전 관망, 0.5=비중 절반 등
        self.factor = min(1.0, max(0.0, float(factor)))
        # include_minor: 옵션만기·월말(마이너 캘린더)도 가드에 포함 —
        # 위험 회피용이며, 이 변형도 오디션을 통과해야만 챔피언이 된다.
        self.include_minor = bool(include_minor)
        self.allow_short = base.allow_short
        # 마지막 봉에서 가드가 걸렸는지 — 설명문이 읽어 간다.
        #
        # ⚠️ 왜 남기는가(2026-08-11 감사 70): 설명문이 `is_event_day(d, pad)`로
        #    조건을 **다시 계산**했는데, 그 함수는 주요 이벤트(FOMC 등)만 본다.
        #    include_minor=True면 이 가드는 옵션만기·월말도 막는데, 설명은
        #    "오늘은 주요 이벤트 없음(매매 허용)"이라고 **정반대**로 말했다.
        #    실측: 2026-01-16(옵션만기) 원신호 +1.00 → 가드 후 0.00인데
        #    설명은 매매 허용. 게다가 factor=0.5(절반)인 날에도 설명은
        #    "관망"이라 말해 크기까지 틀렸다. 판단한 쪽이 남긴다.
        self.last_gate_: dict | None = None

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        guarded = set(event_dates(self.pad_days))
        minor: set = set()
        if self.include_minor:
            from quant.events import minor_event_dates
            minor = set(minor_event_dates())
            guarded |= minor
        scale = pd.Series(
            [self.factor if getattr(ix, "date", lambda: None)() in guarded
             else 1.0 for ix in df.index],
            index=df.index)
        if len(df):
            last = getattr(df.index[-1], "date", lambda: None)()
            if last in guarded:
                kind = "주요 이벤트(FOMC 등)" if last not in minor or \
                    last in set(event_dates(self.pad_days)) else "옵션만기·월말"
                how = ("관망" if self.factor <= 0
                       else f"비중 {self.factor:.0%}로 축소")
                self.last_gate_ = {
                    "open": False, "date": str(last),
                    "reason": (f"{kind} 창(±{self.pad_days}일) — "
                               f"변동성 위험을 피해 {how}")}
            else:
                scope = "주요+마이너" if self.include_minor else "주요"
                self.last_gate_ = {
                    "open": True, "date": str(last),
                    "reason": f"오늘은 해당 이벤트 없음({scope} 달력 기준·매매 허용)"}
        return self._finalize(sig * scale, df.index)
