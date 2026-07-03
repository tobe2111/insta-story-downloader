"""머신러닝 전략 — '다음 봉 상승 확률'을 예측한다 (진짜 ML).

이것이 "AI 투자"의 정통 형태다. GPT 같은 LLM에게 매매를 맡기는 게 아니라,
과거 데이터로 **모델을 학습**시켜 확률을 추정한다:

    1. 피처: 과거 수익률·RSI·변동성·이평선 거리·모멘텀 (모두 '과거' 정보)
    2. 라벨: 다음 봉이 올랐는가(1) 내렸는가(0)
    3. 학습: 로지스틱 회귀 / 랜덤 포레스트가 확률을 배움
    4. 신호: 상승확률 > threshold 면 매수, < 1-threshold 면 청산/숏

⚠️ 룩어헤드 방지가 생명이다. 각 시점의 예측은 '그 이전' 데이터로만 학습한
모델을 쓴다(walk-forward). 미래를 조금이라도 훔쳐보면 백테스트만 화려하고
실전에서 무너진다. 그리고 ML도 수익을 보장하지 않는다 — 대부분의 모델은
거래비용을 넘는 엣지를 내지 못한다. 반드시 워크포워드·몬테카를로로 검증할 것.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.strategies.rsi import rsi


def _features(df: pd.DataFrame) -> pd.DataFrame:
    """과거 정보만으로 구성한 피처 행렬 (룩어헤드 없음)."""
    close = df["close"]
    ret1 = close.pct_change()
    ma20 = close.rolling(20).mean()
    feats = pd.DataFrame(index=df.index)
    feats["ret1"] = ret1
    feats["ret5"] = close.pct_change(5)
    feats["vol"] = ret1.rolling(20).std()
    feats["rsi"] = rsi(close, 14) / 100.0
    feats["ma_dist"] = (close - ma20) / ma20
    feats["mom"] = close.pct_change(20)
    return feats


def _build_model(kind: str):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if kind == "rf":
        return RandomForestClassifier(
            n_estimators=80, max_depth=4, random_state=0, n_jobs=1)
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))


class MLStrategy(Strategy):
    name = "ml"

    def __init__(self, model: str = "logreg", train_window: int = 250,
                 retrain_every: int = 20, threshold: float = 0.55,
                 allow_short: bool = False):
        self.model_kind = model
        self.train_window = train_window
        self.retrain_every = max(1, retrain_every)
        self.threshold = threshold
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        try:
            import sklearn  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "ML 전략에는 scikit-learn이 필요합니다: pip install scikit-learn") from exc

        feats = _features(df)
        close = df["close"].to_numpy()
        # 라벨: 다음 봉 상승 여부 (마지막 행은 미래가 없어 NaN)
        label = (df["close"].shift(-1) > df["close"]).astype(float)
        label[df["close"].shift(-1).isna()] = np.nan
        y = label.to_numpy()

        X = feats.fillna(0.0).to_numpy()
        valid = feats.notna().all(axis=1).to_numpy()
        n = len(df)
        out = np.zeros(n)
        model = None

        for i in range(n):
            # 주기적으로, 그리고 충분한 과거가 쌓였을 때만 재학습
            need_fit = model is None or (i % self.retrain_every == 0)
            if i >= self.train_window and need_fit:
                # j < i 이고 (라벨 알려짐: j+1<=i) 인 표본만 사용 → 룩어헤드 없음
                mask = valid[:i] & ~np.isnan(y[:i])
                if mask.sum() >= 50:
                    yt = y[:i][mask].astype(int)
                    if len(np.unique(yt)) > 1:  # 두 클래스 모두 있어야 학습 가능
                        model = _build_model(self.model_kind)
                        model.fit(X[:i][mask], yt)

            if model is not None and valid[i]:
                prob_up = float(model.predict_proba(X[i:i + 1])[0, 1])
                if prob_up >= self.threshold:
                    out[i] = 1.0
                elif prob_up <= 1.0 - self.threshold:
                    out[i] = -1.0 if self.allow_short else 0.0

        return self._finalize(pd.Series(out, index=df.index), df.index)
