"""펀딩 과열 회피(funding guard) — 가설 우선 후보 5호 (2026-08-25 수집 라운드).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이 후보가 링에 서는 근거는 백테스트 성적이 아니라 **가설**이다.

    무엇:   무기한 선물의 펀딩비가 극단으로 오른 구간은 레버리지 롱이
            한쪽으로 쏠린 상태다. 그 구간에서는 작은 하락이 강제 청산을
            부르고, 청산이 다시 하락을 부르는 연쇄가 열려 있다.
    누가/왜: **강제 청산은 정의상 가격에 둔감한 매매다** — 청산 엔진은
            가격이 얼마든 팔아야 하고, 파는 쪽이 고를 수 있는 것이 없다.
            그 강제 매도가 몰릴 수 있는 자리(과열 펀딩)를 미리 피한다.

    가설이 참이라면 나타날 패턴: 펀딩 과열 구간의 이후 수익률 분포가
    나머지 구간보다 왼쪽 꼬리(급락)가 두껍고, 그 구간을 비켜선 곡선이
    낙폭에서 이긴다. 참이 아니라면(과열이 그저 강세 신호라면) 오디션에서
    진다 — 그 기각도 기록이다.

⚠️ 바깥에서 회자되는 성적은 여기 적지 않는다(생존 편향). 이 규칙이 우리
   종목·우리 기간에서 통하는지는 오디션만 답한다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

규칙(전부 그날까지의 정보):

    과열 = funding > 지난 window봉 펀딩의 quantile 분위수(자기 자신 제외,
           과거만). 과열이면 관망(0), 아니면 보유(1). 롱 전용.

재료: 'funding' 컬럼은 코인 파이프라인이 거래소에서 받아 스냅샷에 보존한다
(quant/data/funding.py — 이미 붙어 있는 재료라 새 배선이 없다).

정직한 규약:
  · funding 컬럼이 없으면(주식·수집 실패) **전부 관망** — "펀딩이 정상"과
    "몰랐다"는 다르다. 0으로 지어내지 않는다(PEAD의 earn_day와 같은 규약).
  · 분위수를 잴 과거가 window봉만큼 쌓이기 전에도 관망 — 모름은 보수 쪽.
  · 분위수는 **자기 봉을 제외한 과거**로만 계산한다(shift 후 rolling) —
    자기 값을 포함하면 극단값이 자기 문턱을 끌어올려 과열이 자기를 감춘다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


class FundingGuard(Strategy):
    name = "funding_guard"

    def __init__(self, window: int = 180, quantile: float = 0.9,
                 allow_short: bool = False):
        window, quantile = int(window), float(quantile)
        if not (30 <= window <= 2000 and 0.5 < quantile < 1.0):
            raise ValueError(
                f"펀딩 가드 설정이 범위를 벗어났습니다: window={window} "
                f"quantile={quantile}")
        self.window = window
        self.quantile = quantile
        # 가설이 '청산 연쇄 회피'라 롱 전용 — 받되 쓰지 않는다(교차 계약).
        self.allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        n = len(df)
        if "funding" not in df.columns or n < 2:
            # 펀딩을 모르는 시장 — 전부 관망. 0으로 지어내지 않는다.
            return self._finalize(pd.Series(np.zeros(n), index=df.index),
                                  df.index)
        fnd = pd.to_numeric(df["funding"], errors="coerce")
        # 자기 봉 제외 + 과거 window봉의 분위수 — shift(1)이 선견을 막는다.
        thr = fnd.shift(1).rolling(self.window,
                                   min_periods=self.window).quantile(
            self.quantile)
        # 문턱을 못 잰 봉(초기 구간·결측)은 관망 — 모름은 보수 쪽.
        pos = ((fnd <= thr) & thr.notna() & fnd.notna()).astype(float)
        return self._finalize(pos, df.index)
