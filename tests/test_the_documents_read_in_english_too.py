"""문서도 영어로 읽을 수 있는가 (2026-08-26 감사 324).

사장님 지시: *"서비스 영어로도 만들어줘 홈페이지나 프로그램이나."* — 사이트만
영어가 되고 README가 한국어면, 저장소를 열어 본 사람은 5초 만에 닫는다.

■ 이 검사가 지키는 것

  ① **있는가** — 영어판 파일이 실제로 있고, 서로를 가리키는가. 링크 없는
     번역은 없는 번역이다.
  ② **한국어가 원본임을 밝히는가** — 두 문서는 언젠가 반드시 어긋난다.
     그때 어느 쪽이 맞는지 문서 자신이 말해야 한다(FROZEN_IDEAS ①).
  ③ **한계를 부드럽게 바꾸지 않았는가** — "수익을 보장하지 않습니다"가
     영어에서 사라지면 그건 번역 실수가 아니라 다른 제품이다. 특히
     '수익 보장' 문구는 이 저장소에서 법률 위험이다.
  ④ **기계 번역을 섞지 않았는가** — 영어 문서에 한국어가 남아 있으면
     반쪽이다. 다만 되돌아가는 링크와 프로그램이 요구하는 확인 문구
     (`실전`)는 한국어여야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PAIRS = [
    (ROOT / "README.md", ROOT / "README.en.md"),
    (ROOT / "docs" / "REALTIME_SETUP.md", ROOT / "docs" / "REALTIME_SETUP.en.md"),
    (ROOT / "docs" / "tradingview.md", ROOT / "docs" / "tradingview.en.md"),
]

# 영어 문서 안에 남아도 되는 한국어 — 되돌아가는 길과, 프로그램이 실제로
# 요구하는 글자다. 이 목록에 없는 한국어가 나오면 옮기다 만 것이다.
KOREAN_ALLOWED = {"한국어", "원문", "실전"}


@pytest.mark.parametrize("ko,en", PAIRS, ids=lambda p: p.name)
def test_the_english_twin_exists(ko, en):
    """영어판이 실제로 있는가 — 그리고 비어 있지 않은가."""
    assert ko.exists(), f"{ko.name}이 없다"
    assert en.exists(), f"{en.name}이 없다 — 영어로 읽을 길이 없다"
    assert len(en.read_text("utf-8")) > 1000, f"{en.name}이 너무 짧다"


@pytest.mark.parametrize("ko,en", PAIRS, ids=lambda p: p.name)
def test_the_two_point_at_each_other(ko, en):
    """링크 없는 번역은 **없는 번역**이다 — 아무도 못 찾는다."""
    assert en.name in ko.read_text("utf-8"), (
        f"{ko.name}에 영어판 링크가 없다")
    assert ko.name in en.read_text("utf-8"), (
        f"{en.name}에 한국어 원문 링크가 없다")


@pytest.mark.parametrize("ko,en", PAIRS, ids=lambda p: p.name)
def test_the_english_says_the_korean_is_the_original(ko, en):
    """두 문서는 언젠가 어긋난다 — **어느 쪽이 맞는지** 문서가 말해야 한다."""
    text = en.read_text("utf-8")
    assert "original" in text.lower(), (
        f"{en.name}이 한국어가 원본이라고 밝히지 않는다 — 어긋난 날 "
        "읽는 사람이 어느 쪽을 믿을지 알 수 없다")


def test_the_english_readme_keeps_the_honest_limits():
    """한계를 부드럽게 바꾸면 그건 번역이 아니라 **다른 제품**이다."""
    text = (ROOT / "README.en.md").read_text("utf-8")
    for must in [
        "does not guarantee profits",     # 수익 보장 없음
        "No system does",                 # "세상에 그런 시스템은 없습니다"
        "survivorship bias",              # 생존 편향
        "52–55%",                         # 방향 적중률 상한
        "worse than simply holding",      # 지금은 그냥 보유보다 못하다
        "decades",                        # 1억은 수십 년이라는 산수
        "own responsibility",             # 손실 책임은 사용자에게
    ]:
        assert must in text, (
            f"영어 README에서 '{must}'가 사라졌다 — 정직한 한계는 번역해도 "
            "남아야 한다")


BANNED = ["guaranteed profit", "guaranteed return", "guarantees profit",
          "risk-free", "sure profit"]
# 그 말을 **경고하려고** 쓴 문장은 다르다 — "guaranteed returns를 광고하는
# 봇은 사기다"는 정확히 우리가 하고 싶은 말이다. 부정·경고가 같은 문장에
# 있으면 주장이 아니다.
DENIAL = ["fraud", "not ", "never", "no ", "cannot", "does not", "⚠"]


@pytest.mark.parametrize("ko,en", PAIRS, ids=lambda p: p.name)
@pytest.mark.parametrize("banned", BANNED)
def test_the_english_never_promises_returns(ko, en, banned):
    """'수익 보장'류를 **주장으로** 쓰지 않는다(법률 위험 · 사기죄)."""
    low = en.read_text("utf-8").lower()
    for m in re.finditer(re.escape(banned), low):
        around = low[max(0, m.start() - 200):m.end() + 200]
        assert any(d in around for d in DENIAL), (
            f"{en.name}에 '{banned}'가 부정 없이 쓰였다:\n  …{around}…")


def test_the_promise_check_would_actually_catch_one():
    """대조군 — 부정 예외가 너무 넓으면 위 검사는 아무것도 안 막는다."""
    low = "our system delivers guaranteed returns every month."
    hits = [m for m in re.finditer("guaranteed returns", low)
            if any(d in low[max(0, m.start() - 200):m.end() + 200]
                   for d in DENIAL)]
    assert not hits, "부정 없이 약속한 문장을 면제가 통과시킨다"


@pytest.mark.parametrize("ko,en", PAIRS, ids=lambda p: p.name)
def test_no_half_translated_korean_is_left(ko, en):
    """영어 문서에 한국어가 섞여 있으면 **옮기다 만 것**이다."""
    left = [w for w in set(re.findall(r"[가-힣]+", en.read_text("utf-8")))
            if w not in KOREAN_ALLOWED]
    assert not left, f"{en.name}에 옮기지 않은 한국어가 남았다: {sorted(left)}"


def test_the_allowance_is_not_a_blanket():
    """대조군 — 면제 목록이 커지면 위 검사는 아무것도 안 지킨다."""
    assert len(KOREAN_ALLOWED) <= 5, (
        f"한국어 면제가 {len(KOREAN_ALLOWED)}개로 늘었다 — 면제를 늘리기 전에 "
        "정말 옮길 수 없는 글자인지 보라")


def test_the_english_readme_points_at_the_live_record():
    """영어권 방문자가 **실제 기록**으로 갈 수 있어야 한다.

    영어 README만 읽고 사이트를 못 찾으면, 이 저장소의 유일한 주장
    ("장부가 공개돼 있다")을 확인할 방법이 없다.
    """
    text = (ROOT / "README.en.md").read_text("utf-8")
    assert "quant.jiwon-1a2.workers.dev" in text, (
        "영어 README에 공개 기록 주소가 없다")
