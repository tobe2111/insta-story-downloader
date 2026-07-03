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
