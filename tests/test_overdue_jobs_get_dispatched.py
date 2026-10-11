"""예약 시각이 지났는데 안 돈 잡은 감시가 대신 띄운다 (2026-10-11 감사 351).

GitHub 크론이 2.5~4시간씩 늦어 주말 장부가 사라졌다(감사 350). 늦음을 한
곳(`scripts/dispatch_overdue.py`)에서 없앤다 — 이 파일이 그 계약이다.
⚠️ 스크립트는 import해도 아무것도 띄우지 않는다(main은 명령줄에서만 돈다).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "dispatch_overdue", ROOT / "scripts" / "dispatch_overdue.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)

UTC = dt.timezone.utc


def _at(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def _run(created: str, status: str = "completed") -> dict:
    return {"created_at": created + "Z", "status": status}


def test_last_tick_reads_daily_and_weekly_crons():
    assert D.last_tick("15 22 * * *", _at("2026-10-11T01:00")) == _at("2026-10-10T22:15")
    assert D.last_tick("15 22 * * *", _at("2026-10-10T22:15")) == _at("2026-10-10T22:15")
    # 토요일(크론 6) 01:10 — 2026-10-10이 토요일이다
    assert D.last_tick("10 1 * * 6", _at("2026-10-12T05:00")) == _at("2026-10-10T01:10")
    assert D.last_tick("*/5 * * * *", _at("2026-10-11T01:03")) == _at("2026-10-11T01:00")


def test_the_real_late_morning_is_caught():
    """10/11 실측 장면 — 22:15 예약이 01:00에야 떴다. 22:25에 띄워야 한다."""
    now = _at("2026-10-10T22:26")
    runs = [_run("2026-10-10T01:51:24"), _run("2026-10-10T01:45:32")]
    why = D.decide("daily-paper.yml", ["15 22 * * *", "30 22 * * *"], runs, now)
    assert why and "22:15" in why


def test_a_run_that_already_started_is_left_alone():
    now = _at("2026-10-10T22:40")
    runs = [_run("2026-10-10T22:16:03")]
    assert D.decide("daily-paper.yml", ["15 22 * * *"], runs, now) is None


def test_nothing_is_stacked_on_a_queued_run():
    now = _at("2026-10-10T23:30")
    runs = [_run("2026-10-09T22:20:00"), _run("2026-10-10T23:29:00", "queued")]
    assert D.decide("daily-paper.yml", ["15 22 * * *"], runs, now) is None


def test_grace_period_is_respected():
    """예약 직후(유예 안)에는 GitHub에게 먼저 기회를 준다."""
    now = _at("2026-10-10T22:20")
    runs = [_run("2026-10-09T22:20:00")]
    assert D.decide("daily-paper.yml", ["15 22 * * *"], runs, now) is None


def test_a_dead_guard_chain_is_revived():
    now = _at("2026-10-11T15:40")
    assert D.decide("guard.yml", [], [_run("2026-10-11T13:12:30")], now)
    assert D.decide("guard.yml", [], [_run("2026-10-11T15:30:00")], now) is None


def test_every_scheduled_job_is_covered_or_excluded_with_a_reason():
    """손 명단을 막는다 — 새 크론 잡은 자동으로 대상이 되고, 빼려면 이유를 적어야 한다."""
    sched = D.scheduled_workflows()
    assert "daily-paper.yml" in sched and "nightly-retrain.yml" in sched
    for wf in D.SKIP:
        assert (ROOT / ".github" / "workflows" / wf).exists(), f"없는 파일을 뺐다: {wf}"
        assert len(D.SKIP[wf]) > 10
    for wf in sched:
        if wf in D.SKIP:
            continue
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / wf).read_text("utf-8"))
        on = doc.get("on") or doc.get(True)
        assert "workflow_dispatch" in on, f"{wf}는 대신 띄울 수 없다(workflow_dispatch 없음)"


def test_the_dispatcher_is_wired_both_ways():
    """감시가 밀린 잡을 깨우고, 일일 기록이 감시를 깨운다."""
    for wf, arg in (("guard.yml", "scripts/dispatch_overdue.py"),
                    ("daily-paper.yml", "scripts/dispatch_overdue.py --guard-only")):
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / wf).read_text("utf-8"))
        perms = doc.get("permissions") or {}
        assert perms.get("actions") == "write", f"{wf}: actions: write 없으면 못 띄운다"
        steps = [s for j in doc["jobs"].values() for s in j.get("steps", [])]
        hit = [s for s in steps if arg in str(s.get("run", ""))]
        assert hit, f"{wf}가 밀린 잡 확인을 부르지 않는다"
        assert "always()" in str(hit[0].get("if", "")), "앞 단계가 실패해도 돌아야 한다"
