"""실적 발표 후 표류(PEAD) — 가설 우선 후보 2호 (2026-08-23 수집 라운드).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 후보가 링에 서는 근거는 백테스트 성적이 아니라 **가설**이다.

    무엇:   좋은 실적 발표에 시장이 **덜 반응**하고, 가격이 그 방향으로
            몇 주에 걸쳐 마저 움직인다(발라·브라운 1968 이래 문서화).
    왜:     ① 정보가 모두에게 같은 속도로 스며들지 않는다 — 발표문을
              그날 다 소화하는 사람은 소수다.
            ② 큰 기관은 원하는 물량을 하루에 못 산다 — 시장충격을 피해
              **며칠에 걸쳐 나눠 집행**하고, 그 동안 가격에 둔감한 매수가
              이어진다.

    가설이 참이라면 나타날 패턴: 발표일에 크게 오른 종목이 그 뒤 몇 주 더
    오른다. 참이 아니라면(이미 차익거래로 소멸했다면) 오디션에서 진다 —
    그 기각도 기록이다.

⚠️ 바깥에서 회자되는 성적(분기당 몇 %니 하는 숫자들)은 여기 적지 않는다 —
   전략을 파는 쪽이 고른 표본이다(생존 편향). 이 규칙이 우리 종목·우리
   기간에서 통하는지는 오디션만 답한다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

규칙(전부 그날까지의 정보):

    발표일(earn_day=1)의 당일 수익률 > min_jump(기본 +2%)
      → 그 봉 마감부터 hold_days(기본 20봉) 보유, 이후 청산
    발표 반응이 작거나 음수면 관망(롱 전용 — 숏 표류는 공매도 비용·제약이
    커서 원문 효과의 절반이 실전에서 사라지는 쪽이다)

재료: 발표일 컬럼(earn_day)은 파이프라인이 **주간 갱신 캐시**에서 붙인다
(state/earnings.json — 실측 2026-08-23: 미국 종목당 25건, 2020~2026 전 구간).
컬럼이 없는 시장(한국·코인 — 캘린더가 야후에서 안정적이지 않다)은 전부
관망한다. 0으로 지어내지 않는다 — "발표가 없었다"와 "몰랐다"는 다르다.

정직한 한계:
  · 실적 서프라이즈의 원문 정의는 '예상치 대비'지만 예상치 데이터는 유료다.
    **발표일 당일 가격 반응**을 대용치로 쓴다 — 시장이 그날 이미 판정한
    서프라이즈다. 대용치라는 사실을 숨기지 않는다.
  · 발표일 캐시가 비면 그 종목은 조용히 관망이 된다 — 그 상태는 피처
    건강(calendar_health)이 따로 센다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class PEADStrategy(Strategy):
    name = "pead"

    def __init__(self, min_jump: float = 0.02, hold_days: int = 20,
                 allow_short: bool = False):
        min_jump, hold_days = float(min_jump), int(hold_days)
        if not (0.0 < min_jump < 0.5 and 1 <= hold_days <= 120):
            raise ValueError(
                f"PEAD 설정이 범위를 벗어났습니다: min_jump={min_jump} "
                f"hold_days={hold_days}")
        self.min_jump = min_jump
        self.hold_days = hold_days
        # 롱 전용 — 숏 표류는 공매도 제약으로 실전 재현이 안 된다.
        self.allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        n = len(df)
        out = np.zeros(n)
        if "earn_day" not in df.columns or n < 2:
            # 발표일을 모르는 시장 — 전부 관망. 0으로 지어내지 않는다.
            return self._finalize(pd.Series(out, index=df.index), df.index)
        close = df["close"].astype(float).to_numpy()
        earn = df["earn_day"].to_numpy()
        ret = np.empty(n)
        ret[0] = 0.0
        ret[1:] = close[1:] / close[:-1] - 1.0
        left = 0
        for i in range(n):
            # 발표일 마감 시점 — 당일 반응은 이미 관측된 값이다(선견 아님)
            if i > 0 and earn[i] > 0 and ret[i] > self.min_jump:
                left = self.hold_days
            elif left > 0:
                left -= 1
            out[i] = 1.0 if left > 0 else 0.0
        return self._finalize(pd.Series(out, index=df.index), df.index)
