"""비어 있거나 사고가 났을 때만 뜨는 화면 줄도 영어로 읽힌다 (2026-09-08).

■ 왜 또 필요한가 — 이 자리에서 세 번 당했다

같은 병을 하루에 세 얼굴로 봤다:

    ① 장중 트랙의 '편도 요율' 줄  — 장부에 값이 실린 **다음 날** CI가 잡았다
    ② 첫 화면의 경보 문구 32개    — 사고가 나야 뜨므로 평소 화면엔 없다
    ③ 실기록의 조기 판정 진도표   — 그날 자료가 쌓인 비교만 그려진다

셋 다 뿌리가 하나다 — **그날의 초록은 "이 줄이 영어로 나온다"가 아니라
"이 줄이 아직 안 뜬다"였다.** ①은 사후에, ②③은 소스에서 세어 막았다.

■ 이번에 남아 있던 자리

완역 대상(`DONE`)으로 **선언한** 7페이지다. 이 페이지들은 "영어로 보면
한국어가 하나도 안 남는다"가 약속인데, 그 검사는 **그날 렌더된 것만** 본다.

실측(2026-09-08): 조건부 조각 **40개**에 영어가 없었다 —
미국 2 · 코인 단타 11 · 선물 11 · 주간 4 · ML 5 · 오늘 3 · 검증 4.
빈 상태 안내("아직 기록이 없습니다"), 불러오기 실패, 강제 청산·하드 스톱
같은 사고 문구가 전부 여기 있었다. **영어 독자가 가장 읽어야 할 날의 문장들이다.**

■ 재는 방법 — 번역기와 **같은 자**로 센다

번역기(`assets/i18n.js`)는 텍스트 노드를 통째로 찾아보고, 못 찾으면
` · `와 ` — `로 끊어(괄호 안은 안 끊는다) 절마다 다시 찾는다. 그러니
여기서도 그렇게 센다 — 통째로 있거나, 절이 전부 있으면 덮인 것이다.

⚠️ `console.error`의 인자는 **화면이 아니다.** 개발자 콘솔에만 나가므로
   사전에 넣으면 사전이 부풀기만 한다. 세는 대상에서 뺀다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_the_site_reads_in_english_too import DONE  # noqa: E402

DOCS = ROOT / "docs"
DICT = (DOCS / "assets" / "i18n-en.js").read_text("utf-8")

#: 한 조각이 '문장'으로 셀 만한 최소 길이(경보 검사와 같은 눈금).
MIN_HANGUL = 6

_STR = re.compile(
    r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', re.S)
_VALUE = "\x00"          # 장부에서 오는 값 자리


def _norm(text: str) -> str:
    """한글과 공백만 남긴다 — 값·날짜·이름은 일부러 열쇠에 안 박기 때문."""
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣\s]", " ", text)).strip()


def _drop_template_values(s: str) -> str:
    """`${…}`는 값 자리다. 중괄호 짝을 세어 통째로 지운다."""
    out, i = [], 0
    while i < len(s):
        if s.startswith("${", i):
            depth, j = 1, i + 2
            while j < len(s) and depth:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                j += 1
            out.append(_VALUE)
            i = j
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _strip_console(js: str) -> str:
    """`console.*(…)`는 화면이 아니다 — 괄호 짝을 세어 통째로 지운다."""
    out, i = [], 0
    while True:
        m = re.compile(r"console\.\w+\(").search(js, i)
        if not m:
            out.append(js[i:])
            return "".join(out)
        out.append(js[i:m.start()])
        depth, j = 1, m.end()
        while j < len(js) and depth:
            if js[j] == "(":
                depth += 1
            elif js[j] == ")":
                depth -= 1
            j += 1
        i = j


def text_runs(js: str) -> list[str]:
    """화면에 나가는 **텍스트 런**을 복원한다.

    ⚠️ 리터럴 하나가 텍스트 노드 하나가 아니다. 화면 문장은 대개 `+`로
       여러 줄에 걸쳐 이어 붙고, 그 사이에 값이 낀다. 리터럴 단위로 세면
       실제로는 없는 문장을 사전에 요구하게 된다(처음에 그렇게 짜서
       부풀린 숫자를 봤다).
    """
    out: list[str] = []
    i, cur = 0, None
    while True:
        m = _STR.search(js, i)
        if not m:
            break
        lit = m.group(1) or m.group(2) or (
            _drop_template_values(m.group(3)) if m.group(3) is not None else "")
        gap = js[i:m.start()]
        if cur is not None and re.fullmatch(r"[\s+]*", gap):
            cur += lit                                   # 바로 이어지는 리터럴
        elif cur is not None and re.fullmatch(r"[\s+]*\+[^\"'`]*\+[\s]*", gap):
            cur += _VALUE + lit                          # 값 하나를 끼고 이어짐
        else:
            if cur:
                out.append(cur)
            cur = lit
        i = m.end()
    if cur:
        out.append(cur)
    return out


def _clauses(text: str) -> list[str]:
    """번역기와 같은 규칙으로 절을 끊는다 — 괄호 안에서는 안 끊는다."""
    out, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            for sep in (" · ", " — "):
                if text.startswith(sep, i):
                    out.append(text[start:i])
                    i += len(sep)
                    start = i
                    break
            else:
                i += 1
            continue
        i += 1
    out.append(text[start:])
    return out


def screen_pieces(name: str) -> list[str]:
    """그 페이지가 화면에 내보낼 수 있는 **한국어 조각** — 소스에서 센다."""
    html = (DOCS / name).read_text("utf-8")
    js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    js = re.sub(r"(?m)^\s*//.*$", " ", js)
    js = _strip_console(js)
    out = []
    for run in text_runs(js):
        # 태그에서 **자른다**(지우지 않는다) — 번역기는 텍스트 노드 단위다.
        for piece in re.split(r"<[^>]+>", run):
            if _enough(piece):
                out.append(" ".join(piece.split()))
    return list(dict.fromkeys(out))


def _enough(text: str) -> bool:
    return len(re.findall(r"[가-힣]", text)) >= MIN_HANGUL


def _covered(piece: str, flat: str) -> bool:
    """이 조각이 사전에 덮여 있는가 — 번역기가 찾는 순서 그대로.

    ⚠️ **값이 낀 자리는 통째로 요구하면 안 된다.** 값 자리(`${…}`)에는
       한국어가 들어 있을 수 있는데(예: "오늘 13종목 보유 / 후보 42종목"),
       이 검사는 그것을 볼 수 없다. 통째로 요구했더니 이미 덮여 있는
       문장을 '빠졌다'고 말했고, 그 거짓 경보를 믿고 **넓은 규칙을 위에
       얹어 아래의 정확한 규칙을 죽였다**(2026-09-08, 브라우저 검사가
       그날 잡았다). 그래서 값 자리로 끊어 **글자로 적힌 부분만** 본다.
    """
    if _norm(piece) in flat:
        return True
    parts = _clauses(piece)
    if len(parts) >= 2 and all(_norm(p) in flat for p in parts if _enough(p)):
        return True
    if _VALUE in piece:
        return all(_norm(p) in flat
                   for p in piece.split(_VALUE) if _enough(p))
    return False


def test_the_counter_actually_finds_the_quiet_lines():
    """세는 장치가 0을 세면 아래 검사가 조용히 통과한다 — 그 길을 막는다."""
    total = sum(len(screen_pieces(n)) for n in DONE)
    assert total >= 100, (
        f"조건부 화면 조각을 {total}개밖에 못 읽었다 — 페이지 짜임새가 "
        "바뀌었다면 이 검사도 따라가야 한다(안 따라가면 조용히 통과한다)")


def test_the_console_is_not_counted_as_a_screen():
    """대조군 — `console.error`의 한국어를 화면으로 세면 사전만 부푼다."""
    js = _strip_console('console.error("주간 아카이브 렌더 실패:", e);'
                        'x.innerHTML="집계할 기록이 부족합니다.";')
    assert "렌더 실패" not in js
    assert "집계할 기록이 부족합니다" in js


def test_every_quiet_line_on_a_finished_page_reads_in_english():
    """완역 선언한 페이지는 **안 뜨는 줄까지** 영어가 있어야 한다.

    실행해 보지 않고 잡는다 — 브라우저 검사는 그 상태가 실제로 온 날에만
    이 줄들을 볼 수 있고, 그날은 이미 늦다.
    """
    flat = _norm(DICT)
    missing = {}
    for name in DONE:
        gap = [p for p in screen_pieces(name) if not _covered(p, flat)]
        if gap:
            missing[name] = gap
    assert not missing, (
        "완역 선언한 페이지에 영어 없는 조건부 문구가 남아 있다 — "
        f"그 상태가 오는 날 영어 독자는 한국어를 받는다: "
        f"{ {k: v[:3] for k, v in missing.items()} }")
