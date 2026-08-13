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
        # ⚠️ **컨텍스트가 예약 키를 덮어쓰면 안 된다**(감사 208). 예전에는
        #    `payload.update(ctx)`라, `msg`·`time`·`level`·`logger`라는 이름의
        #    필드를 넘기면 **진짜 메시지와 시각이 통째로 바뀌었다.** 실측:
        #
        #        log_event(log, "진짜 메시지", msg="가짜 메시지", time="가짜 시각")
        #        →  {"time": "가짜 시각", "msg": "가짜 메시지", ...}
        #
        #    로그가 "언제 무슨 일이 있었는지"를 거짓으로 말하는 것이다 —
        #    감사 추적용 기록에서는 가장 나쁜 종류의 실패다. 게다가 유일한
        #    호출부(`champion_challenger.py`)는 `**result`로 **임의의 dict를
        #    통째로 펼친다** — 부르는 쪽은 무엇이 예약 키인지 알 수 없고,
        #    `"time"`은 이 저장소 장부가 어디서나 쓰는 이름이다.
        #
        #    덮어쓰지도, 버리지도 않는다. 충돌하는 키만 `ctx_` 접두어를 붙여
        #    **둘 다 남긴다** — 값을 잃는 것도 조용한 손실이기 때문이다.
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            for k, v in ctx.items():
                payload[f"ctx_{k}" if k in payload else k] = v
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
