"""화면은 **코드의 말이 아니라 사람의 말**로 적는다 (2026-08-26).

사장님: *"내용들이 무슨 말인지 모르겠어 어려워."*

실측(브라우저로 띄워 본문을 읽어 보고 찾은 것):

    · 실기록 페이지의 통합 계좌 카드 제목이 **`portfolio:ALL`** 이었다 —
      코드가 계좌를 부르는 이름이지 사람이 읽을 이름이 아니다.
    · 지표 이름이 "실력 지표 (시간가중 TWR)", "전략 − 보유 (초과성과)"처럼
      **용어부터** 나왔다. 뜻을 모르면 숫자도 못 읽는다.
    · 종목 이름표가 2026-08-19 확장분 스물두 종목에 없어 "UUP", "XLE",
      "132030.KS"가 그대로 나왔다(그 구멍은
      tests/test_the_universe_says_what_it_is.py가 막는다).

이 저장소의 독자 규약은 CLAUDE.md에 적혀 있다 — **비개발자가 읽는다.**
용어를 지우라는 뜻이 아니라, 처음 나오는 자리에서 풀어 쓰고 원 용어는
괄호나 툴팁으로 남기라는 뜻이다(문서·코드와 이어져야 하니까).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 사람이 읽는 공개 페이지. sns_card는 카드 그리기용 캔버스, index-standalone은
# 단일 파일 배포본, 404는 한 줄 안내문이라 뺀다.
PAGES = ["index.html", "paper.html", "today.html", "weekly.html",
         "intraday.html", "us.html", "futures.html", "ml.html", "trust.html"]


def _visible(html: str) -> str:
    """주석·툴팁·속성을 뺀, 화면에 실제로 뜨는 글자에 가깝게."""
    h = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    h = re.sub(r'title="[^"]*"', " ", h)
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    return re.sub(r"<[^>]+>", " ", h)


def test_no_page_prints_an_internal_account_key():
    """`portfolio:ALL`·`us_stock:UUP` 같은 내부 키를 제목으로 찍지 않는다.

    이런 키는 파일 안에서 계좌를 구분하려고 쓰는 이름이다. 화면에 나오면
    읽는 사람은 그게 종목 이름인지 오류 메시지인지 알 수 없다.
    """
    bad = []
    for name in PAGES:
        src = (DOCS / name).read_text("utf-8")
        # 템플릿이 키를 **그대로** 제목에 꽂는 자리 — 이게 사고의 모양이다.
        if "<h2>${esc(k)}</h2>" in src:
            bad.append(f"{name}: 카드 제목에 내부 키를 그대로 찍는다")
        # 화면 글자에 하드코딩된 내부 키가 있으면 그것도 사고다.
        for m in re.findall(r"portfolio:[A-Z_]+", _visible(src)):
            bad.append(f"{name}: 화면에 {m}")
    assert not bad, "내부 키가 화면에 나온다: " + " / ".join(bad)


def test_the_combined_account_card_is_called_by_its_human_name():
    """대조군 — 위 검사는 **템플릿의 모양**만 본다.

    ``const title = isPf ? k`` 처럼 변수 한 칸만 바꿔도 제목은 다시
    `portfolio:ALL`이 되는데, 위 검사는 초록이었다(변이 시험이 그 자리를
    찔러 잡았다). 그래서 사람이 읽을 이름이 소스에 **실제로 적혀 있는지**를
    따로 확인한다.
    """
    src = (DOCS / "paper.html").read_text("utf-8")
    assert '"통합 계좌 (100만 챌린지)"' in src, (
        "통합 계좌 카드가 사람이 읽을 이름을 안 갖고 있다 — 내부 키가 "
        "제목으로 돌아갈 자리다")
    # 종목 계좌는 이름표에서 이름을 가져오되, 없으면 시장 접두어를 뗀
    # 종목 코드를 쓴다(내부 키를 통째로 찍지 않는다).
    assert "(st.symbols||{})[k]||{}).name" in src, (
        "종목 계좌 제목이 이름표를 안 본다")


def test_the_deep_metrics_lead_with_meaning_not_the_term():
    """실기록 페이지의 지표 이름은 뜻이 먼저 나와야 한다.

    용어를 지우라는 것이 아니다 — 라벨은 뜻으로 쓰고, 원 용어는 툴팁에
    남긴다(문서·코드와 이어져야 하고, 이미 아는 사람도 있다).
    """
    src = (DOCS / "paper.html").read_text("utf-8")
    for term in ("실력 지표 (시간가중 TWR)", "무작위 전략 1,000개 대비",
                 "진화 없이 고정 전략이었다면", "전략 − 보유 (초과성과)"):
        assert term not in src, f"지표 이름이 아직 용어부터 나온다: {term}"
    for plain in ("돈을 넣은 효과를 뺀 수익률", "아무렇게나 매매한 1,000명 중 순위",
                  "첫 전략을 안 바꿨다면", "그냥 들고만 있기보다 얼마나"):
        assert plain in src, f"쉬운 이름이 없다: {plain}"


def test_the_terms_are_kept_where_they_can_be_looked_up():
    """대조군 — 용어를 **지우는** 것으로는 통과할 수 없다.

    쉬운 말로 바꾸면서 원 용어를 없애면, 이 숫자가 무엇인지 다른 자료와
    맞춰 볼 길이 사라진다. 이 저장소는 설명을 접은 적은 있어도 지운 적이
    없다 — 툴팁 안에 그대로 남긴다.
    """
    src = (DOCS / "paper.html").read_text("utf-8")
    # ⚠️ '무작위'는 **다른 검사(test_rigor)가 이미 이 페이지에서 찾고 있었다.**
    #    쉬운 말로 바꾸면서 그 단어를 지웠다가 전체 검사에서 빨개졌다 —
    #    내가 세운 이 규칙(원 용어는 남긴다)을 내가 어긴 것을 다른 검사가
    #    잡아 준 셈이다. 그래서 여기 목록에도 넣어 둔다.
    for term in ("시간가중 수익률·TWR", "초과성과·알파",
                 "무작위 전략 1,000개 순열 검정"):
        assert term in src, (
            f"원 용어가 통째로 사라졌다: {term} — 쉬운 말로 바꾸는 것과 "
            "지우는 것은 다르다")
