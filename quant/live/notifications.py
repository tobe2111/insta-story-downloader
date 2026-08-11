"""실시간 알림 (텔레그램 / 슬랙 / 콘솔).

체결·오류·레짐 변화 등 중요한 이벤트를 즉시 통지한다. 자동매매에서 알림은
사치가 아니라 안전장치다 — 뭔가 잘못됐을 때 가장 먼저 알아채야 한다.

환경변수:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (텔레그램 봇)
    SLACK_WEBHOOK_URL                       (슬랙 Incoming Webhook)
    DISCORD_WEBHOOK_URL                     (디스코드 채널 웹훅)
설정된 채널만 자동으로 활성화되며, 콘솔 알림은 항상 켜져 있다.
모든 전송 오류는 삼켜서(swallow) 알림 실패가 매매를 멈추지 않게 한다.
다만 **삼키되 숨기지는 않는다** — send()는 성공 여부를 bool로 돌려준다.
호출자가 '보냈다'를 장부에 남기는 경우(flag_watch), 실패를 성공으로 적으면
그 경보는 영원히 다시 오지 않는다(2026-08-11 감사에서 발견).
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

from quant.utils.http import post_json, post_text
from quant.utils.logging import get_logger

log = get_logger("live.notify")

# 텔레그램 봇 토큰은 URL 경로(.../bot<TOKEN>/...)에, 슬랙 웹훅은 URL 경로 자체가
# 시크릿이다. HTTP 오류 메시지에 이 URL이 통째로 들어가므로, 로그로 새어나가지
# 않도록 경로/쿼리를 가린다(호스트와 상태코드는 남겨 디버깅은 가능하게).
_URL_RE = re.compile(r"(https?://[^/\s]+)(/\S*)?")


def _redact(exc: object) -> str:
    return _URL_RE.sub(lambda m: f"{m.group(1)}/…(redacted)", str(exc))


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str, level: str = "info") -> bool:
        """전송을 시도하고 성공 여부를 돌려준다(예외는 던지지 않는다)."""
        ...


class ConsoleNotifier(Notifier):
    """로그로 출력 (항상 사용 가능)."""

    def send(self, message: str, level: str = "info") -> bool:
        getattr(log, level if level in ("info", "warning", "error") else "info")(
            "🔔 %s", message
        )
        return True


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send(self, message: str, level: str = "info") -> bool:
        try:
            post_json(self.url, {"content-type": "application/json"},
                      {"chat_id": self.chat_id, "text": message})
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("텔레그램 알림 실패: %s", _redact(exc))
            return False


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str, level: str = "info") -> bool:
        try:
            post_text(self.webhook_url, {"content-type": "application/json"},
                      {"text": message})
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("슬랙 알림 실패: %s", _redact(exc))
            return False


class DiscordNotifier(Notifier):
    """디스코드 웹훅 알림 — 서버 채널 설정에서 웹훅 URL 하나만 만들면 된다."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str, level: str = "info") -> bool:
        try:
            # 디스코드는 {"content": ...} 형식, 2000자 제한
            post_text(self.webhook_url, {"content-type": "application/json"},
                      {"content": message[:1900]})
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("디스코드 알림 실패: %s", _redact(exc))
            return False


class MultiNotifier(Notifier):
    """여러 채널로 동시에 전송. 개별 채널 실패는 서로 격리된다."""

    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def send(self, message: str, level: str = "info") -> bool:
        """모든 채널이 성공해야 True — 하나라도 실패하면 '보냈다'가 아니다."""
        ok = True
        for n in self.notifiers:
            try:
                if n.send(message, level) is False:
                    ok = False
            except Exception as exc:  # noqa: BLE001
                log.warning("알림 채널 오류(%s): %s", type(n).__name__, exc)
                ok = False
        return ok


def get_notifier() -> Notifier:
    """환경변수에 설정된 채널들로 알림기를 구성한다 (콘솔은 항상 포함)."""
    channels: list[Notifier] = [ConsoleNotifier()]

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        channels.append(TelegramNotifier(tg_token, tg_chat))
        log.info("텔레그램 알림 활성화")

    slack = os.getenv("SLACK_WEBHOOK_URL")
    if slack:
        channels.append(SlackNotifier(slack))
        log.info("슬랙 알림 활성화")

    discord = os.getenv("DISCORD_WEBHOOK_URL")
    if discord:
        channels.append(DiscordNotifier(discord))
        log.info("디스코드 알림 활성화")

    return MultiNotifier(channels)
