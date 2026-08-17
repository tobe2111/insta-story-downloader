"""점수판이 **틀린 질문에 답하고 있었다** (감사 276).

첫 화면은 이렇게만 말했습니다.

    손해  −2,802원 (−0.28%)

그런데 같은 기간 **전 종목을 그냥 사서 들고만 있었다면 1,005,900원**이었습니다.
진짜 성적은 −2,802원이 아니라 **−8,702원(−0.87%p)**입니다.

이 구별이 왜 중요한가. 이 저장소가 지금 증명하려는 것은 "1억"이 아닙니다 —
변동성 타깃 12%로는 100배까지 **40.6년**이 걸린다는 산수를 README가 이미
적어 두었고, 그건 결함이 아니라 "엣지를 증명하기 전에는 레버를 올리지
않는다"는 규율의 결과입니다. 증명하려는 것은 **"그냥 보유보다 낫다"**
하나입니다.

그렇다면 점수판도 그 질문에 답해야 합니다. 절대 수익만 크게 적으면
**시장이 오른 날은 실력처럼 보이고 내린 날은 억울해 보입니다.**

기준선은 새로 만들지 않습니다 — 장부가 매일 남기는 `price`(첫날 전 종목
균등 매수 지수)를 씁니다. 사이트 차트가 이미 그 값으로 점선을 그리고
있었고, 두 곳이 각자 기준선을 만들면 언젠가 다른 답을 말합니다(㉞).
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

from quant.reporting.benchmark import vs_hold  # noqa: E402

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# 2026-08-13~15 실측 장부 — 이 파일의 숫자는 전부 여기서 왔다.
REAL = [{"date": "2026-08-13", "price": 100.0, "equity": 999635},
        {"date": "2026-08-14", "price": 100.02, "equity": 999847},
        {"date": "2026-08-15", "price": 100.59, "equity": 997197.56}]
BASE = 1_000_000.0


# ── ① 실측 값이 맞는가 ──────────────────────────────────────────

def test_the_real_score_is_worse_than_the_absolute_one():
    """**이 파일이 생긴 이유.** 절대 −2,802원, 진짜 −8,702원."""
    b = vs_hold(REAL, BASE)
    assert b is not None
    assert round(b["hold"]) == 1_005_900, b
    assert round(b["diff"]) == -8_702, b
    assert b["diff_pct"] == pytest.approx(-0.865, abs=0.01), b
    assert b["ahead"] is False
    # 절대 손익보다 **더 나쁘다** — 시장이 올랐기 때문이다.
    assert b["diff"] < (float(REAL[-1]["equity"]) - BASE), b


# ── ② 대조군 — 이긴 날은 이겼다고 말하는가 ──────────────────────

def test_a_flat_market_makes_profit_and_score_the_same():
    b = vs_hold([{"price": 100, "equity": 1_000_000},
                 {"price": 100, "equity": 1_050_000}], 1_000_000)
    assert b["diff"] == pytest.approx(50_000), b
    assert b["ahead"] is True


def test_profit_in_a_rising_market_can_still_be_a_loss():
    """전략이 +5%인데 시장이 +10%면 **진 것**이다.

    이 줄이 없으면 "절대 수익이 플러스면 잘한 것"이라는 착각이 그대로 남는다.
    """
    b = vs_hold([{"price": 100, "equity": 1_000_000},
                 {"price": 110, "equity": 1_050_000}], 1_000_000)
    assert b["ahead"] is False, b
    assert round(b["hold"]) == 1_100_000, b


def test_a_loss_in_a_falling_market_can_still_be_a_win():
    """대조군의 반대쪽 — 시장이 −10%인데 −5%면 **이긴 것**이다."""
    b = vs_hold([{"price": 100, "equity": 1_000_000},
                 {"price": 90, "equity": 950_000}], 1_000_000)
    assert b["ahead"] is True, b


# ── ③ 모르면 지어내지 않는가 ────────────────────────────────────

@pytest.mark.parametrize("hist,base", [
    ([], BASE),
    (None, BASE),
    ([{"price": 100, "equity": 1}], BASE),                 # 한 줄뿐
    ([{"equity": 1}, {"price": 101, "equity": 2}], BASE),  # 첫날 지수 없음
    ([{"price": 100, "equity": 1}, {"equity": 2}], BASE),  # 오늘 지수 없음
    ([{"price": 100, "equity": 1}, {"price": 101}], BASE),  # 자산 없음
    ([{"price": 0, "equity": 1}, {"price": 101, "equity": 2}], BASE),
    ([{"price": 100, "equity": 1}, {"price": 101, "equity": 2}], None),
    ([{"price": 100, "equity": 1}, {"price": 101, "equity": 2}], 0),
    ([{"price": "백", "equity": 1}, {"price": 101, "equity": 2}], BASE),
])
def test_an_unknown_baseline_produces_no_verdict(hist, base):
    """기준선을 모르는데 "이겼다/졌다"를 적는 것이 최악이다."""
    assert vs_hold(hist, base) is None


# ── ④ 두 언어가 같은 답을 내는가 ────────────────────────────────

def _node() -> str:
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 화면 규칙 실행 검사 생략")
    return node


def test_the_browser_rule_runs_and_is_right():
    r = subprocess.run([_node(), str(ROOT / "tests" / "benchmark_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_python_and_javascript_do_not_drift():
    cases = [
        [REAL, BASE],
        [[{"price": 100, "equity": 1_000_000}, {"price": 110, "equity": 1_050_000}], 1_000_000],
        [[{"price": 100, "equity": 1_000_000}, {"price": 90, "equity": 950_000}], 1_000_000],
        [[{"price": 100, "equity": 1}], 1_000_000],
        [[], 1_000_000],
    ]
    js = f"""
      import {{ readFileSync }} from "node:fs";
      const src = readFileSync("docs/assets/benchmark.js", "utf8");
      new Function(src)();
      const Q = globalThis.QuantBench;
      console.log(JSON.stringify({json.dumps(cases)}.map(([h, b]) => {{
        const r = Q.vsHold(h, b);
        return r ? [Math.round(r.hold), Math.round(r.diff), r.ahead] : null;
      }})));
    """
    r = subprocess.run([_node(), "--input-type=module", "-e", js],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
    got = json.loads(r.stdout)
    want = []
    for h, b in cases:
        v = vs_hold(h, b)
        want.append([round(v["hold"]), round(v["diff"]), v["ahead"]] if v else None)
    assert got == want, f"두 구현이 갈라졌다\n  JS {got}\n  PY {want}"


# ── ⑤ 화면이 실제로 그 말을 하는가 ──────────────────────────────

def _render(tmp_path, history, principal):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    if not Path(CHROME).exists():
        pytest.skip("chromium 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    shutil.copytree(ROOT / "docs", tmp_path, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    pf["principal"] = pf["start_cash"] = principal
    pf["equity"] = history[-1]["equity"]
    keep = pf["history"][-1]
    pf["history"] = [{**keep, **r} for r in history]
    (tmp_path / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)
            pg = b.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            pg.wait_for_timeout(2400)
            txt = pg.locator("#glance").inner_text()
            b.close()
    finally:
        srv.shutdown()
    assert not errors, f"스크립트가 던졌다 — {errors}"
    return txt


def test_the_front_page_says_what_holding_would_have_done(tmp_path):
    txt = _render(tmp_path, REAL, BASE)
    assert "1,005,900원" in txt, f"보유 금액이 없다:\n{txt}"
    assert "8,702원" in txt, f"차이가 없다:\n{txt}"
    assert "뒤집니다" in txt, f"지고 있다고 말하지 않는다:\n{txt}"
    # 이 단계의 목표가 무엇인지도 함께 말해야 한다.
    assert "1억이 아니라" in txt, txt


def test_the_front_page_says_it_plainly_when_ahead(tmp_path):
    """대조군 — 이기는 날은 이겼다고 말해야 한다.

    없으면 "항상 진다고 적는다"도 통과하고, 그러면 점수판이 아니라 장식이다.
    """
    txt = _render(tmp_path, [{"date": "2026-08-13", "price": 100, "equity": 1_000_000},
                             {"date": "2026-08-15", "price": 90, "equity": 950_000}],
                  1_000_000)
    assert "앞섭니다" in txt, f"이기고 있는데 그렇게 말하지 않는다:\n{txt}"
