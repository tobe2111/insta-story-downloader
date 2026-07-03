"""알림 계층 테스트 (순수 stdlib — 네트워크/pandas 불필요)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "notif", str(_ROOT / "quant" / "live" / "notifications.py")
)
notif = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notif)


class _Recorder(notif.Notifier):
    def __init__(self):
        self.messages = []

    def send(self, message, level="info"):
        self.messages.append((message, level))


class _Broken(notif.Notifier):
    def send(self, message, level="info"):
        raise RuntimeError("채널 다운")


def test_multi_notifier_fans_out():
    a, b = _Recorder(), _Recorder()
    m = notif.MultiNotifier([a, b])
    m.send("체결됨", "info")
    assert a.messages == [("체결됨", "info")]
    assert b.messages == [("체결됨", "info")]


def test_multi_notifier_isolates_failures():
    """한 채널이 죽어도 다른 채널로는 전송된다."""
    good = _Recorder()
    m = notif.MultiNotifier([_Broken(), good])
    m.send("중요 알림")  # 예외가 밖으로 새면 안 됨
    assert good.messages == [("중요 알림", "info")]


def test_console_notifier_runs():
    notif.ConsoleNotifier().send("테스트 메시지", "warning")  # 예외 없이 동작


def test_get_notifier_defaults_to_console(monkeypatch=None):
    # 환경변수 없이 호출 시 콘솔만 포함하는 MultiNotifier 반환
    import os

    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SLACK_WEBHOOK_URL"):
        os.environ.pop(k, None)
    n = notif.get_notifier()
    assert isinstance(n, notif.MultiNotifier)
    assert len(n.notifiers) == 1
    assert isinstance(n.notifiers[0], notif.ConsoleNotifier)
