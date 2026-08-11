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


def test_killswitch_flag_and_escalation(tmp_path, monkeypatch):
    st = json.loads(json.dumps(STATUS))
    st["paper"] = {"portfolio:ALL": {"history": [
        {"date": "2026-08-09", "risk_scale": 0.75, "drawdown_pct": -8.2}]}}
    new, spy = _run(tmp_path, monkeypatch, st)
    assert "killswitch:portfolio:ALL:0.75" in new
    assert any("킬스위치 발동" in m and "75%" in m for m in spy.sent)
    # 단계 하강(0.75→0.5) → 키가 바뀌어 재알림
    st["paper"]["portfolio:ALL"]["history"][0]["risk_scale"] = 0.5
    new2, spy2 = _run(tmp_path, monkeypatch, st)
    assert "killswitch:portfolio:ALL:0.5" in new2
    # 복귀(1.0) → 조용히 꺼짐
    st["paper"]["portfolio:ALL"]["history"][0]["risk_scale"] = 1.0
    new3, spy3 = _run(tmp_path, monkeypatch, st)
    assert not any(k.startswith("killswitch") for k in new3)
    assert spy3.sent == []


def test_turnover_cost_alert(tmp_path, monkeypatch):
    """회전율이 높아 비용이 기대수익을 넘으면 경보한다."""
    hi = [{"date": f"2026-08-{d:02d}", "turnover": {"ratio": 0.37},
           "vol_target": {"target": 0.12}} for d in range(1, 21)]
    st = {"paper": {"portfolio:ALL": {"history": hi}}}
    new, spy = _run(tmp_path, monkeypatch, st)
    assert "turnover_cost" in new
    assert any("회전율 경보" in m for m in spy.sent)
    # 회전율이 낮으면 조용하다
    lo = [dict(r, turnover={"ratio": 0.03}) for r in hi]
    new2, _ = _run(tmp_path, monkeypatch,
                   {"paper": {"portfolio:ALL": {"history": lo}}})
    assert "turnover_cost" not in new2


def test_turnover_alert_needs_sample(tmp_path, monkeypatch):
    """표본이 얇으면 판정하지 않는다 — 소표본 경보는 소음이다."""
    hi = [{"date": f"2026-08-{d:02d}", "turnover": {"ratio": 0.9}}
          for d in range(1, 6)]
    new, _ = _run(tmp_path, monkeypatch,
                  {"paper": {"portfolio:ALL": {"history": hi}}})
    assert "turnover_cost" not in new


def test_overfit_and_dsr_alerts(tmp_path, monkeypatch):
    """야간 검증(PBO·DSR)이 콘솔에만 찍히고 사라지던 것을 경보로 잇는다."""
    st = {"validation": {
        "crypto:BTC/USDT": {"strategy": "ml", "pbo": 0.72, "dsr": 0.99},
        "us_stock:SPY": {"strategy": "ml", "pbo": 0.20, "dsr": 0.40}}}
    new, spy = _run(tmp_path, monkeypatch, st)
    assert "overfit:crypto:BTC/USDT" in new       # PBO 0.72 > 0.5
    assert "dsr_low:us_stock:SPY" in new          # DSR 0.40 < 0.95
    assert "overfit:us_stock:SPY" not in new      # PBO 0.20은 조용
    assert "dsr_low:crypto:BTC/USDT" not in new   # DSR 0.99는 조용
    assert any("과최적화 의심" in m for m in spy.sent)


def test_validation_wired_into_status():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "validation.json" in dl and '"validation"' in dl


def test_weekly_health_section(tmp_path):
    """주간 요약이 판정 시계·오디션·킬스위치를 담는다(건강 보고서)."""
    from quant.live.daily import format_weekly, weekly_summary
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "pf.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "start_cash": 80000,
        "history": [
            {"date": "2026-08-08", "equity": 80000.0, "return_pct": 0.0},
            {"date": "2026-08-09", "equity": 79000.0, "return_pct": -1.2,
             "risk_scale": 0.75, "drawdown_pct": -6.0},
        ]}), "utf-8")
    (tmp_path / "retrain_history.jsonl").write_text(json.dumps(
        {"asof": "2026-08-09", "market": "crypto", "symbol": "BTC/USDT",
         "promoted": False, "n_candidates": 12}) + "\n", "utf-8")
    s = weekly_summary(str(tmp_path))
    h = s["health"]
    assert h["auditions"] == {"runs": 1, "candidates": 12, "promoted": 0}
    assert h["killswitch"]["risk_scale"] == 0.75
    assert h["generation"]["target_days"] == 90
    text = format_weekly(s)
    assert "판정 시계" in text and "오디션" in text and "킬스위치 발동 중" in text


def test_wired_into_write_docs_status():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "check_and_notify_flags" in dl
    assert "killswitch" in (ROOT / "quant" / "live" / "flag_watch.py").read_text("utf-8")
