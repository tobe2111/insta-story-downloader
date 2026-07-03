"""머신러닝 전략 — '다음 봉 상승 확률'을 예측한다 (진짜 ML).

이것이 "AI 투자"의 정통 형태다. GPT 같은 LLM에게 매매를 맡기는 게 아니라,
과거 데이터로 **모델을 학습**시켜 확률을 추정한다. sklearn을 내 컴퓨터에서
돌리므로 API 토큰·요금이 전혀 들지 않는다.

    1. 피처: 수익률(다기간)·변동성 레짐·RSI·MACD·볼린저·거래량 z 등 (모두 '과거')
    2. 라벨: 다음 봉이 올랐는가(1) 내렸는가(0)
    3. 학습: 로지스틱회귀 / 랜덤포레스트 / 그라디언트부스팅 / 소프트보팅 앙상블
    4. 사이징: 상승확률을 목표비중으로 매핑 — 확신할수록 크게(conviction sizing)

⚠️ 룩어헤드 방지가 생명이다. 각 시점의 예측은 '그 이전' 데이터로만 학습한
모델을 쓴다(walk-forward). 미래를 조금이라도 훔쳐보면 백테스트만 화려하고
실전에서 무너진다. 그리고 ML도 수익을 보장하지 않는다 — 시장의 방향 예측
정확도 상한은 대개 52~55%에 불과하며, 대부분의 모델은 거래비용을 넘는 엣지를
내지 못한다. 반드시 워크포워드·몬테카를로로 검증할 것.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.strategies.rsi import rsi

# 학습에 쓰는 피처 순서(고정) — feature_importances 해석 시 이 순서를 참조한다.
FEATURE_NAMES = [
    "ret1", "ret5", "ret10", "vol", "vol_ratio", "rsi14", "rsi7",
    "ma_dist20", "ma_dist50", "mom20", "mom60", "macd_hist",
    "bb_pctb", "atr", "vol_z",
]


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _features(df: pd.DataFrame) -> pd.DataFrame:
    """과거 정보만으로 구성한 피처 행렬 (룩어헤드 없음).

    모든 값은 '해당 봉 종가까지'의 정보만 사용한다. 미래 봉을 참조하는 항목은
    하나도 없다. 결측이 있는 초기 구간은 상위 로직에서 무효 처리한다.
    """
    close = df["close"]
    high = df.get("high", close)
    low = df.get("low", close)
    volume = df.get("volume")

    ret1 = close.pct_change()
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    vol20 = ret1.rolling(20).std()
    vol60 = ret1.rolling(60).std()

    # MACD 히스토그램(가격 대비 정규화)
    macd_line = _ema(close, 12) - _ema(close, 26)
    macd_hist = (macd_line - _ema(macd_line, 9)) / close

    # 볼린저 %b: 밴드 내 위치 (0=하단, 1=상단)
    bb_std = close.rolling(20).std()
    bb_pctb = (close - (ma20 - 2 * bb_std)) / (4 * bb_std)

    # ATR 유사치(가격 대비 정규화된 평균 진폭)
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean() / close

    feats = pd.DataFrame(index=df.index)
    feats["ret1"] = ret1
    feats["ret5"] = close.pct_change(5)
    feats["ret10"] = close.pct_change(10)
    feats["vol"] = vol20
    feats["vol_ratio"] = vol20 / vol60            # 변동성 레짐(단기/장기)
    feats["rsi14"] = rsi(close, 14) / 100.0
    feats["rsi7"] = rsi(close, 7) / 100.0
    feats["ma_dist20"] = (close - ma20) / ma20
    feats["ma_dist50"] = (close - ma50) / ma50
    feats["mom20"] = close.pct_change(20)
    feats["mom60"] = close.pct_change(60)
    feats["macd_hist"] = macd_hist
    feats["bb_pctb"] = bb_pctb
    feats["atr"] = atr
    if volume is not None and float(volume.abs().sum()) > 0:
        vmean = volume.rolling(20).mean()
        vstd = volume.rolling(20).std()
        feats["vol_z"] = (volume - vmean) / vstd
    else:
        feats["vol_z"] = 0.0

    return feats[FEATURE_NAMES].replace([np.inf, -np.inf], np.nan)


def _build_model(kind: str):
    """모델 팩토리. sklearn 추정기를 반환한다.

    logreg : 스케일링 + 로지스틱회귀 (빠르고 견고, 기본값)
    rf     : 랜덤포레스트 (비선형·상호작용 포착)
    gb     : 히스토그램 그라디언트부스팅 (대개 가장 강력)
    vote   : 위 셋의 소프트보팅 앙상블 (확률 평균 → 분산 감소)
    """
    from sklearn.ensemble import (
        HistGradientBoostingClassifier,
        RandomForestClassifier,
        VotingClassifier,
    )
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def logreg():
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=500, class_weight="balanced"),
        )

    def rf():
        return RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=20,
            max_features="sqrt", class_weight="balanced_subsample",
            random_state=0, n_jobs=1)

    def gb():
        return HistGradientBoostingClassifier(
            max_depth=3, max_iter=200, learning_rate=0.05,
            l2_regularization=1.0, random_state=0)

    if kind == "rf":
        return rf()
    if kind == "gb":
        return gb()
    if kind in ("vote", "ensemble"):
        return VotingClassifier(
            estimators=[("lr", logreg()), ("rf", rf()), ("gb", gb())],
            voting="soft", n_jobs=1)
    return logreg()


class MLStrategy(Strategy):
    """워크포워드로 재학습하며 상승확률을 목표비중으로 매핑하는 ML 전략."""

    name = "ml"

    def __init__(self, model: str = "logreg", train_window: int = 250,
                 retrain_every: int = 20, threshold: float = 0.55,
                 sizing: str = "proba", min_train: int = 50,
                 allow_short: bool = False):
        self.model_kind = model
        self.train_window = train_window
        self.retrain_every = max(1, retrain_every)
        self.threshold = min(0.99, max(0.5, threshold))
        self.sizing = sizing            # "proba"(확신도 비례) | "binary"(0/1)
        self.min_train = max(30, min_train)
        self.allow_short = allow_short
        # 최근 학습 모델의 피처 중요도(있으면) — 사후 해석용
        self.last_importances_: dict[str, float] | None = None

    # ── 확률 → 목표비중 매핑 ────────────────────────────────────────────
    def _size(self, prob_up: np.ndarray) -> np.ndarray:
        """상승확률 배열을 [-1,1] 목표비중으로 변환한다.

        proba 모드: threshold를 데드존 경계로 두고 확신할수록 크게 태운다.
        binary 모드: 임계 넘으면 풀 포지션(1/-1), 아니면 관망(0).
        """
        if self.sizing == "binary":
            w = np.where(prob_up >= self.threshold, 1.0, 0.0)
            if self.allow_short:
                w = np.where(prob_up <= 1.0 - self.threshold, -1.0, w)
            return w

        gate = self.threshold - 0.5            # 데드존 반폭 (예: 0.05)
        span = max(1e-9, 0.5 - gate)           # 경계~확신(1.0)까지의 폭
        edge = prob_up - 0.5
        w = np.zeros_like(edge, dtype=float)
        long = edge > gate
        w[long] = np.clip((edge[long] - gate) / span, 0.0, 1.0)
        if self.allow_short:
            short = edge < -gate
            w[short] = -np.clip((-edge[short] - gate) / span, 0.0, 1.0)
        return w

    def _record_importances(self, model) -> None:
        """가능하면 피처 중요도/계수를 기록한다(해석용, 실패해도 무시)."""
        try:
            est = model
            if hasattr(est, "feature_importances_"):
                imp = np.asarray(est.feature_importances_, dtype=float)
            elif hasattr(est, "named_steps"):  # 파이프라인(logreg)
                clf = list(est.named_steps.values())[-1]
                imp = np.abs(np.asarray(clf.coef_, dtype=float)).ravel()
            else:
                return
            if len(imp) == len(FEATURE_NAMES):
                self.last_importances_ = dict(zip(FEATURE_NAMES, imp.tolist()))
        except Exception:  # noqa: BLE001  # pragma: no cover
            pass

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        try:
            import sklearn  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "ML 전략에는 scikit-learn이 필요합니다: pip install scikit-learn") from exc

        feats = _features(df)
        # 라벨: 다음 봉 상승 여부 (마지막 행은 미래가 없어 NaN)
        label = (df["close"].shift(-1) > df["close"]).astype(float)
        label[df["close"].shift(-1).isna()] = np.nan
        y = label.to_numpy()

        X = feats.fillna(0.0).to_numpy()
        valid = feats.notna().all(axis=1).to_numpy()
        n = len(df)
        out = np.zeros(n)
        model = None

        # 재학습 구간(블록) 단위로 학습→배치 예측: 행마다 예측하던 것보다 훨씬 빠르다.
        i = self.train_window
        while i < n:
            # j < i 이고 라벨이 확정된 표본만 사용 → 룩어헤드 없음
            mask = valid[:i] & ~np.isnan(y[:i])
            if mask.sum() >= self.min_train:
                yt = y[:i][mask].astype(int)
                if len(np.unique(yt)) > 1:      # 두 클래스 모두 있어야 학습 가능
                    model = _build_model(self.model_kind)
                    model.fit(X[:i][mask], yt)
                    self._record_importances(model)

            block_end = min(i + self.retrain_every, n)
            if model is not None:
                rows = np.arange(i, block_end)
                rows = rows[valid[i:block_end]]
                if len(rows):
                    prob_up = model.predict_proba(X[rows])[:, 1]
                    out[rows] = self._size(prob_up)
            i = block_end

        return self._finalize(pd.Series(out, index=df.index), df.index)
