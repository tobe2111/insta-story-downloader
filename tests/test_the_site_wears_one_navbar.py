"""모든 공개 페이지가 **같은 상단 바 한 벌**을 쓰는가 (2026-08-18 → 08-26).

사장님 요청(2026-08-18): "홈페이지에 있는 바가 모든 페이지에서 보이게 해줘."
사장님 지적(2026-08-26): *"상단바도 페이지마다 구성이 다르고 일치시켜줘."*

첫 지시 때는 홈의 바를 **원본**으로 두고 나머지 페이지에 공용 바를 얹었다.
그래서 구현이 두 벌이 됐다 — 홈은 손으로 쓴 ``<nav>``, 나머지 아홉은
``docs/assets/nav.js``. 링크 **목록**은 이 검사가 맞춰 줬지만 마크업과 CSS는
따로 살아서, 간격·활성 표시·버전 배지가 페이지마다 달랐다. 사장님이 보신
그 차이다. 같은 것을 두 곳에 적으면 언젠가 갈라진다(FROZEN_IDEAS ①) —
상단 바에만 그 원칙이 예외였던 셈이다.

그래서 홈의 손수 바를 지우고 **홈도 공용 바를 싣는다.** 이 검사가 지키는 것:

    ① 홈에 손수 만든 바가 **다시 생기지 않는다.** 구현은 한 벌뿐이다.
    ② 모든 공개 페이지(홈 포함)가 공용 바를 실제로 싣는다.
    ③ 공용 바가 갖춰야 할 것(다운로드·대시보드·언어·삼단 바)이 그대로다.

실제로 그려지는가(스크립트 오류·404)는
``test_every_public_page_actually_renders.py``가 진짜 브라우저로 본다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 공용 바를 실어야 하는 페이지 — **홈이 맨 앞에 있다**(2026-08-26부터).
# index-standalone은 단일 파일 배포본(외부 스크립트 금지), sns_card는 사람이
# 보는 페이지가 아니라 SNS 카드 그리기용 캔버스, 404는 가운데 정렬 한 장짜리
# 안내문이라 바를 얹지 않는다.
# ⚠️ 트랙 페이지 셋(us·futures)과 머신러닝 페이지는 나중에 생겼는데 이
#    목록에 안 들어와 있었다 — **바를 싣는지 아무도 확인하지 않는 페이지**가
#    셋 있었다는 뜻이다(감사 317). 페이지를 늘릴 때 여기도 늘려야 한다.
WEARERS = ["index.html", "paper.html", "today.html", "trust.html",
           "intraday.html", "us.html", "futures.html", "ml.html",
           "weekly.html", "admin.html"]

NAV_JS = (DOCS / "assets" / "nav.js").read_text("utf-8")


def _shared_links() -> list[tuple[str, str]]:
    return [(h, l.strip())
            for h, l in re.findall(r'\["([\w.\-]+)", "([^"]+)"\]', NAV_JS)]


def test_every_public_page_wears_the_shared_bar():
    for name in WEARERS:
        src = (DOCS / name).read_text("utf-8")
        assert 'src="assets/nav.js"' in src, f"{name}이 공용 바를 싣지 않는다"


def test_no_page_carries_a_hand_written_bar():
    """옛 미니 nav가 남아 있으면 바가 두 줄이 되거나 모양이 갈라진다.

    ⚠️ 홈이 이 검사에 **2026-08-26에야** 들어왔다. 그전까지 홈은 "원본"이라는
       이름으로 면제였고, 그 면제가 곧 사장님이 보신 불일치였다. 면제가
       하나 있으면 계약은 그 하나만큼 거짓이 된다.
    """
    for name in WEARERS:
        src = (DOCS / name).read_text("utf-8")
        assert "<nav" not in src, (
            f"{name}에 손수 만든 nav가 있다 — 바는 공용 한 벌뿐이어야 한다")


def test_the_home_does_not_keep_a_private_copy_of_the_bar():
    """대조군 — 마크업만 지우고 CSS·스크립트를 남기면 언젠가 되살아난다.

    홈에 남은 ``.navdash``/``.mnav``/``.burger`` 같은 규칙은 이제 아무것도
    꾸미지 않는 죽은 CSS이고, 다음 사람에게는 "여기에 바가 있(었)다"는
    잘못된 신호다.
    """
    idx = (DOCS / "index.html").read_text("utf-8")
    for dead in ('class="lnk"', 'class="mlnk"', ".navdash", ".navcta",
                 ".navver", ".mnav", "id=\"navver\""):
        assert dead not in idx, (
            f"홈에 옛 바의 흔적이 남아 있다: {dead}")


def test_the_shared_bar_lists_every_track():
    """네 트랙이 나란히, 같은 자리에 있어야 한다.

    2026-08-22 사장님: "100만원 투자 1페이지, 코인투자 1페이지, 선물투자
    1페이지, 미국주식 1페이지 이렇게 나누자고. 지금은 막 섞여있어."
    계좌가 넷이면 첫 줄에서 넷이 다 보여야 한다.
    """
    links = _shared_links()
    hrefs = [h for h, _ in links]
    for page in ("index.html", "intraday.html", "us.html", "futures.html"):
        assert page in hrefs, f"공용 바에 트랙이 빠졌다: {page}"
    assert len(links) >= 5, f"공용 바의 링크가 이상하게 적다: {links}"
    # 트랙 넷이 **앞쪽에 모여** 있어야 한다 — 사이에 다른 것이 끼면
    # "나란히 둔다"는 지시가 무너진다.
    idxs = [hrefs.index(p) for p in
            ("index.html", "intraday.html", "us.html", "futures.html")]
    assert idxs == sorted(idxs) and max(idxs) - min(idxs) == 3, (
        f"트랙 넷이 나란히 있지 않다: {hrefs}")


def test_the_shared_bar_keeps_the_download_button():
    url = "https://github.com/tobe2111/insta-story-downloader/releases/latest"
    assert url in NAV_JS, "공용 바에 다운로드 버튼이 없다"
    assert "무료 다운로드" in NAV_JS, "다운로드 버튼에 이름이 없다"


def test_mobile_gets_a_menu_not_a_dead_end():
    """모바일(≤820px)은 링크를 숨기는 대신 삼단 바 메뉴를 연다.

    2026-08-23 사장님: "모바일로 보면 다른 페이지를 볼 수가 없어."
    그 전까지는 820px 아래에서 링크를 display:none으로 숨기기만 했다 —
    숨긴 자리에 대체 수단이 없으면 그건 정리가 아니라 차단이다.
    """
    assert "qn-burger" in NAV_JS and "qn-menu" in NAV_JS, "공용 바에 삼단 바가 없다"
    assert "#qnav .qn-burger{display:none" in NAV_JS, (
        "삼단 바가 데스크톱에도 보인다")
    assert "#qnav .qn-burger{display:inline-flex}" in NAV_JS, (
        "모바일에서 삼단 바가 안 보인다 — 다시 막다른 길이다")
    # 메뉴 링크는 LINKS 배열 **그대로**를 다시 돈다(목록이 두 곳에 살면
    # 언젠가 갈라진다) — 두 번째 순회 루프가 있는지 확인.
    assert "LINKS[k][0]" in NAV_JS, "메뉴가 LINKS 배열을 재사용하지 않는다"


def test_the_bar_offers_the_other_language():
    """영어 토글은 좁은 화면에서도 남는다 — 글자 두 개라 자리를 거의 안 먹고,
    영어권 방문자가 첫 화면에서 못 찾으면 그 사람에게는 한국어 전용 사이트다.
    """
    assert "qn-lang" in NAV_JS, "공용 바에 언어 버튼이 없다"
    assert "data-qn-lang" in NAV_JS, "언어 버튼이 아무 일도 안 한다"


# ── 대시보드로 가는 문 (2026-08-25 사장님 지시) ─────────────────

def test_the_bar_has_a_door_to_the_dashboard():
    """운영 설정 화면으로 가는 버튼이 바에 있다.

    사장님: "대시보드로 갈 수 있는 버튼도 홈페이지에 넣어줘."
    그 전까지 admin.html은 주소를 외우는 사람만 갈 수 있었다. 바가 한 벌이
    됐으므로 이 문도 한 곳에만 있으면 모든 페이지에 생긴다.
    """
    assert 'var ADMIN = "admin.html"' in NAV_JS, "공용 바에 대시보드 주소가 없다"
    assert "qn-dash" in NAV_JS, "공용 바에 대시보드 문이 없다"
    assert "대시보드" in NAV_JS, "대시보드 버튼에 이름이 없다"


def test_the_dashboard_door_is_reachable_on_a_phone():
    """모바일에서도 닿아야 한다 — 지시가 "모바일 기준으로도"였다.

    ⚠️ 대조군의 반대 실수를 막는다: 좁은 화면에서 버튼을 **바에서 숨기기만**
       하면 그건 정리가 아니라 차단이다(감사 314일자 삼단 바에서 배운 것).
       숨기는 CSS가 있으면 삼단 바 메뉴 안에 대체 문이 반드시 있어야 한다.
    """
    assert "@media(max-width:820px){#qnav .qn-dash{display:none}}" in NAV_JS, (
        "좁은 화면에서 대시보드 버튼이 바를 밀어낸다")
    assert "qn-mdash" in NAV_JS, (
        "바에서 숨겼는데 삼단 바 메뉴에 대체 문이 없다 — 막다른 길이다")


def test_the_dashboard_door_says_it_needs_a_login():
    """문에 "아무나 들어가도 되는 곳"이라고 적지 않는다.

    로그인은 Cloudflare 시크릿(ADMIN_ID/ADMIN_PW)이 있을 때만 켜진다 —
    worker.js가 서버에서 검사한다. 그 사실이 어드민 페이지에 적혀 있어야
    한다. 안 적으면 시크릿이 없는 상태를 '보호되고 있다'로 읽는다.
    """
    assert "운영 설정(로그인 필요)" in NAV_JS, (
        "대시보드 버튼이 로그인 필요를 안 알린다")
    worker = (ROOT / "worker.js").read_text("utf-8")
    assert "ADMIN_ID" in worker and "ADMIN_PW" in worker, (
        "서버에 어드민 로그인 관문이 없다")
    admin = (DOCS / "admin.html").read_text("utf-8")
    assert "ADMIN_ID / ADMIN_PW" in admin, (
        "어드민 페이지가 로그인을 어떻게 켜는지 안 적는다")
