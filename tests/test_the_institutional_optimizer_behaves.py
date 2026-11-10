"""기관식 최적화 엔진 — 미래를 안 보고, 제약을 지키고, 위험 모델이 일을 한다 (2026-11-10 감사 367)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.portfolio import engine_select as E
from quant.portfolio import mvo
from quant.portfolio import trend_core as T


def _closes(n=700, k=12, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    vols = np.r_[np.full(k // 2, 0.004), np.full(k - k // 2, 0.015)]
    r = rng.normal(0.0003, 1, (n, k)) * vols
    r[:, :3] += 0.0005
    return pd.DataFrame(100 * np.exp(np.cumsum(r, 0)), index=idx,
                        columns=[f"us_stock:A{i}" for i in range(k)])


def test_the_projection_is_exact_and_feasible():
    rng = np.random.default_rng(1)
    for _ in range(500):
        n = int(rng.integers(2, 30))
        w, cap = rng.normal(0, 0.3, n), float(rng.uniform(0.05, 0.5))
        p = mvo._project(w, cap, 1.0)
        assert (p >= -1e-12).all() and (p <= cap + 1e-12).all() and p.sum() <= 1 + 1e-9
        if np.clip(w, 0, cap).sum() > 1:
            lo, hi = -10.0, 10.0
            for _ in range(200):
                m = (lo + hi) / 2
                lo, hi = (m, hi) if np.clip(w - m, 0, cap).sum() > 1 else (lo, m)
            assert np.abs(p - np.clip(w - hi, 0, cap)).max() < 1e-6


def test_weights_respect_the_account():
    c = _closes()
    w = mvo.mvo_weights(c, T.variant_config("risk12"))
    live = w[w.sum(axis=1) > 0]
    assert len(live) > 20
    assert (live >= -1e-12).all().all(), "현물 계좌에 숏"
    assert (live.sum(axis=1) <= 1 + 1e-6).all(), "빚을 냈다"
    assert (live.max(axis=1) <= T.variant_config("risk12").asset_cap + 1e-9).all()


def test_it_does_not_see_the_future():
    c = _closes()
    full = mvo.mvo_weights(c, T.variant_config("risk12"))
    cut = c.iloc[:560]
    part = mvo.mvo_weights(cut, T.variant_config("risk12"))
    # 잘린 쪽의 마지막 날은 '마지막 날'이라 따로 계산된다 — 그 앞의 결정일만 견준다.
    days = [d for d in part.index[:-1] if part.loc[d].sum() > 0]
    assert days
    pd.testing.assert_frame_equal(full.loc[days], part.loc[days])


def test_the_risk_model_does_not_count_twins_twice():
    """같이 움직이는 둘(쌍둥이)은 독립인 하나보다 덜 받아야 한다 — 그게 위험 모델의 일."""
    rng = np.random.default_rng(3)
    n = 300
    base = rng.normal(0, 0.01, n)
    twin = np.c_[base, base + rng.normal(0, 0.0005, n)]
    indep = rng.normal(0, 0.01, (n, 2))
    win = pd.DataFrame(np.c_[twin, indep])
    cov = mvo.shrunk_cov(win)
    w = mvo.optimize(np.full(4, 0.01), cov, target_vol=0.12, cap=1.0)
    assert w[0] + w[1] < w[2] + 0.02 or w[0] + w[1] < 0.5, w
    assert max(w[0], w[1]) < min(w[2], w[3]), w


def test_it_stays_diversified_when_the_target_is_out_of_reach():
    """빚 없이 목표 변동성에 못 닿아도 '기대수익 상위 몇 개를 상한까지'가 되지 않는다."""
    rng = np.random.default_rng(4)
    win = pd.DataFrame(rng.normal(0, 0.003, (300, 20)))        # 연 ~5% — 목표 12%에 못 닿는다
    cov = mvo.shrunk_cov(win)
    alpha = np.linspace(0.02, 0.001, 20)
    w = mvo.optimize(alpha, cov, target_vol=0.12, cap=0.25)
    assert abs(w.sum() - 1.0) < 1e-3, "예산을 안 썼다"
    assert (w > 1e-3).sum() >= 8, f"모서리 답(집중): {np.round(w, 3)}"


def test_it_is_a_candidate_not_a_decision():
    for n in ("mvo12", "mvo12w"):
        assert E.CANDIDATES[n]["kind"] == "mvo" and n in E.LABELS
    assert E.universe_of("mvo12w") == "wide"
    tgt, cfg = E.candidate_targets(_closes(), "mvo12")
    assert cfg.rebalance == "W-FRI" and tgt.values.sum() > 0
    t = E.targets_today(_closes(), "mvo12")
    assert t["target_day"] and abs(sum(t["weights"].values()) - 1.0) < 0.01
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "scripts" /
           "managed_futures_research.py").read_text("utf-8")
    assert '"audit367": ["mvo12", "mvo12w"]' in src, "시도 장부에 안 셌다 — 다중검정을 덜 치른다"
