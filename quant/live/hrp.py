"""계층적 리스크 패리티(HRP) — 상관 구조를 '나무'로 읽는 배분.

ERC(위험기여 균등)는 공분산 반복법이라 상관 추정 오차에 민감하다 — 90일
표본으로 추정한 상관은 잡음이 많고, 잡음이 큰 행렬일수록 반복법의 답이
불안정하다. HRP(López de Prado 2016)는 역행렬·반복법을 아예 쓰지 않는다:

    ① 상관 거리(√(½(1−ρ)))로 종목을 계층 군집화(단일 연결)
    ② 군집 트리의 잎 순서로 종목을 재배열(준대각화 — 비슷한 것끼리 이웃)
    ③ 목록을 재귀적으로 절반씩 나누며 '군집 분산'의 역수 비율로 예산 배분

    소표본에서 ERC보다 OOS 분산이 안정적이라는 게 원 논문의 주장이며,
    우리 용도(하루 한 번, 종목 ~20개, 90일 표본)가 정확히 그 환경이다.

⚠️ 배분 규칙이지 알파가 아니다 — 수익을 만드는 게 아니라 추정 오차가
   집중 베팅으로 새는 것을 막는다. 실패 시 None(호출자가 ERC→균등 폴백).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.utils.logging import get_logger

log = get_logger("hrp")


def _cluster_var(cov: pd.DataFrame, items: list) -> float:
    """군집 분산 — 군집 내부를 역분산 비중으로 들었을 때의 분산."""
    sub = cov.loc[items, items].to_numpy()
    ivp = 1.0 / np.maximum(np.diag(sub), 1e-16)
    ivp = ivp / ivp.sum()
    return float(ivp @ sub @ ivp)


def hrp_weights(returns: pd.DataFrame) -> dict | None:
    """수익률 행렬(행=날짜, 열=종목) → HRP 비중 dict. 퇴화 시 None."""
    try:
        if returns.shape[1] < 2 or len(returns) < 40:
            return None
        cov = returns.cov()
        corr = returns.corr().clip(-1.0, 1.0)
        if not np.isfinite(cov.to_numpy()).all():
            return None
        # ① 상관 거리 행렬 → 단일 연결 계층 군집화
        from scipy.cluster.hierarchy import leaves_list, linkage
        from scipy.spatial.distance import squareform
        dist = np.sqrt(0.5 * (1.0 - corr.to_numpy()))
        np.fill_diagonal(dist, 0.0)
        link = linkage(squareform(dist, checks=False), method="single")
        # ② 준대각화 — 잎 순서(비슷한 종목이 이웃하도록 재배열)
        order = [returns.columns[i] for i in leaves_list(link)]
        # ③ 재귀 이분 — 왼/오 군집 분산의 역수 비율로 예산을 쪼갠다
        w = pd.Series(1.0, index=order)
        stack = [order]
        while stack:
            cl = stack.pop()
            if len(cl) <= 1:
                continue
            half = len(cl) // 2
            left, right = cl[:half], cl[half:]
            v_l, v_r = _cluster_var(cov, left), _cluster_var(cov, right)
            if not (np.isfinite(v_l) and np.isfinite(v_r)) or v_l + v_r <= 0:
                return None
            alpha = 1.0 - v_l / (v_l + v_r)
            w[left] *= alpha
            w[right] *= 1.0 - alpha
            stack += [left, right]
        w = w / w.sum()
        if not np.isfinite(w.to_numpy()).all():
            return None
        return {str(k): float(v) for k, v in w.items()}
    except Exception as exc:  # noqa: BLE001 — 배분 실패가 매매를 막으면 안 된다
        log.warning("HRP 계산 실패: %s", exc)
        return None
