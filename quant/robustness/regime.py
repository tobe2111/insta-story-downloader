"""시장 레짐(국면) 분류기 — 진단/피처용.

각 봉을 '추세 국면'(강세/약세)과 '변동성 국면'(고변동/저변동)으로 라벨링한다.
전략을 국면별로 나눠 평가하면 "이 전략은 강세장에서만 되는구나" 같은 통찰을
얻을 수 있고, 라벨을 ML 외부 피처로도 쓸 수 있다.

의존성 없이(numpy/pandas만) 동작하며, 모든 판정은 '과거' 정보만 사용한다:
    - 추세: 종가가 장기 이동평균 위/아래
    - 변동성: 최근 변동성이 '지금까지의' 분위수(expanding quantile) 이상인가
HMM 같은 무거운 모델을 쓰지 않아 개인 도구에 적합하고 과최적화 위험이 낮다.

⚠️ 이 분류기는 '지나고 나서 보면 어떤 국면이었나'를 정직하게 라벨링할 뿐,
미래 국면을 예측하지 않는다. 국면은 사후에야 확실해진다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def classify_regime(
    df: pd.DataFrame,
    trend_window: int = 200,
    vol_window: int = 20,
    vol_quantile: float = 0.8,
) -> pd.DataFrame:
    """봉별 추세/변동성 국면 라벨을 담은 DataFrame을 반환한다.

    컬럼: trend('bull'|'bear'|'unknown'), vol('high'|'low'|'unknown'),
          regime(둘의 결합, 예: 'bull_low').
    """
    close = df["close"]
    ma = close.rolling(trend_window).mean()
    trend = pd.Series("unknown", index=df.index, dtype=object)
    trend[close >= ma] = "bull"
    trend[close < ma] = "bear"

    ret = close.pct_change()
    vol = ret.rolling(vol_window).std()
    # '지금까지'의 분위수 → 미래를 보지 않음(룩어헤드 없음). 최소 표본 확보 후 판정.
    thresh = vol.expanding(min_periods=vol_window * 2).quantile(vol_quantile)
    volr = pd.Series("unknown", index=df.index, dtype=object)
    volr[(vol.notna()) & (thresh.notna()) & (vol >= thresh)] = "high"
    volr[(vol.notna()) & (thresh.notna()) & (vol < thresh)] = "low"

    regime = trend.str.cat(volr, sep="_")
    return pd.DataFrame({"trend": trend, "vol": volr, "regime": regime})


def regime_summary(df: pd.DataFrame, **kwargs) -> dict:
    """각 국면이 전체 기간에서 차지한 비율을 반환한다(진단용)."""
    reg = classify_regime(df, **kwargs)
    counts = reg["regime"].value_counts(normalize=True)
    return {k: float(v) for k, v in counts.items()}


def regime_feature(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """레짐을 숫자 피처로 인코딩한다 (MLStrategy(extra_features=...) 용).

    trend_up ∈ {0,1}, vol_high ∈ {0,1}. 미지(unknown)는 0.5(중립)로 둔다.
    """
    reg = classify_regime(df, **kwargs)
    trend_up = reg["trend"].map({"bull": 1.0, "bear": 0.0}).fillna(0.5)
    vol_high = reg["vol"].map({"high": 1.0, "low": 0.0}).fillna(0.5)
    return pd.DataFrame({"trend_up": trend_up, "vol_high": vol_high},
                        index=df.index).astype(float)
