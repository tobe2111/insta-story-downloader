"""전략 앙상블 — 여러 전략의 신호를 결합한다.

이것이 실전에서 수익을 견고하게 만드는 핵심 기법 중 하나다. 단일 전략은
특정 시장 국면에서 반드시 부진한 구간이 있지만, 서로 상관이 낮은 전략
(예: 추세추종 + 평균회귀)을 결합하면 한쪽이 부진할 때 다른 쪽이 버텨주어
자본곡선이 매끄러워지고 최대낙폭이 줄어든다 → 장기 복리 개선.

신호 결합 방식: 각 전략의 목표비중을 가중 평균한다. 모든 전략이 롱이면
확신이 크므로 +1에 가깝고, 의견이 갈리면 0 근처로 수렴(자동 리스크 축소).

가중치 산정:
    - 고정(fixed): 사용자가 지정하거나 균등.
    - 역변동성(inverse_vol, 리스크 패리티): 변동성이 큰 전략의 비중을 낮춰
      한 전략이 포트폴리오 위험을 독점하지 못하게 균형을 맞춘다.
    - HRP(hrp, 상관 인지): 역변동성은 전략 '개별' 변동성만 보지만, HRP는 전략
      PnL의 '상관 구조'까지 본다. rsi·stochastic·mean_reversion처럼 사실상
      같은 베팅을 반복하는 전략 가족이 앙상블 위험을 중복 점유하지 못하게
      묶어서 감량한다. quant.portfolio.allocation._hrp_weights 재사용.
    - 적응형(AdaptiveEnsemble): 최근 '위험조정 성과'가 좋은 전략에 소프트맥스로
      비중을 더 준다. 모두 룩어헤드를 피해 한 봉 지연시킨다.

가중 갱신 캐던스(rebalance): 가중치를 rebalance봉마다만 갱신하고 사이에는
직전 값을 유지한다. 이것은 회전율(거래비용) 절감 장치이지 수익 개선 장치가
아니다 — 가중치 미세 변동이 매 봉 소량 매매로 새는 것을 막을 뿐이다.
기본 1 = 매 봉 갱신(기존 동작 그대로).

⚠️ 앙상블도 수익을 보장하지 않는다. 분산은 변동성·낙폭을 줄이는 도구일 뿐,
없는 엣지를 만들어내지는 못한다. 반드시 워크포워드로 검증할 것.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy


def _combine(sigs: list[pd.Series], weights: pd.DataFrame) -> pd.Series:
    """전략 신호들을 (봉별) 가중치로 결합한다. weights 각 행의 합은 1."""
    combined = pd.Series(0.0, index=sigs[0].index)
    for i, sig in enumerate(sigs):
        combined = combined + weights[i].values * sig
    return combined


def _normalize_rows(w: pd.DataFrame, n: int) -> pd.DataFrame:
    """각 행을 합=1로 정규화한다.

    개별 전략의 가중치가 정의되지 않은 칸(NaN/음수)은 0으로 본다. 행 전체가
    퇴화(합≤0)한 구간(워크포워드 워밍업 등)은 균등 가중으로 되돌린다. 이렇게
    하면 결합 가중치는 항상 합=1인 볼록결합이 되어 신호가 개별 신호 범위를
    벗어나지 않는다.
    """
    w = w.clip(lower=0.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rs = w.sum(axis=1)
    good = rs > 0
    out = w.div(rs, axis=0)
    out.loc[~good, :] = 1.0 / n
    return out


def _strategy_pnl(df: pd.DataFrame, sigs: list[pd.Series]) -> pd.DataFrame:
    """전략별 '실현 손익' 행렬 — 직전 봉 신호 × 이번 봉 수익률 (룩어헤드 없음)."""
    rets = df["close"].pct_change().fillna(0.0)
    return pd.DataFrame(
        {i: sigs[i].shift(1).fillna(0.0) * rets for i in range(len(sigs))})


def _rolling_hrp(pnl: pd.DataFrame, lookback: int, rebalance: int) -> pd.DataFrame:
    """전략 PnL 행렬에 HRP 가중을 롤링 적용한다 (allocation.hrp와 동일 패턴).

    시점 t의 가중치는 [t-lookback, t-1] 구간의 PnL만 사용하고(룩어헤드 없음)
    rebalance봉마다 갱신한다. 워밍업 구간은 NaN으로 두어 상위에서
    _normalize_rows가 균등 가중으로 되돌리게 한다.
    """
    from quant.portfolio.allocation import _hrp_weights

    cols = list(pnl.columns)
    out = pd.DataFrame(np.nan, index=pnl.index, columns=cols)
    last = None
    for i in range(len(pnl)):
        if i >= lookback and (last is None or i % max(1, rebalance) == 0):
            last = _hrp_weights(
                pnl.iloc[i - lookback:i]).reindex(cols).fillna(0.0).values
        if last is not None:
            out.iloc[i] = last
    return out


def _hold_weights(wdf: pd.DataFrame, rebalance: int) -> pd.DataFrame:
    """가중치를 rebalance봉마다만 갱신하고 사이에는 직전 값을 유지한다.

    회전율 절감 장치일 뿐이다. 갱신 시점 가중치는 이미 t-1까지의 정보로 계산된
    값이고 이를 앞으로 유지하는 것은 '더 오래된' 정보를 쓰는 것 → 룩어헤드 없음.
    """
    k = int(rebalance)
    if k <= 1:
        return wdf
    held = wdf.copy()
    drop = np.flatnonzero(np.arange(len(held)) % k != 0)
    held.iloc[drop] = np.nan
    return held.ffill()


class StrategyEnsemble(Strategy):
    """고정·역변동성(리스크 패리티)·HRP(상관 인지) 가중으로 신호를 결합한다."""

    name = "ensemble"

    def __init__(
        self,
        strategies: Sequence[Strategy],
        weights: Sequence[float] | None = None,
        allow_short: bool = False,
        weighting: str = "fixed",       # "fixed" | "inverse_vol" | "hrp"
        vol_lookback: int = 60,
        rebalance: int = 1,             # 가중 갱신 주기(봉) — 1 = 매 봉(기존 동작)
    ):
        if not strategies:
            raise ValueError("전략을 하나 이상 지정하세요.")
        if weights is not None and len(weights) != len(strategies):
            raise ValueError("weights 개수가 전략 개수와 다릅니다.")
        self.strategies = list(strategies)
        self.weights = list(weights) if weights is not None else [1.0] * len(strategies)
        self.allow_short = allow_short
        self.weighting = weighting
        self.vol_lookback = vol_lookback
        self.rebalance = max(1, int(rebalance))
        # 진단용: 마지막 generate_signals에서 쓴 봉별 결합 가중치 (컬럼=전략 순번)
        self.last_weights_: pd.DataFrame | None = None

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        n = len(self.strategies)
        sigs = [s.generate_signals(df).reindex(df.index).fillna(0.0)
                for s in self.strategies]

        if self.weighting == "inverse_vol":
            # 각 전략의 '실현 손익' 변동성(룩어헤드 없이 한 봉 지연)
            pnl = _strategy_pnl(df, sigs)
            vol = pnl.rolling(self.vol_lookback).std().shift(1)
            inv = (1.0 / vol.replace(0.0, np.nan))
            # 사용자가 지정한 고정 가중을 사전확률(prior)로 곱한다
            for i in range(n):
                inv[i] = inv[i] * self.weights[i]
            wdf = _hold_weights(_normalize_rows(inv, n), self.rebalance)
        elif self.weighting == "hrp":
            # 상관 인지 가중: 상관 높은 전략 가족(예: rsi·stochastic·mean_reversion
            # 같은 평균회귀 무리)이 위험을 중복 점유하지 못하게 묶어서 감량한다.
            # 갱신 주기는 _rolling_hrp 내부에서 처리(allocation.hrp 패턴).
            raw = _rolling_hrp(_strategy_pnl(df, sigs), self.vol_lookback,
                               self.rebalance)
            for i in range(n):
                raw[i] = raw[i] * self.weights[i]   # 고정 가중 = 사전확률(prior)
            wdf = _normalize_rows(raw, n)
        else:  # fixed — 가중치가 상수이므로 rebalance는 의미 없음(무시)
            total_w = float(sum(self.weights))
            wdf = pd.DataFrame(
                {i: np.full(len(df), self.weights[i] / total_w) for i in range(n)},
                index=df.index)

        self.last_weights_ = wdf
        combined = _combine(sigs, wdf)
        return self._finalize(combined, df.index)


class AdaptiveEnsemble(Strategy):
    """성과 기반 적응형 앙상블 — 최근 잘한 전략에 더 큰 가중치를 준다.

    각 시점의 가중치는 '과거' 실현 성과의 이동통계로 정하며, 룩어헤드를 피하기
    위해 한 봉 지연시킨다. 기본은 **위험조정 성과(Sharpe식: 평균/표준편차)**를
    **소프트맥스**로 배분하고(temperature로 민감도 조절), 선택적으로
    **역변동성(리스크 패리티)**를 곱해 위험 기여를 균형화한다.

    - score="sharpe": 수익의 '일관성'을 보상 → 변동성만 큰 전략의 과대평가 방지.
    - method="softmax": 일시 부진한 분산 전략을 0으로 죽이지 않고 부드럽게 감량.
    - risk_parity=True: 변동성이 큰 전략의 비중을 추가로 낮춘다.
      weighting="hrp"면 개별 변동성 대신 HRP(상관 인지) 가중을 곱해 상관 높은
      전략 가족의 중복 위험 기여까지 감량한다 (기본 "inverse_vol" = 기존 동작).
    - rebalance: 최종 가중을 k봉마다만 갱신 — 회전율 절감용이지 수익 개선
      장치가 아니다. 기본 1 = 매 봉 갱신(기존 동작).

    고정 앙상블보다 국면 변화에 유연하지만, 과거 성과 추종이므로 전환점에서
    한 박자 늦을 수 있다. 만능이 아니라 하나의 도구다.
    """

    name = "adaptive_ensemble"

    def __init__(self, strategies: Sequence[Strategy], lookback: int = 60,
                 allow_short: bool = False, score: str = "sharpe",
                 method: str = "softmax", temperature: float = 8.0,
                 risk_parity: bool = True, weighting: str = "inverse_vol",
                 rebalance: int = 1):
        if not strategies:
            raise ValueError("전략을 하나 이상 지정하세요.")
        self.strategies = list(strategies)
        self.lookback = lookback
        self.allow_short = allow_short
        self.score = score
        self.method = method
        self.temperature = temperature
        self.risk_parity = risk_parity
        self.weighting = weighting      # "inverse_vol" | "hrp" (risk_parity=True일 때)
        self.rebalance = max(1, int(rebalance))
        # 진단용: 마지막 generate_signals에서 쓴 봉별 결합 가중치 (컬럼=전략 순번)
        self.last_weights_: pd.DataFrame | None = None

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        n = len(self.strategies)
        sigs = [s.generate_signals(df).reindex(df.index).fillna(0.0)
                for s in self.strategies]
        # 실현 성과: 직전 봉 신호로 보유했을 때의 이번 봉 손익 (룩어헤드 없음)
        pnl = _strategy_pnl(df, sigs)

        mean = pnl.rolling(self.lookback).mean().shift(1)   # t-1 까지 정보만
        std = pnl.rolling(self.lookback).std().shift(1)
        if self.score == "sharpe":
            raw = mean / std.replace(0.0, np.nan)
        else:  # "return"
            raw = mean
        raw = raw.replace([np.inf, -np.inf], np.nan)

        if self.method == "softmax":
            # 행별 최댓값을 빼 수치 안정화 후 지수화 (temperature로 sharpness 조절)
            z = raw * self.temperature
            z = z.sub(z.max(axis=1), axis=0)
            wdf = np.exp(z)
        else:  # "proportional" — 양의 성과에만 비례 배분
            wdf = raw.clip(lower=0.0)

        if self.risk_parity:
            if self.weighting == "hrp":
                # 상관 인지: 개별 변동성 대신 HRP 가중을 곱해 상관 높은 전략
                # 가족의 중복 위험 기여를 감량한다 (t-1까지의 PnL만 사용).
                wdf = wdf * _rolling_hrp(pnl, self.lookback, self.rebalance)
            else:  # "inverse_vol" — 기존 동작
                inv = 1.0 / std.replace(0.0, np.nan)
                wdf = wdf * inv

        wdf = _hold_weights(_normalize_rows(wdf, n), self.rebalance)
        self.last_weights_ = wdf
        combined = _combine(sigs, wdf)
        return self._finalize(combined, df.index)
