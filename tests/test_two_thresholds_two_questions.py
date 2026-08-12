"""문턱 하나로 **두 가지 질문**을 재고 있었다 (감사 159).

감사 146에서 '표준편차 0 판정'을 `quant/utils/numerics.py` 한 곳으로 모았다.
좋은 결정이었는데, 그 뒤 149에서 배분기까지 같은 상수를 쓰게 되면서
**서로 다른 두 질문이 한 문턱을 공유**하게 됐다.

    ① 이 분산은 부동소수 잡음인가       패널 안 최대 분산 대비 (분산 대 분산)
    ② 이 계열에 쓸 만한 분산이 있는가   그 계열의 크기 대비 (표준편차 대 크기)

①은 아주 엄격해야 한다. 진짜로 조용한 자산(저유동 ETF)을 잡음으로 몰면
배분에서 통째로 지워지고, 그건 가드가 덫이 되는 것이다.

②는 훨씬 느슨해야 한다. 표준편차가 평균의 100만분의 1인 계열은 잡음이든
아니든 **샤프를 말할 수 없다.**

한 문턱(1e-12)으로 둘을 다 재니 ②가 새어 나갔다. 실측:

    매일 정확히 +0.005%씩 오르는 계열(예금형 ETF·MMF)
        std/평균 = 2.3e-12          ← 문턱 1e-12를 간발의 차로 통과
        몬테카를로 샤프 중앙값 = 8,130,000,000,000

그 값이 신뢰구간 표에 그대로 나간다. 문턱을 둘로 나눴다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.monte_carlo import bootstrap_metrics, summarize  # noqa: E402
from quant.utils.numerics import (  # noqa: E402
    REL_EPS,
    SHARPE_REL_EPS,
    degenerate_spread,
)

N = 200


def _mmf() -> pd.Series:
    """매일 정확히 +0.005%씩 오르는 상품의 일간 수익률(예금형 ETF·MMF)."""
    price = 100.0 * (1.00005 ** np.arange(N + 1))
    return pd.Series(price[1:] / price[:-1] - 1.0)


# ── 문턱이 둘로 나뉘어 있는가 ─────────────────────────────────


def test_the_two_thresholds_are_different_on_purpose():
    assert SHARPE_REL_EPS > REL_EPS, (
        "두 문턱이 같아졌다 — '잡음인가'와 '쓸 만한가'는 다른 질문이다")
    assert SHARPE_REL_EPS == 1e-6 and REL_EPS == 1e-12


def test_the_mmf_series_sits_between_them():
    """이 계열이 정확히 두 문턱 사이에 있다는 것이 이 감사의 전부다."""
    r = _mmf().to_numpy()
    ratio = r.std() / np.abs(r).mean()
    assert REL_EPS < ratio < SHARPE_REL_EPS, (
        f"std/평균 비율 {ratio:.3e} — 두 문턱 사이가 아니면 이 검사가 헛돈다")


def test_the_sharpe_question_catches_it_and_the_noise_question_does_not():
    r = _mmf().to_numpy()
    scale = float(np.abs(r).mean())
    assert degenerate_spread(r.std(), scale), (
        "샤프 문턱이 이 계열을 못 잡는다 — 샤프가 8e12로 나간다")
    assert not degenerate_spread(r.std(), scale, rel_eps=REL_EPS), (
        "잡음 문턱까지 이 계열을 잡으면, 배분기가 조용한 자산을 지운다")


# ── 몬테카를로가 실제로 고쳐졌는가 ────────────────────────────


def test_a_constant_series_gets_no_sharpe_from_the_bootstrap():
    d = bootstrap_metrics(_mmf(), n_sims=200, seed=1)
    worst = float(np.max(np.abs(d["sharpe"])))
    assert worst == 0.0, (
        f"매일 같은 비율로 오르는 계열의 부트스트랩 샤프가 {worst:.3e} — "
        "분산이 없으면 샤프를 말할 수 없다")


def test_the_summary_table_does_not_print_absurd_numbers():
    """신뢰구간 표는 사람이 읽는 최종 산출물이다 — 여기까지 와야 고친 것이다."""
    text = summarize(bootstrap_metrics(_mmf(), n_sims=200, seed=1))
    assert "e+1" not in text and "e+0" not in text, text
    assert "샤프지수" in text


def test_a_normal_series_is_untouched():
    """대조군 — 정상 계열의 분포가 바뀌면 그건 고침이 아니라 파괴다."""
    r = pd.Series(np.random.default_rng(1).normal(0.0005, 0.01, 300))
    d = bootstrap_metrics(r, n_sims=300, seed=1)
    assert float(np.std(d["sharpe"])) > 0.05, "분포가 한 점으로 뭉쳤다"
    assert (d["sharpe"] != 0.0).mean() > 0.95, (
        f"정상 계열인데 {(d['sharpe'] == 0.0).mean():.1%}가 0으로 판정됐다")


def test_a_tiny_but_real_series_still_gets_a_sharpe():
    """대조군 — 크기만 작은 진짜 계열까지 지우면 가드가 덫이 된다."""
    r = pd.Series(np.random.default_rng(3).normal(1e-6, 1e-5, 300))
    d = bootstrap_metrics(r, n_sims=200, seed=1)
    assert (d["sharpe"] != 0.0).mean() > 0.9, (
        "크기가 작을 뿐 정상인 계열을 퇴화로 오판한다")


# ── 다른 지표는 여전히 계산되는가 ─────────────────────────────


def test_the_other_metrics_still_come_out():
    """샤프만 판정 불가일 뿐, 총수익·낙폭은 여전히 말할 수 있다."""
    d = bootstrap_metrics(_mmf(), n_sims=100, seed=1)
    assert float(np.median(d["total_return"])) > 0.0, (
        "매일 오르는 계열인데 총수익이 0 이하다")
    assert float(np.median(d["max_drawdown"])) == 0.0, (
        "한 번도 안 떨어지는 계열인데 낙폭이 잡힌다")
