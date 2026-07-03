"""로컬 웹서버 실행 예제.

    python examples/run_web.py                 # http://127.0.0.1:8000
    python examples/run_web.py --port 9000

브라우저에서 시장·종목·전략을 고르고 백테스트를 실행해 리포트를 봅니다.
외부 웹 프레임워크가 필요 없습니다 (표준 라이브러리 http.server).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.web.server import run_server


def main() -> None:
    p = argparse.ArgumentParser(description="Quant 로컬 웹서버")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
