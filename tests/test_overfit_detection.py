"""과최적화 탐지 도구 테스트 — PBO(CSCV)·CPCV·파라미터 안정성 점수.

핵심 검증: 순수 노이즈에서 '최적'을 골랐을 때 PBO≈0.5(동전던지기)가 나오고,
진짜 신호가 있는 설정은 낮은 PBO가 나오는지. CPCV는 여러 OOS 경로 분포를
실제로 만드는지. 안정성 점수는 '외딴 봉우리'를 감점하는지.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import SyntheticDataProvider
from quant.optimize import cpcv, cpcv_report, robust_best, stability_report, stability_scores
from quant.robustness import param_returns_matrix, pbo, pbo_report
from quant.strategies import MovingAverageCross


# ── PBO ──────────────────────────────────────────────────────────────────────

def test_pbo_pure_noise_near_half():
    """순수 노이즈 설정들 → IS 1등의 OOS 순위는 동전던지기 → PBO≈0.5."""
    rng = np.random.default_rng(7)
    m = pd.DataFrame(rng.normal(0.0, 0.01, size=(600, 20)))
    r = pbo(m, n_blocks=10)
    assert 0.25 < r["pbo"] < 0.75          # 노이즈면 0.5 근방(표본 오차 허용)
    assert r["n_combinations"] == 252       # C(10,5)


def test_pbo_true_signal_low():
    """한 설정에 진짜 엣지(평균 양수)를 심으면 PBO가 확실히 낮아진다."""
    rng = np.random.default_rng(11)
    m = pd.DataFrame(rng.normal(0.0, 0.01, size=(600, 20)))
    m[0] = rng.normal(0.004, 0.01, size=600)   # 강한 신호 하나
    r = pbo(m, n_blocks=10)
    assert r["pbo"] < 0.2
    assert r["mean_oos_rank"] > 0.7            # IS 1등이 OOS에서도 상위


def test_pbo_input_validation():
    with pytest.raises(ValueError):
        pbo(pd.DataFrame({"a": [0.1] * 100}))            # 설정 1개
    with pytest.raises(ValueError):
        pbo(pd.DataFrame(np.zeros((100, 3))), n_blocks=7)  # 홀수 블록
    with pytest.raises(ValueError):
        pbo(pd.DataFrame(np.zeros((20, 3))), n_blocks=10)  # 데이터 부족


def test_pbo_report_korean():
    rng = np.random.default_rng(3)
    m = pd.DataFrame(rng.normal(0, 0.01, size=(400, 8)))
    text = pbo_report(pbo(m, n_blocks=8))
    assert "PBO" in text and "보장" in text


def test_param_returns_matrix_shapes():
    df = SyntheticDataProvider(seed=9).get_ohlcv("P", "1d", limit=300)
    m = param_returns_matrix(df, MovingAverageCross,
                             {"fast": [5, 10], "slow": [30, 50]})
    assert m.shape == (300, 4)
    assert all("fast=" in c and "slow=" in c for c in m.columns)


def test_param_returns_matrix_skips_invalid():
    """fast>=slow 같은 잘못된 조합은 건너뛴다."""
    df = SyntheticDataProvider(seed=9).get_ohlcv("P", "1d", limit=200)
    m = param_returns_matrix(df, MovingAverageCross,
                             {"fast": [10, 60], "slow": [50, 100]})
    assert m.shape[1] == 3                      # (60,50) 제외


# ── CPCV ─────────────────────────────────────────────────────────────────────

def test_cpcv_produces_multiple_paths():
    df = SyntheticDataProvider(seed=5).get_ohlcv("C", "1d", limit=600)
    r = cpcv(df, MovingAverageCross, {"fast": [5, 10], "slow": [40, 60]},
             n_groups=6, n_test=2, embargo=5)
    assert r["n_combinations"] == 15            # C(6,2)
    assert r["n_paths"] == 5                    # C(5,1) — 그룹당 검증 5회
    assert len(r["paths"]) == 5
    for p in r["paths"]:
        assert np.isfinite(p["sharpe"]) and p["max_drawdown"] <= 0.0
    assert r["sharpe_min"] <= r["sharpe_mean"]


def test_cpcv_report_korean():
    df = SyntheticDataProvider(seed=5).get_ohlcv("C", "1d", limit=600)
    r = cpcv(df, MovingAverageCross, {"fast": [5], "slow": [40, 60]},
             n_groups=4, n_test=2, embargo=3)
    text = cpcv_report(r)
    assert "경로" in text and "보장" in text


def test_cpcv_input_validation():
    df = SyntheticDataProvider(seed=5).get_ohlcv("C", "1d", limit=100)
    with pytest.raises(ValueError):
        cpcv(df, MovingAverageCross, {"fast": [5], "slow": [40]},
             n_groups=4, n_test=4)              # n_test >= n_groups


# ── 파라미터 안정성 ──────────────────────────────────────────────────────────

def _fake_results():
    """3×3 그리드: (10,50)은 '외딴 봉우리'(2.0, 이웃 전부 0.1),
    (30,70) 주변은 '고원'(모두 1.0)."""
    rows = []
    for fast in (10, 20, 30):
        for slow in (50, 60, 70):
            if (fast, slow) == (10, 50):
                s = 2.0
            elif fast == 30 or slow == 70:
                s = 1.0
            else:
                s = 0.1
            rows.append({"fast": fast, "slow": slow, "sharpe": s})
    return rows


def test_stability_penalizes_isolated_peak():
    scored = stability_scores(_fake_results(), objective="sharpe")
    by = {(r["fast"], r["slow"]): r for r in scored}
    peak = by[(10, 50)]
    plateau = by[(30, 70)]
    # 봉우리: 원점수는 최고지만 이웃 평균이 깎여 robust는 고원보다 낮다
    assert peak["sharpe"] > plateau["sharpe"]
    assert peak["robust_score"] < plateau["robust_score"]
    best = robust_best(scored, objective="sharpe")
    assert best == {"fast": 30, "slow": 70}


def test_stability_report_flags_divergence():
    text = stability_report(stability_scores(_fake_results()), objective="sharpe")
    assert "외딴 봉우리" in text and "보장" in text


def test_stability_neighbor_counts():
    scored = stability_scores(_fake_results(), objective="sharpe")
    by = {(r["fast"], r["slow"]): r for r in scored}
    assert by[(20, 60)]["n_neighbors"] == 4     # 중앙 셀: 상하좌우
    assert by[(10, 50)]["n_neighbors"] == 2     # 모서리 셀


def test_stability_single_combo_no_crash():
    scored = stability_scores([{"fast": 5, "sharpe": 1.2}], objective="sharpe")
    assert scored[0]["robust_score"] == 1.2     # 이웃 없음 → 자기 점수
    assert robust_best(scored) == {"fast": 5}


# ── walk_forward DSR 통합 ────────────────────────────────────────────────────

def test_walk_forward_reports_dsr():
    from quant.optimize import walk_forward

    df = SyntheticDataProvider(seed=1).get_ohlcv("W", "1d", limit=500)
    wf = walk_forward(df, MovingAverageCross,
                      {"fast": [5, 10], "slow": [40, 60]},
                      is_window=250, oos_window=125)
    assert 0.0 <= wf["dsr"] <= 1.0
    assert wf["n_trials"] == 4                  # 2×2 그리드
