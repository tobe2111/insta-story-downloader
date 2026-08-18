"""모든 공개 페이지가 **같은 상단 바**를 쓰는가 (2026-08-18).

사장님 요청: "홈페이지에 있는 바가 모든 페이지에서 보이게 해줘."

그 전까지 페이지마다 손으로 만든 미니 nav가 제각각이었다 — 홈 링크만 있는
페이지, 링크 순서가 다른 페이지, 바가 아예 없는 페이지(today). 바를
``docs/assets/nav.js`` 한 파일로 모았으니, 이 검사는 두 가지를 지킨다.

    ① 공용 바의 링크가 홈(index.html)의 바와 **글자까지 같은가.**
       홈은 손대지 않았으므로(그 바가 원본) 둘이 갈라지면 어느 한쪽이
       거짓말을 하게 된다 — 같은 사실은 한 곳에서만 산다.
    ② 모든 공개 페이지가 공용 바를 **실제로 싣는가**, 그리고 옛 미니
       nav가 남아 이중 바가 되지 않는가.

실제로 그려지는가(스크립트 오류·404)는
``test_every_public_page_actually_renders.py``가 진짜 브라우저로 본다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 공용 바를 실어야 하는 페이지. index는 원본 바를 이미 갖고 있어 제외,
# index-standalone은 단일 파일 배포본(외부 스크립트 금지), sns_card는
# 사람이 보는 페이지가 아니라 SNS 카드 그리기용 캔버스, 404는 가운데
# 정렬 한 장짜리 안내문이라 바를 얹지 않는다.
WEARERS = ["paper.html", "today.html", "trust.html",
           "intraday.html", "weekly.html", "admin.html"]


def _index_nav_links() -> list[tuple[str, str]]:
    src = (DOCS / "index.html").read_text("utf-8")
    m = re.search(r"<nav>(.*?)</nav>", src, re.S)
    assert m, "index.html에 원본 바(<nav>)가 없다"
    return re.findall(r'<a class="lnk" href="([^"]+)">([^<]+)</a>', m.group(1))


def test_the_shared_bar_matches_the_home_bar_link_for_link():
    home = _index_nav_links()
    assert len(home) >= 5, f"홈 바의 링크가 이상하게 적다: {home}"
    nav_js = (DOCS / "assets" / "nav.js").read_text("utf-8")
    for href, label in home:
        pair = f'["{href}", "{label.strip()}"]'
        assert pair in nav_js, (
            f"공용 바에 홈 바의 링크가 없다: {pair} — 홈과 공용 바가 "
            "갈라지면 어느 한쪽이 거짓말이 된다")
    # 순서까지 같아야 한다 — 페이지마다 메뉴 순서가 다르면 다른 바다.
    pos = [nav_js.index(f'["{h}", "{l.strip()}"]') for h, l in home]
    assert pos == sorted(pos), "공용 바의 링크 순서가 홈과 다르다"


def test_the_shared_bar_keeps_the_download_button():
    nav_js = (DOCS / "assets" / "nav.js").read_text("utf-8")
    index = (DOCS / "index.html").read_text("utf-8")
    url = "https://github.com/tobe2111/insta-story-downloader/releases/latest"
    assert url in nav_js, "공용 바에 다운로드 버튼이 없다"
    assert url in index, "홈 바에 다운로드 버튼이 없다"
    assert "무료 다운로드" in nav_js, "다운로드 버튼의 문구가 홈과 다르다"


def test_every_public_page_wears_the_shared_bar():
    for name in WEARERS:
        src = (DOCS / name).read_text("utf-8")
        assert 'src="assets/nav.js"' in src, f"{name}이 공용 바를 싣지 않는다"


def test_no_page_wears_two_bars():
    """옛 미니 nav가 남아 있으면 바가 두 줄이 된다 — 한 페이지 한 바."""
    for name in WEARERS:
        src = (DOCS / name).read_text("utf-8")
        assert "<nav" not in src, (
            f"{name}에 옛 nav가 남아 있다 — 공용 바와 이중이 된다")
