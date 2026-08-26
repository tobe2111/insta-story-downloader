"""프로그램 화면·로그를 영어로도 읽게 한다 (2026-08-26 감사 326).

사장님 지시: *"서비스 영어로도 만들어줘 홈페이지나 프로그램이나."*

■ 왜 사이트와 같은 방식인가 — 한국어가 '원본'이다

이 프로그램의 말은 손으로 쓴 한국어 문자열 안에 살고 있다. 영어판 소스를
따로 만들면 같은 문장이 두 곳에 살게 되고, 문구를 고칠 때마다 한쪽이
조용히 낡는다(FROZEN_IDEAS ①). 그래서 **소스는 하나**로 두고, 한국어
문장을 열쇠로 삼는 사전(i18n_en.py)에서 영어를 찾아 바꿔 끼운다.
사이트(docs/assets/i18n.js)와 **같은 규칙**이다:

  · 사전에 없으면 **한국어 그대로 둔다.** 기계 번역으로 메우지 않는다 —
    이 프로그램은 돈 이야기를 한다. "대충 맞는 영어"는 숫자 옆에서
    사실이 아닌 주장이 된다.
  · 숫자가 든 문장은 **규칙(정규식)**으로 옮기고, 숫자·금액·날짜는
    **한 글자도 건드리지 않는다.**
  · 통째로 못 찾으면 ` · ` ` — ` 로 끊어 **절 단위**로 다시 해 본다.
    통째로 찾았더라도 절 단위 결과에 한국어가 덜 남으면 그쪽을 쓴다
    (욕심 많은 규칙이 문장을 삼켜 반쪽 영어가 되는 것을 막는다).

■ 언어는 어떻게 정해지는가

  ① `--lang en` (명령줄) → 그 실행에만 적용되고 환경변수로 전달된다
  ② `QUANT_LANG` 환경변수
  ③ 아무것도 없으면 **한국어**(원본)

⚠️ 브라우저와 달리 터미널의 언어 설정(`LANG=en_US.UTF-8`)은 **보지 않는다.**
   한국 사용자의 터미널이 영어 로케일인 경우가 흔하고, 그 사람에게 원본을
   빼앗는 것은 짐작이 아니라 사고다. 사이트는 방문자가 누구인지 모르지만,
   프로그램을 실행하는 사람은 스스로 말할 수 있다.
"""
from __future__ import annotations

import os
import re

__all__ = ["lang", "set_lang", "t", "say", "translate_parser"]

_ENV = "QUANT_LANG"
_LANGS = ("ko", "en")

# 절을 끊는 이음매 — 사이트(i18n.js)의 SEPS와 같은 목록이다.
_SEPS = (" · ", " — ")
_HANGUL = re.compile(r"[가-힣]")


def lang() -> str:
    v = (os.environ.get(_ENV) or "").strip().lower()
    return v if v in _LANGS else "ko"


def set_lang(value: str) -> None:
    """이 실행의 언어를 정한다. 자식 프로세스도 같은 말을 하게 환경에 남긴다."""
    if value in _LANGS:
        os.environ[_ENV] = value


def _dict() -> dict:
    from quant.i18n_en import STRINGS
    return STRINGS


def _rules() -> list:
    from quant.i18n_en import RULES
    return RULES


def _clauses(text: str) -> list:
    """괄호 밖의 이음매에서만 끊는다 — 괄호 안을 끊으면 뜻이 깨진다."""
    out, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        hit = None
        if depth == 0:
            for sep in _SEPS:
                if text.startswith(sep, i):
                    hit = sep
                    break
        if hit:
            out.append(text[start:i])
            out.append(hit)
            i += len(hit)
            start = i
        else:
            i += 1
    out.append(text[start:])
    return out


# 치환문의 `\*2`는 "잡아 둔 그 조각을 한 번 더 옮겨라"는 뜻이다
# (사이트의 `$*n`과 같다). "우연 배제 예/아니오"처럼 값 자리에 **말**이
# 들어오는 문장이 있는데, 그 말까지 규칙에 다 적을 수는 없다. 값은 그대로
# 흘려보내고 말만 사전으로 보낸다. 사전에 없으면 **한국어를 그대로 둔다.**
_SLOT = re.compile(r"\\(\*?)(\d)")
_MAX_DEPTH = 4


def _fill(repl: str, m, depth: int) -> str:
    def one(mo):
        star, n = mo.group(1), int(mo.group(2))
        if n > (m.re.groups or 0):
            return mo.group(0)                 # 없는 자리는 글자 그대로
        g = m.group(n) or ""
        if not star or depth >= _MAX_DEPTH:
            return g
        deeper = _one(g, depth + 1)
        return g if deeper is None else deeper
    return _SLOT.sub(one, repl)


def _one(core: str, depth: int = 0) -> str | None:
    """절 하나만 찾는다(사전 → 규칙). 못 찾으면 None."""
    d = _dict()
    hit = d.get(core)
    if hit is None:
        hit = d.get(re.sub(r"\s+", " ", core))
    if hit is None:
        for pat, repl in _rules():
            m = re.match(pat, core)
            if m:
                hit = _fill(repl, m, depth)
                break
    return None if hit is None or hit == core else hit


def _by_clause(core: str) -> str | None:
    parts = _clauses(core)
    if len(parts) < 2:
        return None
    any_hit = False
    done = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:                      # 홀수 자리는 이음매
            done.append(part)
            continue
        one = _one(part)
        if one is not None:
            any_hit = True
            done.append(one)
        else:
            done.append(part)
    return "".join(done) if any_hit else None


def _korean(text: str) -> int:
    return len(_HANGUL.findall(text))


def t(text):
    """한 문장을 영어로. 한국어가 아니거나 모르면 **그대로 돌려준다.**"""
    if lang() != "en" or not isinstance(text, str) or not text:
        return text
    # 여러 줄은 줄마다 따로 본다 — 요약 표처럼 줄이 곧 문장인 출력이 많다.
    if "\n" in text:
        return "\n".join(t(line) for line in text.split("\n"))
    m = re.match(r"^(\s*)([\s\S]*?)(\s*)$", text)
    head, core, tail = m.group(1), m.group(2), m.group(3)
    if not core:
        return text
    hit = _one(core)
    by = _by_clause(core)
    if by is not None and (hit is None or _korean(by) < _korean(hit)):
        hit = by
    if hit is None or hit == core:
        return text
    return head + hit + tail


def say(*args, **kwargs) -> None:
    """print의 자리 — 나가는 글자를 한 번 거쳐 보낸다."""
    print(*[t(a) for a in args], **kwargs)


def translate_parser(parser) -> None:
    """argparse의 설명·도움말을 옮긴다 — 소스는 여전히 한국어 하나다."""
    if lang() != "en":
        return
    seen = set()

    def walk(p):
        if id(p) in seen:
            return
        seen.add(id(p))
        for attr in ("description", "epilog", "usage"):
            v = getattr(p, attr, None)
            if isinstance(v, str):
                setattr(p, attr, t(v))
        for act in getattr(p, "_actions", []):
            if isinstance(getattr(act, "help", None), str):
                act.help = t(act.help)
            # ⚠️ 하위 명령의 한 줄 설명은 **여기 없다.** argparse는 그것을
            #    `_choices_actions`라는 별도 목록에 들고 있어서, `_actions`만
            #    훑으면 `--help` 첫 화면이 통째로 한국어로 남는다.
            for pseudo in getattr(act, "_choices_actions", []) or []:
                if isinstance(getattr(pseudo, "help", None), str):
                    pseudo.help = t(pseudo.help)
            choices = getattr(act, "choices", None)
            if isinstance(choices, dict):
                for sub in choices.values():
                    walk(sub)

    walk(parser)
