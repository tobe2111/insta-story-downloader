"""닫았던 트랙을 2기로 다시 연다 — 1기 최종 자산을 현금으로 이어받는다 (2026-11-10 감사 366)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from quant.live import prereg as P
from quant.live import sequential as S
from quant.live import track_closure as TC

ROOT = Path(__file__).resolve().parent.parent


def _closed_book():
    return {"start_cash": 10000.0, "cash": 100.0, "cost_paid": 50.0,
            "positions": {"BTC": 1.0}, "avg_cost": {"BTC": 9000.0},
            "last_prices": {"BTC": 9000.0},
            "rounds": [{"time": "2026-11-09T10:00:00+09:00", "equity": 9100.0}],
            "limit_shadow": {"since": "2026-08-18", "start_equity": 10000.0, "cash": 1.0,
                             "positions": {"BTC": 1.0}, "cost_paid": 3.0,
                             "filled_total": 5, "unfilled_total": 2},
            "operated": {"start_cash": 10000.0, "cash": 200.0, "cost_paid": 10.0,
                         "positions": {"BTC": 1.0}, "avg_cost": {"BTC": 9000.0},
                         "last_prices": {"BTC": 9000.0}, "mode": "hold", "history": []}}


def test_season_two_starts_from_the_closing_cash_and_keeps_season_one():
    st = _closed_book()
    st["closed"] = TC.closure("intraday", st, lambda s: 0.001)
    final, op_final = st["closed"]["final_equity"], st["closed"]["operated"]["final_equity"]
    assert TC.reopen("intraday", st) is True
    assert TC.reopen("intraday", st) is False, "두 번 열면 1기를 또 얼린다"
    assert st["cash"] == final and st["positions"] == {} and st["avg_cost"] == {}
    # 정리 비용은 실제로 낸 비용 — 안 세면 '낸 비용' 칸이 자산 변화와 안 맞는다.
    assert abs(st["cost_paid"] - (50.0 + st["seasons"][0]["exit_cost"])) < 1e-9
    op = st["operated"]
    assert op["cash"] == op_final and op["positions"] == {}
    assert "closed" not in st and "limit_shadow" not in st
    s1 = st["seasons"][0]
    assert s1["n"] == 1 and s1["final_equity"] == final
    assert s1["limit_shadow_final"]["filled_total"] == 5
    assert st["season"]["n"] == 2 and st["season"]["start_equity"] == round(final, 2)
    assert not TC.is_closed("intraday")


def test_the_futures_operated_book_reopens_at_its_final_equity():
    st = {"start_cash": 10000.0, "cash": 8000.0, "positions": {"BTC/USDT": -0.1},
          "rounds": [{"at": "t", "equity": 8100.0, "positions": {"BTC/USDT": -0.1},
                      "prices": {"BTC/USDT": 1000.0}}],
          "operated": {"start_cash": 10000.0, "equity": 8700.0, "peak": 10000.0,
                       "mode": "cash", "history": []}}
    st["closed"] = TC.closure("futures", st, lambda s: 0.001)
    assert TC.reopen("futures", st)
    assert st["positions"] == {} and st["cash"] == st["seasons"][0]["final_equity"]
    assert st["operated"]["equity"] == 8700.0, "현금 모드는 정리할 것이 없다"


def test_the_public_season_block_reports_this_season_and_the_last():
    st = _closed_book()
    st["closed"] = TC.closure("intraday", st, lambda s: 0.0)
    TC.reopen("intraday", st)
    pub = TC.season_public(st, st["season"]["start_equity"] * 1.1)
    assert pub["n"] == 2 and abs(pub["return_pct"] - 10.0) < 0.01
    assert pub["operated_return_pct"] == 0.0
    assert pub["previous"][0]["n"] == 1 and pub["previous"][0]["on"] == TC.CLOSED_ON
    assert TC.season_public({}) is None


def test_the_real_books_reopen_once(tmp_path):
    shutil.copytree(ROOT / "state", tmp_path / "state",
                    ignore=shutil.ignore_patterns("*.jsonl"))
    for t, meta in TC.TRACKS.items():
        p = tmp_path / "state" / Path(*meta["state"])
        st = json.loads(p.read_text("utf-8"))
        had = bool(st.get("closed"))
        assert TC.reopen_track(t, str(tmp_path / "state"), say=lambda *a: None) is had
        assert TC.reopen_track(t, str(tmp_path / "state"), say=lambda *a: None) is False
        st = json.loads(p.read_text("utf-8"))
        assert "closed" not in st
        if had:
            assert st["positions"] == {} and st["season"]["n"] >= 2


def test_the_round_opens_season_two_before_trading(tmp_path, monkeypatch):
    from quant import cli
    import quant.live.futures_challenger as FC
    import quant.live.intraday_challenger as IC

    seen = []
    monkeypatch.setattr(cli, "_halted", lambda a: False)
    monkeypatch.setattr(TC, "reopen_track", lambda t, *a, **k: seen.append(("open", t)))

    def coin(*a, **k):
        seen.append(("round", "intraday"))
        return {"equity": 1.0, "return_pct": 0.0, "trades": 0, "skipped": 0, "cost_paid": 0.0}
    monkeypatch.setattr(IC, "run_intraday_round", coin)
    import quant.live.intraday_us as US
    monkeypatch.setattr(US, "run_us_round", lambda *a, **k: seen.append(("round", "us")) or {"skipped": "장 닫힘"})
    class _Stop(Exception):
        pass

    def fut(*a, **k):
        seen.append(("round", "futures"))
        raise _Stop
    monkeypatch.setattr(FC, "run_futures_round", fut)
    args = SimpleNamespace(state_dir=str(tmp_path), docs_dir=str(tmp_path))
    cli._cmd_intraday_round(args)
    try:
        cli._cmd_futures_round(args)
    except _Stop:
        pass
    assert seen.index(("open", "intraday")) < seen.index(("round", "intraday"))
    assert seen.index(("open", "intraday_us")) < seen.index(("round", "us"))
    assert seen.index(("open", "futures")) < seen.index(("round", "futures"))


def test_season_two_is_registered_before_its_first_round():
    for key in ("intraday_s2", "intraday_us_s2", "futures_s2"):
        exp = P.PREREGISTERED[key]
        assert exp["start"] == TC.REOPENED[{"intraday_s2": "intraday",
                                            "intraday_us_s2": "intraday_us",
                                            "futures_s2": "futures"}[key]]
        assert S.registered_comparisons(exp) == 1
        assert key in S.SEASON2
    # 단타 2기는 옛 챔피언 신호로 돈다 — 은퇴일이 그 판정일보다 앞서면 실험이 무효다.
    assert P.ml_retire_after() >= P.PREREGISTERED["intraday_s2"]["judge_on"]
    assert any(a["on"] == "2026-11-10" for a in P.AMENDMENTS)
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert "2026-11-10 정정" in trust and P.PREREGISTERED["intraday_s2"]["judge_on"] in trust


def test_season_two_pairs_ignore_season_one(tmp_path):
    (tmp_path / "paper").mkdir()
    (tmp_path / "intraday").mkdir()
    main = [{"date": f"2026-11-{d:02d}", "equity": 1000 + d} for d in range(1, 21)]
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps({"history": main}))
    op = [{"time": f"2026-11-{d:02d}T10:00:00+09:00", "equity": 900 + d * 2}
          for d in range(1, 21)]
    (tmp_path / "intraday" / "challenger.json").write_text(
        json.dumps({"operated": {"history": op}}))
    pairs = S._pairs_for("intraday_s2", str(tmp_path))
    (name, diffs), = pairs.items()
    assert name == "intraday_s2:operated-main"
    # 11-10~11-20 = 11일 → 일수익 10개. 1기(11-01~11-09)가 섞이면 19개가 된다.
    assert len(diffs) == 10


def test_the_closed_card_draws_the_season_and_speaks_english():
    js = (ROOT / "docs" / "assets" / "closed.js").read_text("utf-8")
    en = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")
    assert "d.season" in js and "renderSeason" in js
    for ko in re.findall(r'el\("(?:h2|span|div)", "([^"]+)"', js):
        assert f'"{ko}"' in en, f"영어 사전에 없다: {ko}"
