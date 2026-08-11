"""'비중'이 두 가지인데 이름이 하나였다 (감사 100).

이 사이트에는 성격이 다른 계좌가 두 종류 있다.

    종목 계좌   — 그 종목 하나만 굴리는 독립 계좌(각각 만원 시작)
    통합 계좌   — 8마일 챌린지 본체(8만원). 여기 노출은 종목 비중에
                  **배분 슬라이스 × 변동성 타깃 × 킬스위치**를 곱한 값이다.

첫 화면의 '종목별 현황' 표는 종목 계좌의 비중을 그냥 `비중`이라 적었다.
그런데 그 페이지의 주인공은 통합 계좌다. 읽는 사람은 당연히

    "이 펀드가 애플을 12.4% 들고 있구나"

로 읽는다. 실제 통합 노출은 **1.2%** — 10배 차이다. 같은 날 같은 페이지가
'총노출 7%'라고도 말하니, 12.4%짜리 종목이 여럿이면 산술이 성립하지 않는다.

감사 91(카드가 배분 예산을 '매수'라 불렀다)·92(체결 기록이 슬라이스를
빼먹었다)와 정확히 같은 계열이다 — **닮은 숫자 두 개, 이름 하나.**

고친 방식도 같다: 이름을 구분하고, 두 숫자를 나란히 놓는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INDEX = (ROOT / "docs" / "index.html").read_text("utf-8")


def _head_cells() -> list[str]:
    m = re.search(r'<table id="symtable">\s*<thead><tr>(.*?)</tr></thead>',
                  INDEX, re.S)
    assert m, "종목별 현황 표의 머리글을 찾지 못했다 — 검사가 낡았다"
    return [re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<th[^>]*>.*?</th>", m.group(1), re.S)]


def test_the_bare_word_weight_is_not_a_column_name():
    cells = _head_cells()
    assert "비중" not in cells, (
        f"'비중'이라는 이름만으로는 어느 계좌의 비중인지 알 수 없다: {cells}")


def test_both_kinds_are_shown_side_by_side():
    cells = _head_cells()
    assert any("종목계좌" in c for c in cells), f"종목 계좌 비중 열이 없다: {cells}"
    assert any("통합" in c for c in cells), (
        f"통합 계좌 노출 열이 없다 — 읽는 사람이 가장 궁금한 숫자다: {cells}")


def test_the_portfolio_column_reads_the_applied_exposure():
    """통합 노출은 장부의 applied(실제 적용 노출)에서 와야 한다.

    종목 비중에 무언가를 곱해 화면에서 다시 계산하면, 감사 91·92가 고친
    바로 그 실수(스케일러를 빼먹는다)를 화면에서 반복하게 된다.
    """
    body = INDEX.split("/* --- 종목별 표 ---", 1)[1].split("/* --- 오답", 1)[0]
    assert "pfLast.applied" in body, (
        "통합 노출을 장부의 applied에서 읽지 않는다")
    assert not re.search(r"r\.w\s*\*\s*[0-9a-zA-Z_.]+\s*\*", body), (
        "화면에서 종목 비중에 스케일러를 곱해 통합 노출을 다시 계산한다 — "
        "계산은 기록하는 쪽에서 한 번만 한다")


def test_the_column_count_matches_the_header():
    """열을 늘리고 colspan을 안 고치면 '불러오는 중' 칸이 깨진다."""
    n = len(_head_cells())
    for span in re.findall(r'colspan="(\d+)"', INDEX):
        if int(span) >= 5:                      # 이 표의 안내 행만 해당
            assert int(span) == n, (
                f"머리글은 {n}열인데 안내 행 colspan은 {span}이다")
