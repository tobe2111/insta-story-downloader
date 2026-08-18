"""'내 전략' 자료 읽기가 **모든 사용자에게** 실제로 배송되는가 (2026-08-18).

사장님: "내 컴퓨터 뿐 아니라 각 이 프로그램을 쓰는 유저도 가능해야지.
만약 추출이 실패하면 실패한 이유도 알려주고."

실측한 구멍: pypdf·유튜브 자막 라이브러리가 기본 설치 목록에 없어서
"pip install 하세요"라는 안내가 나가고 있었다. 소스 설치자에게는 통하는
말이지만 **실행파일 사용자에게 pip은 없다** — 그 기능이 영영 없는 셈이다.
실행파일은 requirements.txt로 깐 환경에서 구워지므로, 여기 있어야
실행파일에도 들어간다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REQS = (ROOT / "requirements.txt").read_text("utf-8")


def test_the_pdf_reader_ships_by_default():
    assert "pypdf" in REQS, (
        "pypdf가 기본 설치에 없다 — 실행파일 사용자는 PDF 자료를 영영 "
        "못 넣는다('pip install 하세요'는 pip이 있는 사람에게만 통한다)")


def test_the_youtube_reader_ships_by_default():
    assert "youtube-transcript-api" in REQS, (
        "유튜브 자막 라이브러리가 기본 설치에 없다 — 실행파일 사용자는 "
        "유튜브 링크를 영영 못 넣는다")


def test_the_readers_actually_import():
    """목록에 적는 것과 깔리는 것은 다르다 — CI 환경에서 실제로 import한다."""
    import pypdf                                    # noqa: F401
    import youtube_transcript_api                   # noqa: F401


def test_both_transcript_api_generations_are_handled():
    """1.x에서 get_transcript가 사라졌다(실측) — 두 세대를 모두 지원해야
    새로 설치한 사용자에게 '자막이 없다'는 엉뚱한 안내가 안 나간다."""
    src = (ROOT / "quant" / "ingest" / "sources.py").read_text("utf-8")
    assert 'hasattr(YouTubeTranscriptApi, "get_transcript")' in src
    assert ".fetch(" in src


def test_extraction_failure_reasons_reach_the_screen():
    """실패하면 **왜**가 화면에 나가야 한다 — 조용한 실패는 고장으로 읽힌다."""
    src = (ROOT / "quant" / "web" / "mystrategy.py").read_text("utf-8")
    assert "result.reasons" in src, (
        "'내 전략' 화면이 추출 실패 사유를 보여주지 않는다")
