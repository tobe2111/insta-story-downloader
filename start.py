#!/usr/bin/env python3
"""더블클릭 실행기 — 가장 간편한 시작.

이 파일을 실행하면:
    1) 필요한 라이브러리를 (처음 한 번) 자동 설치하고
    2) 로컬 웹 조종석을 켠 뒤
    3) 브라우저를 자동으로 엽니다.

터미널에 익숙하지 않아도 됩니다. 윈도우는 start.bat, 맥/리눅스는 start.sh 를
더블클릭하거나, 어디서든  python start.py  로 실행하세요.

문제가 나면 프로그램 폴더의 start_error.log 에 원인이 저장됩니다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
PORT_TRIES = 20          # 8000이 사용 중이면 8001~8020까지 자동 시도
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


def pick_port(host: str = HOST, start: int = PORT, tries: int = PORT_TRIES) -> int:
    """start부터 시도해 비어 있는 첫 포트를 반환한다.

    다른 프로그램이 8000을 쓰고 있으면(개발 서버 등 흔함) 예전에는 그대로
    죽으면서 창이 바로 닫혀 원인조차 볼 수 없었다 — 자동으로 다음 포트를 쓴다.
    """
    for port in range(start, start + tries + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise OSError(
        f"{start}~{start + tries} 포트가 모두 사용 중입니다. "
        "다른 프로그램을 종료한 뒤 다시 실행해 주세요.")


def _open_browser(url: str, delay: float = 2.0) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


def _pause_before_exit() -> None:
    """더블클릭 실행에서 오류 시 콘솔이 바로 닫히지 않게 잡아둔다."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n엔터를 누르면 창이 닫힙니다...")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    print("⏳ 퀀트 조종석을 준비하는 중입니다...")
    os.chdir(_ROOT)
    sys.path.insert(0, _ROOT)
    _ensure_deps()

    # 정품 확인(배포본에서 QUANT_REQUIRE_LICENSE=1 일 때만 강제. 개발/CI는 통과).
    from quant.licensing import require_license
    if not require_license(root=_ROOT):
        _pause_before_exit()
        return

    from quant.web.server import run_server

    port = pick_port()
    if port != PORT:
        print(f"ℹ️  {PORT} 포트가 사용 중이라 {port} 포트로 엽니다.")
    url = f"http://{HOST}:{port}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    print(f"🌐 브라우저에서 {url} 이 열립니다. (자동으로 안 열리면 직접 접속하세요)")
    print("   이 창은 서버 창입니다 — 사용하는 동안 닫지 마세요. 종료는 Ctrl+C.\n")
    run_server(HOST, port)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    except Exception:  # noqa: BLE001
        # 원인을 화면 + 파일로 남긴다 — 더블클릭 실행에서는 창이 즉시 닫혀
        # 오류를 볼 수 없기 때문에, 파일 로그와 '엔터로 닫기'가 필수다.
        err = traceback.format_exc()
        print("\n🚨 실행 중 오류가 발생했습니다:\n")
        print(err)
        log_path = os.path.join(_ROOT, "start_error.log")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{err}")
            print(f"오류 내용을 저장했습니다: {log_path}")
            print("이 파일 내용을 개발자(GitHub Issues)에 보내주시면 도움이 됩니다.")
        except OSError:
            pass
        _pause_before_exit()
