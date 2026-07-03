"""전략 계층."""
from __future__ import annotations

from quant.strategies.adx import ADXFilter
from quant.strategies.base import Strategy
from quant.strategies.breakout import Breakout
from quant.strategies.ensemble import AdaptiveEnsemble, StrategyEnsemble
from quant.strategies.keltner import KeltnerBreakout
from quant.strategies.macd import MACD
from quant.strategies.mean_reversion import MeanReversion
from quant.strategies.momentum import Momentum
from quant.strategies.ml import MLStrategy
from quant.strategies.moving_average import MovingAverageCross
from quant.strategies.regime import RegimeFilter
from quant.strategies.rsi import RSIReversion
from quant.strategies.stochastic import Stochastic

# 파라미터만으로 생성 가능한 단순 전략 (앙상블/레짐/ADX는 다른 전략을 인자로 받아 별도 취급)
_REGISTRY = {
    "ma_cross": MovingAverageCross,
    "momentum": Momentum,
    "mean_reversion": MeanReversion,
    "rsi": RSIReversion,
    "breakout": Breakout,
    "macd": MACD,
    "keltner": KeltnerBreakout,
    "stochastic": Stochastic,
    "ml": MLStrategy,
}

__all__ = [
    "Strategy",
    "MovingAverageCross",
    "Momentum",
    "MeanReversion",
    "RSIReversion",
    "Breakout",
    "MACD",
    "KeltnerBreakout",
    "Stochastic",
    "MLStrategy",
    "StrategyEnsemble",
    "AdaptiveEnsemble",
    "RegimeFilter",
    "ADXFilter",
    "get_strategy",
    "list_strategies",
    "default_ensemble",
    "adaptive_ensemble",
]


def get_strategy(name: str, **kwargs) -> Strategy:
    """이름으로 전략 인스턴스를 생성한다."""
    if name not in _REGISTRY:
        raise ValueError(f"알 수 없는 전략: {name}. 사용 가능: {list(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)


def list_strategies() -> list[str]:
    return list(_REGISTRY)


def _diversified_book(allow_short: bool = False):
    """추세추종 2 + 평균회귀 2로 균형 잡은 전략 묶음 (상관이 낮아 분산 효과가 크다)."""
    return [
        MovingAverageCross(fast=20, slow=60),      # 추세추종
        Breakout(window=55, exit_window=20),       # 추세추종(돌파)
        RSIReversion(period=14),                   # 평균회귀(단기)
        MeanReversion(window=20, z=2.0),           # 평균회귀(밴드)
    ]


def default_ensemble(allow_short: bool = False,
                     weighting: str = "fixed") -> StrategyEnsemble:
    """추세추종 + 평균회귀를 균형 있게 섞은 기본 앙상블.

    weighting="inverse_vol" 이면 리스크 패리티(역변동성 가중)로 결합해 변동성이
    큰 전략이 포트폴리오 위험을 독점하지 못하게 균형을 맞춘다.
    """
    return StrategyEnsemble(
        strategies=_diversified_book(allow_short),
        allow_short=allow_short,
        weighting=weighting,
    )


def adaptive_ensemble(lookback: int = 60, allow_short: bool = False,
                      score: str = "sharpe", risk_parity: bool = True) -> AdaptiveEnsemble:
    """최근 위험조정 성과에 따라 소프트맥스로 가중치를 조정하는 적응형 앙상블."""
    return AdaptiveEnsemble(
        strategies=_diversified_book(allow_short),
        lookback=lookback,
        allow_short=allow_short,
        score=score,
        risk_parity=risk_parity,
    )
