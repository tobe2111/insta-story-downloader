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

# 브라우저를 어디서 찾는지는 **한 곳에서만** 정한다(감사 278). 이 줄이
# 파일마다 컨테이너 전용 경로를 적고 있던 탓에, GitHub 러너에서는
# 일곱 파일의 화면 계약이 통째로 조용히 건너뛰어지고 있었다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chromium_or_skip  # noqa: E402


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
            b = p.chromium.launch(executable_path=chromium_or_skip())
            pg = b.new_page()
            block_external(pg)
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            pg.wait_for_timeout(2400)
            # '한눈에' 카드는 사장님 지시(2026-08-18)로 내렸다 — 보유 대비
            # 점수는 '한눈에' 카드 안에 있다(감사 282). 잠시 잔고 카드
            # 아래(#bal-bench)에 있었지만, 첫 화면이 세 질문에만 답하도록
            # 정리하면서 **'지금 얼마인가' 바로 옆**으로 돌아왔다 —
            # "그래서 잘하고 있나"는 그 셋 중 하나다.
            txt = pg.locator("#glance").inner_text()
            b.close()
    finally:
        srv.shutdown()
    assert not errors, f"스크립트가 던졌다 — {errors}"
    return txt


def test_the_front_page_says_what_holding_would_have_done(tmp_path):
    """화면이 말하는 '그냥 보유'가 **같은 계산의 결과**와 일치하는가.

    ⚠️ 예전에는 1,005,900원을 글자로 박아 뒀다(2026-08-22 CI 빨간불).
       그 값은 비용을 안 문 기준선이었는데, 그 뒤 "그냥 보유도 살 때 한 번은
       수수료를 낸다"가 반영되면서 화면 숫자가 1,004,788원으로 바뀌었다.
       **화면이 더 정확해졌는데 검사가 틀렸다고 말한 것**이다. 기대값을
       화면과 같은 함수·같은 비용률에서 뽑아, 계산이 바뀌면 검사도 따라오게
       한다. 지켜야 할 것은 특정 숫자가 아니라 '화면과 계산이 같다'이다.
    """
    txt = _render(tmp_path, REAL, BASE)
    # 화면이 쓰는 비용률과 같은 값을 장부에서 읽는다(없으면 0).
    live = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    last = (live["paper"]["portfolio:ALL"]["history"] or [{}])[-1]
    rate = last.get("bench_cost_rate") or 0.0
    b = vs_hold(REAL, BASE, rate)
    assert b is not None
    assert f"{round(b['hold']):,}원" in txt, (
        f"보유 금액이 없다(기대 {round(b['hold']):,}원 · 비용률 {rate}):\n{txt}")
    assert f"{abs(round(b['diff'])):,}원" in txt, (
        f"차이가 없다(기대 {abs(round(b['diff'])):,}원):\n{txt}")
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


# ── ⑥ 방송 캡션도 같은 점수를 말하는가 (감사 277) ────────────────
#
# ⚠️ **부품을 만들어 놓고 안 붙이면 없는 것과 같다.** 감사 276에서 이 계산의
#    파이썬 짝(quant/reporting/benchmark.py)을 만들었는데, 붙인 곳은 화면뿐이고
#    **파이썬 쪽에서는 아무도 부르지 않았다** — 검사만 그 함수를 import하고
#    있었다. 이 저장소가 감사 135·139·243에서 반복해 겪은 자리이고,
#    감사 238·218·113은 전부 "산문은 고쳤는데 캡션만 남았다"였다.
#    캡션이 사이트보다 멀리 퍼지므로 이쪽이 오히려 더 위험하다.

def _status(history, principal=BASE) -> dict:
    return {"updated": history[-1]["date"],
            "paper": {"portfolio:ALL": {
                "principal": principal, "start_cash": principal,
                "goal": 100_000_000, "equity": history[-1]["equity"],
                "history": history}},
            "symbols": {}}


def test_the_broadcast_caption_carries_the_same_score():
    from quant.reporting.social import build_captions

    c = build_captions(_status(REAL))
    for name, txt in (("인스타", c["instagram"]), ("스레드", c["threads"])):
        assert "1,005,900원" in txt or "-0.87%p" in txt, (
            f"{name} 캡션이 보유 대비 성적을 말하지 않는다:\n{txt[:400]}")


def test_the_caption_says_ahead_when_it_is_ahead():
    """대조군 — 이기는 날은 이겼다고 방송해야 한다."""
    from quant.reporting.social import build_captions

    win = [{"date": "2026-08-13", "price": 100, "equity": 1_000_000},
           {"date": "2026-08-15", "price": 90, "equity": 950_000}]
    txt = build_captions(_status(win))["instagram"]
    assert "앞섭니다" in txt, f"이기는 날인데 그렇게 말하지 않는다:\n{txt[:400]}"


def test_the_caption_stays_silent_when_it_cannot_measure():
    """기준선을 모르면 **아무 말도 안 한다** — 지어내는 것보다 침묵이 낫다."""
    from quant.reporting.social import build_captions

    blind = [{"date": "2026-08-13", "equity": 1_000_000},
             {"date": "2026-08-15", "equity": 950_000}]     # price 없음
    txt = build_captions(_status(blind))["instagram"]
    assert "들고만 있었다면" not in txt, f"기준선을 모르는데 적었다:\n{txt[:400]}"
    assert "%p" not in txt.split("자산")[1][:120], txt[:400]


def test_the_short_caption_keeps_the_score_even_when_trimmed():
    """길이가 넘쳐 잘려도 이 숫자는 남아야 한다 — 하이라이트가 아니라 **고지**다.

    감사 97과 같은 규칙: 쓸 말이 많은 날일수록 중요한 것이 잘려 나가면 안 된다.
    """
    from quant.reporting.social import THREADS_TEXT_LIMIT, build_captions

    st = _status(REAL)
    # ⚠️ 이름을 조금 길게 하는 정도로는 **잘림 경로가 안 탄다** — 처음 쓴
    #    검사가 그랬고, 그래서 변이 하나가 살아남았다(짧은 판에서 점수를
    #    빼도 통과했다). 한도를 확실히 넘겨 **그 가지를 실제로 태운다.**
    st["symbols"] = {f"kr_stock:{i:06d}.KS": {"name": "아주아주긴종목이름" * 20}
                     for i in range(12)}
    st["paper"]["portfolio:ALL"]["history"][-1]["applied"] = {
        f"kr_stock:{i:06d}.KS": 0.05 for i in range(12)}
    long_th = build_captions(st)["threads"]
    assert len(long_th) <= THREADS_TEXT_LIMIT, len(long_th)
    # 잘림이 실제로 일어났는지부터 확인한다 — 안 잘렸으면 이 검사는 아무것도
    # 지키지 않는다(하이라이트인 '배분 상위'가 사라진 것이 잘림의 표식이다).
    assert "배분 상위" not in long_th, (
        f"잘림 경로를 안 탔다 — 이 검사가 헛돈다:\n{long_th}")
    assert "%p" in long_th, f"잘린 판에서 보유 대비 성적이 사라졌다:\n{long_th}"
