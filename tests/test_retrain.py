"""야간 자동 재학습(quant/live/retrain.py) 계약 검사.

핵심 계약: 챌린저는 '선발전+결승전'을 모두 이겨야만 승격된다. 비기거나 지면
챔피언 유지가 정답이며, 그 결정 과정이 전부 파일로 기록되어야 한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.retrain import (  # noqa: E402
    DEFAULT_CHAMPION, append_history, champion_spec, champion_strategy,
    load_champions, mutate_champion, nightly_retrain, save_champions,
)


# ── 진화(돌연변이) 탐색 (pandas 불필요) ────────────────────────────────────

def test_mutate_champion_is_deterministic_and_bounded():
    spec = {"strategy": "ml", "params": {"model": "logreg", "threshold": 0.55,
                                         "train_window": 250, "retrain_every": 20}}
    a = mutate_champion(spec, seed="2026-08-04:crypto:BTC/USDT")
    b = mutate_champion(spec, seed="2026-08-04:crypto:BTC/USDT")
    assert a == b, "같은 시드는 같은 후보(멱등)여야 한다"
    assert 1 <= len(a) <= 4
    keys = [str(m) for m in a]
    assert len(keys) == len(set(keys)), "중복 후보 금지"
    for m in a:
        assert m != spec, "챔피언 자신은 후보가 아니다"
        th = m["params"].get("threshold", 0.55)
        assert 0.52 <= th <= 0.70, "임계는 보수적 경계 안에서만 변형"
    # 다른 날(시드)에는 다른 주변을 탐색한다
    c = mutate_champion(spec, seed="2026-08-05:crypto:BTC/USDT")
    assert c != a


def test_mutate_champion_non_ml_strategy():
    """전통 전략 챔피언도 수치 파라미터를 변형해 진화를 잇는다."""
    spec = {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}}
    muts = mutate_champion(spec, seed="2026-08-04:test")
    assert muts, "후보가 나와야 한다"
    for m in muts:
        assert m["strategy"] == "ma_cross"
        assert m["params"] != spec["params"]
        for v in m["params"].values():
            assert isinstance(v, int) and v >= 2


# ── 상태 파일 (pandas 불필요 — 어디서나 실행) ──────────────────────────────

def test_champions_roundtrip(tmp_path):
    d = str(tmp_path)
    assert load_champions(d) == {}
    data = {"crypto:BTC/USDT": {"strategy": "ml", "params": {"model": "gb"},
                                "promotions": 1}}
    save_champions(data, d)
    assert load_champions(d) == data


def test_history_append(tmp_path):
    d = str(tmp_path)
    append_history({"asof": "2026-01-01", "promoted": False}, d)
    append_history({"asof": "2026-01-02", "promoted": True}, d)
    lines = (tmp_path / "retrain_history.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["promoted"] is True


def test_champion_spec_falls_back_to_default(tmp_path):
    """기록이 없어도(새 설치/실행파일) 기본 챔피언으로 항상 동작해야 한다."""
    spec = champion_spec("crypto", "BTC/USDT", str(tmp_path))
    assert spec == {"strategy": DEFAULT_CHAMPION["strategy"],
                    "params": DEFAULT_CHAMPION["params"]}
    spec["params"]["model"] = "변조"          # 반환값 변조가 원본을 오염시키면 안 됨
    assert DEFAULT_CHAMPION["params"]["model"] == "logreg"


def test_champion_spec_reads_promoted(tmp_path):
    d = str(tmp_path)
    save_champions({"crypto:BTC/USDT": {
        "strategy": "ml", "params": {"model": "gb", "threshold": 0.6},
        "promotions": 1}}, d)
    assert champion_spec("crypto", "BTC/USDT", d)["params"]["model"] == "gb"
    # 다른 종목은 여전히 기본 챔피언
    assert champion_spec("crypto", "ETH/USDT", d)["params"]["model"] == "logreg"


# ── 승격 판정 (pandas 필요 — CI에서 실행) ──────────────────────────────────

def _dummy_setup():
    """우상향 데이터 + 더미 전략 2종(항상 매수 vs 항상 관망)을 만든다."""
    import numpy as np
    import pandas as pd

    from quant.strategies.base import Strategy

    rng = np.random.default_rng(7)
    n = 500
    ret = 0.002 + rng.normal(0, 0.004, n)     # 뚜렷한 상승 추세 + 작은 잡음
    close = 100 * np.cumprod(1 + ret)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1.0}, index=idx)

    class Dummy(Strategy):
        name = "dummy"

        def __init__(self, which: str = "flat"):
            self.which = which

        def generate_signals(self, df):
            v = 1.0 if self.which == "up" else 0.0
            return pd.Series(v, index=df.index)

    build = lambda spec: Dummy(**spec.get("params", {}))  # noqa: E731
    return df, build


def test_promotes_clearly_better_challenger():
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "flat"}}
    out = nightly_retrain(df, champion, [{"which": "up"}], build=build,
                          confirm_window=120)
    assert out["promoted"] is True
    assert out["champion"]["params"]["which"] == "up"
    assert "승격" in out["reason"]


def test_keeps_champion_when_no_better_candidate():
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "up"}}
    # 챌린저(관망)는 상승장에서 챔피언(매수)을 이길 수 없다 → 유지
    out = nightly_retrain(df, champion, [{"which": "flat"}], build=build,
                          confirm_window=120)
    assert out["promoted"] is False
    assert "유지" in out["reason"]


def test_skips_challenger_identical_to_champion():
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "up"}}
    out = nightly_retrain(df, champion, [{"which": "up"}], build=build,
                          confirm_window=120)
    assert out["promoted"] is False
    assert out["candidates"] == []             # 자기 자신과의 대결은 건너뜀


def test_cross_strategy_challenger_can_win():
    """전통 전략도 {"strategy": ...} 형식으로 참전해 챔피언이 될 수 있다."""
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "flat"}}
    out = nightly_retrain(
        df, champion, [{"strategy": "dummy", "params": {"which": "up"}}],
        build=build, confirm_window=120)
    assert out["promoted"] is True
    assert out["champion"] == {"strategy": "dummy", "params": {"which": "up"}}


def test_cross_strategy_identical_champion_is_skipped():
    """새 형식이라도 챔피언과 전략·파라미터가 같으면 대결하지 않는다."""
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "up"}}
    out = nightly_retrain(
        df, champion, [{"strategy": "dummy", "params": {"which": "up"}}],
        build=build, confirm_window=120)
    assert out["candidates"] == []


def test_insufficient_data_keeps_champion():
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "flat"}}
    out = nightly_retrain(df.iloc[:100], champion, [{"which": "up"}],
                          build=build, confirm_window=120)
    assert out["promoted"] is False
    assert "데이터 부족" in out["reason"]


def test_champion_strategy_hot_reloads_on_promotion(tmp_path):
    """야간 승격이 일어나면 실행 중인 봇이 재시작 없이 새 챔피언으로 갈아탄다."""
    df, _build = _dummy_setup()
    d = str(tmp_path)
    save_champions({"crypto:BTC/USDT": {
        "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
        "promotions": 0}}, d)

    strat = champion_strategy("crypto", "BTC/USDT", d)
    strat.generate_signals(df)
    assert strat._impl.fast == 5               # 저장된 챔피언을 위임 실행

    # 야간 재학습이 챔피언을 교체했다고 가정
    save_champions({"crypto:BTC/USDT": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 40},
        "promotions": 1}}, d)
    strat.generate_signals(df)
    assert strat._impl.fast == 10              # 재시작 없이 자동 반영


def test_run_retrain_writes_state(tmp_path, monkeypatch=None):
    """합성 데이터 + 실제 MLStrategy(logreg 1종)로 전체 경로를 얇게 통과한다."""
    import quant.live.retrain as rt

    # 후보 1개(logreg 변형)만 남겨 CI 시간을 아낀다 — 경로 검증이 목적.
    orig = rt.DEFAULT_CHALLENGERS
    rt.DEFAULT_CHALLENGERS = [{"model": "logreg", "threshold": 0.60}]
    try:
        out = rt.run_retrain("synthetic", "DEMO", limit=400,
                             state_dir=str(tmp_path), confirm_window=100,
                             require_real_data=False, evolve=False)
    finally:
        rt.DEFAULT_CHALLENGERS = orig

    assert "champion" in out and isinstance(out["promoted"], bool)
    champs = load_champions(str(tmp_path))
    assert "synthetic:DEMO" in champs          # 첫 실행도 챔피언을 명시 기록
    hist = (tmp_path / "retrain_history.jsonl").read_text(encoding="utf-8")
    assert '"promoted"' in hist
