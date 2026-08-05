"""의회(혼합 운용) 계약 검사 — 입성·비중 EMA·상관 탈락·혼합 신호·verify 정합.

핵심 계약:
  ① 입성은 오디션 통과로만(promoted_spec), 신입 의석은 서서히 커진다
  ② 상관 CORR_CAP 초과 의원은 점수 낮은 쪽 탈락(다양성 강제)
  ③ 혼합 신호 = 의석 비중 가중합, 한 의원의 실패는 그 의원만 관망
  ④ verify 대조 필드는 '오디션 결정'을 기록한다(의회 리더와 분리)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.parliament import (  # noqa: E402
    ENTRY_WEIGHT,
    PARLIAMENT_K,
    ParliamentStrategy,
    parliament_summary,
    update_parliament,
)


def _df(n: int = 300, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, n))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1000.0}, index=idx)


def test_update_parliament_admits_promoted_and_caps_seats():
    entry = {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30}}
    df = _df()
    out = update_parliament(
        entry, df, build=__import__("quant.live.retrain",
                                    fromlist=["build_strategy"]).build_strategy,
        confirm_window=120,
        promoted_spec={"strategy": "breakout",
                       "params": {"window": 55, "exit_window": 20}})
    assert 1 <= len(out) <= PARLIAMENT_K
    assert abs(sum(m["weight"] for m in out) - 1.0) < 0.01
    names = {m["strategy"] for m in out}
    # 신입은 입성하되(또는 상관 탈락) 의석 총합은 항상 정규화된다
    assert "ma_cross" in names or "breakout" in names
    # 신입 초기 의석은 EMA로 제한 — 곧바로 과반을 차지하지 않는다
    for m in out:
        if m["strategy"] == "breakout":
            assert m["weight"] <= ENTRY_WEIGHT + 0.35


def test_update_parliament_drops_correlated_duplicates():
    from quant.live.retrain import build_strategy
    entry = {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
             "parliament": [
                 {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
                  "weight": 0.5},
                 {"strategy": "ma_cross", "params": {"fast": 10, "slow": 31},
                  "weight": 0.5}]}     # 사실상 동일 전략(상관 ~1)
    out = update_parliament(entry, _df(), build=build_strategy,
                            confirm_window=120)
    assert len(out) == 1               # 중복 의원은 한 자리만


def test_update_parliament_survives_build_failure():
    def bad_build(spec):
        raise RuntimeError("boom")
    entry = {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30}}
    out = update_parliament(entry, _df(), build=bad_build, confirm_window=120)
    assert out[0]["strategy"] == "ma_cross"   # 실패 시 기존 명단 유지


def test_parliament_strategy_blends_and_isolates_failures():
    class Const:
        allow_short = False
        def __init__(self, v): self.v = v
        def generate_signals(self, df):
            return pd.Series(self.v, index=df.index)
    class Boom:
        allow_short = False
        def generate_signals(self, df):
            raise RuntimeError("x")
    df = _df(50)
    builders = {"a": Const(1.0), "b": Const(0.0), "x": Boom()}
    strat = ParliamentStrategy(
        [{"strategy": "a", "params": {}, "weight": 0.6},
         {"strategy": "b", "params": {}, "weight": 0.4}],
        build=lambda s: builders[s["strategy"]])
    sig = strat.generate_signals(df)
    assert float(sig.iloc[-1]) == 0.6          # 0.6·1 + 0.4·0
    strat2 = ParliamentStrategy(
        [{"strategy": "a", "params": {}, "weight": 0.5},
         {"strategy": "x", "params": {}, "weight": 0.5}],
        build=lambda s: builders[s["strategy"]])
    sig2 = strat2.generate_signals(df)
    assert float(sig2.iloc[-1]) == 0.5         # 실패 의원만 관망


def test_summary_and_champion_strategy_hot_loads_parliament(tmp_path):
    from quant.live.retrain import champion_strategy, save_champions
    assert parliament_summary({"parliament": []}) is None
    entry = {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
             "parliament": [
                 {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
                  "weight": 0.7},
                 {"strategy": "breakout",
                  "params": {"window": 55, "exit_window": 20},
                  "weight": 0.3}]}
    assert "ma_cross 70%" in parliament_summary(entry)
    save_champions({"synthetic:DEMO": entry}, str(tmp_path))
    strat = champion_strategy("synthetic", "DEMO", str(tmp_path))
    sig = strat.generate_signals(_df(200))
    assert len(sig) == 200 and sig.abs().max() <= 1.0


def test_run_retrain_populates_parliament_and_verify_still_ok(tmp_path):
    import quant.live.retrain as rt
    d = str(tmp_path)
    rt.save_champions({"synthetic:DEMO": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
        "promotions": 0}}, d)
    orig = rt.DEFAULT_CHALLENGERS
    rt.DEFAULT_CHALLENGERS = [
        {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}}]
    try:
        rt.run_retrain("synthetic", "DEMO", limit=400, state_dir=d,
                       require_real_data=False, evolve=True)
        champs = json.loads((tmp_path / "champions.json")
                            .read_text(encoding="utf-8"))
        e = champs["synthetic:DEMO"]
        assert e.get("parliament") and abs(
            sum(m["weight"] for m in e["parliament"]) - 1.0) < 0.01
        # 리더 = 최대 의석이 단일 챔피언 자리를 유지
        assert e["strategy"] == e["parliament"][0]["strategy"]
        recs = [json.loads(ln) for ln in
                (tmp_path / "retrain_history.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        assert recs[-1]["parliament"]          # 구성이 장부에 남는다
        # 의회 도입 후에도 재현성 검증이 성립한다
        out = rt.verify_retrain(recs[-1]["asof"], state_dir=d)
        assert out and all(r["ok"] for r in out), out
    finally:
        rt.DEFAULT_CHALLENGERS = orig
