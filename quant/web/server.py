"""가벼운 로컬 웹서버 (표준 라이브러리 http.server).

외부 웹 프레임워크(Flask/FastAPI) 없이 브라우저에서 백테스트를 실행하고
리포트를 볼 수 있게 한다. 로컬 전용 도구이므로 localhost 바인딩을 기본으로 한다.

    python -m quant.web.server            # http://127.0.0.1:8000
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from quant.web.app import render_form, run_backtest_html


class QuantHandler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
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
        else:
            self._send(render_form("알 수 없는 경로입니다."), status=404)

    def log_message(self, *args) -> None:  # 기본 액세스 로그 억제
        pass


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), QuantHandler)
    print(f"🌐 Quant 웹서버 실행: http://{host}:{port}  (Ctrl+C로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.shutdown()


if __name__ == "__main__":
    run_server()
