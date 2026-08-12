"""드리프트 경보가 자기 잡음을 아는가 (감사 189).

`quant/robustness/drift.py` — 사이트의 "피처 드리프트 N종목" 경고를 만든다.
**결함 못 찾았다.** 확인한 것을 적어 둔다.

PSI의 0.1/0.25 문턱은 신용평가 업계 관행인데, 그 관행은 표본 수만 건 기준이다.
우리는 최근 60거래일로 잰다 — **드리프트가 전혀 없어도** 그 크기에서는
PSI 중앙값이 0.30쯤 나온다. 문턱을 그대로 쓰면 아무 일 없는 날의 절반이
'드리프트'로 찍힌다(감사 99에서 고쳤다).

실측 확인:

    같은 분포        PSI 0.003
    평균 +1 이동     PSI 1.028
    분산 3배         PSI 1.052
    상수·표본부족    NaN  ('계산 불가'를 0(안정)으로 위장하지 않는다)

    n=60 귀무분포   중앙 0.304 · 95% 0.957
    값 0.30 판정    n=60이면 '안정' · 큰 표본이면 '드리프트'
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.drift import interpret_psi, psi, psi_null  # noqa: E402


def _n(mu, sd, n, seed):
    return list(np.random.default_rng(seed).normal(mu, sd, n))


def test_the_same_distribution_scores_near_zero():
    assert psi(_n(0, 1, 2000, 1), _n(0, 1, 2000, 2)) < 0.05


def test_a_shifted_distribution_scores_high():
    """대조군 — 늘 0에 가까우면 이 경보는 아무것도 못 잡는다."""
    assert psi(_n(0, 1, 2000, 1), _n(1, 1, 2000, 3)) > 0.5
    assert psi(_n(0, 1, 2000, 1), _n(0, 3, 2000, 4)) > 0.5


def test_cannot_compute_is_nan_not_zero():
    """'계산 불가'를 0(안정)으로 위장하면 경보가 조용히 꺼진다."""
    assert math.isnan(psi([1.0] * 50, _n(0, 1, 100, 5)))   # 상수 기준
    assert math.isnan(psi([1.0, 2.0], _n(0, 1, 100, 5)))   # 표본 부족
    assert math.isnan(psi(_n(0, 1, 100, 5), []))           # 비교 표본 없음


def test_the_small_sample_null_is_far_above_the_textbook_threshold():
    """60거래일에서는 아무 일이 없어도 PSI가 0.3쯤 나온다 — 그게 핵심이다."""
    null = psi_null(60, 60)
    assert null["p50"] > 0.25, (
        f"귀무 중앙값이 {null['p50']:.3f} — 업계 문턱(0.25)보다 낮으면 "
        "이 보정이 필요 없다는 뜻이라 전제가 깨진다")
    assert null["p95"] > null["p50"]


def test_the_same_value_is_judged_differently_by_sample_size():
    """표본 크기를 모르면 잡음을 드리프트라 부른다(감사 99)."""
    assert "안정" in interpret_psi(0.30, n_ref=60, n_new=60)
    assert "드리프트" in interpret_psi(0.30)


def test_a_genuinely_large_shift_is_still_called_drift_at_small_n():
    """대조군 — 보정을 넣느라 진짜 드리프트까지 삼키면 안 된다."""
    got = interpret_psi(3.0, n_ref=60, n_new=60)
    assert "드리프트" in got, got


def test_the_null_distribution_is_deterministic():
    assert psi_null(60, 60) == psi_null(60, 60)
