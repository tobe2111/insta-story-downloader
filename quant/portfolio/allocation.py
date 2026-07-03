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


_SCHEMES = {
    "equal": equal_weight,
    "inverse_vol": inverse_vol,
}


def get_scheme(name: str):
    if name not in _SCHEMES:
        raise ValueError(f"알 수 없는 배분 방식: {name}. 사용 가능: {list(_SCHEMES)}")
    return _SCHEMES[name]


def list_schemes() -> list[str]:
    return list(_SCHEMES)
