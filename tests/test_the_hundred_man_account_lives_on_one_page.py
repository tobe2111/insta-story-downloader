"""100만 계좌는 **한 페이지**에서 다 읽힌다 (2026-08-26).

사장님: *"오늘의 판단, 주간 아카이브, 실기록(100만) 페이지들은 그냥
메인페이지에 중복 없이 몰아넣으면 되는거 아니야? 분리할 필요가 없잖아."*

맞는 지적이었다. 넷(index·today·weekly·paper)은 전부 **같은 계좌의 다른
화면**이고 같은 파일(status.json) 하나를 읽는다. 2026-08-22에 세운 원칙은
"계좌가 넷이면 페이지도 넷"이었는데, 그 반대편이 안 지켜지고 있었다 —
계좌 하나가 페이지 넷에 흩어져 있었다.

실측(2026-08-26, 브라우저로 네 페이지를 띄워 본문을 비교):

    · today.html의 종목별 판단은 **이미 홈에 더 자세히 있었다** — 홈의
      종목별 현황이 같은 '새벽 판단' 문장에 현재가·누적·적중률까지 붙여
      보여 준다. 페이지가 통째로 중복이었다.
    · weekly.html은 표 둘(12줄)뿐이라 홈으로 옮겼다.
    · paper.html은 종목별 1만원 참고 계좌 42개가 있어 양이 크다 — 홈에
      얹으면 첫 화면이 무너지므로 링크로 남긴다.

그래서 메뉴에서 셋을 뺐다. 이 검사가 지키는 것:

    ① 뺀 화면들이 **홈에서 여전히 닿는다.** 메뉴에서 빼면서 링크까지
       없애면 그건 정리가 아니라 기록 차단이다.
    ② 주간 표가 홈에 **실제로 그려진다**(문구만 넣고 배선을 빠뜨리는 사고).
    ③ 홈이 주간 수익률을 **다시 계산하지 않는다** — 배치가 낸 값을 읽는다.
    ④ SNS 카드 촬영 원본(today.html)은 살아 있다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
IDX = (DOCS / "index.html").read_text("utf-8")
NAV_JS = (DOCS / "assets" / "nav.js").read_text("utf-8")

MERGED = ["today.html", "weekly.html", "paper.html"]


def test_the_merged_pages_left_the_menu():
    """메뉴가 짧아졌는지 — 안 짧아졌으면 합친 것이 아니다."""
    links = re.findall(r'\["([\w.\-]+)", "[^"]+"\]', NAV_JS)
    still = [p for p in MERGED if p in links]
    assert not still, f"합쳤다면서 메뉴에 그대로 있다: {still}"


def test_the_merged_pages_are_still_reachable_from_home():
    """대조군 — 메뉴에서 빼면서 링크까지 없애면 기록을 끊은 것이다.

    이 저장소는 화면을 접은 적은 있어도 지운 적이 없다. 밖에 공유된
    주소가 죽는 것도 같은 종류의 사고다.
    """
    for page in MERGED:
        assert f'href="{page}"' in IDX, (
            f"{page}로 가는 길이 홈에서 사라졌다 — 메뉴에서 뺐으면 본문에 "
            "남겨야 한다(정리와 차단은 다르다)")
        assert (DOCS / page).exists(), f"{page} 파일 자체가 사라졌다"


def test_the_weekly_table_is_actually_wired_on_the_home():
    """문구만 넣고 배선을 빠뜨리면 카드가 영원히 '불러오는 중…'이다."""
    assert 'id="weekly-card"' in IDX, "홈에 주간 카드가 없다"
    assert 'id="weekly-body"' in IDX, "주간 카드에 내용을 넣을 자리가 없다"
    assert 'getElementById("weekly-body")' in IDX, "주간 카드를 아무도 안 채운다"
    assert "st.weekly" in IDX, "홈이 주간 집계를 읽지 않는다"
    assert 'card.style.display=""' in IDX, (
        "채워 놓고 카드를 안 편다 — 기본이 display:none이다")


def test_the_home_reads_the_weekly_numbers_it_does_not_recompute_them():
    """감사 246의 재발 방지 — 같은 판정을 두 곳에서 하면 갈라진다.

    옛 주간 페이지는 자기 복사본으로 주간 수익률을 셌고, 그 복사본은
    "주간 수익률" 칸에 그 주 **마지막 하루치**(day_pct)를 넣고 있었다.
    실측(2026-08-10 주) — 아카이브 +0.02% / 사실 -0.02%. 부호가 반대였다.
    """
    i = IDX.index('getElementById("weekly-body")')
    block = IDX[i:i + 3000]
    assert "day_pct" not in block, (
        "홈이 주간 수익률을 하루치로 다시 세고 있다 — 감사 246의 재발")
    assert "r.return_pct" in block, "배치가 낸 주간 수익률을 안 읽는다"


def test_an_empty_week_does_not_show_a_zero():
    """집계가 없으면 카드를 아예 안 띄운다 — 빈 표는 '수익 0'으로 읽힌다."""
    i = IDX.index('getElementById("weekly-body")')
    block = IDX[i:i + 900]
    assert "if(!wk||!Object.keys(wk).length)return" in block, (
        "주간 집계가 없을 때 빈 카드를 띄운다")


def test_the_weekly_table_calls_symbols_by_name():
    """표 머리글은 종목 코드가 아니라 이름이어야 한다.

    2026-08-19 유니버스 확장 때 이름표(SYMBOL_INFO)를 안 늘려서, 이 표가
    "132030.KS", "UUP", "XLE"를 그대로 찍고 있었다. 이름은 한 곳
    (status.json의 symbols)에서만 오고, 그 한 곳을 채우는 것이
    tests/test_the_universe_says_what_it_is.py의 일이다.
    """
    i = IDX.index('getElementById("weekly-body")')
    block = IDX[i:i + 3000]
    assert 'st.symbols' in block, "주간 표가 이름표를 안 본다"


def test_the_card_source_page_survives_the_merge():
    """today.html은 사람용 페이지이기 전에 **SNS 카드 촬영 원본**이다.

    매일 새벽 배치가 헤드리스 크롬으로 ``today.html?card=1``을 찍어
    card.png를 만든다. 메뉴에서 뺐다고 파일을 지우면 그날부터 SNS 카드가
    조용히 죽는다 — 화면이 아니라 파이프라인이 끊긴다.
    """
    wf = (ROOT / ".github" / "workflows" / "daily-paper.yml").read_text("utf-8")
    assert "today.html?card=1" in wf, "카드 촬영이 today.html을 안 쓴다"
    assert (DOCS / "today.html").exists(), (
        "SNS 카드 촬영 원본이 사라졌다 — 매일 카드가 죽는다")
    assert "?card=1" in (DOCS / "today.html").read_text("utf-8"), (
        "촬영용 카드 모드가 today.html에서 사라졌다")
