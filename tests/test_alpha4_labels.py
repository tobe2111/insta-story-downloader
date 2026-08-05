"""알파 개선 4차 계약 검사 — 라벨 재설계·메타라벨링·표본 가중·횡단면 틸트.

핵심 계약:
  ① 트리플 배리어 라벨 — 먼저 친 배리어가 라벨이고, 미래 없는 구간은 NaN
  ② label="triple"이어도 미래 절단 불변(룩어헤드 없음) — 학습창 상한이
     horizon만큼 당겨졌음의 방증
  ③ 메타라벨링 — 방향은 추세 규칙(종가 vs MA50), ML은 크기만 정한다
  ④ 표본 시간감쇠 가중 — 모든 모델 종류에서 학습이 성공한다(무가중 폴백 포함)
  ⑤ 새 변형들이 챌린저 링에 참전한다 — 강제 적용이 아니라 오디션
  ⑥ 횡단면 확신도 틸트 — 순위 단조·동률 공평·총예산 보존·장부 기록
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies.ml import MLStrategy, _triple_barrier_labels  # noqa: E402


def _df(n: int, base: float = 100.0, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    ret = rng.normal(0.0005, 0.02, n)
    close = base * np.cumprod(1 + ret)
    opn = close * (1 + rng.normal(0, 0.004, n))
    return pd.DataFrame({
        "open": opn,
        "high": np.maximum(opn, close) * (1 + abs(rng.normal(0, 0.005, n))),
        "low": np.minimum(opn, close) * (1 - abs(rng.normal(0, 0.005, n))),
        "close": close, "volume": 1000.0 + rng.integers(0, 500, n)},
        index=idx)


# ── ① 트리플 배리어 라벨 ────────────────────────────────────────


def test_triple_barrier_first_touch_wins():
    """급등이 상단 배리어를 먼저 치면 1, 급락이 하단을 먼저 치면 0."""
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    rng = np.random.default_rng(0)
    close = 100.0 + rng.normal(0, 0.2, n).cumsum()      # 잔잔한 시장(vol>0)
    high = close + 0.1
    low = close - 0.1
    j_up, j_dn = 30, 40
    high[j_up + 1] = close[j_up] * 1.50                  # j_up 다음 봉에 급등
    low[j_dn + 1] = close[j_dn] * 0.50                   # j_dn 다음 봉에 급락
    df = pd.DataFrame({"open": close, "high": high, "low": low,
                       "close": close}, index=idx)
    y = _triple_barrier_labels(df, horizon=5, k=1.5)
    assert y[j_up] == 1.0                                # 이익 배리어 먼저
    assert y[j_dn] == 0.0                                # 손절 배리어 먼저
    assert np.isnan(y[:20]).all()                        # 변동성 미정의 구간
    assert np.isnan(y[-5:]).all()                        # 수직 배리어 관측 불가


def test_triple_barrier_values_are_binary_or_nan():
    y = _triple_barrier_labels(_df(300), horizon=10, k=1.5)
    vals = y[np.isfinite(y)]
    assert set(np.unique(vals)) <= {0.0, 1.0}
    assert len(vals) > 200                               # 대부분 라벨링된다


# ── ② 룩어헤드 차단(미래 절단 불변) ─────────────────────────────


def test_ml_triple_truncation_invariance():
    df = _df(500, seed=3)
    cut = 400
    make = lambda: MLStrategy(model="logreg", train_window=200,  # noqa: E731
                              retrain_every=50, label="triple",
                              label_horizon=10)
    full = make().generate_signals(df)
    trunc = make().generate_signals(df.iloc[:cut])
    a = full.iloc[:cut - 1].to_numpy()
    b = trunc.iloc[:cut - 1].to_numpy()
    assert int(np.sum(~np.isclose(a, b, atol=1e-9))) == 0


def test_ml_triple_runs_bounded_and_trades():
    sig = MLStrategy(model="gb", train_window=200, retrain_every=50,
                     label="triple").generate_signals(_df(500, seed=5))
    assert sig.abs().max() <= 1.0 + 1e-9
    assert (sig != 0).any()


# ── ③ 메타라벨링 — 방향은 규칙, 크기는 ML ──────────────────────


def test_ml_meta_positions_only_in_uptrend():
    """롱온리 메타라벨링: 비중>0인 봉은 반드시 추세 규칙(종가>MA50)이 롱인 봉."""
    df = _df(500, seed=11)
    strat = MLStrategy(model="logreg", train_window=200, retrain_every=50,
                       label="triple", meta=True)
    sig = strat.generate_signals(df)
    assert sig.min() >= -1e-9                            # 롱온리
    assert sig.max() <= 1.0 + 1e-9
    ma50 = df["close"].rolling(50).mean()
    traded = sig[sig > 0].index
    assert len(traded)                                   # 거래가 존재하고
    assert (df.loc[traded, "close"] > ma50.loc[traded]).all()


def test_ml_meta_short_follows_downtrend():
    """숏 허용 메타라벨링: 음(-) 비중 봉은 추세 규칙이 숏(종가<MA50)인 봉."""
    df = _df(500, seed=13)
    sig = MLStrategy(model="logreg", train_window=200, retrain_every=50,
                     label="triple", meta=True, allow_short=True,
                     threshold=0.52).generate_signals(df)
    ma50 = df["close"].rolling(50).mean()
    shorts = sig[sig < 0].index
    if len(shorts):                                      # 숏이 나왔다면 방향 일치
        assert (df.loc[shorts, "close"] < ma50.loc[shorts]).all()
    assert sig.abs().max() <= 1.0 + 1e-9


# ── ④ 표본 시간감쇠 가중 ────────────────────────────────────────


def test_ml_sample_weight_decay_all_model_kinds():
    """가중 직접 지원(gb·rf)·파이프라인 라우팅(logreg)·무가중 폴백(vote)
    모두에서 학습이 죽지 않고 경계 안의 신호를 낸다."""
    df = _df(400, seed=17)
    for kind in ("logreg", "rf", "gb", "vote"):
        sig = MLStrategy(model=kind, train_window=200, retrain_every=100,
                         sample_weight="decay").generate_signals(df)
        assert sig.abs().max() <= 1.0 + 1e-9, kind
        assert sig.index.equals(df.index), kind


def test_ml_invalid_label_and_weight_raise():
    with pytest.raises(ValueError):
        MLStrategy(label="quadruple")
    with pytest.raises(ValueError):
        MLStrategy(sample_weight="linear")


# ── ⑤ 링 구성 — 새 변형들이 오디션에 참전한다 ──────────────────


def test_ring_includes_label_meta_and_decay_variants():
    from quant.live.retrain import DEFAULT_CHALLENGERS
    triples = [c for c in DEFAULT_CHALLENGERS if c.get("label") == "triple"]
    assert len(triples) >= 2                             # 순수 + 메타
    assert any(c.get("meta") for c in triples)
    assert any(c.get("sample_weight") == "decay" for c in DEFAULT_CHALLENGERS)


def test_mutation_explores_label_and_weight_axes():
    """돌연변이가 라벨·표본가중 축도 탐색한다(시드 결정적)."""
    from quant.live.retrain import mutate_champion
    spec = {"strategy": "ml",
            "params": {"model": "logreg", "threshold": 0.55}}
    seen_axes = set()
    for d in range(30):                                  # 시드만 바꿔 반복 생성
        for m in mutate_champion(spec, seed=f"2026-08-{d:02d}:t"):
            seen_axes |= set(m["params"]) - set(spec["params"])
    assert "label" in seen_axes
    assert "sample_weight" in seen_axes
    # 결정성: 같은 시드 → 같은 결과
    a = mutate_champion(spec, seed="2026-08-06:x")
    b = mutate_champion(spec, seed="2026-08-06:x")
    assert a == b


# ── ⑥ 횡단면 확신도 틸트 ────────────────────────────────────────


def test_xsec_tilt_rank_monotone_and_bounded():
    from quant.live.daily import _xsec_tilt
    t = _xsec_tilt({"a": 0.2, "b": 0.8, "c": 0.5, "d": 1.0})
    assert t["a"] < t["c"] < t["b"] < t["d"]             # 확신도 순위대로
    assert min(t.values()) >= 0.75 - 1e-9
    assert max(t.values()) <= 1.25 + 1e-9


def test_xsec_tilt_ties_are_fair_and_degenerate_cases():
    from quant.live.daily import _xsec_tilt
    # 전 종목 동률이면 나열 순서와 무관하게 전부 1.0(평균 순위)
    t = _xsec_tilt({"a": 1.0, "b": 1.0, "c": 1.0})
    assert all(abs(v - 1.0) < 1e-9 for v in t.values())
    # 활성 종목이 2개 미만이면 틸트 없음
    t = _xsec_tilt({"a": 0.5, "b": 0.0})
    assert all(v == 1.0 for v in t.values())
    # 관망(비중 0) 종목은 항상 1.0
    t = _xsec_tilt({"a": 0.5, "b": 0.9, "c": 0.0})
    assert t["c"] == 1.0


def test_portfolio_record_logs_xsec_tilt_and_preserves_budget(tmp_path):
    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({
        "synthetic:DEMO": {"strategy": "ma_cross",
                           "params": {"fast": 10, "slow": 30}, "promotions": 0},
        "synthetic:DEMO2": {"strategy": "ma_cross",
                            "params": {"fast": 5, "slow": 20}, "promotions": 0},
    }, d)
    rec = run_daily_portfolio([("synthetic", "DEMO"), ("synthetic", "DEMO2")],
                              lookback=200, state_dir=d,
                              require_real_data=False)
    assert "xsec_tilt" in rec and len(rec["xsec_tilt"]) == 2
    for v in rec["xsec_tilt"].values():
        assert 0.75 - 1e-9 <= v <= 1.25 + 1e-9
    # 틸트 후에도 슬라이스 합(총예산)은 종목 수 기준 예산을 넘지 않는다
    assert sum(rec["alloc"].values()) <= 1.0 + 1e-6
