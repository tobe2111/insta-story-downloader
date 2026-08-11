"""DSR 다중검정 보정 계약 검사 — 허들이 현실의 시행 횟수를 반영하는가.

배경(2026-08-11 감사): 야간 검증의 DSR이 **검증 명령의 그리드 크기**(ml은
2×2=4)로 다중검정을 보정하고 있었다. 그런데 실제로 굴리는 챔피언은 매일 밤
23명씩, 종목당 누적 100회 이상(전체 1,846회)의 도전자를 이겨서 뽑힌 것이다.

    N=4    → 기대 최대 샤프 허들 1.05σ
    N=1846 → 3.43σ   (3.3배)

허들이 낮으면 DSR이 부풀고, "실력 미확인(DSR<0.95)" 경보가 울려야 할 때
울리지 않는다. 감시 장치가 감시 대상보다 후한 기준을 쓰고 있었던 셈이다.

핵심 계약:
  ① N이 커지면 허들이 오르고 DSR은 내려간다(보정이 실제로 작동)
  ② walk_forward가 장부의 실제 시행 횟수를 반영한다
  ③ 검증 명령이 그 값을 장부에서 읽어 넘긴다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.robustness.deflated_sharpe import (  # noqa: E402
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)

ROOT = Path(__file__).resolve().parent.parent


def _rets(n=500, mu=0.0008, sd=0.01, seed=3):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mu, sd, n))


# ── ① 보정이 실제로 작동한다 ──────────────────────────────────


def test_more_trials_raises_the_hurdle():
    lo = expected_max_sharpe(4, 1.0)
    hi = expected_max_sharpe(1846, 1.0)
    assert hi > lo * 3, f"허들이 거의 안 오른다: {lo:.3f} → {hi:.3f}"


def test_more_trials_lowers_dsr():
    r = _rets()
    d4 = deflated_sharpe_ratio(r, n_trials=4)
    d1846 = deflated_sharpe_ratio(r, n_trials=1846)
    assert d1846 < d4, "시행 횟수를 늘려도 DSR이 안 내려간다 — 보정이 죽었다"


def test_single_trial_equals_plain_psr():
    r = _rets()
    assert abs(deflated_sharpe_ratio(r, n_trials=1)
               - probabilistic_sharpe_ratio(r)) < 1e-12


def test_dsr_is_bounded():
    for n in (1, 4, 100, 5000):
        d = deflated_sharpe_ratio(_rets(), n_trials=n)
        assert 0.0 <= d <= 1.0, (n, d)


# ── ② walk_forward가 장부 시행 횟수를 받는다 ──────────────────


def test_walkforward_accepts_extra_trials():
    import inspect

    from quant.optimize.walkforward import walk_forward
    assert "extra_trials" in inspect.signature(walk_forward).parameters
    src = (ROOT / "quant" / "optimize" / "walkforward.py").read_text("utf-8")
    assert "n_trials = max(n_trials, int(extra_trials or 0))" in src


def test_grid_size_is_a_floor_not_a_ceiling():
    """그리드가 크면 그대로, 장부가 크면 장부를 쓴다 — 둘 중 큰 쪽."""
    src = (ROOT / "quant" / "optimize" / "walkforward.py").read_text("utf-8")
    assert "max(n_trials, int(extra_trials" in src


# ── ③ 검증 명령이 장부에서 읽어 넘긴다 ────────────────────────


def test_validate_reads_trials_from_the_ledger():
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "recent_trials(args.market, args.symbol" in src
    assert "extra_trials=ledger_trials" in src


def test_ledger_trials_are_actually_nonzero():
    """장부에 실제로 시행 기록이 쌓여 있는가 — 0이면 보정이 무의미하다."""
    import datetime as dt

    from quant.live.retrain import recent_trials
    n = recent_trials("crypto", "BTC/USDT", dt.date.today().isoformat(),
                      state_dir=str(ROOT / "state"))
    assert n > 0, "장부에 도전자 기록이 없다 — 보정 값이 그리드로만 남는다"
