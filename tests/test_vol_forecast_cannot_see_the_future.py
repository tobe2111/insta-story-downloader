"""HAR 변동성 예측이 **미래를 보지 않고, 폭주해도 새지 않는가** (감사 147).

이 예측치는 변동성 타깃 사이징의 **분모**다. 예측이 절반으로 나오면 비중이
두 배가 된다. 그런데 변이를 처음 걸어 보니 둘 다 무방비였다.

    rows = np.arange(lo, i - 1)  →  np.arange(lo, n - 1)   ❌ 전 구간 학습
    pred.clip(base*0.25, base*4) →  clip(base*1e-6, 1e6)   ❌ 안전 클립 해제

기존 검사는 '폴드 과반 게이트'만 봤다 — 예측 자체의 성질은 아무도 안 봤다.

──────────────────────────────────────────────────────────────
룩어헤드를 어떻게 잡는가

값 하나를 못 박는 방식은 회귀 구조가 바뀌면 같이 바뀌어 쓸모가 없다.
대신 **접두사 안정성**을 본다:

    har(r)[:k]  ==  har(r[:k])

t시점 예측이 t 이후 데이터를 조금이라도 쓰면 이 등식이 깨진다. 어떤 경로로
새든 잡히는 검사다. 실측 — 정상 0.0 · 전 구간 학습 2.16e-2.

⚠️ 여기서 하나 배웠다. 처음 건 변이는 `np.arange(lo, i)`(학습 상한을 예측
   시점까지 한 봉 늘림)였는데 **룩어헤드가 아니다.** 그 한 봉의 타깃은
   rv[i]이고, 예측 시점 i에는 rv[i]가 이미 확정돼 있다. 값은 달라지지만
   (최대차 0.0039) 접두사 안정성은 그대로 0.0이다. 행동이 같은 변이를
   '놓침'으로 세면 존재하지 않는 피해를 못 박게 된다(FROZEN_IDEAS ㉚).
   그래서 진짜로 미래를 쓰는 변이(전 구간 학습)로 바꿔 걸었다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.risk.volforecast import har_forecast_vol  # noqa: E402

N = 400
IDX = pd.date_range("2025-01-01", periods=N, freq="D")


def _clustered() -> pd.Series:
    """변동성 군집이 있는 계열 — HAR이 의미를 갖는 최소 조건."""
    rng = np.random.default_rng(4)
    vol = 0.01 * np.exp(np.cumsum(rng.normal(0, 0.05, N)))
    return pd.Series(rng.normal(0, 1, N) * vol, index=IDX)


def _shocked() -> pd.Series:
    """평온하다가 이틀 크게 터지는 계열 — 회귀 계수가 폭주하는 조건."""
    rng = np.random.default_rng(4)
    r = pd.Series(rng.normal(0, 0.01, N), index=IDX)
    r.iloc[250] = 0.55       # 플래시 크래시 / 서킷브레이커급
    r.iloc[251] = -0.45
    return r


# ── 룩어헤드 ──────────────────────────────────────────────────


def test_the_forecast_prefix_does_not_change_when_the_future_arrives():
    """t시점 예측은 t 이후 데이터가 붙어도 그대로여야 한다."""
    r = _clustered()
    for k in (150, 220, 300):
        full = har_forecast_vol(r).iloc[:k].to_numpy()
        pre = har_forecast_vol(r.iloc[:k]).to_numpy()
        both = np.isfinite(full) & np.isfinite(pre)
        assert both.any(), f"k={k}: 비교할 예측이 하나도 없다 — 전제가 깨졌다"
        worst = float(np.max(np.abs(full[both] - pre[both])))
        assert worst == 0.0, (
            f"뒤에 {N - k}봉을 더 붙였더니 앞 {k}봉 예측이 최대 {worst:.3e} "
            "달라진다 — 예측이 미래를 보고 있다")


def test_the_forecast_actually_produces_numbers():
    """대조군 — 전부 NaN이면 위 검사가 공짜로 통과한다(0 == 0)."""
    v = har_forecast_vol(_clustered())
    assert v.notna().sum() > 200, f"유효 예측이 {v.notna().sum()}개뿐"
    assert (v.dropna() > 0).all(), "변동성 예측에 0·음수가 섞였다"


# ── 안전 클립 ─────────────────────────────────────────────────


def test_a_shock_cannot_blow_the_forecast_past_the_safety_clip():
    """예측은 후행 20일 변동성의 [1/2, 2]배 안에 있어야 한다.

    분산 기준 [1/4, 4]배 = 변동성 기준 [1/2, 2]배. 클립을 풀면 실측으로

        예측/후행 최대 5.34배 · **최소 0.001배**

    가 나온다. 위험한 쪽은 최소값이다 — 변동성 타깃은 이 값을 **분모**로
    쓰므로, 예측이 후행의 1/1000이면 비중이 1000배로 계산된다. 회귀가
    한 번 폭주하는 것으로 계좌가 끝날 수 있다.
    """
    r = _shocked()
    v = har_forecast_vol(r)
    trailing = np.sqrt((r ** 2).rolling(20).mean())
    ratio = (v / trailing).replace([np.inf, -np.inf], np.nan).dropna()
    assert len(ratio) > 100, f"비교 표본이 {len(ratio)}개뿐 — 전제가 깨졌다"
    assert ratio.max() <= 2.0 + 1e-9, (
        f"예측이 후행 변동성의 {ratio.max():.2f}배까지 튄다 — 상한 클립이 없다")
    assert ratio.min() >= 0.5 - 1e-9, (
        f"예측이 후행 변동성의 {ratio.min():.4f}배까지 내려간다 — 하한 클립이 "
        "없다. 이 값이 변동성 타깃의 분모라 비중이 그 역수만큼 커진다")


def test_the_clip_is_not_pinning_everything_to_one_value():
    """대조군 — 클립이 너무 좁아 예측이 후행의 복사본이 되면 장치가 무의미하다."""
    v = har_forecast_vol(_clustered())
    r = _clustered()
    ratio = (v / np.sqrt((r ** 2).rolling(20).mean())).dropna()
    assert ratio.std() > 0.05, (
        f"예측/후행 비율의 표준편차가 {ratio.std():.4f} — 예측이 후행을 "
        "그대로 따라가기만 한다(HAR을 쓸 이유가 없다)")
