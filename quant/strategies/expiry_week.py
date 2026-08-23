"""옵션 만기 주간(expiry week) — 가설 우선 후보 3호 (2026-08-23, 사장님 지시).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 후보가 링에 서는 근거는 백테스트 성적이 아니라 **가설**이다.

    누가:   옵션을 판 딜러·마켓메이커.
    왜:     만기가 다가오면 결제·롤오버·델타 헤지 되감기를 **만기가 정한
            주간**에 해야 한다. 미루면 결제 리스크가 커지므로 그날 가격이
            싸든 비싸든 집행한다 — **가격에 둔감한 매매**가 매달 같은
            달력 자리(셋째 금요일 주)에 몰린다.

    가설이 참이라면 나타날 패턴: 만기 주간의 수익률이 나머지 주보다
    체계적으로 다르다(문헌은 대형주에서 양의 방향을 보고한다 — 헤지
    되감기가 순매수 압력이 되는 쪽). 참이 아니라면(이미 차익거래로
    소멸했다면) 오디션에서 진다 — 그 기각도 기록이다.

⚠️ 바깥에서 회자되는 성적은 여기 적지 않는다 — 전략을 파는 쪽이 고른
   표본이다(생존 편향). 우리 종목·우리 기간의 답은 오디션만 안다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

규칙(전부 달력, 가격은 안 본다):

    보유: 그 봉의 달력일이 [그 달 셋째 금요일 − 4일, 셋째 금요일] 안
          (= 만기 주 월~금. 셋째 금요일은 15~21일이라 항상 같은 달이다)
    관망: 그 밖의 날

셋째 금요일은 그 봉의 연·월에서 **순수 달력 계산**으로 나온다 — 색인의
다른 봉(미래 포함)을 보지 않으므로 선견 여지가 0이다(TOM과 같은 원리).

정직한 한계:
  · 미국 파생 관행(셋째 금요일)이다. 한국 지수옵션 만기는 **둘째 목요일**
    이라 이 달력이 맞지 않는다 — 한국식 달력은 별도 후보로 세울 일이지,
    한 후보에 파라미터로 얹어 시행 수를 몰래 늘리지 않는다.
  · 롱 전용이다(문헌이 보고하는 방향이 매수 쪽이고, 숏 재현은 비용·제약이
    크다). allow_short는 받되 쓰지 않는다.
  · 코인은 파생 만기(분기·월물)가 있지만 달력이 다르다 — 시장별로 결과가
    갈리는 것 자체가 가설 검정이다.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


def third_friday(year: int, month: int) -> int:
    """그 달 셋째 금요일의 달력일(15~21) — 순수 달력 함수."""
    w15 = _dt.date(int(year), int(month), 15).weekday()   # 월=0 … 금=4
    return 15 + (4 - w15) % 7


class ExpiryWeek(Strategy):
    name = "expiry_week"

    def __init__(self, allow_short: bool = False):
        # 문헌이 보고하는 방향이 매수 쪽 — 롱 전용. 교차 전략 계약이 모든
        # 전략에 이 인자를 넘기므로 받되 쓰지 않는다.
        self.allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        idx = pd.DatetimeIndex(df.index)
        years, months, days = idx.year.to_numpy(), idx.month.to_numpy(), \
            idx.day.to_numpy()
        pos = np.zeros(len(idx))
        for i in range(len(idx)):
            tf = third_friday(years[i], months[i])
            # 만기 주 월~금 = [셋째 금요일 − 4, 셋째 금요일]. tf ≥ 15라
            # 주 시작(tf−4 ≥ 11)이 항상 같은 달에 있다 — 월 경계 문제 없음.
            pos[i] = 1.0 if tf - 4 <= days[i] <= tf else 0.0
        return self._finalize(pd.Series(pos, index=df.index), df.index)
