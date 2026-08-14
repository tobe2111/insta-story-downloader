"""첫 화면에서 종목을 누르면 그 종목 차트가 열리는지.

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님 요청).

    "이 페이지에서 종목을 클릭하면 트레이딩뷰 차트가 보이게끔 해줘.
     종목마다의 차트 말이야. 지금은 /today 여기밖에 안보여"

차트 매핑은 today.html **안에만** 있었다. 첫 화면에 붙이려면 그 매핑이
필요한데, 복사하면 두 벌이 된다 — 상장 시장이 바뀌거나 종목이 추가될 때
한쪽만 고쳐지고, 그러면 어느 쪽이 맞는지 아무도 모른다(FROZEN_IDEAS ①).
그래서 docs/assets/tradingview.js 하나로 빼고, 두 화면이 그것을 싣는다.

매핑이 틀리면 차트가 **조용히 안 뜬다** — 화면에서는 '아직 로딩 중'과
구별되지 않는다. 그래서 값으로 확인한다(tests/tradingview_check.mjs).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
IDX = (DOCS / "index.html").read_text(encoding="utf-8")
TODAY = (DOCS / "today.html").read_text(encoding="utf-8")


def test_the_mapping_runs_and_is_right():
    """매핑을 **실행해서** 확인한다 — 운영 종목 전부가 심볼을 갖는지 포함."""
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 차트 매핑 실행 검사 생략")
    r = subprocess.run([node, str(ROOT / "tests" / "tradingview_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


@pytest.mark.parametrize("page", ["index.html", "today.html"])
def test_every_page_loads_the_mapping_before_using_it(page):
    src = (DOCS / page).read_text(encoding="utf-8")
    assert 'src="assets/tradingview.js"' in src, f"{page}가 매핑 파일을 안 싣는다"
    i = src.find("assets/tradingview.js")
    j = src.find("QuantTV.")
    assert 0 < i < j, f"{page}가 매핑을 쓰는 곳보다 뒤에서 싣는다"


def test_no_page_keeps_its_own_copy_of_the_mapping():
    """사본이 되살아나면 여기서 걸린다.

    옛 today.html은 `if(m==="crypto")return "BINANCE:"+...`를 직접 갖고
    있었고, 그 사본은 코스닥(.KQ)을 못 뗐다. 사본이 있었다는 사실 자체가
    그 결함이 오래 살아남은 이유다.
    """
    for page in ("index.html", "today.html", "paper.html"):
        src = (DOCS / page).read_text(encoding="utf-8")
        assert '"BINANCE:"' not in src, f"{page}가 매핑 사본을 갖고 있다"
        assert '"KRX:"' not in src, f"{page}가 매핑 사본을 갖고 있다"


def test_the_front_page_rows_are_clickable():
    """행이 눌리지 않으면 이 기능은 없는 것과 같다."""
    assert 'class="symrow' in IDX, "종목 행에 표시가 없다"
    assert "tr.clickable" in IDX, "누를 수 있는 행을 고르는 규칙이 없다"
    assert 'closest("tr.clickable")' in IDX, "클릭을 받는 곳이 없다"


def test_only_rows_with_a_chart_look_clickable():
    """차트를 못 여는 행이 손 모양이면, 눌러 보고 아무 일이 없어 고장으로 읽힌다.

    매핑이 null인 종목에는 clickable을 붙이지 않는다.
    """
    m = re.search(r"const tvs=QuantTV\.symbol\(r\.k\);", IDX)
    assert m, "행마다 심볼을 만들지 않는다"
    tail = IDX[m.end():m.end() + 400]
    assert 'tvs?" clickable"' in tail, "심볼이 없는 행도 눌리게 돼 있다"


def test_the_chart_can_be_opened_with_the_keyboard():
    """마우스로만 되는 기능은 절반만 있는 기능이다."""
    assert 'tabindex="0"' in IDX and 'role="button"' in IDX, "키보드로 못 연다"
    assert 'addEventListener("keydown"' in IDX, "키 입력을 안 받는다"


def test_the_chart_says_it_is_display_only():
    """실시간 가격이 판단에 쓰인다고 읽히면 안 된다 — 이 제품에서 가장
    위험한 오해다. 매매는 새벽 확정 데이터로만 한다.
    """
    box = IDX[IDX.find('id="symchart-box"'):IDX.find('id="symchart-box"') + 900]
    assert "표시 전용" in box, "차트가 표시 전용임을 안 밝힌다"
    assert "판단에 쓰이지 않습니다" in box, "판단에 안 쓴다는 말이 없다"
    src = (DOCS / "assets" / "tradingview.js").read_text(encoding="utf-8")
    assert "표시 전용" in src, "모듈에도 같은 경고를 남긴다"


def test_a_symbol_without_a_chart_says_so():
    """열 수 없으면 열 수 없다고 말한다 — 빈 상자는 고장으로 읽힌다."""
    assert 'id="symchart-none"' in IDX
    assert "거래소 코드가 없습니다" in IDX


def test_today_page_still_has_its_chart():
    """공용 파일로 옮기면서 원래 있던 기능이 사라지지 않았는지."""
    assert 'id="tvchart"' in TODAY and 'id="tvsel"' in TODAY
    assert "QuantTV.mount" in TODAY, "위젯을 공용 함수로 띄우지 않는다"
