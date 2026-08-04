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
    append_history, load_champions, nightly_retrain, save_champions,
)


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


def test_insufficient_data_keeps_champion():
    df, build = _dummy_setup()
    champion = {"strategy": "dummy", "params": {"which": "flat"}}
    out = nightly_retrain(df.iloc[:100], champion, [{"which": "up"}],
                          build=build, confirm_window=120)
    assert out["promoted"] is False
    assert "데이터 부족" in out["reason"]


def test_run_retrain_writes_state(tmp_path, monkeypatch=None):
    """합성 데이터 + 실제 MLStrategy(logreg 1종)로 전체 경로를 얇게 통과한다."""
    import quant.live.retrain as rt

    # 후보 1개(logreg 변형)만 남겨 CI 시간을 아낀다 — 경로 검증이 목적.
    orig = rt.DEFAULT_CHALLENGERS
    rt.DEFAULT_CHALLENGERS = [{"model": "logreg", "threshold": 0.60}]
    try:
        out = rt.run_retrain("synthetic", "DEMO", limit=400,
                             state_dir=str(tmp_path), confirm_window=100,
                             require_real_data=False)
    finally:
        rt.DEFAULT_CHALLENGERS = orig

    assert "champion" in out and isinstance(out["promoted"], bool)
    champs = load_champions(str(tmp_path))
    assert "synthetic:DEMO" in champs          # 첫 실행도 챔피언을 명시 기록
    hist = (tmp_path / "retrain_history.jsonl").read_text(encoding="utf-8")
    assert '"promoted"' in hist
