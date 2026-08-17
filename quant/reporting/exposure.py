"""종목별 실제 노출(장부의 ``applied``)을 **부호까지 지켜서** 읽는 규칙.

⚠️ 왜 이 파일이 생겼나 (2026-08-17, 감사 264).
   장부는 오랫동안 노출을 ``abs()``로 적었다. 그래서 **숏 -30%와 롱 +30%가
   화면·캡션에 똑같이 ``30%``로 남았다.** 지금은 숏이 링에 없어 값이 늘
   양수라 아무도 눈치채지 못한다 — 숏을 켜는 날, 캡션은 "아마존 30% 배분"
   이라고 방송하면서 실제로는 아마존을 **팔아 둔** 상태가 된다.

   부호를 살리는 것만으로는 부족했다. 화면·캡션 네 곳이 각자
   ``applied[k] > 0``을 "들고 있다"의 뜻으로 쓰고 있어서, 부호를 살리면
   **숏이 '보유 없음'으로 사라진다.** 판정을 한 곳에 모으는 이유다
   (FROZEN_IDEAS ①·㉞ — 같은 판정을 두 곳에서 쓰면 언젠가 갈라진다).

브라우저 짝은 ``docs/assets/exposure.js``이고, 두 구현이 같은 답을 내는지는
``tests/test_the_ledger_keeps_the_direction.py``가 값으로 확인한다.
"""

from __future__ import annotations

import math


def held(v) -> bool:
    """이 종목을 지금 **잡고 있는가** — 롱이든 숏이든."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and abs(x) > 0


def count(applied: dict | None) -> int:
    """잡고 있는 종목 수 (롱 + 숏)."""
    return sum(1 for v in (applied or {}).values() if held(v))


def side(v) -> str:
    """방향 — 롱이면 ``""``, 숏이면 ``"숏 "``. 문구 앞에 그대로 붙인다."""
    try:
        return "숏 " if float(v) < 0 else ""
    except (TypeError, ValueError):
        return ""


def text(v, digits: int = 2) -> str:
    """화면에 찍을 노출 문자열. **크기는 절댓값, 방향은 말로** 적는다.

    ``-30%``라고만 쓰면 "손실 30%"로 읽힌다 — 방향은 부호가 아니라 글자로.
    """
    if not held(v):
        return "0%"
    x = float(v)
    return f"{side(x)}{abs(x) * 100:.{digits}f}%"


def top(applied: dict | None, n: int = 5) -> list[tuple[str, float]]:
    """큰 것부터 n개 — **크기(절댓값) 기준**이다.

    부호로 정렬하면 숏이 아무리 커도 목록 맨 끝으로 밀려 "오늘 어디에
    실었나"에 답하지 못한다.
    """
    rows = [(k, float(v)) for k, v in (applied or {}).items() if held(v)]
    rows.sort(key=lambda kv: -abs(kv[1]))
    return rows[:n]


def gross(applied: dict | None) -> float:
    """총노출 Σ|w| — "얼마가 시장에 나가 있나"."""
    return sum(abs(float(v)) for v in (applied or {}).values() if held(v))


def net(applied: dict | None) -> float:
    """순노출 Σw — "시장이 오르면 이득인가".

    롱숏이 반반이면 총노출은 100%인데 순노출은 0%(시장 중립)다. 총노출만
    적으면 그 구별이 사라진다.
    """
    return sum(float(v) for v in (applied or {}).values() if held(v))
