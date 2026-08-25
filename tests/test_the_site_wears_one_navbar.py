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
# ⚠️ 트랙 페이지 셋(us·futures)과 머신러닝 페이지는 나중에 생겼는데 이
#    목록에 안 들어와 있었다 — **바를 싣는지 아무도 확인하지 않는 페이지**가
#    셋 있었다는 뜻이다(감사 317). 페이지를 늘릴 때 여기도 늘려야 한다.
WEARERS = ["paper.html", "today.html", "trust.html",
           "intraday.html", "us.html", "futures.html", "ml.html",
           "weekly.html", "admin.html"]


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

    # ⚠️ 반대 방향도 봐야 한다(감사 317). 예전 판은 "홈의 링크가 공용 바에
    #    있는가"만 봤다. 그래서 머신러닝 페이지를 공용 바에만 넣고 홈 바에는
    #    안 넣은 것이 **한 달 가까이 초록불로 지나갔다** — 다른 모든 페이지
    #    에서는 보이는 메뉴가 정작 첫 화면에서만 없었다.
    shared = re.findall(r'\["([\w.\-]+)", "([^"]+)"\]', nav_js)
    assert [(h, l.strip()) for h, l in shared] == \
        [(h, l.strip()) for h, l in home], (
        f"공용 바에만 있는 링크가 있다: {shared} != {home}")


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


def test_mobile_gets_a_menu_not_a_dead_end():
    """모바일(≤820px)은 링크를 숨기는 대신 삼단 바 메뉴를 연다.

    2026-08-23 사장님: "모바일로 보면 다른 페이지를 볼 수가 없어."
    그 전까지는 820px 아래에서 링크를 display:none으로 숨기기만 했다 —
    숨긴 자리에 대체 수단이 없으면 그건 정리가 아니라 차단이다.
    """
    nav_js = (DOCS / "assets" / "nav.js").read_text("utf-8")
    assert "qn-burger" in nav_js and "qn-menu" in nav_js, "공용 바에 삼단 바가 없다"
    assert "#qnav .qn-burger{display:none" in nav_js, (
        "삼단 바가 데스크톱에도 보인다")
    assert "#qnav .qn-burger{display:inline-flex}" in nav_js, (
        "모바일에서 삼단 바가 안 보인다 — 다시 막다른 길이다")
    # 메뉴 링크는 LINKS 배열 **그대로**를 다시 돈다(목록이 두 곳에 살면
    # 언젠가 갈라진다) — 두 번째 순회 루프가 있는지 확인.
    assert "LINKS[k][0]" in nav_js, "메뉴가 LINKS 배열을 재사용하지 않는다"

    idx = (DOCS / "index.html").read_text("utf-8")
    assert 'class="burger"' in idx and 'class="mnav"' in idx, (
        "홈 바에 삼단 바가 없다")
    assert ".burger{display:inline-flex}" in idx, (
        "홈의 모바일 화면에서 삼단 바가 안 보인다")
    # 홈의 모바일 메뉴는 홈 바 링크와 글자까지 같아야 한다(같은 사실 한 곳).
    home = _index_nav_links()
    menu = re.findall(r'<a class="mlnk" href="([^"]+)">([^<]+)</a>', idx)
    assert [(h, l.strip()) for h, l in menu] == \
        [(h, l.strip()) for h, l in home], (
        f"홈의 모바일 메뉴가 상단 바와 다르다: {menu} != {home}")


def test_no_page_wears_two_bars():
    """옛 미니 nav가 남아 있으면 바가 두 줄이 된다 — 한 페이지 한 바."""
    for name in WEARERS:
        src = (DOCS / name).read_text("utf-8")
        assert "<nav" not in src, (
            f"{name}에 옛 nav가 남아 있다 — 공용 바와 이중이 된다")


# ── 대시보드로 가는 문 (2026-08-25 사장님 지시) ─────────────────

def test_both_bars_have_a_door_to_the_dashboard():
    """운영 설정 화면으로 가는 버튼이 홈 바와 공용 바 **양쪽**에 있다.

    사장님: "대시보드로 갈 수 있는 버튼도 홈페이지에 넣어줘."
    그 전까지 admin.html은 주소를 외우는 사람만 갈 수 있었다.
    """
    idx = (DOCS / "index.html").read_text("utf-8")
    nav_js = (DOCS / "assets" / "nav.js").read_text("utf-8")
    assert 'class="navdash" href="admin.html"' in idx, "홈 바에 대시보드 문이 없다"
    assert "대시보드" in idx, "홈 바의 대시보드 버튼에 이름이 없다"
    assert 'var ADMIN = "admin.html"' in nav_js, "공용 바에 대시보드 주소가 없다"
    assert "qn-dash" in nav_js, "공용 바에 대시보드 문이 없다"


def test_the_dashboard_door_is_reachable_on_a_phone():
    """모바일에서도 닿아야 한다 — 지시가 "모바일 기준으로도"였다.

    ⚠️ 대조군의 반대 실수를 막는다: 좁은 화면에서 버튼을 **바에서 숨기기만**
       하면 그건 정리가 아니라 차단이다(감사 314일자 삼단 바에서 배운 것).
       숨기는 CSS가 있으면 삼단 바 메뉴 안에 대체 문이 반드시 있어야 한다.
    """
    idx = (DOCS / "index.html").read_text("utf-8")
    nav_js = (DOCS / "assets" / "nav.js").read_text("utf-8")

    assert "@media(max-width:820px){.navdash{display:none}}" in idx, (
        "홈: 좁은 화면에서 대시보드 버튼이 바를 밀어낸다")
    assert 'class="mdash" href="admin.html"' in idx, (
        "홈: 바에서 숨겼는데 삼단 바 메뉴에 대체 문이 없다 — 막다른 길이다")

    assert "@media(max-width:820px){#qnav .qn-dash{display:none}}" in nav_js, (
        "공용 바: 좁은 화면에서 대시보드 버튼이 바를 밀어낸다")
    assert "qn-mdash" in nav_js, (
        "공용 바: 바에서 숨겼는데 삼단 바 메뉴에 대체 문이 없다")


def test_the_dashboard_door_says_it_needs_a_login():
    """문에 "아무나 들어가도 되는 곳"이라고 적지 않는다.

    로그인은 Cloudflare 시크릿(ADMIN_ID/ADMIN_PW)이 있을 때만 켜진다 —
    worker.js가 서버에서 검사한다. 그 사실이 어드민 페이지에 적혀 있어야
    한다. 안 적으면 시크릿이 없는 상태를 '보호되고 있다'로 읽는다.
    """
    idx = (DOCS / "index.html").read_text("utf-8")
    assert "로그인 필요" in idx, "홈의 대시보드 버튼이 로그인 필요를 안 알린다"
    worker = (ROOT / "worker.js").read_text("utf-8")
    assert "ADMIN_ID" in worker and "ADMIN_PW" in worker, (
        "서버에 어드민 로그인 관문이 없다")
    admin = (DOCS / "admin.html").read_text("utf-8")
    assert "ADMIN_ID / ADMIN_PW" in admin, (
        "어드민 페이지가 로그인을 어떻게 켜는지 안 적는다")
