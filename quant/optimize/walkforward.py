"""워크포워드 검증 — 과최적화를 막는 정직한 최적화.

방식:
    [--- 학습(IS) ---][검증(OOS)]
              [--- 학습(IS) ---][검증(OOS)]
                        [--- 학습(IS) ---][검증(OOS)]
    각 구간마다 '과거(IS)'에서 최적 파라미터를 찾고, 그 파라미터를
    '보지 않은 미래(OOS)'에 적용한다. OOS 성과만 이어붙여 평가한다.

이렇게 나온 OOS 성적이 실전에서 기대할 수 있는 '진짜' 성과에 훨씬 가깝다.
IS에서 화려한 성과가 OOS에서 무너지면 그 전략은 실전에서도 무너진다.
"""
from __future__ import annotations

from typing import Any, Sequence, Type

import pandas as pd

from quant.backtest.engine import Backtester
from quant.backtest.metrics import Metrics, compute_metrics
from quant.optimize.grid import grid_search
from quant.risk import RiskManager
from quant.strategies.base import Strategy


def walk_forward(
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    param_grid: dict[str, Sequence[Any]],
    is_window: int,
    oos_window: int,
    step: int | None = None,
    objective: str = "sharpe",
    risk: RiskManager | None = None,
    initial_capital: float = 10_000.0,
    fee: float = 0.001,
    periods_per_year: int = 365,
) -> dict[str, Any]:
    """롤링 워크포워드 검증을 수행한다.

    is_window : 학습(in-sample) 구간 길이(봉 개수)
    oos_window: 검증(out-of-sample) 구간 길이
    step      : 창을 밀어내는 간격(기본 = oos_window, 겹치지 않게)
    반환: {oos_metrics, segments[], equity}
    """
    step = step or oos_window
    n = len(df)
    if is_window + oos_window > n:
        raise ValueError(
            f"데이터({n})가 is_window+oos_window({is_window + oos_window})보다 짧습니다."
        )

    oos_returns: list[pd.Series] = []
    segments: list[dict] = []
    start = 0
    while start + is_window + oos_window <= n:
        is_slice = df.iloc[start : start + is_window]
        oos_slice = df.iloc[start + is_window : start + is_window + oos_window]

        gs = grid_search(
            is_slice, strategy_cls, param_grid, risk, objective,
            initial_capital, fee, periods_per_year,
        )
        best = gs["best_params"]
        if best is None:
            start += step
            continue

        # 보지 않은 구간(OOS)에 최적 파라미터 적용
        strat = strategy_cls(**best)
        res = Backtester(
            strat, risk, initial_capital, fee, periods_per_year=periods_per_year
        ).run(oos_slice)
        oos_returns.append(res.returns)
        segments.append(
            {
                "is_start": str(df.index[start]),
                "oos_start": str(df.index[start + is_window]),
                "params": best,
                "is_sharpe": round(gs["best_score"], 3),
                "oos_sharpe": round(res.metrics.sharpe, 3),
                "oos_return": round(res.metrics.total_return, 4),
            }
        )
        start += step

    if not oos_returns:
        raise ValueError("검증 구간을 만들지 못했습니다. 윈도우 크기를 줄이세요.")

    stitched = pd.concat(oos_returns)
    stitched = stitched[~stitched.index.duplicated(keep="first")].sort_index()
    equity = (1 + stitched).cumprod() * initial_capital
    positions = (stitched != 0).astype(float)
    oos_metrics: Metrics = compute_metrics(equity, stitched, positions, periods_per_year)

    return {"oos_metrics": oos_metrics, "segments": segments, "equity": equity}
