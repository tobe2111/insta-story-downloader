"""단타냐 그냥 보유냐 — 운용 계좌가 기계로 고른다 (감사 345).

사장님(2026-10-11): "그냥 결과적으로 수익을 최대한 만들면 되는거야."
실험 계좌(사전 등록 90일)는 그대로 두고, 옆의 운용 계좌가 수수료 뺀
일수익 차이로 방식을 고른다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import intraday_challenger as IC  # noqa: E402
from quant.live import intraday_mode as M  # noqa: E402


def _rets(vals, start="2026-08-01"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="D"))


def test_hold_wins_only_when_it_clears_the_bar():
    rng = np.random.default_rng(3)
    trade = _rets(rng.normal(-0.002, 0.01, 40))
    hold = _rets(trade.values + 0.006 + rng.normal(0, 0.002, 40))
    op = M.new_account(10_000, "2026-09-10", "USDT")
    dec = M.decide(op, trade, hold, "2026-09-10")
    assert dec["choice"] == "hold" and dec["reason"] == "switch"
    assert dec["t"] >= dec["t_needed"] == round(M.t_switch(), 3)
    noisy = _rets(trade.values + rng.normal(0, 0.01, 40))
    assert M.decide(op, trade, noisy, "2026-09-10")["choice"] == "trade", (
        "우연과 구별 안 되는 차이로 갈아탔다")


def test_too_few_days_and_min_hold_keep_the_incumbent():
    trade, hold = _rets([0.0] * 10), _rets([0.05] * 10)
    op = M.new_account(10_000, "2026-08-11", "USDT")
    assert M.decide(op, trade, hold, "2026-08-11")["reason"] == "not_enough_days"
    trade, hold = _rets([0.0, 0.01] * 20), _rets([0.02, 0.03] * 20)
    op.update(mode="hold", mode_since="2026-09-05")
    dec = M.decide(op, hold, trade, "2026-09-10")
    assert dec["choice"] == "hold" and dec["reason"] == "min_hold"


def test_today_is_not_counted_and_decision_is_once_a_day():
    trade, hold = _rets([0.0, 0.01] * 20), _rets([0.02, 0.03] * 20)
    op = M.new_account(10_000, "2026-08-20", "USDT")
    dec = M.decide(op, trade, hold, "2026-08-25")
    assert dec["n_days"] == 24, "아직 안 끝난 날(오늘)과 미래가 창에 들어갔다"
    op.update(decided_on="2026-08-25", decision={"choice": "x"})
    assert M.decide(op, trade, hold, "2026-08-25") == {"choice": "x"}


def test_trade_returns_sort_mixed_offsets_by_time():
    rounds = [{"time": "2026-08-02T08:00:00+09:00", "equity": 100.0},   # 8/1 23:00 UTC
              {"time": "2026-08-01T10:00:00+00:00", "equity": 90.0},
              {"time": "2026-08-02T12:00:00+00:00", "equity": 110.0}]
    r = M.trade_daily_returns(rounds)
    assert len(r) == 1 and abs(r.iloc[0] - 0.10) < 1e-12, (
        "글자 정렬로 그날 마지막 자산을 잘못 골랐다")


def test_hold_mode_trades_only_outside_the_band():
    op = M.new_account(10_000, "2026-10-11", "USDT")
    op["mode"] = "hold"
    uni = ["A", "B"]
    px = {"A": 100.0, "B": 100.0}
    first = M.advance(op, mode_signals={"A": 0.0, "B": 0.0}, prices=px,
                      per_side=0.001, universe=uni, now_iso="2026-10-11T01:00:00+00:00")
    assert len(first["trades"]) == 2, "보유 모드가 첫날 사지 않았다"
    again = M.advance(op, mode_signals={}, prices={"A": 102.0, "B": 99.0},
                      per_side=0.001, universe=uni, now_iso="2026-10-11T02:00:00+00:00")
    assert again["trades"] == [], "밴드 안의 표류를 매번 고쳐 잡았다"
    assert op["cost_paid"] > 0, "보유도 사는 값은 낸다"


def _df(closes, start="2026-07-01"):
    idx = pd.date_range(start, periods=len(closes), freq="h")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 1.0}, index=idx)


class _Const:
    def __init__(self, sig):
        self.sig = sig

    def generate_signals(self, df):
        return pd.Series(self.sig, index=df.index)


def test_the_crypto_round_runs_the_operated_account_and_publishes_it(tmp_path):
    closes = list(np.linspace(100, 130, 24 * 60))
    data = {s: _df(closes) for s in IC.UNIVERSE}
    IC.run_intraday_round("2026-08-30T10:00:00+00:00",
                          state_dir=str(tmp_path / "state"),
                          docs_dir=str(tmp_path / "docs"), data=data,
                          strategy_factory=lambda s: _Const(0.0))
    st = IC.load_state(str(tmp_path / "state"))
    assert st["operated"]["decided_on"] == "2026-08-30"
    assert st["operated"]["decision"]["reason"] == "not_enough_days"
    out = IC.write_public_report(st, docs_dir=str(tmp_path / "docs"),
                                 state_dir=str(tmp_path / "state"))
    assert out["operated"]["mode"] == "trade"
    assert out["operated"]["rule"]["t_switch"] == round(M.t_switch(), 3)


def test_a_broken_operated_account_does_not_stop_the_experiment(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(M, "step", boom)
    data = {s: _df([100.0] * 100) for s in IC.UNIVERSE}
    v = IC.run_intraday_round("2026-07-05T10:00:00+00:00",
                              state_dir=str(tmp_path / "state"),
                              docs_dir=str(tmp_path / "docs"), data=data,
                              strategy_factory=lambda s: _Const(1.0))
    assert v["trades"] == len(IC.UNIVERSE)


def test_both_tracks_share_one_function_and_the_pages_show_it():
    us = (ROOT / "quant" / "live" / "intraday_us.py").read_text("utf-8")
    assert "operated_round(" in us, "미국 트랙이 운용 계좌를 안 굴린다"
    for page in ("intraday.html", "us.html"):
        html = (ROOT / "docs" / page).read_text("utf-8")
        assert "operated" in html, f"{page}가 운용 계좌를 안 보여 준다"
    i18n = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")
    for v in M.LABELS.values():
        assert f'"{v}":' in i18n, v
