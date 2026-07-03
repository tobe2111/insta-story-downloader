"""전략 계층."""
from __future__ import annotations

from quant.strategies.base import Strategy
from quant.strategies.breakout import Breakout
from quant.strategies.ensemble import AdaptiveEnsemble, StrategyEnsemble
from quant.strategies.keltner import KeltnerBreakout
from quant.strategies.macd import MACD
from quant.strategies.mean_reversion import MeanReversion
from quant.strategies.momentum import Momentum
from quant.strategies.moving_average import MovingAverageCross
from quant.strategies.regime import RegimeFilter
from quant.strategies.rsi import RSIReversion

# 파라미터만으로 생성 가능한 단순 전략 (앙상블/레짐은 다른 전략을 인자로 받아 별도 취급)
_REGISTRY = {
    "ma_cross": MovingAverageCross,
    "momentum": Momentum,
    "mean_reversion": MeanReversion,
    "rsi": RSIReversion,
    "breakout": Breakout,
    "macd": MACD,
    "keltner": KeltnerBreakout,
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
    "StrategyEnsemble",
    "AdaptiveEnsemble",
    "RegimeFilter",
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


def default_ensemble(allow_short: bool = False) -> StrategyEnsemble:
    """추세추종 + 평균회귀를 섞은 기본 앙상블 (상관이 낮아 분산 효과가 좋다)."""
    return StrategyEnsemble(
        strategies=[
            MovingAverageCross(fast=20, slow=60),
            Breakout(window=55, exit_window=20),
            RSIReversion(period=14),
        ],
        allow_short=allow_short,
    )


def adaptive_ensemble(lookback: int = 60, allow_short: bool = False) -> AdaptiveEnsemble:
    """최근 성과에 따라 가중치를 조정하는 적응형 앙상블 (추세추종+평균회귀)."""
    return AdaptiveEnsemble(
        strategies=[
            MovingAverageCross(fast=20, slow=60),
            Breakout(window=55, exit_window=20),
            RSIReversion(period=14),
        ],
        lookback=lookback,
        allow_short=allow_short,
    )
