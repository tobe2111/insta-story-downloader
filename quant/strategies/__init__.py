"""전략 계층."""
from __future__ import annotations

from quant.strategies.base import Strategy
from quant.strategies.mean_reversion import MeanReversion
from quant.strategies.momentum import Momentum
from quant.strategies.moving_average import MovingAverageCross

_REGISTRY = {
    "ma_cross": MovingAverageCross,
    "momentum": Momentum,
    "mean_reversion": MeanReversion,
}

__all__ = [
    "Strategy",
    "MovingAverageCross",
    "Momentum",
    "MeanReversion",
    "get_strategy",
    "list_strategies",
]


def get_strategy(name: str, **kwargs) -> Strategy:
    """이름으로 전략 인스턴스를 생성한다."""
    if name not in _REGISTRY:
        raise ValueError(f"알 수 없는 전략: {name}. 사용 가능: {list(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)


def list_strategies() -> list[str]:
    return list(_REGISTRY)
