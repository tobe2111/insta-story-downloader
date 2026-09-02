"""배치 건강 기록의 병합 열쇠가 **한국 밤**인가 — UTC 달력일이 아니라.

■ 왜 (2026-09-02 실측)

건강 기록은 "같은 날짜면 종목 단위로 합친다"인데, 그 날짜를 UTC로 세고
있었다. 어젯밤 두 회차가 23:52 UTC → 01:05 UTC로 자정을 넘기자 두 번째
회차가 첫 회차를 **덮어썼다**:

    장부·패널          : 밤 9/2 두 회차 · 22종목 심사
    run_health.retrain : runs 1 · ok 12 · not_reached 28   ← 첫 회차만

하루 전에 붙인 '못 돈 종목' 칸이 옛 날짜 열쇠 때문에 10종목을 부풀려
말했다. 밤 배치가 쓰는 열쇠(한국 달력일)를 그대로 쓴다 — 한국 자정
(15:00 UTC)은 배치 창에서 가장 먼 자리라 회차를 안 가른다.
"""
from __future__ import annotations

import datetime as dt
import json

import quant.live.retrain as R
from quant.live.daily import _write_run_health

ROSTER = [f"m:{i}" for i in range(10)]


def _health(tmp_path) -> dict:
    return json.loads((tmp_path / "run_health.json").read_text("utf-8"))


def _at(monkeypatch, iso_utc: str) -> None:
    """밤 열쇠가 보는 '지금'을 고정한다(UTC ISO)."""
    fixed = dt.datetime.fromisoformat(iso_utc).replace(tzinfo=dt.timezone.utc)
    monkeypatch.setattr(R, "night_key", lambda now=None: R.night_key.__wrapped__(fixed)
                        if hasattr(R.night_key, "__wrapped__") else _real_night_key(fixed))


def _real_night_key(now):
    from quant.live.market_hours import KST
    return now.astimezone(KST).date().isoformat()


def test_two_runs_across_utc_midnight_merge_into_one_night(monkeypatch, tmp_path):
    """23:52 UTC 회차와 01:05 UTC 회차는 **한 밤**이다 — 합쳐진다."""
    monkeypatch.setattr(R, "night_key", lambda now=None: _real_night_key(
        dt.datetime(2026, 9, 1, 23, 52, tzinfo=dt.timezone.utc)))
    _write_run_health(str(tmp_path), "retrain", ROSTER[:6], {}, roster=ROSTER)
    monkeypatch.setattr(R, "night_key", lambda now=None: _real_night_key(
        dt.datetime(2026, 9, 2, 1, 5, tzinfo=dt.timezone.utc)))
    _write_run_health(str(tmp_path), "retrain", ROSTER[6:9], {}, roster=ROSTER)
    e = _health(tmp_path)["retrain"]
    assert e["date"] == "2026-09-02"          # 한국 날짜
    assert e["runs"] == 2 and e["ok"] == 9
    assert e["not_reached"] == 1 and e["not_reached_keys"] == [ROSTER[9]]


def test_by_utc_date_the_same_two_runs_would_not_have_merged():
    """대조군 — UTC 날짜로 세면 두 회차가 다른 날이다(고치기 전 모습)."""
    a = dt.datetime(2026, 9, 1, 23, 52, tzinfo=dt.timezone.utc)
    b = dt.datetime(2026, 9, 2, 1, 5, tzinfo=dt.timezone.utc)
    assert a.date() != b.date()                              # UTC: 갈린다
    assert _real_night_key(a) == _real_night_key(b) == "2026-09-02"   # 한국: 한 밤


def test_two_different_korean_nights_still_do_not_merge(monkeypatch, tmp_path):
    """대조군 — 진짜 다른 밤은 여전히 합치지 않는다.

    이게 없으면 위 검사는 "날짜를 아예 안 보고 늘 합친다"로도 통과한다.
    """
    monkeypatch.setattr(R, "night_key", lambda now=None: "2026-09-01")
    _write_run_health(str(tmp_path), "retrain", ROSTER[:6], {}, roster=ROSTER)
    monkeypatch.setattr(R, "night_key", lambda now=None: "2026-09-02")
    _write_run_health(str(tmp_path), "retrain", ROSTER[6:9], {}, roster=ROSTER)
    e = _health(tmp_path)["retrain"]
    assert e["date"] == "2026-09-02"
    assert e["runs"] == 1 and e["ok"] == 3
    assert e["not_reached"] == 7
