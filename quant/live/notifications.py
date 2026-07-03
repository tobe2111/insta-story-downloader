"""실시간 알림 (텔레그램 / 슬랙 / 콘솔).

체결·오류·레짐 변화 등 중요한 이벤트를 즉시 통지한다. 자동매매에서 알림은
사치가 아니라 안전장치다 — 뭔가 잘못됐을 때 가장 먼저 알아채야 한다.

환경변수:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (텔레그램 봇)
    SLACK_WEBHOOK_URL                       (슬랙 Incoming Webhook)
설정된 채널만 자동으로 활성화되며, 콘솔 알림은 항상 켜져 있다.
모든 전송 오류는 삼켜서(swallow) 알림 실패가 매매를 멈추지 않게 한다.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from quant.utils.http import post_json, post_text
from quant.utils.logging import get_logger

log = get_logger("live.notify")


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str, level: str = "info") -> None:
        ...


class ConsoleNotifier(Notifier):
    """로그로 출력 (항상 사용 가능)."""

    def send(self, message: str, level: str = "info") -> None:
        getattr(log, level if level in ("info", "warning", "error") else "info")(
            "🔔 %s", message
        )


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send(self, message: str, level: str = "info") -> None:
        try:
            post_json(self.url, {"content-type": "application/json"},
                      {"chat_id": self.chat_id, "text": message})
        except Exception as exc:  # noqa: BLE001
            log.warning("텔레그램 알림 실패: %s", exc)


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str, level: str = "info") -> None:
        try:
            post_text(self.webhook_url, {"content-type": "application/json"},
                      {"text": message})
        except Exception as exc:  # noqa: BLE001
            log.warning("슬랙 알림 실패: %s", exc)


class MultiNotifier(Notifier):
    """여러 채널로 동시에 전송. 개별 채널 실패는 서로 격리된다."""

    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def send(self, message: str, level: str = "info") -> None:
        for n in self.notifiers:
            try:
                n.send(message, level)
            except Exception as exc:  # noqa: BLE001
                log.warning("알림 채널 오류(%s): %s", type(n).__name__, exc)


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

    return MultiNotifier(channels)
