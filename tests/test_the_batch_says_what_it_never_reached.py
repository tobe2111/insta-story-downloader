"""밤 배치 장부의 산술이 닫히는가 — 명단 40, 심사 24, 실패 0, 건너뜀 0.

■ 왜 (2026-09-01 실측)

밤 배치에는 시간 예산이 있어 명단 끝까지 못 가고 끊긴다. 그런데 그렇게
**한 번도 손대지 않은** 종목은 실패도 건너뜀도 아니라, 장부의 세 칸
(ok·failed·skipped) 어디에도 안 들어간다. 그날 밤의 실제 기록:

    명단 40종목 · 심사 24 · 실패 0 · 건너뜀 0   → 어느 칸에도 없음 16

24 ≠ 40인데 그 사실이 어디에도 안 적힌다. 화면과 경보는 "실패 0 · 건너뜀 0"
만 보고 **깨끗하게 끝난 밤**으로 읽는다. 그 16이라는 숫자는 이어달리기 커서
파일에만 있고 어떤 경보도 그 파일을 안 읽는다. 정체 경보도 `skipped` 목록만
먹으므로, 예산에 밀려 계속 뒤로 가는 종목이 생겨도 빨간불이 안 뜬다.

⚠️ **정직하게 — 지금 굶는 종목은 없다.** 40종목 전부가 최근 다섯 밤 안에
오디션을 받았고 최악의 간격은 3밤이다. 이어달리기는 설계대로 돌고 있다.
이건 실측된 사고가 아니라 **기록의 구멍**이다.
"""
from __future__ import annotations

import json

import pytest

import quant.live.retrain as R
from quant.live.daily import _write_run_health

ROSTER = [f"m:{i}" for i in range(10)]


def _health(tmp_path) -> dict:
    return json.loads((tmp_path / "run_health.json").read_text("utf-8"))


def test_the_ledger_says_how_many_it_never_reached(tmp_path):
    """명단을 주면 못 돈 종목이 수와 이름으로 남는다."""
    _write_run_health(str(tmp_path), "retrain", ROSTER[:6], {},
                      skipped=[ROSTER[6]], roster=ROSTER)
    e = _health(tmp_path)["retrain"]
    assert e["roster"] == 10
    assert e["not_reached"] == 3
    assert e["not_reached_keys"] == ROSTER[7:]
    # 산술이 닫힌다 — 이게 이 기록의 존재 이유다.
    assert e["ok"] + e["failed"] + e["skipped"] + e["not_reached"] == 10


def test_without_a_roster_the_hole_is_invisible(tmp_path):
    """대조군 — 명단을 안 주면 "실패 0 · 건너뜀 0"만 남는다(고치기 전 모습)."""
    _write_run_health(str(tmp_path), "retrain", ROSTER[:6], {})
    e = _health(tmp_path)["retrain"]
    assert e["ok"] == 6 and e["failed"] == 0 and e["skipped"] == 0
    assert "not_reached" not in e          # 못 돈 4종목이 어디에도 없다


def test_the_second_run_of_a_night_clears_what_it_covered(tmp_path):
    """밤의 2회차가 1회차의 못 돈 종목을 돌면 목록에서 빠진다.

    ⚠️ 못 돈 종목을 따로 받아 적으면 두 회차의 값이 어긋난다. 명단에서
       빼서 구하므로 합쳐진 성적이 자동으로 반영된다.
    """
    _write_run_health(str(tmp_path), "retrain", ROSTER[:6], {}, roster=ROSTER)
    assert _health(tmp_path)["retrain"]["not_reached"] == 4
    _write_run_health(str(tmp_path), "retrain", ROSTER[6:9], {}, roster=ROSTER)
    e = _health(tmp_path)["retrain"]
    assert e["runs"] == 2 and e["ok"] == 9
    assert e["not_reached"] == 1 and e["not_reached_keys"] == [ROSTER[9]]


def test_a_night_that_finished_says_zero_not_nothing(tmp_path):
    """다 돈 밤은 **0이라고 말한다** — 칸이 없는 것과 0은 다른 사건이다."""
    _write_run_health(str(tmp_path), "retrain", ROSTER, {}, roster=ROSTER)
    e = _health(tmp_path)["retrain"]
    assert e["not_reached"] == 0 and e["not_reached_keys"] == []


def test_the_batch_really_hands_its_roster_down(monkeypatch, tmp_path):
    """배선을 **돌려서** 확인한다 — 명단을 안 넘기면 장부에 칸이 안 생긴다.

    예산에 걸려 끊기는 상황을 만들기 위해 마감을 이미 지난 시각으로 준다.
    """
    seen: list = []

    def fake_run_retrain(market, symbol, **kw):
        seen.append(f"{market}:{symbol}")
        return {"skipped": False, "asof": "2026-09-01", "panel_diffs": {}}

    monkeypatch.setattr(R, "run_retrain", fake_run_retrain)
    targets = [("crypto", "BTC/USDT"), ("us_stock", "AAPL"),
               ("kr_stock", "005930")]
    R.run_retrain_all(targets=targets, state_dir=str(tmp_path))
    e = _health(tmp_path)["retrain"]
    assert e["roster"] == 3
    assert e["not_reached"] == 0
    assert len(seen) == 3


def test_a_budget_cut_night_is_recorded_as_cut(monkeypatch, tmp_path):
    """예산에 걸려 끊긴 밤 — 못 돈 종목이 장부에 그대로 남는다.

    이게 이 기록의 존재 이유다. 예전에는 이런 밤도 "실패 0 · 건너뜀 0"으로
    남아, 명단의 절반이 손도 안 닿았는데 깨끗하게 끝난 밤처럼 보였다.
    """
    import time as _t

    def fake_run_retrain(market, symbol, **kw):
        return {"skipped": False, "asof": "2026-09-01", "panel_diffs": {}}

    # 마감 계산에는 정상값을 주고, 그 뒤로는 이미 지난 시각을 준다.
    calls = {"n": 0}
    real = _t.monotonic

    def fake_monotonic():
        calls["n"] += 1
        return real() if calls["n"] == 1 else 1e18

    monkeypatch.setattr(R, "run_retrain", fake_run_retrain)
    monkeypatch.setattr(_t, "monotonic", fake_monotonic)
    monkeypatch.setenv("QUANT_RETRAIN_BUDGET_SEC", "1")
    targets = [("crypto", "BTC/USDT"), ("us_stock", "AAPL"),
               ("kr_stock", "005930")]
    R.run_retrain_all(targets=targets, state_dir=str(tmp_path))
    e = _health(tmp_path)["retrain"]
    assert e["roster"] == 3
    assert e["not_reached"] == 3, e
    assert e["ok"] == 0 and e["failed"] == 0 and e["skipped"] == 0
    # 대조 — 커서에도 같은 목록이 남는다(두 기록이 어긋나면 안 된다).
    cur = json.loads((tmp_path / "retrain_cursor.json").read_text("utf-8"))
    assert sorted(cur["not_reached"]) == sorted(e["not_reached_keys"])


def test_a_night_cut_before_the_first_symbol_is_not_called_a_wipeout(
        monkeypatch, tmp_path):
    """예산이 첫 종목 전에 지났으면 "전 종목 실패"라고 말하지 않는다.

    이 자리는 위 기록을 붙이다 드러났다: `ok`도 `skipped`도 비면 배치가
    ``전 종목 재학습 실패: {}``를 던진다 — **실패한 종목이 하나도 없는데**
    전멸이라고 말하는 것이고, 그러면 진짜 전멸과 구별이 안 된다.
    """
    import time as _t

    monkeypatch.setattr(R, "run_retrain", lambda *a, **k: {"skipped": False})
    calls = {"n": 0}
    real = _t.monotonic
    monkeypatch.setattr(_t, "monotonic", lambda: (
        calls.update(n=calls["n"] + 1) or (real() if calls["n"] == 1 else 1e18)))
    monkeypatch.setenv("QUANT_RETRAIN_BUDGET_SEC", "1")
    out = R.run_retrain_all(targets=[("crypto", "BTC/USDT")],
                            state_dir=str(tmp_path))
    assert out["ok"] == [] and out["failed"] == {}


def test_a_real_wipeout_is_still_raised(monkeypatch, tmp_path):
    """대조군 — 진짜로 전 종목이 실패하면 그대로 예외를 올린다.

    이게 없으면 위 검사는 "예외를 아예 없애도" 통과한다.
    """
    def boom(*a, **k):
        raise RuntimeError("데이터 수신 실패")

    monkeypatch.setattr(R, "run_retrain", boom)
    with pytest.raises(RuntimeError, match="전 종목 재학습 실패"):
        R.run_retrain_all(targets=[("crypto", "BTC/USDT")],
                          state_dir=str(tmp_path))
