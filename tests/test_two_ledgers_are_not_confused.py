"""두 종류의 계좌를 **읽는 사람이 구별할 수 있는가** (감사 107).

이 실험에는 계좌가 두 종류 있다.

    통합 계좌   8만원 하나            ← 8마일 챌린지 본체. 이게 실험이다.
    종목 계좌   1만원 × 20개 = 20만원  ← "이 종목만 굴렸다면?" 참고 지표

그런데 `paper.html`의 표는 종목 계좌의 자산·일간·누적·최대낙폭·비중을
아무 설명 없이 '종목별 현황'으로 보여줬다. 8만원짜리 실험 페이지에
합계 20만원이 그대로 보인 셈이다.

**이 프로젝트를 만든 사람이 직접 물었다**:

    "8만원으로 투자했는데 종목별로 보니까 8만원이 넘어가는데..? 어떻게 된거지?"

만든 사람이 헷갈리면 읽는 사람은 반드시 헷갈린다. 그리고 이 사이트의
유일한 자산은 "숫자를 있는 그대로 보여준다"는 신뢰다 — 숫자가 맞아도
**무엇의 숫자인지 모르면 거짓말과 같은 효과**를 낸다.

감사 91·92·100과 같은 계열의 마지막 조각이다: 닮은 숫자를 같은 이름으로
불렀다. 여기서는 이름을 나누고, 합계를 **먼저** 밝힌다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAPER = (ROOT / "docs" / "paper.html").read_text("utf-8")


def _table_head() -> list[str]:
    m = re.search(r'<tr><th style="text-align:left">종목</th>(.*?)</tr>', PAPER, re.S)
    assert m, "종목별 표의 머리글을 찾지 못했다 — 검사가 낡았다"
    return [re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<th[^>]*>.*?</th>", m.group(1), re.S)]


def test_the_section_is_not_called_just_current_status():
    """'종목별 현황'은 통합 계좌의 현황처럼 읽힌다.

    ⚠️ 문서 어딘가에 그 문구가 있는지만 보면 안 된다 — 첫 문단 안내에도
       같은 말이 있어서, **표 제목만 되돌려도** 검사가 통과했다(변이 시험이
       잡았다). 표를 만드는 그 자리를 본다.
    """
    # 종목 표를 만드는 그 줄(`const tbl=`)의 카드 제목만 본다.
    seg = PAPER.split("const tbl=", 1)[1][:400]
    m = re.search(r'<div class="card"><h2>([^<]+)', seg)
    assert m, "표 카드 제목을 찾지 못했다 — 검사가 낡았다"
    title = m.group(1).strip()
    assert "참고" in title, (
        f"표 제목이 '{title}'이라 어느 계좌의 것인지 알 수 없다")


def test_the_columns_say_which_account_they_belong_to():
    cells = _table_head()
    assert not any(c == "자산" for c in cells), f"'자산'만으로는 모른다: {cells}"
    assert not any(c == "비중" for c in cells), f"'비중'만으로는 모른다: {cells}"
    assert any("참고계좌" in c for c in cells), cells


def test_the_page_states_the_total_before_the_table():
    """합계를 먼저 밝힌다 — 독자가 스스로 더해 보고 놀라기 전에."""
    assert "합치면" in PAPER, "20개를 합치면 얼마인지 말하지 않는다"
    assert "별개의 장부" in PAPER or "별개의" in PAPER


def test_the_total_is_computed_not_written_in_prose():
    """합계를 산문에 박으면 종목이 늘 때 조용히 거짓말이 된다."""
    assert "symEq" in PAPER, "합계를 장부에서 계산하지 않는다"
    # 주석은 뺀다 — '왜 이렇게 했나'의 기록이지 화면에 나가는 글이 아니다.
    shown = re.sub(r"/\*(?:.|\n)*?\*/", "", PAPER)
    assert not re.search(r"20만\s*원", shown), "합계가 산문에 박혀 있다"


def test_the_lead_paragraph_warns_before_the_reader_scrolls():
    """표까지 내려가기 전에 첫 문단에서 한 번 말한다."""
    lead = PAPER.split('<div id="content">', 1)[0]
    assert "별개의" in lead and "1만원" in lead, (
        "첫 문단이 두 계좌의 차이를 말하지 않는다 — 표까지 내려가야 알게 된다")


def test_the_headline_start_cash_is_still_the_portfolio_one():
    """혼동을 없애려다 8만원 주장까지 흐리면 안 된다."""
    assert "80,000원" in PAPER


def test_the_symbol_start_cash_is_not_hardcoded_wrongly():
    """참고 계좌 시작금은 코드의 START_CASH와 같아야 한다."""
    from quant.live.ledger_basics import START_CASH
    assert f"won({int(START_CASH)})" in PAPER, (
        "참고 계좌 시작금을 코드에서 읽지 않는다")
