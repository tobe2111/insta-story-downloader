"""전략 앙상블 — 여러 전략의 신호를 결합한다.

이것이 실전에서 수익을 견고하게 만드는 핵심 기법 중 하나다. 단일 전략은
특정 시장 국면에서 반드시 부진한 구간이 있지만, 서로 상관이 낮은 전략
(예: 추세추종 + 평균회귀)을 결합하면 한쪽이 부진할 때 다른 쪽이 버텨주어
자본곡선이 매끄러워지고 최대낙폭이 줄어든다 → 장기 복리 개선.

신호 결합 방식: 각 전략의 목표비중을 가중 평균한다. 모든 전략이 롱이면
확신이 크므로 +1에 가깝고, 의견이 갈리면 0 근처로 수렴(자동 리스크 축소).
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd

from quant.strategies.base import Strategy


class StrategyEnsemble(Strategy):
    name = "ensemble"

    def __init__(
        self,
        strategies: Sequence[Strategy],
        weights: Sequence[float] | None = None,
        allow_short: bool = False,
    ):
        if not strategies:
            raise ValueError("전략을 하나 이상 지정하세요.")
        if weights is not None and len(weights) != len(strategies):
            raise ValueError("weights 개수가 전략 개수와 다릅니다.")
        self.strategies = list(strategies)
        self.weights = list(weights) if weights is not None else [1.0] * len(strategies)
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        total_w = sum(self.weights)
        combined = pd.Series(0.0, index=df.index)
        for strat, w in zip(self.strategies, self.weights):
            sig = strat.generate_signals(df).reindex(df.index).fillna(0.0)
            combined = combined + w * sig
        combined = combined / total_w
        return self._finalize(combined, df.index)


class AdaptiveEnsemble(Strategy):
    """성과 기반 적응형 앙상블 — 최근 잘한 전략에 더 큰 가중치를 준다.

    각 시점의 가중치는 '과거' 실현 성과(전략 신호로 얻었을 수익)의 이동평균으로
    정하며, 룩어헤드를 피하기 위해 한 봉 지연시킨다. 양(+)의 성과를 낸 전략에만
    비중을 배분하고, 모두 부진하면 균등 가중으로 되돌린다.

    고정 앙상블보다 국면 변화에 유연하지만, 과거 성과 추종이므로 전환점에서
    한 박자 늦을 수 있다. 만능이 아니라 하나의 도구다.
    """

    name = "adaptive_ensemble"

    def __init__(self, strategies: Sequence[Strategy], lookback: int = 60,
                 allow_short: bool = False):
        if not strategies:
            raise ValueError("전략을 하나 이상 지정하세요.")
        self.strategies = list(strategies)
        self.lookback = lookback
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        rets = df["close"].pct_change().fillna(0.0)
        sigs, scores = [], {}
        for i, strat in enumerate(self.strategies):
            sig = strat.generate_signals(df).reindex(df.index).fillna(0.0)
            sigs.append(sig)
            # 실현 성과: 직전 봉 신호로 보유했을 때의 이번 봉 손익 (룩어헤드 없음)
            pnl = sig.shift(1).fillna(0.0) * rets
            # 과거 lookback 평균을 한 봉 지연 → 가중치는 t-1 까지 정보만 사용
            scores[i] = pnl.rolling(self.lookback).mean().shift(1).fillna(0.0)

        score_df = pd.DataFrame(scores).clip(lower=0.0)  # 양의 성과만 보상
        row_sum = score_df.sum(axis=1)
        weights = score_df.div(row_sum, axis=0)
        # 모든 전략이 부진(합=0)한 구간은 균등 가중으로 대체
        weights = weights.fillna(1.0 / len(self.strategies))

        combined = pd.Series(0.0, index=df.index)
        for i, sig in enumerate(sigs):
            combined = combined + weights[i] * sig
        return self._finalize(combined, df.index)
