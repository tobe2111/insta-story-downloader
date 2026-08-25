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

심볼 변환 자체는 `tests/tv_symbols_check.mjs`가 **실행해서** 고정 코어
전부를 값으로 확인한다(소스 문자열만 읽는 검사는 "검사는 초록인데 기능은
죽어 있다"를 못 잡는다 — 감사 229). 그 하네스는 아래 pytest가 CI에서
직접 돌린다.
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

def _table_us_symbols() -> set:
    return set(re.findall(r"^\s+(\w+): \"(?:NASDAQ|AMEX|NYSE)\",", TV, re.M))


def test_every_traded_symbol_has_a_tradingview_mapping():
    """**아는 것만 세지 않는다** — 실제 운영 목록에서 훑는다.

    새 종목을 추가하고 매핑을 빠뜨리면 그 종목만 차트가 안 뜬다. 조용히
    빠지는 것이 이 저장소가 가장 싫어하는 상태다.

    ⚠️ 2026-08-25 CI가 잡은 것: 이 검사는 옛 고정 20종목(AUTO_TARGETS)만
       훑고 있었다. 유니버스가 규칙 스냅샷(state/universe.json)으로 40여
       종목이 된 지 엿새 — 잔고 1위 UUP는 이 검사 밖에 있었고, 눌러도
       차트가 침묵했다. 이제 **지금 운용 중인 목록 그대로**를 훑는다.
       (표에 없는 미국 티커는 티커 단독 후퇴로가 받는다 — 시총 상위
       회전분까지 표로 따라가는 것은 불가능해서다. .mjs ③-0 참조.)
    """
    from quant.universe import active_targets

    us = _table_us_symbols()
    missing = []
    for market, symbol in active_targets(state_dir=str(ROOT / "state")):
        if market == "crypto":
            ok = "/" in symbol
        elif market == "us_stock":
            ok = symbol in us or bool(re.match(r"^[A-Z][A-Z0-9]{0,4}$", symbol))
        elif market == "kr_stock":
            ok = bool(re.match(r"^\d{6}\.(KS|KQ)$", symbol))
        else:
            ok = False
        if not ok:
            missing.append(f"{market}:{symbol}")
    assert not missing, f"트레이딩뷰 매핑이 없는 운영 종목: {missing}"


def test_the_fixed_us_cores_are_in_the_exchange_table_not_the_fallback():
    """규칙으로 박아 둔 고정 코어는 **거래소까지 정확히** 표에 있어야 한다.

    후퇴로(티커 단독)는 매달 회전하는 시총 상위분을 위한 것이다. 고정
    코어는 목록이 소스(quant/universe.py)에 적혀 있고 바뀌지 않으므로,
    거래소를 명시한 표가 못 따라갈 이유가 없다 — 여기 없다는 것은
    2026-08-19 확장 때처럼 표 갱신을 잊었다는 뜻이다.
    """
    from quant.universe import US_ASSET_CORE, US_CORE

    us = _table_us_symbols()
    missing = [s for s in US_CORE + US_ASSET_CORE if s not in us]
    assert not missing, (
        f"고정 코어인데 거래소 표에 없다(후퇴로에 얹혀 있다): {missing}")


def test_the_mapper_actually_computes_the_promised_values():
    """소스 문자열이 아니라 **실행한 값**으로 — mjs 하네스를 여기서 돌린다.

    이 하네스는 지금까지 야간 변이 시험과 손 실행으로만 돌았다 — 감사
    229("실행해서 확인한다")를 반만 지킨 셈이다. PR CI가 직접 돌려야
    표가 낡거나 변환이 깨지는 순간 **그 PR이** 빨개진다.
    """
    import shutil
    import subprocess
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 값 실행 검사 생략")
    r = subprocess.run([node, str(ROOT / "tests" / "tv_symbols_check.mjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_node_harness_covers_the_same_count():
    """하네스가 20종목을 다 적어 뒀는지 — 목록이 늘면 거기도 늘어야 한다."""
    from quant.markets import AUTO_TARGETS

    harness = (ROOT / "tests" / "tv_symbols_check.mjs").read_text("utf-8")
    for market, symbol in AUTO_TARGETS:
        assert f'"{market}:{symbol}"' in harness, (
            f"{market}:{symbol}가 실행 검사에 없다")
