"""PBO — 백테스트 과적합 확률 (Probability of Backtest Overfitting).

Bailey·Borwein·López de Prado·Zhu(2015)의 CSCV(조합 대칭 교차검증) 방식.

질문: "IS(과거)에서 1등이었던 설정이 OOS(미래)에서도 상위권인가?"
방법: 수익률 행렬(시간×설정)을 S개 블록으로 나누고, S/2개 블록을 IS로 뽑는
    모든 조합(C(S,S/2)개)에 대해 IS 1등 설정의 OOS '상대 순위'를 본다.
    OOS 순위가 중앙값 이하로 떨어진 조합의 비율이 PBO다.

해석:
    PBO ≈ 0.5  → IS 1등이 OOS에서 동전던지기 수준. 선택 과정이 노이즈를 고름.
    PBO < 0.2  → IS 성과가 OOS로 어느 정도 이어짐(과적합 위험 낮음).
    PBO > 0.7  → 사실상 확실한 과적합. 그 '최적 파라미터'는 버릴 것.

⚠️ PBO가 낮아도 미래 수익이 보장되는 것은 아니다 — '선택 절차가 노이즈를
   고르고 있지 않다'는 증거일 뿐이다.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Sequence, Type

import numpy as np
import pandas as pd

from quant.utils.numerics import SHARPE_REL_EPS


def _sharpe_cols(block: np.ndarray) -> np.ndarray:
    """블록(시간×설정)의 설정별 주기 샤프. 표준편차 0이면 0."""
    mu = block.mean(axis=0)
    sd = block.std(axis=0, ddof=1)
    out = np.zeros(block.shape[1])
    # ⚠️ `sd > 0`이면 통과시키면 안 된다(감사 146). 한 설정의 수익이 거의
    #    상수면 표준편차가 1e-19이 되어 샤프가 1e15로 튀고, 그 설정이 어떤
    #    조합에서도 IS 1등이 된다 — PBO가 통째로 그 잡음에 좌우된다.
    scale = np.abs(block).mean(axis=0)
    ok = np.isfinite(sd) & (sd > SHARPE_REL_EPS * np.maximum(scale, 1e-300))
    out[ok] = mu[ok] / sd[ok]
    return out


def pbo(returns_matrix: pd.DataFrame, n_blocks: int = 10) -> dict[str, Any]:
    """수익률 행렬(index=시간, columns=설정)로 PBO를 계산한다.

    n_blocks: 시계열을 나눌 블록 수(짝수). 기본 10 → C(10,5)=252개 조합.
    반환: {pbo, n_combinations, lambda_values, mean_oos_rank,
           prob_oos_loss(선택된 설정의 OOS 샤프가 음수인 비율)}
    """
    if returns_matrix.shape[1] < 2:
        raise ValueError("설정(컬럼)이 2개 이상이어야 PBO를 계산할 수 있습니다.")
    S = int(n_blocks)
    if S < 2 or S % 2 != 0:
        raise ValueError("n_blocks는 2 이상의 짝수여야 합니다.")
    m = returns_matrix.to_numpy(dtype=float)
    m = np.nan_to_num(m, nan=0.0, posinf=0.0, neginf=0.0)
    T, N = m.shape
    if T < S * 4:
        raise ValueError(f"데이터({T}봉)가 너무 짧습니다. 블록당 최소 4봉 필요.")

    # 시간 순서를 유지한 채 S개 등분(끝자락 나머지는 마지막 블록에 흡수)
    edges = np.linspace(0, T, S + 1, dtype=int)
    blocks = [m[edges[i]:edges[i + 1]] for i in range(S)]

    lambdas: list[float] = []
    oos_ranks: list[float] = []
    oos_selected_sharpe: list[float] = []
    idx_all = set(range(S))
    for is_idx in combinations(range(S), S // 2):
        oos_idx = sorted(idx_all - set(is_idx))
        is_m = np.vstack([blocks[i] for i in is_idx])
        oos_m = np.vstack([blocks[i] for i in oos_idx])
        sr_is = _sharpe_cols(is_m)
        sr_oos = _sharpe_cols(oos_m)
        best = int(np.argmax(sr_is))                 # IS 1등 설정
        # OOS에서의 상대 순위(0~1). 0.5=중앙값, 1에 가까울수록 OOS서도 상위.
        omega = (np.sum(sr_oos <= sr_oos[best])) / (N + 1.0)
        omega = min(max(omega, 1e-9), 1.0 - 1e-9)
        lambdas.append(float(np.log(omega / (1.0 - omega))))
        oos_ranks.append(float(omega))
        oos_selected_sharpe.append(float(sr_oos[best]))

    lam = np.asarray(lambdas)
    return {
        "pbo": float((lam <= 0).mean()),
        "n_combinations": len(lambdas),
        "lambda_values": lambdas,
        "mean_oos_rank": float(np.mean(oos_ranks)),
        "prob_oos_loss": float((np.asarray(oos_selected_sharpe) < 0).mean()),
    }


def param_returns_matrix(
    df: pd.DataFrame,
    strategy_cls: Type,
    param_grid: dict[str, Sequence[Any]],
    fee: float = 0.001,
    initial_capital: float = 10_000.0,
    periods_per_year: int = 365,
) -> pd.DataFrame:
    """파라미터 그리드의 모든 조합을 백테스트해 수익률 행렬을 만든다(PBO 입력용).

    컬럼명은 'fast=5,slow=50' 형식. 잘못된 조합(예: fast>=slow)은 건너뛴다.
    """
    from itertools import product

    from quant.backtest.engine import Backtester

    keys = list(param_grid)
    cols: dict[str, pd.Series] = {}
    for values in product(*[param_grid[k] for k in keys]):
        params = dict(zip(keys, values))
        try:
            strat = strategy_cls(**params)
        except (ValueError, TypeError):
            continue
        res = Backtester(strat, initial_capital=initial_capital, fee=fee,
                         periods_per_year=periods_per_year).run(df)
        name = ",".join(f"{k}={v}" for k, v in params.items())
        cols[name] = res.returns
    if len(cols) < 2:
        raise ValueError("유효한 파라미터 조합이 2개 미만이라 PBO를 계산할 수 없습니다.")
    return pd.DataFrame(cols)


def pbo_report(result: dict[str, Any]) -> str:
    """PBO 결과를 사람이 읽을 한국어 요약으로."""
    p = result["pbo"]
    if p < 0.2:
        verdict = "과적합 위험 낮음 — IS 성과가 OOS로 이어지는 편"
    elif p < 0.5:
        verdict = "주의 — 선택된 파라미터의 OOS 성과가 불안정"
    else:
        verdict = "과적합 가능성 높음 — 이 '최적 파라미터'를 신뢰하지 말 것"
    return (f"PBO(백테스트 과적합 확률): {p:.1%} ({result['n_combinations']}개 조합)\n"
            f"IS 1등의 평균 OOS 순위: 상위 {(1 - result['mean_oos_rank']):.0%}\n"
            f"IS 1등이 OOS에서 손실일 확률: {result['prob_oos_loss']:.1%}\n"
            f"판정: {verdict}\n"
            f"⚠️ PBO가 낮아도 미래 수익이 보장되지 않습니다.")
