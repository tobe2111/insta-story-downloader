"""FOMC 사전 표류(pre-FOMC drift) — 가설 우선 후보 4호 (2026-08-23, 사장님 지시).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 후보가 링에 서는 근거는 백테스트 성적이 아니라 **가설**이다.

    무엇:   미국 주식의 초과수익이 FOMC 성명 발표 **직전 구간**에
            집중된다는 관측(루카·묀히 2015, 뉴욕 연준 — 발표 전 24시간).
    누가/왜: 발표 일정은 1년 전에 공표된 **모두가 아는 달력**이다.
            불확실성 해소를 앞두고 위험 보상을 요구하는 쪽과, 발표 전
            포지션을 정리해야 하는 쪽(레버리지·리스크 한도 규정)의 매매가
            같은 달력 자리에 몰린다 — 규정이 시키는 **가격에 둔감한 매매**,
            즉 가격이 아니라 달력이 시키는 매매다.

    가설이 참이라면 나타날 패턴: 발표 전 1~2거래일의 수익률이 나머지
    날보다 체계적으로 높다. 참이 아니라면(공표 이후 차익거래로 소멸했다면)
    오디션에서 진다 — 그 기각도 기록이다.

⚠️ 바깥에서 회자되는 성적은 여기 적지 않는다(생존 편향). 원 논문 이후
   이 효과가 약해졌다는 후속 연구도 있다 — 어느 쪽인지는 오디션이 답한다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

규칙(전부 달력, 가격은 안 본다):

    포지션: 그 봉의 날짜 d에 대해 d+1 또는 d+2(달력일)가 FOMC 결정일이면 1
    관망:   그 밖의 날

체결 규약(이번 봉 종가 결정 → 다음 봉 보유)상, D−2·D−1 봉에 선 포지션이
**D−1일과 발표일 D의 수익**을 번다 — 문헌이 말하는 발표 전 구간이다.
일봉이라 '발표 전 24시간'을 정확히 자를 수 없다는 근사는 정직하게 적는다.

정직한 한계:
  · 달력(quant/data/fomc.py)은 2020~2026 정례 일정만 안다. 그 밖의 해는
    전부 관망이 된다 — 달력 수명(FOMC_LAST_YEAR)을 넘긴 데이터가 오면
    경고를 남긴다(조용한 관망은 고장이다).
  · 미국 통화정책 이벤트다 — 미국 주식에서 강하고 다른 시장에서 약하게
    나오는 것 자체가 가설 검정이다.
  · 롱 전용(문헌 방향이 매수 쪽). allow_short는 받되 쓰지 않는다.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.utils.logging import get_logger

log = get_logger("strategy.fomc_drift")


class FOMCDrift(Strategy):
    name = "fomc_drift"

    def __init__(self, allow_short: bool = False):
        # 문헌 방향이 매수 쪽 — 롱 전용. 교차 전략 계약이 모든 전략에
        # 이 인자를 넘기므로 받되 쓰지 않는다.
        self.allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        from quant.data.fomc import FOMC_DECISION_DAYS, FOMC_LAST_YEAR

        idx = pd.DatetimeIndex(df.index)
        pos = np.zeros(len(idx))
        stale = False
        for i, ts in enumerate(idx):
            d = ts.date()
            if d.year > FOMC_LAST_YEAR:
                stale = True
                continue                     # 달력 수명 밖 — 관망(아래 경고)
            # 그 봉의 날짜 **하나만** 본다(+상수 달력) — 선견 여지 0.
            nxt1 = (d + _dt.timedelta(days=1)).isoformat()
            nxt2 = (d + _dt.timedelta(days=2)).isoformat()
            if nxt1 in FOMC_DECISION_DAYS or nxt2 in FOMC_DECISION_DAYS:
                pos[i] = 1.0
        if stale:
            log.warning(
                "FOMC 달력 수명(%d) 밖의 봉이 왔다 — 그 구간은 관망이 된다. "
                "quant/data/fomc.py에 다음 해 일정(연준 공표)을 추가할 것",
                FOMC_LAST_YEAR)
        return self._finalize(pd.Series(pos, index=df.index), df.index)
