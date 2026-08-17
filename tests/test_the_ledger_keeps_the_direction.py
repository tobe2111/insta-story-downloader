"""장부가 **숏의 부호를 지우고 있었다** (감사 264).

    applied = {k: round(abs(v), 4) for k, v in fitted_w.items() if abs(v) > 0}
                        ^^^^^^

숏 -30%와 롱 +30%가 장부·사이트·SNS 카드에 똑같이 `30%`로 남았습니다.
지금은 숏이 링에 없어 값이 늘 양수라 아무도 눈치채지 못합니다 — **숏을
켜는 날**, 화면은 "아마존 30% 보유"라고 말하면서 계좌는 아마존을 팔아 둔
상태가 됩니다. 방송에 나가는 숫자라 사이트보다 오히려 더 위험합니다
(감사 238·218과 같은 계열: 산문은 고쳤는데 캡션만 남아 있었다).

부호를 살리는 것만으로는 부족했습니다. 화면·캡션 네 곳이 각자
`applied[k] > 0`을 "들고 있다"의 뜻으로 쓰고 있어서, 부호를 살리면 이번엔
**숏이 '보유 없음'으로 사라집니다.** 그래서 판정을 한 곳
(`docs/assets/exposure.js` · `quant/reporting/exposure.py`)에 모았습니다.

그리고 **실행해 보고 나서야** 더 나쁜 것이 나왔습니다. 숏이 한 번이라도
증거금에 걸려 거부되면 새벽 배치가 통째로 죽습니다:

    File "quant/live/daily.py", line 2332, in <listcomp>
        {"key": r["symbol"], "need": round(float(r["need"]), 2), ...
    KeyError: 'need'

감사 233의 현금 부족 거부와 감사 260의 공매도 한도 거부가 **같은 목록**에
쌓이는데, 장부는 모든 줄이 현금 부족이라고 가정하고 있었습니다. 소스만
읽었으면 두 줄이 같은 목록을 쓴다는 사실이 보이지 않습니다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import run_daily_portfolio  # noqa: E402
from quant.live.flag_watch import _current_flags  # noqa: E402
from quant.live.retrain import save_champions  # noqa: E402
from quant.reporting import exposure as expo  # noqa: E402
from quant.reporting.social import _today_numbers  # noqa: E402
from quant.strategies import _REGISTRY  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402


class _AlwaysShort(Strategy):
    """항상 -weight — 숏이 링에 오르는 날을 지금 미리 재현한다."""

    name = "always_short_probe"

    def __init__(self, weight: float = 0.5, allow_short: bool = True):
        self.weight = abs(float(weight))
        self.allow_short = True

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return self._finalize(pd.Series(-self.weight, index=df.index), df.index)


@pytest.fixture()
def short_strategy():
    """전역 등록부를 빌렸다가 반드시 돌려놓는다 — 다른 테스트에 새면 안 된다."""
    _REGISTRY["always_short_probe"] = _AlwaysShort
    try:
        yield "always_short_probe"
    finally:
        _REGISTRY.pop("always_short_probe", None)


def _run(tmp_path, first_strategy: str):
    d = str(tmp_path)
    save_champions({f"synthetic:T{i}": {
        "strategy": (first_strategy if i == 0 else "buy_hold"),
        "params": {}, "promotions": 0} for i in range(3)}, d)
    targets = [("synthetic", f"T{i}") for i in range(3)]
    run_daily_portfolio(targets, lookback=200, state_dir=d,
                        require_real_data=False)
    st = json.loads(
        (tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))
    return st, st["history"][-1]


# ── ① 장부가 방향을 남기는가 ─────────────────────────────────────

def test_a_short_stays_negative_in_the_ledger(tmp_path, short_strategy):
    _, last = _run(tmp_path, short_strategy)
    applied = last.get("applied") or {}
    assert applied.get("synthetic:T0", 0) < 0, (
        f"숏이 롱으로 기록됐다: {applied}")
    # 대조군 — 나머지는 롱 그대로다. 부호를 통째로 뒤집은 게 아니다.
    assert applied.get("synthetic:T1", 0) > 0, applied


def test_long_only_days_are_unchanged(tmp_path):
    """대조군 — 숏이 없으면 예전과 똑같은 장부여야 한다.

    이 줄이 없으면 "부호를 살렸다"가 실은 "전부 음수로 적는다"여도 통과한다.
    """
    _, last = _run(tmp_path, "buy_hold")
    applied = last.get("applied") or {}
    assert applied and all(v > 0 for v in applied.values()), applied
    assert abs(last["weight"] - last["net_weight"]) < 1e-6, (
        f"롱만 있는 날인데 총노출≠순노출: {last['weight']} vs {last['net_weight']}")


def test_gross_and_net_split_when_a_short_is_on(tmp_path, short_strategy):
    """총노출(Σ|w|)과 순노출(Σw)은 다른 질문이다 — 숏이 켜지면 갈린다."""
    _, last = _run(tmp_path, short_strategy)
    applied = last["applied"]
    short_w = abs(applied["synthetic:T0"])
    assert short_w > 0
    assert last["weight"] == pytest.approx(sum(abs(v) for v in applied.values()), abs=1e-3)
    assert last["net_weight"] == pytest.approx(sum(applied.values()), abs=1e-3)
    # 총노출이 순노출보다 정확히 '숏 두 배'만큼 크다.
    assert last["weight"] - last["net_weight"] == pytest.approx(2 * short_w, abs=1e-3)


# ── ② 거부는 두 종류다 — 배치가 죽지 않는가 ──────────────────────

def test_a_refused_short_does_not_kill_the_batch(tmp_path, short_strategy):
    """실측 그 장면 — `KeyError: 'need'`로 새벽 배치가 통째로 죽었다.

    증거금이 0인 지금 구조에서 숏 주문은 **반드시** 거부된다. 즉 숏을 켜는
    첫날 밤 배치가 한 줄도 못 남기고 죽는다는 뜻이었다.
    """
    _, last = _run(tmp_path, short_strategy)   # 여기서 죽으면 그게 결함이다
    refused = last.get("short_refused") or []
    assert refused, f"거부를 장부에 안 남겼다: {last.get('short_refused')}"
    assert refused[0]["key"] == "synthetic:T0", refused
    assert refused[0]["short_over"] > 0, refused
    # **현금 부족과 섞이지 않는다** — 이름이 틀리면 원인을 잘못 짚는다.
    assert not (last.get("cash_short") or []), (
        f"증거금 사고가 현금 부족으로 기록됐다: {last['cash_short']}")


def test_a_refused_short_reaches_the_alarm(tmp_path, short_strategy):
    st, _ = _run(tmp_path, short_strategy)
    flags = _current_flags({"paper": {"portfolio:ALL": st}}, today=st["history"][-1]["date"])
    keys = [k for k in flags if k.startswith("short_refused:")]
    assert keys, f"증거금 사고가 경보에 안 실렸다: {list(flags)}"
    assert "synthetic:T0" in flags[keys[0]], flags[keys[0]]
    assert not [k for k in flags if k.startswith("cash_short:")], list(flags)


def test_a_quiet_day_raises_neither(tmp_path):
    """대조군 — 거부가 없으면 두 경보 다 조용해야 한다."""
    st, last = _run(tmp_path, "buy_hold")
    assert not last.get("short_refused") and not last.get("cash_short"), last
    flags = _current_flags({"paper": {"portfolio:ALL": st}}, today=last["date"])
    assert not [k for k in flags
                if k.startswith(("short_refused:", "cash_short:"))], list(flags)


# ── ③ 캡션이 숏을 지우지 않는가 ──────────────────────────────────

def _status(applied: dict) -> dict:
    return {"paper": {"portfolio:ALL": {
        "principal": 1_000_000.0, "start_cash": 1_000_000.0, "goal": 100_000_000,
        "history": [{"date": "2026-08-17", "equity": 1_000_000.0,
                     "return_pct": 0.0, "weight": expo.gross(applied),
                     "applied": applied}]}},
        "symbols": {k: {"name": k.split(":")[-1]} for k in applied}}


def test_the_caption_does_not_erase_a_short():
    """"배분 상위: 아마존"이 실은 **아마존을 팔아 둔** 것이면 그 캡션은 거짓이다."""
    x = _today_numbers(_status({"us_stock:AMZN": -0.30, "us_stock:SPY": 0.10}))
    assert x["n_held"] == 2, x["n_held"]
    # 가장 큰 자리가 숏이어도 1위다 — 부호로 정렬하면 맨 끝으로 밀린다.
    assert x["top_names"][0].startswith("AMZN"), x["top_names"]
    assert "(숏)" in x["top_names"][0], x["top_names"]
    assert "(숏)" not in x["top_names"][1], x["top_names"]


def test_a_long_only_caption_is_unchanged():
    """대조군 — 롱만 있는 날 캡션에 '숏'이 끼면 안 된다."""
    x = _today_numbers(_status({"us_stock:AMZN": 0.30, "us_stock:SPY": 0.10}))
    assert x["top_names"] == ["AMZN", "SPY"], x["top_names"]
    assert x["n_held"] == 2


# ── ④ 두 언어가 같은 답을 내는가 ─────────────────────────────────

def _node() -> str:
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 화면 규칙 실행 검사 생략")
    return node


def test_the_browser_rule_runs_and_is_right():
    r = subprocess.run([_node(), str(ROOT / "tests" / "exposure_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_python_and_javascript_do_not_drift():
    """같은 규칙을 두 언어로 쓸 수밖에 없다면, **같은 답인지 매번 확인한다.**

    갈라지면 같은 날 같은 종목이 사이트에서는 '숏 30%'인데 캡션에서는
    '보유 없음'으로 나간다(FROZEN_IDEAS ①·㉞).
    """
    books = [{"A": 0.3, "B": -0.2, "C": 0.0},
             {"A": 0.5, "B": -0.5},
             {"A": -0.4, "B": -0.1},
             {"A": 0.1}, {}]
    js = f"""
      import {{ readFileSync }} from "node:fs";
      const src = readFileSync("docs/assets/exposure.js", "utf8");
      new Function(src)();
      const Q = globalThis.QuantExposure;
      const out = {json.dumps(books)}.map(b => [
        Q.count(b), Q.gross(b), Q.net(b),
        Q.top(b, 3).map(e => e[0]), Q.text(b.A == null ? 0 : b.A),
      ]);
      console.log(JSON.stringify(out));
    """
    r = subprocess.run([_node(), "--input-type=module", "-e", js],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
    got = json.loads(r.stdout)
    want = [[expo.count(b), expo.gross(b), expo.net(b),
             [k for k, _ in expo.top(b, 3)], expo.text(b.get("A", 0))]
            for b in books]
    assert got == want, f"두 구현이 갈라졌다\n  JS  {got}\n  PY  {want}"


# ── ⑤ 화면이 실제로 그렇게 그리는가 (진짜 브라우저) ──────────────

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _render(tmp_path, page_name: str, applied: dict, selector: str) -> str:
    """docs를 복사해 통합 계좌의 마지막 기록만 바꿔 띄운다.

    ⚠️ 문자열 검사로는 부족하다(감사 245). `QuantExposure`를 부르는 코드가
       거기 있다는 것과, 그 스크립트가 실제로 **적재돼서** 값을 낸다는 것은
       다른 말이다 — `<script src>` 한 줄을 빠뜨리면 페이지가 통째로 죽는데
       소스 검사는 초록이다.
    """
    import functools
    import http.server
    import shutil
    import socketserver
    import threading

    pw = pytest.importorskip("playwright.sync_api",
                             reason="playwright 없음 — 화면 렌더 검사 생략")
    if not Path(CHROME).exists():
        pytest.skip("chromium 없음 — 화면 렌더 검사 생략")

    shutil.copytree(ROOT / "docs", tmp_path, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    last = st["paper"]["portfolio:ALL"]["history"][-1]
    last["applied"] = applied
    last["weight"] = round(expo.gross(applied), 4)
    last["net_weight"] = round(expo.net(applied), 4)
    (tmp_path / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)
            page = b.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page_name}")
            page.wait_for_timeout(1800)
            out = page.locator(selector).inner_text()
            b.close()
    finally:
        srv.shutdown()
    assert not errors, f"{page_name}에서 스크립트가 터졌다: {errors}"
    return out


_SHORT_BOOK = {"us_stock:AMZN": -0.30, "us_stock:SPY": 0.10,
               "crypto:BTC/USDT": 0.05}
_LONG_BOOK = {"us_stock:AMZN": 0.30, "us_stock:SPY": 0.10,
              "crypto:BTC/USDT": 0.05}


def test_the_front_page_counts_a_short_as_held(tmp_path):
    """숏 한 자리가 '보유'에서 빠지면 사이드바가 한 곳 적게 담겼다고 쓴다."""
    import re

    short = _render(tmp_path / "s", "index.html", _SHORT_BOOK, "#side-cash")
    long_ = _render(tmp_path / "l", "index.html", _LONG_BOOK, "#side-cash")
    assert "돈이 지금 어디 있나" in short, f"사이드바가 안 그려졌다:\n{short}"
    ns = re.search(r"(\d+)곳만 담김", short)
    nl = re.search(r"(\d+)곳만 담김", long_)
    assert ns and nl, (short, long_)
    # 대조군과 **같은 수** — 부호만 바뀌었지 담긴 종목은 그대로다.
    assert ns.group(1) == nl.group(1) == "3", (short, long_)


def test_todays_page_counts_a_short_as_held(tmp_path):
    short = _render(tmp_path / "s", "today.html", _SHORT_BOOK, ".hero")
    long_ = _render(tmp_path / "l", "today.html", _LONG_BOOK, ".hero")
    import re
    n_short = re.search(r"오늘 (\d+)종목 보유", short)
    n_long = re.search(r"오늘 (\d+)종목 보유", long_)
    assert n_short and n_long, (short, long_)
    # 대조군과 **같은 수**여야 한다 — 부호만 바뀌었지 보유 종목은 그대로다.
    assert n_short.group(1) == n_long.group(1) == "3", (short, long_)
