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
    embargo: int = 0,
) -> dict[str, Any]:
    """롤링 워크포워드 검증을 수행한다.

    is_window : 학습(in-sample) 구간 길이(봉 개수)
    oos_window: 검증(out-of-sample) 구간 길이
    step      : 창을 밀어내는 간격(기본 = oos_window, 겹치지 않게)
    embargo   : 학습(IS)과 검증(OOS) 사이에 두는 공백 봉 수(퍼징/엠바고).
                지표가 롤링 윈도우를 쓰거나 라벨이 다음 봉을 참조하면 IS 끝과
                OOS 시작이 맞닿아 정보가 새어들 수 있다. 이 갭이 그 누수를 막아
                OOS 성과를 더 보수적·정직하게 만든다 (López de Prado 방식).
    반환: {oos_metrics, segments[], equity}
    """
    step = step or oos_window
    gap = max(0, embargo)
    n = len(df)
    if is_window + gap + oos_window > n:
        raise ValueError(
            f"데이터({n})가 is_window+embargo+oos_window"
            f"({is_window + gap + oos_window})보다 짧습니다."
        )

    oos_returns: list[pd.Series] = []
    segments: list[dict] = []
    start = 0
    while start + is_window + gap + oos_window <= n:
        is_slice = df.iloc[start : start + is_window]
        oos_start = start + is_window + gap        # 엠바고 갭만큼 띄운다
        oos_end = oos_start + oos_window

        gs = grid_search(
            is_slice, strategy_cls, param_grid, risk, objective,
            initial_capital, fee, periods_per_year,
        )
        best = gs["best_params"]
        if best is None:
            start += step
            continue

        # 보지 않은 구간(OOS)에 최적 파라미터 적용.
        # ⚠️ 워밍업 편향 방지: OOS 구간만 잘라 백테스트하면 이동평균·롤링지표·ML이
        #    콜드 스타트라 초반 봉이 전부 관망(0)이 되어 OOS 성과가 왜곡된다.
        #    실전에서는 과거 이력이 이미 있으므로, IS 이력을 워밍업으로 함께 넣어
        #    백테스트한 뒤 '마지막 oos_window봉'만 성과로 취한다. OOS 봉의 신호는
        #    여전히 그 봉까지의 과거만 참조하므로 룩어헤드는 없다.
        warm_slice = df.iloc[start:oos_end]
        strat = strategy_cls(**best)
        res = Backtester(
            strat, risk, initial_capital, fee, periods_per_year=periods_per_year
        ).run(warm_slice)
        oos_ret = res.returns.iloc[-oos_window:]
        oos_returns.append(oos_ret)

        # 구간별 OOS 지표는 워밍업을 제외한 '꼬리'로만 계산해야 정직하다.
        # seg_pos는 (수익!=0) 마스크라 이미 수익과 정렬돼 있으므로 추가 시프트 금지.
        seg_pos = (oos_ret != 0).astype(float)
        seg_eq = (1 + oos_ret).cumprod() * initial_capital
        seg_m = compute_metrics(seg_eq, oos_ret, seg_pos, periods_per_year,
                                positions_are_decision_time=False)
        segments.append(
            {
                "is_start": str(df.index[start]),
                "oos_start": str(df.index[oos_start]),
                "params": best,
                "is_sharpe": round(gs["best_score"], 3),
                "oos_sharpe": round(seg_m.sharpe, 3),
                "oos_return": round(seg_m.total_return, 4),
            }
        )
        start += step

    if not oos_returns:
        raise ValueError("검증 구간을 만들지 못했습니다. 윈도우 크기를 줄이세요.")

    stitched = pd.concat(oos_returns)
    stitched = stitched[~stitched.index.duplicated(keep="first")].sort_index()
    equity = (1 + stitched).cumprod() * initial_capital
    positions = (stitched != 0).astype(float)   # 수익과 정렬된 마스크 → 시프트 금지
    oos_metrics: Metrics = compute_metrics(equity, stitched, positions, periods_per_year,
                                           positions_are_decision_time=False)

    return {"oos_metrics": oos_metrics, "segments": segments, "equity": equity}
