"""레짐 필터 — 시장 국면에 따라 매매를 켜고 끈다.

어떤 전략이든 감싸서, '불리한 국면'에서는 강제로 관망(현금)하게 만든다.
경험적으로 최대낙폭을 줄이는 가장 신뢰도 높은 방법 중 하나:

    - 추세 필터: 장기 이동평균 아래(약세장)에서는 강제로 관망(현금).
      롱·숏 신호를 모두 0으로 만들어 대하락장(2008·2022 등)을 '회피'한다.
      ※ 여기서 목표는 하락장 '회피(현금화)'이지 숏으로 '수익화'가 아니다.
        하락장에서 숏을 내고 싶다면 이 필터로 감싸지 말 것(관망시켜 버린다).
    - 변동성 필터: 일간 변동성이 임계치를 넘는 패닉 구간에서는 신규 진입 금지.

'돈을 잃지 않는 것'이 복리의 핵심이다. 100을 벌고 -50%를 맞으면 원점이지만,
낙폭을 -20%로 막으면 회복이 훨씬 쉽다.
"""
from __future__ import annotations

import pandas as pd

from quant.strategies.base import Strategy


class RegimeFilter(Strategy):
    name = "regime"

    def __init__(
        self,
        base: Strategy,
        trend_window: int = 200,
        use_trend: bool = True,
        vol_window: int = 20,
        max_daily_vol: float | None = None,
    ):
        self.base = base
        self.trend_window = trend_window
        self.use_trend = use_trend
        self.vol_window = vol_window
        self.max_daily_vol = max_daily_vol
        self.allow_short = base.allow_short
        # 마지막 봉에서 이 필터가 왜 열렸/닫혔는지 — 설명문이 읽어 간다.
        #
        # ⚠️ 왜 남기는가(2026-08-11 감사 69): 설명문(explain.py)이 같은 조건을
        #    **다시 계산**하고 있었는데, 재계산이 여기와 어긋났다. 특히
        #    MA가 NaN(데이터 부족)일 때 이 필터는 '진입 보류'로 막는데,
        #    설명문의 `px < ma`는 NaN 비교가 False라 "200일선 위(매매 허용)"
        #    이라고 정반대로 말했다. 그 문장이 사이트와 SNS에 "왜 오늘 이
        #    비중인가"의 답으로 나간다. 같은 규칙을 두 곳에 적으면 반드시
        #    어긋난다 — 그래서 판단한 쪽이 결과를 남기고 설명은 읽기만 한다.
        self.last_gate_: dict | None = None

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_sig = self.base.generate_signals(df).reindex(df.index).fillna(0.0)
        allowed = pd.Series(1.0, index=df.index)
        gate: dict = {"open": True, "reason": "필터 없음"}

        if self.use_trend:
            ma = df["close"].rolling(self.trend_window).mean()
            # 약세장(장기MA 아래)에서는 관망(현금)한다 — 롱·숏 신호를 모두 0으로.
            # 데이터 부족(MA=NaN) 구간도 진입 보류. '하락장 회피'가 목적이다.
            blocked = (df["close"] < ma) | ma.isna()
            allowed[blocked] = 0.0
            if len(df):
                last_ma = ma.iloc[-1]
                if last_ma != last_ma:                     # NaN
                    gate = {"open": False, "kind": "trend_unknown",
                            "reason": (f"{self.trend_window}일선 미정"
                                       f"(데이터 {len(df)}봉으로 부족) → "
                                       "레짐 판정 보류, 진입하지 않음")}
                elif bool(blocked.iloc[-1]):
                    gate = {"open": False, "kind": "trend_down",
                            "reason": (f"주가가 {self.trend_window}일선 아래"
                                       "(약세 국면) → 손실 회피를 위해 관망")}
                else:
                    gate = {"open": True, "kind": "trend_up",
                            "reason": f"{self.trend_window}일선 위(매매 허용)"}

        if self.max_daily_vol is not None:
            vol = df["close"].pct_change().rolling(self.vol_window).std()
            hot = vol > self.max_daily_vol
            allowed[hot] = 0.0
            if len(df) and bool(hot.iloc[-1]):
                gate = {"open": False, "kind": "vol_panic",
                        "reason": (f"일간 변동성 {float(vol.iloc[-1]):.2%}가 "
                                   f"한도 {self.max_daily_vol:.2%} 초과"
                                   "(패닉 구간) → 신규 진입 금지")}
        self.last_gate_ = gate

        # allowed ∈ {0,1} 이므로 곱셈만으로 롱·숏을 함께 게이팅한다(불리한 국면의
        # 신호를 방향에 관계없이 0=관망으로 만든다). 이것이 이 필터의 의도된 동작이다.
        return self._finalize(base_sig * allowed, df.index)
