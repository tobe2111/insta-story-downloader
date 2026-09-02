"""회전(리밸런스 밴드)은 사람이 정하지 않는다 — 기계가 비용 아래서 고른다.

■ 왜 (2026-09-02 사장님 지시)

"각 수수료도 고려해서 수익을 생각해야지 — 이런 것도 너가 할 게 아니라
머신러닝 차원에서 알아서 해야지." 실측: 선물 실험 열흘 −4.17% 중 수수료
5.47%p, 전략 자체 +1.42%. 비용은 오디션에서 이미 물리고 있었지만, 회전을
정하는 밴드가 **시장별 고정값 하나**라 후보마다 같았다 — 어떤 후보도 "덜
사고팔면 더 남는가"를 물어볼 수 없었다.

이제 밴드 배수(`band_mult`)가 후보의 손잡이이자 언덕오르기의 탐색 축이고,
챔피언과 후보는 **각자의 배수**로 돌아 같은 비용 아래서 겨루며, 승격된
배수는 실거래 체결기가 그대로 따른다.
"""
from __future__ import annotations

import json
import random

import numpy as np
import pandas as pd
import pytest

import quant.live.retrain as R
from quant.live.champion_challenger import ChampionChallenger


def _df(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": px, "high": px * 1.01, "low": px * 0.99,
                         "close": px, "volume": 1e6}, index=idx)


# ── 손잡이로서의 band_mult ───────────────────────────────────────────────────

def test_band_mult_is_a_search_axis():
    assert "band_mult" in R.ML_EXPLICIT_AXES
    got = {R._axis_band_mult(random.Random(i), {"band_mult": 1.0})["band_mult"]
           for i in range(40)}
    assert got <= set(R.BAND_MULT_CHOICES) and 1.0 not in got   # 지금 값은 안 고른다
    assert len(got) >= 2


def test_the_hill_climber_actually_proposes_a_band_change():
    """후보 생성기가 실제로 band_mult 를 흔든 후보를 낸다(축이 표에 있어도
    골라지지 않으면 없는 것과 같다)."""
    spec = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55}}
    seen = set()
    for d in range(1, 40):
        for c in R.mutate_champion(spec, seed=f"2026-09-{d:02d}:x", n=4):
            if "band_mult" in c.get("params", {}):
                seen.add(c["params"]["band_mult"])
    assert seen, "40일 동안 band_mult 를 흔든 후보가 하나도 없다"


def test_default_multiplier_is_the_same_setting_as_none():
    """band_mult 1.0 은 안 적은 것과 같다 — 중복 정규화가 지운다(16.8% 헛수고 재발 방지)."""
    a = {"strategy": "ml", "params": {"model": "gb"}}
    b = {"strategy": "ml", "params": {"model": "gb", "band_mult": 1.0}}
    c = {"strategy": "ml", "params": {"model": "gb", "band_mult": 2.0}}
    assert R.strip_default_params(a) == R.strip_default_params(b)
    assert R.strip_default_params(c) != R.strip_default_params(a)


def test_the_strategy_constructor_never_sees_the_execution_knob():
    s = R.build_strategy({"strategy": "ml", "params": {"model": "logreg", "band_mult": 2.0}})
    assert type(s).__name__ == "MLStrategy"
    assert not hasattr(s, "band_mult")


def test_band_mult_of_is_safe():
    assert R.band_mult_of(None) == 1.0
    assert R.band_mult_of({}) == 1.0
    assert R.band_mult_of({"band_mult": "x"}) == 1.0
    assert R.band_mult_of({"band_mult": -3}) == 0.0
    assert R.band_mult_of({"band_mult": 2}) == 2.0


# ── 오디션: 챔피언과 후보가 각자의 밴드로 돈다 ─────────────────────────────

def test_the_challenger_runs_with_its_own_band():
    """도전자 밴드를 따로 주면 결과가 실제로 달라진다."""
    from quant.strategies import get_strategy
    df = _df()
    champ = get_strategy("ma_cross", fast=5, slow=20)
    chal = get_strategy("ma_cross", fast=5, slow=20)
    same = ChampionChallenger(champ, chal, rebalance_band=0.0).evaluate(df)
    own = ChampionChallenger(champ, chal, rebalance_band=0.0,
                             challenger_band=1.2).evaluate(df)   # 0↔1 점프를 막는 밴드
    # 같은 전략이라 밴드가 같으면 동일(identical), 밴드가 다르면 달라진다
    assert same.get("identical") is True
    assert own.get("identical") is not True


def test_holdout_diffs_apply_each_specs_multiplier(monkeypatch):
    """홀드아웃(동시검정·패널)도 스펙별 배수로 돈다 — 배수가 다르면 차이가 생긴다."""
    df = _df()
    champ = {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}}
    twin = {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20, "band_mult": 2.0}}
    # ma_cross 는 포지션이 0↔1 로 뛰므로 밴드가 1 미만이면 아무것도 안 막는다.
    # 시장 밴드 0.6 × 배수 2 = 1.2 → 쌍둥이는 거래를 전부 건너뛰고 챔피언은 돈다.
    diffs = R.holdout_diffs(champ, [twin], df, tail=100, build=R.build_strategy,
                            bt_kwargs={"rebalance_band": 0.6})
    assert len(diffs) == 1
    d = next(iter(diffs.values()))
    assert float(d.abs().sum()) > 0.0        # 배수 2 vs 1 — 같은 신호인데 회전이 달라 성적이 갈린다


# ── 승격된 배수를 체결기가 따른다 ───────────────────────────────────────────

def test_live_band_follows_the_champions_multiplier(tmp_path, monkeypatch):
    import quant.live.daily as D
    key = "crypto:BTC/USDT"
    (tmp_path / "champions.json").write_text(json.dumps({
        key: {"strategy": "ml", "params": {"model": "logreg", "band_mult": 2.0},
              "parliament": [{"strategy": "ml", "params": {"model": "logreg", "band_mult": 2.0},
                              "weight": 1.0}]}}), "utf-8")
    base = D._rebalance_band_rel("crypto", str(tmp_path))
    assert base > 0
    assert D._champion_band_rel(key, str(tmp_path)) == pytest.approx(base * 2.0)
    # 대조군 — 기록이 없는 종목은 배수 1(지금까지와 같다)
    assert D._champion_band_rel("crypto:ETH/USDT", str(tmp_path)) == pytest.approx(base)
