"""국내주식 실거래 브로커 둘 — 응답이 어긋난 날 무슨 일이 벌어지는가 (감사 182).

훑은 파일 — `broker/kiwoom_live.py`(전수조사 마지막 파일) · 형제로 함께 고친
`broker/kr_live.py`.

**결함 셋을 찾았다. 셋 다 실제 돈이 오가는 경로다.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① **모르는 주문 방향의 기본값이 '매도'였다.**

    api_id = self.TR_BUY if side == "buy" else self.TR_SELL

정확히 `"buy"`가 아닌 **무엇이든** — `"BUY"`, `"Buy"`, `"long"`, 오타 —
조용히 **매도 주문**이 되어 나간다. 사는 줄 알고 팔린다. 지금 상위 로직
(`base.rebalance_to_weight`)은 소문자만 만들지만, `market_order`는 Broker의
**공개 API**다. 수동 호출·다른 하네스·앞으로 들어올 코드가 대문자를 넘기면
그날 계좌가 반대로 움직인다. **기본값이 파괴적인 쪽이면 안 된다.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
② **보유 목록 키가 없으면 '0주 보유'라고 답했다.**

    for item in data.get(self.HOLDINGS_KEY, []) or []:
        ...
    return Position(symbol, 0.0, 0.0)      # 키가 통째로 없어도 여기로 온다

이건 **감사 55와 같은 결함**이다. 그때는 us_live가 401·429·500·타임아웃을
전부 '0주'로 읽었다. 여기서는 응답은 멀쩡히 왔는데 **키 이름이 달라졌을 때**
같은 일이 벌어진다. 실거래에서 보유를 0으로 읽으면 상위 로직은 목표 비중만큼
**다시 사서** 포지션이 두 배가 된다. 20종목이면 스무 번.

특히 고약한 이유: `kiwoom_live.py`는 **첫 줄부터** "응답 필드명은 개정될 수
있다"고 적어 두고 필드명을 오버라이드 가능한 속성으로 뒀다. 즉 **이름이
어긋나는 일이 실제로 일어난다는 전제**로 만들어 놓고, 어긋났을 때의 답이
가장 위험한 쪽이었다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
③ **예수금 필드가 없으면 '현금 0'이라고 답했다.**

현금 0은 보수적으로 보이지만 아니다. 상위 로직은 현금으로 평가금액을 만들고
거기에 목표 비중을 곱한다. 0으로 읽히면 평가금액이 쪼그라들어 **보유분을
팔라는 지시**가 나온다. 필드명 하나가 바뀐 날 계좌가 통째로 청산될 수 있다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
공통 규칙 하나로 정리된다 — **'모름'은 숫자가 아니다.** 키가 **있는데**
그 안에 이 종목이 없으면 그건 진짜 '보유 없음'이다. 키가 **없으면** 우리는
모르는 것이고, 모르면 매매를 하지 않아야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.broker.kiwoom_live as K  # noqa: E402
import quant.broker.kr_live as R  # noqa: E402
from quant.broker.kiwoom_live import KiwoomBroker  # noqa: E402


@pytest.fixture()
def kiwoom(monkeypatch):
    for k, v in (("KIWOOM_APP_KEY", "ak"), ("KIWOOM_SECRET", "sk"),
                 ("KIWOOM_ACCOUNT", "1234")):
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(K, "post_json",
                        lambda *a, **k: {"token": "t", "expires_in": 86400})
    b = KiwoomBroker(paper=True)
    b._token, b._token_expiry = "t", 1e18
    return b


def _serve(monkeypatch, payload, sent=None):
    """잔고/주문 응답을 고정하고, 보낸 요청을 sent에 모은다."""
    def _post(url, headers=None, body=None):
        if sent is not None:
            sent.append({"url": url, "headers": headers or {}, "body": body})
        return payload(url) if callable(payload) else payload

    monkeypatch.setattr(K, "post_json", _post)


GOOD = {"acnt_evlt_remn_indv_tot": [{"stk_cd": "A005930", "rmnd_qty": "10",
                                     "pur_pric": "70,000"}],
        "prsm_dpst_aset_amt": "1,234,567"}


# ── ① 모르는 방향이 매도가 되지 않는가 ────────────────────────


@pytest.mark.parametrize("bad", ["long", "매수", "", "sel", "b", "SELL_ALL"])
def test_an_unknown_side_never_becomes_a_sell_order(kiwoom, monkeypatch, bad):
    sent: list = []
    _serve(monkeypatch, {"return_code": 0, "ord_no": "1"}, sent)
    with pytest.raises(ValueError, match="주문 방향"):
        kiwoom.market_order("005930", bad, 10, 70000.0)
    assert sent == [], f"거절해야 할 방향인데 주문이 나갔다: {sent}"


@pytest.mark.parametrize("side,api", [("buy", KiwoomBroker.TR_BUY),
                                      ("sell", KiwoomBroker.TR_SELL),
                                      ("BUY", None), ("Sell", None)])
def test_the_two_real_sides_route_to_their_own_api_id(kiwoom, monkeypatch,
                                                      side, api):
    """대조군 — 대소문자는 받아 주되 방향은 정확히 그 방향이어야 한다."""
    want = api or (KiwoomBroker.TR_BUY if side.lower() == "buy"
                   else KiwoomBroker.TR_SELL)
    sent: list = []
    _serve(monkeypatch, {"return_code": 0, "ord_no": "7"}, sent)
    got = kiwoom.market_order("005930", side, 10, 70000.0)
    assert sent[-1]["headers"]["api-id"] == want, (
        f"{side} 주문이 {sent[-1]['headers']['api-id']}로 나갔다 — 기대 {want}")
    assert got.side == side.lower()
    assert got.status == "accepted" and got.filled_quantity == 0.0


def test_a_rejected_order_is_not_reported_as_accepted(kiwoom, monkeypatch):
    _serve(monkeypatch, {"return_code": 9, "return_msg": "잔고 부족"})
    got = kiwoom.market_order("005930", "buy", 10, 70000.0)
    assert got.status == "잔고 부족", got


def test_a_sub_share_order_is_skipped_not_rounded_up(kiwoom, monkeypatch):
    sent: list = []
    _serve(monkeypatch, {"return_code": 0}, sent)
    got = kiwoom.market_order("005930", "buy", 0.4, 70000.0)
    assert got.status == "skipped" and got.quantity == 0.0
    assert sent == [], "0주 주문이 브로커까지 나갔다"


# ── ② 보유 목록 키가 없으면 '없음'이 아니라 '모름'인가 ────────


def test_a_renamed_holdings_key_is_an_error_not_an_empty_account(kiwoom,
                                                                 monkeypatch):
    """보유를 0으로 읽으면 상위 로직이 목표만큼 다시 사서 포지션이 두 배가 된다."""
    _serve(monkeypatch, {"acnt_evlt_remn_XXXX": [], "prsm_dpst_aset_amt": "1"})
    with pytest.raises(RuntimeError, match="보유목록"):
        kiwoom.get_position("005930")


def test_a_symbol_missing_from_a_present_list_really_is_zero(kiwoom,
                                                             monkeypatch):
    """대조군 — 키가 있는데 이 종목이 없으면 그건 진짜 '보유 없음'이다."""
    _serve(monkeypatch, GOOD)
    assert kiwoom.get_position("000660").quantity == 0.0

    kiwoom._balance_cache = None
    _serve(monkeypatch, {"acnt_evlt_remn_indv_tot": [],
                         "prsm_dpst_aset_amt": "1"})
    assert kiwoom.get_position("005930").quantity == 0.0


def test_a_real_holding_is_read_with_its_commas_stripped(kiwoom, monkeypatch):
    _serve(monkeypatch, GOOD)
    pos = kiwoom.get_position("005930")
    assert pos.quantity == 10.0
    assert pos.avg_price == 70000.0, "콤마가 붙은 단가를 못 읽었다"


# ── ③ 예수금 필드가 없으면 '현금 0'이 아닌가 ──────────────────


def test_a_renamed_cash_field_is_an_error_not_zero_cash(kiwoom, monkeypatch):
    """현금 0은 보수적이지 않다 — 평가금액이 쪼그라들어 청산 지시가 나간다."""
    _serve(monkeypatch, {"acnt_evlt_remn_indv_tot": [], "dpst_XXXX": "1"})
    with pytest.raises(RuntimeError, match="예수금"):
        kiwoom.get_cash()


def test_real_cash_is_read_with_its_commas_stripped(kiwoom, monkeypatch):
    _serve(monkeypatch, GOOD)
    assert kiwoom.get_cash() == 1234567.0


def test_a_genuinely_empty_account_reads_zero(kiwoom, monkeypatch):
    """대조군 — 필드가 있고 값이 0이면 그건 진짜 0원이다."""
    _serve(monkeypatch, {"acnt_evlt_remn_indv_tot": [],
                         "prsm_dpst_aset_amt": "0"})
    assert kiwoom.get_cash() == 0.0


# ── 형제: KIS(kr_live)도 같은 자리에서 같은 답을 하는가 ────────


@pytest.fixture()
def kis(monkeypatch):
    for k, v in (("KIS_APP_KEY", "ak"), ("KIS_APP_SECRET", "sk"),
                 ("KIS_CANO", "12345678"), ("KIS_ACNT_PRDT_CD", "01")):
        monkeypatch.setenv(k, v)
    b = R.KISBroker(paper=True)
    b._token, b._token_expiry = "t", 1e18
    return b


def test_the_kis_broker_makes_the_same_three_answers(kis, monkeypatch):
    """증권사를 갈아탄 날 한쪽만 규격이 살아 있으면 그게 더 나쁘다(⑭)."""
    monkeypatch.setattr(R, "get_json", lambda *a, **k: {"output_XXXX": []})
    with pytest.raises(RuntimeError, match="보유목록"):
        kis.get_position("005930")

    kis._balance_cache = None
    with pytest.raises(RuntimeError, match="output2"):
        kis.get_cash()

    kis._balance_cache = None
    monkeypatch.setattr(R, "get_json", lambda *a, **k: {
        "output1": [{"pdno": "005930", "hldg_qty": "10",
                     "pchs_avg_pric": "70000"}],
        "output2": [{"dnca_tot_amt": "1234567"}]})
    assert kis.get_position("005930").quantity == 10.0
    assert kis.get_position("000660").quantity == 0.0
    assert kis.get_cash() == 1234567.0


@pytest.mark.parametrize("bad", ["long", "매수", "", "sel"])
def test_the_kis_broker_also_refuses_an_unknown_side(kis, monkeypatch, bad):
    sent: list = []
    monkeypatch.setattr(R, "post_json",
                        lambda *a, **k: sent.append(a) or {"rt_cd": "0"})
    with pytest.raises(ValueError, match="주문 방향"):
        kis.market_order("005930", bad, 10, 70000.0)
    assert sent == [], f"거절해야 할 방향인데 주문이 나갔다: {sent}"


def test_the_kis_broker_routes_upper_case_to_the_right_tr_id(kis, monkeypatch):
    """대조군 — 대문자는 받아 주되 방향이 뒤집히면 안 된다."""
    seen: list = []

    def _post(url, headers=None, body=None):
        seen.append(headers.get("tr_id"))
        return {"rt_cd": "0", "output": {"ODNO": "1"}}

    monkeypatch.setattr(R, "post_json", _post)
    kis.market_order("005930", "BUY", 10, 70000.0)
    kis.market_order("005930", "Sell", 10, 70000.0)
    # hashkey 발급도 같은 post_json을 지나므로 tr_id 없는 호출은 걸러낸다
    assert [t for t in seen if t] == [R.KISBroker._TR_BUY["paper"],
                                      R.KISBroker._TR_SELL["paper"]], seen


# ── 두 브로커의 공통 계약 ─────────────────────────────────────


def test_both_korean_brokers_declare_whole_share_lots():
    from quant.broker.specs import MarketSpec

    for spec in (KiwoomBroker.market_spec(None, "005930"),
                 R.KISBroker.market_spec(None, "005930")):
        assert isinstance(spec, MarketSpec)
        assert spec.min_qty == 1.0 and spec.qty_step == 1.0


def test_missing_credentials_refuse_to_build_a_broker(monkeypatch):
    for k in ("KIWOOM_APP_KEY", "KIWOOM_SECRET", "KIWOOM_ACCOUNT"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="환경변수"):
        KiwoomBroker(paper=True)


def test_paper_and_real_go_to_different_hosts(kiwoom, monkeypatch):
    assert kiwoom.base == KiwoomBroker.MOCK_URL
    for k, v in (("KIWOOM_APP_KEY", "ak"), ("KIWOOM_SECRET", "sk"),
                 ("KIWOOM_ACCOUNT", "1234")):
        monkeypatch.setenv(k, v)
    assert KiwoomBroker(paper=False).base == KiwoomBroker.REAL_URL
    assert KiwoomBroker.MOCK_URL != KiwoomBroker.REAL_URL


def test_the_token_is_refreshed_before_it_expires(kiwoom, monkeypatch):
    """만료를 안 쫓으면 24시간 뒤 모든 주문이 401로 죽는다."""
    calls = {"n": 0}

    def _post(url, headers=None, body=None):
        calls["n"] += 1
        return {"token": f"t{calls['n']}", "expires_in": 3600}

    monkeypatch.setattr(K, "post_json", _post)
    kiwoom._token, kiwoom._token_expiry = None, 0.0
    assert kiwoom._get_token() == "t1"
    assert kiwoom._get_token() == "t1", "유효한 토큰을 매번 새로 받는다"
    import time as _t
    assert kiwoom._token_expiry <= _t.time() + 3600 - 300 + 1, (
        "만료 직전 여유(5분)를 안 두면 경계에서 401이 난다")


# ── 형제 둘이 더 있었다 — 코인·미국주식 (감사 199) ─────────────
#
# 감사 182에서 국내 브로커 둘에 이 검사를 넣으면서 "형제를 둘 다 고친다"고
# 적었다. 그런데 형제는 넷이었다. `crypto_live.py`와 `us_live.py`가 같은
# 자리에서 같은 답(0)을 하고 있었고, 그 사이 감사 192에서 두 파일의
# `normalize_side`는 고쳤으면서 **바로 몇 줄 위의 이 자리는 안 봤다.**
#
# 그래서 판정을 `broker/base.require_field` 하나로 모았다. 아래 검사는
# **네 브로커 전부**가 같은 답을 하는지 본다 — 한 곳만 고쳐진 상태가
# 넷 다 안 고쳐진 것보다 알아채기 어렵기 때문이다.


@pytest.fixture()
def ccxt_broker():
    import quant.broker.crypto_live as CL

    def _make(balance):
        class _Client:
            def fetch_balance(self):
                return balance
        return CL.CryptoLiveBroker(client=_Client(), quote="USDT")
    return _make


@pytest.fixture()
def alpaca(monkeypatch):
    import quant.broker.us_live as U

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")

    def _make(account):
        monkeypatch.setattr(U, "get_json", lambda *a, **k: account)
        return U.AlpacaBroker(paper=True)
    return _make


def test_a_renamed_ccxt_balance_key_is_an_error_not_zero(ccxt_broker):
    """`free`·`total`이 없으면 '잔고 0'이 아니라 '모름'이다."""
    with pytest.raises(RuntimeError, match="free"):
        ccxt_broker({"balances": {"USDT": 5000}, "total": {}}).get_cash()
    with pytest.raises(RuntimeError, match="total"):
        ccxt_broker({"free": {"USDT": 5000}}).get_position("BTC/USDT")


def test_a_currency_missing_from_a_present_ccxt_key_really_is_zero(ccxt_broker):
    """대조군 — 거래소는 잔고 0인 통화를 응답에서 **생략하는 것이 정상**이다.

    이 대조군이 없으면 위 검사는 "무엇이든 거절하는 브로커"도 통과시키고,
    그러면 잔고가 진짜 0인 평범한 날 매매가 통째로 멈춘다.
    """
    b = ccxt_broker({"free": {}, "total": {}})
    assert b.get_cash() == 0.0
    assert b.get_position("BTC/USDT").quantity == 0.0
    b2 = ccxt_broker({"free": {"USDT": 5000}, "total": {"BTC": 0.5}})
    assert b2.get_cash() == 5000.0
    assert b2.get_position("BTC/USDT").quantity == 0.5


def test_a_renamed_alpaca_equity_field_cannot_empty_the_account(alpaca):
    """가장 날카로운 자리 — `equity`가 0이면 **전 종목 청산 지시**가 나간다.

    `equity()`는 MultiTrader·RobustBroker가 총자산을 찾을 때 부르는 값이다.
    0으로 읽히면 모든 종목의 목표가 (비중 × 0) = 0주가 된다.
    """
    with pytest.raises(RuntimeError, match="equity"):
        alpaca({"cash": "5000", "portfolio_value": "12000"}).equity()
    with pytest.raises(RuntimeError, match="cash"):
        alpaca({"cash_balance": "5000", "equity": "12000"}).get_cash()

    # 대조군 — 멀쩡한 응답은 그대로 읽힌다. 마이너스 현금(마진)도 살린다.
    ok = alpaca({"cash": "5000", "equity": "12000"})
    assert (ok.get_cash(), ok.equity()) == (5000.0, 12000.0)
    assert alpaca({"cash": "-300", "equity": "12000"}).get_cash() == -300.0


def test_all_four_live_brokers_ask_the_same_judge():
    """네 브로커의 잔고 조회가 전부 `require_field`를 지나는가.

    ㉞ — 같은 판정을 여러 곳에서 쓰면 언젠가 갈라진다. 감사 182에서 둘만
    고치고 둘을 빠뜨린 것이 정확히 그 일이었다. 파일이 늘어날 때 이
    검사가 빠진 브로커를 잡는다.

    ⚠️ 이 검사는 처음에 소스에서 **글자**를 찾았다가 제 발에 걸렸다 —
       고친 이유를 설명하려고 독스트링에 적어 둔 옛 코드
       (`acct.get("equity", 0.0)`)를 위반으로 잡았다. 감사 183에서 겪은
       것과 같다. 글자가 아니라 **코드**를 봐야 한다면 `ast`로 파싱한다.
    """
    import ast

    BALANCE_KEYS = {"free", "total", "cash", "equity", "output1", "output2"}
    for mod in ("kiwoom_live", "kr_live", "crypto_live", "us_live"):
        path = ROOT / "quant" / "broker" / f"{mod}.py"
        src = path.read_text(encoding="utf-8")
        assert "require_field(" in src, f"{mod}: 공통 판정을 안 쓴다"
        for node in ast.walk(ast.parse(src)):
            # 잔고에서 값을 꺼내며 '없으면 0/빈값'을 기본값으로 두는 옛 모양
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and len(node.args) == 2
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value in BALANCE_KEYS):
                raise AssertionError(
                    f"{mod}:{node.lineno} — 잔고 키 "
                    f"{node.args[0].value!r}를 기본값으로 얼버무린다. "
                    f"require_field를 쓸 것")
