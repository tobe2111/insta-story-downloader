"""공통 로깅 유틸."""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str = "quant") -> logging.Logger:
    """모듈 공통 로거를 반환한다."""
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
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
