"""경보 전달 계약 검사 — 실패한 경보가 조용히 사라지지 않는다.

배경(2026-08-11 감사): flag_watch는 '새로 켜진 플래그'만 알리고 현재 집합을
state/flag_state.json에 적는다. 그런데 전송 성공 여부와 무관하게 적었다.
웹훅이 죽은 날 켜진 경보는 다음 실행에서 '이미 알린 것'으로 분류돼 **영원히
다시 오지 않는다** — 하필 그날이 킬스위치 발동일이면 끝내 모르게 된다.

핵심 계약:
  ① 전송 실패한 플래그는 저장되지 않아 다음 실행에 재시도된다
  ② 성공한 플래그는 저장되어 매일 반복되지 않는다
  ③ 알림기는 성공 여부를 bool로 보고한다(예외는 던지지 않는다)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import flag_watch  # noqa: E402

_STATUS = {"paper": {"portfolio:ALL": {"history": [
    {"date": "2026-08-11", "risk_scale": 0.75, "drawdown_pct": -8.2}]}}}


class _Notifier:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def send(self, message, level="info"):
        self.sent.append(message)
        return self.ok


def _saved(tmp_path):
    p = Path(tmp_path) / "flag_state.json"
    return set(json.loads(p.read_text(encoding="utf-8"))["flags"]) if p.exists() \
        else set()


def test_failed_alert_is_retried_next_run(tmp_path, monkeypatch):
    fail = _Notifier(ok=False)
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: fail)
    new = flag_watch.check_and_notify_flags(_STATUS, str(tmp_path))
    assert new == []                       # 보냈다고 보고하지 않는다
    assert len(fail.sent) == 1             # 시도는 했다
    assert not _saved(tmp_path)            # 장부에 '보냄'으로 남기지 않는다

    ok = _Notifier(ok=True)
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: ok)
    new = flag_watch.check_and_notify_flags(_STATUS, str(tmp_path))
    assert any(k.startswith("killswitch:") for k in new)   # 다음 실행에 재시도
    assert len(ok.sent) == 1
    assert _saved(tmp_path)


def test_successful_alert_is_not_repeated(tmp_path, monkeypatch):
    ok = _Notifier(ok=True)
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: ok)
    flag_watch.check_and_notify_flags(_STATUS, str(tmp_path))
    flag_watch.check_and_notify_flags(_STATUS, str(tmp_path))
    assert len(ok.sent) == 1               # 같은 경보는 한 번만


def test_legacy_notifier_returning_none_counts_as_sent(tmp_path, monkeypatch):
    """반환값 없는 구식 구현도 깨지지 않아야 한다(None은 성공 취급)."""
    class _Old:
        def __init__(self): self.sent = []
        def send(self, m, level="info"): self.sent.append(m)

    old = _Old()
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: old)
    new = flag_watch.check_and_notify_flags(_STATUS, str(tmp_path))
    assert new and _saved(tmp_path)


def test_notifiers_report_success_as_bool(monkeypatch):
    from quant.live import notifications as nt

    assert nt.ConsoleNotifier().send("x") is True

    monkeypatch.setattr(nt, "post_text", lambda *a, **k: None)
    assert nt.DiscordNotifier("https://x/y").send("x") is True
    monkeypatch.setattr(nt, "post_text", lambda *a, **k: (_ for _ in ()).throw(
        OSError("boom")))
    assert nt.DiscordNotifier("https://x/y").send("x") is False


def test_multi_notifier_is_false_when_any_channel_fails(monkeypatch):
    from quant.live import notifications as nt

    good, bad = _Notifier(True), _Notifier(False)
    assert nt.MultiNotifier([good, good]).send("x") is True
    assert nt.MultiNotifier([good, bad]).send("x") is False

    class _Boom:
        def send(self, m, level="info"): raise RuntimeError("x")

    assert nt.MultiNotifier([good, _Boom()]).send("x") is False
