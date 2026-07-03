"""병렬 파라미터 스윕 + 2D 민감도 그리드.

grid_search는 '최고 조합 하나'를 찾지만, 스윕은 '파라미터 공간 전체의 지형'을
본다. 좋은 성과가 넓은 고원(plateau)을 이루면 견고한 전략이고, 외딴 봉우리
하나뿐이면 과최적화다. 이 지형을 히트맵으로 그리면 한눈에 판별된다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import product
from typing import Any, Sequence, Type

import pandas as pd

from quant.backtest.engine import Backtester
from quant.risk import RiskManager
from quant.strategies.base import Strategy


def parallel_grid(
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    param_grid: dict[str, Sequence[Any]],
    objective: str = "sharpe",
    risk: RiskManager | None = None,
    workers: int = 4,
    periods_per_year: int = 365,
) -> list[dict]:
    """모든 파라미터 조합을 병렬 백테스트해 결과 목록을 반환한다."""
    keys = list(param_grid)
    combos = [dict(zip(keys, v)) for v in product(*[param_grid[k] for k in keys])]

    def _run(params: dict) -> dict | None:
        try:
            strat = strategy_cls(**params)
        except (ValueError, TypeError):
            return None
        res = Backtester(strat, risk, periods_per_year=periods_per_year).run(df)
        return {**params, objective: getattr(res.metrics, objective),
                "metrics": res.metrics}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return [r for r in ex.map(_run, combos) if r is not None]


def sensitivity_grid(
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    x_param: str,
    x_values: Sequence[Any],
    y_param: str,
    y_values: Sequence[Any],
    base_params: dict | None = None,
    objective: str = "sharpe",
    risk: RiskManager | None = None,
    periods_per_year: int = 365,
) -> list[list[float | None]]:
    """두 파라미터를 격자로 훑어 objective 값의 2D 그리드를 만든다.

    반환: grid[i][j] = (y_values[i], x_values[j]) 조합의 objective 값.
          유효하지 않은 조합은 None.
    """
    base = base_params or {}
    grid: list[list[float | None]] = [[None] * len(x_values) for _ in y_values]
    for i, y in enumerate(y_values):
        for j, x in enumerate(x_values):
            params = {**base, x_param: x, y_param: y}
            try:
                strat = strategy_cls(**params)
            except (ValueError, TypeError):
                continue
            res = Backtester(strat, risk, periods_per_year=periods_per_year).run(df)
            grid[i][j] = float(getattr(res.metrics, objective))
    return grid
