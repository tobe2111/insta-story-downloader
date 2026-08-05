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


def test_redact_hides_secret_url_path():
    """오류 로그에서 텔레그램 토큰/슬랙 웹훅 경로가 가려지는지 검증(시크릿 유출 방지)."""
    tg = "HTTP 400 https://api.telegram.org/bot123456:ABCSECRET/sendMessage: bad"
    out = notif._redact(tg)
    assert "ABCSECRET" not in out
    assert "api.telegram.org" in out and "HTTP 400" in out   # 호스트·상태는 유지
    slack = "네트워크 오류 https://hooks.slack.com/services/T00/B00/XXXSECRET: refused"
    out2 = notif._redact(slack)
    assert "XXXSECRET" not in out2
    assert "hooks.slack.com" in out2


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

    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SLACK_WEBHOOK_URL",
              "DISCORD_WEBHOOK_URL"):
        os.environ.pop(k, None)
    n = notif.get_notifier()
    assert isinstance(n, notif.MultiNotifier)
    assert len(n.notifiers) == 1
    assert isinstance(n.notifiers[0], notif.ConsoleNotifier)


def test_discord_notifier_posts_content(monkeypatch):
    """디스코드 웹훅 형식({"content": ...})과 2000자 제한 준수 검증."""
    calls = []

    def fake_post(url, headers=None, body=None):
        calls.append((url, headers, body))
        return ""

    monkeypatch.setattr(notif, "post_text", fake_post)
    d = notif.DiscordNotifier("https://discord.com/api/webhooks/1/SECRET")
    d.send("가" * 3000)
    assert len(calls) == 1
    url, headers, body = calls[0]
    assert url.endswith("/1/SECRET")
    assert "content" in body and len(body["content"]) <= 1900


def test_discord_notifier_swallows_errors(monkeypatch):
    """웹훅 실패가 매매를 멈추지 않아야 한다(예외 삼킴)."""
    def boom(*a, **k):
        raise RuntimeError("HTTP 404 https://discord.com/api/webhooks/1/SECRET: no")

    monkeypatch.setattr(notif, "post_text", boom)
    notif.DiscordNotifier("https://discord.com/api/webhooks/1/SECRET").send("x")


def test_get_notifier_enables_discord(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")
    n = notif.get_notifier()
    assert any(isinstance(c, notif.DiscordNotifier) for c in n.notifiers)
