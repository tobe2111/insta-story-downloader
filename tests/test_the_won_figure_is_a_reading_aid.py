"""원화 환산이 성적을 물들이지 않는가 (감사 312).

사장님 지시(2026-08-24): *"각 페이지 당 최종 수익 결과 한국돈으로도
알려줘."*

맞는 지적이었다. 100만 챌린지는 원화로 나오는데 실험 세 트랙은 달러·USDT
로만 나왔다. "9,983 USD"는 한국에서 사는 사람에게 바로 와닿지 않는다.

■ 이 검사가 가장 무서워하는 것

감사 212·254가 이 저장소에서 가장 비쌌던 사고다. 한 계좌 안에 원화와
달러가 섞여서, META를 달러 시가(596.98)로 사고 원화 종가(832,868)로
평가하는 바람에 **100만원 계좌가 7,249만원으로 찍혔다(+7,150%)**.

그래서 원화를 덧붙이는 이 작업은 그 사고의 재발 지점을 새로 만드는
일이다. 아래 검사들은 전부 "장부는 그대로인가"를 지킨다.

■ 지켜야 할 것

  · **시드와 지금 자산을 같은 환율로 바꾼다.** 시드를 옛 환율로 바꾸면
    환차손익이 성적에 섞인다 — 이 실험은 환위험을 진 적이 없다. 달러
    계좌 안에서만 사고팔았다. 원/달러가 3% 오른 날 "실험이 3% 벌었다"고
    적으면 하지 않은 일을 했다고 말하는 것이다.
  · **퍼센트 수익률은 안 바뀐다.** 위 규칙의 검산이다.
  · **모르면 비운다.** 환율을 못 받으면 None이고, 화면이 그렇게 적는다.
    1.0으로 대신하면 1만 달러가 1만 원이 된다.
  · **USDT를 달러로 친 사실을 밝힌다.** 연동이 깨진 적이 있다(2023-03,
    한때 0.97). 조용히 1:1로 치면 사실이 아닌 주장을 숫자로 파는 것이다.
  · **장부의 통화는 그대로다.** 원화는 덧붙인 값이지 계좌 단위가 아니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.krw import krw_view  # noqa: E402

RATE = 1380.0


# ══ ① 환율이 성적에 섞이지 않는다 ═════════════════════════════════

def test_the_percent_return_is_unchanged_by_the_conversion():
    """이 파일에서 가장 중요한 검사.

    시드와 자산을 같은 환율로 바꾸면 퍼센트가 그대로여야 한다. 안 그러면
    환차손익이 실험 성적에 섞인 것이다.
    """
    v = krw_view(9983.35, 10_000.0, "USD", rate=RATE)
    in_won = v["equity"] / v["start_cash"] - 1.0
    in_usd = 9983.35 / 10_000.0 - 1.0
    assert in_won == pytest.approx(in_usd, abs=1e-6), (
        f"원화로 보니 {in_won:.6f}, 달러로는 {in_usd:.6f} — 환율이 성적에 "
        "섞였다")


@pytest.mark.parametrize("rate", [900.0, 1380.0, 1800.0])
def test_the_percent_return_is_the_same_at_any_rate(rate):
    """대조군 — 환율이 얼마든 퍼센트는 같아야 한다.

    하나의 환율만 보면 "우연히 맞았다"를 구별할 수 없다.
    """
    v = krw_view(11_000.0, 10_000.0, "USD", rate=rate)
    assert v["equity"] / v["start_cash"] - 1.0 == pytest.approx(0.10, abs=1e-6)


def test_the_seed_is_converted_at_todays_rate_too():
    """시드도 오늘 환율로 바꾼다 — 옛 환율을 쓰면 환차손익이 생긴다."""
    v = krw_view(10_000.0, 10_000.0, "USD", rate=RATE)
    assert v["start_cash"] == pytest.approx(10_000.0 * RATE)
    assert v["pnl"] == pytest.approx(0.0), (
        "본전인데 손익이 0이 아니다 — 시드와 자산의 환율이 다르다")


def test_a_loss_stays_a_loss_and_a_gain_stays_a_gain():
    assert krw_view(9_000.0, 10_000.0, "USD", rate=RATE)["pnl"] < 0
    assert krw_view(11_000.0, 10_000.0, "USD", rate=RATE)["pnl"] > 0


# ══ ② 모르면 비운다 ═══════════════════════════════════════════════

@pytest.mark.parametrize("rate", [None, 0, -5, "많이", float("nan")])
def test_an_unusable_rate_produces_nothing(rate):
    """1.0으로 대신하면 1만 달러가 1만 원이 된다."""
    assert krw_view(10_000.0, 10_000.0, "USD", rate=rate) is None


@pytest.mark.parametrize("equity", [None, "x", float("nan")])
def test_an_unreadable_equity_produces_nothing(equity):
    assert krw_view(equity, 10_000.0, "USD", rate=RATE) is None


def test_a_won_account_is_not_converted_again():
    """이미 원화인 계좌를 또 곱하면 자산이 1,380배가 된다."""
    assert krw_view(1_000_000, 1_000_000, "KRW", rate=RATE) is None


def test_an_unknown_currency_is_not_guessed_to_be_dollars():
    """모르는 통화를 달러로 넘겨짚지 않는다 — 엔이면 10배쯤 틀린다."""
    assert krw_view(10_000.0, 10_000.0, "JPY", rate=RATE) is None


# ══ ③ USDT를 달러로 친 사실을 밝힌다 ══════════════════════════════

def test_it_admits_when_it_assumed_the_peg():
    assert krw_view(10_000.0, 10_000.0, "USDT", rate=RATE)["assumed_peg"] is True


def test_a_dollar_account_claims_no_peg_assumption():
    """대조군 — 달러 계좌에 '가정했다'를 붙이면 없는 한계를 지어낸 것이다."""
    assert krw_view(10_000.0, 10_000.0, "USD", rate=RATE)["assumed_peg"] is False


# ══ ④ 트레이딩 모듈은 환율을 모른다 (감사 254의 하드 경계) ════════
#
# ⚠️ 처음에 나는 세 트랙의 리포트 작성기 안에서 환산했다. 기존 검사
#    (test_the_currency_never_mixes)가 즉시 걸렸고, **그 검사가 맞았다.**
#
#    감사 254: META를 달러 시가(596.98)로 사고 원화 종가(832,868)로
#    평가하는 바람에 100만원 계좌가 7,249만원(+7,150%)으로 찍혔다.
#    환산이 필요한 자리를 두 군데에 나눠 적으면 반드시 한 곳이 빠진다 —
#    그래서 체결·평가가 도는 모듈은 **원화라는 말을 아예 모르게** 둔다.
#
#    아래 검사는 그 경계를 세 트랙 **모두**에 건다. 원래는 코인 트랙에만
#    걸려 있었다 — 고친 결함은 형제를 찾기 전까지 고친 게 아니다(⑭).

_TRADING_MODULES = [
    "quant/live/intraday_us.py",
    "quant/live/intraday_challenger.py",
    "quant/live/futures_challenger.py",
]


@pytest.mark.parametrize("path", _TRADING_MODULES)
def test_a_trading_module_does_not_know_about_won(path):
    """환산을 **하는** 식별자가 없어야 한다.

    ⚠️ 한국어 낱말 '원화'는 막지 않는다. 이 파일들에는 "본 계좌(원화)와
       절대 섞지 않는다" 같은 주석이 있고, 그건 경계를 **지키는** 문장이지
       어기는 코드가 아니다. 낱말을 막으면 경계를 설명한 주석까지 지우게
       되고, 그러면 다음 사람이 왜 이 경계가 있는지 모른다.
       기존 검사(test_the_currency_never_mixes)와 같은 규칙이다.
    """
    low = (ROOT / path).read_text("utf-8").lower()
    for ident in ("krw", "usdkrw", "to_krw"):
        assert ident not in low, (
            f"{path}가 환율을 안다('{ident}') — 감사 254의 재발 지점이다. "
            "환산은 장부가 다 쓰인 뒤(quant/reporting/krw_attach.py)에 한다")


# ══ ⑤ 뒷단계가 공개 장부에만 덧붙인다 ═════════════════════════════

_LEDGERS = {"intraday.json": "USDT", "intraday_us.json": "USD",
            "futures.json": "USDT"}


def _docs(tmp_path, **over):
    d = tmp_path / "docs"
    d.mkdir(parents=True, exist_ok=True)
    for name, cur in _LEDGERS.items():
        body = {"equity": 9_500.0, "start_cash": 10_000.0, "currency": cur}
        body.update(over.get(name) or {})
        (d / name).write_text(json.dumps(body, ensure_ascii=False),
                              encoding="utf-8")
    return d


def _read(d, name):
    return json.loads((d / name).read_text("utf-8"))


@pytest.mark.parametrize("name", sorted(_LEDGERS))
def test_the_attach_step_adds_the_won_block(name, tmp_path):
    from quant.reporting.krw_attach import attach
    d = _docs(tmp_path)
    attach(str(d), rate=RATE)
    k = _read(d, name).get("krw")
    assert k and k["rate"] == pytest.approx(RATE), f"{name}: 원화가 안 붙었다"
    assert k["start_cash"] == pytest.approx(10_000.0 * RATE)
    assert k["pnl"] < 0, "손실인데 원화 손익이 음수가 아니다"


@pytest.mark.parametrize("name", sorted(_LEDGERS))
def test_the_attach_step_leaves_the_account_currency_alone(name, tmp_path):
    """⚠️ 이 검사가 감사 254를 막는다 — 자산이 원화로 **바뀌면** 안 된다."""
    from quant.reporting.krw_attach import attach
    d = _docs(tmp_path)
    attach(str(d), rate=RATE)
    body = _read(d, name)
    assert body["equity"] == pytest.approx(9_500.0), (
        f"{name}: 자산이 원화로 덮어써졌다({body['equity']}) — 장부가 오염됐다")
    assert body["start_cash"] == pytest.approx(10_000.0)
    assert body["currency"] == _LEDGERS[name], "통화 표기가 바뀌었다"


def test_a_missing_rate_leaves_the_ledger_untouched(tmp_path):
    """대조군 — 환율이 없으면 아무것도 안 붙이고 원본을 그대로 둔다."""
    from quant.reporting.krw_attach import attach
    d = _docs(tmp_path)
    before = {n: _read(d, n) for n in _LEDGERS}
    out = attach(str(d), rate=None, fetch=lambda *a, **k: None)
    for n in _LEDGERS:
        assert "krw" not in _read(d, n), f"{n}: 환율도 없이 원화를 지어냈다"
        assert _read(d, n) == before[n], f"{n}: 원본이 변형됐다"
        assert "환율" in out[n]


def test_a_missing_ledger_is_not_an_error(tmp_path):
    """아직 안 돈 트랙이 있어도 나머지는 붙는다 — 하나가 전부를 막지 않는다."""
    from quant.reporting.krw_attach import attach
    d = _docs(tmp_path)
    (d / "futures.json").unlink()
    out = attach(str(d), rate=RATE)
    assert "krw" in _read(d, "intraday.json")
    assert "없음" in out["futures.json"]


def test_the_command_the_batch_calls_actually_attaches(tmp_path, monkeypatch):
    """배치가 부르는 그 명령을 그대로 부른다.

    함수만 검사하면 "명령 이름이 바뀌어 배치가 매일 조용히 실패한다"를
    놓친다(감사 289가 그 모양이었다).
    """
    from quant.cli import main
    d = _docs(tmp_path)
    monkeypatch.setattr("quant.data.fx.usdkrw", lambda *a, **k: RATE)
    main(["krw-attach", "--docs", str(d)])
    assert _read(d, "intraday.json").get("krw"), "명령이 원화를 안 붙였다"


def test_the_batch_actually_runs_the_command():
    """⚠️ 명령이 멀쩡해도 **배치가 안 부르면** 사이트에는 영영 안 나온다."""
    y = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "krw-attach" in y, "배치가 원화 환산을 안 부른다"


# ══ ⑤ 화면이 '환산'이라고 말한다 ══════════════════════════════════
#
# ⚠️ 숫자만 크게 적고 '환산'이라 안 하면, 읽는 사람은 이 계좌가 원화
#    계좌인 줄 안다. 그 오해가 곧 감사 212의 사고 모양이다.

import functools  # noqa: E402
import http.server  # noqa: E402
import shutil  # noqa: E402
import socketserver  # noqa: E402
import threading  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))

_PAGES = {"us.html": ("intraday_us.json", "USD"),
          "intraday.html": ("intraday.json", "USDT"),
          "futures.html": ("futures.json", "USDT")}


def _render(tmp_path, page, krw):
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright

    root = tmp_path / page.replace(".", "_")
    shutil.copytree(ROOT / "docs", root, dirs_exist_ok=True)
    led = json.loads((root / _PAGES[page][0]).read_text("utf-8"))
    led["krw"] = krw
    led["currency"] = _PAGES[page][1]
    (root / _PAGES[page][0]).write_text(json.dumps(led, ensure_ascii=False),
                                        encoding="utf-8")

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chromium_or_skip())
        pg = b.new_page()
        block_external(pg)
        try:
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page}")
            pg.wait_for_timeout(1500)
            el = pg.locator("#krw")
            return el.inner_text() if el.count() else ""
        finally:
            pg.close()
            b.close()
            srv.shutdown()


_GOOD = {"rate": 1380.0, "equity": 13_777_023, "start_cash": 13_800_000,
         "pnl": -22_977, "assumed_peg": False}


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_the_page_shows_the_won_amount(page, tmp_path):
    t = _render(tmp_path, page, _GOOD)
    assert "13,777,023원" in t, f"{page}: 원화 자산을 안 적는다 ({t!r})"
    assert "22,977원" in t, f"{page}: 원화 손익을 안 적는다"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_the_page_calls_it_a_conversion_not_the_account(page, tmp_path):
    """'환산'이라고 말해야 한다 — 안 그러면 원화 계좌로 읽힌다."""
    t = _render(tmp_path, page, _GOOD)
    assert "환산" in t, f"{page}: 환산이라고 말하지 않는다"
    assert "환율 변동은 이 실험의 성적에 들어가지 않습니다" in t, (
        f"{page}: 환율이 성적에 안 섞인다는 사실을 안 적는다")
    assert "1,380원" in t, f"{page}: 어떤 환율을 썼는지 안 적는다"


@pytest.mark.parametrize("page", sorted(_PAGES))
def test_the_page_stays_quiet_when_the_rate_is_missing(page, tmp_path):
    """대조군 — 환율이 없으면 숫자를 지어내지 않고 그 사실을 적는다."""
    t = _render(tmp_path, page, None)
    assert "원화 환산을 건너뜁니다" in t, f"{page}: 환율 없음을 안 알린다"
    assert "원" not in t.replace("원화", "").replace("원/달러", ""), (
        f"{page}: 환율이 없는데 원화 금액을 적었다 ({t!r})")


def test_a_usdt_page_admits_the_peg_assumption(tmp_path):
    t = _render(tmp_path, "futures.html", {**_GOOD, "assumed_peg": True})
    assert "USDT는 1달러로 가정했습니다" in t


def test_a_dollar_page_does_not_claim_a_peg_assumption(tmp_path):
    """대조군 — 달러 계좌에 붙이면 없는 한계를 지어낸 것이다."""
    t = _render(tmp_path, "us.html", _GOOD)
    assert "USDT는 1달러로 가정했습니다" not in t
