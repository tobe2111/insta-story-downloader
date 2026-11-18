"""네 페이지가 같은 모양으로 시작한다 (2026-11-18).

사장님: "이 4개 페이지 모두 좀 일관성이 있어야하지 않겠어? … 지금 모두 다 무슨
말을 하는지도 모르겠고"

지키는 것:
1. 트랙 페이지 셋(코인 단타 · 미국 단타 · 코인 선물)은 제목 바로 다음이 '한눈에'
   카드(assets/glance.js)다 — 다른 설명이 그 앞에 끼지 않는다.
2. 그 아래 보이는 칸의 순서가 같다: 지금 들고 있는 것 → 종목별 손익 → 자산 곡선.
   최근 체결과 실험 세부는 '자세히 보기'(.adv) 안에 있고(2026-11-18 "필요이상의
   TMI"), 정직한 한계는 언제나 보인다.
3. 100만 챌린지의 '한눈에'도 같은 두 줄(기계가 고른 방식 · 다음 공식 판정)을 싣는다.
4. glance.js의 한국어 조각은 전부 영어 사전에 있다(트랙 페이지는 완역 대상이다).
"""
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
TRACKS = {"intraday.html": "intraday.json", "us.html": "intraday_us.json",
          "futures.html": "futures.json"}
ORDER = ["지금 들고 있는 것", "종목별 손익", "자산 곡선"]


def _visible_h2(html: str) -> list[str]:
    """'자세히 보기'(.adv) 밖에 있는 h2 제목들 — 위에서부터.

    `.adv` 묶음은 여러 개일 수 있고 안에 div가 겹쳐 있으므로 깊이를 세어 닫는다."""
    out, i = [], 0
    while True:
        a = html.find('<div class="adv">', i)
        seg = html[i:] if a < 0 else html[i:a]
        out += [re.sub(r"<[^>]+>", "", m).strip()
                for m in re.findall(r"<h2>(.*?)</h2>", seg)]
        if a < 0:
            return out
        depth, k = 0, a
        for m in re.finditer(r"<div\b|</div>", html[a:]):
            depth += 1 if m.group(0) != "</div>" else -1
            if depth == 0:
                k = a + m.end()
                break
        i = k


def test_track_pages_open_with_the_glance_card():
    for page, src in TRACKS.items():
        html = (DOCS / page).read_text("utf-8")
        h1 = html.index("<h1>")
        glance = html.index(f'data-glance="{src}"')
        first_h2 = html.index("<h2>", h1)
        # 제목 끝 ~ 한눈에 카드의 여는 태그 사이: 주석 말고는 아무것도 없어야 한다.
        between = html[html.index("</h1>", h1) + 5:html.rfind("<div", 0, glance)]
        between = re.sub(r"<!--.*?-->", "", between, flags=re.S).strip()
        assert glance < first_h2, page
        assert between == "", f"{page}: 한눈에 카드 앞에 다른 내용이 끼었다: {between[:80]}"
        assert "assets/glance.js" in html, page


def test_visible_sections_follow_the_same_order():
    for page in TRACKS:
        titles = _visible_h2((DOCS / page).read_text("utf-8"))
        seen = [t for t in titles if any(t.startswith(o) for o in ORDER)]  # 페이지 순서 그대로
        idx = [next(i for i, o in enumerate(ORDER) if t.startswith(o)) for t in seen]
        assert idx == sorted(idx), f"{page}: 순서가 다르다 {seen}"
        assert titles[-1].startswith("정직한 한계"), f"{page}: 정직한 한계가 마지막에 안 보인다"
        assert "최근 체결" not in titles, f"{page}: 체결 표는 '자세히 보기' 안에 있어야 한다"
        assert {"종목별 손익", "자산 곡선"} <= {
            o for o in ORDER for t in titles if t.startswith(o)}, page


def test_the_main_page_glance_answers_the_same_two_questions():
    html = (DOCS / "index.html").read_text("utf-8")
    for label in ("기계가 고른 방식", "다음 공식 판정"):
        assert label in html


def test_every_korean_piece_of_the_glance_card_has_english():
    src = (DOCS / "assets" / "glance.js").read_text("utf-8")
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    pieces = set(re.findall(r'"([^"]*[가-힣][^"]*)"', code))
    dic = (DOCS / "assets" / "i18n-en.js").read_text("utf-8")
    missing = sorted(p for p in pieces if f'"{p}":' not in dic)
    assert not missing, f"영어 사전에 없다: {missing}"
