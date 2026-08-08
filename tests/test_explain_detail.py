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


def test_band_accuracy_needs_min_samples_and_matches():
    hist = [{"prob_up": 0.7, "price": 100 + i + (i % 2)}  # 절반 상승
            for i in range(8)]
    out = _band_accuracy(hist, 0.72)
    assert "실제 상승 비율" in out and "표본 적음" in out
    assert _band_accuracy(hist[:4], 0.72) != ""      # 4기록 = 3짝 → 표시
    assert _band_accuracy(hist[:3], 0.72) == ""      # 3기록 = 2짝 → 숨김
    assert _band_accuracy([], 0.7) == ""
    # 확률대가 멀면(±10%p 밖) 집계되지 않는다
    assert _band_accuracy(hist, 0.45) == ""


# ── ④ 실패 안전 ────────────────────────────────────────────────


def test_explain_never_raises_on_garbage():
    txt = explain_signal({"strategy": "ml", "params": {}}, None, 0.3, None)
    assert "—" in txt                                # 폴백 문장이라도 나온다
