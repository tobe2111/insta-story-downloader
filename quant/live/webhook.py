"""트레이딩뷰(및 기타) 알림 웹훅 수신 → 기존 실행 계층으로 주문.

트레이딩뷰는 개인용 시세/주문 API가 없다. 대신 Pine Script 전략의 '알림(alert)'이
지정한 URL로 JSON을 POST할 수 있다. 이 모듈은 그 신호를 받아, 이미 검증된 실행
계층(리스크·킬스위치·장시간 가드·체결확인)을 그대로 태워 주문을 낸다.

⚠️ 이것은 이 시스템에서 가장 위험한 표면이다 — 인터넷에 '주문을 실행하는 문'을
   연다. 방어가 뚫리면 누구나 가짜 신호로 내 돈으로 주문을 낼 수 있다. 그래서:
     1. 공유 비밀키(secret) 상수시간 비교 — 없거나 틀리면 거부.
     2. (선택) 발신 IP 허용목록 — 트레이딩뷰 공식 IP만.
     3. (선택) 타임스탬프 신선도 + 재전송(replay) 중복 차단.
     4. 기본은 페이퍼 모드. 실거래는 명시적으로 켜야만.
     5. 신호는 '목표 비중'으로 해석(멱등) — 같은 신호를 두 번 받아도 포지션을
        같은 목표로 맞출 뿐 두 배로 사지 않는다.

Pine Script 알림 메시지(JSON) 예:
    {"secret": "<내-비밀키>", "action": "long", "symbol": "BTC/USDT", "weight": 1.0}
action: long|buy | short|sell | flat|close|exit  (weight 생략 시 long=1, short=-1)
"""
from __future__ import annotations

import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from quant.utils.logging import get_logger

log = get_logger("live.webhook")

# 트레이딩뷰 공식 웹훅 발신 IP(문서 기준). ⚠️ 변경될 수 있으니 실제 사용 전
# 트레이딩뷰 최신 문서로 확인하고 QUANT_WEBHOOK_ALLOW_IPS로 덮어쓸 것.
TRADINGVIEW_IPS = {"52.89.214.238", "34.212.75.30", "52.32.178.7", "52.30.86.128"}

_LONG = {"long", "buy", "enter_long", "1"}
_SHORT = {"short", "sell", "enter_short", "-1"}
_FLAT = {"flat", "close", "exit", "close_long", "close_short", "0"}


def parse_alert(raw: bytes | str) -> dict:
    """웹훅 본문(JSON 또는 'k=v;k=v')을 dict로 파싱한다. 실패 시 ValueError."""
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    text = text.strip()
    if not text:
        raise ValueError("빈 본문")
    if text[0] in "{[":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 파싱 실패: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("최상위가 객체(dict)가 아님")
        return data
    # 단순 'action=long;symbol=BTC/USDT' 형식도 허용(Pine에서 쓰기 쉬움)
    out: dict[str, str] = {}
    for part in text.replace("\n", ";").split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    if not out:
        raise ValueError("파싱할 필드가 없음")
    return out


def _target_weight(action: str, weight) -> float:
    """action(+선택 weight)을 목표 비중[-1,1]으로 변환한다."""
    a = str(action or "").strip().lower()
    if a in _FLAT:
        return 0.0
    try:
        w = float(weight) if weight not in (None, "") else None
    except (TypeError, ValueError):
        w = None
    if a in _LONG:
        base = 1.0 if w is None else abs(w)
        return max(0.0, min(1.0, base))
    if a in _SHORT:
        base = 1.0 if w is None else abs(w)
        return -max(0.0, min(1.0, base))
    raise ValueError(f"알 수 없는 action: {action!r} (long|short|flat 계열이어야 함)")


class WebhookExecutor:
    """검증된 알림 dict를 받아 목표 비중 주문을 낸다(브로커 무관, 테스트 가능).

    실행은 기존 broker.target_weight을 그대로 쓰므로 리스크 사이징·데드밴드·
    (RobustBroker로 감쌌다면) 재시도·체결확인이 모두 적용된다.
    """

    def __init__(self, broker, symbols=None, market=None, rebalance_band=0.02,
                 max_weight=1.0, allow_short=False, price_fn=None):
        self.broker = broker
        # 허용 종목 화이트리스트(대문자 정규화). None이면 모든 종목 허용.
        self.symbols = ({s.upper() for s in symbols} if symbols else None)
        self.market = market
        self.rebalance_band = max(0.0, rebalance_band)
        self.max_weight = max(0.0, min(1.0, max_weight))
        self.allow_short = allow_short
        # 페이로드에 price/close가 없을 때 현재가를 조회하는 함수(선택).
        self.price_fn = price_fn

    def execute(self, alert: dict) -> dict:
        symbol = str(alert.get("symbol") or alert.get("ticker") or "").strip()
        if not symbol:
            return {"ok": False, "error": "symbol 누락"}
        if self.symbols is not None and symbol.upper() not in self.symbols:
            return {"ok": False, "error": f"허용되지 않은 종목: {symbol}"}
        try:
            weight = _target_weight(alert.get("action"), alert.get("weight"))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if weight < 0 and not self.allow_short:
            return {"ok": False, "error": "숏 비활성(allow_short=False)"}
        weight = max(-self.max_weight, min(self.max_weight, weight))

        # 사장님의 전역 스위치 — **주문을 내는 모든 경로**에 걸린다(감사 82).
        # 예전에는 새벽 배치(daily.py)만 이 설정을 읽었고 웹훅은 읽지 않았다.
        # 즉 대시보드에서 '일시정지'를 눌러 두어도 트레이딩뷰 알림 하나가
        # 실계좌에 주문을 냈다 — 스위치를 누른 사람은 멈췄다고 믿는다.
        # 설정을 못 읽는 것이 매매를 막는 이유가 되어서는 안 되므로(설정
        # 파일이 없는 것이 정상 상태다) 실패는 기본값으로 흘린다.
        try:
            from quant.utils.settings import load_settings
            settings = load_settings()
        except Exception:  # noqa: BLE001
            settings = {}
        if bool(settings.get("trading_paused")):
            # daily.py와 같은 의미 — 신규 주문만 막고 보유는 건드리지 않는다.
            return {"ok": False, "skipped": True, "reason": "어드민 일시정지"}
        try:
            weight *= float(settings.get("exposure_scale", 1.0))
        except (TypeError, ValueError):
            pass                      # 값이 이상하면 배수 미적용(전액)

        # 장 시간 가드(주식). 코인·미지정은 항상 통과.
        if self.market is not None:
            from quant.live.market_hours import is_market_open, market_status
            if not is_market_open(self.market):
                return {"ok": False, "skipped": True,
                        "reason": market_status(self.market)}

        price = self._price(symbol, alert)
        if price <= 0:
            return {"ok": False, "error": "현재가를 얻지 못함(price/close 필드 또는 "
                    "브로커 시세 헬퍼 필요)"}
        equity = self._equity(symbol, price)
        order = self.broker.target_weight(symbol, weight, price, equity,
                                          rebalance_band=self.rebalance_band)
        if order is None:
            return {"ok": True, "action": "no_change", "symbol": symbol,
                    "weight": weight}
        return {"ok": True, "symbol": symbol, "weight": weight,
                "side": order.side, "quantity": order.quantity,
                "status": order.status, "order_id": getattr(order, "order_id", "")}

    def _price(self, symbol: str, alert: dict) -> float:
        """현재가: 페이로드의 price/close(트레이딩뷰 {{close}}) 우선, 없으면
        브로커 시세 헬퍼로 폴백. 둘 다 없으면 0(주문 거부)."""
        for key in ("price", "close"):
            v = alert.get(key)
            if v not in (None, ""):
                try:
                    p = float(v)
                    if p > 0:
                        return p
                except (TypeError, ValueError):
                    pass
        if callable(self.price_fn):
            try:
                # 위 페이로드 경로와 같은 기준으로 거른다(감사 167). 예전엔
                # 여기만 `> 0` 검사가 없어서, 시세 헬퍼가 NaN을 주면 그대로
                # 반환됐다 — 호출부의 `price <= 0`은 NaN을 못 막는다.
                p = float(self.price_fn(symbol))
                return p if p > 0 else 0.0
            except Exception:  # noqa: BLE001
                return 0.0
        return 0.0

    def _equity(self, symbol: str, price: float) -> float:
        if hasattr(self.broker, "equity"):
            return float(self.broker.equity({symbol: price}))
        pos = self.broker.get_position(symbol)
        return float(self.broker.get_cash() + pos.quantity * price)


def verify_secret(alert: dict, expected: str) -> bool:
    """페이로드의 secret을 상수시간 비교로 검증한다. expected가 없으면 항상 실패."""
    if not expected:
        return False
    got = str(alert.get("secret", ""))
    return hmac.compare_digest(got, expected)


class _ReplayGuard:
    """최근 페이로드 지문을 기억해 동일 신호의 재전송(replay)을 차단한다.

    목표 비중 방식이라 재전송이 이론상 무해(같은 목표로 재조정)하지만, 캡처된
    신호를 악용한 재전송·중복 발사를 한 번 더 막는 방어층이다. 메모리 상한을 둔다.
    """

    def __init__(self, window_sec: float = 300.0, cap: int = 512):
        self.window = window_sec
        self.cap = cap
        self._seen: dict[str, float] = {}

    def seen_before(self, fingerprint: str, now: float) -> bool:
        # 만료 청소
        if len(self._seen) > self.cap:
            for k, t in list(self._seen.items()):
                if now - t > self.window:
                    self._seen.pop(k, None)
        prev = self._seen.get(fingerprint)
        self._seen[fingerprint] = now
        return prev is not None and (now - prev) < self.window


def make_handler(executor: "WebhookExecutor", secret: str, *,
                 allow_ips=None, replay_guard=None, max_age_sec: float = 0.0,
                 now=time.time):
    """검증 → 실행을 수행하는 BaseHTTPRequestHandler 클래스를 만든다.

    allow_ips  : 허용 발신 IP 집합(None이면 IP 검사 생략 — 리버스 프록시 뒤 등).
    max_age_sec: >0이면 페이로드의 timestamp(초)가 이만큼보다 오래되면 거부.
    """
    _MAXLEN = 16 * 1024   # 페이로드 크기 상한(과대 본문 방어)

    class WebhookHandler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 기본 접근로그 억제(키 유출 방지)
            pass

        def _reply(self, code: int, obj: dict) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            # 1) IP 허용목록(선택)
            client = self.client_address[0] if self.client_address else ""
            if allow_ips is not None and client not in allow_ips:
                log.warning("웹훅 거부: 허용되지 않은 IP %s", client)
                return self._reply(403, {"ok": False, "error": "forbidden"})
            # 2) 크기 제한
            length = int(self.headers.get("content-length") or 0)
            if length <= 0 or length > _MAXLEN:
                return self._reply(400, {"ok": False, "error": "bad length"})
            raw = self.rfile.read(length)
            # 3) 파싱
            try:
                alert = parse_alert(raw)
            except ValueError as exc:
                return self._reply(400, {"ok": False, "error": str(exc)})
            # 4) 비밀키(상수시간)
            if not verify_secret(alert, secret):
                log.warning("웹훅 거부: 비밀키 불일치 (IP %s)", client)
                return self._reply(401, {"ok": False, "error": "unauthorized"})
            # 5) 타임스탬프 신선도(선택)
            if max_age_sec > 0:
                ts = alert.get("timestamp") or alert.get("time")
                try:
                    age = now() - float(ts)
                except (TypeError, ValueError):
                    return self._reply(400, {"ok": False, "error": "timestamp 필요"})
                if age > max_age_sec or age < -max_age_sec:
                    return self._reply(400, {"ok": False, "error": "stale"})
            # 6) 재전송 차단(선택)
            if replay_guard is not None:
                fp = hmac.new(secret.encode(), raw, "sha256").hexdigest()
                if replay_guard.seen_before(fp, now()):
                    return self._reply(409, {"ok": False, "error": "duplicate"})
            # 7) 실행
            try:
                result = executor.execute(alert)
            except Exception as exc:  # noqa: BLE001
                log.error("웹훅 실행 오류: %s", exc)
                return self._reply(500, {"ok": False, "error": "실행 오류"})
            code = 200 if result.get("ok") else 422
            return self._reply(code, result)

        def do_GET(self) -> None:  # noqa: N802
            # 헬스체크만 — 어떤 상태·키도 노출하지 않는다.
            self._reply(200, {"ok": True, "service": "quant-webhook"})

    return WebhookHandler


def run_webhook_server(executor: "WebhookExecutor", host: str = "0.0.0.0",
                       port: int = 8100, secret: str | None = None,
                       allow_ips=None, replay: bool = True,
                       max_age_sec: float = 0.0) -> None:
    """웹훅 서버를 실행한다(Ctrl+C로 종료).

    secret 미지정 시 환경변수 QUANT_WEBHOOK_SECRET 를 쓴다. 비밀키가 전혀 없으면
    보안상 실행을 거부한다 — 인증 없는 주문 엔드포인트는 절대 열지 않는다.
    """
    secret = secret or os.getenv("QUANT_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError(
            "QUANT_WEBHOOK_SECRET(공유 비밀키)이 필요합니다. 인증 없는 웹훅은 "
            "누구나 내 계좌로 주문을 낼 수 있어 실행을 거부합니다.")
    guard = _ReplayGuard() if replay else None
    handler = make_handler(executor, secret, allow_ips=allow_ips,
                           replay_guard=guard, max_age_sec=max_age_sec)
    server = ThreadingHTTPServer((host, port), handler)
    log.warning("🔌 웹훅 수신 대기: %s:%d  (POST /) — 비밀키 인증 필수", host, port)
    if allow_ips:
        log.warning("   IP 허용목록: %s", ", ".join(sorted(allow_ips)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
