"""화면이 **사지 않은 것을 샀다고** 말하고 있었다 (감사 281).

사장님 지적(2026-08-18):
    *"투자한 잔고는 지금 코인밖에 없고, 거래내역에는 주식이 있고...
      지금 홈페이지는 보기 힘들어. 이해하기 어렵게 구성이 되어있어."*

맞는 지적이었고, 원인은 화면이 거짓말을 하고 있었기 때문입니다.
2026-08-15 기록에는 **같은 종목이 두 줄로** 들어 있습니다.

    fills:      아마존 매수 24,017.24주 · 6,361,687.93원
    cash_short: 아마존 need 6,365,504.94 / cash 677,061.47

"샀다"와 "돈이 모자라 못 샀다"가 같은 날 같은 종목에 동시에 적혀 있고,
잔고에 아마존은 **없습니다.** 진실은 "못 샀다"입니다.

⚠️ 감사 273·274에서 이미 이 사고를 다뤘는데 **금액만** 가렸습니다
   ("확인 필요"). 화면에는 여전히 "아마존 · 매수"라고 적혀 있었습니다 —
   **숫자를 가려도 주장은 그대로 남습니다.** 절반만 고친 것이고, 그
   절반이 사장님 눈에 "일관성이 없다"로 보였습니다.

기록은 고치지 않습니다(과거 불변). 대신 화면이 같은 기록의 다른 칸을
읽어 무엇이 사실이었는지 고릅니다 — 판정은 `docs/assets/fills.js` 한 곳.
"""

from __future__ import annotations

import functools
import http.server
import json
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _browser import block_external, chromium_or_skip  # noqa: E402

DOCS = ROOT / "docs"

# 2026-08-15 실측 — 이 파일의 숫자는 전부 장부에서 왔다.
EQ = 997197.56
ACCIDENT = {
    "key": "us_stock:AMZN", "side": "buy", "type": "시가",
    "price": 264.880005, "quantity": 24017.2448278807, "amount": 6361687.93,
}
GOOD = {
    "key": "crypto:BNB/USDT", "side": "buy", "type": "즉시",
    "price": 865173.744141, "quantity": 0.0322824708, "amount": 27929.95,
}


# ── ① 판정 자체를 실행해서 확인한다 ──────────────────────────────

def _node() -> str:
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 화면 규칙 실행 검사 생략")
    return node


def test_the_browser_rule_runs_and_is_right():
    r = subprocess.run([_node(), str(ROOT / "tests" / "fills_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_the_real_ledger_still_contains_the_contradiction():
    """전제 고정 — 그 기록이 사라지면 아래 검사들은 아무것도 안 지킨다.

    ⚠️ 이 기록을 **고쳐서** 통과시키면 안 된다. 과거를 고치지 않는 것이
       이 저장소의 정체성이고, 화면이 사실을 고르는 것으로 해결한다.
    """
    fp = ROOT / "state" / "paper" / "portfolio_ALL.json"
    if not fp.exists():
        pytest.skip("장부 없음(새 설치)")
    d = json.loads(fp.read_text("utf-8"))
    rec = next((r for r in (d.get("history") or [])
                if str(r.get("date")) == "2026-08-15"), None)
    if rec is None:
        pytest.skip("그날 기록이 아카이브로 옮겨졌다")
    fills = {f.get("key") for f in (rec.get("fills") or [])}
    short = {c.get("key") for c in (rec.get("cash_short") or [])}
    assert "us_stock:AMZN" in fills & short, (
        "체결과 현금 부족이 같은 종목에 함께 있던 그 기록이 아니다 — "
        f"fills={fills} cash_short={short}")
    assert "us_stock:AMZN" not in (d.get("positions") or {}), (
        "잔고에 아마존이 생겼다 — 이 검사의 전제가 바뀌었다")


# ── ② 화면이 정말 그렇게 말하는가 (진짜 브라우저) ────────────────

def _serve(root: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _site(base: Path, name: str, *, refused: bool):
    """사고를 재현한 하루. `refused=False`면 대조군(정상 체결)."""
    root = base / name
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    pf["equity"], pf["principal"], pf["start_cash"] = EQ, 1_000_000.0, 1_000_000.0
    rec = pf["history"][-1]
    day = str(rec.get("date"))[:10]
    for r in pf["history"]:
        r["equity"] = EQ
    rec["fills"] = [dict(ACCIDENT), dict(GOOD)]
    rec["cash_short"] = ([{"key": ACCIDENT["key"], "need": 6365504.94,
                           "cash": 677061.47}] if refused else [])
    pf["trades"] = [{**ACCIDENT, "date": day}, {**GOOD, "date": day}]
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    return root


@pytest.fixture(scope="module")
def screens(tmp_path_factory):
    """사고를 낸 하루 / 정상인 하루의 거래내역·체결표 글자."""
    exe = chromium_or_skip()
    from playwright.sync_api import sync_playwright

    base = tmp_path_factory.mktemp("fills")
    urls, servers, out = {}, [], {}
    for name, refused in (("bad", True), ("ok", False)):
        url, srv = _serve(_site(base, name, refused=refused))
        urls[name] = url
        servers.append(srv)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=exe)
            try:
                for name, url in urls.items():
                    got = {}
                    for page, sel in (("index.html", "#trades-card"),
                                      ("today.html", "#content")):
                        pg = b.new_page(viewport={"width": 1440, "height": 1000})
                        block_external(pg)
                        errs = []
                        pg.on("pageerror", lambda e: errs.append(str(e)))
                        pg.goto(f"{url}/{page}")
                        pg.wait_for_timeout(2400)
                        got[page] = pg.locator(sel).inner_text()
                        assert not errs, f"{name}/{page}: 스크립트가 던졌다 — {errs}"
                        pg.close()
                    out[name] = got
            finally:
                b.close()
        yield out
    finally:
        for srv in servers:
            srv.shutdown()


def test_the_trade_history_does_not_call_it_a_purchase(screens):
    """한 주도 안 샀으면 그 줄은 '매수'가 아니다."""
    txt = screens["bad"]["index.html"]
    amzn = next((l for l in txt.splitlines() if "아마존" in l), None)
    assert amzn, f"아마존 줄이 없다:\n{txt[:600]}"
    assert "매수" not in amzn, f"사지 않은 것을 '매수'라고 적는다:\n{amzn}"
    assert "주문 실패" in amzn, f"무슨 일이었는지 말하지 않는다:\n{amzn}"
    assert "현금 부족" in amzn, f"이유를 말하지 않는다:\n{amzn}"


def test_the_numbers_of_a_failed_order_are_not_shown(screens):
    """체결되지 않았으므로 체결가·수량·금액은 존재하지 않는다."""
    txt = screens["bad"]["index.html"]
    amzn = next(l for l in txt.splitlines() if "아마존" in l)
    for n in ("264.88", "6,361,688", "6,361,687", "24,017"):
        assert n not in amzn, f"없던 체결의 숫자가 남아 있다({n}):\n{amzn}"


def test_it_says_why_the_balance_and_the_history_disagree(screens):
    """사장님이 본 그 모순을 화면이 먼저 설명해야 한다."""
    txt = screens["bad"]["index.html"]
    assert "체결되지 않은 주문" in txt, f"실패한 주문 건수를 세지 않는다:\n{txt[:400]}"
    assert "잔고에도 없습니다" in txt, (
        f"잔고와 거래내역이 왜 어긋나 보이는지 설명하지 않는다:\n{txt[:800]}")


def _fill_section(txt: str) -> str:
    """'오늘의 체결' 표만 잘라 온다.

    ⚠️ 페이지 전체에서 종목 이름을 찾으면 **'새벽 판단' 표의 같은 종목**이
       먼저 걸린다. 그러면 이 검사는 체결표를 한 번도 안 보고 통과하거나
       엉뚱하게 실패한다 — 이 저장소가 반복해서 겪은 '엉뚱한 자리를 재는
       검사'다.
    """
    i = txt.find("오늘의 체결")
    j = txt.find("예약 주문", i + 1)
    assert i >= 0, f"'오늘의 체결' 표를 못 찾았다:\n{txt[:400]}"
    return txt[i:j if j > i else len(txt)]


def test_the_today_page_uses_the_same_verdict(screens):
    """한 곳을 고치면 거울이 하나 더 있다(FROZEN_IDEAS ⑭)."""
    txt = _fill_section(screens["bad"]["today.html"])
    amzn = next((l for l in txt.splitlines() if "아마존" in l), None)
    assert amzn, f"'오늘의 체결'에 아마존 줄이 없다:\n{txt[:600]}"
    assert "주문 실패" in amzn and "현금 부족" in amzn, (
        f"첫 화면과 다른 말을 한다:\n{amzn}")


def test_a_real_fill_is_still_a_real_fill(screens):
    """대조군 — 멀쩡한 체결까지 지우면 그건 장부가 아니다."""
    for page in ("index.html", "today.html"):
        txt = (screens["bad"][page] if page == "index.html"
               else _fill_section(screens["bad"][page]))
        bnb = next((l for l in txt.splitlines() if "비앤비" in l), None)
        assert bnb, f"{page}: 정상 체결 줄이 사라졌다:\n{txt[:600]}"
        assert "주문 실패" not in bnb, f"{page}: 정상 체결을 실패로 적는다:\n{bnb}"
        assert "27,930" in bnb, f"{page}: 정상 체결의 금액이 사라졌다:\n{bnb}"


def test_without_a_refusal_it_reads_as_a_purchase(screens):
    """대조군 — 거부 기록이 없으면 그 줄은 그냥 매수여야 한다.

    이것이 없으면 "무조건 주문 실패로 적는다"로 바뀌어도 위 검사들이
    전부 통과한다.
    """
    txt = screens["ok"]["index.html"]
    amzn = next((l for l in txt.splitlines() if "아마존" in l), None)
    assert amzn, f"아마존 줄이 없다:\n{txt[:600]}"
    assert "매수" in amzn, f"거부된 적 없는 주문을 실패로 적는다:\n{amzn}"
    assert "주문 실패" not in amzn, amzn
    assert "체결되지 않은 주문" not in txt, (
        f"실패가 없는 날에도 실패 건수를 적는다:\n{txt[:400]}")
