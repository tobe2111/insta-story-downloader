"""CPCV — 조합 퍼지드 교차검증 (Combinatorial Purged Cross-Validation).

롤링 워크포워드는 '과거→미래' 경로 하나만 본다. 그 한 경로의 성과는 우연일 수
있다. CPCV는 데이터를 n_groups개 그룹으로 나누고, n_test개 그룹을 검증(OOS)으로
빼는 모든 조합을 학습/검증해 **여러 개의 독립적인 OOS 경로**를 만든다
(López de Prado, Advances in Financial Machine Learning 12장).

    n_groups=6, n_test=2 → C(6,2)=15개 조합 → 각 그룹이 5번씩 검증
    → 완전한 OOS 경로 5개 → 성과의 '분포'를 본다.

경로 간 성과가 크게 흔들리면(예: 샤프 0.2~2.0) 워크포워드 한 번의 좋은 숫자는
운일 가능성이 높다. 분포가 좁고 일관되게 양수여야 신뢰할 수 있다.

퍼징/엠바고: 검증 그룹과 맞닿은 학습 구간 경계에서 embargo봉을 제거해,
롤링 지표·다음 봉 라벨을 통한 정보 누수를 막는다.

⚠️ CPCV 분포가 좋아도 미래 수익은 보장되지 않는다 — 과최적화 탐지가 목적이다.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Sequence, Type

import numpy as np
import pandas as pd

from quant.backtest.engine import Backtester
from quant.optimize.grid import grid_search
from quant.risk import RiskManager
from quant.strategies.base import Strategy


def _train_segments(n_groups: int, test_idx: tuple[int, ...]) -> list[list[int]]:
    """검증 그룹을 뺀 나머지를 '연속 구간' 단위로 묶는다(지표 연속성 유지)."""
    segs: list[list[int]] = []
    cur: list[int] = []
    for g in range(n_groups):
        if g in test_idx:
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(g)
    if cur:
        segs.append(cur)
    return segs


def cpcv(
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    param_grid: dict[str, Sequence[Any]],
    n_groups: int = 6,
    n_test: int = 2,
    embargo: int = 5,
    objective: str = "sharpe",
    risk: RiskManager | None = None,
    initial_capital: float = 10_000.0,
    fee: float = 0.001,
    periods_per_year: int = 365,
    min_train_bars: int = 60,
) -> dict[str, Any]:
    """CPCV로 OOS 경로 분포를 계산한다.

    각 조합마다: 연속 학습 구간들에서 grid_search → objective를 구간 길이 가중
    평균해 최적 파라미터 선택 → 각 검증 그룹을 (콜드스타트 방지를 위해 그 그룹
    '이전' 전체 데이터를 워밍업으로 넣어) 백테스트하고 마지막 그룹 길이만 취한다.
    검증 그룹의 수익은 파라미터 학습에 쓰인 적 없는 구간의 것이다.

    반환: {paths: [{sharpe, total_return}...], sharpe_mean, sharpe_std,
           sharpe_min, worst_path_return, n_combinations, n_paths, segments[]}
    """
    from quant.backtest.metrics import compute_metrics

    n = len(df)
    if n_test >= n_groups:
        raise ValueError("n_test는 n_groups보다 작아야 합니다.")
    if n < n_groups * max(20, embargo * 2):
        raise ValueError(f"데이터({n}봉)가 그룹 {n_groups}개로 나누기에 짧습니다.")

    edges = np.linspace(0, n, n_groups + 1, dtype=int)
    group_rng = [(int(edges[i]), int(edges[i + 1])) for i in range(n_groups)]

    combos = list(combinations(range(n_groups), n_test))
    # 경로 수 φ = 각 그룹이 검증으로 등장하는 횟수 = C(n_groups-1, n_test-1)
    n_paths = sum(1 for c in combos if 0 in c)
    # 경로 배정: 그룹 g의 k번째 검증 등장 → 경로 k
    occurrence: dict[int, int] = {g: 0 for g in range(n_groups)}
    path_returns: list[list[pd.Series]] = [[] for _ in range(n_paths)]
    seg_log: list[dict] = []

    for ci, test_idx in enumerate(combos):
        # 1) 학습: 연속 구간별 grid_search → 길이 가중 평균 점수로 최적 선택
        scores: dict[str, float] = {}
        weights: dict[str, float] = {}
        params_by_name: dict[str, dict] = {}
        for seg in _train_segments(n_groups, test_idx):
            lo, hi = group_rng[seg[0]][0], group_rng[seg[-1]][1]
            # 퍼징/엠바고: 검증 그룹과 맞닿은 경계를 embargo봉 잘라낸다
            if seg[0] > 0 and (seg[0] - 1) in test_idx:
                lo += embargo
            if seg[-1] < n_groups - 1 and (seg[-1] + 1) in test_idx:
                hi -= embargo
            if hi - lo < min_train_bars:
                continue
            gs = grid_search(df.iloc[lo:hi], strategy_cls, param_grid, risk,
                             objective, initial_capital, fee, periods_per_year)
            for row in gs["results"]:
                sc = row[objective]
                if not np.isfinite(sc):
                    continue
                params = {k: v for k, v in row.items() if k != objective}
                name = ",".join(f"{k}={v}" for k, v in sorted(params.items()))
                w = float(hi - lo)
                scores[name] = scores.get(name, 0.0) + sc * w
                weights[name] = weights.get(name, 0.0) + w
                params_by_name[name] = params
        if not scores:
            continue
        from quant.objective import LOWER_IS_BETTER
        sign = -1.0 if objective in LOWER_IS_BETTER else 1.0
        best_name = max(scores, key=lambda k: sign * scores[k] / weights[k])
        best = params_by_name[best_name]

        # 2) 검증: 그룹별로 '그 그룹 이전 전체'를 워밍업으로 붙여 백테스트.
        #    워밍업은 지표 계산용일 뿐 파라미터 학습에 쓰이지 않는다(룩어헤드 없음).
        for g in test_idx:
            lo, hi = group_rng[g]
            res = Backtester(strategy_cls(**best), risk, initial_capital, fee,
                             periods_per_year=periods_per_year).run(df.iloc[:hi])
            grp_ret = res.returns.iloc[lo:hi]
            path_returns[occurrence[g]].append(grp_ret)
            occurrence[g] += 1
        seg_log.append({"combo": ci, "test_groups": list(test_idx), "params": best})

    paths: list[dict] = []
    for pr in path_returns:
        if not pr:
            continue
        stitched = pd.concat(pr).sort_index()
        stitched = stitched[~stitched.index.duplicated(keep="first")]
        if len(stitched) < 3:
            continue
        # 선행 자본 점을 붙여 equity[0]=capital (첫 봉 수익 누락 방지 — 워크포워드와 동일)
        idx = stitched.index
        lead = idx[0] - (idx[1] - idx[0]) if len(idx) > 1 else idx[0]
        eq = pd.concat([pd.Series([initial_capital], index=[lead]),
                        (1 + stitched).cumprod() * initial_capital])
        m = compute_metrics(eq, stitched, (stitched != 0).astype(float),
                            periods_per_year, positions_are_decision_time=False)
        paths.append({"sharpe": m.sharpe, "total_return": m.total_return,
                      "max_drawdown": m.max_drawdown})

    if not paths:
        raise ValueError("유효한 CPCV 경로를 만들지 못했습니다. 그룹 수를 줄이세요.")

    sharpes = np.array([p["sharpe"] for p in paths])
    return {
        "paths": paths,
        "n_paths": len(paths),
        "n_combinations": len(combos),
        "sharpe_mean": float(sharpes.mean()),
        "sharpe_std": float(sharpes.std(ddof=1)) if len(sharpes) > 1 else 0.0,
        "sharpe_min": float(sharpes.min()),
        "worst_path_return": float(min(p["total_return"] for p in paths)),
        "segments": seg_log,
    }


def cpcv_report(result: dict[str, Any]) -> str:
    """CPCV 결과를 한국어 요약으로."""
    mu, sd = result["sharpe_mean"], result["sharpe_std"]
    lo = result["sharpe_min"]
    if lo > 0 and sd < max(0.5, abs(mu)):
        verdict = "경로 간 일관성 양호 — 한 경로의 성과가 운만은 아닐 가능성"
    elif lo <= 0 <= mu:
        verdict = "주의 — 일부 경로는 손실. 워크포워드 한 번의 성과를 과신하지 말 것"
    else:
        verdict = "경로 전반이 부진 — 이 전략/그리드는 검증을 통과하지 못함"
    return (f"CPCV OOS 경로 {result['n_paths']}개 "
            f"(조합 {result['n_combinations']}개)\n"
            f"샤프 분포: 평균 {mu:.2f} · 표준편차 {sd:.2f} · 최소 {lo:.2f}\n"
            f"최악 경로 수익률: {result['worst_path_return']:.2%}\n"
            f"판정: {verdict}\n"
            f"⚠️ 분포가 좋아도 미래 수익은 보장되지 않습니다.")
