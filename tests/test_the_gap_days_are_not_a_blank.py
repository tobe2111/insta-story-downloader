"""빈칸을 **"그런 일이 없었다"로 읽게 두지 않는다** (2026-08-19).

2026-08-16~18 사흘은 배치가 판단을 끝내 놓고 저장을 못 한 날이다. 그날
실행 로그에는 자산이 그대로 찍혀 있고, 그 로그는 깃허브가 보관하며 우리가
고칠 수 없다. 그러니 사실은 "모른다"가 아니라 **"알지만 장부에 못 넣었다"**다.
둘은 다르다 — 이 저장소가 반복해서 지켜 온 구분이다.

⚠️ 그렇다고 장부에 채워 넣지도 않는다. 사장님 지시로 실제 되살리기를
   돌려 봤고(2026-08-19), 08-17 자산이 **1,051,671원**으로 나왔다 — 그날
   실제로 말한 999,268원보다 **5.24% 높다.** 그날의 입력이 더는 존재하지
   않기 때문이다(코인 시세 공급처가 바뀌어 같은 날 가격이 9~20% 다르고,
   한국 ETF는 18봉만 와서 계산에서 빠졌다). 하필 **좋아 보이는 쪽**으로
   틀렸다. 그런 숫자를 장부에 넣는 것이 이 실험이 가장 하면 안 되는 일이다.

그래서 화면은 세 가지를 함께 말한다: 그날 뭐라고 했는지 · 왜 장부엔 없는지 ·
다시 계산하면 왜 안 되는지. 그리고 숫자는 산문에 박지 않고 파일에서 읽는다.
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
GAP = json.loads((DOCS / "gap_days.json").read_text("utf-8"))


def _won(v: float) -> str:
    return f"{round(v):,}"


# ── 자료가 자료로서 말이 되는가 (브라우저 없이) ─────────────────

def test_the_gap_days_are_never_in_the_ledger():
    """가장 중요한 자물쇠 — 이 숫자들이 **장부로 새어 들어가면 안 된다.**

    화면에 보이는 것과 계좌에 기록된 것은 다른 일이다. 섞이는 순간
    "다시 계산한 값"이 성적표가 되고, 그 성적표가 내일의 출발 상태가 된다.
    """
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    hist = ((st.get("paper") or {}).get("portfolio:ALL") or {}).get("history") or []
    dates = {r.get("date") for r in hist}
    leaked = sorted(d["date"] for d in GAP["days"] if d["date"] in dates)
    assert not leaked, (
        f"장부에 없어야 할 날이 장부에 있다: {leaked} — 로그에서 옮긴 관측값과 "
        "계좌 기록이 섞였다")


def test_every_gap_day_points_at_an_unforgeable_source():
    """근거가 우리 저장소 안에 있으면 아무것도 증명하지 못한다."""
    for d in GAP["days"] + [GAP["recompute_attempt"]]:
        run = d.get("run") or ""
        assert run.startswith(
            "https://github.com/tobe2111/insta-story-downloader/actions/runs/"), (
            f"{d.get('date') or d.get('bar')}: 확인할 수 있는 실행 기록이 없다 — "
            f"{run!r}")


def test_the_recompute_attempt_is_recorded_with_its_verdict():
    """다시 계산해 봤다는 사실과 **그 결과를 안 썼다는 사실**을 함께 남긴다."""
    r = GAP["recompute_attempt"]
    assert r["recomputed_equity"] != r["logged_equity"]
    assert r["verdict"] == "기록하지 않음", r
    # 좋아 보이는 쪽으로 틀렸다는 것 자체가 이 판단의 핵심 근거다.
    assert r["recomputed_equity"] > r["logged_equity"], (
        "재계산이 실제보다 낮게 나왔다면 설명을 다시 써야 한다 — "
        "지금 문구는 '좋아 보이는 쪽으로 틀렸다'를 전제한다")


def test_the_numbers_are_not_hardcoded_in_the_page():
    """산문에 박으면 다음에 또 갈라진다(이 저장소가 세 번 겪은 결함).

    화면을 그리는 자리는 파일에서 읽어야 한다. 설명 주석에 예시로 적힌
    숫자는 세지 않는다 — 주석은 화면에 안 나온다.
    """
    import re

    src = (DOCS / "index.html").read_text("utf-8")
    # ⚠️ 주석 **덩어리째** 지운다. 줄 앞머리만 보면 여러 줄 주석의 가운데
    #    줄들이 그대로 남아, 설명하려고 적은 숫자가 '박아 넣은 숫자'로
    #    잡힌다(실제로 이 검사를 처음 돌렸을 때 그렇게 헛울렸다).
    body = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    body = re.sub(r"(?m)^\s*//.*$", " ", body)
    for lit in ("999267", "1000116", "1051671"):
        assert lit not in body.replace(",", ""), (
            f"{lit}이(가) 화면 코드에 박혀 있다 — gap_days.json에서 읽을 것")


# ── 정말 화면에 나오는가 (브라우저) ─────────────────────────────

def _serve(root: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


# 지연 띠가 뜨는 상태를 만들기 위한 기준일. 실제 장부가 이 날짜에 멈춰
# 있기를 **바라지 않는다** — 그날까지만 잘라서 직접 만든다(2026-08-19).
# 배치가 성공해 기록이 늘어난 날 이 검사가 깨지면, 하필 가장 확인하고 싶은
# 날 못 쓰게 된다.
_STALE_UNTIL = "2026-08-15"


def _site(base: Path, name: str, *, fresh: bool) -> Path:
    root = base / name
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    if not fresh:
        st = json.loads((DOCS / "status.json").read_text("utf-8"))
        pf = st["paper"]["portfolio:ALL"]
        pf["history"] = [r for r in pf["history"]
                         if str(r.get("date")) <= _STALE_UNTIL]
        assert pf["history"], "기준일까지의 기록이 없다 — 검사가 낡았다"
        st["updated"] = pf["history"][-1]["date"]
        # ⚠️ 검사가 만든 장부가 스스로 말이 돼야 한다. 날짜가 중복되거나 거꾸로
        #    가면 차트 라이브러리는 'Value is null'이라고만 말하고 죽는다 —
        #    그 한 줄로는 원인을 찾는 데 한참 걸린다(2026-08-19 실측). 여기서
        #    먼저, 사람이 읽을 수 있는 말로 걸린다.
        _d = [str(r.get("date")) for r in pf["history"]]
        assert _d == sorted(set(_d)), f"검사가 만든 장부의 날짜가 중복·역순이다: {_d}"
        (root / "status.json").write_text(json.dumps(st, ensure_ascii=False),
                                          "utf-8")
    if fresh:
        # 기록이 오늘이면 지연 띠 자체가 없다 → 할 말도 없어야 한다.
        from datetime import date
        st = json.loads((DOCS / "status.json").read_text("utf-8"))
        pf = st["paper"]["portfolio:ALL"]
        pf["history"][-1]["date"] = date.today().isoformat()
        st["updated"] = date.today().isoformat()
        (root / "status.json").write_text(json.dumps(st, ensure_ascii=False),
                                          "utf-8")
    return root


@pytest.fixture(scope="module")
def screens(tmp_path_factory):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    base = tmp_path_factory.mktemp("gapdays")
    urls, servers, out = {}, [], {}
    for name, fresh in (("stale", False), ("fresh", True)):
        url, srv = _serve(_site(base, name, fresh=fresh))
        urls[name] = url
        servers.append(srv)
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
                    pg.wait_for_timeout(3200)
                    out[name] = pg.locator("#glance").inner_text()
                    assert not errs, f"{name}: 스크립트가 던졌다 — {errs}"
                    pg.close()
            finally:
                b.close()
        yield out
    finally:
        for srv in servers:
            srv.shutdown()


def test_the_screen_says_what_the_system_said_on_those_days(screens):
    txt = screens["stale"]
    for d in GAP["days"]:
        if isinstance(d.get("equity"), (int, float)):
            assert _won(d["equity"]) in txt, (
                f"{d['date']}에 시스템이 말한 자산이 화면에 없다:\n{txt}")


def test_the_screen_says_which_day_had_no_result_at_all(screens):
    """08-16은 성적이 나쁜 날이 아니라 **결과가 없는 날**이다. 다르게 말해야 한다."""
    txt = screens["stale"]
    none = [d for d in GAP["days"] if not isinstance(d.get("equity"), (int, float))]
    assert none, "결과 없는 날이 사라졌다 — 검사가 낡았다"
    assert "결과 자체가 없습니다" in txt, f"빈 날을 빈 날이라 말하지 않는다:\n{txt}"
    for d in none:
        assert d["date"] in txt, f"{d['date']}이 화면에 없다:\n{txt}"


def test_the_screen_admits_the_recompute_came_out_flattering(screens):
    """다시 계산하면 왜 안 되는지를 **숫자로** 말한다."""
    txt = screens["stale"]
    r = GAP["recompute_attempt"]
    assert _won(r["recomputed_equity"]) in txt, f"재계산 값이 없다:\n{txt}"
    assert f'{r["diff_pct"]:.2f}%' in txt, f"얼마나 어긋났는지가 없다:\n{txt}"
    assert "좋아 보이는 쪽" in txt, (
        f"어느 방향으로 틀렸는지를 말하지 않는다 — 그게 핵심이다:\n{txt}")


def test_a_fresh_ledger_says_none_of_this(screens):
    """대조군 — 기록이 최신인 날에 이 설명이 뜨면 매일 읽히는 배경음이 된다."""
    txt = screens["fresh"]
    for d in GAP["days"]:
        if isinstance(d.get("equity"), (int, float)):
            assert _won(d["equity"]) not in txt, (
                f"기록이 최신인데 빠진 날 설명이 뜬다:\n{txt}")
    assert "결과 자체가 없습니다" not in txt, txt
