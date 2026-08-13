"""종목별 현황이 "그래서 얼마" 에 답한다 (사장님 2026-08-13).

배경:
  종목별 현황 표는 비중(%)만 보여줬다. "통합 노출 1.2%"는 읽어도 **얼마를
  넣어 뒀는지**는 알 수 없다. 잔고 표에는 평가금액이 있었지만 그건 통합
  계좌가 무언가를 들고 있을 때만 나타나는 별도 카드라, 종목표를 보던
  사람은 계속 답을 못 얻는다.

  같은 날 두 번째 질문 — "실시간으로 반영되는거야? 얼마에 한번씩?" — 도
  같은 성질이다. 답은 툴팁에만 있었다. **물어봐야 알 수 있으면 적어 두지
  않은 것과 같다.**

핵심 계약:
  · 종목표의 보유액은 장부(holdings)에서 읽는다 — 화면이 다시 계산하지
    않는다. 두 표가 각자 계산하면 언젠가 다른 값을 말한다(감사 197)
  · 안 들고 있는 종목은 0원이 아니라 '—'다
  · 갱신 주기는 툴팁이 아니라 화면 본문에 적혀 있다
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
IDX = (ROOT / "docs" / "index.html").read_text("utf-8")


def _symtable_head() -> str:
    m = re.search(r'<table id="symtable">\s*<thead><tr>(.*?)</tr></thead>',
                  IDX, re.S)
    assert m, "종목별 현황 표를 찾지 못했다"
    return m.group(1)


# ── ① "얼마치" 열이 있고, 장부에서 온다 ──────────────────────


def test_the_table_has_a_money_column_not_only_percentages():
    head = _symtable_head()
    assert "통합 보유" in head, (
        "비중만 있고 금액이 없다 — '그래서 얼마'에 답하지 못한다")
    # 원화임을 밝힌다 — 현재가 열은 현지 통화라 단위가 섞여 있다
    assert "원화" in head


def test_the_amount_is_read_from_the_ledger_not_recomputed():
    """화면이 수량×현재가를 다시 곱하면 잔고 표와 갈라진다(감사 197).

    그래서 `holdings`(장부가 이미 계산해 실은 값)에서만 읽어야 한다.
    """
    assert "pf.holdings" in IDX, "종목표가 장부의 보유 기록을 읽지 않는다"
    m = re.search(r"const held=\{\};\n(.*?)\n", IDX)
    assert m, "보유 조회 맵(held)이 없다"
    assert "held[h.key]=h" in m.group(1)
    # 종목표 행이 그 맵을 쓴다
    assert "const hd=held[r.k]" in IDX


def test_a_symbol_that_is_not_held_shows_a_dash_not_zero():
    """안 들고 있는 것과 0원어치 들고 있는 것은 다른 사실이다."""
    row = IDX[IDX.find("const hd=held[r.k]"):]
    row = row[:row.find("}).join(")]
    assert '"보유 없음"' not in row          # 문구는 아래에서 따로 본다
    assert "보유 없음" in row and ':"—"' in row, (
        "보유가 없을 때 0원처럼 보이는 값을 찍는다")
    # 오늘 살 예정인 종목은 '보유 없음 + N% 예정'으로, 아무 계획도 없는
    # 종목은 '—'로 — 두 사실을 같은 칸에서 구분한다(감사 217·223과 같은 계열)
    assert "% 예정" in row


def test_the_header_row_and_the_placeholder_span_the_same_columns():
    """열을 늘리고 colspan을 안 고치면 '불러오는 중' 줄이 표를 깨뜨린다."""
    n_cols = len(re.findall(r"<th", _symtable_head()))
    block = IDX[IDX.find('<table id="symtable">'):]
    block = block[:block.find("</table>")]
    spans = {int(x) for x in re.findall(r'colspan="(\d+)"', block)}
    assert spans == {n_cols}, (
        f"열은 {n_cols}개인데 colspan은 {sorted(spans)}이다")
    # 기록이 하나도 없을 때 쓰는 자리표시자도 같은 폭이어야 한다
    empty = re.findall(r"'<tr><td colspan=\"(\d+)\" class=\"sub\">기록 대기 중",
                       IDX)
    assert empty and {int(x) for x in empty} == {n_cols}


# ── ② 갱신 주기를 화면에 적는다 ───────────────────────────────


def _visible(html: str) -> str:
    """화면에 실제로 나오는 글자만 남긴다 — 주석과 툴팁을 지운다.

    ⚠️ 이 헬퍼가 왜 있는가: 처음엔 툴팁만 지웠다. 그랬더니 **제가 이 변경을
       왜 했는지 적은 HTML 주석**에 같은 문구가 들어 있어서, 본문 안내를
       통째로 지워도 검사가 초록이었다(변이 시험이 잡아냈다).

       감사 183·199·204·211·212·213·217, `social.py`의 하드코딩 검사에 이어
       **아홉 번째** 같은 함정이다. 규칙은 매번 같다 — 소스를 문자열로 훑지
       말고, 보려는 것만 남기고 파싱한다. 주석은 화면에 나오지 않는다.
    """
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)   # 주석은 화면에 없다
    return re.sub(r'title="[^"]*"', "", html)            # 툴팁은 호버해야 뜬다


def test_the_refresh_cadence_is_written_on_the_page_not_only_in_a_tooltip():
    """툴팁은 마우스를 올려야 보인다 — 폰에서는 아예 안 보인다."""
    sect = IDX[IDX.find('<table id="symtable">'):]
    body = _visible(sect[:sect.find("</section>")])
    assert "하루 한 번 확정" in body, (
        "갱신 주기가 툴팁에만 있다 — 물어봐야 알 수 있으면 적어 두지 않은 것이다")
    assert "실시간이 아닙니다" in body


def test_the_page_says_where_the_live_prices_actually_are():
    """준실시간이 어디에 있고 어디에 안 쓰이는지도 함께 밝힌다."""
    sect = IDX[IDX.find('<table id="symtable">'):]
    sect = _visible(sect[:sect.find("</section>")])
    assert "시세띠" in sect
    assert "체결 즉시" in sect, "코인 스트림의 신선도가 화면에 없다"
    assert "15초" in sect, "주식 갱신 주기가 화면에 없다"
    assert "판단·체결·평가에는 쓰지 않습니다" in sect, (
        "살아 있는 시세가 매매에 쓰이는 것으로 오해될 수 있다")


def test_the_stated_cadence_matches_the_code_that_polls():
    """화면에 적은 주기와 실제 폴링 간격이 같아야 한다.

    ⚠️ 같은 사실을 두 곳에 적으면 언젠가 갈라진다 — 여기서는 문구가
       코드보다 오래 남을 수 있으므로 검사가 둘을 묶는다.
    """
    m = re.search(r"STOCK_MS_OPEN=(\d+)", IDX)
    assert m, "장중 주식 갱신 주기 상수를 찾지 못했다"
    assert f"{int(m.group(1)) // 1000}초 간격" in IDX, (
        "화면에 적은 주식 갱신 주기가 실제 상수와 다르다")
    # 코인은 주기가 아니라 스트림이다 — '초 간격'으로 적으면 거짓말이 된다
    assert "wss://stream.binance.com" in IDX, "코인 스트림이 없다"
    assert not re.search(r"setInterval\(pollCrypto", IDX), (
        "코인이 아직 폴링이다 — 화면은 '체결 즉시'라고 말한다")
