"""트레일링 스톱 래퍼 — 보유 중 고점 대비 되돌림이 크면 신호를 끊는다.

레짐/이벤트 래퍼와 같은 문법의 세 번째 가드: 다른 전략(inner)의 신호를
받아, 롱 보유 구간에서 종가가 '보유 중 최고 종가' 대비 trail만큼 내려오면
그 자리부터 신호를 0으로 만든다. inner가 스스로 신호를 접을 때까지 재진입도
막는다(스톱 직후 같은 신호로 바로 재진입하면 스톱이 무의미해진다).

⚠️ 스톱은 이익 장치가 아니다 — 추세 전략에서는 되돌림에 털려 수익을 깎는
경우도 흔하다. 그래서 강제 적용이 아니라 오디션 챌린저로만 참전한다:
현재 챔피언을 감싼 변형이 2단계 관문을 통과할 때만 채택된다.
경로 의존 로직이지만 입력이 같으면 출력이 같다(결정적 — verify 재현 가능).
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class TrailingStopGuard(Strategy):
    name = "stop_wrap"

    def __init__(self, base: Strategy, trail: float = 0.10):
        self.base = base
        self.trail = max(0.01, float(trail))

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        close = df["close"].to_numpy(dtype=float)
        w = sig.to_numpy(dtype=float).copy()
        peak = None            # 보유 중 최고 종가
        stopped = False        # 스톱 발동 후 재진입 대기
        for t in range(len(w)):
            if w[t] > 0:
                if stopped:
                    w[t] = 0.0                     # inner가 접을 때까지 관망
                    continue
                peak = close[t] if peak is None else max(peak, close[t])
                if close[t] < peak * (1.0 - self.trail):
                    stopped = True                 # 고점 대비 되돌림 초과 → 청산
                    w[t] = 0.0
            else:
                peak, stopped = None, False        # 신호 종료 → 상태 리셋
        return self._finalize(pd.Series(w, index=df.index), df.index)
