"""포트폴리오 리스크 지표 — VaR/CVaR·상관 집중도·롤링 평균 상관.

분산 효과는 '상관이 낮을 때'만 존재한다. 위기 국면에서는 자산 간 상관이
치솟아 분산이 사라지는 일이 흔하다(2020.3, 2022 등). 이 지표들은 그런
'분산의 환상'을 수치로 드러낸다.

⚠️ 과거 수익률 기반 통계일 뿐, 미래 손실의 한도를 보장하지 않는다.
   특히 역사적 VaR는 표본에 없던 꼬리 사건을 원리적으로 포착하지 못한다.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


def var_cvar(returns: pd.Series | pd.DataFrame, alpha: float = 0.95):
    """역사적(historical) VaR / CVaR.

    VaR  = 신뢰수준 alpha에서의 손실 한계(양수 = 손실). 예: alpha=0.95면
           '과거 분포 기준 하위 5% 수익률의 경계'.
    CVaR = VaR 이하 꼬리 수익률의 평균 손실(양수). VaR보다 항상 크거나 같아
           꼬리 위험을 더 정직하게 보여준다.

    Series 입력 → (var, cvar) 튜플.
    DataFrame 입력 → 컬럼별 결과 DataFrame(index=['var','cvar']).
    표본이 없으면 NaN을 반환한다(0으로 '무위험'처럼 보이게 하지 않는다).
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha는 (0,1) 범위여야 합니다: {alpha}")
    if isinstance(returns, pd.DataFrame):
        cols = {c: var_cvar(returns[c], alpha) for c in returns.columns}
        return pd.DataFrame(cols, index=["var", "cvar"])

    r = returns.dropna()
    if len(r) == 0:
        return float("nan"), float("nan")
    # 'lower' 보간: 하위 (1-alpha) 경계를 '그 이하 표본이 실제로 존재하는 값'으로
    # 잡는다. 기본 선형 보간은 손실 표본이 딱 (1-alpha)×N개일 때 경계가 이익
    # 구간으로 넘어가 VaR가 손실을 과소평가(음수화)할 수 있다 — 리스크 지표는
    # 보수적인 쪽을 택한다.
    q = float(r.quantile(1.0 - alpha, interpolation="lower"))
    var = -q
    tail = r[r <= q]
    cvar = -float(tail.mean()) if len(tail) else var
    return var, cvar


def correlation_concentration(
    returns_df: pd.DataFrame, weights=None
) -> dict:
    """상관 집중도 요약 — 분산이 실제로 작동하는지 점검한다.

    반환 dict:
        avg_correlation : 쌍별 상관의 평균 (1에 가까울수록 분산 효과 없음)
        max_correlation : 쌍별 상관의 최댓값 (숨은 중복 베팅 탐지)
        effective_n     : 유효 종목 수 = 1/Σw² (균등 가중이면 종목 수와 같고,
                          한 종목에 쏠릴수록 1에 가까워진다)
        n_assets        : 실제 종목 수
    weights 미지정 시 균등 가중으로 계산한다.
    """
    n = returns_df.shape[1]
    if weights is None:
        w = np.full(n, 1.0 / n) if n > 0 else np.array([])
    else:
        w = np.asarray(list(weights), dtype=float)
        total = np.abs(w).sum()
        # |비중| 정규화 — 롱숏 혼합에서도 집중도(쏠림)만 측정한다.
        w = np.abs(w) / total if total > 0 else np.full(len(w), 1.0 / max(len(w), 1))
    eff_n = float(1.0 / np.square(w).sum()) if len(w) and np.square(w).sum() > 0 \
        else float("nan")

    if n < 2:
        return {"avg_correlation": float("nan"), "max_correlation": float("nan"),
                "effective_n": eff_n, "n_assets": int(n)}

    corr = returns_df.corr().to_numpy()
    iu = np.triu_indices(n, k=1)               # 대각선 제외 상삼각(쌍별 상관)
    pair = corr[iu]
    pair = pair[np.isfinite(pair)]
    if len(pair) == 0:
        avg, mx = float("nan"), float("nan")
    else:
        avg, mx = float(pair.mean()), float(pair.max())
    return {"avg_correlation": avg, "max_correlation": mx,
            "effective_n": eff_n, "n_assets": int(n)}


def rolling_avg_correlation(returns_df: pd.DataFrame, window: int) -> pd.Series:
    """쌍별 상관의 롤링 평균 — '상관 레짐' 모니터링용.

    값이 급등하면 분산 효과가 사라지는 국면(위기 동조화)일 수 있으므로
    총 노출 축소를 검토할 신호로 쓴다. 종목이 2개 미만이면 전부 NaN.
    """
    if window < 2:
        raise ValueError(f"window는 2 이상이어야 합니다: {window}")
    cols = list(returns_df.columns)
    if len(cols) < 2:
        return pd.Series(np.nan, index=returns_df.index, name="avg_correlation")
    acc = None
    pairs = list(combinations(cols, 2))
    for a, b in pairs:
        c = returns_df[a].rolling(window).corr(returns_df[b])
        acc = c if acc is None else acc + c
    out = acc / len(pairs)
    # 분산 0 구간(가격 고정 등)에서 rolling corr가 ±inf를 낼 수 있다 → NaN 처리
    return out.replace([np.inf, -np.inf], np.nan).rename("avg_correlation")
