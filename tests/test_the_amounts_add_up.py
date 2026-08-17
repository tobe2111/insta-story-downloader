"""사이트가 **계좌보다 큰 금액**을 사실처럼 보여주고 있었다 (감사 273).

사장님 지적: *"홈페이지 내에서 지금 숫자들이 다 맞진 않은 것 같은데?
금액이 말이야."* 맞았습니다. 자산 997,198원짜리 계좌의 2026-08-15 기록입니다.

    오늘의 체결   아마존 매수 24,017.24주 · 6,361,687.93원   ← 자산의 6.4배
    지금 켜진 경고 비앤비 4,526,594원 / 배정 4,501,933원      ← 4.5배
                   리플   4,084,420원 / 배정 4,062,168원      ← 4.1배
                   비트코인 1,086,327원 / 배정 1,080,409원    ← 1.09배

세 갈래가 겹쳤습니다.

**① 거부된 주문이 체결로 적혔다.** 그날 장부에는 같은 종목이 두 줄로 있습니다 —
`fills: 아마존 매수` 와 `cash_short: 아마존 need 6,365,505 / cash 677,061`.
**한 주도 안 샀는데** 화면은 "아마존 매수"라고 말했고, 같은 화면의 잔고 표에
아마존은 없었습니다. 코인 즉시 체결 쪽은 감사 233이 이미 상태를 보게
고쳤는데 **바로 그 짝(주식 시가 체결)은 안 고쳤습니다.**

**② 금액을 아무도 검사하지 않았다.** 비중은 검사합니다(체결 비중 ≤ 그날
총노출). 그런데 그날 체결 비중은 0.0878, 총노출은 0.4215 — **비중은 전부
정상이었습니다.** 비중과 금액이 다른 통화로 계산되면 비중만 보는 검사는
그냥 통과합니다.

**③ 화면에 통화 단위가 없었다.** 체결가 열에 비트코인 89,883,874.8(원)과
아마존 264.88(달러)이 나란히 찍혔습니다.

**기록은 고치지 않습니다**(과거 불변). 대신 계좌로 설명되지 않는 금액은
화면에서 "표시하지 않음"으로 두고 무슨 일이었는지 밝힙니다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker.paper import PaperBroker  # noqa: E402
from quant.live.daily import (AMOUNT_SANITY_RATIO,  # noqa: E402
                              amounts_over_equity)
from quant.live.flag_watch import _current_flags  # noqa: E402

# 2026-08-15 실측 기록(줄여 옮긴 것) — 이 파일의 모든 숫자는 장부에서 왔다.
EQ = 997197.56
REAL = {
    "date": "2026-08-15", "equity": EQ,
    "fills": [{"key": "us_stock:AMZN", "amount": 6361687.93},
              {"key": "crypto:BNB/USDT", "amount": 27929.95}],
    "lot_priority": {"crypto:BTC/USDT": {"spent": 1086327.14},
                     "crypto:ETH/USDT": {"spent": 80581.96},
                     "crypto:BNB/USDT": {"spent": 4526594.72}},
}


# ── ① 거부된 주문은 체결이 아니다 ────────────────────────────────

def test_a_refused_buy_is_not_a_fill():
    """브로커가 실제로 거부하는지부터 값으로 본다 — 여기가 사실의 출처다."""
    b = PaperBroker(cash=677061.47, fee=0.0)
    order = b.market_order("us_stock:AMZN", "buy", 24017.24, 264.88)
    assert order.status == "rejected", order
    assert float(order.filled_quantity) == 0.0, order
    # ⚠️ **요청 수량은 그대로 남아 있다** — 여기가 함정이었다. 장부가
    #    `order.quantity`를 적으면 거부된 주문이 체결로 남는다.
    assert float(order.quantity) > 0, order


def test_the_ledger_writes_the_filled_quantity_not_the_requested_one():
    """장부는 `filled_quantity`를 적어야 한다 — 두 값이 다른 자리가 사고 지점."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    # 시가 체결(주식)·즉시 체결(코인) **두 곳 모두** 상태를 봐야 한다.
    assert src.count('not in ("filled", "partial")') >= 2, (
        "체결 기록 경로 중 주문 상태를 안 보는 곳이 남아 있다")
    assert 'round(float(order.quantity), 10)' not in src, (
        "요청 수량을 체결 수량으로 적는 자리가 남아 있다")


# ── ② 금액이 계좌를 넘을 수 없다 ─────────────────────────────────

def test_the_real_accident_is_caught():
    bad = amounts_over_equity(EQ, REAL["fills"], REAL["lot_priority"])
    assert [f["key"] for f in bad["fills"]] == ["us_stock:AMZN"], bad
    assert {f["key"] for f in bad["lot_priority"]} == {
        "crypto:BTC/USDT", "crypto:BNB/USDT"}, bad
    assert bad["equity"] == EQ


def test_a_normal_day_is_silent():
    """대조군 — 멀쩡한 날에 걸리면 이 경보는 배경음이 된다."""
    assert amounts_over_equity(
        999847.15,
        [{"key": "crypto:BNB/USDT", "amount": 27929.95}],
        {"crypto:BTC/USDT": {"spent": 62776.39}}) == {}


def test_the_slack_is_for_rounding_not_for_orders_of_magnitude():
    """여유를 1.5배로 잡으면 실측 사고 중 1.09배짜리를 놓친다."""
    assert AMOUNT_SANITY_RATIO < 1.1, AMOUNT_SANITY_RATIO
    assert amounts_over_equity(EQ, [{"key": "k", "amount": 1086327.14}], None), (
        "계좌를 9% 넘는 금액이 통과했다")


def test_an_unknown_equity_accuses_nobody():
    """모르는 것과 아닌 것은 다르다 — 근거가 없으면 판정도 하지 않는다."""
    for eq in (None, 0, -1, float("nan"), "백만원"):
        assert amounts_over_equity(eq, REAL["fills"], REAL["lot_priority"]) == {}


def test_the_weight_check_alone_would_have_missed_it():
    """**왜 기존 검사가 통과했는지**를 못 박는다.

    그날 체결 비중 0.0878 ≤ 총노출 0.4215 — 비중만 보는 검사는 조용하다.
    이 줄이 없으면 "검사를 하나 더 만들었다"의 이유가 코드에서 사라진다.
    """
    gross, fill_w = 0.4215, 0.0878
    assert fill_w <= gross, "전제가 바뀌었다 — 그날 비중은 정상 범위였다"
    assert amounts_over_equity(EQ, REAL["fills"], None), (
        "비중은 정상인데 금액은 6.4배였다 — 금액 검사가 잡아야 한다")


# ── ③ 경보가 울리는가 ────────────────────────────────────────────

def _status(**over):
    rec = {"date": "2026-08-17", "equity": EQ}
    rec.update(over)
    return {"paper": {"portfolio:ALL": {"history": [rec]}}}


def test_the_accident_reaches_the_alarm():
    bad = amounts_over_equity(EQ, REAL["fills"], REAL["lot_priority"])
    flags = _current_flags(_status(impossible_amounts=bad), today="2026-08-17")
    keys = [k for k in flags if k.startswith("impossible_amounts:")]
    assert keys, list(flags)
    assert "us_stock:AMZN" in flags[keys[0]], flags[keys[0]]


def test_a_clean_day_raises_no_alarm():
    flags = _current_flags(_status(), today="2026-08-17")
    assert not [k for k in flags if k.startswith("impossible_amounts:")], list(flags)


# ── ④ 저장된 장부 전체 — 새 기록에는 이런 것이 없어야 한다 ───────

def test_no_stored_record_hides_an_impossible_amount_without_saying_so():
    """이미 저장된 기록은 **고치지 않는다.** 다만 표식이 붙어 있어야 한다.

    `impossible_amounts` 칸이 생기기 전(2026-08-15 이전) 기록은 건드리지
    않는다 — 그때는 그런 칸 자체가 없었다.
    """
    for fp in (ROOT / "state" / "paper").glob("portfolio_*.json"):
        for rec in json.loads(fp.read_text("utf-8")).get("history") or []:
            bad = amounts_over_equity(rec.get("equity"), rec.get("fills"),
                                      rec.get("lot_priority"))
            if not bad:
                continue
            assert "impossible_amounts" in rec or rec.get("date") <= "2026-08-15", (
                f"{fp.name} {rec.get('date')}: 계좌보다 큰 금액이 표식 없이 "
                f"들어 있다 — 화면이 그걸 사실로 말한다: {bad}")


# ── ⑤ 두 언어가 같은 답을 내는가 ─────────────────────────────────

def _node() -> str:
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 화면 규칙 실행 검사 생략")
    return node


def test_the_browser_rule_runs_and_is_right():
    r = subprocess.run([_node(), str(ROOT / "tests" / "amounts_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_python_and_javascript_do_not_drift():
    """갈라지면 사이트는 숨기는데 경보는 안 울리거나, 그 반대가 된다."""
    cases = [[EQ, 6361687.93], [EQ, 27929.95], [EQ, 1086327.14],
             [EQ, -6361687.93], [EQ, EQ], [0, 9e9], [999847.15, 62776.39]]
    js = f"""
      import {{ readFileSync }} from "node:fs";
      const src = readFileSync("docs/assets/amounts.js", "utf8");
      new Function(src)();
      const Q = globalThis.QuantAmounts;
      console.log(JSON.stringify(
        {json.dumps(cases)}.map(([e, a]) => Q.impossible(e, a))));
    """
    r = subprocess.run([_node(), "--input-type=module", "-e", js],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
    got = json.loads(r.stdout)
    want = [bool(amounts_over_equity(e, [{"key": "k", "amount": a}], None))
            for e, a in cases]
    assert got == want, f"두 구현이 갈라졌다\n  JS {got}\n  PY {want}"


# ── ⑥ 화면이 정말로 그 숫자를 안 보여주는가 (진짜 브라우저) ──────

# 브라우저를 어디서 찾는지는 **한 곳에서만** 정한다(감사 278). 이 줄이
# 파일마다 컨테이너 전용 경로를 적고 있던 탓에, GitHub 러너에서는
# 일곱 파일의 화면 계약이 통째로 조용히 건너뛰어지고 있었다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chrome_exe  # noqa: E402

CHROME = chrome_exe()


def _render(tmp_path, page, selector, detail=False):
    """2026-08-15 사고를 그대로 넣은 status.json으로 페이지를 띄운다.

    ⚠️ 실제 `docs/status.json`을 그대로 쓰면 내일 새벽 배치가 그 파일을
       바꾸는 순간 이 검사가 이유 없이 깨진다. 사고를 **재현해서** 넣는다.
    """
    import functools
    import http.server
    import socketserver
    import threading

    pw = pytest.importorskip("playwright.sync_api",
                             reason="playwright 없음 — 화면 렌더 검사 생략")
    if not Path(CHROME).exists():
        pytest.skip("chromium 없음 — 화면 렌더 검사 생략")

    import shutil as _sh
    _sh.copytree(ROOT / "docs", tmp_path, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    last = st["paper"]["portfolio:ALL"]["history"][-1]
    last["equity"] = EQ
    last["fills"] = [{"key": "us_stock:AMZN", "price": 264.880005,
                      "bar": "2026-08-14 00:00:00", "side": "buy",
                      "quantity": 24017.2448278807, "amount": 6361687.93,
                      "type": "시가"},
                     {"key": "crypto:BNB/USDT", "price": 865173.744141,
                      "bar": "2026-08-14 00:00:00", "side": "buy",
                      "quantity": 0.0322824708, "amount": 27929.95,
                      "type": "즉시"}]
    # 거래내역 표는 `trades`를 읽는다 — 같은 사고의 세 번째 자리(감사 274).
    st["paper"]["portfolio:ALL"]["trades"] = [
        {"key": "us_stock:AMZN", "price": 264.880005, "date": "2026-08-15",
         "side": "buy", "quantity": 24017.2448278807, "amount": 6361687.93,
         "type": "시가"},
        {"key": "crypto:BNB/USDT", "price": 865173.744141, "date": "2026-08-14",
         "side": "buy", "quantity": 0.0322824708, "amount": 27929.95,
         "type": "즉시"}]
    for r in st["paper"]["portfolio:ALL"]["history"]:
        r["equity"] = EQ                      # 그날 자산과 견주므로 채워 준다
    last["lot_priority"] = {
        "crypto:BNB/USDT": {"budget": 4501932.95, "spent": 4526594.72,
                            "price": 860614.0, "gave_way": []},
        "crypto:ETH/USDT": {"budget": 80142.94, "spent": 80581.96,
                            "price": 2661605.88, "gave_way": []}}
    (tmp_path / "status.json").write_text(
        json.dumps(st, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)
            pg = b.new_page()
            block_external(pg)
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page}")
            pg.wait_for_timeout(2200)
            if detail and pg.locator("#morebtn").count():
                pg.locator("#morebtn").click()   # 간단 보기에선 접혀 있다(감사 274)
                pg.wait_for_timeout(400)
            out = pg.locator(selector).inner_text()
            b.close()
    finally:
        srv.shutdown()
    assert not errors, f"{page}: 스크립트가 던졌다 — {errors}"
    return out


def test_the_fill_table_refuses_the_impossible_amount(tmp_path):
    txt = _render(tmp_path, "today.html", "#content")
    i = txt.find("오늘의 체결")
    tab = txt[i:i + 500]
    assert "표시하지 않음" in tab, f"못 믿을 금액을 그대로 보여준다:\n{tab}"
    assert "6,361,688" not in tab and "6361687" not in tab, tab
    # 체결가도 가린다 — 그 264.88이 **환산이 빠진 값**이었다. 금액만 가리고
    # 가격을 남기면 "아마존을 264원에 샀다"는 오독이 그대로 남는다.
    assert "264.88" not in tab, f"못 믿을 체결가가 그대로 남아 있다:\n{tab}"
    # 대조군 — 멀쩡한 체결의 가격은 보여야 한다.
    assert "865,173" in tab, f"정상 체결가까지 가렸다:\n{tab}"
    # 대조군 — 멀쩡한 체결은 금액이 그대로 나와야 한다. 다 가리면 장부가 아니다.
    assert "27,930원" in tab, f"정상 체결까지 가렸다:\n{tab}"
    # 단위가 없어서 264.88을 '264원'으로 읽었다(사장님 지적).
    assert "체결가(원)" in tab, f"체결가에 통화 단위가 없다:\n{tab}"


def test_the_front_page_says_the_amounts_do_not_add_up(tmp_path):
    """🚨 경고는 **간단 보기에서도** 보여야 한다 — 접어 두면 없는 것과 같다."""
    txt = _render(tmp_path, "index.html", "#side-flags")
    assert "금액이 계좌와 안 맞는 기록" in txt, f"경고가 없다:\n{txt[:600]}"
    # ⚠️ `won()`은 반올림한다 — 4,526,594.72원은 화면에 "4,526,595원"으로
    #    찍힌다. 원본 소수점으로 검사하면 이 줄은 아무것도 안 지킨다.
    assert "4,526,595" not in txt and "4,526,594" not in txt, (
        f"못 믿을 금액을 그대로 읽어 준다:\n{txt[:600]}")
    assert "비앤비" not in txt.split("금액이 계좌와 안 맞는")[0], (
        f"못 믿을 종목이 '예산을 끌어 쓴' 줄에 남아 있다:\n{txt[:600]}")



def test_a_normal_over_budget_line_survives(tmp_path):
    """대조군 — 같은 날의 **정상** 예산 초과는 지우지 않는다.

    (감사 274에서 이 줄은 '자세히 보기' 뒤로 접혔으므로 펴서 확인한다.)
    """
    txt = _render(tmp_path, "index.html", "#side-flags", detail=True)
    assert "이더리움" in txt and "80,582원" in txt, (
        f"정상 기록까지 함께 지웠다:\n{txt[:600]}")


# ── ⑦ 배치를 실제로 돌려서 확인한다 ──────────────────────────────

def test_a_batch_never_writes_a_refused_order_as_a_fill(tmp_path, monkeypatch):
    """소스를 읽는 대신 **배치를 돌린다**(감사 264의 교훈).

    현금을 바닥까지 줄여 두면 그날의 매수는 반드시 거부된다. 그때 장부에
    체결이 한 줄이라도 적히면 그게 결함이다 — 2026-08-15에 실제로 그랬다.
    """
    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions

    d = str(tmp_path)
    save_champions({f"synthetic:T{i}": {"strategy": "buy_hold", "params": {},
                                        "promotions": 0} for i in range(3)}, d)
    targets = [("synthetic", f"T{i}") for i in range(3)]
    (tmp_path / "paper").mkdir(parents=True, exist_ok=True)
    # 현금 1원짜리 계좌 — 어떤 매수도 낼 수 없다.
    (tmp_path / "paper" / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "cash": 1.0, "start_cash": 1.0,
        "positions": {}, "history": [], "base_prices": {}}), "utf-8")

    run_daily_portfolio(targets, lookback=200, state_dir=d,
                        require_real_data=False)
    last = json.loads(
        (tmp_path / "paper" / "portfolio_ALL.json").read_text("utf-8"))["history"][-1]
    for f in last.get("fills") or []:
        assert float(f.get("quantity") or 0) > 0, (
            f"수량 0짜리 '체결'이 적혔다: {f}")
        assert float(f.get("amount") or 0) <= float(last["equity"]) * 1.02, (
            f"계좌({last['equity']})보다 큰 체결이 적혔다: {f}")
    assert not last.get("impossible_amounts"), last["impossible_amounts"]


def test_the_trade_history_refuses_the_impossible_amount(tmp_path):
    """거래내역 표도 같은 판정을 써야 한다.

    감사 273에서 '오늘의 판단'의 체결 표와 첫 화면 경고는 고쳤는데
    **이 표만 남아 있었다** — 한 곳을 고치면 거울이 하나 더 있다
    (FROZEN_IDEAS ⑭). 화면으로 보고서야 알았다.
    """
    txt = _render(tmp_path, "index.html", "#trades-card")
    assert "확인 필요" in txt, f"못 믿을 금액을 그대로 보여준다:\n{txt[:600]}"
    assert "6,361,688" not in txt, txt[:600]
    assert "264.88" not in txt, f"못 믿을 체결가가 남아 있다:\n{txt[:600]}"
    # 대조군 — 멀쩡한 체결은 금액도 가격도 그대로 보여야 한다.
    assert "27,930원" in txt and "865,173" in txt, (
        f"정상 체결까지 가렸다:\n{txt[:600]}")
