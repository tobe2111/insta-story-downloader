"""더블클릭 실행기(start.py)의 계약 검사 (표준 라이브러리만).

포트가 선점됐을 때 그대로 죽으면 더블클릭 사용자는 창이 즉시 닫혀 원인조차
볼 수 없다 — 자동 포트 전환과 오류 로그 장치를 테스트로 고정한다.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import start  # noqa: E402


def test_pick_port_skips_busy_port():
    """선점된 포트는 건너뛰고 다음 빈 포트를 고른다."""
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))          # OS가 빈 포트를 배정
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    try:
        picked = start.pick_port(start=busy, tries=10)
        assert picked != busy and picked > busy
        # 반환된 포트는 실제로 바인딩 가능해야 한다
        probe = socket.socket()
        probe.bind(("127.0.0.1", picked))
        probe.close()
    finally:
        blocker.close()


def test_pick_port_raises_when_all_busy():
    """시도 범위가 전부 사용 중이면 한국어 안내와 함께 실패한다."""
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    try:
        try:
            start.pick_port(start=busy, tries=0)
            raise AssertionError("OSError가 나야 한다")
        except OSError as exc:
            assert "사용 중" in str(exc)
    finally:
        blocker.close()


def test_error_logging_contract():
    """오류 시 콘솔 유지 + 파일 로그 장치가 소스에 존재한다(더블클릭 진단 필수)."""
    src = Path(start.__file__).read_text(encoding="utf-8")
    assert "start_error.log" in src
    assert "_pause_before_exit" in src
    assert "traceback" in src
