"""포트폴리오 자산배분(allocation) 방식.

전략이 각 종목의 '방향(롱/숏/관망)'을 정하면, 여기서 '각 종목에 자본을
얼마나 배분할지'를 정한다. 분산투자는 공짜 점심에 가장 가까운 것으로,
동일 기대수익에서 변동성을 낮춰 장기 복리를 개선한다.

모든 함수는 동일 시그니처를 따른다:
    fn(returns: DataFrame, signals: DataFrame, window: int) -> weights DataFrame
컬럼 = 종목, 값 = 목표 비중(부호 포함). 각 시점 |비중| 합이 대략 1을 넘지 않게 정규화.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def equal_weight(returns: pd.DataFrame, signals: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """활성(신호≠0) 종목에 자본을 균등 배분한다."""
    direction = np.sign(signals)
    active = (signals.abs() > 0).astype(float)
    n = active.sum(axis=1).replace(0, np.nan)
    magnitude = active.div(n, axis=0).fillna(0.0)
    return (direction * magnitude).fillna(0.0)


def inverse_vol(returns: pd.DataFrame, signals: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """변동성 역가중(리스크 패리티 근사).

    변동성이 낮은 종목에 더 많이 배분해 각 종목의 리스크 기여를 균등화한다.
    """
    vol = returns.rolling(window).std()
    inv = (1.0 / vol).replace([np.inf, -np.inf], np.nan)
    inv = inv.where(signals.abs() > 0, 0.0).fillna(0.0)
    total = inv.sum(axis=1).replace(0, np.nan)
    magnitude = inv.div(total, axis=0).fillna(0.0)
    return (np.sign(signals) * magnitude).fillna(0.0)


def _inv_var_weights(cov: pd.DataFrame) -> pd.Series:
    """역분산 가중 (HRP 실패 시 폴백)."""
    ivp = 1.0 / np.diag(cov.values)
    ivp = np.where(np.isfinite(ivp) & (ivp > 0), ivp, 0.0)
    s = ivp.sum()
    if s <= 0:
        ivp = np.ones(len(cov)) / len(cov)
    else:
        ivp = ivp / s
    return pd.Series(ivp, index=cov.index)


def _cluster_var(cov: pd.DataFrame, items: list) -> float:
    sub = cov.loc[items, items]
    w = _inv_var_weights(sub).values
    return float(w @ sub.values @ w)


def _quasi_diag(link) -> list:
    """계층 클러스터 링크를 준대각(quasi-diagonal) 순서로 펼친다 (López de Prado)."""
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = link[-1, 3]
    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= num_items]
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]
        df0 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df0]).sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    return sort_ix.tolist()


def _hrp_weights(win: pd.DataFrame) -> pd.Series:
    """한 구간의 수익률로 HRP 가중치(합=1, 롱 온리)를 계산한다.

    상관관계를 계층적으로 군집화해 준대각으로 정렬한 뒤, 재귀적 이분할로
    역분산 배분한다. 공분산 역행렬을 쓰지 않아 상관 급변장에서도 안정적이다.
    실패(자산<2, 특이 공분산, scipy 부재)하면 역분산 가중으로 폴백한다.
    """
    cols = list(win.columns)
    cov = win.cov()
    if len(cols) < 2 or not np.isfinite(cov.values).all():
        return _inv_var_weights(cov) if len(cols) else pd.Series(dtype=float)
    try:
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform

        corr = win.corr().fillna(0.0)
        dist = np.sqrt(((1.0 - corr) / 2.0).clip(lower=0.0).values)
        np.fill_diagonal(dist, 0.0)
        link = linkage(squareform(dist, checks=False), method="single")
        order = [cols[i] for i in _quasi_diag(link)]
    except Exception:  # noqa: BLE001  # scipy 부재/특이값 → 폴백
        return _inv_var_weights(cov)

    w = pd.Series(1.0, index=order)
    clusters = [order]
    while clusters:
        nxt = []
        for c in clusters:
            if len(c) <= 1:
                continue
            half = len(c) // 2
            left, right = c[:half], c[half:]
            v_left, v_right = _cluster_var(cov, left), _cluster_var(cov, right)
            alpha = 1.0 - v_left / (v_left + v_right) if (v_left + v_right) > 0 else 0.5
            w[left] *= alpha
            w[right] *= 1.0 - alpha
            nxt += [left, right]
        clusters = nxt
    return w.reindex(cols).fillna(0.0)


def hrp(returns: pd.DataFrame, signals: pd.DataFrame, window: int = 60,
        rebalance: int = 21) -> pd.DataFrame:
    """계층적 리스크 패리티(HRP) 배분.

    최근 window봉 수익률로 HRP 가중을 구하고 rebalance봉마다 갱신한다(과거만
    사용 → 룩어헤드 없음). 활성(신호≠0) 종목으로 마스킹·재정규화한 뒤 방향을 곱한다.
    """
    cols = list(returns.columns)
    n = len(returns)
    base = pd.DataFrame(0.0, index=returns.index, columns=cols)
    last = None
    for i in range(n):
        if i >= window and (last is None or i % max(1, rebalance) == 0):
            last = _hrp_weights(returns.iloc[i - window:i])
        if last is not None:
            base.iloc[i] = last.reindex(cols).fillna(0.0).values

    active = (signals.abs() > 0).astype(float)
    w = base * active.values
    total = w.sum(axis=1).replace(0, np.nan)
    magnitude = w.div(total, axis=0).fillna(0.0)
    return (np.sign(signals) * magnitude).fillna(0.0)


_SCHEMES = {
    "equal": equal_weight,
    "inverse_vol": inverse_vol,
    "hrp": hrp,
}


def get_scheme(name: str):
    if name not in _SCHEMES:
        raise ValueError(f"알 수 없는 배분 방식: {name}. 사용 가능: {list(_SCHEMES)}")
    return _SCHEMES[name]


def list_schemes() -> list[str]:
    return list(_SCHEMES)
