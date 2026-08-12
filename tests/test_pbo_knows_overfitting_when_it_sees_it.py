"""PBO가 **아는 답을 맞히는가** (감사 145).

PBO(과적합 확률)는 "IS에서 1등이던 설정이 OOS에서도 상위권인가"를 묻는다.
이 값이 검증 리포트의 종합 판정과 flag_watch의 과적합 경보로 이어진다.

변이를 처음 걸어 보니 **핵심 셋이 전부 무방비**였다.

    best = np.argmax(sr_is)    →  np.argmax(sr_oos)    ❌ PBO가 구조적으로 0
    pbo  = (lam <= 0).mean()   →  (lam >= 0).mean()    ❌ 과적합을 건전으로 보고
    for is_idx in combinations(range(S), S//2)         ❌ 조합 하나로 줄여도 통과
                               →  [tuple(range(S//2))]

기존 검사는 "0과 1 사이의 값이 나온다", "조합 수가 맞다" 같은 **형식**만
봤다. 값이 옳은지는 아무도 확인하지 않았다.

그래서 이 파일은 **정답을 아는 데이터** 셋을 만들어 못 박는다.

    ① 순수 잡음      → 선택이 노이즈를 고른다        PBO ≈ 0.5  (실측 0.575)
    ② 진짜 우위 하나 → IS 1등이 OOS서도 1등          PBO ≈ 0    (실측 0.000)
    ③ 블록 패리티 교대 → IS 승자가 OOS서 최하위       PBO ≈ 1    (실측 1.000)

③이 이 지표의 존재 이유다. 두 설정이 서로 반대 블록에서만 좋으면, 어떤
조합으로 나누든 IS 승자는 OOS에서 진다 — 성과가 아니라 **분할 운**을 고른
것이다. PBO는 그것을 1.0으로 말해야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.pbo import pbo  # noqa: E402

T, S = 400, 10
IDX = pd.date_range("2025-01-01", periods=T, freq="D")


def _noise(seed: int = 7, cols: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({f"c{i}": rng.normal(0, 0.01, T) for i in range(cols)},
                        index=IDX)


def _with_real_edge() -> pd.DataFrame:
    df = _noise()
    df["star"] = np.random.default_rng(99).normal(0.004, 0.01, T)
    return df


def _alternating() -> pd.DataFrame:
    """A는 짝수 블록에서만, B는 홀수 블록에서만 좋다 — 전형적 과적합 함정."""
    edges = np.linspace(0, T, S + 1, dtype=int)
    a, b = np.zeros(T), np.zeros(T)
    for k in range(S):
        lo, hi = edges[k], edges[k + 1]
        a[lo:hi] = 0.01 if k % 2 == 0 else -0.01
        b[lo:hi] = -0.01 if k % 2 == 0 else 0.01
    rng = np.random.default_rng(3)
    return pd.DataFrame({"A": a, "B": b,
                         "n1": rng.normal(0, 0.0005, T),
                         "n2": rng.normal(0, 0.0005, T)}, index=IDX)


# ── 정답을 아는 세 가지 ───────────────────────────────────────


def test_pure_noise_scores_near_a_coin_flip():
    got = pbo(_noise())["pbo"]
    assert 0.3 <= got <= 0.7, (
        f"잡음뿐인 행렬의 PBO가 {got:.3f} — 동전던지기(≈0.5) 언저리여야 한다")


def test_a_genuinely_better_configuration_scores_low():
    got = pbo(_with_real_edge())
    assert got["pbo"] <= 0.2, f"진짜 우위가 있는데 PBO가 {got['pbo']:.3f}"
    assert got["mean_oos_rank"] >= 0.7, (
        f"IS 1등이 OOS서도 상위권이어야 한다: 평균 순위 {got['mean_oos_rank']:.3f}")


def test_the_overfitting_trap_scores_high():
    """이 지표의 존재 이유 — 분할 운을 고른 경우를 1.0으로 말해야 한다."""
    got = pbo(_alternating())
    assert got["pbo"] >= 0.8, (
        f"IS 승자가 OOS서 반드시 지는 구조인데 PBO가 {got['pbo']:.3f}")
    assert got["mean_oos_rank"] <= 0.35, got["mean_oos_rank"]
    assert got["prob_oos_loss"] >= 0.8, (
        f"선택된 설정의 OOS 샤프가 늘 음수여야 한다: {got['prob_oos_loss']:.3f}")


def test_the_three_cases_are_ordered():
    """방향이 뒤집히면(부호 변이) 이 순서가 깨진다."""
    low = pbo(_with_real_edge())["pbo"]
    mid = pbo(_noise())["pbo"]
    high = pbo(_alternating())["pbo"]
    assert low < mid < high, f"진짜우위 {low:.3f} · 잡음 {mid:.3f} · 과적합 {high:.3f}"


# ── 조합 대칭 교차검증이 실제로 돌아가는가 ────────────────────


def test_all_symmetric_combinations_are_evaluated():
    """C(10,5)=252개. 하나만 보면 그날의 분할 운에 답이 좌우된다."""
    import math
    got = pbo(_noise())["n_combinations"]
    want = math.comb(S, S // 2)
    assert got == want, f"조합을 {got}개만 봤다 — {want}개여야 한다"


def test_block_count_changes_the_number_of_combinations():
    """블록 수를 바꾸면 조합 수도 따라 바뀐다(상수로 굳어 있지 않은가)."""
    import math
    assert pbo(_noise(), n_blocks=6)["n_combinations"] == math.comb(6, 3)


# ── 입력 검증 ─────────────────────────────────────────────────


def test_odd_or_tiny_block_counts_are_refused():
    for bad in (0, 1, 3, 7):
        with pytest.raises(ValueError):
            pbo(_noise(), n_blocks=bad)


def test_a_single_configuration_is_refused():
    """설정이 하나면 '1등 선택'이라는 개념 자체가 없다."""
    with pytest.raises(ValueError):
        pbo(_noise(cols=1))


def test_a_short_series_is_refused_not_guessed():
    short = _noise().iloc[:20]
    with pytest.raises(ValueError):
        pbo(short)


# ── 분산이 사실상 0인 설정 (감사 146) ─────────────────────────


def test_a_flat_stretch_does_not_win_by_floating_point_noise():
    """구간의 대부분이 평평한 설정이 IS 1등을 훔쳐 PBO를 오염시키면 안 된다.

    `sd > 0`으로 막으면 np.full(...).std(ddof=1) == 1e-19이 통과해 샤프가
    1e15로 튄다.

    ⚠️ 처음에 '전 구간 상수' 열로 검사를 썼는데 **잡히지 않았다.** 전 구간
       상수면 IS에서도 OOS에서도 1등이라 λ가 양수로 남아 PBO가 그대로다.
       진짜로 해를 끼치는 건 **일부 구간만 평평한** 설정이다 — 오래 관망하다
       뒤늦게 무너진 전략이 바로 이 모양이고, 이건 실제로 흔하다.

    정답을 아는 데이터: c0만 진짜 우위(평균 0.002), 나머지는 잡음. 거기에
    앞 90%가 +0.05% 상수이고 뒤 10%에서 -2%씩 무너지는 열(cX)을 끼운다.

        가드가 없으면  PBO 0.056 → 0.560   (분할 운을 고른 것이 절반)
        가드가 있으면  PBO 0.056 → 0.056   (cX는 판정 불가로 0점, 무시)
    """
    rng = np.random.default_rng(11)
    cols = {f"c{i}": rng.normal(0.0, 0.01, T) for i in range(1, 8)}
    cols["c0"] = rng.normal(0.002, 0.01, T)          # 진짜 우위
    clean = pd.DataFrame(cols, index=IDX)

    flat = np.empty(T)
    flat[:int(T * 0.9)] = 0.0005                      # 표준편차 ≈ 1e-19
    flat[int(T * 0.9):] = -0.02                       # 뒤늦게 무너진다
    with_flat = clean.copy()
    with_flat["cX"] = flat

    base = pbo(clean)["pbo"]
    got = pbo(with_flat)["pbo"]
    assert base < 0.2, f"대조군 전제가 깨졌다 — 진짜 우위가 있는데 PBO {base:.3f}"
    assert got < 0.2, (
        f"평평한 열을 하나 끼웠을 뿐인데 PBO가 {base:.3f} → {got:.3f}로 뛴다 — "
        "분산 없는 구간이 IS 1등을 훔친다")


def test_a_small_but_real_configuration_is_still_ranked():
    """대조군 — 크기만 작은 정상 설정을 퇴화로 몰면 안 된다(가드가 덫이 되면 안 됨)."""
    rng = np.random.default_rng(13)
    cols = {f"c{i}": rng.normal(0.0, 1e-5, T) for i in range(1, 8)}
    cols["c0"] = rng.normal(2e-6, 1e-5, T)            # 크기만 작은 진짜 우위
    tiny = pd.DataFrame(cols, index=IDX)
    assert pbo(tiny)["pbo"] < 0.3, (
        "크기가 작을 뿐 정상인 설정들을 전부 퇴화로 몰아 순위가 무의미해진다")
