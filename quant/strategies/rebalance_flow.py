"""목표비중 자금의 월말 강제 리밸런싱 — 가설 우선 후보 6호 (2026-08-27).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 후보가 링에 서는 근거는 백테스트 성적이 아니라 **가설**이다.

    누가:   목표 비중이 **규정으로 정해진** 자금 — 연기금, 타깃데이트펀드,
            자산배분(60/40류) 펀드, 위험균형 펀드.
    왜:     달 안에서 어떤 자산이 많이 오르면 그 비중이 목표를 넘는다.
            규정상 정해진 날(대개 월말)에 **되돌려야** 한다. 그때 파는
            이유는 "비싸다고 판단해서"가 아니라 **비중이 넘쳤기 때문**이다.
    그래서: 월중 많이 오른 자산에는 **가격에 둔감한 매도**가, 많이 내린
            자산에는 **가격에 둔감한 매수**가 월말에 몰린다. 그리고 그것은
            정보가 아니라 압력이므로 다음 달 초에 **되돌아온다**.

    가설이 참이라면 나타날 패턴 (둘 다 있어야 한다):
      ① 월말 며칠 구간에서, 그달 많이 오른 자산의 이후 수익률이 낮다.
      ② 그 눌림은 다음 달 초 며칠에 **되돌아온다**(일시적 압력이므로).
    ①만 있고 ②가 없으면 그건 '압력'이 아니라 그냥 추세 반전이고, 이
    가설은 기각된 것이다.

■ 이미 있는 월말 후보(turn_of_month)와 무엇이 다른가

    turn_of_month: 달력만 본다. "월말·월초는 무조건 산다"(무조건 매수).
    이 후보:       **부호가 있다.** 같은 월말이라도 그달 많이 오른 자산은
                   피하고 많이 내린 자산은 산다. 즉 다른 질문이다 —
                   "언제 사는가"가 아니라 "**누가 팔릴 차례인가**".

    그래서 두 후보의 신호는 달력이 겹쳐도 서로 다르다. 겹쳐서 똑같아지면
    오디션의 무효 후보 탐지가 잡아내고 링에서 빠진다.

⚠️ 왜 가설이 있는 후보만 세우는가(2026-08-23 방침, 사장님 승인). 후보를
   심사할 때마다 다중검정 문턱이 올라간다. 이유 없는 패턴은 표본 밖에서
   무너지는 것이 정의상 당연하므로, 문턱 비용만 내고 아무것도 안 남긴다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ ⚠️ 선견(룩어헤드)을 어떻게 0으로 만들었나

"이 봉이 이 달의 **마지막** 거래일인가"는 **미래를 봐야** 안다(다음 봉이
같은 달인지 확인해야 한다). 데이터 끝에 봉을 하나 붙이면 과거 판단이
바뀌는데, 그건 백테스트에서만 좋아 보이는 전형적인 함정이다.

그래서 이 규칙은 **그 봉 자신의 날짜 하나**와 **과거 봉**만 본다:

    · "이 봉이 이 달의 **첫** 봉인가" — 직전 봉의 달과 비교한다(과거).
    · 그 달 시작 직전 종가 — 첫 봉에서 ``close.shift(1)``(과거).
    · 창 구분 — 그 봉의 **달력일**(그 봉 자신).

거칠지만 선견 여지가 0이다. turn_of_month와 같은 원칙이다.

■ 정직한 한계

  · 롱 전용이다. 가설의 매도 쪽(넘친 비중을 파는 압력)은 '피한다'로만
    쓴다 — 숏은 조달·차입 비용과 무한손실 위험이 붙어 다른 검증이 필요하고,
    이 저장소의 실계좌는 롱 전용이다.
  · 이 효과는 학계에 알려져 있어 이미 소멸했을 수 있다. 그걸 판정하는 것이
    오디션의 일이다. 바깥에서 회자되는 성적은 근거로 쓰지도 적지도 않는다
    (생존 편향).
  · 자산배분 펀드가 실제로 담는 자산(주가지수·채권·금)에서 강하고, 개별
    종목·코인에서는 약할 것이다. 시장마다 다르게 나오는 것 자체가 가설
    검정이다 — 지수형에서만 이기면 가설과 부합한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class RebalanceFlow(Strategy):
    """월말 강제 리밸런싱 압력 — 그달 오른 자산은 피하고, 내린 자산은 산다."""

    name = "rebalance_flow"

    def __init__(self, entry_day: int = 25, exit_day: int = 3,
                 band: float = 0.03, allow_short: bool = False):
        entry_day, exit_day, band = int(entry_day), int(exit_day), float(band)
        if not (exit_day < entry_day and 1 <= exit_day and entry_day <= 31):
            raise ValueError(
                "압력 구간 시작일은 되돌림 구간 종료일보다 커야 합니다"
                f"(달력일 기준): entry_day={entry_day} exit_day={exit_day}")
        if band <= 0:
            raise ValueError(
                "band는 양수여야 합니다 — 0이면 '많이 올랐다'의 기준이 없어져 "
                f"잡음 한 톨에도 방향이 뒤집힙니다: {band}")
        self.entry_day = entry_day
        self.exit_day = exit_day
        self.band = band
        # 가설의 매도 쪽은 '피한다'로만 쓴다(위 정직한 한계 참조).
        self.allow_short = bool(allow_short)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = pd.to_numeric(df["close"], errors="coerce")
        idx = pd.DatetimeIndex(df.index)

        # ── 이 달의 첫 봉인가 — **직전 봉**과 비교한다(과거만 본다) ──────
        month_id = idx.year * 12 + idx.month
        first_of_month = pd.Series(month_id, index=idx).diff().fillna(1) != 0

        # 이 달 시작 **직전** 종가 — 달 내내 상수로 들고 간다.
        # 첫 봉에서 close.shift(1)이면 지난달 마지막 종가다(과거).
        anchor = close.shift(1).where(first_of_month).ffill()
        mtd = close / anchor - 1.0                    # 그 봉까지의 월중 수익률

        # 직전 달 **전체** 수익률 — 각 달의 앵커끼리 비교하면 나온다.
        # 이 달 첫 봉 시점에 이미 알 수 있는 값이라 선견이 없다.
        month_anchor = anchor[first_of_month]
        prev_month_ret = (month_anchor.pct_change()
                          .reindex(close.index).ffill())

        day = pd.Series(idx.day, index=idx)
        pressure = day >= self.entry_day        # 월말: 압력이 걸리는 구간
        unwind = day <= self.exit_day           # 월초: 압력이 풀리는 구간

        sig = pd.Series(0.0, index=close.index)
        # ① 압력 구간 — 그달 많이 **내린** 자산에는 규정상 매수가 몰린다.
        #    많이 오른 자산은 팔릴 차례이므로 관망(0)한다.
        sig[pressure & (mtd < -self.band)] = 1.0
        # ② 되돌림 구간 — 지난달 많이 **올라서** 팔렸던 자산의 눌림이 풀린다.
        #    ①만 있고 이게 없으면 그건 압력이 아니라 그냥 추세 반전이다.
        sig[unwind & (prev_month_ret > self.band)] = 1.0
        # 재료가 아직 없는 초반 구간(앵커·직전달 미정)은 관망.
        return sig.where(np.isfinite(mtd.to_numpy()), 0.0).fillna(0.0)
