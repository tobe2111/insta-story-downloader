"""공통 로깅 유틸.

기본은 사람이 읽기 좋은 텍스트 로그. 환경변수 QUANT_LOG_JSON=1 이면 구조화
JSON 로그로 전환한다. log_event(...)로 주문·전략 컨텍스트(order_id, strategy_id
등)를 함께 남기면 실거래 디버깅 시 추적이 쉬워진다.
"""
from __future__ import annotations

import json
import logging
import os
import sys

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """로그를 JSON 한 줄로 직렬화한다(구조화 로깅)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            payload.update(ctx)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _json_enabled() -> bool:
    return os.environ.get("QUANT_LOG_JSON", "").strip().lower() in ("1", "true", "yes")


def get_logger(name: str = "quant") -> logging.Logger:
    """모듈 공통 로거를 반환한다."""
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        if _json_enabled():
            handler.setFormatter(_JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        root = logging.getLogger("quant")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("quant") else f"quant.{name}")


def log_event(logger: logging.Logger, event: str, level: str = "info", **fields) -> None:
    """구조화 이벤트를 남긴다. fields는 JSON 로그에서 개별 키로 기록된다.

    예: log_event(log, "order_filled", order_id="A1", strategy_id="ma_cross",
                  side="buy", qty=0.1, price=60000)
    텍스트 로그 모드에서는 event 문자열만 보이고 fields는 무시된다.
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.log(lvl, event, extra={"ctx": dict(fields)})
