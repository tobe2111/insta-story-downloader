"""선물 공개 보고서가 **수수료 빼기 전** 성적을 함께 싣는가.

■ 왜 (2026-09-02, 사장님 질문 "코인 선물 손해가 꽤 크네")

실측: 열흘에 −4.17%인데 수수료가 5.47%p — 전략 자체는 **+1.42%**였고
손실의 131%가 수수료였다. 순수익률만 보이면 "전략이 잃었다"로 읽히는데
사실이 아니다. 반대로 총수익률만 보이면 광고다. 그래서 둘을 같은 화면에
놓고, 최근 7일의 수수료와 총이득을 **기록만** 한다(관문이 아니다).
"""
from __future__ import annotations

import pytest

from quant.live.futures_challenger import _fee_window, public_report


def _st(rounds):
    return {"start_cash": 10000.0, "cash": 0.0, "positions": {},
            "cost_paid": rounds[-1]["cost_paid"],
            "funding_paid": rounds[-1]["funding_paid"],
            "rounds": rounds, "curve": [{"at": r["at"], "equity": r["equity"]}
                                        for r in rounds]}


def _round(day: int, equity: float, cost: float, funding: float = 0.0):
    return {"at": f"2026-08-{day:02d}T10:00:00+09:00", "equity": equity,
            "cost_paid": cost, "funding_paid": funding, "gross_exposure": 0.0}


def test_gross_return_is_net_plus_what_was_paid():
    """수수료 빼기 전 = 자산 + 낸 수수료 + 낸 자금조달, 시드 대비."""
    rounds = [_round(23, 10000.0, 0.0), _round(31, 9582.73, 547.23, 11.64)]
    rep = public_report(_st(rounds))
    assert rep["return_pct"] == pytest.approx(-4.1727, abs=1e-3)
    assert rep["gross_return_pct"] == pytest.approx(
        ((9582.73 + 547.23 + 11.64) / 10000 - 1) * 100, abs=1e-3)   # +1.416


def test_net_and_gross_really_differ_when_fees_were_paid():
    """대조군 — 수수료를 냈으면 두 숫자는 다르고, 안 냈으면 같다."""
    paid = public_report(_st([_round(23, 10000.0, 0.0), _round(31, 9900.0, 300.0)]))
    free = public_report(_st([_round(23, 10000.0, 0.0), _round(31, 9900.0, 0.0)]))
    assert paid["gross_return_pct"] > paid["return_pct"]
    assert free["gross_return_pct"] == free["return_pct"]


def test_the_seven_day_window_uses_the_round_before_it_as_baseline():
    """7일 창의 수수료·총이득은 창 **직전** 회차를 기준선으로 뺀다."""
    rounds = [_round(20, 10000.0, 0.0),      # 창 밖
              _round(22, 10050.0, 20.0),      # 창 밖 → 기준선(마지막 창 밖)
              _round(26, 10020.0, 60.0),      # 창 안
              _round(30, 9980.0, 110.0)]      # 창 안(마지막)
    w = _fee_window(_st(rounds), days=7)
    assert w["rounds"] == 2 and w["since"] == rounds[1]["at"]
    assert w["fees"] == pytest.approx(110.0 - 20.0)
    # 총이득 = (자산+누적수수료) 마지막 − 기준선
    assert w["gross_pnl"] == pytest.approx((9980 + 110) - (10050 + 20))


def test_a_window_is_not_reported_as_a_ratio():
    """비율로 적지 않는다 — 총이득이 0이나 음수인 주에는 비율이 뜻을 잃는다."""
    w = _fee_window(_st([_round(23, 10000.0, 0.0), _round(30, 9900.0, 50.0)]))
    assert set(w) >= {"days", "rounds", "fees", "gross_pnl", "since"}
    assert not any(k.endswith("ratio") for k in w)


# ── 공개 페이지가 실제로 그 숫자를 그리는가 ─────────────────────────────

def _render_futures(tmp_path, report: dict) -> str:
    import functools, http.server, json as _json, shutil, socketserver, sys, threading
    from pathlib import Path
    pytest.importorskip("playwright.sync_api", reason="playwright 없음")
    from playwright.sync_api import sync_playwright
    root_repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _browser import block_external, chromium_or_skip

    site = tmp_path / "site"
    shutil.copytree(root_repo / "docs", site, dirs_exist_ok=True)
    (site / "futures.json").write_text(_json.dumps(report, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0),
                                 functools.partial(_Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            try:
                pg = b.new_page(viewport={"width": 1200, "height": 900})
                block_external(pg)
                errs: list[str] = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/futures.html")
                pg.wait_for_timeout(1800)
                text = pg.locator("body").inner_text()
                assert not errs, errs[:2]
                return text
            finally:
                b.close()
    finally:
        srv.shutdown()


def test_the_page_shows_before_fees_next_to_net(tmp_path):
    """화면에 '수수료 빼기 전'이 순수익률 옆에 실제로 그려진다."""
    rep = public_report(_st([_round(23, 10000.0, 0.0),
                             _round(31, 9582.73, 547.23, 11.64)]))
    text = _render_futures(tmp_path, rep)
    assert "수수료 빼기 전" in text, text[:300]
    assert "+1.42%" in text or "+1.4%" in text, text[:300]
    assert "-4.17%" in text or "−4.17%" in text, text[:300]
