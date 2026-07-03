"""확률적/디플레이티드 샤프 지수 (Bailey & López de Prado).

샤프지수 하나로는 '실력'과 '운'을 구분할 수 없다. 특히 여러 전략·파라미터를
시도하면(다중검정) 그중 하나는 우연히 높은 샤프가 나온다. 이를 보정한다.

- PSR (Probabilistic Sharpe Ratio): 표본 길이·왜도·첨도를 반영해, 참(true)
  샤프가 기준치를 넘을 '확률'을 준다.
- DSR (Deflated Sharpe Ratio): 기준치를 '시행 횟수 N번에서 기대되는 최대 샤프'로
  올려 PSR을 계산한다. 즉 "N번 시도했을 때 이 정도는 운으로도 나온다"를 제거한다.

해석: DSR이 0.95 이상이면 실력일 가능성이 높고, 0.5 근처거나 이하면 운일 수 있다.
과거 성과가 미래를 보장하지 않는다는 사실은 이 보정 뒤에도 그대로다.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

_EULER = 0.5772156649015329  # 오일러-마스케로니 상수
_ND = NormalDist()


def _moments(returns: pd.Series | np.ndarray) -> tuple[int, float, float, float]:
    """표본 길이 T, 주기 샤프, 왜도(γ3), 첨도(γ4, 정규=3)를 반환."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    T = len(r)
    if T < 3:
        return T, 0.0, 0.0, 3.0
    mu = r.mean()
    sd = r.std(ddof=1)
    if sd <= 0:
        return T, 0.0, 0.0, 3.0
    sr = mu / sd
    z = (r - mu) / sd
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())
    return T, float(sr), skew, kurt


def probabilistic_sharpe_ratio(returns, sr_benchmark: float = 0.0) -> float:
    """참 샤프가 sr_benchmark(주기 기준)를 초과할 확률 (0~1)."""
    T, sr, skew, kurt = _moments(returns)
    if T < 3:
        return 0.0
    denom = np.sqrt(max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2))
    stat = (sr - sr_benchmark) * np.sqrt(T - 1.0) / denom
    return float(_ND.cdf(stat))


def expected_max_sharpe(n_trials: int, trials_sharpe_std: float) -> float:
    """N번 시행에서 기대되는 최대 샤프 (귀무가설: 진짜 엣지 없음)."""
    N = max(2, int(n_trials))
    return trials_sharpe_std * (
        (1.0 - _EULER) * _ND.inv_cdf(1.0 - 1.0 / N)
        + _EULER * _ND.inv_cdf(1.0 - 1.0 / (N * np.e))
    )


def deflated_sharpe_ratio(returns, n_trials: int = 1,
                          trials_sharpe_std: float | None = None) -> float:
    """다중검정 보정된 샤프 신뢰도 (0~1).

    trials_sharpe_std: 시행 간 샤프의 표준편차. 미지정 시 표본 샤프의 표준오차로
    근사한다(단일 전략 상황의 실용적 대용치).
    """
    T, sr, skew, kurt = _moments(returns)
    if T < 3:
        return 0.0
    if trials_sharpe_std is None:
        trials_sharpe_std = float(np.sqrt(max(
            1e-12, (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2) / (T - 1.0))))
    sr_star = expected_max_sharpe(n_trials, trials_sharpe_std) if n_trials > 1 else 0.0
    return probabilistic_sharpe_ratio(returns, sr_benchmark=sr_star)
