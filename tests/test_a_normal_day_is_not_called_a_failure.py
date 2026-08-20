"""정상인 날을 고장이라 부르지 않는다 (감사 293).

첫 화면에는 기록이 오래됐을 때 뜨는 띠가 있다. 2026-08-16~18 사흘 공백
때 제 몫을 한 장치다. 그런데 문턱이 **1일**이었다.

장부는 어제 닫힌 봉으로 하루 한 번 확정한다. 그래서 다음 배치(22:15 UTC)가
돌기 전까지는 **멀쩡한 날에도** 기준일이 하루 전이다. 즉 이 띠는 매일
22시간씩, 아무 문제 없는 시스템을 두고 이렇게 말하고 있었다.

    ⏳ 이 숫자는 … 1일 전. 시장이 쉰 것이 아니라
       **기록을 만드는 자동 배치가 실패했습니다**

고장 경보가 매일 뜨면 진짜 고장이 났을 때 아무도 안 본다 — 이 저장소가
사이드바 경고에서 이미 겪은 실패 모양이다(감사 274).

여기서 지키는 것:
  · 1일 전은 **정상**이라고 말한다(그리고 실패라고 말하지 않는다).
  · 2일 전부터는 예전 그대로 고장 띠를 띄운다 — **대조군**. 없으면
    "문턱을 무한대로 올렸다"는 고장도 이 검사를 통과한다.
  · 0일 전에는 둘 다 말하지 않는다.

⚠️ 시계를 가짜로 돌려 본다. 실제 날짜에 기대면 이 검사는 내일 다른 것을
   재게 되고, 언젠가 아무 이유 없이 빨개진다.
"""

from __future__ import annotations

import functools
import http.server
import json
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

# 장부의 마지막 기록일을 고정하고, 브라우저 시계만 옮긴다.
_DAY = "2026-08-19"
_CLOCKS = {
    "오늘": "2026-08-19T23:30:00Z",      # 0일 전
    "하루": "2026-08-20T02:00:00Z",      # 1일 전 — 정상 주기
    "이틀": "2026-08-21T02:00:00Z",      # 2일 전 — 진짜 빠졌다
}

_FAIL = "자동 배치가 실패했습니다"
_OK = "정상입니다"


def _serve(root: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _site(base: Path) -> Path:
    root = base / "site"
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    st["paper"]["portfolio:ALL"]["history"][-1]["date"] = _DAY
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False),
                                      "utf-8")
    return root


@pytest.fixture(scope="module")
def _texts(tmp_path_factory):
    """세 시점의 '한눈에' 전문."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    url, srv = _serve(_site(tmp_path_factory.mktemp("stale")))
    out = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                for name, when in _CLOCKS.items():
                    pg = b.new_page(viewport={"width": 1440, "height": 900})
                    block_external(pg)
                    errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    # 브라우저 시계만 고정한다 — 페이지 코드는 그대로.
                    pg.add_init_script(
                        "const _D=Date;"
                        f"const fixed=new _D('{when}').getTime();"
                        "class D extends _D{constructor(...a){"
                        "if(!a.length)super(fixed);else super(...a)}"
                        "static now(){return fixed}}"
                        "window.Date=D;")
                    pg.goto(f"{url}/index.html")
                    pg.wait_for_timeout(2200)
                    out[name] = pg.locator("#glance-body").inner_text()
                    assert not errs, f"{name}: 페이지 오류 {errs[:2]}"
                    pg.close()
            finally:
                b.close()
    finally:
        srv.shutdown()
    return out


def test_one_day_old_is_called_normal_not_broken(_texts):
    t = _texts["하루"]
    assert _FAIL not in t, (
        "하루 전 기록을 두고 '자동 배치가 실패했습니다'라고 말한다 — "
        "장부는 어제 닫힌 봉으로 확정하므로 정상인 날에도 하루 전이다.\n" + t[:400])
    assert _OK in t, (
        "하루 전이 정상이라는 것을 말하지 않는다 — 아무 설명이 없으면 "
        "읽는 사람이 지어낸다(감사 281).\n" + t[:400])
    assert _DAY in t, "기준일 자체를 안 적는다"


def test_two_days_old_still_raises_the_alarm(_texts):
    """대조군 — 진짜 빠진 날에는 예전 그대로 고장이라고 말해야 한다.

    이게 없으면 "문턱을 무한대로 올렸다"(=경보를 껐다)는 고장도 위 검사를
    통과한다. 2026-08-16~18의 사흘 공백을 잡은 것이 이 띠다.
    """
    t = _texts["이틀"]
    assert _FAIL in t, f"이틀이나 빠졌는데 조용하다:\n{t[:400]}"
    assert "2일 전" in t, f"며칠 빠졌는지 말하지 않는다:\n{t[:400]}"
    assert "시세로 평가된 금액" in t, "낡은 숫자의 의미를 말하지 않는다"


def test_a_fresh_record_says_neither(_texts):
    t = _texts["오늘"]
    assert _FAIL not in t, f"당일 기록에 고장 경보가 뜬다:\n{t[:300]}"
    assert _OK not in t, (
        "당일인데 '하루 전이라 정상'이라고 말한다 — 안 겪은 일을 설명한다")


def test_the_threshold_lives_in_one_named_place():
    """문턱을 숫자로 흩뿌리면 한쪽만 고쳐져 갈라진다(FROZEN_IDEAS ①)."""
    page = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "const _STALE_DAYS=2;" in page
    assert "age>=_STALE_DAYS" in page, "띠 조건이 상수를 안 읽는다"
    assert "age>=1" not in page, "예전 문턱(1일)이 어딘가 남아 있다"
