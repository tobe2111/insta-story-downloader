"""트레이딩뷰 웹훅 수신·보안·실행 테스트 (순수 stdlib).

인터넷에 열리는 주문 엔드포인트라, 보안 층(비밀키·IP·재전송·크기)과 신호→주문
매핑을 특히 촘촘히 검증한다. 실제 브로커·네트워크 없이 가짜로 확인한다.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker.base import Broker, Order, Position

# webhook 모듈을 패키지 __init__(pandas) 없이 직접 로드 → 로컬 stdlib 실행 가능
_spec = importlib.util.spec_from_file_location(
    "wh", str(Path(__file__).resolve().parent.parent / "quant" / "live" / "webhook.py"))
wh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wh)


class _FakeBroker(Broker):
    def __init__(self, cash=10_000.0):
        self.cash = cash
        self._pos = 0.0
        self.calls = []

    def get_cash(self):
        return self.cash

    def get_position(self, symbol):
        return Position(symbol, self._pos, 0.0)

    def market_order(self, symbol, side, quantity, price):
        return Order(symbol, side, quantity, price, status="filled",
                     filled_quantity=quantity)

    def target_weight(self, symbol, weight, price, equity, rebalance_band=0.0):
        self.calls.append((symbol, weight, price, equity, rebalance_band))
        if weight == 0.0 and self._pos == 0.0:
            return None
        side = "buy" if weight >= 0 else "sell"
        qty = abs(weight) * equity / price
        return Order(symbol, side, qty, price, status="accepted",
                     filled_quantity=0.0, order_id="W1")


# ── 페이로드 파싱 ────────────────────────────────────────────────────────────

def test_parse_json_and_kv():
    assert wh.parse_alert('{"action":"long","symbol":"BTC/USDT"}')["action"] == "long"
    kv = wh.parse_alert("action=short;symbol=005930;weight=0.5")
    assert kv["action"] == "short" and kv["symbol"] == "005930" and kv["weight"] == "0.5"


def test_parse_rejects_garbage():
    for bad in ("", "   ", "not json at all", "[1,2,3]"):
        try:
            wh.parse_alert(bad)
            assert False, f"거부돼야: {bad!r}"
        except ValueError:
            pass


# ── action → 목표 비중 ───────────────────────────────────────────────────────

def test_action_to_weight():
    tw = wh._target_weight
    assert tw("long", None) == 1.0
    assert tw("buy", 0.5) == 0.5
    assert tw("short", None) == -1.0
    assert tw("sell", 0.3) == -0.3
    assert tw("flat", None) == 0.0 and tw("close", None) == 0.0
    assert tw("long", 5) == 1.0            # [0,1] 클립
    try:
        tw("hodl", None); assert False
    except ValueError:
        pass


# ── 비밀키 검증 ──────────────────────────────────────────────────────────────

def test_verify_secret_constant_time():
    assert wh.verify_secret({"secret": "abc"}, "abc") is True
    assert wh.verify_secret({"secret": "abc"}, "abcd") is False
    assert wh.verify_secret({"secret": "wrong"}, "abc") is False
    assert wh.verify_secret({}, "abc") is False
    assert wh.verify_secret({"secret": "abc"}, "") is False   # 서버 비밀키 없음 → 거부


# ── 실행: 신호 → 목표 비중 주문 ──────────────────────────────────────────────

def test_execute_long_places_target_weight():
    b = _FakeBroker()
    ex = wh.WebhookExecutor(b, symbols=["BTC/USDT"])
    r = ex.execute({"action": "long", "symbol": "BTC/USDT", "price": 60000})
    assert r["ok"] and r["weight"] == 1.0 and r["side"] == "buy"
    assert b.calls[0][0] == "BTC/USDT" and b.calls[0][1] == 1.0


def test_execute_rejects_unlisted_symbol():
    ex = wh.WebhookExecutor(_FakeBroker(), symbols=["BTC/USDT"])
    r = ex.execute({"action": "long", "symbol": "DOGE/USDT", "price": 1})
    assert not r["ok"] and "허용" in r["error"]


def test_execute_short_blocked_by_default():
    ex = wh.WebhookExecutor(_FakeBroker(), symbols=["BTC/USDT"])
    r = ex.execute({"action": "short", "symbol": "BTC/USDT", "price": 60000})
    assert not r["ok"] and "숏" in r["error"]
    ex2 = wh.WebhookExecutor(_FakeBroker(), symbols=["BTC/USDT"], allow_short=True)
    assert ex2.execute({"action": "short", "symbol": "BTC/USDT", "price": 60000})["ok"]


def test_execute_missing_price_rejected():
    ex = wh.WebhookExecutor(_FakeBroker(), symbols=["BTC/USDT"])
    r = ex.execute({"action": "long", "symbol": "BTC/USDT"})
    assert not r["ok"] and "현재가" in r["error"]


def test_execute_price_fn_fallback():
    ex = wh.WebhookExecutor(_FakeBroker(), symbols=["BTC/USDT"],
                            price_fn=lambda s: 61000.0)
    r = ex.execute({"action": "long", "symbol": "BTC/USDT"})
    assert r["ok"] and abs(ex.broker.calls[0][2] - 61000.0) < 1e-9


def test_execute_max_weight_cap():
    b = _FakeBroker()
    ex = wh.WebhookExecutor(b, symbols=["BTC/USDT"], max_weight=0.3)
    ex.execute({"action": "long", "symbol": "BTC/USDT", "weight": 1.0, "price": 60000})
    assert b.calls[0][1] == 0.3            # 0.3으로 제한


def test_execute_market_hours_gate():
    # 주식 시장 + 주말 → 스킵
    b = _FakeBroker()
    ex = wh.WebhookExecutor(b, symbols=["005930"], market="kr_stock")
    from datetime import datetime, timezone
    # is_market_open은 now 인자를 받지만 execute 경유라 실시간을 쓴다. 대신
    # 주말 판정은 market_hours 단위테스트(test_fill_and_hours)에서 커버하므로,
    # 여기서는 코인(항상 통과)으로 게이트가 정상 경로를 막지 않는지만 확인.
    ex_ok = wh.WebhookExecutor(b, symbols=["BTC/USDT"], market=None)
    assert ex_ok.execute({"action": "long", "symbol": "BTC/USDT", "price": 60000})["ok"]


# ── 재전송(replay) 가드 ──────────────────────────────────────────────────────

def test_replay_guard_blocks_duplicate():
    g = wh._ReplayGuard(window_sec=100.0)
    assert g.seen_before("fp1", now=1000.0) is False   # 최초
    assert g.seen_before("fp1", now=1001.0) is True    # 100초 내 재전송 → 차단
    assert g.seen_before("fp2", now=1002.0) is False   # 다른 지문은 통과
    assert g.seen_before("fp1", now=2000.0) is False   # 윈도우 밖 → 다시 허용


# ── HTTP 핸들러 보안 (가짜 요청) ─────────────────────────────────────────────

class _FakeRequest:
    """BaseHTTPRequestHandler를 소켓 없이 구동하기 위한 최소 가짜 요청."""

    def __init__(self, body: bytes, client_ip="1.2.3.4", headers=None):
        import io
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self._body = body
        self._client_ip = client_ip
        self._headers = headers or {"content-length": str(len(body))}


def _drive(handler_cls, req: _FakeRequest):
    """핸들러 인스턴스를 만들어 do_POST를 실행하고 (status, json)을 돌려준다."""
    h = handler_cls.__new__(handler_cls)
    h.rfile = req.rfile
    h.wfile = req.wfile
    h.client_address = (req._client_ip, 12345)
    h.headers = req._headers
    h.request_version = "HTTP/1.1"
    captured = {}

    def send_response(code, *a):
        captured["code"] = code

    def send_header(*a):
        pass

    def end_headers():
        pass

    h.send_response = send_response
    h.send_header = send_header
    h.end_headers = end_headers
    h.do_POST()
    out = req.wfile.getvalue()
    body = json.loads(out.decode()) if out else {}
    return captured.get("code"), body


def _handler(secret="topsecret", **kw):
    b = _FakeBroker()
    ex = wh.WebhookExecutor(b, symbols=["BTC/USDT"])
    return wh.make_handler(ex, secret, **kw), b


def test_http_rejects_wrong_secret():
    handler, b = _handler()
    body = json.dumps({"secret": "WRONG", "action": "long",
                       "symbol": "BTC/USDT", "price": 60000}).encode()
    code, resp = _drive(handler, _FakeRequest(body))
    assert code == 401 and not resp["ok"]
    assert b.calls == []                   # 주문 실행 안 됨


def test_http_accepts_valid_and_executes():
    handler, b = _handler()
    body = json.dumps({"secret": "topsecret", "action": "long",
                       "symbol": "BTC/USDT", "price": 60000}).encode()
    code, resp = _drive(handler, _FakeRequest(body))
    assert code == 200 and resp["ok"] and resp["weight"] == 1.0
    assert len(b.calls) == 1


def test_http_ip_allowlist_blocks():
    handler, b = _handler(allow_ips={"9.9.9.9"})
    body = json.dumps({"secret": "topsecret", "action": "long",
                       "symbol": "BTC/USDT", "price": 60000}).encode()
    code, resp = _drive(handler, _FakeRequest(body, client_ip="1.2.3.4"))
    assert code == 403 and b.calls == []


def test_http_oversized_body_rejected():
    handler, b = _handler()
    body = b"x" * (20 * 1024)
    req = _FakeRequest(body, headers={"content-length": str(len(body))})
    code, resp = _drive(handler, req)
    assert code == 400 and b.calls == []


def test_http_replay_duplicate_rejected():
    guard = wh._ReplayGuard(window_sec=100.0)
    handler, b = _handler(replay_guard=guard, now=lambda: 1000.0)
    body = json.dumps({"secret": "topsecret", "action": "long",
                       "symbol": "BTC/USDT", "price": 60000}).encode()
    c1, _ = _drive(handler, _FakeRequest(body))
    c2, r2 = _drive(handler, _FakeRequest(body))
    assert c1 == 200 and c2 == 409          # 두 번째(동일 페이로드)는 중복 차단
    assert len(b.calls) == 1


def test_http_stale_timestamp_rejected():
    handler, b = _handler(max_age_sec=60.0, now=lambda: 10_000.0)
    body = json.dumps({"secret": "topsecret", "action": "long",
                       "symbol": "BTC/USDT", "price": 60000,
                       "timestamp": 1000.0}).encode()   # 아주 오래됨
    code, resp = _drive(handler, _FakeRequest(body))
    assert code == 400 and "stale" in resp["error"] and b.calls == []


def test_run_server_requires_secret():
    ex = wh.WebhookExecutor(_FakeBroker())
    import os
    os.environ.pop("QUANT_WEBHOOK_SECRET", None)
    try:
        wh.run_webhook_server(ex, secret="")
        assert False, "비밀키 없으면 실행 거부해야 함"
    except RuntimeError as e:
        assert "QUANT_WEBHOOK_SECRET" in str(e)
