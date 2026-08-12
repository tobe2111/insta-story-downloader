"""방송에서 말하는 숫자와 재현성 지문 (감사 187).

훑은 파일 — `live/explain.py` · `utils/repro.py` (둘 다 변이 1건이었다).

**결함 하나를 찾았다 — 보합을 말하지 않는다.**

`_band_pairs`는 "모델이 70%라 말한 날들 중 실제로 오른 비율"을 센다. 보합
(정확히 같은 가격)은 '오르지 않음'으로 세는데, 보정 곡선이라 **그 셈 자체는
옳다.** 문제는 **보합 빈도가 종목마다 다르다는 것**이다 — 거래정지·상하한가·
저유동 국내주식은 잦고 코인은 거의 없다.

실측(같은 '오를 때만 오른다' 성질):

    보합 4일 섞인 종목 → 상승 비율  56%
    보합 없는 종목     → 상승 비율 100%

감사 168에서 적중률에 대해 똑같은 것을 찾아 고쳐 놓고, **형제인 이 자리는
안 찾았다.** 이 문장은 방송·사이트에 그대로 나간다. 규칙도 그때와 같게 —
빼거나 숨기지 않고 **보합이 몇 날이었는지 함께 말한다.**

`repro.py`에서는 결함 못 찾음. 버전 범위 파서를 실제 `requirements.txt`로
확인했다(9개 패키지 전부 파싱, 위반 0건, 경계값 정상).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.explain import (  # noqa: E402
    MIN_BAND_SAMPLES, _band_accuracy, _band_pairs, _wilson_ci,
)
from quant.utils.repro import (  # noqa: E402
    declared_requirements, lock_violations, version_satisfies,
)


def _hist(prices, prob=0.7):
    return [{"prob_up": prob, "price": float(p)} for p in prices]


# ── 보합을 말하는가 ───────────────────────────────────────────


def test_a_sample_with_flat_days_says_so():
    """보합을 숨기면 '보합이 없었다'와 구별되지 않는다(감사 168과 같은 규칙)."""
    got = _band_accuracy(_hist([100, 101, 101, 102, 102, 103, 103,
                                104, 104, 105] * 4), 0.7)
    assert "보합" in got, f"보합이 섞였는데 말하지 않는다: {got}"
    assert "보합 16일 포함" in got, got


def test_a_sample_without_flat_days_stays_quiet():
    """대조군 — 없는 날까지 '보합 0일'이라 붙이면 문장이 지저분해진다."""
    got = _band_accuracy(_hist(range(100, 140)), 0.7)
    assert "보합" not in got, got
    assert "100%" in got


def test_the_flat_days_move_the_number_which_is_why_we_say_it():
    """이 검사가 헛돌지 않는다는 증거 — 보합이 실제로 숫자를 바꾼다."""
    flat = _band_pairs(_hist([100, 101, 101, 102, 102, 103, 103,
                              104, 104, 105]), 0.7, 0.10)
    clean = _band_pairs(_hist(range(100, 110)), 0.7, 0.10)
    assert sum(flat) / len(flat) < sum(clean) / len(clean), (
        "보합이 비율을 안 낮춘다 — 전제가 깨졌다")


def test_a_small_sample_shows_no_ratio_at_all():
    """25건 미만의 비율은 통계가 아니라 잡음이다."""
    got = _band_accuracy(_hist(range(100, 110)), 0.7)
    assert "축적 중" in got and "%p" in got
    assert "상승 비율" not in got, f"소표본인데 비율을 말한다: {got}"
    assert MIN_BAND_SAMPLES == 25


def test_the_pooled_sample_is_used_only_when_the_symbol_is_short():
    own = _hist(range(100, 110))                       # 9건 — 미달
    pooled = [_hist(range(100, 140)) for _ in range(2)]
    got = _band_accuracy(own, 0.7, pooled_history=pooled)
    assert "전 종목 합산" in got and "축적 중" in got, got


def test_the_confidence_interval_brackets_the_ratio():
    for p, n in ((0.5, 30), (1.0, 30), (0.0, 30), (0.75, 100)):
        lo, hi = _wilson_ci(p, n)
        assert 0.0 <= lo <= p <= hi <= 1.0, (p, n, lo, hi)
    assert _wilson_ci(0.5, 400)[1] - _wilson_ci(0.5, 400)[0] < \
        _wilson_ci(0.5, 30)[1] - _wilson_ci(0.5, 30)[0], (
        "표본이 커져도 구간이 안 좁아진다")


def test_records_without_a_probability_or_price_are_skipped():
    rows = [{"prob_up": None, "price": 100.0}, {"price": 101.0},
            {"prob_up": 0.7, "price": 0}, {"prob_up": 0.7, "price": 102.0},
            {"prob_up": 0.7, "price": 103.0}]
    assert _band_pairs(rows, 0.7, 0.10) == [1.0]


def test_a_probability_outside_the_band_is_not_counted():
    rows = _hist([100, 101], prob=0.2) + _hist([102, 103], prob=0.7)
    assert len(_band_pairs(rows, 0.7, 0.10)) <= 1


# ── 재현성 지문: 선언한 범위가 실제로 검사되는가 ──────────────


def test_every_pinned_package_declares_a_range():
    """범위 없는 줄은 `lock_violations`가 조용히 건너뛴다 — 잠금이 아니게 된다."""
    d = declared_requirements(str(ROOT / "requirements.txt"))
    assert d, "requirements.txt를 못 읽었다"
    empty = [k for k, v in d.items() if not v]
    assert not empty, f"버전 범위가 없어 검사에서 빠지는 패키지: {empty}"
    for name in ("pandas", "numpy", "scikit-learn", "scipy"):
        assert name in d, f"핵심 의존성 {name}이 선언에서 사라졌다"


def test_the_running_environment_is_inside_the_declared_range():
    assert lock_violations(str(ROOT / "requirements.txt")) == []


def test_a_violated_range_is_actually_reported(tmp_path):
    """⚠️ '위반 없음'만 확인하면 **검사를 꺼도 똑같아 보인다**(감사 187에서
    변이를 놓쳤다). 실제로 어기는 파일을 넣어 걸리는지 본다 — 대조군이다.
    """
    import pandas as pd

    req = tmp_path / "requirements.txt"
    req.write_text("pandas>=99,<100\n", encoding="utf-8")
    got = lock_violations(str(req))
    assert got, "지금 깔린 pandas가 >=99를 만족할 리 없는데 위반이 안 잡힌다"
    assert "pandas" in got[0] and pd.__version__ in got[0], got

    req.write_text("pandas>=0,<999\n", encoding="utf-8")
    assert lock_violations(str(req)) == [], "만족하는데도 위반이라 한다"


def test_version_comparison_handles_uneven_lengths_and_tails():
    assert version_satisfies("2.0.1", [(">=", "2")]) is True
    assert version_satisfies("2", [(">=", "2.0.1")]) is False
    assert version_satisfies("2.0.0rc1", [(">=", "2.0")]) is True
    assert version_satisfies("3.0.0", [("<", "3")]) is False
    assert version_satisfies("0.2.40", [(">=", "0.2.40"), ("<", "0.3")]) is True
    assert version_satisfies("0.3.0", [("<", "0.3")]) is False
