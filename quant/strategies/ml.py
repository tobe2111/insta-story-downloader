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
    # fs2 — 변동성 구조: 고가·저가를 쓰는 Garman-Klass 추정량(같은 기간에
    # 종가 표준편차보다 정확)과 단기/장기 실현변동성 비율(레짐 신호).
    "gk_vol", "rv_5_60",
]

# 피처셋 버전 — 피처를 '가설 그룹' 단위로 추가·기록하기 위한 태그.
# 재학습 장부에 함께 남겨, 성과 변화가 어느 피처 배치 이후인지 추적 가능하다.
#   fs1: 기본 15개 (가격 유도 지표)
#   fs2: +변동성 구조(gk_vol, rv_5_60) +코인 펀딩비(x_funding, 컬럼 있을 때)
FEATURE_SET = "fs2:+volstruct+funding"


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _features(df: pd.DataFrame, extra: pd.DataFrame | None = None) -> pd.DataFrame:
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
    # Garman-Klass 변동성(고저가 활용) — 하루 봉 하나에서도 분산 정보를 뽑아
    # 종가 표준편차보다 같은 윈도에서 추정 오차가 작다. 가격 유도지만 OHLC
    # 4개를 모두 쓰는 유일한 변동성 추정량이라 vol(종가 std)과 정보가 다르다.
    opn = df.get("open", close)
    log_hl = np.log((high / low).replace([np.inf, -np.inf], np.nan))
    log_co = np.log((close / opn).replace([np.inf, -np.inf], np.nan))
    gk_var = 0.5 * log_hl ** 2 - (2 * np.log(2) - 1) * log_co ** 2
    feats["gk_vol"] = np.sqrt(gk_var.rolling(20).mean().clip(lower=0.0))
    # 단기/장기 실현변동성 비율(5일/60일) — 1보다 크면 변동성 확장 국면.
    # 사이징의 변동성 타깃팅과 같은 재료를 예측 피처로도 재사용한다.
    feats["rv_5_60"] = ret1.rolling(5).std() / vol60
    if volume is not None and float(volume.abs().sum()) > 0:
        vmean = volume.rolling(20).mean()
        vstd = volume.rolling(20).std()
        feats["vol_z"] = (volume - vmean) / vstd
    else:
        feats["vol_z"] = 0.0

    out = feats[FEATURE_NAMES].copy()
    # 코인 펀딩비 — 데이터 로더가 df에 'funding' 컬럼을 붙여 준 경우에만 쓴다.
    # 가격에서 유도할 수 없는 진짜 신규 정보(포지셔닝 과열도)이며, 컬럼으로
    # 받는 이유는 재현성 때문이다: 입력 스냅샷(csv.gz)에 함께 보존돼
    # verify가 같은 피처로 그날의 결정을 재현할 수 있다.
    if "funding" in df.columns:
        out["x_funding"] = pd.to_numeric(df["funding"], errors="coerce").ffill()
    # 외부(거시) 피처 병합 — 예: 공포탐욕지수, 펀딩비, 금리. 날짜로 정렬 후
    # 전진충전(ffill)한다. 해당 봉 시점까지 알려진 값만 쓰므로 룩어헤드 없음.
    if extra is not None and len(extra.columns):
        ext = extra.reindex(df.index).ffill()
        for col in extra.columns:
            out[f"x_{col}"] = ext[col]
    return out.replace([np.inf, -np.inf], np.nan)


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
                 allow_short: bool = False, extra_features=None,
                 calibrate: str | None = None, weight_step: float = 0.0):
        if calibrate not in (None, "sigmoid", "isotonic"):
            raise ValueError(
                f"calibrate는 None·'sigmoid'·'isotonic' 중 하나여야 합니다: {calibrate!r}")
        self.model_kind = model
        self.train_window = train_window
        self.retrain_every = max(1, retrain_every)
        self.threshold = min(0.99, max(0.5, threshold))
        self.sizing = sizing            # "proba"(확신도 비례) | "binary"(0/1)
        self.min_train = max(30, min_train)
        self.allow_short = allow_short
        # 확률 보정: 학습창 내부 3-겹 CV로 CalibratedClassifierCV를 적합한다.
        # ⚠️ 보정은 엣지를 만들지 않는다 — 모델이 말하는 70%가 실제 70%가 되게
        # 맞출 뿐이며, 과대확신 확률로 사이징할 때의 기하(복리) 손실을 줄이는
        # 용도다. 기본 None = 기존 동작 그대로.
        self.calibrate = calibrate
        # Δ비중 양자화 격자(예: 0.1). 확률의 미세한 흔들림이 매 봉 소량 매매로
        # 새는 것을 막는 회전율 절감 장치 — 수익 개선 장치가 아니다. 0 = 끔(기존).
        self.weight_step = max(0.0, float(weight_step))
        # 외부(거시) 피처: DataFrame 또는 callable(df)->DataFrame. 예: 공포탐욕지수.
        self.extra_features = extra_features
        # 최근 학습에 쓰인 피처 이름(기본 15개 + 외부 피처)
        self.feature_names_: list[str] = list(FEATURE_NAMES)
        # 최근 학습 모델의 피처 중요도(있으면) — 사후 해석용
        self.last_importances_: dict[str, float] | None = None
        # 마지막 봉의 예측 상승확률 — 신뢰도 곡선(보정 검증) 기록용
        self.last_proba_: float | None = None

    # ── 확률 → 목표비중 매핑 ────────────────────────────────────────────
    def _size(self, prob_up: np.ndarray) -> np.ndarray:
        """상승확률 배열을 [-1,1] 목표비중으로 변환한다.

        proba 모드: threshold를 데드존 경계로 두고 확신할수록 크게 태운다.
                    weight_step>0이면 결과를 격자에 반올림(양자화)한다.
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
        if self.weight_step > 0.0:
            # Δ비중 양자화: 확률 지터로 인한 소량 리밸런스 주문을 죽인다.
            # 가장 가까운 격자점으로 반올림 → 오차는 step/2 이내, 경계는 유지.
            w = np.clip(np.round(w / self.weight_step) * self.weight_step, -1.0, 1.0)
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
            if len(imp) == len(self.feature_names_):
                self.last_importances_ = dict(zip(self.feature_names_, imp.tolist()))
        except Exception:  # noqa: BLE001  # pragma: no cover
            pass

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        try:
            import sklearn  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "ML 전략에는 scikit-learn이 필요합니다: pip install scikit-learn") from exc

        extra = self.extra_features
        if callable(extra):
            extra = extra(df)
        feats = _features(df, extra)
        self.feature_names_ = list(feats.columns)
        # 라벨: 다음 봉 상승 여부 (마지막 행은 미래가 없어 NaN)
        label = (df["close"].shift(-1) > df["close"]).astype(float)
        label[df["close"].shift(-1).isna()] = np.nan
        y = label.to_numpy()

        # 외부 피처(x_*)의 결측은 0으로 대치한다(아래 valid는 기본 피처만 보므로
        # 이 대치가 실제로 쓰인다). 0은 이상적 중립값은 아니지만, 외부 피처가
        # 아직 시작 전인 구간에서 상수(정보 없음)로 취급돼 무해하다.
        X = feats.fillna(0.0).to_numpy()
        # ⚠️ valid는 '기본 15개 피처'만으로 판정한다. 외부 피처까지 AND에 넣으면,
        # 외부 피처가 시작 전(예: 공포탐욕지수는 ~2018년부터)이거나 정렬이 어긋나
        # NaN인 구간이 학습·예측에서 통째로 빠져 모델이 '조용히 전 구간 무거래'가
        # 된다(에러도 없이). 외부 피처는 선택적 맥락일 뿐 필수가 아니다.
        base_cols = [c for c in feats.columns if c in FEATURE_NAMES]
        valid = feats[base_cols].notna().all(axis=1).to_numpy()
        n = len(df)
        out = np.zeros(n)
        probs = np.full(n, np.nan)     # 봉별 예측확률 — 신뢰도 곡선(보정 검증)용
        model = None

        # 재학습 구간(블록) 단위로 학습→배치 예측: 행마다 예측하던 것보다 훨씬 빠르다.
        i = self.train_window
        while i < n:
            # 최근 train_window봉만 학습에 사용(롤링) → 옛 국면을 버리고 학습량도 O(n²)로
            # 커지지 않는다. 상한을 i-1로 두어 라벨(y[j]=close[j+1]>close[j])이 예측
            # 대상 봉을 침범하지 않게 한다(엄격한 룩어헤드 차단).
            lo = max(0, i - self.train_window)
            hi = i - 1
            mask = valid[lo:hi] & ~np.isnan(y[lo:hi])
            if mask.sum() >= self.min_train:
                yt = y[lo:hi][mask].astype(int)
                if len(np.unique(yt)) > 1:      # 두 클래스 모두 있어야 학습 가능
                    model = _build_model(self.model_kind)
                    # 확률 보정: 학습창 '내부'의 3-겹 CV로만 적합 → 룩어헤드 없음.
                    # 소수 클래스 표본이 3 미만이면 3-겹 층화 CV가 불가능하므로
                    # 그 블록만 비보정 모델로 학습한다(조용한 실패 대신 명시적 규칙).
                    if self.calibrate is not None and np.bincount(yt).min() >= 3:
                        from sklearn.calibration import CalibratedClassifierCV
                        model = CalibratedClassifierCV(
                            model, method=self.calibrate, cv=3)
                    model.fit(X[lo:hi][mask], yt)
                    self._record_importances(model)

            block_end = min(i + self.retrain_every, n)
            if model is not None:
                rows = np.arange(i, block_end)
                rows = rows[valid[i:block_end]]
                if len(rows):
                    prob_up = model.predict_proba(X[rows])[:, 1]
                    out[rows] = self._size(prob_up)
                    probs[rows] = prob_up
            i = block_end

        # 마지막 봉(오늘 판단)의 예측확률 — 매일 기록에 남겨, "AI가 60%라고
        # 한 날들의 실제 적중률"(신뢰도 곡선)을 사이트에서 검증할 수 있게 한다.
        self.last_proba_ = (float(probs[-1])
                            if n and np.isfinite(probs[-1]) else None)
        return self._finalize(pd.Series(out, index=df.index), df.index)
