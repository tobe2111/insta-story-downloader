"""로컬 조종석 보안 계약 검사 — 장부 오염 경로를 막는다.

배경(2026-08-11 감사): 웹 조종석의 /deposit/run은 GET + 쿼리 파라미터이고
Host 검증도 CSRF 방어도 없었다. 그래서

    <img src="http://127.0.0.1:8000/deposit/run?amount=10000000">

한 줄이 박힌 아무 웹페이지만 방문해도 **가짜 입금이 공개 장부에 커밋**된다.
이 프로젝트에서 장부 오염은 돈이 나가는 것만큼 나쁘다. DNS 리바인딩으로
/api/state(포지션·손익)를 읽히는 경로도 함께 열려 있었다.

핵심 계약:
  ① Host가 루프백(또는 실제 바인딩 주소)이 아니면 거부 — 리바인딩 차단
  ② 상태 변경 경로는 교차출처 요청을 거부 — CSRF 차단
  ③ 조회 경로와 비브라우저(curl) 요청은 막지 않는다 — 도구 사용성 유지
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.web import server as ws  # noqa: E402


class _H(ws.QuantHandler):
    """소켓 없이 헤더 검사만 하기 위한 최소 스텁."""

    def __init__(self, headers):  # noqa: D107 — 부모 __init__을 부르지 않는다
        self.headers = headers


def _mk(host="127.0.0.1:8000", **extra):
    return _H({"Host": host, **extra})


def test_loopback_host_is_accepted():
    for h in ("127.0.0.1:8000", "localhost:8000", "[::1]:8000", "localhost"):
        assert _mk(h)._host_ok(), h


def test_foreign_host_is_rejected():
    """DNS 리바인딩 — 공격자 도메인이 127.0.0.1로 해석되는 경우."""
    for h in ("evil.example.com:8000", "attacker.io"):
        assert not _mk(h)._host_ok(), h


def test_bound_host_is_accepted_when_not_loopback(monkeypatch):
    monkeypatch.setattr(ws, "_BIND_HOST", "192.168.0.7")
    assert _mk("192.168.0.7:8000")._host_ok()
    assert not _mk("192.168.0.8:8000")._host_ok()


def test_cross_site_deposit_is_blocked():
    p = urlparse("/deposit/run?amount=10000000")
    assert not _mk(**{"Sec-Fetch-Site": "cross-site"})._same_site_ok(p)
    assert not _mk(**{"Origin": "http://evil.example.com"})._same_site_ok(p)


def test_same_origin_deposit_is_allowed():
    p = urlparse("/deposit/run?amount=10000")
    assert _mk(**{"Sec-Fetch-Site": "same-origin"})._same_site_ok(p)
    assert _mk(**{"Origin": "http://127.0.0.1:8000"})._same_site_ok(p)


def test_non_browser_requests_still_work():
    """curl 등 헤더 없는 요청은 막지 않는다 — 로컬 CLI 사용을 위해."""
    assert _mk()._same_site_ok(urlparse("/deposit/run?amount=10000"))


def test_read_only_paths_are_not_restricted():
    for path in ("/api/state", "/monitor", "/broadcast", "/health", "/"):
        assert _mk(**{"Sec-Fetch-Site": "cross-site"})._same_site_ok(
            urlparse(path)), path


def test_expensive_compute_paths_are_also_protected():
    """수 분짜리 연산을 교차출처에서 반복 호출하면 PC 자원이 탄다."""
    for path in ("/optimize/run", "/sweep/run", "/portfolio/run",
                 "/screener/run", "/validate/run", "/backtest"):
        assert not _mk(**{"Sec-Fetch-Site": "cross-site"})._same_site_ok(
            urlparse(path)), path


def test_every_run_route_is_covered():
    """새 /run 경로가 생기면 보호 목록에도 들어가야 한다."""
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "web" / "server.py").read_text("utf-8")
    import re
    routes = set(re.findall(r'parsed\.path == "(/[^"]*)"', src))
    runs = {r for r in routes if r.endswith("/run")}
    assert runs <= set(ws.QuantHandler._MUTATING), (
        f"보호되지 않은 실행 경로: {sorted(runs - set(ws.QuantHandler._MUTATING))}")


def test_guards_run_before_anything_else():
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "web" / "server.py").read_text("utf-8")
    body = src.split("def do_GET")[1]
    i_host = body.index("_host_ok")
    i_csrf = body.index("_same_site_ok")
    i_auth = body.index("_authorized")
    assert i_host < i_auth and i_csrf < i_auth


# ── ④ 가드가 '호출되는지'까지 확인한다 (감사 58) ───────────────
#
# 위 검사들은 _host_ok()·_same_site_ok()를 직접 불러 판정만 본다. 그래서
# do_GET에서 그 호출을 통째로 무력화해도(`if False and not ...`) 전부
# 통과한다 — 변이 시험에서 실제로 그랬다. 함수가 옳은 것과 그 함수가
# 실제로 요청 경로에 꽂혀 있는 것은 다른 문제다. 여기서는 소켓 없이
# do_GET을 끝까지 돌려 응답 상태코드로 확인한다.


class _Wire(ws.QuantHandler):
    """소켓 없이 do_GET을 돌리는 스텁 — _send를 가로채 상태만 기록한다."""

    def __init__(self, path, headers):  # noqa: D107
        self.path = path
        self.headers = headers
        self.sent = []

    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        self.sent.append((status, str(body)[:200]))

    # 인증은 이 검사의 관심사가 아니다 — 토큰 미설정 시의 기본 동작을 쓴다.


def _get(path, **headers):
    h = {"Host": "127.0.0.1:8000", **headers}
    w = _Wire(path, h)
    w.do_GET()
    return w.sent[0] if w.sent else (200, "")


def test_cross_site_deposit_actually_gets_403():
    status, body = _get("/deposit/run?amount=10000000",
                        **{"Sec-Fetch-Site": "cross-site"})
    assert status == 403, "교차출처 입금 요청이 막히지 않았다"
    assert "CSRF" in body or "교차 출처" in body


def test_foreign_host_actually_gets_403():
    status, body = _get("/api/state", Host="evil.example.com:8000")
    assert status == 403, "DNS 리바인딩 요청이 막히지 않았다"
    assert "Host" in body


def test_evil_origin_deposit_actually_gets_403():
    status, _ = _get("/deposit/run?amount=1",
                     Origin="http://evil.example.com")
    assert status == 403


def test_readonly_cross_site_is_not_403():
    """조회 경로는 교차출처여도 CSRF로 막지 않는다(과잉 차단 방지)."""
    status, _ = _get("/health", **{"Sec-Fetch-Site": "cross-site"})
    assert status != 403
