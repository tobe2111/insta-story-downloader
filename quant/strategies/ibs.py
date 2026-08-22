"""내부 봉 강도(IBS) — **종가가 그날 범위의 어디에 앉았는가** (2026-08-22 수집).

공개된 결정적 규칙이고 한 줄로 끝난다:

    IBS = (종가 − 저가) / (고가 − 저가)          → 0(바닥 마감) ~ 1(꼭대기 마감)

    진입: IBS < 0.2   — 그날 밑바닥에서 마감했으면 산다(약세에 산다)
    청산: IBS > 0.8   — 꼭대기에서 마감하면 판다(강세에 판다)

⚠️ 왜 이 규칙을 링에 새로 세우는가 (중복 검토, 2026-08-22).

    이 저장소의 도전자 대부분은 **종가만** 본다(이동평균·RSI·MACD·볼린저).
    터틀·일목·파라볼릭은 고저가를 보지만 **여러 봉에 걸친 극단**을 본다.
    IBS가 보는 것은 다르다 — **하루 안에서 종가가 앉은 위치**다. 같은 종가로
    끝난 두 날이라도, 장중 내내 밀리다 겨우 버틴 날과 종일 오르다 꺾인 날은
    IBS가 정반대다. 기존 부품의 조합으로는 표현되지 않는 정보다.

    그래도 신호가 챔피언과 같다면 오디션의 무효 후보 탐지가 걸러 내고, 그
    판정도 기록에 남는다. 여기서 미리 단정하지 않는다.

⚠️⚠️ **바깥에서 회자되는 성적은 근거로 쓰지 않는다.** 이 규칙을 소개하는
     글들은 대개 전략을 파는 쪽에서 쓴 것이고, 잘 된 시장·잘 된 기간만
     추려 실린다(생존 편향). 그런 숫자는 여기 적지 않는다 — 이 규칙이
     쓸모 있는지는 **우리 종목·우리 기간의 오디션**만 답한다. 도전자는
     돈을 받지 않는다.

정직한 한계:
  · 롱 전용이다(원문도 롱 편향). `allow_short`는 받되 쓰지 않는다.
  · 고가와 저가가 같은 봉(거래 정지·상한가 등)에서는 IBS를 정의할 수 없다.
    그런 날은 **직전 판단을 유지**한다 — 0.5로 채우면 '모른다'가 '중립이라고
    판단했다'로 둔갑한다(이 저장소가 반복해 잡아 온 결함 계열).
  · 평균회귀 규칙이라 추세가 한 방향으로 길게 가는 구간에서는 일찍 팔고
    계속 떨어지는 것을 계속 산다. 그 위험은 본 계좌의 킬스위치·손절
    가드가 별도로 맡는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


def internal_bar_strength(df: pd.DataFrame) -> pd.Series:
    """IBS 계열. 고가=저가인 봉은 NaN — **모르는 것을 0.5로 채우지 않는다.**"""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    rng = high - low
    ibs = (df["close"].astype(float) - low) / rng.where(rng > 0)
    return ibs.clip(0.0, 1.0)


class IBSStrategy(Strategy):
    name = "ibs"

    def __init__(self, entry: float = 0.2, exit: float = 0.8,
                 allow_short: bool = False):
        if not (0.0 < float(entry) < float(exit) < 1.0):
            raise ValueError(
                "IBS 문턱은 0 < entry < exit < 1 이어야 합니다: "
                f"entry={entry} exit={exit}")
        self.entry = float(entry)
        self.exit = float(exit)
        # 롱 전용 규칙이다. 교차 전략 계약이 모든 전략에 이 인자를 넘기므로
        # 받되 쓰지 않는다 — 건너뛴 계약은 아무것도 지키지 못한다.
        self.allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ibs = internal_bar_strength(df).to_numpy()
        n = len(df)
        out = np.zeros(n)
        pos = 0.0
        for i in range(n):
            v = ibs[i]
            # 정의 불가(고가=저가) — 직전 판단을 유지한다.
            # ⚠️ 이 줄을 떼도 **행동은 같다**(변이 시험 2026-08-22):
            #    NaN은 어떤 비교에도 False라 아래 두 갈래를 그냥
            #    지나친다. 그래도 남겨 두는 이유는, 그 성질이
            #    파이썬·넘파이의 조용한 규칙이라 누군가 비교를 마스크로
            #    바꾸거나 fillna를 한 줄 넣는 순간 소리 없이 깨지기
            #    때문이다. 지금 지켜지는 것이 아니라 **앞으로 지켜지길
            #    바라는 것**이므로, 변이 앵커는 여기 걸지 않는다 —
            #    잡히지 않는 앵커는 "지켜지고 있다"는 착각만 남긴다.
            if v != v:
                out[i] = pos
                continue
            if pos == 0.0 and v < self.entry:
                pos = 1.0
            elif pos > 0 and v > self.exit:
                pos = 0.0
            out[i] = pos
        return self._finalize(pd.Series(out, index=df.index), df.index)
