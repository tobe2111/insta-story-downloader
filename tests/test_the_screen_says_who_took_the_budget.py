"""장부에 남긴 사실이 **정말 화면에 나오는가** — 브라우저로 확인한다.

감사 98은 "기록했다"와 "보여줬다"는 다른 일이라고 정했고, 감사 278은 그
구별을 검사 자신이 못 하고 있었다는 것을 드러냈다. `lot_priority`를 화면에서
지워도 그 낱말이 다른 파일에 남아 있어 문자열 검사는 조용했다.

여기서는 **경고가 뜰 만한 하루**와 **조용해야 하는 하루**를 각각 만들어
페이지를 실제로 그려 본다. 짝은 `tests/test_ledger_fields_reach_the_screen.py`
— 그쪽은 값을 기록에서 읽는지(구조)만 보고, 브라우저를 쓰지 않는다.

⚠️ 파일이 나뉜 이유(감사 280): 짝 파일은 배치가 커밋 **직전에** 돌리는 장부
   관문에 들어 있다. 배치 러너에는 브라우저가 없으므로, 거기에 브라우저
   검사가 섞이면 화면과 무관한 이유로 그날 장부가 통째로 안 남는다.
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

# 실측 계좌 크기(2026-08-15) — 이 금액을 넘는 값은 화면이 일부러 감춘다.
_EQ = 997197.56

# 경고가 떠야 하는 하루 / 조용해야 하는 하루. 대조군이 없으면 "매일 뜨는
# 경고"가 되어도 모른다 — 매일 뜨는 경고는 꺼진 경고와 같다.
_LOUD = {"lot_priority": {"crypto:BTC/USDT": {"spent": 200000.0,
                                              "budget": 120000.0,
                                              "gave_way": ["kr_stock:069500"]}},
         "bar_age_days": {"us_stock": 3, "kr_stock": 0}}
_QUIET = {"lot_priority": None, "bar_age_days": {"us_stock": 0, "kr_stock": 1}}


def _serve(root: Path) -> tuple[str, socketserver.TCPServer]:
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _make_site(base: Path, name: str, patch: dict) -> Path:
    root = base / name
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    pf["equity"], pf["principal"], pf["start_cash"] = _EQ, 1_000_000.0, 1_000_000.0
    rec = pf["history"][-1]
    rec["equity"] = _EQ
    # ⚠️ 계좌 안에 들어오는 금액만 쓴다 — 넘으면 화면이 '못 믿을 값'으로
    #    따로 처리하고(감사 273) 이 경고 자체가 안 뜬다.
    for k, v in patch.items():
        if v is None:
            rec.pop(k, None)
        else:
            rec[k] = v
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    return root


@pytest.fixture(scope="module")
def _flags(tmp_path_factory):
    """두 하루(시끄러운 날·조용한 날)의 사이드바 경고 전문.

    ⚠️ playwright 동기 API는 한 프로세스에 **하나의 드라이버 루프**만
       허용한다. 검사마다 sync_playwright()를 열면 두 번째가 "이미 도는
       루프" 오류로 죽는다 — 한 번 열고 두 페이지를 본다.
    """
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    base = tmp_path_factory.mktemp("fields")
    urls, servers, out = {}, [], {}
    for name, patch in (("loud", _LOUD), ("quiet", _QUIET)):
        url, srv = _serve(_make_site(base, name, patch))
        urls[name], _ = url, servers.append(srv)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                for name, url in urls.items():
                    pg = b.new_page(viewport={"width": 1440, "height": 900})
                    block_external(pg)
                    errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    pg.goto(f"{url}/index.html")
                    pg.wait_for_timeout(2400)
                    # 접이식은 사장님 지시(2026-08-18)로 되돌렸다 — 경고는
                    # 처음부터 전부 펴져 있다. 펴는 버튼이 되살아나면
                    # test_the_first_screen…이 그 사실을 잡는다.
                    out[name] = pg.locator("#side-flags").inner_text()
                    assert not errs, f"{name}: 스크립트가 던졌다 — {errs}"
                    pg.close()
            finally:
                b.close()
        yield out
    finally:
        for srv in servers:
            srv.shutdown()


def test_the_screen_says_who_took_the_budget(_flags):
    """'못 샀다'만 말하고 '그 돈은 누가 가져갔나'를 감추면 절반만 밝힌 것이다."""
    txt = _flags["loud"]
    assert "예산을 끌어 쓴 종목" in txt, f"예산을 끌어 쓴 사실이 화면에 없다:\n{txt}"
    assert "BTC/USDT" in txt or "비트코인" in txt, f"어느 종목인지가 없다:\n{txt}"
    assert "자리를 내줬습니다" in txt, f"대신 밀려난 종목을 말하지 않는다:\n{txt}"


def test_the_screen_says_it_judged_on_a_stale_bar(_flags):
    """묵은 봉으로 낸 판단은 다른 시장과 같은 날로 비교할 수 없다."""
    txt = _flags["loud"]
    assert "묵은 봉으로 판단" in txt, f"묵은 봉으로 판단한 시장이 화면에 없다:\n{txt}"
    assert "us_stock 3일 전 봉" in txt, f"어느 시장이 며칠 묵었는지가 없다:\n{txt}"


def test_a_fresh_and_full_day_says_neither(_flags):
    """대조군 — 정상인 날에 이 경고가 뜨면 매일 울리는 배경음이 된다."""
    txt = _flags["quiet"]
    assert "예산을 끌어 쓴 종목" not in txt, f"끌어 쓴 적 없는데 경고가 뜬다:\n{txt}"
    assert "묵은 봉으로 판단" not in txt, f"최신 봉인데 묵었다고 한다:\n{txt}"
