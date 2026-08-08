"""상세 해설(새벽 판단 근거 v2) 계약 검사.

핵심 계약:
  ① 판단 재료가 이름 나열이 아니라 '현재값 + 상태'로 나온다
  ② 원비중과 최종 비중이 다르면 사이징 사슬이 붙는다
  ③ 오늘 확률대의 과거 실제 적중률이 표본 3일 이상일 때만 붙는다
  ④ 해설 실패는 절대 예외를 내지 않는다(폴백 문장)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.explain import (  # noqa: E402
    _band_accuracy,
    _feature_note,
    explain_signal,
)
from quant.strategies import MLStrategy  # noqa: E402


def _df(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    ret = rng.normal(0.0005, 0.02, n)
    close = 100 * np.cumprod(1 + ret)
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1000.0 + rng.integers(0, 500, n)}, index=idx)


# ── ① 피처 현재값·상태 표기 ────────────────────────────────────


def test_feature_notes_are_human_readable():
    assert "과열권" in _feature_note("rsi14", 0.80)
    assert "과매도권" in _feature_note("rsi14", 0.20)
    assert "선 위" in _feature_note("ma_dist20", 0.03)
    assert "상승 우위" in _feature_note("macd_hist", 0.001)
    assert "변동성 확장 국면" in _feature_note("rv_5_60", 1.5)
    assert "상단 접근" in _feature_note("bb_pctb", 0.9)
    assert "롱 과열" in _feature_note("x_funding", 0.001)
    assert "일 2.0%" in _feature_note("gk_vol", 0.02)


def test_ml_explanation_includes_feature_values():
    df = _df()
    strat = MLStrategy(model="logreg", train_window=200, retrain_every=50)
    sig = strat.generate_signals(df)
    w = float(sig.iloc[-1])
    spec = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
    txt = explain_signal(spec, df, w, strat)
    assert "판단 재료:" in txt
    # 값이 붙는다 — 이름만 나열되는 구식 표기가 아니어야 한다
    assert any(tok in txt for tok in ("%", "우위", "국면", "중립", "접근"))


# ── ② 사이징 사슬 ──────────────────────────────────────────────


def test_sizing_chain_shown_when_risk_reduces_weight():
    df = _df()
    strat = MLStrategy(model="logreg", train_window=200, retrain_every=50)
    strat.generate_signals(df)
    spec = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
    txt = explain_signal(spec, df, 0.40, strat, raw_weight=0.80)
    assert "사이징: 신호 원비중 80%" in txt and "40%" in txt
    # 차이가 미미하면 사슬 생략(잡음 방지)
    txt2 = explain_signal(spec, df, 0.40, strat, raw_weight=0.41)
    assert "사이징:" not in txt2


# ── ③ 확률대 과거 적중률 ───────────────────────────────────────


def test_band_accuracy_min_25_samples_and_wilson_ci():
    def hist(n):                                     # 절반쯤 상승하는 장부
        return [{"prob_up": 0.7, "price": 100 + i + (i % 2)} for i in range(n)]
    # 25짝 미만: 숫자 대신 '표본 축적 중 (n=X)' — 잡음이 확신처럼 안 보이게
    out = _band_accuracy(hist(9), 0.72)              # 8짝
    assert "표본 축적 중" in out and "종목 n=8" in out
    assert "실제 상승 비율" not in out
    assert "종목 n=0" in _band_accuracy([], 0.7)
    # 확률대가 멀면(±10%p 밖) 표본에 안 잡힌다 → n=0 축적 중
    assert "종목 n=0" in _band_accuracy(hist(9), 0.45)
    # 25짝 이상: 비율 + 윌슨 95% 신뢰구간 병기
    out = _band_accuracy(hist(30), 0.72)             # 29짝
    assert "실제 상승 비율" in out and "95% 신뢰구간" in out
    assert "표본 축적 중" not in out


def test_wilson_ci_bounded_and_sane():
    from quant.live.explain import _wilson_ci
    lo, hi = _wilson_ci(0.5, 25)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    assert hi - lo < 0.45                            # n=25에서 폭이 유한
    lo0, hi0 = _wilson_ci(0.0, 25)                   # 극단 비율도 [0,1] 안
    assert lo0 == 0.0 and hi0 > 0.0
    lo1, hi1 = _wilson_ci(1.0, 25)
    assert hi1 == 1.0 and lo1 < 1.0


# ── ④ 실패 안전 ────────────────────────────────────────────────


def test_explain_never_raises_on_garbage():
    txt = explain_signal({"strategy": "ml", "params": {}}, None, 0.3, None)
    assert "—" in txt                                # 폴백 문장이라도 나온다


def test_band_accuracy_pooled_fallback():
    """종목 표본 미달 + 합산 25건 이상 → '전 종목 합산' 통계로 폴백."""
    own = [{"prob_up": 0.7, "price": 100 + i} for i in range(5)]      # 4짝
    pool = [[{"prob_up": 0.7, "price": 100 + i + (i % 2)} for i in range(16)]
            for _ in range(2)]                                        # 30짝
    out = _band_accuracy(own, 0.72, pooled_history=pool)
    assert "전 종목 합산" in out and "95% 신뢰구간" in out
    assert "단독 표본은 4건" in out
    # 합산도 미달이면 양쪽 카운트를 밝힌 축적 중 문구
    out2 = _band_accuracy(own, 0.72, pooled_history=pool[:1][:1])
    assert "표본 축적 중" in out2 and "종목 n=4" in out2


def test_daily_passes_pooled_history():
    """daily가 합산 장부를 해설에 전달한다(연결 계약)."""
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "pooled_history=_all_paper_histories" in src
