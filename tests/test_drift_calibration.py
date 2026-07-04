"""피처 드리프트(PSI) + 확률 보정 진단 테스트 (손으로 계산한 값과 대조)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.robustness.calibration import (
    brier_score,
    calibration_bins,
    calibration_summary,
)
from quant.robustness.drift import (
    drift_summary,
    feature_drift_report,
    interpret_psi,
    psi,
)

# ── PSI ─────────────────────────────────────────────────────────────────


def test_psi_identical_distributions_is_zero():
    vals = list(range(1, 101))
    assert psi(vals, vals, bins=10) == pytest.approx(0.0, abs=1e-12)


def test_psi_shifted_distribution_flags_drift():
    expected = list(range(1, 101))
    actual = [200.0] * 100                    # 전부 학습 범위 밖 → 극단 드리프트
    value = psi(expected, actual, bins=10)
    assert value > 0.25
    assert interpret_psi(value) == "드리프트"


def test_psi_hand_computed_value():
    """expected 균등 10구간, actual 전부 마지막 구간 — 손계산 값과 대조."""
    expected = list(range(1, 101))            # 각 구간 비율 정확히 0.1
    actual = [200.0] * 50
    eps = 1e-4
    manual = 9 * (0.1 - eps) * math.log(0.1 / eps) + (0.1 - 1.0) * math.log(0.1 / 1.0)
    assert psi(expected, actual, bins=10) == pytest.approx(manual, rel=1e-9)


def test_psi_zero_count_bins_no_blowup():
    """한쪽에만 값이 있는 구간이 있어도 epsilon 보정으로 유한값을 낸다."""
    value = psi(list(range(100)), [0.0, 1.0, 2.0], bins=10)
    assert math.isfinite(value)


def test_psi_degenerate_inputs_return_nan():
    assert math.isnan(psi([1.0] * 100, [1.0] * 100))       # 상수 피처
    assert math.isnan(psi(list(range(100)), []))           # actual 없음
    assert math.isnan(psi([1.0, 2.0], [1.0], bins=10))     # 표본 < bins


def test_psi_ignores_nan_values():
    vals = list(range(1, 101))
    with_nan = vals + [float("nan")] * 20
    assert psi(with_nan, with_nan, bins=10) == pytest.approx(0.0, abs=1e-12)


def test_feature_drift_report_and_summary():
    train = pd.DataFrame({"a": range(100), "b": range(100)})
    recent = pd.DataFrame({"a": range(100), "b": [500.0] * 100})
    report = feature_drift_report(train, recent)
    assert set(report) == {"a", "b"}
    assert report["a"] == pytest.approx(0.0, abs=1e-12)
    assert report["b"] > 0.25
    text = drift_summary(report)
    assert "드리프트" in text and "PSI" in text
    assert "보장" in text or "재학습" in text       # 정직한 안내 포함


# ── 확률 보정 ────────────────────────────────────────────────────────────


def test_brier_score_hand_computed():
    y_true = [1, 0, 1, 0]
    y_prob = [0.8, 0.2, 0.6, 0.4]
    # ((0.2)^2 + (0.2)^2 + (0.4)^2 + (0.4)^2) / 4 = 0.1
    assert brier_score(y_true, y_prob) == pytest.approx(0.1, rel=1e-12)


def test_brier_score_bounds():
    assert brier_score([1, 0], [1.0, 0.0]) == 0.0          # 완벽
    assert brier_score([1, 0], [0.5, 0.5]) == pytest.approx(0.25)  # 무지한 상수
    assert math.isnan(brier_score([], []))


def test_brier_score_validates_inputs():
    with pytest.raises(ValueError):
        brier_score([1, 0], [0.5])            # 길이 불일치
    with pytest.raises(ValueError):
        brier_score([1], [1.5])               # 확률 범위 밖


def test_calibration_bins_hand_computed():
    y_true = [1, 0, 1, 0]
    y_prob = [0.8, 0.2, 0.6, 0.4]
    rows = calibration_bins(y_true, y_prob, bins=2)
    assert len(rows) == 2
    lo, hi = rows
    assert lo["count"] == 2 and lo["mean_prob"] == pytest.approx(0.3)
    assert lo["frac_positive"] == 0.0
    assert hi["count"] == 2 and hi["mean_prob"] == pytest.approx(0.7)
    assert hi["frac_positive"] == 1.0


def test_calibration_bins_prob_one_in_last_bin():
    rows = calibration_bins([1], [1.0], bins=10)
    assert rows[-1]["count"] == 1             # p=1.0이 인덱스 밖으로 새지 않는다
    assert sum(r["count"] for r in rows) == 1


def test_calibration_summary_flags_overconfidence():
    # 모델이 0.9를 말하지만 실제 양성은 30%뿐 — 과대확신
    y_prob = [0.9] * 10
    y_true = [1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    text = calibration_summary(y_true, y_prob)
    assert "과대확신" in text and "브라이어" in text


def test_calibration_summary_honest_when_calibrated():
    y_prob = [0.5] * 10
    y_true = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    text = calibration_summary(y_true, y_prob)
    assert "보장" in text                     # 보정이 좋아도 수익 보장 아님을 고지
