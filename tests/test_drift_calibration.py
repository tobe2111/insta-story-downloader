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


# ── 확률 보정은 '표시 전용'이다 — 사이징에 개입하지 않는다 (감사 62) ──
#
# recalibrated_prob은 "60%라고 한 날 실제 적중률이 45%였다"는 경험 보정을
# 화면에 병기한다. 규약은 명확하다: **보여주기만 하고 비중은 건드리지
# 않는다.** 모델의 말과 경험을 나란히 두는 것이 목적이고, 보정값으로
# 사이징까지 하면 그날부터 장부의 '판단'과 '표시'가 서로 다른 것을
# 가리키게 된다.
#
# 변이 시험에서 보정값을 비중에 대입해도(`weight = float(adj)`) 아무 검사가
# 실패하지 않았다. 규약은 주석에만 있었다.


def test_calibration_never_moves_the_recorded_weight(monkeypatch, tmp_path):
    import json as _json

    import numpy as _np
    import pandas as _pd

    from quant.live import daily as dl

    rng = _np.random.default_rng(8)
    close = 100 * _np.exp(_np.cumsum(rng.normal(0.0004, 0.02, 300)))
    idx = _pd.date_range("2025-01-01", periods=300, freq="D")
    bars = _pd.DataFrame({"open": close, "high": close * 1.01,
                          "low": close * 0.99, "close": close,
                          "volume": 1e6}, index=idx)

    class _P:
        def get_ohlcv(self, *a, **k):
            return bars.copy()

    class _S:
        """ML 챔피언 흉내 — last_proba_가 있어야 prob_up이 기록된다."""

        name = "fixed"
        allow_short = False
        last_proba_ = 0.62

        def generate_signals(self, df):
            return _pd.Series(0.8, index=df.index)

    def _run(state_dir, adjusted):
        monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
        monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _S())
        monkeypatch.setattr(dl, "champion_spec",
                            lambda *a, **k: {"strategy": "fixed", "params": {}})
        monkeypatch.setattr(
            "quant.live.calibration_guard.recalibrated_prob",
            # **kw — 운영 호출이 휴장일 달력을 함께 넘긴다(감사 247).
            # 위치 인자만 받는 가짜를 두면 TypeError가 나는데, 운영 코드의
            # except가 그걸 삼켜서 이 검사가 조용히 헛돈다.
            lambda p, h, **kw: ((0.01, True) if adjusted else (p, False)))
        dl.run_daily_paper("synthetic", "DEMO", state_dir=str(state_dir),
                           require_real_data=False)
        st = _json.loads((state_dir / "paper" / "synthetic_DEMO.json")
                         .read_text(encoding="utf-8"))
        return st["history"][-1]

    off = _run(tmp_path / "off", adjusted=False)
    on = _run(tmp_path / "on", adjusted=True)

    # 보정이 확률을 0.8 → 0.01로 뒤집어도 비중은 한 톨도 움직이면 안 된다
    assert on["weight"] == off["weight"], (
        f"보정이 비중을 움직였다: {off['weight']} → {on['weight']} "
        "— 확률 보정은 표시 전용이다")
    assert on["prob_up_cal"] == 0.01, "보정값이 기록되지 않았다(전제 확인)"
    assert "prob_up_cal" not in off, "보정 비활성인데 값이 기록됐다"


def test_calibration_is_documented_as_display_only():
    from pathlib import Path as _P
    src = (_P(__file__).resolve().parent.parent / "quant" / "live"
           / "daily.py").read_text(encoding="utf-8")
    block = src.split("recalibrated_prob")[0][-600:]
    assert "표시 전용" in block or "사이징에는 개입하지 않" in block
