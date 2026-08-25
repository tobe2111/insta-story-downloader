"""종목 상세 창 — **두 출처를 한 창에 놓되 섞지 않는다** (2026-08-14).

종목을 누르면 창이 열리고 위에는 우리 장부, 아래에는 트레이딩뷰의 거래소
차트가 나온다. 여기서 지켜야 할 것이 이 사이트의 계약이다:

    "화면에 보이는 것 = 장부에 있는 것"

트레이딩뷰는 **다른 출처**다. 같은 종목이라도 값이 미세하게 다를 수 있고,
저희 체결가·진입가·보유는 거기 없다. 그래서

  · 장부 숫자는 **표에서 그대로 옮긴다** — 창이 자기 계산을 시작하면 두
    표가 갈라진다(감사 197이 그 사고였다)
  · 어느 쪽이 무엇인지 **화면에 적는다** — 안 적으면 사람은 둘을 같은
    출처로 읽는다
  · 매핑이 없는 종목에는 **차트를 지어내지 않는다** — "삼성전자"라고
    써 놓고 다른 회사를 보여주는 것은 UI 버그가 아니라 가짜를 진짜처럼
    보여주는 사고다

⚠️ 외부 스크립트를 쓰지 않는다. 트레이딩뷰가 권하는 방식은 그쪽 자바스크립트를
   우리 문서에 넣는 것인데, 이 사이트는 공개 장부다 — 숫자를 보여주는 화면에
   제3자 코드를 들이지 않는다. iframe은 경계가 있고, 트레이딩뷰가 죽어도 그
   칸만 빈다.

심볼 변환 자체는 `tests/tv_symbols_check.mjs`가 **실행해서** 20종목을 값으로
확인한다(소스 문자열만 읽는 검사는 "검사는 초록인데 기능은 죽어 있다"를
못 잡는다 — 감사 229).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
IDX = (ROOT / "docs" / "index.html").read_text("utf-8")
TV = (ROOT / "docs" / "assets" / "tv-symbols.js").read_text("utf-8")


def _visible(html: str) -> str:
    h = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    h = re.sub(r'title="[^"]*"', " ", h)
    return re.sub(r"<[^>]+>", " ", h)


# ── 배선 ──────────────────────────────────────────────────────

def test_the_rows_carry_the_symbol_key():
    """줄에 키가 없으면 눌러도 무엇을 열지 모른다."""
    assert 'data-k="\'+esc(r.k)+\'"' in IDX


def test_the_dialog_exists_and_is_wired():
    assert '<dialog id="symdlg">' in IDX
    assert 'getElementById("symtable")' in IDX
    assert 'tbody tr[data-k]' in IDX


def test_the_mapping_module_is_loaded():
    assert 'src="assets/tv-symbols.js"' in IDX


# ── 두 출처를 구분해 말하는가 ─────────────────────────────────

def test_the_page_says_which_half_is_the_ledger():
    v = _visible(IDX)
    assert "여기까지가" in v and "장부" in v, (
        "장부 구간이 어디까지인지 화면이 말하지 않는다")


def test_the_page_says_the_chart_is_someone_elses_data():
    v = _visible(IDX)
    assert "거래소 공개 데이터" in v
    assert "출처가 다르므로" in v, "값이 다를 수 있다는 사실을 안 적었다"


def test_the_page_says_the_numbers_come_from_the_ledger_only():
    assert "매매·수익률은 위 장부에서만 나옵니다." in IDX


def test_tradingview_is_credited():
    """무료 위젯의 조건이자, 출처를 밝히는 것이 이 사이트의 방식이다."""
    assert "tradingview.com" in IDX
    assert "차트 제공" in _visible(IDX)


# ── 창이 스스로 계산하지 않는가 ───────────────────────────────

def test_the_dialog_copies_the_row_it_does_not_recompute():
    """감사 197 — 화면이 자기 계산을 시작하면 두 표가 갈라진다."""
    i = IDX.index('function openSymbol(tr)')
    body = IDX[i:i + 2000]
    # ⚠️ 예전에는 `cells[i].innerText`(칸 번호)를 요구했다. 그러면 이 창은
    #    종목표 한 곳에서만 맞고, 잔고·거래내역에서 열면 엉뚱한 칸을 읽는다.
    #    지금은 **그 표의 머리글을 읽어** 짝지운다(감사 274) — 여전히 표의
    #    값을 그대로 옮길 뿐, 다시 계산하지는 않는다. 실제로 세 표에서
    #    열어 보는 것은 tests/test_the_first_screen_answers_the_first_question.py.
    assert "td.innerText" in body, "표의 값을 그대로 옮기지 않는다"
    assert "thead th" in body, "표의 머리글이 아니라 칸 번호로 집는다"
    for forbidden in ("*100", "toFixed(", "Number("):
        assert forbidden not in body, (
            f"창 안에서 다시 계산한다({forbidden}) — 표와 갈라진다")


# ── 남의 코드를 우리 문서에 들이지 않는가 ─────────────────────

def test_no_third_party_script_tag():
    """트레이딩뷰 스크립트를 <script src>로 넣으면 안 된다."""
    for host in ("s3.tradingview.com", "external-embedding"):
        assert host not in IDX, f"{host} 스크립트를 페이지에 넣었다"
    assert re.search(r'<script[^>]+src="https?://', IDX) is None, (
        "외부 스크립트를 직접 불러온다 — 공개 장부 화면에 제3자 코드를 "
        "들이지 않는다")


def test_the_chart_is_a_sandboxed_iframe():
    assert 'sandbox="allow-scripts allow-same-origin allow-popups"' in IDX
    assert 'referrerpolicy="no-referrer"' in IDX
    assert 'loading="lazy"' in IDX


def test_the_chart_is_torn_down_on_close():
    """닫아도 남아 있으면 배경에서 계속 돈다(데이터·배터리)."""
    assert 'dlg.addEventListener("close"' in IDX
    assert 'getElementById("dlg-chart").innerHTML=""' in IDX


# ── 모르면 지어내지 않는가 ────────────────────────────────────

def test_an_unmapped_symbol_shows_nothing_rather_than_something_wrong():
    v = _visible(IDX)
    assert "엉뚱한 종목이 뜨느니 비워 둡니다" in v


def test_the_mapper_returns_null_for_unknown_markets():
    """변환기 자체의 계약 — 실제 값 확인은 .mjs 하네스가 한다."""
    assert "return null;      // upbit·synthetic 등 — 모르면 안 만든다" in TV


# ── 매핑이 운영 종목을 전부 덮는가 ────────────────────────────

# 지금 **차트를 못 여는 것으로 확인된** 종목들 — 2026-08-25 감사 318.
#
# 2026-08-19에 유니버스 규칙이 20종목 → 45종목으로 넓어지면서 미국 자산군
# ETF 15종이 계좌에 들어왔다. 그런데 차트 변환표는 그때 따라오지 않았고,
# **아무도 몰랐다** — 아래 검사가 옛 고정 목록(AUTO_TARGETS)만 훑고 있었기
# 때문이다. 계좌 잔고 1위(UUP)를 눌러도 차트가 안 뜨는 상태가 엿새째였다.
#
# 왜 지금 안 채우나: 트레이딩뷰는 미국 종목에 **거래소 표기**를 요구하는데
# (AMEX/NASDAQ/NYSE), 이 15종의 상장 거래소를 여기서 확인할 방법이 없다
# (개발 컨테이너는 외부 조회가 막혀 있다). 틀린 거래소를 적으면 차트가
# 아예 안 열리거나 **엉뚱한 종목**이 뜬다 — 비워 두는 것보다 나쁘다.
# 이 저장소의 규칙 그대로다: **모르면 지어내지 않는다.**
#
# 이 목록은 '봐준 것'이 아니라 **적어 둔 빚**이다. 아래 두 번째 검사가
# 목록이 썩지 못하게 막는다 — 매핑을 채우면 여기서도 빼야 한다.
CHART_GAP = {
    "us_stock:GLD", "us_stock:SLV", "us_stock:TLT", "us_stock:IEF",
    "us_stock:LQD", "us_stock:TIP", "us_stock:DBC", "us_stock:XLE",
    "us_stock:XLU", "us_stock:XLP", "us_stock:VNQ", "us_stock:UUP",
    "us_stock:EWJ", "us_stock:VGK", "us_stock:EEM",
}


def _rule_universe() -> list[tuple[str, str]]:
    """규칙이 **고정으로** 넣는 종목들 — 여기 있는 것은 반드시 계좌에 온다.

    시총·거래대금 상위로 매달 갈리는 자리는 미리 알 수 없어 뺀다(그쪽은
    화면이 "연결해 두지 않았습니다"라고 말하는 것으로 정직함을 지킨다).
    """
    from quant import universe as U
    out = [("crypto", s) for s in U.CRYPTO_CORE]
    out += [("kr_stock", s) for s in U.KR_CORE + U.KR_ASSET_CORE]
    out += [("us_stock", s) for s in U.US_CORE + U.US_ASSET_CORE]
    return out


def _unmapped(pairs) -> list[str]:
    us = set(re.findall(r"^\s+(\w+): \"(?:NASDAQ|AMEX|NYSE)\",", TV, re.M))
    missing = []
    for market, symbol in pairs:
        if market == "crypto":
            ok = "/" in symbol
        elif market == "us_stock":
            ok = symbol in us
        elif market == "kr_stock":
            ok = bool(re.match(r"^\d{6}\.(KS|KQ)$", symbol))
        else:
            ok = False
        if not ok:
            missing.append(f"{market}:{symbol}")
    return missing


def test_every_traded_symbol_has_a_tradingview_mapping():
    """**아는 것만 세지 않는다** — 규칙이 고정으로 넣는 종목 전부를 훑는다.

    ⚠️ 예전 판은 `quant.markets.AUTO_TARGETS`(2026-08-19 이전의 고정 20종목)
       를 훑었다. 그 뒤 유니버스 규칙이 45종목으로 넓어졌는데 이 검사는
       옛 목록을 계속 보고 있었고, **계좌에 실제로 들어온 15종의 차트가
       빠진 것을 한 번도 알려주지 않았다.** 감사 296과 같은 모양이다 —
       규칙이 넓어졌는데 따라오지 않은 것이 또 있었다.
    """
    missing = set(_unmapped(_rule_universe())) - CHART_GAP
    assert not missing, (
        f"트레이딩뷰 매핑이 없는 운영 종목: {sorted(missing)} — "
        "docs/assets/tv-symbols.js의 US_EXCHANGE에 상장 거래소를 "
        "**확인해서** 넣으세요(추측 금지). 확인할 수 없으면 CHART_GAP에 "
        "사유와 함께 적으세요.")


def test_the_known_gap_does_not_rot():
    """빚 목록이 **낡지 않게** — 다 갚았으면 목록에서 빠져야 한다.

    적어 둔 빚이 그대로 남아 있으면 다음 사람은 그것을 '원래 그런 것'으로
    읽는다. 매핑을 채우고도 여기 남겨 두면 이 검사가 알려준다.
    """
    still = set(_unmapped([tuple(k.split(":", 1)) for k in CHART_GAP]))
    healed = CHART_GAP - still
    assert not healed, (
        f"이제 차트가 열리는데 아직 '빚' 목록에 남아 있다: {sorted(healed)} — "
        "CHART_GAP에서 빼세요")


def test_the_site_tells_the_reader_when_a_chart_is_missing():
    """빚이 있는 동안 화면은 **왜 비었는지** 말해야 한다.

    빈 칸만 남기면 읽는 사람은 그것을 '고장'으로 읽는다.
    """
    v = _visible(IDX)
    assert "트레이딩뷰 차트를 연결해" in v and "비워 둡니다" in v


def test_the_node_harness_covers_the_same_count():
    """하네스가 20종목을 다 적어 뒀는지 — 목록이 늘면 거기도 늘어야 한다."""
    from quant.markets import AUTO_TARGETS

    harness = (ROOT / "tests" / "tv_symbols_check.mjs").read_text("utf-8")
    for market, symbol in AUTO_TARGETS:
        assert f'"{market}:{symbol}"' in harness, (
            f"{market}:{symbol}가 실행 검사에 없다")
