"""장중 실험의 시각은 **한국 시간**이다 (2026-08-19 사장님 지시).

회차와 체결 시각은 원래 UTC로 찍혔고, 페이지는 그 글자의 앞 16자를 그냥
잘라서 보여 줬다. 그래서 화면에 "2026-08-18 05:00"이라고 적힌 체결은
실제로는 **한국 시간 오후 2시**였다. 9시간이 어긋난 채, 어긋났다는 표시도
없이 나가고 있었다(표 머리글에만 작게 UTC라고 적혀 있었다).

이제 두 가지가 바뀐다.

  ① 새 기록은 처음부터 한국 시간으로 찍힌다(`+09:00`).
  ② 화면은 글자를 자르지 않고 **옮겨 적는다.** 그래서 UTC로 남아 있는
     예전 기록도 한국 시간으로 보인다 — 과거 기록은 고치지 않는다.

②가 핵심이다. ①만 하면 오늘 이후만 맞고 어제까지는 계속 9시간 틀린다.

대조군도 함께 본다: 이미 한국 시간으로 저장된 값은 **그대로** 나와야
한다. 그게 없으면 "무조건 9시간 더한다"는 고장도 이 검사를 통과한다.
"""

from __future__ import annotations

import argparse
import datetime as dt
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

# 예전 방식으로 남은 기록(UTC)과 새 방식으로 찍힌 기록(한국 시간).
# 앞의 것은 옮겨 적어야 하고, 뒤의 것은 건드리면 안 된다.
_OLD_UTC = "2026-08-18T05:00:03+00:00"      # → 한국 2026-08-18 14:00
_OLD_KST_SHOWN = "2026-08-18 14:00"
_OLD_SLICED = "2026-08-18 05:00"            # 글자만 자르면 나오던 값

_NEW_KST = "2026-08-19T09:15:00+09:00"      # 이미 한국 시간 — 그대로
_NEW_KST_SHOWN = "2026-08-19 09:15"


# ─────────────────────────── 저장하는 쪽 ───────────────────────────
def test_the_stamp_the_batch_writes_is_korean():
    from quant.live.market_hours import now_kst_iso

    stamp = now_kst_iso()
    assert stamp.endswith("+09:00"), f"한국 시간이 아니다: {stamp}"
    # 표기만 바뀌고 순간은 그대로여야 한다 — 어긋나면 회차 간격이 틀어진다.
    made = dt.datetime.fromisoformat(stamp)
    drift = abs((made - dt.datetime.now(dt.timezone.utc)).total_seconds())
    assert drift < 120, f"찍힌 순간이 지금과 {drift:.0f}초 어긋났다"


def test_the_round_hands_that_korean_stamp_to_both_tracks(tmp_path,
                                                          monkeypatch):
    """코인 트랙과 미국 트랙이 **같은** 한국 시간 값을 받아야 한다.

    두 트랙이 각자 시각을 만들면 회차를 나란히 놓고 볼 수 없다 — 같은
    회차인데 시각이 다르게 적힌다(FROZEN_IDEAS ①).
    """
    import quant.cli as cli
    import quant.live.intraday_challenger as ch
    import quant.live.intraday_us as us

    seen = {}
    monkeypatch.setattr(ch, "run_intraday_round", lambda now, **kw: (
        seen.__setitem__("coin", now),
        {"equity": 1.0, "return_pct": 0.0, "trades": 0, "skipped": 0,
         "cost_paid": 0.0})[1])
    monkeypatch.setattr(us, "run_us_round", lambda now, **kw: (
        seen.__setitem__("us", now), {"skipped": "휴장"})[1])

    cli._cmd_intraday_round(
        argparse.Namespace(state_dir=str(tmp_path), docs_dir=str(tmp_path)))

    assert seen.get("coin", "").endswith("+09:00"), seen
    assert seen.get("us") == seen.get("coin"), (
        f"두 트랙이 다른 시각을 받았다: {seen}")


# ─────────────────────────── 보여 주는 쪽 ───────────────────────────
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
    d = json.loads((DOCS / "intraday.json").read_text("utf-8"))
    d["since"] = _OLD_UTC
    d["last_time"] = _NEW_KST
    d["recent_trades"] = [
        {"time": _OLD_UTC, "symbol": "BTC/USDT", "side": "buy",
         "notional": 212.06, "price": 64219.5, "cost": 0.31, "signal": 0.1},
        {"time": _NEW_KST, "symbol": "ETH/USDT", "side": "sell",
         "notional": 100.0, "price": 3000.0, "cost": 0.15, "signal": -0.2},
    ]
    (root / "intraday.json").write_text(json.dumps(d, ensure_ascii=False),
                                        "utf-8")
    return root


@pytest.fixture(scope="module")
def _page_text(tmp_path_factory):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    url, srv = _serve(_site(tmp_path_factory.mktemp("kst")))
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                pg = b.new_page(viewport={"width": 1440, "height": 900})
                block_external(pg)
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"{url}/intraday.html")
                pg.wait_for_timeout(2000)
                text = pg.inner_text("body")
                assert not errs, f"페이지에서 오류가 났다: {errs[:2]}"
            finally:
                b.close()
    finally:
        srv.shutdown()
    return text


def test_an_old_utc_fill_is_shown_in_korean_time(_page_text):
    assert _OLD_KST_SHOWN in _page_text, (
        f"예전 UTC 체결이 한국 시간({_OLD_KST_SHOWN})으로 안 나온다")
    assert _OLD_SLICED not in _page_text, (
        f"UTC 글자를 그대로 잘라 보여 준다({_OLD_SLICED}) — 9시간 어긋난 값이다")


def test_a_fill_already_in_korean_time_is_left_alone(_page_text):
    """대조군 — 이미 한국 시간인 값에 또 9시간을 더하면 안 된다."""
    assert _NEW_KST_SHOWN in _page_text, (
        f"한국 시간으로 저장된 체결이 {_NEW_KST_SHOWN}으로 안 나온다")
    assert "2026-08-19 18:15" not in _page_text, (
        "한국 시간에 9시간을 또 더했다")


def test_the_screen_says_which_clock_it_is(_page_text):
    """어느 시계인지 화면이 말해야 한다 — 안 적으면 읽는 사람이 못 고른다."""
    assert "시각(한국 시간)" in _page_text
    assert "(한국 시간)" in _page_text
