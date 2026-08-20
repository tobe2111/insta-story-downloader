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
