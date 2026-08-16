"""검증 3종이 **구조적으로 못 보는 것** — 도중에 죽는 경로.

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 선물 준비 ③단계).

    DSR·PBO·CPCV는 전부 **수익률의 분포**를 본다. "평균적으로 좋은가"를 묻는다.
    그런데 레버리지가 붙으면 평균이 아무 의미가 없어지는 순간이 생긴다 —
    도중에 계좌가 0이 되면 그 뒤의 좋은 수익률은 나에게 오지 않는다.

    실측(이 파일의 첫 검사): 51% 확률로 +10%, 49% 확률로 -10%인 전략은
    하루 기댓값이 **+0.3%**이고 DSR이 **0.83**이다. 그런데 배수 없이도
    **37%**가 파산한다. 산술평균은 양수인데 기하평균이 음수이기 때문이다.
    분포만 보는 검사는 이걸 통과시킨다.

    그래서 레버리지를 열기 전에 이 계산을 먼저 만든다. 순서를 바꾸면
    "검증 3종을 통과했으니 안전합니다"가 거짓말이 된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.deflated_sharpe import deflated_sharpe_ratio  # noqa: E402
from quant.robustness.ruin import (                                  # noqa: E402
    RUIN_PASS,
    max_leverage_by_ruin,
    probability_of_ruin,
)


def _coinflip(n=1000, seed=1):
    """산술평균은 양수인데 기하평균이 음수인 전략 — 이 파일의 본보기."""
    rng = np.random.default_rng(seed)
    return np.where(rng.random(n) < 0.51, 0.10, -0.10)


def _realistic(n=800, mu=0.0003, sd=0.015, seed=5):
    return np.random.default_rng(seed).normal(mu, sd, n)


# ── ① 분포 검사가 놓치는 것을 이 검사가 잡는가 ──────────────────

def test_a_strategy_the_sharpe_likes_can_still_ruin_you():
    """**이 검사가 이 파일이 존재하는 이유다.**

    기댓값 양수 · DSR 0.8 이상인데 파산확률이 30%를 넘는다. 분포를 보는
    검사와 경로를 보는 검사가 서로 다른 것을 본다는 증거다.
    """
    r = _coinflip()
    assert r.mean() > 0, "본보기가 망가졌다 — 기댓값이 양수여야 한다"
    assert deflated_sharpe_ratio(r, n_trials=1) > 0.8, "DSR이 통과시켜야 한다"

    ruin = probability_of_ruin(r, leverage=1.0, seed=3)
    assert ruin.probability > 0.30, f"파산확률 {ruin.probability:.1%}"
    assert not ruin.ok, "분포는 좋은데 경로가 죽는 전략을 통과시켰다"


def test_leverage_makes_ruin_worse_not_better():
    """배수가 커지면 파산확률은 **단조 증가**해야 한다.

    이게 깨지면 '배수를 올렸더니 더 안전해졌다'는 답이 나오고, 그 위에
    세운 상한 계산(이분법)도 전부 무의미해진다.
    """
    r = _realistic()
    probs = [probability_of_ruin(r, leverage=L, seed=3).probability
             for L in (1, 2, 3, 5, 10)]
    assert probs == sorted(probs), f"배수에 단조가 아니다: {probs}"


def test_a_realistic_strategy_is_not_rejected_at_one_times():
    """지금 이 시스템(1배)이 이 검사에 걸리면 안 된다 — 관문이 먼저, 문은 나중."""
    assert probability_of_ruin(_realistic(), leverage=1.0, seed=3).ok


def test_passing_ruin_is_not_a_claim_that_the_strategy_is_good():
    """파산확률 통과는 **'안 죽는다'이지 '번다'가 아니다.**

    손실 전략도 천천히 잃으면 1년 안에 파산선을 안 밟는다. 이 숫자를
    '좋은 전략'의 근거로 읽으면 안 된다 — 그건 DSR·PBO가 답할 질문이다.
    """
    losing = _realistic(mu=-0.0002, sd=0.02)
    assert probability_of_ruin(losing, leverage=1.0, seed=3).ok
    assert losing.mean() < 0, "본보기가 손실 전략이어야 한다"


# ── ② 모르면 통과시키지 않는다 ─────────────────────────────────

def test_too_few_samples_blocks_instead_of_passing():
    """표본이 모자라면 '안전'이 아니라 '모른다'다 — 미측정=절반 규칙과 같은 정신."""
    x = probability_of_ruin([0.01] * 10, leverage=3.0)
    assert not x.ok
    assert "잴 수 없습니다" in x.reason
    assert x.probability != x.probability, "모르는 값을 숫자로 내보내면 안 된다"


# ── ③ 나쁜 날이 뭉쳐 오는 성질을 살리는가 ───────────────────────

def test_it_uses_block_bootstrap_not_shuffled_days():
    """하루씩 섞으면 연속된 하락이 흩어져 파산확률이 **낮게** 나온다.

    실제로 계좌를 죽이는 것은 나쁜 날이 뭉쳐 오는 것이다. 그 성질을 지우면
    이 계산은 안전하다는 잘못된 답을 준다.

    확인 방법: 하락이 뭉쳐 있는 수익률을 무작위로 섞으면 파산확률이 크게
    떨어져야 한다 — 즉 이 함수가 순서에 **민감해야** 한다.
    """
    rng = np.random.default_rng(11)
    r = rng.normal(0.002, 0.01, 600)
    r[200:260] = -0.03                     # 60일 연속 하락(뭉친 나쁜 구간)
    # ⚠️ 배수를 크게 잡으면 **둘 다 죽어서** 차이가 안 보인다(실측 5배:
    #    뭉침 66% vs 섞음 75%로 오히려 뒤집힌다 — 양쪽 다 포화된 잡음이다).
    #    차이가 드러나는 구간에서 재야 검사에 뜻이 있다(2배: 30% vs 1.4%).
    clustered = probability_of_ruin(r, leverage=2.0, seed=3).probability
    shuffled = probability_of_ruin(rng.permutation(r), leverage=2.0,
                                   seed=3).probability
    assert clustered > shuffled * 3 + 0.05, (
        f"뭉친 하락({clustered:.1%})이 흩어진 것({shuffled:.1%})보다 뚜렷하게 "
        f"위험하지 않다 — 순서를 무시하고 있다(블록 부트스트랩이 아니다)")


def test_ruin_is_judged_on_the_path_not_the_ending():
    """도중에 -95%까지 갔다가 돌아온 경로는 **무사가 아니다.**

    최종 자산만 보면 그런 경로가 '살아남음'으로 세어진다. 실제로는 그
    시점에 청산돼 돌아올 기회 자체가 없다.
    """
    src = (ROOT / "quant" / "robustness" / "ruin.py").read_text("utf-8")
    assert ".any(axis=1)" in src, "경로 전체가 아니라 한 지점만 본다"
    # 값으로도 확인 — 크게 빠졌다 회복하는 수익률에서 파산이 잡혀야 한다.
    r = np.concatenate([np.full(40, -0.08), np.full(200, 0.02)])
    x = probability_of_ruin(r, leverage=2.0, seed=3)
    assert x.probability > 0, "빠졌다 회복하는 경로에서 파산을 못 잡는다"


# ── ④ 상한 계산이 문턱과 어긋나지 않는가 ────────────────────────

def test_max_leverage_agrees_with_the_threshold():
    r = _realistic()
    L = max_leverage_by_ruin(r, seed=3)
    assert probability_of_ruin(r, leverage=L, seed=3).ok
    if L < 20.0:
        assert not probability_of_ruin(r, leverage=L * 1.2, seed=3).ok


def test_a_ruinous_strategy_gets_no_leverage_at_all():
    """1배로도 죽는 전략에는 배수를 한 톨도 주지 않는다."""
    assert max_leverage_by_ruin(_coinflip(), seed=3) == 1.0


def test_the_threshold_is_strict_enough_to_mean_something():
    """"100번 중 몇 번 죽어도 된다"가 느슨하면 이 관문은 장식이다."""
    assert 0 < RUIN_PASS <= 0.05, f"파산 허용 기준이 {RUIN_PASS:.0%}로 느슨하다"
