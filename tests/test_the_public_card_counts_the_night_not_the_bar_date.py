"""공개 SNS 카드가 **그 밤의** 오디션을 세는가 — 봉 날짜가 아니라.

■ 왜 (2026-09-01 장부 실측)

카드는 그날 오디션을 ``r.asof === date``로 골랐다. ``date``는 달력일이고
``asof``는 그 종목의 **마지막 봉 날짜**다. 매일 봉이 생기는 것은 코인뿐이고
주식은 금요일에 멈추므로 둘이 어긋난다. 그래서 공개 게시물의 숫자가
**양방향으로** 틀렸다(최근 120줄 창 기준):

    8/29  카드 후보 247명   ← 그 밤 실제 1,183명 (5분의 1로 축소)
    8/28  카드 후보 2,283명 ← 그 밤 실제 1,332명 (한 칸에 네 밤이 섞임)
    8/31  카드 후보 1,199명 ← 그 밤 실제 846명

그리고 미국주식만 돈 밤에는 일치하는 줄이 하나도 없어 카드가
"오늘은 오디션이 없었습니다 / 휴장 등으로 재학습 기록이 없는 날입니다"를
내보냈다 — 21종목을 심사한 밤에 대해서다.

이 계정의 정체성은 **선택 편향 없는 공개 실험**이다. 공개 숫자가 밤마다
축소·과대를 오가면 그 정체성이 무너진다.
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
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chromium_or_skip  # noqa: E402

NIGHT = "2026-09-01"
FRIDAY = "2026-08-28"      # 그 밤 주식의 마지막 봉 날짜(금요일)
PER = 50                   # 종목당 후보 수


def _rows(n_crypto: int, n_stock: int) -> list[dict]:
    """한 밤의 심사 목록 — 코인은 그날 봉, 주식은 금요일 봉."""
    out = [{"asof": NIGHT, "night": NIGHT, "key": f"crypto:C{i}",
            "promoted": False, "n_candidates": PER, "vacuous": False,
            "inert": 0, "trials_total": 100} for i in range(n_crypto)]
    out += [{"asof": FRIDAY, "night": NIGHT, "key": f"us_stock:S{i}",
             "promoted": False, "n_candidates": PER, "vacuous": False,
             "inert": 0, "trials_total": 100} for i in range(n_stock)]
    return out


def _serve(root: Path):
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _card_text(tmp_path, rows: list[dict]) -> str:
    """3장(오디션 카드)을 실제로 그려 전문을 돌려준다."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    root = tmp_path / "site"
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    st["paper"]["portfolio:ALL"]["history"][-1]["date"] = NIGHT
    st["retrain_recent"] = rows
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False),
                                      "utf-8")
    url, srv = _serve(root)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                pg = b.new_page(viewport={"width": 1080, "height": 1350})
                block_external(pg)
                errs: list[str] = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"{url}/sns_card.html?n=3")
                pg.wait_for_timeout(2200)
                # ⚠️ 카드는 `#root`를 **outerHTML로 통째 교체**한다 — 그리고
                #    나면 그 id는 사라진다. body 를 읽는다.
                text = pg.locator("body").inner_text()
                assert not errs, f"페이지 오류 {errs[:2]}"
                return text
            finally:
                b.close()
    finally:
        srv.shutdown()


def test_the_card_publishes_every_audition_of_that_night(tmp_path):
    """한 밤에 24종목을 심사했으면 카드도 그 24종목의 후보를 다 센다."""
    text = _card_text(tmp_path, _rows(5, 19))
    assert f"후보 {24 * PER}명이" in text, text[:400]


def test_counting_by_bar_date_would_have_published_a_fifth(tmp_path):
    """대조군 — 봉 날짜로 골랐으면 코인 5종목만 잡힌다(고치기 전의 값).

    이 검사가 없으면 위 검사는 "아무 숫자나 맞다"를 통과할 수 있다.
    """
    rows = _rows(5, 19)
    by_bar = [r for r in rows if r["asof"] == NIGHT]
    assert len(by_bar) == 5
    assert sum(r["n_candidates"] for r in by_bar) == 5 * PER      # 250
    assert sum(r["n_candidates"] for r in rows) == 24 * PER       # 1200


def test_a_stock_only_night_is_not_published_as_a_holiday(tmp_path):
    """미국주식만 돈 밤을 "휴장"이라고 내보내지 않는다.

    그런 밤에는 모든 줄의 봉 날짜가 금요일이라, 예전 방식으로는 일치하는
    줄이 **하나도 없어** 카드가 "오늘은 오디션이 없었습니다"를 공개했다.
    """
    text = _card_text(tmp_path, _rows(0, 21))
    assert f"후보 {21 * PER}명이" in text, text[:400]
    assert "없었습니다" not in text, text[:400]
    assert "휴장" not in text, text[:400]


# ── 배선: 밤 열쇠가 화면까지 실제로 전달되는가 ─────────────────────────────
#
# 위 검사들은 status.json 의 목록에 `night`가 있다고 **가정**하고 손으로
# 넣어 준다. 배치가 그 칸을 안 실으면 카드는 언제나 옛 경로(봉 날짜)로
# 되돌아가는데 검사는 전부 초록이다.

def test_the_status_payload_carries_the_night_key(tmp_path):
    """장부의 밤 열쇠가 status.json 의 심사 목록까지 실려 나간다."""
    import quant.live.daily as dl

    (tmp_path / "retrain_history.jsonl").write_text(json.dumps({
        "asof": FRIDAY, "night": NIGHT, "market": "us_stock", "symbol": "AAPL",
        "promoted": False, "n_candidates": PER, "vacuous": False,
        "trials_total": 100}, ensure_ascii=False) + "\n", "utf-8")
    out = tmp_path / "status.json"
    dl.write_docs_status(str(tmp_path), str(out))
    rows = json.loads(out.read_text("utf-8"))["retrain_recent"]
    assert len(rows) == 1
    assert rows[0]["night"] == NIGHT
    assert rows[0]["asof"] == FRIDAY        # 대조 — 둘은 실제로 다른 값이다


def test_an_old_line_without_a_night_key_passes_through(tmp_path):
    """밤 열쇠가 없던 옛 줄은 그 칸이 비어 나간다 — 읽는 쪽이 되돌아간다."""
    import quant.live.daily as dl

    (tmp_path / "retrain_history.jsonl").write_text(json.dumps({
        "asof": FRIDAY, "market": "us_stock", "symbol": "AAPL",
        "promoted": False, "n_candidates": PER}, ensure_ascii=False) + "\n",
        "utf-8")
    out = tmp_path / "status.json"
    dl.write_docs_status(str(tmp_path), str(out))
    row = json.loads(out.read_text("utf-8"))["retrain_recent"][0]
    assert row.get("night") in (None, "")
    assert row["asof"] == FRIDAY


# ── 공회전 경보도 같은 방식으로 묶는다 ────────────────────────────────────
#
# ⚠️ 정직하게 — 이 자리에서 측정된 피해는 아직 없다(장부 493줄 중 공회전은
#    2줄, 둘 다 2026-08 중순). 같은 뿌리라 함께 고친 것이지 실측된 사고가
#    있어서가 아니다.

def _vacuous_flags(rows: list[dict]) -> dict:
    from quant.live.flag_watch import _current_flags
    flags = _current_flags({"retrain_recent": rows})
    return {k: v for k, v in flags.items() if k.startswith("audition_vacuous")}


def test_the_vacuous_alarm_counts_the_whole_night(tmp_path):
    """코인과 주식이 함께 공회전한 밤 — 경보가 둘 다 센다."""
    rows = [dict(r, vacuous=True) for r in _rows(2, 3)]
    flags = _vacuous_flags(rows)
    assert len(flags) == 1
    key, msg = next(iter(flags.items()))
    assert key.endswith(f":{NIGHT}:5"), key
    assert f"{NIGHT} 5종목" in msg, msg


def test_by_bar_date_the_stock_side_would_have_vanished():
    """대조군 — 봉 날짜로 골랐으면 주식 쪽 공회전 3종목이 통째로 빠진다."""
    rows = [dict(r, vacuous=True) for r in _rows(2, 3)]
    day = max(r["asof"] for r in rows)
    assert day == NIGHT
    assert len([r for r in rows if r["asof"] == day]) == 2   # 코인 2개뿐


def test_the_vacuous_alarm_names_the_night_not_the_friday(tmp_path):
    """주식만 공회전한 밤 — 경보가 **그 밤 날짜**를 말한다.

    그런 밤에는 모든 줄의 봉 날짜가 금요일이라, 봉 날짜로 날을 고르면 경보가
    "8/28 3종목 공회전"이라고 **지난 금요일을 가리킨다.** 고장 경보가 엉뚱한
    날을 짚으면 그날 밤을 들여다볼 사람이 아무도 없다.
    """
    rows = [dict(r, vacuous=True) for r in _rows(0, 3)]
    assert max(r["asof"] for r in rows) == FRIDAY      # 봉 날짜는 전부 금요일
    key, msg = next(iter(_vacuous_flags(rows).items()))
    assert key.endswith(f":{NIGHT}:3"), key
    assert NIGHT in msg and FRIDAY not in msg, msg
