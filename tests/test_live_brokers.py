"""실거래 브로커 목(mock) 테스트 — 실제 API 없이 주문/조회 로직을 검증한다.

이 브로커들은 실제 자금이 오가므로, 요청 본문 구성과 응답 파싱이 정확한지
가짜 API로 반드시 확인해야 한다. (pandas 불필요 — 표준 라이브러리만)
"""
from __future__ import annotations

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
            return {"rt_cd": "0", "msg1": "정상처리"}
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
    assert order.status == "filled"
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
            return {"return_code": 0, "return_msg": "정상", "ord_no": "0001"}
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
    assert buy.status == "filled" and sell.status == "filled"
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


def test_crypto_live_injected_client():
    fake = _FakeCcxt()
    broker = crypto_live.CryptoLiveBroker(client=fake)
    assert broker.get_cash() == 500.0
    assert broker.get_position("BTC/USDT").quantity == 0.1
    order = broker.market_order("BTC/USDT", "buy", 0.05, 60000)
    assert fake.last_order == ("BTC/USDT", "market", "buy", 0.05)
    assert order.filled_quantity == 0.05 and order.status == "closed"
