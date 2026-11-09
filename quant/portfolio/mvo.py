"""기관식 포트폴리오 구성 — 알파 결합 · 수축 위험 모델 · 제약 최적화 (2026-11-10 감사 367).

사장님: *"로직도 대기업급으로 해줘 가장 이상적으로"*

대형 운용사의 포트폴리오 구성은 "점수 높은 것을 담는다"가 아니라 세 겹이다.

  ① **알파 결합** — 서로 다른 근거의 신호를 같은 눈금(횡단면 z)으로 맞춰 더한다.
     여기서는 문헌에서 가장 오래 살아남은 둘만 쓴다: 시계열 추세(여러 기간 수익의
     부호)와 횡단면 모멘텀(12-1개월). 가중치는 **같게** 둔다 — 결합 비중을 과거
     성적으로 맞추면 그 자리가 곧 과최적화다.
  ② **기대수익의 눈금** — 그리놀드의 기본 법칙 α = IC × σ × z. IC는 0.05로
     **고정**한다(맞추지 않는다). 최적화는 α의 상대 크기만 쓰고, 전체 크기는 아래
     ④의 목표 변동성이 정하므로 IC 값 자체는 결과를 거의 바꾸지 않는다.
  ③ **위험 모델** — 표본 공분산은 종목 수(최대 ~90)가 날 수(252)에 비해 많아
     잡음이 크다. 레도이트-울프 수축(표본 공분산을 대각 목표 쪽으로 데이터가
     정한 만큼 당긴다)으로 추정한다. 같이 움직이는 둘을 따로 세지 않게 하는 것이
     이 모델의 일이다 — 균등·역변동성 배분은 그걸 못 한다.
  ④ **제약 최적화** — max αᵀw − ½λ·wᵀΣw, 0 ≤ w ≤ 한 종목 상한, Σw ≤ 1(빚 없음).
     λ는 사람이 고르지 않는다 — 사전 변동성이 목표(12%)에 닿도록 이분법으로 정한다.

■ 정직한 한계

  · 이것은 **새 수익원이 아니다.** 같은 두 신호를 더 잘 담는 방법이다. 위험 대비
    효율이 좋아질 수 있지만, 이 저장소의 실측(감사 336·342)은 신호 자체가 생존
    편향을 빼면 얇다고 말한다 — 담는 기술이 그걸 바꾸지 못한다.
  · 비용은 최적화 안에 넣지 않았다 — 이전 비중에 묶는 회전 벌점은 경로 의존이라
    검증(긴 역사)과 매일 배치(400봉)가 다른 답을 낸다(학습·서빙 불일치). 비용은
    검증과 실계좌가 **같은 곳**(무거래 밴드 · 종목별 실측 편도 · 환전)에서 뗀다.
  · 롱 전용이다(본 계좌는 현물 — CLAUDE.md 하락장 ②).
  · 채택은 사람이 안 한다 — 엔진 후보(`mvo12` · `mvo12w`)로 다른 후보와 같은 관문
    (낙폭 −20% 자격 · t 문턱 · 넓은 목록 확인)을 지나야 실계좌가 따른다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.portfolio import trend_core as T

IC = 0.05                 # 그리놀드 기본 법칙의 정보 계수 — 고정(맞추지 않는다)
RISK_WINDOW = 252         # 위험 모델에 쓰는 날 수
MIN_ASSETS = 4            # 이보다 적으면 횡단면 z가 뜻이 없다 — 현금
Z_CLIP = 3.0


def _zscore(s: pd.Series) -> pd.Series:
    s = s.dropna()
    if len(s) < 2:
        return s * 0.0
    sd = float(s.std(ddof=0))
    if not sd > 0:
        return s * 0.0
    return ((s - s.mean()) / sd).clip(-Z_CLIP, Z_CLIP)


def shrunk_cov(window: pd.DataFrame) -> np.ndarray:
    """레도이트-울프 수축 공분산(연율). 결측이 있는 줄은 뺀다."""
    from sklearn.covariance import LedoitWolf
    x = window.dropna(how="any").values
    if len(x) < 20:
        raise ValueError("위험 모델 표본 부족")
    return LedoitWolf().fit(x).covariance_ * T.PERIODS


def _project(w: np.ndarray, cap: float, budget: float) -> np.ndarray:
    """0 ≤ w ≤ cap, Σw ≤ budget 위로의 유클리드 사영(정확해).

    예산이 묶이면 해는 clip(w − τ, 0, cap)이고 Σ가 τ에 대해 구간별 선형이라
    꺾이는 점(w_i, w_i − cap)에서 값을 재 구간을 찾고 직선으로 푼다.
    """
    p = np.clip(w, 0.0, cap)
    if p.sum() <= budget:
        return p
    bp = np.unique(np.concatenate([w, w - cap]))
    g = np.clip(w[None, :] - bp[:, None], 0.0, cap).sum(axis=1)   # bp 오름차순 → g 내림차순
    j = int(np.searchsorted(-g, -budget))      # g[j] <= budget < g[j-1]
    if j <= 0:
        tau = float(bp[0])
    else:
        t0, t1, g0, g1 = bp[j - 1], bp[j], g[j - 1], g[j]
        tau = float(t0 + (g0 - budget) * (t1 - t0) / (g0 - g1)) if g0 != g1 else float(t1)
    return np.clip(w - tau, 0.0, cap)


def _solve(alpha: np.ndarray, cov: np.ndarray, lam: float, cap: float,
           budget: float, top_eig: float, w0=None, iters: int = 80) -> np.ndarray:
    """사영 경사법 — 볼록 이차계획이라 보폭 1/L에서 수렴한다(따뜻한 시작 허용)."""
    step = 1.0 / (lam * top_eig + 1e-12)
    w = np.zeros_like(alpha) if w0 is None else w0.copy()
    for _ in range(iters):
        w = _project(w + step * (alpha - lam * (cov @ w)), cap, budget)
    return w


def _bisect_lambda(f, lo: float = 1e-2, hi: float = 1e4, n: int = 14) -> float:
    """f(λ)가 참인 가장 작은 λ(로그 눈금). f는 λ에 대해 단조(작을수록 거짓)."""
    for _ in range(n):
        mid = float(np.sqrt(lo * hi))
        if f(mid):
            hi = mid
        else:
            lo = mid
    return hi


def optimize(alpha: np.ndarray, cov: np.ndarray, target_vol: float,
             cap: float, budget: float = 1.0) -> np.ndarray:
    """λ를 사람이 고르지 않는다 — 두 조건 중 더 보수적인 쪽(큰 λ)을 쓴다.

    · λ_vol: 사전 변동성이 목표 이하가 되는 가장 작은 λ.
    · λ_budget: 예산 제약이 **없을 때** 비중 합이 1 이하가 되는 가장 작은 λ.
      ⚠️ 빚을 못 내는 계좌에서 목표 변동성에 못 닿으면 λ_vol이 0으로 내려가
      평균-분산이 '기대수익 상위 몇 개를 상한까지'라는 모서리 답이 된다(위험
      모델을 버리고 추정 오차를 최대화하는 교과서적 실패). λ를 λ_budget 아래로
      안 내리면 예산을 다 쓰면서도 위험 모델이 분산을 정한다.
    """
    if not (alpha > 0).any():
        return np.zeros_like(alpha)
    top = float(np.linalg.eigvalsh(cov).max())
    vol = lambda w: float(np.sqrt(max(w @ cov @ w, 0.0)))      # noqa: E731
    lam_b = _bisect_lambda(
        lambda l: _solve(alpha, cov, l, cap, np.inf, top).sum() <= budget)
    lam_v = _bisect_lambda(
        lambda l: vol(_solve(alpha, cov, l, cap, budget, top)) <= target_vol)
    return _solve(alpha, cov, max(lam_b, lam_v), cap, budget, top, iters=400)


def alpha_frames(closes: pd.DataFrame, lookbacks=T.LOOKBACKS):
    """(추세 −1~1, 12-1 모멘텀) — 둘 다 그날 종가까지만 본다(과거 shift만 쓴다)."""
    trend = pd.DataFrame({k: T.trend_score(closes[k], lookbacks) for k in closes.columns}
                         ) * 2.0 - 1.0
    mom = closes.shift(T.XS_SKIP) / closes.shift(T.XS_LOOKBACK) - 1.0
    return trend, mom


def alpha_scores(trend: pd.Series, mom: pd.Series, vol: pd.Series) -> pd.Series:
    """그날의 결합 z(추세 + 12-1 모멘텀, 같은 비중)."""
    ok = trend.notna() & mom.notna() & vol.notna() & (vol > 0)
    keys = list(ok[ok].index)
    if len(keys) < MIN_ASSETS:
        return pd.Series(dtype=float)
    return 0.5 * _zscore(trend[keys]) + 0.5 * _zscore(mom[keys])


def _decision_days(index: pd.DatetimeIndex, rule: str) -> pd.Series:
    """계산할 날 — 검증의 리밸런스 날 ∪ 실계좌의 목표일(`engine_select.target_day`)
    후보 날짜(주 단위면 금요일) ∪ 마지막 날. 나머지 날은 아무도 읽지 않는다."""
    rb = T._rebalance_days(index, rule)
    fri = pd.Series((index.dayofweek == 4) & (rule not in ("M", "D")), index=index)
    last = pd.Series(index == index[-1], index=index)
    return rb | fri | last


def mvo_weights(closes: pd.DataFrame, cfg: T.TrendConfig | None = None) -> pd.DataFrame:
    """날짜 × 자산의 목표 비중. 결정하지 않는 날은 0(검증·실계좌 모두 그날을 안 읽는다)."""
    cfg = cfg or T.TrendConfig()
    rets = closes.pct_change(fill_method=None)
    vol = rets.ewm(halflife=cfg.vol_halflife, min_periods=cfg.vol_halflife
                   ).std() * np.sqrt(T.PERIODS)
    out = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    if len(closes) == 0:
        return out
    days = _decision_days(closes.index, cfg.rebalance)
    trend, mom = alpha_frames(closes, cfg.lookbacks)
    for i, day in enumerate(closes.index):
        if not days.iloc[i]:
            continue
        z = alpha_scores(trend.loc[day], mom.loc[day], vol.loc[day])
        if z.empty:
            continue
        keys = list(z.index)
        win = rets.iloc[max(0, i - RISK_WINDOW + 1): i + 1][keys]
        try:
            cov = shrunk_cov(win)
        except ValueError:
            continue
        alpha = IC * vol.loc[day, keys].values * z.values
        w = optimize(alpha, cov, cfg.target_vol, cfg.asset_cap, cfg.max_gross)
        out.loc[day, keys] = w
    return out
