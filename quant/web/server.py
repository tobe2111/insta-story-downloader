"""가벼운 로컬 웹서버 (표준 라이브러리 http.server).

외부 웹 프레임워크(Flask/FastAPI) 없이 브라우저에서 백테스트를 실행하고
리포트를 볼 수 있게 한다. 로컬 전용 도구이므로 localhost 바인딩을 기본으로 한다.

    python -m quant.web.server            # http://127.0.0.1:8000
"""
from __future__ import annotations

import hmac
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_LOOPBACK = {"127.0.0.1", "localhost", "::1", ""}
# 실제 바인딩 호스트(run_server가 채운다) — 비-로컬 바인딩 시 그 주소도 허용
_BIND_HOST = "127.0.0.1"

from quant.web.app import (
    broadcast_json,
    candles_json,
    render_broadcast,
    render_deposit_form,
    render_form,
    render_monitor,
    render_optimize_form,
    render_portfolio_form,
    render_screener_form,
    render_sweep_form,
    render_validate_form,
    run_backtest_html,
    run_deposit_html,
    run_optimize_html,
    run_portfolio_html,
    run_screener_html,
    run_sweep_html,
    quotes_proxy,
    run_validate_html,
    state_json,
)
from quant.web.mystrategy import (
    render_ingest_form,
    render_pin_prepare,
    render_pins_page,
    run_ingest_html,
    run_pin_save,
    run_pin_unpin,
)
from quant.web.app import render_halt_page, run_halt_toggle
from quant.web.auth import render_login_form, run_login

# 로그인 없이도 닿아야 하는 경로 — 로그인 화면 자체와 라이브니스 체크.
_OPEN_PATHS = {"/health", "/login", "/login/run"}


class QuantHandler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200,
              content_type: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        # 로그인 쿠키·리다이렉트용 — 응답 직전에 심고 바로 비운다.
        for k, v in (getattr(self, "_extra_headers", None) or {}).items():
            self.send_header(k, v)
        self._extra_headers = None
        self.end_headers()
        self.wfile.write(data)

    def _session_ok(self) -> bool:
        """로그인 세션 쿠키가 유효한가 — 서명·만료를 함께 본다."""
        import time as _time

        from quant.web import auth as _auth
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, val = part.strip().partition("=")
            if name == _auth.COOKIE_NAME:
                return _auth.check_session(val, _time.time())
        return False

    def _authorized(self, parsed) -> bool:
        """로그인(세션 쿠키) 또는 토큰 — 설정된 관문은 모두 지켜야 한다.

        · 아이디/비밀번호가 설정돼 있으면(web-passwd) 로그인 세션을 요구한다
          (사장님 2026-08-18: "모두가 다 접속 가능하면 안되니까").
        · QUANT_WEB_TOKEN은 화면 없는 접근(OBS 방송 소스 등)용으로 계속
          유효하다 — 둘 중 하나만 통과하면 된다.
        · 아무것도 설정 안 된 기본값은 예전처럼 게이트 없음 — 127.0.0.1
          바인딩이라 본인 컴퓨터에서만 열린다.
        · /health와 로그인 화면 자체는 항상 허용(_OPEN_PATHS).
        """
        from quant.web import auth as _auth
        if parsed.path in _OPEN_PATHS:
            return True
        token = os.environ.get("QUANT_WEB_TOKEN", "")
        if token:
            q = parse_qs(parsed.query)
            supplied = (q["token"][0] if q.get("token")
                        else self.headers.get("X-Auth-Token", ""))
            if hmac.compare_digest(supplied, token):
                return True
        if _auth.configured():
            return self._session_ok()
        return not token

    # 교차출처에서 유발되면 안 되는 경로.
    #   · /deposit/run — 바깥 세상을 바꾼다(입금 워크플로 디스패치)
    #   · 나머지 /run  — 수 초~수 분짜리 연산이라 교차출처에서 반복 호출되면
    #     사장님 PC의 자원을 태운다. 다른 사이트가 이걸 부를 이유는 없다.
    # 조회 경로(/api/state·/monitor 등)는 막지 않는다 — 로컬 도구의 사용성.
    _MUTATING = ("/login/run", "/halt/run", "/ingest/run", "/pin/save", "/pin/unpin",
                 "/deposit/run", "/optimize/run", "/sweep/run",
                 "/portfolio/run", "/screener/run", "/validate/run",
                 "/backtest")

    def _host_ok(self) -> bool:
        """Host 헤더가 루프백인가 — DNS 리바인딩 차단.

        공격자 도메인이 127.0.0.1로 해석되게 만들면, 브라우저는 그 사이트를
        '같은 출처'로 취급해 로컬 서버의 응답(/api/state = 포지션·손익)을
        읽을 수 있다. Host를 검사하면 그 경로가 막힌다.
        """
        raw = (self.headers.get("Host") or "").strip()
        if raw.startswith("["):                 # IPv6 리터럴: [::1]:8000
            host = raw[1:raw.find("]")] if "]" in raw else raw[1:]
        else:
            host = raw.split(":", 1)[0]
        host = host.lower()
        return host in _LOOPBACK or host == _BIND_HOST

    def _same_site_ok(self, parsed) -> bool:
        """교차출처에서 유발된 요청인가 — CSRF 차단.

        ⚠️ 왜 필요한가(2026-08-11 감사): /deposit/run이 GET + 쿼리라
        `<img src="http://127.0.0.1:8000/deposit/run?amount=10000000">` 한 줄이
        박힌 아무 웹페이지만 방문해도 **가짜 입금이 공개 장부에 커밋**된다.
        이 프로젝트에서 장부 오염은 돈이 나가는 것만큼 나쁘다.

        Origin이 있으면 자기 자신이어야 하고, 브라우저가 보내는
        Sec-Fetch-Site가 cross-site면 거부한다. 두 헤더가 모두 없는 요청
        (curl 등 비브라우저)은 통과 — 로컬 CLI 사용을 막을 이유가 없다.
        """
        if parsed.path not in self._MUTATING:
            return True
        site = (self.headers.get("Sec-Fetch-Site") or "").lower()
        if site and site not in ("same-origin", "same-site", "none"):
            return False
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            want = f"http://{self.headers.get('Host', '')}"
            if origin.rstrip("/") != want.rstrip("/"):
                return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._host_ok():
            self._send("허용되지 않은 Host 헤더입니다(로컬 전용 도구).",
                       status=403, content_type="text/plain; charset=utf-8")
            return
        if not self._same_site_ok(parsed):
            self._send("교차 출처 요청은 거부됩니다(CSRF 방지).",
                       status=403, content_type="text/plain; charset=utf-8")
            return
        if not self._authorized(parsed):
            from quant.web import auth as _auth
            if _auth.configured():
                # 사람이 브라우저로 온 경우 — 401 글자벽 대신 로그인 화면으로.
                self._extra_headers = {"Location": "/login"}
                self._send("로그인이 필요합니다.", status=302,
                           content_type="text/plain; charset=utf-8")
            else:
                self._send("인증이 필요합니다: ?token=... 또는 X-Auth-Token 헤더를 제공하세요.",
                           status=401, content_type="text/plain; charset=utf-8")
            return
        if parsed.path in ("/", "/index.html"):
            self._send(render_form())
        elif parsed.path == "/login":
            self._send(render_login_form())
        elif parsed.path == "/halt":
            # 긴급 정지 화면 — 상태 확인은 GET, 켜고 끄기는 POST만.
            self._send(render_halt_page())
        elif parsed.path == "/health":
            self._send("ok")
        elif parsed.path == "/backtest":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_backtest_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/monitor":
            # 상태 파일이 없거나 손상돼 render_monitor가 던지면 500 트레이스백 대신
            # 안내 메시지를 보여준다(다른 라우트와 일관).
            try:
                self._send(render_monitor())
            except Exception as exc:  # noqa: BLE001
                self._send(render_form(f"모니터 로드 오류: {exc}"), status=400)
        elif parsed.path == "/api/state":
            self._send(state_json(), content_type="application/json; charset=utf-8")
        elif parsed.path == "/broadcast":
            # 방송 모드 — OBS 브라우저 소스로 잡아 유튜브 라이브에 송출하는 화면
            self._send(render_broadcast())
        elif parsed.path == "/api/candles":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(candles_json(params.get("key", "crypto:BTC/USDT"),
                                        tf=params.get("tf", "1m")),
                           content_type="application/json; charset=utf-8")
            except Exception:  # noqa: BLE001
                self._send("{}", content_type="application/json; charset=utf-8")
        elif parsed.path == "/api/quotes":
            # 조종석 준실시간 시세 — **판정 사다리를 여기서 다시 만들지
            # 않는다.** 배포된 워커(같은 코드)로 그대로 넘긴다. 같은 판정을
            # 두 곳에 두면 언젠가 갈라진다(감사 219). 주소가 없으면 빈
            # 응답이고 조종석은 확정값만 보여준다 — 조용히 틀린 값을
            # 만들어 내지 않는다.
            self._send(quotes_proxy(parsed.query),
                       content_type="application/json; charset=utf-8")
        elif parsed.path == "/api/broadcast":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                # nolive=1: 첫 페인트용 — 느릴 수 있는 실시간 시세 수집을 건너뛴다
                self._send(broadcast_json(with_live=not params.get("nolive")),
                           content_type="application/json; charset=utf-8")
            except Exception:  # noqa: BLE001 — 방송 화면은 조용히 재시도한다
                self._send("{}", content_type="application/json; charset=utf-8")
        elif parsed.path == "/portfolio":
            self._send(render_portfolio_form())
        elif parsed.path == "/portfolio/run":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_portfolio_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_portfolio_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/screener":
            self._send(render_screener_form())
        elif parsed.path == "/screener/run":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_screener_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_screener_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/optimize":
            self._send(render_optimize_form())
        elif parsed.path == "/optimize/run":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_optimize_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_optimize_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/validate":
            self._send(render_validate_form())
        elif parsed.path == "/validate/run":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_validate_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_validate_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/deposit":
            self._send(render_deposit_form())
        elif parsed.path == "/deposit/run":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_deposit_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_deposit_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/ingest":
            self._send(render_ingest_form())
        elif parsed.path == "/pins":
            try:
                self._send(render_pins_page())
            except Exception as exc:  # noqa: BLE001
                self._send(render_form(f"고정 페이지 오류: {exc}"), status=400)
        elif parsed.path == "/pin/prepare":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(render_pin_prepare(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_form(f"성적표 오류: {exc}"), status=400)
        elif parsed.path == "/sweep":
            self._send(render_sweep_form())
        elif parsed.path == "/sweep/run":
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                self._send(run_sweep_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_sweep_form(f"실행 오류: {exc}"), status=400)
        else:
            self._send(render_form("알 수 없는 경로입니다."), status=404)

    def do_POST(self) -> None:  # noqa: N802
        """전략 등록·고정처럼 **긴 본문**과 **상태 변경**이 있는 경로만 POST.

        GET과 같은 세 관문(Host·교차출처·토큰)을 똑같이 지난다 — 메서드가
        다르다고 관문이 얇아지면 CSRF 방지(2026-08-11 감사)가 반쪽이 된다.
        """
        parsed = urlparse(self.path)
        if not self._host_ok():
            self._send("허용되지 않은 Host 헤더입니다(로컬 전용 도구).",
                       status=403, content_type="text/plain; charset=utf-8")
            return
        if not self._same_site_ok(parsed):
            self._send("교차 출처 요청은 거부됩니다(CSRF 방지).",
                       status=403, content_type="text/plain; charset=utf-8")
            return
        if not self._authorized(parsed):
            self._send("인증이 필요합니다: ?token=... 또는 X-Auth-Token 헤더를 제공하세요.",
                       status=401, content_type="text/plain; charset=utf-8")
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0),
                         2_000_000)          # 자료 본문 상한 2MB — 폭주 방지
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            params = {k: v[0] for k, v in parse_qs(body).items()}
        except Exception:  # noqa: BLE001
            params = {}
        if parsed.path == "/login/run":
            hdrs: dict = {}
            try:
                html = run_login(params, hdrs)
            except Exception:  # noqa: BLE001 — 로그인 오류도 한 문장으로만
                html = render_login_form("로그인 처리 중 오류가 났습니다.")
            self._extra_headers = hdrs or None
            self._send(html)
        elif parsed.path == "/halt/run":
            try:
                self._send(run_halt_toggle(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_halt_page(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/ingest/run":
            try:
                self._send(run_ingest_html(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_ingest_form(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/pin/save":
            try:
                self._send(run_pin_save(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_pins_page(f"실행 오류: {exc}"), status=400)
        elif parsed.path == "/pin/unpin":
            try:
                self._send(run_pin_unpin(params))
            except Exception as exc:  # noqa: BLE001
                self._send(render_pins_page(f"실행 오류: {exc}"), status=400)
        else:
            self._send(render_form("알 수 없는 경로입니다."), status=404)

    def log_message(self, *args) -> None:  # 기본 액세스 로그 억제
        pass


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    # .env 자동 로딩 — setup 마법사로 저장한 키를 웹 경로에서도 쓸 수 있게.
    from quant.utils.envfile import load_env_file
    load_env_file()
    # 사용자 전략 폴더를 불러와 웹 전략 드롭다운에도 노출한다(폼 렌더는 여전히
    # pandas 불필요 — 여기서 확장된 목록만 읽는다).
    try:
        from quant.strategies import list_strategies, load_user_strategies
        from quant.web import app as _app
        if load_user_strategies():
            for nm in list_strategies():
                if nm not in _app.STRATEGIES:
                    _app.STRATEGIES.append(nm)
    except Exception:  # noqa: BLE001
        pass
    # 비-로컬 바인딩은 무인증 노출 위험이 있어 경고한다(/api/state가 포지션·손익을
    # 공개하고, 어떤 라우트든 백테스트를 강제 실행시킬 수 있다).
    if host not in _LOOPBACK:
        print(f"⚠️  경고: 비-로컬 주소({host})에 바인딩합니다. 웹 조종석은 인증이 없어")
        print("   같은 네트워크의 누구나 포지션·손익(/api/state)을 보고 백테스트를 돌릴 수 있습니다.")
        if not os.environ.get("QUANT_WEB_TOKEN"):
            print("   → QUANT_WEB_TOKEN 환경변수를 설정하면 토큰 인증이 켜집니다(권장).")
    from quant.web import auth as _auth
    if _auth.configured():
        print("🔐 로그인 켜짐 — 브라우저에서 아이디/비밀번호를 물어봅니다.")
    else:
        print("🔓 로그인 미설정 — 이 컴퓨터에서만 열립니다. 다른 기기에서도 보려면")
        print("   먼저 `python -m quant web-passwd` 로 아이디·비밀번호를 만드세요.")
    global _BIND_HOST
    _BIND_HOST = str(host).lower()
    server = ThreadingHTTPServer((host, port), QuantHandler)
    print(f"🌐 Quant 웹서버 실행: http://{host}:{port}  (Ctrl+C로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.shutdown()


if __name__ == "__main__":
    run_server()
