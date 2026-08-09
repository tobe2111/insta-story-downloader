"""HAR-RV 변동성 예측 — 방향은 못 맞춰도 변동성은 꽤 맞는다.

변동성은 강한 자기상관(군집)이 있어 예측 가능성이 방향보다 훨씬 높다.
HAR(Heterogeneous AutoRegressive) 모델은 어제(일)·최근 5일(주)·최근 22일(월)
실현분산의 선형 조합으로 내일 분산을 예측한다(Corsi 2009) — 단순한데도
GARCH류와 대등해 실무 표준으로 쓰인다.

    RV(t+1) ≈ c + βd·RV_d(t) + βw·RV_w(t) + βm·RV_m(t)

용도: 변동성 타깃 사이징의 분모. 후행 실현변동성(rolling std)은 변동성이
치솟은 '다음 날'에야 비중을 줄이지만, 예측치는 군집의 초입에서 먼저 줄인다 —
같은 예측력으로 복리 손실을 줄이는 장치이며 수익 예측 장치가 아니다.

⚠️ 룩어헤드 없음: 각 시점의 예측은 그 이전 데이터로만 적합한 회귀를 쓴다
   (워크포워드, ML 전략과 같은 규약). 안전장치로 예측치를 후행 실현분산의
   [1/4, 4배] 범위로 클립한다 — 회귀가 폭주해도 사이징이 망가지지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def har_forecast_vol(returns: pd.Series, train_window: int = 250,
                     refit_every: int = 20, min_train: int = 100) -> pd.Series:
    """봉별 '다음 봉' 일 변동성(σ, 일 단위) 예측 시계열을 반환한다.

    반환 Series의 t번째 값 = t 시점까지의 정보로 예측한 t+1봉 변동성.
    적합 불가 구간(초기·퇴화 데이터)은 NaN — 호출자가 후행 변동성으로 폴백한다.
    """
    r = pd.to_numeric(returns, errors="coerce")
    rv = (r ** 2).astype(float)                    # 일 실현분산 프록시
    rv_d = rv
    rv_w = rv.rolling(5).mean()
    rv_m = rv.rolling(22).mean()
    X_all = np.column_stack([
        np.ones(len(rv)), rv_d.to_numpy(), rv_w.to_numpy(), rv_m.to_numpy()])
    y_next = rv.shift(-1).to_numpy()               # 타깃: 다음 봉 분산
    valid_x = np.isfinite(X_all).all(axis=1)

    n = len(rv)
    out = np.full(n, np.nan)
    coef = None
    i = min_train
    while i < n:
        # 학습 상한 i-1: 타깃 rv(t+1)이 있으려면 t ≤ i-2 — 예측 시점 i의
        # 정보(rv_i)는 학습에 쓰이지 않는다(엄격한 워크포워드).
        lo = max(0, i - train_window)
        rows = np.arange(lo, i - 1)
        rows = rows[valid_x[rows] & np.isfinite(y_next[rows])]
        if len(rows) >= min_train // 2:
            try:
                coef, *_ = np.linalg.lstsq(X_all[rows], y_next[rows], rcond=None)
            except np.linalg.LinAlgError:
                coef = None
        block_end = min(i + refit_every, n)
        if coef is not None:
            rows_p = np.arange(i, block_end)
            rows_p = rows_p[valid_x[rows_p]]
            if len(rows_p):
                out[rows_p] = X_all[rows_p] @ coef
        i = block_end

    pred_var = pd.Series(out, index=rv.index)
    # 안전 클립: 후행 20일 실현분산의 [1/4, 4배] — 회귀 폭주 방어
    base_var = rv.rolling(20).mean()
    pred_var = pred_var.clip(lower=base_var * 0.25, upper=base_var * 4.0)
    pred_var = pred_var.where(pred_var > 0)        # 0·음수 예측은 '모름'(NaN)
    return np.sqrt(pred_var).rename("har_vol")
