"""ML 종목 순위 엔진 — 다음 달 상대 성적을 기계가 배운다 (2026-11-09 감사 362).

사장님: *"머신러닝도 최고급 대기업급으로."*

⚠️ 먼저 정직하게 — 대형 퀀트의 ML이 이기는 이유는 모델이 아니라 **남이 못 구하는
데이터·검증 규율·규모**다. 이 저장소의 종목별 ML은 11,721회 시행에 승격 2회,
DSR 통과 0종목이었다. 그러니 여기서 들여오는 것은 '더 큰 모델'이 아니라 **규율**이다:

  ① **패널로 배운다** — 종목 하나의 시계열이 아니라 같은 날의 여러 자산을 나란히
     놓고 "누가 상대적으로 나을까"를 배운다(횡단면 순위). 표본이 자산 수만큼 는다.
  ② **특징도 정답도 날짜마다 순위로 바꾼다** — 시장 전체가 오르내리는 몫을 지우고
     상대 성적만 남긴다. 규모가 다른 시기를 한 모델이 배울 수 있다.
  ③ **정답 구간이 판단 시점을 넘는 줄은 학습에서 뺀다**(퍼지) — 다음 달 수익이
     정답이므로, 판단일 d에 쓸 수 있는 학습 줄은 정답 구간이 d 이전에 끝난 것뿐이다.
  ④ **워크포워드** — 1년마다 그때까지의 자료로만 다시 학습한다. 3년치가 쌓이기 전에는
     아무것도 담지 않는다.
  ⑤ **결정적** — 같은 자료면 같은 답(난수 고정).
  ⑥ 채택은 이 모듈이 정하지 않는다. 엔진 후보로 링에 서서 다른 후보와 **같은 관문**
     (낙폭 −20% · 넓은 목록 · 유의성 · 최소 유지)을 지나야 실계좌가 따른다.

담는 방식은 상대 강세 엔진과 같다(상위 25% · 이중 모멘텀 · 역변동성 · 목표 변동성 ·
한 종목 상한) — 그래야 두 엔진의 차이가 **고르는 눈**의 차이만 된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.portfolio import trend_core as T

HORIZON_NAME = "다음 달(월말→월말)"
MIN_TRAIN_MONTHS = 36
REFIT_EVERY = 12
FEATURES = ("mom21", "mom63", "mom126", "mom252", "mom_skip", "vol63", "trend", "ma200")


def month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    rb = T._rebalance_days(index, "M")
    return index[rb.values]


def features(closes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """날짜 × 자산 특징(그날 종가까지만). 날짜마다 순위(0~1)로 바꾼다."""
    rets = closes.pct_change(fill_method=None)
    raw = {
        "mom21": closes / closes.shift(21) - 1,
        "mom63": closes / closes.shift(63) - 1,
        "mom126": closes / closes.shift(126) - 1,
        "mom252": closes / closes.shift(252) - 1,
        "mom_skip": closes.shift(21) / closes.shift(252) - 1,
        "vol63": rets.rolling(63, min_periods=40).std(),
        "trend": pd.DataFrame({k: T.trend_score(closes[k]) for k in closes.columns}),
        "ma200": closes / closes.rolling(200, min_periods=150).mean() - 1,
    }
    return {k: v.rank(axis=1, pct=True) for k, v in raw.items()}, raw["mom252"]


def _model():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(max_depth=3, max_iter=150, learning_rate=0.05,
                                         l2_regularization=1.0, min_samples_leaf=40,
                                         random_state=0)


def scores(closes: pd.DataFrame) -> pd.DataFrame:
    """월말마다 예측 점수(자산별). 그날까지의 정답만으로 학습한 모델로."""
    feats, _ = features(closes)
    me = month_ends(closes.index)
    out = pd.DataFrame(np.nan, index=me, columns=closes.columns)
    px = closes.loc[me]
    fwd = (px.shift(-1) / px - 1).rank(axis=1, pct=True)        # 정답: 다음 월말까지 순위
    X_at = {d: np.column_stack([feats[f].loc[d].values for f in FEATURES]) for d in me}
    model, fitted_at = None, None
    for i, d in enumerate(me):
        # ③ 퍼지 — 정답 구간(me[j] → me[j+1])이 d 이전에 끝난 줄만
        usable = me[: max(0, i)]        # j+1 <= i  ⇔  j <= i-1
        if len(usable) < MIN_TRAIN_MONTHS:
            continue
        if model is None or (i - fitted_at) >= REFIT_EVERY:
            Xs, ys = [], []
            for dj in usable:
                X, y = X_at[dj], fwd.loc[dj].values
                ok = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
                if ok.sum() >= 4:
                    Xs.append(X[ok]); ys.append(y[ok])
            if not Xs:
                continue
            model = _model().fit(np.vstack(Xs), np.concatenate(ys))
            fitted_at = i
        X = X_at[d]
        ok = ~np.isnan(X).any(axis=1)
        if ok.sum() >= 4:
            out.loc[d, closes.columns[ok]] = model.predict(X[ok])
    return out


def ml_weights(closes: pd.DataFrame, cfg: T.TrendConfig | None = None) -> pd.DataFrame:
    """월말 점수 → 목표 비중(상대 강세와 같은 담는 방식). 다른 날은 직전 월말 그대로."""
    cfg = cfg or T.TrendConfig()
    sc = scores(closes)
    _, mom252 = features(closes)
    rets = closes.pct_change(fill_method=None)
    vol = rets.ewm(halflife=cfg.vol_halflife, min_periods=cfg.vol_halflife).std() * np.sqrt(T.PERIODS)
    out = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for d in sc.index:
        s = sc.loc[d].dropna()
        v = vol.loc[d]
        s = s[v.reindex(s.index).notna() & (v.reindex(s.index) > 0)]
        if len(s) < 4:
            continue
        k = max(1, int(round(len(s) * T.XS_TOP)))
        pick = s.sort_values(ascending=False).iloc[:k]
        pick = pick[mom252.loc[d].reindex(pick.index) > 0]       # 이중 모멘텀(상대 강세와 같다)
        if pick.empty:
            continue
        w = 1.0 / v[pick.index]
        w = w / w.sum()
        i = closes.index.get_loc(d)
        win = rets.iloc[max(0, i - cfg.cov_window + 1): i + 1][list(w.index)]
        cov = win.cov() * T.PERIODS
        if cov.isna().values.any():
            cov = pd.DataFrame(np.diag(v[w.index] ** 2), index=w.index, columns=w.index)
        ex = float(np.sqrt(max(w.values @ cov.values @ w.values, 0.0)))
        if ex > 0:
            w = w * (cfg.target_vol / ex)
        w = w.clip(upper=cfg.asset_cap)
        if w.sum() > cfg.max_gross:
            w = w * (cfg.max_gross / w.sum())
        out.loc[d, w.index] = w.values
    me = set(sc.index)
    mask = pd.Series([d in me for d in closes.index], index=closes.index)
    return out.where(mask, np.nan).ffill().fillna(0.0)
