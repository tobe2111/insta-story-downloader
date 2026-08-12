"""부트스트랩이 표본의 앞부분을 조용히 깎고 있었다 (감사 188).

블록 부트스트랩은 수익률의 자기상관을 보존하려고 **연속 구간(블록)** 단위로
재추출한다. 두 구현 모두 이렇게 잘랐다.

    idx.extend(range(start, min(start + block, n)))     # compare.py
    out.extend(r[start : start + block])                # monte_carlo.py

블록은 `start ≤ j`인 자리에서만 j를 담는다. 그래서 **앞쪽 원소는 들어갈
블록 자체가 적다.** 실측(n=100 · block=10 · 2만 회):

    index 0    0.108×      (균등이면 1.00×)
    앞 10개    0.584×
    중간·뒤    1.05×

표본의 앞부분이 **절반 무게로 깎인다.** 이게 어디에 쓰이냐면:

  · `compare.py` — 챔피언을 바꿀지 정하는 **A/B 유의성 검정**. 초반이 다른
    국면이었다면(워밍업·다른 레짐) 그 구간만 빠진 채 판정이 난다.
  · `monte_carlo.py` — 사이트에 찍히는 **'무작위 대비 백분위'의 분모**.
    비교 기준이 흔들리면 우리 성적의 위치도 흔들린다.

끝에서 자르지 않고 **앞으로 감으면**(modulo) 모든 인덱스의 포함 확률이
같아진다(원형 블록 부트스트랩). 자기상관 보존이라는 목적은 그대로다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.compare import _block_indices, compare_strategies  # noqa: E402
from quant.robustness.monte_carlo import _block_bootstrap  # noqa: E402

N, BLOCK, DRAWS = 100, 10, 8000


def _coverage(sampler) -> np.ndarray:
    """각 인덱스가 뽑힌 상대 빈도 — 균등이면 전부 1.0 근처."""
    rng = np.random.default_rng(0)
    cnt = np.zeros(N)
    for _ in range(DRAWS):
        for i in sampler(rng):
            cnt[int(i)] += 1
    return cnt / cnt.sum() * N


def test_every_bar_has_the_same_chance_of_being_resampled():
    """앞부분이 덜 뽑히면 그 구간의 사실이 판정에서 조용히 빠진다."""
    cov = _coverage(lambda rng: _block_indices(N, rng, BLOCK))
    assert cov[0] > 0.9, (
        f"첫 봉의 표집 빈도가 {cov[0]:.3f}× — 블록을 끝에서 자르고 있다")
    assert cov[:BLOCK].mean() > 0.95, (
        f"앞 {BLOCK}개 평균 {cov[:BLOCK].mean():.3f}× — 앞부분이 깎였다")
    assert cov.min() > 0.9 and cov.max() < 1.1, (
        f"표집이 균등하지 않다: 최소 {cov.min():.3f} · 최대 {cov.max():.3f}")


def test_the_random_benchmark_resampler_is_uniform_too():
    """형제 — 사이트의 '무작위 대비 백분위'가 이 표집 위에 서 있다."""
    r = np.arange(N, dtype=float)
    cov = _coverage(lambda rng: _block_bootstrap(r, rng, BLOCK))
    assert cov[0] > 0.9, f"첫 봉 {cov[0]:.3f}×"
    assert cov.min() > 0.9 and cov.max() < 1.1, (cov.min(), cov.max())


def test_the_resample_still_keeps_runs_together():
    """대조군 — 균등하게 고치느라 블록 구조를 잃으면 자기상관 보존이 죽는다."""
    rng = np.random.default_rng(1)
    idx = _block_indices(N, rng, BLOCK)
    steps = np.diff(idx)
    consecutive = int((steps == 1).sum())
    assert consecutive >= len(steps) * 0.7, (
        f"연속으로 이어진 자리가 {consecutive}/{len(steps)}뿐 — 블록이 아니라 "
        "낱개 재추출이 됐다")


def test_the_resample_has_the_right_length():
    rng = np.random.default_rng(2)
    for n in (7, 50, 100):
        assert len(_block_indices(n, rng, 10)) == n
        assert len(_block_bootstrap(np.arange(n, dtype=float), rng, 10)) == n


def test_every_index_stays_in_range():
    """감아 돌리다 범위를 넘으면 IndexError나 엉뚱한 봉을 읽는다."""
    rng = np.random.default_rng(3)
    for n, blk in ((7, 10), (100, 10), (100, 1)):
        idx = _block_indices(n, rng, blk)
        assert idx.min() >= 0 and idx.max() < n, (n, blk, idx.min(), idx.max())


# ── A/B 검정의 계약 ───────────────────────────────────────────


def test_two_identical_series_are_never_called_significantly_different():
    r = np.random.default_rng(4).normal(0, 0.01, 300)
    got = compare_strategies(r, r.copy(), n_sims=400, seed=1)
    assert got["significant"] is False
    assert abs(got["sharpe_diff"]) < 1e-9
    assert got["paired"] is True


def test_a_clearly_better_series_is_called_significant():
    """대조군 — 늘 '유의하지 않다'면 이 검정은 아무 말도 안 하는 것과 같다."""
    rng = np.random.default_rng(5)
    base = rng.normal(0, 0.01, 300)
    got = compare_strategies(base + 0.004, base, n_sims=400, seed=1)
    assert got["significant"] is True, got
    assert got["sharpe_diff"] > 0 and got["ci_low"] > 0
    assert got["prob_a_better"] > 0.9


def test_the_same_seed_gives_the_same_answer():
    """재현성이 이 저장소의 전제다 — 같은 입력이면 같은 판정이어야 한다."""
    a = np.random.default_rng(6).normal(0, 0.01, 200)
    b = np.random.default_rng(7).normal(0, 0.01, 200)
    x = compare_strategies(a, b, n_sims=200, seed=11)
    y = compare_strategies(a, b, n_sims=200, seed=11)
    assert x == y
