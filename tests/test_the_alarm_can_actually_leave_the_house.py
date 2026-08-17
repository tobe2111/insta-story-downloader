"""경보가 **마지막 한 걸음에서 전부 죽고 있었다** (감사 263).

2026-08-16 야간 배치 로그를 읽다가 나왔습니다. 그날 시스템은 경보 8건을
만들었습니다 — 보정 어긋남, 현금 부족 거부, 장중 감시 지연, 과최적화 의심,
판정 불가, 실력 미확인, 피처 유실, 판정 시계 리셋. 그리고 **8건 전부**가
이렇게 끝났습니다:

    디스코드 알림 실패: HTTP 403 https://discord.com/…  error code: 1010

클라우드플레어 오류 **1010은 "브라우저 서명 기반 차단"**입니다. 우리가 보낸
서명은 이랬습니다:

    User-Agent: Python-urllib/3.11        ← urllib 기본값. 아무도 안 정했다.

즉 **킬스위치·낙폭·배치 실패·과최적화 경보가 전부 도착하지 않고 있었습니다.**
감사 175 덕분에 '보냈다'로 기록되지는 않아 매일 재시도했지만, 매일 같은
이유로 막혔으니 사장님께는 한 건도 가지 않았습니다.

이 저장소가 반복해서 잡아 온 계열의 마지막 판입니다 — **장치는 다 있는데
그 장치가 내는 소리가 문밖으로 안 나갔습니다.**

⚠️ 검사가 제 첫 수정도 잡았습니다: `url_ok`는 `_request`를 안 거쳐서 그
   통로만 배선이 빠져 있었습니다. 신원을 붙이는 규칙을 한 곳(`_with_agent`)에
   모으고 두 통로가 함께 읽게 했습니다.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.utils.http import (  # noqa: E402
    USER_AGENT,
    _with_agent,
    get_json,
    get_text,
    post_json,
    post_text,
    url_ok,
)


class _Echo(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def _rec(self):
        type(self).seen.append(self.headers.get("User-Agent"))

    def do_POST(self):  # noqa: N802
        self._rec()
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_GET(self):  # noqa: N802
        self._rec()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    _Echo.seen = []
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Echo)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/hook", _Echo
    srv.shutdown()
    srv.server_close()


# ── 모든 통로가 신원을 밝히는가 ──────────────────────────────

def test_every_outbound_call_identifies_itself(server):
    """⚠️ 한 통로라도 빠지면 그 통로의 경보만 조용히 죽는다.

    실제로 `url_ok`가 그랬다 — `_request`를 안 거쳐 배선에서 빠졌고,
    이 검사가 그것을 잡았다.
    """
    url, echo = server
    post_text(url, {"content-type": "application/json"}, {"content": "x"})
    post_json(url, {"content-type": "application/json"}, {"content": "x"})
    get_text(url)
    get_json(url)
    url_ok(url)
    assert len(echo.seen) == 5
    for ua in echo.seen:
        assert ua == USER_AGENT, f"신원을 안 밝힌 통로가 있다: {ua!r}"


def test_the_default_agent_is_not_the_library_default(server):
    """`Python-urllib/…`이 그대로 나가면 클라우드플레어가 막는다."""
    assert "urllib" not in USER_AGENT.lower()
    assert USER_AGENT.strip(), "빈 User-Agent도 차단 대상이다"


def test_the_agent_says_who_we_are():
    """차단당했을 때 상대가 우리를 식별하고 풀어줄 수 있어야 한다."""
    assert "quant" in USER_AGENT.lower()
    assert "http" in USER_AGENT.lower(), "연락처(저장소 주소)가 없다"


def test_a_caller_can_still_choose_its_own(server):
    """대조군 — API가 특정 UA를 요구하는 경우가 있다. 덮어쓰면 안 된다."""
    url, echo = server
    post_text(url, {"User-Agent": "caller-chosen/9"}, {"a": 1})
    assert echo.seen == ["caller-chosen/9"]


@pytest.mark.parametrize("given,expect", [
    ({}, USER_AGENT),
    (None, USER_AGENT),
    ({"user-agent": "lower/1"}, "lower/1"),      # 대소문자 달라도 존중한다
    ({"USER-AGENT": "upper/1"}, "upper/1"),
])
def test_the_rule_is_case_insensitive(given, expect):
    got = _with_agent(given)
    ua = next(v for k, v in got.items() if k.lower() == "user-agent")
    assert ua == expect


def test_other_headers_survive():
    """신원을 붙이면서 원래 헤더를 잃으면 인증이 깨진다."""
    got = _with_agent({"Authorization": "Bearer x", "content-type": "application/json"})
    assert got["Authorization"] == "Bearer x"
    assert got["content-type"] == "application/json"


def test_the_caller_dict_is_not_mutated():
    """호출자가 재사용하는 헤더 dict를 몰래 바꾸면 안 된다."""
    original = {"Authorization": "Bearer x"}
    _with_agent(original)
    assert "User-Agent" not in original


# ── 규칙이 한 곳에만 있는가 ──────────────────────────────────

def test_only_one_place_decides_the_agent():
    """두 곳에서 붙이면 언젠가 한쪽만 고쳐져 그 통로가 다시 막힌다."""
    import re

    src = (ROOT / "quant" / "utils" / "http.py").read_text("utf-8")
    body = re.sub(r'"""(?:.|\n)*?"""', "", src)
    body = "\n".join(ln.split("#", 1)[0] for ln in body.splitlines())
    assert body.count("USER_AGENT") == 2, (
        "신원 문자열이 정의·사용 각 1회가 아니다 — 규칙이 흩어져 있다")
    assert body.count("urllib.request.Request(") == 2, (
        "요청을 만드는 자리가 늘었다 — 새 자리에도 _with_agent가 필요하다")
    assert body.count("_with_agent(") == 3, (
        "요청을 만드는 모든 자리가 _with_agent를 거치지 않는다")


# ── 전달 실패를 성공으로 적지 않는가 (감사 175가 남긴 방어선) ──

def test_a_failed_send_is_not_recorded_as_sent(tmp_path, monkeypatch):
    """막힌 경보가 '보냈다'로 적히면 **영원히 다시 오지 않는다.**

    감사 263의 사고에서 이 방어선이 실제로 값을 했다 — 매일 재시도했다.
    """
    from quant.live import flag_watch

    class _Dead:
        def send(self, message, level="info"):
            return False                    # 디스코드 1010과 같은 상황

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _Dead())
    status = {"validation": {"crypto:BTC/USDT": {"strategy": "ml",
                                                 "pbo": 0.72, "dsr": 0.99}}}
    first = flag_watch.check_and_notify_flags(status, str(tmp_path))
    assert first == [], "전달 실패인데 '새로 알림'으로 셌다"
    again = flag_watch.check_and_notify_flags(status, str(tmp_path))
    assert again == [], "재시도 자체가 사라졌다"

    class _Alive:
        def __init__(self):
            self.sent = []

        def send(self, message, level="info"):
            self.sent.append(message)
            return True

    live = _Alive()
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: live)
    third = flag_watch.check_and_notify_flags(status, str(tmp_path))
    assert third, "채널이 살아난 날 밀린 경보가 안 갔다"
    assert live.sent
