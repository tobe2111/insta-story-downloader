"""실거래/페이퍼 운영 모듈 — 지연 임포트(PEP 562).

하위 모듈 상당수가 pandas를 요구하지만, retrain의 상태 파일 처리처럼 pandas
없이 쓸 수 있는 부분도 있다. 패키지 임포트만으로 pandas를 강제하지 않도록
실제 접근 시점에 하위 모듈을 불러온다(기존 `from quant.live import X`는 동일 동작).
"""
from __future__ import annotations

_EXPORTS = {
    "AutoLearner": "quant.live.autolearn",
    "ChampionChallenger": "quant.live.champion_challenger",
    "BreakerConfig": "quant.live.circuit_breaker",
    "CircuitBreaker": "quant.live.circuit_breaker",
    "LiveTrader": "quant.live.engine",
    "DailyLossKillSwitch": "quant.live.killswitch",
    "MultiTrader": "quant.live.multi",
    "Notifier": "quant.live.notifications",
    "ConsoleNotifier": "quant.live.notifications",
    "DiscordNotifier": "quant.live.notifications",
    "TelegramNotifier": "quant.live.notifications",
    "SlackNotifier": "quant.live.notifications",
    "MultiNotifier": "quant.live.notifications",
    "get_notifier": "quant.live.notifications",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name in _EXPORTS:
        import importlib
        return getattr(importlib.import_module(_EXPORTS[name]), name)
    raise AttributeError(f"module 'quant.live' has no attribute {name!r}")
