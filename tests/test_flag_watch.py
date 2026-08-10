"""플래그 파수꾼 — 새로 켜진 플래그만 알림, 반복 발송 없음.

핵심 계약:
  ① 낙관 의심(fill_check)·보정 어긋남(calibration)·판정 시계(generation)
     플래그를 status 재료에서 수집한다
  ② '새로 켜진' 플래그만 알림 발송 — 같은 플래그는 다음 날 조용하다
  ③ 꺼졌다가 다시 켜지면 다시 알린다 (상태 파일 diff)
  ④ write_docs_status 끝에 배선된다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import flag_watch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

STATUS = {
    "fill_check": {"markets": {"kr_stock": {
        "n": 31, "mean_abs_gap_bp": 90.0, "mean_adverse_bp": 79.0,
        "worst_adverse_bp": 210.0, "assumed_bp": 14.0, "optimistic": True}}},
    "generation": {"feature_set": "fs8:+fredmacro", "since": "2026-08-09",
                   "days": 1, "target_days": 90},
    "paper": {},
}


class _Spy:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


def _run(tmp_path, monkeypatch, status):
    spy = _Spy()
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: spy)
    new = flag_watch.check_and_notify_flags(status, str(tmp_path))
    return new, spy


def test_new_flags_notified_once(tmp_path, monkeypatch):
    new, spy = _run(tmp_path, monkeypatch, STATUS)
    assert sorted(new) == ["generation:fs8:+fredmacro", "optimistic:kr_stock"]
    assert len(spy.sent) == 2
    assert any("백테스트가 낙관적" in m for m in spy.sent)
    assert any("판정 시계 리셋" in m for m in spy.sent)
    # 다음 날 같은 플래그 — 조용해야 한다
    new2, spy2 = _run(tmp_path, monkeypatch, STATUS)
    assert new2 == [] and spy2.sent == []


def test_flag_off_then_on_notifies_again(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, STATUS)
    off = json.loads(json.dumps(STATUS))
    off["fill_check"]["markets"]["kr_stock"]["optimistic"] = False
    new_off, _ = _run(tmp_path, monkeypatch, off)
    assert new_off == []                      # 꺼질 때는 조용
    new_on, spy = _run(tmp_path, monkeypatch, STATUS)
    assert new_on == ["optimistic:kr_stock"]  # 재점등 → 재알림
    assert len(spy.sent) == 1


def test_generation_done_flag(tmp_path, monkeypatch):
    st = json.loads(json.dumps(STATUS))
    st["generation"]["days"] = 90
    new, spy = _run(tmp_path, monkeypatch, st)
    assert "generation_done:fs8:+fredmacro" in new
    assert any("판정 시계 만료" in m for m in spy.sent)


def test_wired_into_write_docs_status():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "check_and_notify_flags" in dl
