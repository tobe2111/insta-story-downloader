"""되돌린 날은 **장부의 대기 주문**을 체결한다 (2026-11-09 감사 359).

같은 날을 다시 계산할 때(검증 장부가 늦게 와서) 대기 주문을 **되감기 전에**
읽었다. 그래서 버려질 첫 회차가 다음 시가용으로 남긴 주문이 체결되고, 장부가
들고 있던 주문(전날 정한 것)은 조용히 사라졌다. 실측: 본 계좌 09-23·10-09 ·
섀도 09-23·11-04·11-06 — 체결 산술 검사(`test_fill_records_match_the_orders`)가
11-06에서 잡았다.

계좌를 실제로 돌려서 본다(함수 하나가 아니라 — 이 저장소는 "함수는 맞는데
순서가 틀렸다"로 당했다).
"""
from __future__ import annotations

import copy
import datetime as dt
import json

import numpy as np
import pandas as pd

import quant.live.daily as dl
from quant.live.redo import RESTORE_KEY


class _P:
    def __init__(self, frames):
        self._frames = frames

    def get_ohlcv(self, symbol, *a, **k):
        return self._frames[symbol].copy()


class _Flat:
    name, allow_short = "fixed", False

    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index)


def _frame(end, seed):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 300)))
    idx = pd.date_range(end=pd.Timestamp(end), periods=300, freq="D")
    return pd.DataFrame({"open": close * 0.995, "high": close * 1.01,
                         "low": close * 0.99, "close": close, "volume": 1e6}, index=idx)


def test_a_redo_fills_yesterdays_orders_not_the_discarded_runs(monkeypatch, tmp_path):
    today = pd.Timestamp(dt.date.today())
    yday = today - pd.Timedelta(days=1)
    frames = {"SPY": _frame(today, 1), "QQQ": _frame(today, 2)}
    monkeypatch.setattr(dl, "usdkrw", lambda *a, **k: 1400.0)
    monkeypatch.setattr("quant.data.get_provider", lambda m: _P(frames))
    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Flat())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    monkeypatch.setattr(dl, "bar_status", lambda *a, **k: None)

    bar = str(today.date())                 # 장부의 하루 이름(날짜)
    decided = str(yday)                     # 대기 주문의 결정 봉(봉 시각)
    on_books = {"us_stock:SPY": {"weight": 0.3, "slice": 1.0, "decided_bar": decided}}
    discarded = {"us_stock:QQQ": {"weight": 0.4, "slice": 1.0, "decided_bar": decided}}
    before = {"cash": 1_000_000.0, "positions": {}, "currency": "KRW",
              "base_prices": {"us_stock:SPY": 140_000.0, "us_stock:QQQ": 140_000.0},
              "last_bar": str(yday.date()), "pending": on_books, "pending_engine": "champions",
              "history": [{"date": str(yday.date()), "equity": 1_000_000.0,
                           "engine": None}]}
    after_first = copy.deepcopy(before)
    after_first.update({"last_bar": bar, "pending": discarded,
                        "history": before["history"] + [
                            {"date": str(today.date()), "equity": 1_000_000.0,
                             "validation_stamp": "옛 장부", "engine": None}]})
    after_first[RESTORE_KEY] = {"bar": bar, "state": copy.deepcopy(before)}
    (tmp_path / "paper").mkdir(parents=True)
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps(after_first), "utf-8")
    (tmp_path / "validation.json").write_text(json.dumps(
        {"us_stock:SPY": {"asof": str(today.date()), "pbo": 0.1}}), "utf-8")

    out = dl.run_daily_portfolio([("us_stock", "SPY"), ("us_stock", "QQQ")],
                                 state_dir=str(tmp_path), require_real_data=False)
    assert not out.get("skipped"), out
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))
    row = st["history"][-1]
    assert row["date"] == str(today.date()) and len(st["history"]) == 2
    filled = {f["key"] for f in row.get("fills") or [] if f.get("type") == "시가"}
    assert "us_stock:QQQ" not in filled, "버려진 첫 회차의 주문을 체결했다"
    assert "us_stock:SPY" in filled, "장부가 들고 있던 전날 주문이 사라졌다"
