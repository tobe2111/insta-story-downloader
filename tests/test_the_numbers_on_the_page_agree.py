"""같은 화면의 숫자들이 서로 맞지 않았다 (감사 275).

사장님 2026-08-17: *"실시간으로 페이지의 숫자들이 다 일치가 돼야 해."*

전수 대조했더니 두 곳이 어긋나 있었습니다.

**① 잔고 표 '합계' 줄이 스스로 안 맞았다.**

    합계   매입금액 271,221원   평가금액 997,198원   평가손익 −2,396원

매입금액 칸은 **현금을 빼고**, 평가금액 칸은 **현금을 넣고** 세고 있었습니다.
읽는 사람이 빼 보면 `997,198 − 271,221 = +725,977원 이익`이 나옵니다.

**② 한 화면에 '손익'이 둘 있었다.**

    한눈에·히어로   −2,802원   (자산 − 원금)
    잔고 합계       −2,396원   (평가 − 매입)

둘 다 맞는 값이고 정의가 다를 뿐인데, **이름이 같고 설명이 없으면** 읽는
사람은 하나가 틀렸다고 결론짓습니다. 차이 407원은 이미 낸 매매 수수료로,
계좌에서 빠져나가 어느 칸에도 남아 있지 않아 화면만 봐서는 찾을 수 없습니다.

**③ 준실시간 시세가 오면 잔고 표만 움직였다.** '한눈에'는 확정값에 머물러
있어서, 시세가 붙는 순간 같은 화면이 두 금액을 말하게 됩니다.

숫자를 억지로 맞추지는 않습니다 — 정의가 다른 값을 같게 만들면 그때부터
거짓말입니다. **왜 다른지를 화면에 적고, 같아야 할 것은 한 곳에서 계산해
여러 곳에 칠합니다**(㉞).
"""

from __future__ import annotations

import functools
import http.server
import json
import re
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 브라우저를 어디서 찾는지는 **한 곳에서만** 정한다(감사 278). 이 줄이
# 파일마다 컨테이너 전용 경로를 적고 있던 탓에, GitHub 러너에서는
# 일곱 파일의 화면 계약이 통째로 조용히 건너뛰어지고 있었다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _browser import block_external, chromium_or_skip  # noqa: E402



def _money(text: str) -> list[int]:
    """화면 글자에서 '1,234원'을 숫자로 뽑는다(음수 기호는 −와 - 둘 다)."""
    out = []
    for m in re.finditer(r"([−-])?([\d,]+)원", text):
        v = int(m.group(2).replace(",", ""))
        out.append(-v if m.group(1) else v)
    return out


@pytest.fixture(scope="module")
def ledger():
    pf = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    return pf["paper"]["portfolio:ALL"]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    root = tmp_path_factory.mktemp("agree")
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


@pytest.fixture(scope="module")
def browser(site):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chromium_or_skip())
        try:
            yield b
        finally:
            b.close()


@pytest.fixture()
def page(browser, site):
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    block_external(pg)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/index.html")
    pg.wait_for_timeout(2600)
    # 첫 화면은 세 질문에만 답하고 나머지는 접힌다(감사 282). 이 파일은
    # 접힌 자리의 숫자까지 대조하므로 펴고 읽는다 — 접힌 글자는
    # inner_text()에 들어오지 않는다.
    if pg.locator("#morebtn").count():
        pg.click("#morebtn")
        pg.wait_for_timeout(300)
    yield pg
    assert not errors, f"스크립트가 던졌다 — {errors}"
    pg.close()


# ── ① 자산은 화면 어디서나 같은 값인가 ──────────────────────────

def test_the_account_value_is_the_same_everywhere(page, ledger):
    """티커띠·히어로·잔고 합계가 같은 자산을 말해야 한다.

    ('한눈에' 카드는 사장님 지시(2026-08-18)로 내렸다 — 남은 자리끼리도
    갈라질 수 있으므로 검사는 그대로 산다.)
    """
    want = round(float(ledger["equity"]))
    places = {
        "티커띠": page.locator(".strip").inner_text(),
        "히어로 우측": page.locator("#proof").inner_text(),
        "잔고 합계": page.locator("#baltable").inner_text(),
    }
    for name, txt in places.items():
        assert want in _money(txt), (
            f"{name}에 자산 {want:,}원이 없다:\n{txt[:400]}")


def test_the_cash_and_holdings_agree_between_table_and_sidebar(page, ledger):
    """잔고 표와 사이드바가 장부와 같은 현금·보유를 말해야 한다."""
    cash = round(float(ledger["cash"]))
    heldv = round(sum(float(h["value"]) for h in ledger["holdings"]))
    got = _money(page.locator("#side-cash").inner_text())
    assert cash in got, f"사이드바에 현금 {cash:,}원이 없다: {got}"
    assert heldv in got, f"사이드바에 보유 {heldv:,}원이 없다: {got}"
    bal = _money(page.locator("#baltable").inner_text())
    assert cash in bal, f"잔고 표에 현금 {cash:,}원이 없다: {bal}"


# ── ② 잔고 표가 스스로 앞뒤가 맞는가 ────────────────────────────

def _total_row(page) -> list[str]:
    for row in page.locator("#baltable tbody tr").all():
        cells = [c.inner_text().strip() for c in row.locator("td").all()]
        if cells and cells[0].startswith("합계"):
            return cells
    raise AssertionError("합계 줄이 없다")


def test_the_total_row_subtracts_to_its_own_profit(page):
    """**이 줄이 실측 결함이다.** 매입 칸은 현금을 빼고 평가 칸은 넣고 있었다.

    빼 보면 +725,977원 '이익'이 나온다 — 어느 칸도 틀리지 않았는데
    줄 전체가 거짓말을 한다.
    """
    cells = _total_row(page)
    nums = [_money(c) for c in cells]
    cost = next(n[0] for n in nums if n and n[0] > 500_000)     # 넣은 돈
    flat = [v for n in nums for v in n]
    value = next(v for v in flat if 900_000 < v < 1_100_000 and v != cost)
    pnl = next(v for v in flat if abs(v) < 100_000)
    assert abs((value - cost) - pnl) <= 2, (
        f"합계 줄이 스스로 안 맞는다: {cost:,} → {value:,} 인데 손익 {pnl:,}")


def test_each_holding_plus_cash_makes_the_account(page, ledger):
    """종목 평가금액을 다 더하고 현금을 더하면 자산이 나와야 한다."""
    rows = page.locator("#baltable tbody tr").all()
    total = 0
    for row in rows:
        cells = [c.inner_text().strip() for c in row.locator("td").all()]
        if not cells or cells[0].startswith(("합계", "현금")):
            continue
        vals = _money(" ".join(cells))
        # 매입금액 · 평가금액 순으로 두 값이 있다 — 뒤엣것이 평가금액이다.
        assert len(vals) >= 2, cells
        total += vals[1]
    total += round(float(ledger["cash"]))
    assert abs(total - round(float(ledger["equity"]))) <= 5, (
        f"종목 평가 합 + 현금 = {total:,} ≠ 자산 {round(float(ledger['equity'])):,}")


# ── ③ 두 '손익'이 다르면 왜 다른지 말하는가 ─────────────────────

def test_two_different_profits_are_explained(page, ledger):
    """숫자를 억지로 맞추지 않는다 — **왜 다른지**를 화면에 적는다."""
    cost = sum(float(h["cost"]) for h in ledger["holdings"])
    val = sum(float(h["value"]) for h in ledger["holdings"])
    base = float(ledger["principal"])
    p_book, p_total = round(val - cost), round(float(ledger["equity"]) - base)
    if p_book == p_total:
        pytest.skip("두 손익이 같은 날 — 설명할 것이 없다")
    bridge = page.locator("#bal-bridge").inner_text()
    got = _money(bridge)
    assert p_book in got, f"표의 손익({p_book:,})을 안 짚는다:\n{bridge}"
    assert p_total in got, f"맨 위 손익({p_total:,})을 안 짚는다:\n{bridge}"
    assert "수수료" in bridge, f"차이의 정체를 말하지 않는다:\n{bridge}"
    # 다리가 실제로 맞는 금액을 말하는가 — 문장만 있고 숫자가 틀리면 더 나쁘다.
    # (화면은 실수를 한 번 반올림하고 여기서는 반올림한 값끼리 빼므로 ±1원.)
    gap = round(abs(p_total - p_book))
    assert any(abs(v - gap) <= 1 for v in got), f"차이 {gap:,}원을 안 말한다:\n{bridge}"


def test_the_bridge_is_quiet_when_there_is_nothing_to_explain(browser, site,
                                                              tmp_path):
    """대조군 — 두 손익이 같으면 다리 문장이 뜨면 안 된다.

    없으면 "항상 뭔가 다르다고 적는다"도 통과하고, 그러면 진짜 차이를
    구별할 수 없다.
    """
    root = tmp_path / "even"
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    # 원금 = 매입 + 현금 으로 맞춘다 → 수수료 유출이 0인 계좌.
    cost = sum(float(h["cost"]) for h in pf["holdings"])
    pf["principal"] = round(cost + float(pf["cash"]), 2)
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        pg = browser.new_page()
        block_external(pg)
        pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
        pg.wait_for_timeout(2400)
        bridge = pg.locator("#bal-bridge").inner_text()
        pg.close()
    finally:
        srv.shutdown()
    assert "수수료" not in bridge, f"차이가 없는데 수수료를 말한다:\n{bridge}"


# ── ④ 실시간 시세가 오면 **함께** 움직이는가 ────────────────────

BINANCE = "**/api/v3/ticker/24hr*"
QUOTES = "**/api/quotes*"


FAKE_FX = 1400.0


def _fake_quotes(page, drift=0.01):
    """코인 시세와 환율을 가짜로 물려 준다 — 컨테이너에서 거래소는 막혀 있다.

    ⚠️ '실시간이면 다 같이 움직여야 한다'는 요구는 **시세가 실제로 들어왔을
       때만** 검사할 수 있다. 시세가 없으면 두 자리 모두 조용해서, 갈라져
       있어도 검사가 통과한다 — 건너뛴 검사는 아무것도 지키지 않는다.

    ⚠️ **환율도 함께** 넣어야 한다. 코인은 USDT 호가라 원/달러가 없으면
       `markHoldings`가 값을 만들지 않는다(1.0으로 때우지 않는 규칙,
       감사 212). 코인만 넣고 검사를 돌리면 영영 건너뛴다.
    """
    # ⚠️ **보유가 코인뿐이라고 가정하지 않는다**(2026-08-19). 예전에는
    #    코인이 아닌 보유가 하나라도 있으면 검사가 그 자리에서 죽었다 —
    #    "이 하네스로는 합계가 안 찬다"고 스스로 적어 두고 그대로 뒀다.
    #    그러다 08-19 배치가 한국 주식 두 종목을 담는 순간 검사가 깨졌다.
    #    계좌 구성이 바뀌면 못 쓰게 되는 검사는, 하필 **구성이 바뀐 날**
    #    필요한데 없다. 이제 시장마다 알맞은 통화로 시세를 물려 준다.
    st = json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    hold = {h["key"]: h for h in st["paper"]["portfolio:ALL"]["holdings"]}
    assert hold, "보유가 하나도 없다 — 이 검사가 볼 것이 없다"
    # ⚠️ 값을 아무렇게나 넣으면 안 된다. 확정 자산과 **자릿수가 맞아야**
    #    화면이 합계를 낸다(감사 275의 환율 누락 방어). 장부의 평가금액에서
    #    거꾸로 계산해 '오늘 조금 오른' 시세를 만든다.
    body, quotes = [], {"KRW=X": {"price": FAKE_FX, "change_pct": 0.0,
                                  "delayed": False}}
    for k, h in hold.items():
        qty = float(h["quantity"])
        if not qty:
            continue
        market, ticker = k.split(":", 1)
        # 원화 종목은 장부 금액이 곧 그 종목의 통화다. 코인·미국 주식은
        # 달러 호가라 환율로 되돌려야 화면이 다시 곱했을 때 맞는다.
        unit = float(h["value"]) / qty * (1.0 + drift)
        if market != "kr_stock":
            unit /= FAKE_FX
        if market == "crypto":
            body.append({"symbol": ticker.replace("/", ""),
                         "lastPrice": f"{unit:.8f}",
                         "priceChangePercent": "1.0"})
        else:
            # 워커에 가는 것은 **티커**다(장부 키가 아니다 — 감사 229).
            quotes[ticker] = {"price": unit, "change_pct": 1.0,
                              "delayed": False}
    page.route(BINANCE, lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(body)))
    page.route(QUOTES, lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"quotes": quotes})))


def test_the_live_total_appears_in_both_places_at_once(browser, site):
    """준실시간 합계는 **한 곳에서 계산해 여러 곳에 칠한다.**

    자리는 지금 둘이다: 잔고 합계 줄(.lvv)과 표 아래 참고 줄(#live-note).
    ('한눈에' 카드의 세 번째 자리는 사장님 지시(2026-08-18)로 화면과 함께
    내렸다.) 한쪽만 움직이면 같은 화면이 두 금액을 말하게 된다.
    """
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    block_external(pg)
    _fake_quotes(pg)
    pg.goto(f"{site}/index.html")
    pg.wait_for_timeout(3000)
    nodes = pg.locator('.lvv[data-k="__total__"]')
    assert nodes.count() >= 1, "잔고 합계 줄에 준실시간 자리가 없다"
    texts = [nodes.nth(i).inner_text().strip() for i in range(nodes.count())]
    note = pg.locator("#live-note").inner_text().strip()
    pg.close()
    shown = [t for t in texts if t]
    assert len(shown) == len(texts), (
        f"준실시간 합계가 일부 자리에만 찍혔다 — 화면이 두 금액을 말한다: {texts}")
    assert note, "잔고 표는 움직였는데 참고 줄(#live-note)은 조용하다"
    # 두 자리가 **같은 금액**을 말해야 한다 — 문구는 달라도 숫자는 하나다.
    amounts = {tuple(sorted(_money(t))) for t in shown}
    assert len(amounts) == 1, f"준실시간 자리끼리 다른 값을 말한다: {shown}"
    live_amt = max(_money(shown[0]))
    assert live_amt in _money(note), (
        f"참고 줄이 다른 금액을 말한다: lvv {shown[0]!r} vs note {note!r}")
    assert "확정" in shown[0] and "확정" in note, (
        f"확정값과 다른 숫자인데 그 말이 없다: {shown[0]!r} / {note!r}")


def test_the_live_number_never_pretends_to_be_the_ledger(page):
    """준실시간 값은 **반드시 라벨과 함께** 나가야 한다.

    라벨 없이 큰 숫자만 바뀌면, 수익률·낙폭이 그 값으로 계산된다고 읽힌다.
    """
    for i in range(page.locator('.lvv[data-k="__total__"]').count()):
        html = page.locator('.lvv[data-k="__total__"]').nth(i).inner_html()
        if html.strip():
            assert "확정" in html and "판단에는 쓰지 않" in html, html


def test_a_live_total_with_a_missing_rate_is_not_shown(browser, site, ledger):
    """자릿수가 다른 준실시간 합계는 **라벨을 붙여도 내보내지 않는다.**

    환율이 빠지면 코인 평가액이 1,400배로 튄다(감사 212가 그 사고였다).
    "지금 35,969,655원"에 '참고'라고 적어도 100만원 계좌에서는 거짓이다.
    """
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    block_external(pg)
    _fake_quotes(pg, drift=35.0)          # 확정값의 36배 — 환율 누락과 같은 모양
    pg.goto(f"{site}/index.html")
    pg.wait_for_timeout(3000)
    nodes = pg.locator('.lvv[data-k="__total__"]')
    texts = [nodes.nth(i).inner_text().strip() for i in range(nodes.count())]
    texts.append(pg.locator("#live-note").inner_text().strip())
    pg.close()
    assert texts and all(t for t in texts), f"아무 말도 안 한다: {texts}"
    # 잔고 줄과 참고 줄이 **같은 판정**을 해야 한다 — 한 곳만 숨기면 더 나쁘다.
    for t in texts:
        assert "표시하지 않습니다" in t, f"터무니없는 값을 그대로 보여준다: {t}"
        assert "35,969,655" not in t and "환율" in t, t
