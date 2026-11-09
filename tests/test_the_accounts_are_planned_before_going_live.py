"""엔진을 온전히 따르려면 계좌마다 얼마가 필요한가 — 점검표가 말한다 (2026-11-09 감사 364)."""
from __future__ import annotations

import json

from quant.live import account_plan as A


def _ledger(tmp_path, applied, equity=1_000_000.0):
    (tmp_path / "paper").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps(
        {"history": [{"date": "2026-11-08", "equity": equity, "applied": applied}]}), "utf-8")


def test_the_targets_are_split_by_account(tmp_path):
    _ledger(tmp_path, {"kr_stock:069500.KS": 0.2, "us_stock:SPY": 0.3,
                       "us_stock:IEF": 0.2, "crypto:BTC/USDT": 0.1})
    p = A.plan(str(tmp_path))
    assert p["accounts"]["us_stock"]["krw"] == 500_000
    assert p["accounts"]["kr_stock"]["krw"] == 200_000
    assert abs(p["cash_weight"] - 0.2) < 1e-9
    assert abs(p["domestic_only_covers"] - 0.25) < 1e-9
    line = A.advisory(str(tmp_path))
    assert "25%만" in line and "매주" in line


def test_no_ledger_says_nothing(tmp_path):
    assert A.plan(str(tmp_path)) is None and A.advisory(str(tmp_path)) is None


def test_the_live_check_carries_it():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "quant" / "live" / "daily_live.py").read_text("utf-8")
    assert "from quant.live.account_plan import advisory" in src
