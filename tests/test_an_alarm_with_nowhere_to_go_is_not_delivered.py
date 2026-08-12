"""보낼 곳이 없는데 '보냈다'로 기록됐다 (감사 175).

`flag_watch`는 새 경보(킬스위치 발동·과최적화 의심 등)를 알림으로 내보내고,
성공한 것만 장부에 '보냈다'로 적는다. 적힌 플래그는 다음 실행부터
**'이미 켜져 있던 것'**으로 분류돼 다시 오지 않는다. 그래서 전송 성공 여부가
곧 "이 경보가 사장님께 닿았는가"다.

    if notifier.send(cur[k]) is False:
        failed.add(k)                      # 실패분만 다시 시도
    atomic_write_json(path, {"flags": sorted(set(cur) - failed)})

이 파일(`notifications.py`) 머리말은 그 위험을 이미 알고 있었다 —
"실패를 성공으로 적으면 그 경보는 영원히 다시 오지 않는다".

그런데 문이 하나 더 있었다. **보낼 곳이 아예 없는 경우다.**

`get_notifier()`는 콘솔을 항상 포함한다. 텔레그램·슬랙·디스코드를 하나도
설정하지 않으면 `MultiNotifier([ConsoleNotifier()])`가 되고, 콘솔은 언제나
성공하므로 `send()`가 **True**를 돌려줬다.

결과: 킬스위치가 발동한 날, 그 사실이 **깃허브 액션 로그 안에 한 줄 남고
장부에는 '전달됨'으로 적혀 영구히 사라진다.** 사장님은 끝내 모른다.

고침: 채널에 '바깥으로 나가는가'(`external`)를 표시하고, 나가는 채널이 하나도
없으면 `send()`가 False를 돌려준다 — 경고와 함께. 그러면 채널을 설정하는
순간 밀린 경보가 다시 뜬다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.notifications as nt  # noqa: E402


class _External(nt.Notifier):
    """텔레그램·슬랙·디스코드를 대신하는 가짜 — 바깥으로 나간다."""

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.sent: list[str] = []

    def send(self, message: str, level: str = "info") -> bool:
        self.sent.append(message)
        return self.ok


# ── 보낼 곳이 없으면 '보냈다'가 아니다 ────────────────────────


def test_console_only_is_not_a_delivery():
    """이것이 감사 175 — 콘솔은 아무에게도 닿지 않는다."""
    assert nt.MultiNotifier([nt.ConsoleNotifier()]).send("킬스위치 발동") is False, (
        "바깥 채널이 하나도 없는데 '전달됨'으로 기록된다 — "
        "그 경보는 영원히 다시 오지 않는다")


def test_the_console_is_marked_as_not_reaching_outside():
    assert nt.ConsoleNotifier.external is False
    assert nt.Notifier.external is True, "기본값은 '바깥으로 나간다'여야 한다"


def test_the_missing_channel_is_announced(caplog):
    """조용히 False를 돌려주면 왜 경보가 안 오는지 알 수 없다."""
    import logging

    with caplog.at_level(logging.WARNING):
        nt.MultiNotifier([nt.ConsoleNotifier()]).send("x")
    assert any("알림 채널이 없습니다" in r.message for r in caplog.records), caplog.text


def test_the_message_still_reaches_the_console():
    """대조군 — 전달로 안 친다고 로그까지 끊으면 안 된다."""
    console = nt.ConsoleNotifier()
    assert console.send("보이긴 해야 한다") is True


# ── 대조군: 원래 계약이 그대로인가 ────────────────────────────


def test_an_external_channel_makes_it_a_real_delivery():
    ext = _External()
    assert nt.MultiNotifier([nt.ConsoleNotifier(), ext]).send("경보") is True
    assert ext.sent == ["경보"], ext.sent


def test_a_failing_external_channel_is_not_a_delivery():
    """전송 실패를 성공으로 적으면 안 된다(원래 있던 계약)."""
    assert nt.MultiNotifier([nt.ConsoleNotifier(),
                             _External(ok=False)]).send("경보") is False


def test_one_failing_channel_spoils_the_delivery():
    assert nt.MultiNotifier([_External(), _External(ok=False)]).send("x") is False


def test_a_raising_channel_does_not_break_the_others():
    class _Boom(nt.Notifier):
        def send(self, message, level="info"):
            raise RuntimeError("웹훅 죽음")

    good = _External()
    assert nt.MultiNotifier([_Boom(), good]).send("x") is False
    assert good.sent == ["x"], "한 채널이 터져도 나머지는 보내야 한다"


def test_two_healthy_external_channels_are_a_delivery():
    assert nt.MultiNotifier([_External(), _External()]).send("x") is True


# ── 배선: 실제 구성이 어떻게 되는가 ───────────────────────────


def test_with_no_secrets_the_notifier_cannot_deliver(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "SLACK_WEBHOOK_URL", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    assert nt.get_notifier().send("킬스위치 발동") is False


def test_with_a_webhook_configured_it_can_deliver(monkeypatch):
    """대조군 — 설정하면 실제로 전달로 잡혀야 한다."""
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    sent: list = []
    monkeypatch.setattr(nt, "post_text",
                        lambda url, headers, body: sent.append(body) or {})
    assert nt.get_notifier().send("경보") is True
    assert sent and "경보" in str(sent[0])


def test_a_failed_alert_is_retried_next_time(tmp_path, monkeypatch):
    """배선 — 전달 실패면 장부에 안 적히고 다음 실행에 다시 떠야 한다."""
    from quant.live.flag_watch import check_and_notify_flags

    # ⚠️ 실제로 플래그가 켜지는 모양이어야 한다. 처음엔 아무 dict나 넣었다가
    #    플래그가 하나도 안 켜져서 첫 단언이 **헛돌았다**(빈 목록 == 빈 목록).
    status = {"fill_check": {"markets": {"crypto": {
        "optimistic": True, "mean_adverse_bp": 20.0,
        "assumed_bp": 15.0, "n": 50}}}}
    assert check_and_notify_flags  # (import 확인용)

    monkeypatch.setattr("quant.live.notifications.get_notifier",
                        lambda: nt.MultiNotifier([nt.ConsoleNotifier()]))
    first = check_and_notify_flags(status, state_dir=str(tmp_path))
    assert first == [], "전달 못 했는데 '보냈다'로 돌려준다"

    ext = _External()
    monkeypatch.setattr("quant.live.notifications.get_notifier",
                        lambda: nt.MultiNotifier([nt.ConsoleNotifier(), ext]))
    second = check_and_notify_flags(status, state_dir=str(tmp_path))
    assert second, "채널을 설정했는데 밀린 경보가 안 온다"
    assert ext.sent, ext.sent


# ── 비밀이 로그로 새지 않는가 ─────────────────────────────────


@pytest.mark.parametrize("url", [
    "https://api.telegram.org/bot123456:SECRET-TOKEN/sendMessage",
    "https://hooks.slack.com/services/T000/B000/SECRETPART",
    "https://discord.com/api/webhooks/123/SECRETPART",
])
def test_a_webhook_secret_is_redacted_from_errors(url):
    """텔레그램 토큰과 웹훅 URL은 **경로 자체가 비밀**이다."""
    masked = nt._redact(RuntimeError(f"HTTP 401 {url}: nope"))
    assert "SECRET" not in masked, masked
    assert "redacted" in masked
