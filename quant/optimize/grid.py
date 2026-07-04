"""그리드 서치 — 주어진 데이터에서 목표 지표를 최대화하는 파라미터 탐색.

⚠️ 단독 사용 주의: 이건 '과거(in-sample)'에서 가장 좋았던 파라미터를 찾을 뿐이다.
그대로 실전에 쓰면 과최적화된다. 반드시 walk_forward로 검증할 것.
"""
from __future__ import annotations

from itertools import product
from typing import Any, Sequence, Type

import pandas as pd

from quant.backtest.engine import Backtester
from quant.objective import LOWER_IS_BETTER as _LOWER_IS_BETTER
from quant.risk import RiskManager
from quant.strategies.base import Strategy


def grid_search(
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    param_grid: dict[str, Sequence[Any]],
    risk: RiskManager | None = None,
    objective: str = "sharpe",
    initial_capital: float = 10_000.0,
    fee: float = 0.001,
    periods_per_year: int = 365,
) -> dict[str, Any]:
    """param_grid의 모든 조합을 백테스트해 objective가 최대인 조합을 찾는다.

    objective: Metrics의 속성명 (sharpe, calmar, sortino, cagr, total_return ...)
    반환: {best_params, best_score, best_metrics, results[]}
    """
    keys = list(param_grid)
    lower_better = objective in _LOWER_IS_BETTER
    best_cmp = float("-inf")           # 방향 보정된 비교값(항상 클수록 좋음)
    best_score = float("-inf")         # 리포트용 원본 점수
    best_params: dict | None = None
    best_metrics = None
    results: list[dict] = []

    for values in product(*[param_grid[k] for k in keys]):
        params = dict(zip(keys, values))
        try:
            strat = strategy_cls(**params)
        except (ValueError, TypeError):
            continue  # 잘못된 조합 (예: fast >= slow) 은 건너뜀
        res = Backtester(
            strat, risk, initial_capital, fee, periods_per_year=periods_per_year
        ).run(df)
        score = getattr(res.metrics, objective)
        results.append({**params, objective: score})
        cmp = -score if lower_better else score   # 작을수록 좋은 지표는 부호 반전
        if cmp > best_cmp:
            best_cmp, best_score, best_params, best_metrics = cmp, score, params, res.metrics

    return {
        "best_params": best_params,
        "best_score": best_score,
        "best_metrics": best_metrics,
        "results": results,
    }
