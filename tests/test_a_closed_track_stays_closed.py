"""닫은 트랙은 회차를 안 돌리고, 최종 성적은 정리 비용을 뺀다 (2026-11-09 감사 357)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from quant.live import track_closure as TC

ROOT = Path(__file__).resolve().parent.parent


def test_the_exit_cost_is_deducted_from_the_final_result():
    held, cost = TC.exit_cost({"A": 2.0, "B": -1.0}, {"A": 100.0, "B": 50.0},
                              lambda s: 0.001)
    assert held == 250.0 and abs(cost - 0.25) < 1e-12
    st = {"start_cash": 1000.0, "cash": 750.0, "positions": {"A": 2.0},
          "last_prices": {"A": 125.0}, "rounds": [{"time": "t", "equity": 1000.0}]}
    c = TC.closure("intraday", st, lambda s: 0.002)
    assert c["final_equity"] == 999.5 and c["return_pct"] == -0.05


def test_closing_is_idempotent_and_repairs_the_futures_operated_account(tmp_path):
    shutil.copytree(ROOT / "state", tmp_path / "state",
                    ignore=shutil.ignore_patterns("*.jsonl"))
    (tmp_path / "docs").mkdir()
    for f in ("intraday.json", "intraday_us.json", "futures.json"):
        shutil.copy(ROOT / "docs" / f, tmp_path / "docs" / f)
    first = TC.close_all(str(tmp_path / "state"), str(tmp_path / "docs"), say=lambda *a: None)
    again = TC.close_all(str(tmp_path / "state"), str(tmp_path / "docs"), say=lambda *a: None)
    assert first == again and set(first) == set(TC.TRACKS)
    fut = json.loads((tmp_path / "docs" / "futures.json").read_text("utf-8"))
    assert fut["closed"]["operated"]["final_equity"] > 0, "−578% 오류가 최종 성적이 됐다"
    assert fut["operated"]["equity"] > 0
    for f in ("intraday.json", "intraday_us.json"):
        pub = json.loads((tmp_path / "docs" / f).read_text("utf-8"))
        assert pub["closed"]["exit_cost"] >= 0 and pub["closed"]["on"] == TC.CLOSED_ON


def test_the_rounds_do_not_run_once_closed(tmp_path, monkeypatch):
    from quant import cli
    import quant.live.intraday_challenger as IC
    import quant.live.futures_challenger as FC

    def boom(*a, **k):
        raise AssertionError("닫힌 트랙이 회차를 돌렸다")
    monkeypatch.setattr(IC, "run_intraday_round", boom)
    monkeypatch.setattr(FC, "run_futures_round", boom)
    monkeypatch.setattr(TC, "close_all", lambda *a, **k: {})
    args = SimpleNamespace(state_dir=str(tmp_path), docs_dir=str(tmp_path))
    cli._cmd_intraday_round(args)
    cli._cmd_futures_round(args)


def test_the_pages_say_the_track_is_closed_and_trust_records_it():
    for page, doc in (("intraday", "intraday.json"), ("us", "intraday_us.json"),
                      ("futures", "futures.json")):
        html = (ROOT / "docs" / f"{page}.html").read_text("utf-8")
        assert f'data-closed="{doc}"' in html and "assets/closed.js" in html
    from quant.live.prereg import AMENDMENTS
    assert sum(a["on"] == TC.CLOSED_ON for a in AMENDMENTS) >= 1
