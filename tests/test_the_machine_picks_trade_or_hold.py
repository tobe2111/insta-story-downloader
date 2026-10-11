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
    dec = M.decide(op, {"trade": trade, "hold": hold}, "2026-09-10")
    assert dec["choice"] == "hold" and dec["reason"] == "switch"
    assert dec["t"] >= dec["t_needed"] == round(M.t_switch(2), 3)
    noisy = _rets(trade.values + rng.normal(0, 0.01, 40))
    assert M.decide(op, {"trade": trade, "hold": noisy}, "2026-09-10")["choice"] == "trade", (
        "우연과 구별 안 되는 차이로 갈아탔다")


def test_too_few_days_and_min_hold_keep_the_incumbent():
    trade, hold = _rets([0.0] * 10), _rets([0.05] * 10)
    op = M.new_account(10_000, "2026-08-11", "USDT")
    assert M.decide(op, {"trade": trade, "hold": hold}, "2026-08-11")["reason"] == "not_enough_days"
    trade, hold = _rets([0.0, 0.01] * 20), _rets([0.02, 0.03] * 20)
    op.update(mode="hold", mode_since="2026-09-05")
    dec = M.decide(op, {"trade": hold, "hold": trade}, "2026-09-10")
    assert dec["choice"] == "hold" and dec["reason"] == "min_hold"


def test_today_is_not_counted_and_decision_is_once_a_day():
    trade, hold = _rets([0.0, 0.01] * 20), _rets([0.02, 0.03] * 20)
    op = M.new_account(10_000, "2026-08-20", "USDT")
    dec = M.decide(op, {"trade": trade, "hold": hold}, "2026-08-25")
    assert dec["n_days"] == 24, "아직 안 끝난 날(오늘)과 미래가 창에 들어갔다"
    op.update(decided_on="2026-08-25", decision={"choice": "x"})
    assert M.decide(op, {"trade": trade, "hold": hold}, "2026-08-25") == {"choice": "x"}


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
    assert out["operated"]["rule"]["t_switch"] == st["operated"]["decision"]["t_needed"]


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


def test_the_operated_account_continues_the_experiment_not_from_zero():
    st = {"start_cash": 10_000.0, "currency": "USDT", "cash": 2_000.0,
          "positions": {"BTC/USDT": 0.1}, "avg_cost": {"BTC/USDT": 70_000.0},
          "cost_paid": 607.0, "peak_equity": 10_700.0,
          "rounds": [{"time": "2026-08-18T05:00:00+00:00", "equity": 10_000.0},
                     {"time": "2026-08-18T09:00:00+09:00", "equity": 9_990.0},
                     {"time": "2026-10-11T05:00:00+00:00", "equity": 9_981.0}]}
    op = M.continue_from(st, "2026-10-11")
    assert op["cash"] == 2_000.0 and op["positions"] == {"BTC/USDT": 0.1}
    assert op["start_cash"] == 10_000.0 and op["since"] == "2026-08-18"
    assert op["cost_paid"] == 607.0 and op["peak_equity"] == 10_700.0
    assert [h["equity"] for h in op["history"]] == [10_000.0, 9_981.0]
    op["positions"]["BTC/USDT"] = 0.0
    assert st["positions"]["BTC/USDT"] == 0.1, "복사가 아니라 같은 dict를 공유한다"
    out = M.public({"operated": op})
    assert out["return_pct"] == round((9_981.0 / 10_000.0 - 1) * 100, 4)


# ── 감사 346 — 사다리 트랙(15분·5분)도 후보 ─────────────────────────

def test_a_ladder_track_can_win_and_the_bar_rises_with_more_modes():
    rng = np.random.default_rng(5)
    trade = _rets(rng.normal(-0.002, 0.01, 40))
    t15 = _rets(trade.values + 0.006 + rng.normal(0, 0.002, 40))
    hold = _rets(trade.values + rng.normal(0, 0.01, 40))
    op = M.new_account(10_000, "2026-09-10", "USDT")
    dec = M.decide(op, {"trade": trade, "hold": hold, "trade_15m": t15}, "2026-09-10")
    assert dec["choice"] == "trade_15m" and dec["best_challenger"] == "trade_15m"
    assert set(dec["table"]) == {"trade", "hold", "trade_15m"}
    assert M.t_switch(8) > M.t_switch(4), "후보가 늘었는데 문턱이 그대로다"


def test_following_a_track_copies_its_weights_at_its_prices():
    track = {"cash": 5_000.0, "positions": {"A": 50.0},
             "last_prices": {"A": 100.0, "B": 10.0}}
    sig, px = M.follow_signals(track, ["A", "B"])
    assert px == {"A": 100.0, "B": 10.0}
    assert sig["A"] == 1.0 and sig["B"] == 0.0     # 비중 50% × 종목 2 = 1.0
    op = M.new_account(10_000, "2026-10-11", "USDT")
    op["mode"] = "trade_15m"
    M.advance(op, mode_signals={"A": 0.0, "B": 0.0}, prices={"A": 90.0, "B": 9.0},
              per_side=0.0, universe=["A", "B"], now_iso="2026-10-11T01:00:00+00:00",
              tracks={"trade_15m": track})
    assert abs(op["positions"]["A"] * 100.0 / 10_000 - 0.5) < 1e-9, (
        "트랙 비중을 따라가지 않았거나 묵은 가격으로 샀다")


def test_the_ladder_keeps_its_last_prices_for_followers():
    src = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")
    assert 'st["last_prices"] = {**(st.get("last_prices") or {}), **prices}' in src


# ── 감사 346 — 선물 운용 계좌(엔진 그대로 / 코인 보유 / 현금) ──────────

def _fut_rounds(n=40, drift=-0.004, seed=9):
    rng = np.random.default_rng(seed)
    eq, px, out = 10_000.0, 100.0, []
    for i in range(n):
        eq *= 1 + drift + rng.normal(0, 0.002)
        px *= 1 + rng.normal(0.001, 0.01)
        day = pd.Timestamp("2026-08-23") + pd.Timedelta(days=i)
        out.append({"at": f"{day.date()}T15:00:00+09:00", "equity": eq,
                    "gross_exposure": 0.8, "prices": {"BTC/USDT": px, "ETH/USDT": px}})
    return out


def test_futures_account_inherits_the_curve_and_leaves_a_losing_engine():
    from quant.live import futures_mode as F
    st = {"start_cash": 10_000.0, "rounds": _fut_rounds()}
    last_day = pd.Timestamp(st["rounds"][-1]["at"]).tz_convert("UTC").date()
    today = str(last_day + pd.Timedelta(days=1))
    F.step(st, now_iso=f"{today}T01:00:00+00:00", per_side=0.001)
    op = st["operated"]
    assert op["since"] == "2026-08-23" and op["history"][0]["inherited"]
    assert op["equity"] < 10_000.0, "이어받은 손실이 사라졌다(0에서 시작했다)"
    assert op["mode"] in ("cash", "hold"), op["decision"]
    assert op["switches"] and op["cost_paid"] > 0, "갈아탈 때 비용을 안 뗐다"
    out = F.public(st)
    assert out["rule"]["modes"] == F.LABELS and out["as_of"]


def test_futures_account_compounds_finished_days_once():
    from quant.live import futures_mode as F
    st = {"start_cash": 10_000.0, "rounds": _fut_rounds(n=10)}
    F.step(st, now_iso="2026-09-02T01:00:00+00:00", per_side=0.0)
    before = st["operated"]["equity"]
    F.step(st, now_iso="2026-09-02T05:00:00+00:00", per_side=0.0)
    assert st["operated"]["equity"] == before, "같은 날 두 번 곱했다"


def test_the_futures_page_shows_the_operated_account():
    html = (ROOT / "docs" / "futures.html").read_text("utf-8")
    assert 'data-operated="futures.json"' in html and "assets/operated.js" in html
    cli = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "futures_mode.step(" in cli
