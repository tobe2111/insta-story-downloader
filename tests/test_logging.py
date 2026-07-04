"""구조화(JSON) 로깅 테스트 — 순수 stdlib (pandas 불필요)."""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.logging import _JsonFormatter, log_event


def test_json_formatter_includes_context():
    rec = logging.LogRecord("quant.x", logging.INFO, "f.py", 1,
                            "order filled", None, None)
    rec.ctx = {"order_id": "A1", "strategy_id": "ma_cross", "qty": 0.1}
    out = _JsonFormatter().format(rec)
    d = json.loads(out)
    assert d["msg"] == "order filled" and d["level"] == "INFO"
    assert d["order_id"] == "A1" and d["strategy_id"] == "ma_cross" and d["qty"] == 0.1


def test_json_formatter_without_context():
    rec = logging.LogRecord("quant.y", logging.WARNING, "f.py", 1,
                            "hi", None, None)
    d = json.loads(_JsonFormatter().format(rec))
    assert d["msg"] == "hi" and d["level"] == "WARNING"


def test_log_event_attaches_fields():
    """log_event로 남긴 필드가 JSON 로그의 개별 키로 나타난다."""
    logger = logging.getLogger("quant.test_event")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(_JsonFormatter())
    logger.addHandler(h)

    log_event(logger, "order_filled", order_id="X9", side="buy", price=100.0)
    h.flush()
    d = json.loads(buf.getvalue().strip())
    assert d["msg"] == "order_filled"
    assert d["order_id"] == "X9" and d["side"] == "buy" and d["price"] == 100.0
