"""사전 파일은 **자기 상태를 맞게 말해야 한다** (2026-09-08).

■ 무엇이 있었나

영어 사전(`docs/assets/i18n-en.js`) 머리말이 이렇게 적어 두고 있었다:

    첫 화면(index)·실기록(paper)·**오늘의 판단(today)·기록 검증(trust)**은
    분량이 커서 다음 차례다. 그 페이지들은 영어로 봐도 한국어가 남는다.

그런데 `today.html`과 `trust.html`은 **이미 완역 대상**(`DONE`)이다 — 영어로
띄우면 한국어가 하나도 안 남아야 하고, 브라우저 검사가 그것을 확인한다.
즉 **번역 상태를 알려 주는 파일이 자기 상태를 틀리게 말하고 있었다.**

⚠️ 기계가 읽는 `partial`(화면에 '일부만 번역됨'을 띄우는 목록)은 맞았다.
   틀린 것은 **사람이 읽는 산문**이다. 그래서 화면은 멀쩡했고, 다음 사람이
   "today는 아직 미완이구나"라고 잘못 읽을 자리만 남았다.

■ 그래서 무엇을 검사하는가

산문을 고치는 것으로는 다음에 또 낡는다. 목록을 **검사가 읽을 수 있는
모양**으로 적게 하고 실제 분류와 대조한다(오늘 배운 것: *사유는 검사할 수
있는 모양으로 적는다*).

그리고 하나 더 — **공개 페이지가 어디에도 분류되지 않는 것**을 막는다.
지금은 10장이 전부 셋 중 하나에 들어 있지만(실측), 그것을 지키는 장치가
없었다. 새 페이지를 만들고 분류를 잊으면 완역도 아니고 하한도 없는 채로
조용히 산다.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_the_site_reads_in_english_too import (  # noqa: E402
    COVERAGE_FLOOR, DONE, KOREAN_ONLY)

DICT = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")

#: 공개 페이지로 세지 않는 것 — 오류 화면·조각·배포 산출물.
NOT_A_PAGE = {"404.html", "index-standalone.html", "sns_card.html"}


#: 머리말이 목록을 다는 이름들 — 다음 이름이 나오면 앞 목록이 끝난 것이다.
LABELS = ("완역", "충족률 하한", "일부러 안 옮김")


def _header_list(label: str) -> set[str]:
    """머리말의 `<label>: a.html · b.html` 목록을 읽는다(여러 줄 이어짐 허용).

    ⚠️ 욕심 많은 정규식으로 한 번에 잡으려다 **다음 목록까지 삼켰다.**
       목록의 끝은 '다음 이름표가 나오는 줄'이다 — 줄 단위로 센다.
    """
    assert label in LABELS, label
    lines, out, on = DICT.splitlines(), [], False
    for line in lines:
        head = re.match(r"\s*\*\s+(\S[^:]*):", line)
        if head and head.group(1).strip() in LABELS:
            on = head.group(1).strip() == label
        elif head or not line.lstrip().startswith("*"):
            on = False                          # 다른 문단이 시작됐다
        if on:
            out.append(line)
    assert out, f"머리말에서 '{label}' 줄을 못 찾았다 — 머리말 짜임새가 바뀌었나"
    return set(re.findall(r"[\w-]+\.html", "\n".join(out)))


def public_pages() -> set[str]:
    return {Path(p).name for p in glob.glob(str(ROOT / "docs" / "*.html"))} - NOT_A_PAGE


def test_the_header_says_what_is_actually_finished():
    """머리말의 '완역' 목록 = 실제 완역 대상."""
    assert _header_list("완역") == set(DONE), (
        "사전 머리말이 완역 목록을 틀리게 적고 있다 — 2026-09-08에 "
        "'오늘의 판단·기록 검증은 다음 차례'라고 적혀 있었고 둘 다 이미 "
        "완역이었다")


def test_the_header_says_what_is_still_partial():
    """머리말의 '충족률 하한' 목록 = 화면이 '일부만 번역됨'을 띄우는 목록."""
    assert _header_list("충족률 하한") == set(COVERAGE_FLOOR)
    partial = set(re.findall(r"[\w-]+\.html",
                             re.search(r"partial:\s*\[([^\]]*)\]", DICT).group(1)))
    assert partial == set(COVERAGE_FLOOR), (
        "화면에 '일부만 번역됨'을 띄우는 목록과 충족률 하한 목록이 갈렸다 — "
        "둘 중 하나는 반드시 거짓말이 된다")


def test_the_header_says_what_is_deliberately_korean():
    """머리말의 '일부러 안 옮김' 목록 = 운영자 전용 화면."""
    assert _header_list("일부러 안 옮김") == set(KOREAN_ONLY)


def test_every_public_page_belongs_somewhere():
    """새 페이지가 어디에도 안 들어가면 그날 말한다.

    ⚠️ 분류가 없으면 완역도 아니고 하한도 없다 — 아무 검사도 그 페이지의
       영어를 보지 않는데, 화면에는 '일부만 번역됨' 안내도 안 뜬다.
    """
    declared = set(DONE) | set(COVERAGE_FLOOR) | set(KOREAN_ONLY)
    pages = public_pages()
    assert not (pages - declared), (
        f"어느 분류에도 안 들어간 공개 페이지: {sorted(pages - declared)}")
    assert not (declared - pages), (
        f"있지도 않은 페이지가 분류돼 있다: {sorted(declared - pages)}")
