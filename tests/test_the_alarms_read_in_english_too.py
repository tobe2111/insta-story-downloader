"""잘못됐을 때만 뜨는 경보 문구도 영어로 읽힌다 (2026-09-08).

■ 왜 이 검사가 따로 필요한가

이 파일의 형제(`test_the_site_reads_in_english_too.py`)는 **브라우저로
페이지를 띄워** 한국어가 남았는지 본다. 그 방법의 한계가 같은 파일에 이미
적혀 있다:

    "브라우저 검사는 그날 장부가 들고 있는 종목만 그리므로,
     안 들고 있는 종목의 구멍은 못 본다."      (2026-08-26, 종목 이름)

첫 화면의 **경보 문구**가 정확히 그 자리다. 그 줄들은 장부에 사고가 적혀야만
뜬다 — 장부가 묵거나 · 사람이 개입했거나 · 합성 데이터로 떨어졌을 때. 사고가
없는 날에는 줄 자체가 없으므로, 영어가 빠져 있어도 **브라우저 검사가 구조적으로
못 본다.** 그날의 초록은 "이 줄이 영어로 나온다"가 아니라 "이 줄이 아직 안 뜬다"다.

⚠️ 이건 2026-09-08 아침에 값비싸게 배운 것이다. 장중 트랙의 '편도 요율' 줄이
   똑같은 이유로 붙인 날에는 안 걸렸고, 밤 배치가 값을 채운 **다음 날** CI가
   잡았다. 경보는 그보다 나쁘다 — 사고가 나야 뜨므로, 처음 뜨는 날이 곧
   "가장 읽혀야 할 날"이다.

■ 실측 (2026-09-08)

첫 화면 경보 32개의 한국어 조각 81개 중 **54개가 사전에 아예 없었다.**
장부가 묵었다 · 사람이 개입했다 · 합성 데이터를 썼다 — 영어 독자가 가장
읽어야 할 문장들이 한국어로 나가고 있었다.

⚠️ **정직하게 — 이건 숨어 있던 고장이 아니라 선언된 미완이었다.** 사전
   머리말이 "첫 화면·실기록은 분량이 커서 다음 차례"라고 적어 두었고,
   첫 화면은 완역 대상(DONE)이 아니라 **충족률 하한**(0.85)으로 관리된다.
   다만 그 하한은 **조용한 날의 화면**에서 재므로, 사고가 난 날 영어 독자가
   실제로 받는 화면은 그 숫자보다 나쁘다. 그래서 경보부터 옮겼다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INDEX = (ROOT / "docs" / "index.html").read_text("utf-8")
DICT = (ROOT / "docs" / "assets" / "i18n-en.js").read_text("utf-8")

#: 한 조각이 '문장'으로 셀 만한 최소 길이. 조사 한두 글자까지 요구하면
#: 사전이 부풀기만 하고 읽는 사람에게 달라지는 것이 없다.
MIN_HANGUL = 6


def _norm(text: str) -> str:
    """한글과 공백만 남긴다.

    사전의 열쇠는 정규식이라 값 자리가 ``(\\d+)`` 같은 문법으로 들어 있고,
    숫자·날짜·종목 이름은 **일부러 열쇠에 안 박는다**(장부에서 오므로 곧
    만료된다 — 2026-08-26에 배운 규칙). 그래서 견줄 때 그것들을 지운다.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣\s]", " ", text)).strip()


def alarm_pieces() -> list[str]:
    """첫 화면 경보가 화면에 내보내는 **한국어 조각** — 소스에서 센다.

    ⚠️ 태그에서 **자른다**(지우지 않는다). 번역기는 텍스트 노드 단위로
       움직이므로 ``<b>제목</b> — 본문``은 두 조각이다. 지워서 이어 붙이면
       실제로는 없는 문장을 사전에 요구하게 된다.
    """
    blocks = "\n".join(re.findall(r"<script>(.*?)</script>", INDEX, re.S))
    calls = []
    for m in re.finditer(r"flags\.push\(", blocks):
        i, depth = m.end(), 1
        while i < len(blocks) and depth:
            if blocks[i] == "(":
                depth += 1
            elif blocks[i] == ")":
                depth -= 1
            i += 1
        calls.append(blocks[m.end():i - 1])

    out: list[str] = []
    for arg in calls:
        arg = re.sub(r"/\*.*?\*/", "", arg, flags=re.S)     # 주석은 화면이 아니다
        for a, b in re.findall(r"\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'",
                               arg):
            for piece in re.split(r"<[^>]+>", a or b):
                if len(re.findall(r"[가-힣]", piece)) >= MIN_HANGUL:
                    out.append(piece.strip())
    return out


def test_the_counter_actually_finds_the_alarms():
    """세는 장치가 0을 세면 이 파일 전체가 조용히 통과한다 — 그 길을 막는다."""
    pieces = alarm_pieces()
    assert len(pieces) >= 40, (
        f"경보 조각을 {len(pieces)}개밖에 못 읽었다 — 화면의 경보 짜임새가 "
        "바뀌었다면 이 검사도 따라가야 한다(안 따라가면 조용히 통과한다)")


def test_every_alarm_can_be_read_in_english():
    """사고가 났을 때 뜨는 문장은 **전부** 사전에 있어야 한다.

    실행해 보지 않고 잡는다 — 브라우저 검사는 그 사고가 실제로 난 날에만
    이 줄들을 볼 수 있고, 그날은 이미 늦다.
    """
    flat = _norm(DICT)
    missing = [p for p in alarm_pieces() if _norm(p) not in flat]
    assert not missing, (
        f"영어 사전에 없는 경보 문구 {len(missing)}건 — 사고가 난 날 영어 "
        f"독자는 이 문장을 한국어로 받는다: {missing[:5]}")


def test_the_dictionary_does_not_pin_a_measured_value():
    """경보의 숫자·날짜를 열쇠에 박으면 다음 사고에서 영어가 사라진다.

    2026-08-26에 배운 규칙(날짜)과 2026-08-27에 넓힌 규칙(실측 숫자)을
    경보 자리에도 건다. 여기 값은 전부 장부에서 온다.
    """
    i = DICT.index("잘못됐을 때만 뜨는 경보 문구")
    block = DICT[i:i + 12000]
    # 사전 항목 안(따옴표 안)의 값만 본다 — 주석의 날짜·실측은 기록이다.
    for line in block.split("\n"):
        if not line.strip().startswith('["^'):
            continue
        key = line.split('",')[0]
        assert not re.search(r"\d{4}-\d{2}-\d{2}(?!\})", key.replace("\\d", "")), (
            f"열쇠에 날짜가 박혔다 — 그 날짜가 바뀌면 영어가 사라진다: {line.strip()[:90]}")
