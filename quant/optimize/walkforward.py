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


def _oos_equity_curve(returns: pd.Series, capital: float) -> pd.Series:
    """OOS 수익률 시리즈를 자본곡선으로 변환한다.

    맨 앞에 '첫 수익을 실현하기 전' 자본 점을 넣어 equity[0]==capital이 되게 한다.
    compute_metrics는 equity[0]을 기준가로, len(equity)-1을 복리 기간 수로 쓰므로,
    이 선행 점이 없으면 (1+returns).cumprod()의 첫 값이 곧 기준가가 되어 첫 OOS 봉의
    수익이 total_return·CAGR에서 통째로 누락된다(워밍업 편향 수정이 드러낸 회귀 —
    샤프/변동성은 returns를 직접 써 첫 봉을 포함하므로 지표 간 불일치가 났었다).
    선행 봉의 타임스탬프는 첫 봉 간격만큼 앞선 시점으로 둬 그래프 시간축도 잇는다.
    """
    grown = (1.0 + returns).cumprod() * capital
    idx = returns.index
    if len(idx) > 1:
        lead = idx[0] - (idx[1] - idx[0])
    else:
        lead = idx[0]
    return pd.concat([pd.Series([capital], index=[lead]), grown])


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
    extra_trials: int = 0,
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
        seg_eq = _oos_equity_curve(oos_ret, initial_capital)
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
    equity = _oos_equity_curve(stitched, initial_capital)
    positions = (stitched != 0).astype(float)   # 수익과 정렬된 마스크 → 시프트 금지
    oos_metrics: Metrics = compute_metrics(equity, stitched, positions, periods_per_year,
                                           positions_are_decision_time=False)

    # 다중검정 보정: '운으로 나올 최대 샤프'를 기준선으로 올린 DSR.
    # 0.95↑ 실력 가능성, 0.5 근처면 운일 수 있음.
    #
    # ⚠️ N은 '이 전략을 골라내기까지 시도한 총 횟수'여야 한다(2026-08-11 감사).
    #    예전에는 이 검증 명령의 그리드 크기(4)만 셌다. 그런데 실제로 굴리는
    #    챔피언은 매일 밤 23명씩, 누적 1,846명의 도전자를 이겨서 뽑힌 것이다.
    #    N=4의 허들은 1.05σ, N=1846은 3.43σ — 3.3배 차이다. 즉 DSR이 크게
    #    부풀어 "실력 미확인" 경보가 울려야 할 때 울리지 않았다.
    #    호출자가 장부의 실제 시행 횟수를 extra_trials로 넘긴다.
    n_trials = 1
    for vals in param_grid.values():
        n_trials *= max(1, len(vals))
    n_trials = max(n_trials, int(extra_trials or 0))
    from quant.robustness.deflated_sharpe import deflated_sharpe_ratio
    dsr = deflated_sharpe_ratio(stitched, n_trials=n_trials)

    return {"oos_metrics": oos_metrics, "segments": segments, "equity": equity,
            "dsr": dsr, "n_trials": n_trials}
