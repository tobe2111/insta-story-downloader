"""실거래 브로커 목(mock) 테스트 — 실제 API 없이 주문/조회 로직을 검증한다.

이 브로커들은 실제 자금이 오가므로, 요청 본문 구성과 응답 파싱이 정확한지
가짜 API로 반드시 확인해야 한다. (pandas 불필요 — 표준 라이브러리만)
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import crypto_live, kiwoom_live, kr_live, us_live


# --- Alpaca (미국주식) ---
def test_alpaca_order_and_queries():
    os.environ["ALPACA_API_KEY"] = "k"
    os.environ["ALPACA_SECRET"] = "s"
    broker = us_live.AlpacaBroker(paper=True)

    def fake_get(url, headers=None):
        if "account" in url:
            return {"cash": "1000.5", "equity": "1200.0"}
        return {"qty": "2", "avg_entry_price": "50.0"}

    sent = {}

    def fake_post(url, headers=None, body=None):
        sent["body"] = body
        return {"filled_avg_price": "51.0", "filled_qty": "3", "status": "filled"}

    with mock.patch.object(us_live, "get_json", fake_get), \
         mock.patch.object(us_live, "post_json", fake_post):
        assert broker.get_cash() == 1000.5
        assert broker.get_equity() == 1200.0
        assert broker.get_position("AAPL").quantity == 2.0
        order = broker.market_order("AAPL", "buy", 3, 50.0)

    assert sent["body"]["symbol"] == "AAPL"
    assert sent["body"]["side"] == "buy"
    assert sent["body"]["type"] == "market"
    assert order.filled_quantity == 3.0 and order.status == "filled"


def test_alpaca_accepted_order_not_marked_filled():
    """체결 전(accepted) 응답을 전량 체결로 꾸며내지 않는다(중복 주문 방지)."""
    os.environ["ALPACA_API_KEY"] = "k"
    os.environ["ALPACA_SECRET"] = "s"
    broker = us_live.AlpacaBroker(paper=True)

    def fake_post(url, headers=None, body=None):
        # 시장가 접수 직후: 아직 체결 안 됨
        return {"status": "accepted", "filled_qty": "0", "filled_avg_price": None}

    with mock.patch.object(us_live, "post_json", fake_post):
        order = broker.market_order("AAPL", "buy", 3, 50.0)

    assert order.status == "accepted"
    assert order.filled_quantity == 0.0        # 전량 체결로 위조하지 않음


def test_kis_token_refreshes_after_expiry():
    """토큰 만료 시각이 지나면 재발급한다(장기 실행 시 만료 토큰 주문 실패 방지)."""
    os.environ.update({"KIS_APP_KEY": "k", "KIS_APP_SECRET": "s", "KIS_CANO": "1"})
    broker = kr_live.KISBroker(paper=True)
    calls = {"n": 0}

    def fake_post(url, headers=None, body=None):
        if "tokenP" in url:
            calls["n"] += 1
            return {"access_token": f"tok{calls['n']}", "expires_in": 86400}
        return {}

    with mock.patch.object(kr_live, "post_json", fake_post):
        t1 = broker._get_token()
        t2 = broker._get_token()            # 아직 유효 → 재사용
        assert t1 == t2 and calls["n"] == 1
        broker._token_expiry = 0.0          # 만료 강제
        t3 = broker._get_token()            # 재발급
        assert calls["n"] == 2 and t3 != t1


def test_alpaca_equity_uses_account_value():
    """equity()가 계좌 평가액을 그대로 반환한다(MultiTrader 인터페이스 일관성)."""
    os.environ.update({"ALPACA_API_KEY": "k", "ALPACA_SECRET": "s"})
    broker = us_live.AlpacaBroker(paper=True)

    def fake_get(url, headers=None):
        return {"cash": "1000.0", "equity": "1234.5"}

    with mock.patch.object(us_live, "get_json", fake_get):
        assert hasattr(broker, "equity")
        assert broker.equity({"AAPL": 100.0}) == 1234.5   # marks 무시, 계좌값이 정답


def test_alpaca_missing_keys_raises():
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET"):
        os.environ.pop(k, None)
    try:
        us_live.AlpacaBroker(paper=True)
        assert False, "키 없으면 예외여야 함"
    except RuntimeError:
        pass


# --- 한국투자증권 KIS (국내주식) ---
def test_kis_order_and_balance():
    os.environ["KIS_APP_KEY"] = "k"
    os.environ["KIS_APP_SECRET"] = "s"
    os.environ["KIS_CANO"] = "12345678"
    broker = kr_live.KISBroker(paper=True)

    order_body = {}

    def fake_post(url, headers=None, body=None):
        if "tokenP" in url:
            return {"access_token": "tok"}
        if "hashkey" in url:
            return {"HASH": "hh"}
        if "order-cash" in url:
            order_body.update(body or {})
            return {"rt_cd": "0", "msg1": "정상처리", "output": {"ODNO": "0000117"}}
        return {}

    def fake_get(url, headers=None):
        return {"output1": [{"pdno": "005930", "hldg_qty": "5",
                             "pchs_avg_pric": "68000"}],
                "output2": [{"dnca_tot_amt": "1000000"}]}

    with mock.patch.object(kr_live, "post_json", fake_post), \
         mock.patch.object(kr_live, "get_json", fake_get):
        order = broker.market_order("005930", "buy", 10, 70000)
        cash = broker.get_cash()
        pos = broker.get_position("005930")

    # 시장가 주문 규격 검증
    assert order_body["PDNO"] == "005930"
    assert order_body["ORD_DVSN"] == "01"   # 시장가
    assert order_body["ORD_QTY"] == "10"
    # 접수(rt_cd=0)를 '체결'로 위조하지 않는다 — 'accepted'로 정직하게 보고하고
    # 주문번호를 남긴다. 실제 체결은 RobustBroker(confirm_fills)가 포지션으로 확인.
    assert order.status == "accepted"
    assert order.filled_quantity == 0.0
    assert order.order_id == "0000117"
    assert cash == 1000000.0
    assert pos.quantity == 5.0 and pos.avg_price == 68000.0


def test_kis_uses_paper_tr_ids():
    os.environ.update({"KIS_APP_KEY": "k", "KIS_APP_SECRET": "s", "KIS_CANO": "1"})
    broker = kr_live.KISBroker(paper=True)
    assert broker.env == "paper"
    assert broker._TR_BUY["paper"].startswith("V")  # 모의투자 tr_id


# --- 키움증권 (국내주식) ---
def test_kiwoom_order_routing_and_balance():
    os.environ.update({"KIWOOM_APP_KEY": "k", "KIWOOM_SECRET": "s",
                       "KIWOOM_ACCOUNT": "1234567890"})
    broker = kiwoom_live.KiwoomBroker(paper=True)
    assert broker.base == kiwoom_live.KiwoomBroker.MOCK_URL   # 모의 URL

    sent = {}

    def fake_post(url, headers=None, body=None):
        if url.endswith("/oauth2/token"):
            return {"token": "tok"}
        if url.endswith("/api/dostk/ordr"):
            sent["api_id"] = headers.get("api-id")
            sent["body"] = body
            return {"return_code": 0, "return_msg": "정상", "ord_no": "0000123"}
        if url.endswith("/api/dostk/acnt"):
            return {"prsm_dpst_aset_amt": "2,000,000",
                    "acnt_evlt_remn_indv_tot": [
                        {"stk_cd": "A005930", "rmnd_qty": "7", "pur_pric": "68000"}]}
        return {}

    with mock.patch.object(kiwoom_live, "post_json", fake_post):
        buy = broker.market_order("005930", "buy", 10, 70000)
        sell = broker.market_order("005930", "sell", 3, 70000)
        cash = broker.get_cash()
        pos = broker.get_position("005930")

    assert sent["api_id"] == broker.TR_SELL          # 마지막 주문은 매도
    assert sent["body"]["stk_cd"] == "005930"
    assert sent["body"]["ord_qty"] == "3"
    assert sent["body"]["trde_tp"] == "3"            # 시장가
    # 접수를 '체결'로 위조하지 않는다(KIS와 동일 규약)
    assert buy.status == "accepted" and sell.status == "accepted"
    assert buy.order_id == "0000123" and buy.filled_quantity == 0.0
    assert cash == 2_000_000.0                        # 콤마 제거 파싱
    assert pos.quantity == 7.0 and pos.avg_price == 68000.0   # 'A005930' → '005930' 매칭


def test_kiwoom_missing_keys_raises():
    for k in ("KIWOOM_APP_KEY", "KIWOOM_SECRET", "KIWOOM_ACCOUNT"):
        os.environ.pop(k, None)
    try:
        kiwoom_live.KiwoomBroker(paper=True)
        assert False, "키 없으면 예외여야 함"
    except RuntimeError:
        pass


def test_kiwoom_zero_qty_skipped():
    os.environ.update({"KIWOOM_APP_KEY": "k", "KIWOOM_SECRET": "s",
                       "KIWOOM_ACCOUNT": "1"})
    broker = kiwoom_live.KiwoomBroker(paper=True)
    order = broker.market_order("005930", "buy", 0.4, 70000)  # int(0.4)=0
    assert order.status == "skipped"


# --- ccxt 범용 거래소 ---
def test_crypto_korean_exchange_defaults_krw():
    """국내 거래소(업비트)는 기본 정산통화가 KRW."""
    fake = _FakeCcxt()
    broker = crypto_live.CryptoLiveBroker(exchange="upbit", client=fake)
    assert broker.quote == "KRW"


def test_crypto_quote_override():
    fake = _FakeCcxt()
    broker = crypto_live.CryptoLiveBroker(exchange="binance", quote="USDT", client=fake)
    assert broker.quote == "USDT"


# --- ccxt (암호화폐) ---
class _FakeCcxt:
    def __init__(self):
        self.last_order = None

    def fetch_balance(self):
        return {"free": {"USDT": 500.0}, "total": {"BTC": 0.1}}

    def create_order(self, symbol, type_, side, quantity):
        self.last_order = (symbol, type_, side, quantity)
        return {"average": 60000.0, "filled": quantity, "status": "closed"}


class _OpenOrderCcxt:
    """미체결(open) 주문을 반환하는 가짜 거래소."""

    def fetch_balance(self):
        return {"free": {"USDT": 500.0}, "total": {}}

    def create_order(self, symbol, type_, side, quantity):
        return {"status": "open", "filled": 0}   # 아직 체결 안 됨


def test_crypto_open_order_not_marked_filled():
    """ccxt가 미체결(open)을 주면 전량 체결로 위조하지 않는다(us_live와 동일 규약)."""
    broker = crypto_live.CryptoLiveBroker(client=_OpenOrderCcxt())
    order = broker.market_order("BTC/USDT", "buy", 0.05, 60000)
    assert order.status == "open"
    assert order.filled_quantity == 0.0


def test_safe_amount_rejects_non_finite_and_negative():
    """거래소 응답의 inf/nan/음수가 자금 계산을 오염시키지 않게 걸러진다."""
    from quant.broker.base import safe_amount
    assert safe_amount("100.5") == 100.5
    assert safe_amount(float("inf")) == 0.0
    assert safe_amount("nan") == 0.0
    assert safe_amount("1e400") == 0.0            # → inf
    assert safe_amount(-5) == 0.0                 # 음수 거부(기본)
    assert safe_amount(-5, allow_negative=True) == -5.0   # 숏 수량은 허용
    assert safe_amount(None) == 0.0
    assert safe_amount("abc", default=1.0) == 1.0


class _BadBalanceCcxt:
    def fetch_balance(self):
        return {"free": {"USDT": float("inf")}, "total": {"BTC": float("nan")}}

    def create_order(self, *a):
        return {"status": "closed", "filled": 0.01, "average": 60000.0}


def test_crypto_broker_sanitizes_bad_balance():
    """inf 현금/nan 수량이 0으로 걸러져 'inf 수량 주문' 같은 사고를 막는다."""
    b = crypto_live.CryptoLiveBroker(client=_BadBalanceCcxt())
    assert b.get_cash() == 0.0                              # inf → 0
    assert b.get_position("BTC/USDT").quantity == 0.0       # nan → 0


def test_crypto_live_injected_client():
    fake = _FakeCcxt()
    broker = crypto_live.CryptoLiveBroker(client=fake)
    assert broker.get_cash() == 500.0
    assert broker.get_position("BTC/USDT").quantity == 0.1
    order = broker.market_order("BTC/USDT", "buy", 0.05, 60000)
    assert fake.last_order == ("BTC/USDT", "market", "buy", 0.05)
    assert order.filled_quantity == 0.05 and order.status == "closed"


# ── 조회 실패를 '보유 없음'으로 읽지 않는다 (감사 55) ─────────


def test_alpaca_position_404_means_no_position():
    """진짜 '없음'(404)만 0주로 읽는다."""
    from quant.utils.http import HttpError
    os.environ["ALPACA_API_KEY"] = "k"
    os.environ["ALPACA_SECRET"] = "s"
    broker = us_live.AlpacaBroker(paper=True)

    def not_found(url, headers=None):
        raise HttpError("HTTP 404 ...: position does not exist", status=404)

    with mock.patch.object(us_live, "get_json", not_found):
        pos = broker.get_position("AAPL")
    assert pos.quantity == 0.0 and pos.avg_price == 0.0


def test_alpaca_position_error_is_not_silently_zero():
    """401/429/500/네트워크 오류를 '0주 보유'로 읽으면 포지션이 두 배가 된다.

    상위 로직은 보유 0을 보면 목표 비중만큼 **다시 산다.** 토큰이 만료된
    실거래 계좌에서 이 폴백은 조용한 2배 노출을 만든다. 예전 코드는
    `except RuntimeError: return Position(symbol, 0, 0)` 한 줄로 404와
    나머지를 구분하지 않았다 — 주석에는 "포지션 없음 → 404"라고 적혀
    있었지만 실제로는 모든 실패를 그렇게 읽었다.
    """
    from quant.utils.http import HttpError
    os.environ["ALPACA_API_KEY"] = "k"
    os.environ["ALPACA_SECRET"] = "s"
    broker = us_live.AlpacaBroker(paper=True)

    for exc in (HttpError("HTTP 401 ...: unauthorized", status=401),
                HttpError("HTTP 429 ...: rate limited", status=429),
                HttpError("HTTP 500 ...: server error", status=500),
                HttpError("네트워크 오류 ...: timed out")):    # status=None
        def boom(url, headers=None, _e=exc):
            raise _e
        with mock.patch.object(us_live, "get_json", boom):
            try:
                broker.get_position("AAPL")
            except RuntimeError:
                pass                      # 올바른 동작: 모름을 그대로 올린다
            else:
                raise AssertionError(f"{exc} 를 '보유 없음'으로 삼켰다")


def test_http_errors_carry_status_codes():
    """404와 그 밖의 실패를 구분하려면 상태코드가 예외에 실려야 한다."""
    import urllib.error
    from unittest import mock as _mock

    from quant.utils import http as _http

    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {},
                                     io.BytesIO(b"nope"))

    with _mock.patch.object(_http._opener, "open", raise_http):
        try:
            _http.get_json("https://example.com/x")
        except _http.HttpError as exc:
            assert exc.status == 404
            assert isinstance(exc, RuntimeError)      # 기존 except와 호환
        else:
            raise AssertionError("예외가 안 났다")

    def raise_url(req, timeout=None):
        raise urllib.error.URLError("timed out")

    with _mock.patch.object(_http._opener, "open", raise_url):
        try:
            _http.get_json("https://example.com/x")
        except _http.HttpError as exc:
            assert exc.status is None       # 서버 응답 자체를 못 받았다
        else:
            raise AssertionError("예외가 안 났다")
