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

from quant.web.app import (
    render_form,
    render_monitor,
    render_optimize_form,
    render_portfolio_form,
    render_screener_form,
    render_sweep_form,
    render_validate_form,
    run_backtest_html,
    run_optimize_html,
    run_portfolio_html,
    run_screener_html,
    run_sweep_html,
    run_validate_html,
    state_json,
)


class QuantHandler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200,
              content_type: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, parsed) -> bool:
        """QUANT_WEB_TOKEN이 설정된 경우에만 토큰 인증을 요구한다.

        기본(토큰 미설정)은 게이트 없음 — 로컬 전용 도구라 무리 없다. 비-로컬
        주소에 바인딩해 노출할 때 이 토큰을 켜면 무인증 접근을 막는다. /health는
        라이브니스 체크용으로 항상 허용.
        """
        token = os.environ.get("QUANT_WEB_TOKEN", "")
        if not token or parsed.path == "/health":
            return True
        q = parse_qs(parsed.query)
        supplied = q["token"][0] if q.get("token") else self.headers.get("X-Auth-Token", "")
        return hmac.compare_digest(supplied, token)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorized(parsed):
            self._send("인증이 필요합니다: ?token=... 또는 X-Auth-Token 헤더를 제공하세요.",
                       status=401, content_type="text/plain; charset=utf-8")
            return
        if parsed.path in ("/", "/index.html"):
            self._send(render_form())
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

    def log_message(self, *args) -> None:  # 기본 액세스 로그 억제
        pass


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    # .env 자동 로딩 — setup 마법사로 저장한 키를 웹 경로에서도 쓸 수 있게.
    from quant.utils.envfile import load_env_file
    load_env_file()
    # 비-로컬 바인딩은 무인증 노출 위험이 있어 경고한다(/api/state가 포지션·손익을
    # 공개하고, 어떤 라우트든 백테스트를 강제 실행시킬 수 있다).
    if host not in _LOOPBACK:
        print(f"⚠️  경고: 비-로컬 주소({host})에 바인딩합니다. 웹 조종석은 인증이 없어")
        print("   같은 네트워크의 누구나 포지션·손익(/api/state)을 보고 백테스트를 돌릴 수 있습니다.")
        if not os.environ.get("QUANT_WEB_TOKEN"):
            print("   → QUANT_WEB_TOKEN 환경변수를 설정하면 토큰 인증이 켜집니다(권장).")
    server = ThreadingHTTPServer((host, port), QuantHandler)
    print(f"🌐 Quant 웹서버 실행: http://{host}:{port}  (Ctrl+C로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.shutdown()


if __name__ == "__main__":
    run_server()
