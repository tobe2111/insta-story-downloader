"""결승은 '후보 N명 중 최고'라는 사실을 잊지 않는가 (2026-08-18).

confirm_threshold(로그+상한)는 시도가 아주 많아지면 상한(1.35)에 붙어 더
오르지 않는다 — 링이 커진 날 CI가 실측으로 드러낸 빈틈이다. 그 빈틈을
막는 것이 동시검정(현실성 검사)이다: 오늘 링의 모든 후보를 홀드아웃에서
재생해 "N명 중 최고 성적이 우연으로 나올 확률" p를 부트스트랩으로 직접
재고, p가 크면 결승 t를 넘었어도 승격을 보류한다.

지켜야 할 약속:
- 잡음뿐인 후보 무리에서 '가장 좋아 보이는 놈'은 승격되지 않는다.
- 진짜 우위가 있는 후보는 이 관문을 통과한다.
- 같은 행렬 → 언제나 같은 p (고정 시드 — 시드 채택 편향 금지).
- 관문이 실제 승격 경로에 배선돼 있다(함수만 있고 안 부르면 소용없다).
- 옛 기록(gate_version < 3)의 재현에는 이 관문을 걸지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.retrain as rt                      # noqa: E402
from quant.strategies.base import Strategy           # noqa: E402


# ── ① 검정 자체 — 잡음은 걸리고, 진짜는 통과한다 ────────────────

def test_the_best_of_many_noises_is_not_a_champion():
    """후보 40개가 전부 잡음이면 그중 최고도 잡음이다."""
    rng = np.random.RandomState(3)
    mat = rng.normal(0.0, 0.01, size=(120, 40))
    res = rt.reality_check(mat)
    assert res["n_cand"] == 40
    assert res["p"] > rt.RC_ALPHA, (
        f"잡음 40개 중 최고(t={res['t_max']})를 우연이 아니라고 판정한다 — "
        f"p={res['p']}. 이 관문의 존재 이유가 사라진다")


def test_a_real_edge_survives_the_crowd():
    """진짜 우위(일 +0.4%, t≈4)는 잡음 무리 속에서도 살아남아야 한다."""
    rng = np.random.RandomState(3)
    mat = rng.normal(0.0, 0.01, size=(120, 40))
    mat[:, 7] += 0.004                               # 한 명만 진짜
    res = rt.reality_check(mat)
    assert res["p"] <= 0.05, (
        f"명백한 우위(t={res['t_max']})를 우연이라 한다 — p={res['p']}. "
        "관문이 너무 엄격하면 진화가 멈춘다")


def test_more_rivals_means_a_bigger_chance_of_a_lucky_best():
    """같은 성적(t≈3)이라도 후보가 많을수록 더 의심받아야 한다 — 이것이
    상한 없는 다중검정 보정의 핵심 성질이다(confirm_threshold의 상한은
    바로 이 성질을 큰 시도 수에서 잃는다)."""
    rng = np.random.RandomState(11)
    big = rng.normal(0.0, 0.01, size=(150, 60))
    big[:, 0] += 0.0025                              # 같은 우위 후보 하나
    few = big[:, :3]
    p_few = rt.reality_check(few)["p"]
    p_big = rt.reality_check(big)["p"]
    assert p_big > p_few, (
        f"같은 성적인데 후보 60개(p={p_big})가 3개(p={p_few})보다 우연을 "
        "덜 의심받는다 — 보정 방향이 거꾸로다")


def test_same_matrix_same_pvalue_always():
    rng = np.random.RandomState(5)
    mat = rng.normal(0.0, 0.01, size=(90, 10))
    assert rt.reality_check(mat) == rt.reality_check(mat), "재현성 위반"


def test_a_constant_column_does_not_crash_or_win():
    """분산 0(챔피언과 상수 차이) 열은 t=0 — 0/0로 죽거나 이기면 안 된다."""
    rng = np.random.RandomState(7)
    mat = rng.normal(0.0, 0.01, size=(60, 4))
    mat[:, 2] = 0.0
    res = rt.reality_check(mat)
    assert np.isfinite(res["t_max"]) and 0.0 < res["p"] <= 1.0


# ── ② 배선 — 승격 경로가 실제로 이 관문을 지난다 ────────────────

class _Flat(Strategy):
    name = "flat"

    def generate_signals(self, df):
        return self._finalize(pd.Series(0.0, index=df.index), df.index)


class _Hold(Strategy):
    name = "hold"

    def generate_signals(self, df):
        return self._finalize(pd.Series(1.0, index=df.index), df.index)


def _drift_df(n=320, seed=2):
    rng = np.random.RandomState(seed)
    r = rng.normal(0.002, 0.005, size=n)             # 완만한 진짜 상승
    close = 100.0 * np.cumprod(1.0 + r)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": np.full(n, 1e6)}, index=idx)


def _build(spec):
    return _Hold() if spec["strategy"] == "hold" else _Flat()


def _audition(**kw):
    return rt.nightly_retrain(
        _drift_df(), {"strategy": "flat", "params": {}},
        [{"strategy": "hold", "params": {}}],
        build=_build, confirm_window=120, confirm_t=0.3, min_obs=30, **kw)


def test_a_high_pvalue_blocks_the_promotion(monkeypatch):
    monkeypatch.setattr(rt, "reality_check",
                        lambda *a, **k: {"p": 0.9, "t_max": 1.0,
                                         "n": 120, "n_cand": 1})
    decision = _audition()
    assert not decision["promoted"], "p=0.9인데 승격했다 — 관문이 장식이다"
    assert "동시검정" in decision["reason"]
    assert decision["reality_check"]["p"] == 0.9


def test_a_low_pvalue_lets_the_promotion_through(monkeypatch):
    monkeypatch.setattr(rt, "reality_check",
                        lambda *a, **k: {"p": 0.01, "t_max": 4.0,
                                         "n": 120, "n_cand": 1})
    decision = _audition()
    assert decision["promoted"], "p=0.01인데 승격을 막았다"
    assert decision["reality_check"]["p"] == 0.01


def test_old_records_replay_without_the_new_gate(monkeypatch):
    """gate_version < 3 기록의 재현에 오늘의 관문을 걸면 과거가 바뀐다."""
    called = {"n": 0}

    def _spy(*a, **k):
        called["n"] += 1
        return {"p": 0.9, "t_max": 1.0, "n": 120, "n_cand": 1}

    monkeypatch.setattr(rt, "reality_check", _spy)
    decision = _audition(reality_gate=False)
    assert decision["promoted"] and called["n"] == 0, (
        "reality_gate=False인데 동시검정이 돌았다 — 옛 기록 재현이 깨진다")
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert 'reality_gate=int(rec.get("gate_version", 1)) >= 3' in src, (
        "verify가 관문 세대를 보지 않는다 — 옛 결정이 새 규칙으로 재현된다")
    assert '"gate_version": 3' in src, "새 기록이 관문 세대를 안 밝힌다"


def test_the_ledger_keeps_the_reality_check(tmp_path):
    """장부 없이 관문만 있으면 '왜 승격이 안 됐나'에 답할 수 없다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"reality_check": decision.get("reality_check")' in src, (
        "동시검정 결과가 재학습 장부에 안 실린다")


def test_thin_holdout_skips_with_a_reason():
    """표본이 얇으면 '검정 생략'을 명시한다 — 조용한 통과 금지."""
    rng = np.random.RandomState(1)
    with pytest.raises(ValueError):
        rt.reality_check(rng.normal(size=(2, 3)))    # 3봉 미만은 검정 불가
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "동시검정 생략(관문 미적용)" in src, (
        "홀드아웃 표본 부족을 조용히 넘긴다 — 생략은 밝혀야 한다")
