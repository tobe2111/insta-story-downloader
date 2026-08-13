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
        # ⚠️ 이 한 줄이 없었다(감사 214). `Strategy.allow_short`의 클래스
        #    기본값이 False라, 숏을 내는 전략을 이 래퍼로 감싸면 `_finalize`가
        #    **숏을 전부 0으로 잘라 버렸다.** 실측: 숏 88봉 → 0봉.
        #    형제 셋(adx·event_guard·liquidity)은 전부 base에서 물려받고
        #    있었고 여기만 빠져 있었다. 오디션에서 이 래퍼를 씌운 변형은
        #    전략의 절반을 잃은 채로 평가되므로, 채택·탈락이 스톱의 효과가
        #    아니라 사라진 숏 때문에 갈렸다.
        self.allow_short = base.allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        close = df["close"].to_numpy(dtype=float)
        w = sig.to_numpy(dtype=float).copy()
        extreme = None         # 보유 중 최고(롱)·최저(숏) 종가
        stopped = False        # 스톱 발동 후 재진입 대기
        side = 0               # 지금 보고 있는 방향(+1 롱 / -1 숏)
        for t in range(len(w)):
            cur = 1 if w[t] > 0 else (-1 if w[t] < 0 else 0)
            if cur == 0 or cur != side:
                # 신호가 끊겼거나 방향이 뒤집혔다 — 상태를 새로 잡는다.
                # 방향 전환을 리셋으로 보지 않으면, 롱에서 눌린 고점이 숏
                # 구간까지 따라와 엉뚱한 자리에서 스톱이 걸린다.
                extreme, stopped, side = None, False, cur
                if cur == 0:
                    continue
            if stopped:
                w[t] = 0.0                         # inner가 접을 때까지 관망
                continue
            c = close[t]
            if c != c:                             # 시세 결측 — 판단 보류
                continue
            if side > 0:
                extreme = c if extreme is None else max(extreme, c)
                hit = c < extreme * (1.0 - self.trail)
            else:
                # ⚠️ 숏은 **저점 대비 반등**이 손실이다. 예전에는 숏이 아예
                #    이 분기에 오지 못해(위 클립) 스톱 없이 방치됐다 —
                #    '스톱 가드'라는 이름으로 한쪽만 지키고 있었던 셈이다.
                extreme = c if extreme is None else min(extreme, c)
                hit = c > extreme * (1.0 + self.trail)
            if hit:
                stopped = True                     # 되돌림 초과 → 청산
                w[t] = 0.0
        return self._finalize(pd.Series(w, index=df.index), df.index)
