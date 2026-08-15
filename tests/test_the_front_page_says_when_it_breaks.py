"""첫 화면이 도중에 죽어도 조용하다 (감사 245).

`docs/index.html`의 장부 렌더링은 **긴 then 하나**입니다. 중간 한 줄이
터지면 그 아래가 전부 안 그려지는데, 예외를 `catch(()=>{})`로 통째로
삼키고 있었습니다 — 화면에도 콘솔에도 아무 말이 없습니다.

그러면 읽는 사람은 **빈칸을 "오늘은 그런 일이 없었다"로 읽습니다.**
경고 패널이 통째로 사라져도 "켜진 경고 없음"과 구별되지 않습니다. 공개
장부에서 가장 하면 안 되는 일입니다 — 모르는 것과 아닌 것은 다릅니다.

가정이 아닙니다. **이 감사 도중에 실제로 그 일이 일어났습니다.** 새로
넣은 블록이 다른 블록 안에서만 사는 const(`nm`)를 불러 ReferenceError가
났고, 사이드바의 경고 7개가 통째로 사라졌는데 콘솔조차 조용했습니다.
검사는 초록이었습니다 — 하네스가 그 이름을 스스로 주입했기 때문입니다.
**브라우저로 띄워 봐서** 알았습니다.

그래서 이 검사는 진짜 브라우저로 페이지를 띄웁니다.
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

IDX = (ROOT / "docs" / "index.html").read_text("utf-8")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


# ── 삼키지 않는가 (소스 계약) ─────────────────────────────────

def test_the_ledger_render_does_not_swallow_its_error():
    """`catch(()=>{})`는 '아무 일도 없었다'와 같은 말이다.

    ⚠️ 안쪽의 `.catch(()=>{})`들은 **정상이다** — 시세 폴링 하나가 실패했다고
       화면 전체가 소리칠 필요는 없다. 문제는 장부 렌더 **자체**를 닫는
       바깥 catch다. 그래서 들여쓰기 0칸으로 시작하는 그 줄만 본다
       (안쪽 것까지 싸잡아 금지하면 검사가 엉뚱한 것을 지킨다).
    """
    import re

    head = IDX.index('fetch("status.json")')
    tail = IDX.index("후원 랭킹", head)
    chain = IDX[head:tail]
    outer = re.findall(r"(?m)^\}\)\.catch\((.*)$", chain)
    assert outer, "장부 렌더를 닫는 catch가 아예 없다 — 실패가 콘솔에만 남는다"
    assert not any(c.startswith("()=>{}") for c in outer), (
        f"장부 렌더가 예외를 통째로 삼킨다 — 반쪽만 그려진 화면이 정상으로 "
        f"보인다: {outer}")
    assert "console.error" in chain, "콘솔에도 안 남기면 개발자도 못 본다"


# ── 진짜 브라우저로 확인한다 ──────────────────────────────────

def _serve(tmp_path, patch: dict):
    """docs를 복사해 status.json만 바꿔 띄운다. 반환: (url, 서버)."""
    shutil.copytree(ROOT / "docs", tmp_path, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    st.update(patch)
    (tmp_path / "status.json").write_text(
        json.dumps(st, ensure_ascii=False), "utf-8")
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):              # 로그가 검사 출력을 덮지 않게
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0),
        functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/index.html", srv


def _flags_text(tmp_path, patch: dict) -> str:
    pw = pytest.importorskip("playwright.sync_api",
                             reason="playwright 없음 — 화면 렌더 검사 생략")
    if not Path(CHROME).exists():
        pytest.skip("chromium 없음 — 화면 렌더 검사 생략")
    url, srv = _serve(tmp_path, patch)
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)
            page = b.new_page()
            page.goto(url)
            page.wait_for_timeout(1500)
            out = page.locator("#side-flags").inner_text()
            b.close()
    finally:
        srv.shutdown()
    return out


HEALTH = {"run_health": {
    "paper": {"date": "2026-08-18", "ok": 1, "failed": 19, "skipped": 0,
              "failed_keys": ["kr_stock:005930.KS"]},
    "retrain": {"date": "2026-08-18", "ok": 0, "failed": 0, "skipped": 5,
                "stale": {"crypto:BTC/USDT": 5}, "max_stale_days": 5,
                "stale_unit": "거래일"}}}


def test_the_warning_panel_actually_renders(tmp_path):
    """대조군 — 멀쩡한 장부로는 패널이 그려져야 한다.

    이게 없으면 아래 검사들이 '아무것도 안 그려진 화면'을 통과시킨다.
    """
    txt = _flags_text(tmp_path, HEALTH)
    assert "지금 켜진 경고" in txt, f"경고 패널이 통째로 안 그려졌다:\n{txt}"
    assert "다 그리지 못했습니다" not in txt, f"멀쩡한 장부인데 실패했다:\n{txt}"


def test_the_batch_health_is_visible_to_a_reader(tmp_path):
    """값이 실려 와도 **화면에 안 나오면** 없는 것과 같다(감사 229)."""
    txt = _flags_text(tmp_path, HEALTH)
    assert "부분 실패 19종목" in txt, f"배치 부분 실패가 화면에 없다:\n{txt}"
    assert "삼성전자" in txt, "종목 코드만 보여주면 비개발자는 못 읽는다"
    assert "5거래일" in txt, f"정체 단위가 화면에서 달력 일수로 바뀌었다:\n{txt}"


def test_a_broken_render_says_so_instead_of_going_blank(tmp_path):
    """빈 화면과 '경고 없음'이 같아 보이면 안 된다."""
    txt = _flags_text(tmp_path, {"swaps": 5})   # (st.swaps||[]).slice → TypeError
    assert "다 그리지 못했습니다" in txt, (
        f"렌더가 죽었는데 화면이 아무 말도 안 한다:\n{txt}")
    assert "status.json" in txt, "원본을 어디서 볼지 안 알려준다"
