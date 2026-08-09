"""알파 12차 계약 검사 — 풀링(패널) 학습.

핵심 계약:
  ① 풀 주입 학습이 동작하고, pool=None(기본)은 기존과 동일 결과
  ② 룩어헤드 차단: 학습 상한 이후의 풀 행은 결과에 영향을 못 준다 —
     '미래 풀 행'을 극단값으로 바꿔도 신호가 안 변한다
  ③ meta+pool 조합은 명시적 거부, 잘못된 pool 값도 거부
  ④ 스냅샷 로더: 당일 폴더 제외(엄격히 이전 날짜의 최신 폴더 — verify
     재현 보존), 폴더 없으면 빈 목록
  ⑤ 풀링 챌린저 2종이 링에 있고, explain이 풀링을 표기한다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies.ml import MLStrategy  # noqa: E402
from quant.utils.repro import load_snapshot_pool, save_snapshot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _df(n: int = 200, seed: int = 11, drift: float = 0.0005) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100.0 * np.cumprod(1 + rng.normal(drift, 0.02, n))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1000.0 + rng.integers(0, 500, n)},
                        index=idx)


def _strat(**kw) -> MLStrategy:
    return MLStrategy(model="logreg", train_window=100, retrain_every=20,
                      min_train=40, **kw)


# ── ① 학습 동작 + 기본 불변 ────────────────────────────────────


def test_pooled_trains_and_default_unchanged():
    df = _df()
    peers = [_df(seed=s) for s in (21, 22, 23)]
    sig_pool = _strat(pool=peers).generate_signals(df)
    assert len(sig_pool) == len(df)
    assert np.isfinite(sig_pool.to_numpy()).all()
    a = _strat().generate_signals(df)
    b = _strat(pool=None).generate_signals(df)
    assert (a.to_numpy() == b.to_numpy()).all()


# ── ② 룩어헤드 차단 ────────────────────────────────────────────


def test_pool_rows_after_cutoff_cannot_leak():
    df = _df()
    peer = _df(seed=31)
    sig1 = _strat(pool=[peer]).generate_signals(df)
    # 타깃 마지막 학습 상한 이후 구간의 풀 행을 극단값으로 오염시켜도
    # (날짜 필터가 각 블록에서 미래 풀 행을 배제하므로) 신호는 동일해야 한다
    poisoned = peer.copy()
    poisoned.loc[poisoned.index >= df.index[-1], "close"] = 1e9
    sig2 = _strat(pool=[poisoned]).generate_signals(df)
    assert (sig1.to_numpy() == sig2.to_numpy()).all()


# ── ③ 조합·값 검증 ─────────────────────────────────────────────


def test_pool_rejects_meta_and_bad_values():
    import pytest
    with pytest.raises(ValueError, match="meta"):
        _strat(pool="peers", meta=True, label="triple")
    with pytest.raises(ValueError, match="pool"):
        _strat(pool="everything")


# ── ④ 스냅샷 로더 규칙 ─────────────────────────────────────────


def test_snapshot_pool_strictly_before_cutoff(tmp_path):
    d = str(tmp_path)
    save_snapshot(_df(60, seed=1), d, "2026-08-07", "crypto", "BTC/USDT")
    save_snapshot(_df(60, seed=2), d, "2026-08-08", "crypto", "BTC/USDT")
    save_snapshot(_df(60, seed=3), d, "2026-08-08", "us_stock", "SPY")
    # 당일(08-09) 폴더는 순회 중 채워지는 중일 수 있어 제외 — 전일 폴더 사용
    save_snapshot(_df(60, seed=4), d, "2026-08-09", "crypto", "BTC/USDT")
    pool = load_snapshot_pool(d, "2026-08-09")
    assert len(pool) == 2                      # 08-08 폴더의 2종목
    assert load_snapshot_pool(d, "2026-08-07") == []  # 그 이전 폴더 없음
    assert load_snapshot_pool(str(tmp_path / "없음"), "2026-08-09") == []


# ── ⑤ 링·explain 배선 ──────────────────────────────────────────


def test_pool_challengers_in_ring_and_explained():
    from quant.live.retrain import DEFAULT_CHALLENGERS
    pooled = [c for c in DEFAULT_CHALLENGERS if c.get("pool") == "peers"]
    assert {c["model"] for c in pooled} == {"gb", "logreg"}

    from quant.live.explain import explain_signal
    df = _df(120)
    spec = {"strategy": "ml",
            "params": {"model": "gb", "threshold": 0.55, "pool": "peers"}}
    txt = explain_signal(spec, df, 0.3)
    assert "풀링" in txt
