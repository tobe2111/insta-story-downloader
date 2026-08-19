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
        vol_quantile: float | None = None,
        vol_lookback: int = 252,
    ):
        self.base = base
        self.trend_window = trend_window
        self.use_trend = use_trend
        self.vol_window = vol_window
        self.max_daily_vol = max_daily_vol
        # 변동성 **분위수** 필터(2026-08-19) — 절대 한도(max_daily_vol)는
        # 코인(일 3~5%)과 주식(일 1%)의 체급이 달라 한 값으로 이식이 안 된다.
        # 문턱을 그 시장 자신의 과거 분위수(추적 창)에서 뽑으면 어느 시장에
        # 씌워도 "평소보다 유난히 흔들리는 구간"이라는 같은 뜻이 된다.
        self.vol_quantile = vol_quantile
        self.vol_lookback = vol_lookback
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
            # ⚠️ **'모름'을 두 필터가 정반대로 처리하고 있었다**(감사 206).
            #    추세 쪽은 `| ma.isna()`로 판정 불가를 **막는데**(바로 위,
            #    주석에도 "데이터 부족 구간도 진입 보류"라고 적혀 있다),
            #    변동성 쪽은 `vol > 한도` 하나뿐이라 **NaN이면 통과**했다 —
            #    파이썬에서 NaN과의 비교는 전부 False이기 때문이다.
            #
            #    실측(추세 필터를 끄고 변동성 필터만, 한도 0.5%·실제 1.0%):
            #        판정 불가(워밍업 20봉)  → 신호 살아 있음 20/20
            #        판정 가능 구간          → 신호 살아 있음  0/220
            #    **판정을 못 하는 구간에만 매매가 열려 있었다.**
            #
            #    기본 설정(use_trend=True)에서는 추세 워밍업(200봉)이 변동성
            #    워밍업(20봉)을 덮어 새지 않는다. 즉 지금 새는 곳은 아니고,
            #    **추세 필터를 끄는 순간 조용히 열린다** — 설정을 바꿀 수 있게
            #    만들어 놓고 기본값에만 맞춰 둔 코드는 결함이 예약된 것이다
            #    (감사 204와 같은 형태).
            hot = (vol > self.max_daily_vol) | vol.isna()
            allowed[hot] = 0.0
            if len(df) and bool(hot.iloc[-1]):
                last_vol = vol.iloc[-1]
                if last_vol != last_vol:                   # NaN
                    gate = {"open": False, "kind": "vol_unknown",
                            "reason": (f"변동성 미정({self.vol_window}봉 필요, "
                                       f"데이터 {len(df)}봉) → 판정 보류, "
                                       "진입하지 않음")}
                else:
                    gate = {"open": False, "kind": "vol_panic",
                            "reason": (f"일간 변동성 {float(last_vol):.2%}가 "
                                       f"한도 {self.max_daily_vol:.2%} 초과"
                                       "(패닉 구간) → 신규 진입 금지")}
        if self.vol_quantile is not None:
            vol = df["close"].pct_change().rolling(self.vol_window).std()
            # 문턱 계산 창은 전부 과거다. shift(1): 오늘 변동성이 문턱에
            # 스스로 들어가면 급등한 날 문턱도 같이 올라 판정이 무뎌진다.
            thr = vol.shift(1).rolling(
                self.vol_lookback,
                min_periods=self.vol_lookback // 2).quantile(self.vol_quantile)
            # '모름'(워밍업 NaN)은 보류 — 위 절대 한도 필터가 감사 206에서
            # NaN 통과로 뚫렸던 그 자리와 같은 규칙을 쓴다.
            hot = (vol > thr) | vol.isna() | thr.isna()
            allowed[hot] = 0.0
            if len(df) and bool(hot.iloc[-1]):
                last_vol, last_thr = vol.iloc[-1], thr.iloc[-1]
                if last_vol != last_vol or last_thr != last_thr:   # NaN
                    gate = {"open": False, "kind": "vol_regime_unknown",
                            "reason": (f"변동성 분위수 미정(관측 창 부족, "
                                       f"데이터 {len(df)}봉) → 판정 보류, "
                                       "진입하지 않음")}
                else:
                    gate = {"open": False, "kind": "vol_regime_high",
                            "reason": (f"일간 변동성 {float(last_vol):.2%}가 "
                                       f"이 시장 자신의 최근 상위 "
                                       f"{(1 - self.vol_quantile):.0%} 문턱"
                                       f"({float(last_thr):.2%})을 넘음 → "
                                       "평소보다 유난히 흔들리는 구간, 관망")}
        self.last_gate_ = gate

        # allowed ∈ {0,1} 이므로 곱셈만으로 롱·숏을 함께 게이팅한다(불리한 국면의
        # 신호를 방향에 관계없이 0=관망으로 만든다). 이것이 이 필터의 의도된 동작이다.
        return self._finalize(base_sig * allowed, df.index)
