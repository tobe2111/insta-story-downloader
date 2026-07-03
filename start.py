#!/usr/bin/env python3
"""더블클릭 실행기 — 가장 간편한 시작.

이 파일을 실행하면:
    1) 필요한 라이브러리를 (처음 한 번) 자동 설치하고
    2) 로컬 웹 조종석을 켠 뒤
    3) 브라우저를 자동으로 엽니다.

터미널에 익숙하지 않아도 됩니다. 윈도우는 start.bat, 맥/리눅스는 start.sh 를
더블클릭하거나, 어디서든  python start.py  로 실행하세요.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
_FROZEN = getattr(sys, "frozen", False)
# 무설치 실행파일(frozen)이면 exe 위치, 아니면 스크립트 위치를 기준 폴더로
_ROOT = os.path.dirname(sys.executable) if _FROZEN \
    else os.path.dirname(os.path.abspath(__file__))


def _ensure_deps() -> None:
    """핵심 라이브러리가 없으면 requirements.txt로 자동 설치한다."""
    if _FROZEN:
        return  # 무설치 실행파일은 라이브러리가 이미 포함되어 있음
    try:
        import numpy  # noqa: F401
        import pandas  # noqa: F401
        import yaml  # noqa: F401
        return
    except ImportError:
        print("📦 필요한 라이브러리를 설치합니다 (처음 한 번, 1~2분 걸릴 수 있어요)...")
        req = os.path.join(_ROOT, "requirements.txt")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req])
        print("✅ 설치 완료.\n")


def _open_browser(url: str, delay: float = 2.0) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    os.chdir(_ROOT)
    sys.path.insert(0, _ROOT)
    _ensure_deps()

    from quant.web.server import run_server

    url = f"http://{HOST}:{PORT}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    print(f"🌐 브라우저에서 {url} 이 열립니다. (자동으로 안 열리면 직접 접속하세요)")
    print("   종료하려면 이 창에서 Ctrl+C 를 누르세요.\n")
    run_server(HOST, PORT)


if __name__ == "__main__":
    main()
