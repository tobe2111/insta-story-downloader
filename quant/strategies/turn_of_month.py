"""월말·월초 효과(turn-of-month) — 가설 우선 후보 1호 (2026-08-23 방침 전환).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 후보가 링에 서는 근거는 백테스트 성적이 아니라 **가설**이다.

    누가:   연금·퇴직연금·적립식 펀드.
    왜:     월급일(대개 월말)에 들어온 적립금을 규정상 정해진 비율로
            사야 하고, 월말 리밸런싱도 달력이 정한 날 해야 한다.
    그래서: 이들은 그날 가격이 싸든 비싸든 산다 — **가격에 둔감한
            매수 수요**가 매달 같은 달력 자리에 몰린다.

    가설이 참이라면 나타날 패턴: 월말 며칠 + 월초 며칠의 수익률이
    나머지 날보다 체계적으로 높다. 참이 아니라면(수요가 분산 집행되거나
    이미 차익거래로 소멸했다면) 이 규칙은 오디션에서 진다 — 그러면
    가설이 기각된 것이고, 그 기각도 기록이다.

⚠️ 왜 가설이 있는 후보만 세우는가(2026-08-23 방침, 사장님 승인). 후보를
   심사할 때마다 다중검정 문턱이 올라간다(실측: 시행 238→373회에 필요
   샤프 2.52→2.61). 이유 없는 패턴은 표본 밖에서 무너지는 것이 정의상
   당연하므로(과적합), 문턱 비용만 내고 아무것도 남기지 않는다. 경제적
   이유가 있는 패턴만 그 비용을 낼 자격이 있다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

규칙(전부 달력, 가격은 안 본다):

    보유: 달력일 ≥ entry_day(기본 25) 또는 달력일 ≤ exit_day(기본 3)
    관망: 그 밖의 날

⚠️ 학술 정의는 "월말 마지막 거래일 + 월초 3거래일"이지만 **거래일**로 재면
   "이 봉이 이 달의 마지막 거래일인가"를 알기 위해 미래 달력(다음 봉이
   같은 달인가)을 봐야 한다. 데이터 색인에서 그것을 읽으면 뒤에 봉을
   붙였을 때 과거 판단이 바뀌는 선견 편향이 된다. 그래서 **그 봉의 날짜
   하나만 보는 달력일 창**으로 정의한다 — 조금 거칠지만 선견 여지가 0이다.

정직한 한계:
  · 롱 전용이다(수급 가설이 매수 쪽이다). allow_short는 받되 쓰지 않는다.
  · 이 효과는 널리 알려져 있어 이미 소멸했을 수 있다 — 그걸 판정하는 것이
    오디션의 일이다. 바깥에서 회자되는 성적은 근거로 쓰지 않는다(생존 편향).
  · 코인은 월급 적립 수요가 주식보다 약할 것이다 — 시장별로 다르게 나오는
    것 자체가 가설 검정이다(주식에서만 이기면 가설과 부합).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class TurnOfMonth(Strategy):
    name = "turn_of_month"

    def __init__(self, entry_day: int = 25, exit_day: int = 3,
                 allow_short: bool = False):
        entry_day, exit_day = int(entry_day), int(exit_day)
        if not (exit_day < entry_day and 1 <= exit_day and entry_day <= 31):
            raise ValueError(
                "월말 진입일은 월초 청산일보다 커야 합니다(달력일 기준): "
                f"entry_day={entry_day} exit_day={exit_day}")
        self.entry_day = entry_day
        self.exit_day = exit_day
        # 수급 가설이 매수 쪽이므로 롱 전용. 교차 전략 계약이 모든 전략에
        # 이 인자를 넘기므로 받되 쓰지 않는다.
        self.allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        day = pd.DatetimeIndex(df.index).day.to_numpy()
        # 그 봉의 날짜 **하나만** 본다 — 색인의 다른 봉(미래 포함)을 보면
        # 뒤에 봉을 붙였을 때 과거 판단이 바뀐다(선견 편향).
        pos = ((day >= self.entry_day) | (day <= self.exit_day)).astype(float)
        return self._finalize(pd.Series(pos, index=df.index), df.index)
