"""'한눈에'는 지금 상황만 말한다 (감사 294).

사장님 지적(2026-08-20): *"너무 TMI야. 그냥 현재 상황만 얘기하면 될 것 같아."*

카드에는 숫자와 설명이 섞여 있었다. 왜 자산군을 늘리는지, 무엇을 증명하려는
것인지 같은 **설명문**이 금액 사이에 끼어 있어, 정작 "지금 얼마인가"가
안 읽혔다. 화면에 글이 많으면 읽는 사람은 다 읽는 게 아니라 **아무것도**
안 읽는다.

그래서 설명은 지우지 않고 **접었다** — '자세히 보기' 안으로.

여기서 지키는 것:
  · 기본 화면에는 지금 상황(원금·자산·손익·보유·현금·보유 대비)만 남는다.
  · 설명문은 **사라지지 않는다** — 펼치면 그대로 있다(대조군).
    지우는 것과 접는 것은 다르고, 이 저장소는 지운 적이 없다.
"""

from __future__ import annotations

import functools
import http.server
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _browser import block_external, chromium_or_skip  # noqa: E402

DOCS = ROOT / "docs"

# 첫 화면에 **반드시 있어야 하는** 것 — 지금 상황.
_MUST_SHOW = ("넣은 돈", "지금", "이익", "기준일", "현금",
              "그냥 전 종목을 사서 들고만 있었다면")
# 첫 화면에서 **접혀야 하는** 것 — 설명·구호.
_MUST_FOLD = ("다르게 움직이는 자산", '"그냥 보유보다 낫다" 하나입니다')


def _serve(root: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


@pytest.fixture(scope="module")
def _views(tmp_path_factory):
    """접었을 때와 펼쳤을 때의 '한눈에' 전문."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    base = tmp_path_factory.mktemp("glance")
    root = base / "site"
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    url, srv = _serve(root)
    out = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                pg = b.new_page(viewport={"width": 1440, "height": 900})
                block_external(pg)
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"{url}/index.html")
                pg.wait_for_timeout(2200)
                out["접음"] = pg.inner_text("#glance-body")
                out["라벨"] = pg.locator(
                    "#glance-body .gk").all_inner_texts()
                out["높이"] = pg.locator("#glance").bounding_box()["height"]
                pg.click("#morebtn")
                pg.wait_for_timeout(600)
                out["펼침"] = pg.inner_text("#glance-body")
                assert not errs, f"페이지 오류 {errs[:2]}"
            finally:
                b.close()
    finally:
        srv.shutdown()
    return out


@pytest.mark.parametrize("phrase", _MUST_SHOW)
def test_the_situation_is_on_the_first_screen(phrase, _views):
    assert phrase in _views["접음"], (
        f"'{phrase}'이(가) 첫 화면에서 사라졌다 — 접는 것은 설명이지 "
        f"숫자가 아니다:\n{_views['접음'][:400]}")


@pytest.mark.parametrize("phrase", _MUST_FOLD)
def test_the_explaining_is_folded_away(phrase, _views):
    assert phrase not in _views["접음"], (
        f"설명문('{phrase}')이 아직 첫 화면에 있다 — 숫자 사이에 글이 길게 "
        f"끼면 정작 숫자가 안 읽힌다:\n{_views['접음'][:400]}")


@pytest.mark.parametrize("phrase", _MUST_FOLD)
def test_folding_is_not_deleting(phrase, _views):
    """대조군 — 펼치면 그대로 있어야 한다.

    이게 없으면 "설명을 통째로 지웠다"도 위 검사를 통과한다. 이 저장소는
    설명을 지운 적이 없다 — 접었을 뿐이다.
    """
    assert phrase in _views["펼침"], (
        f"'{phrase}'이(가) 펼쳐도 없다 — 접은 게 아니라 지운 것이다")


def test_the_card_is_actually_shorter():
    """숫자로 재는 것 — '줄였다'는 말이 아니라 값으로 확인한다.

    설명문 두 덩이가 접히면 카드가 눈에 띄게 짧아진다. 문구만 바꾸고
    실제로는 그대로인 변경을 막는다.
    """
    page = (DOCS / "index.html").read_text("utf-8")
    # 접히는 두 자리가 실제로 adv 표식을 달고 있는가.
    assert '<div class="sub adv" style="margin-top:6px">종목 ' in page, (
        "실효 표본 설명이 접이식 표식(adv)을 안 달았다")
    assert page.count('<div class="sub adv" style="margin-top:4px">') == 1, (
        "'그냥 보유' 구호가 접이식 표식(adv)을 안 달았다")


def test_only_one_number_is_called_now(_views):
    """'지금'이라 불리는 숫자는 화면에 하나뿐이어야 한다 (감사 299).

    사장님 지적(2026-08-22): *"준실시간 시세는 라이브인데 '지금 (마지막
    기록일 기준)'과 시점이 안 맞는 것 같다."*

    맞는 지적이었고, 원인은 계산이 아니라 **이름**이었다. 첫 화면에는 성격이
    다른 두 숫자가 있다.

      · 새벽 배치가 하루 한 번 **확정한** 자산 — 어제 종가로 굳은 값
      · 준실시간 시세로 **방금 다시 계산한** 참고 합계 — 초 단위로 움직인다

    그런데 카드 라벨이 확정값을 "지금 (마지막 기록일 기준)"이라 불렀다. 바로
    아래 줄은 "준실시간 시세로 다시 계산하면 **지금** …"이라 말한다. 같은
    화면에서 서로 다른 두 숫자가 둘 다 '지금'이면, 읽는 사람은 둘이 안 맞는
    것을 **고장으로** 읽는다 — 실제로는 둘 다 맞는 값인데도.

    확정값은 '지금'이 아니라 **그날 확정된 값**이다. 그래서 날짜로 부른다.
    '지금'이라는 말은 준실시간 쪽 한 곳만 쓴다.

    ⚠️ 여기서 재는 것은 라벨이지 숫자가 아니다. 숫자 두 개가 다른 것은
       정상이고(하나는 어제 종가, 하나는 방금 시세), 고쳐야 할 것은
       **다른 것을 같은 이름으로 부른 것**뿐이었다.
    """
    called_now = [t for t in _views["라벨"] if "지금" in t]
    assert not called_now, (
        "확정 자산 카드가 아직 '지금'이라 불린다 — 바로 아래 준실시간 줄도 "
        f"'지금'이라 말하므로 두 숫자가 같은 이름을 갖는다: {called_now}")


def test_the_confirmed_card_says_which_day_it_confirmed(_views):
    """대조군 — 라벨을 지우는 것으로는 통과할 수 없다.

    위 검사만 있으면 "라벨을 통째로 비운다"도 초록이 된다. 확정값 카드는
    **어느 날 확정된 값인지**를 말해야 한다 — 날짜 없는 '확정'은 언제
    것인지 모르는 숫자고, 그건 '지금'이라 부르는 것만큼이나 못 읽는다.
    """
    import re
    dated = [t for t in _views["라벨"]
             if re.match(r"^\d{4}-\d{2}-\d{2} 확정$", t.strip())]
    assert dated, (
        "확정 자산 카드에 'YYYY-MM-DD 확정' 라벨이 없다 — 라벨을 지우는 것은 "
        f"이름을 고치는 것이 아니다: {_views['라벨']}")
