"""조종석 로그인이 **약속대로** 지키는가 (2026-08-18, 사장님 요청).

"모두가 다 접속 가능하면 안되니까" — 로그인을 만들었다. 이 파일이 지키는 것:

  ① 평문 비밀번호는 어디에도 저장되지 않는다 — .env에는 해시만.
  ② 틀린 비밀번호는 들어올 수 없고, 맞아도 세션은 만료된다.
  ③ 로그인이 설정되면 관문이 실제로 닫힌다 — 설정 전에는 예전과 같다
     (127.0.0.1 전용이라 본인 컴퓨터에서만 열리는 기본값을 깨지 않는다).
  ④ 실패 응답은 한 문장 — 아이디가 맞는지조차 알려주지 않는다.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.web import auth as A                    # noqa: E402
from quant.web import server as ws                 # noqa: E402

SRC = (ROOT / "quant" / "web" / "auth.py").read_text("utf-8")


# ── ① 평문은 어디에도 없다 ─────────────────────────────────────

def test_the_hash_never_contains_the_password():
    h = A.hash_password("hunter2-secret")
    assert "hunter2" not in h and h.startswith("pbkdf2$")
    _, iters, _salt, _dk = h.split("$", 3)
    assert int(iters) >= 100_000, (
        f"반복수가 {iters} — 해시가 너무 싸면 유출 시 몇 초 만에 풀린다")


def test_the_env_file_stores_only_the_hash(tmp_path, monkeypatch):
    # set_credentials가 환경변수도 채우므로, monkeypatch로 먼저 등록해 둬야
    # 검사가 끝날 때 원상복구된다 — 안 하면 뒤 검사들이 로그인 켜진 채 돈다.
    monkeypatch.setenv(A.ENV_USER, "placeholder")
    monkeypatch.setenv(A.ENV_HASH, "placeholder")
    env = tmp_path / ".env"
    env.write_text("BINANCE_KEY=abc\n", encoding="utf-8")
    A.set_credentials("boss@example.com", "very-secret-pw!", str(env))
    text = env.read_text("utf-8")
    assert "very-secret-pw" not in text, ".env에 평문 비밀번호가 적혔다"
    assert "pbkdf2$" in text and "boss@example.com" in text
    assert "BINANCE_KEY=abc" in text, "기존 API 키가 지워졌다 — 다른 비밀 보존 실패"


def test_no_hardcoded_credentials_in_source():
    """이 저장소는 공개다 — 실제 아이디·비밀번호가 코드에 적히면 전 세계 공개다."""
    for banned in ("naver.com", "358533"):
        assert banned not in SRC, "실제 자격증명이 코드에 하드코딩됐다"


# ── ② 검증·세션 ────────────────────────────────────────────────

def test_wrong_password_is_rejected():
    h = A.hash_password("right-password")
    assert A.verify_password("right-password", h)
    assert not A.verify_password("wrong-password", h)
    assert not A.verify_password("right-password", "garbage")
    assert not A.verify_password("right-password", "")


def test_comparison_is_constant_time_by_construction():
    assert "compare_digest" in SRC, (
        "== 비교는 한 글자씩 맞춰 보는 타이밍 공격에 열린다")


def test_sessions_expire_and_reject_tampering():
    t0 = 1_000_000.0
    tok = A.issue_session(t0)
    assert A.check_session(tok, t0 + 60)
    assert not A.check_session(tok, t0 + A.SESSION_TTL_SECONDS + 61), (
        "세션이 만료되지 않는다 — 훔친 쿠키가 영원히 산다")
    exp, sig = tok.split(".", 1)
    forged = f"{int(exp) + 999999}.{sig}"
    assert not A.check_session(forged, t0 + 60), (
        "만료시각을 손으로 늘려도 통과한다 — 서명이 장식이다")


# ── ③ 관문이 실제로 닫힌다 ─────────────────────────────────────

class _Wire(ws.QuantHandler):
    def __init__(self, path, headers=None):  # noqa: D107
        self.path = path
        self.headers = {"Host": "127.0.0.1:8000", "Content-Length": "0",
                        **(headers or {})}
        self.rfile = io.BytesIO(b"")
        self.sent = []

    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        self.sent.append((status, str(body)[:300],
                          dict(getattr(self, "_extra_headers", None) or {})))
        self._extra_headers = None


def _login_on(monkeypatch):
    monkeypatch.setenv(A.ENV_USER, "boss@example.com")
    monkeypatch.setenv(A.ENV_HASH, A.hash_password("correct-horse-9!"))


def test_without_setup_the_cockpit_opens_as_before(monkeypatch):
    monkeypatch.delenv(A.ENV_USER, raising=False)
    monkeypatch.delenv(A.ENV_HASH, raising=False)
    monkeypatch.delenv("QUANT_WEB_TOKEN", raising=False)
    w = _Wire("/monitor")
    monkeypatch.setattr(ws, "render_monitor", lambda: "<h1>m</h1>")
    w.do_GET()
    assert w.sent[0][0] == 200, "설정 전 기본값(로컬 전용·게이트 없음)이 깨졌다"


def test_with_setup_the_front_door_redirects_to_login(monkeypatch):
    _login_on(monkeypatch)
    w = _Wire("/")
    w.do_GET()
    status, _body, headers = w.sent[0]
    assert status == 302 and headers.get("Location") == "/login", (
        f"로그인 설정 후에도 첫 화면이 열린다: {w.sent[0]}")


def test_the_login_page_itself_stays_reachable(monkeypatch):
    _login_on(monkeypatch)
    w = _Wire("/login")
    w.do_GET()
    status, body, _ = w.sent[0]
    assert status == 200 and "로그인" in body, (
        "로그인 화면까지 잠그면 아무도 못 들어온다")


def test_health_stays_open_for_liveness(monkeypatch):
    _login_on(monkeypatch)
    w = _Wire("/health")
    w.do_GET()
    assert w.sent[0][0] == 200


def test_a_valid_session_cookie_opens_the_door(monkeypatch):
    import time
    _login_on(monkeypatch)
    monkeypatch.setattr(ws, "render_form", lambda *a, **k: "<h1>home</h1>")
    tok = A.issue_session(time.time())
    w = _Wire("/", {"Cookie": f"{A.COOKIE_NAME}={tok}"})
    w.do_GET()
    assert w.sent[0][0] == 200, f"유효한 세션인데 막혔다: {w.sent[0]}"


def test_a_forged_cookie_does_not(monkeypatch):
    _login_on(monkeypatch)
    w = _Wire("/", {"Cookie": f"{A.COOKIE_NAME}=9999999999.deadbeef"})
    w.do_GET()
    assert w.sent[0][0] == 302, "위조 쿠키로 들어와졌다"


# ── ④ 로그인 시도 자체 ─────────────────────────────────────────

def test_a_correct_login_sets_a_hardened_cookie(monkeypatch):
    _login_on(monkeypatch)
    hdrs: dict = {}
    html = A.run_login({"user": "boss@example.com",
                        "password": "correct-horse-9!"}, hdrs)
    ck = hdrs.get("Set-Cookie", "")
    assert A.COOKIE_NAME in ck and "HttpOnly" in ck and "SameSite=Strict" in ck, (
        f"쿠키가 무장돼 있지 않다: {ck}")
    assert "url=/" in html


def test_a_wrong_login_says_one_sentence_and_sets_nothing(monkeypatch):
    _login_on(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda *_: None)   # 검사만 빨리
    for user, pw in (("boss@example.com", "wrong"),
                     ("nobody@example.com", "correct-horse-9!")):
        hdrs: dict = {}
        html = A.run_login({"user": user, "password": pw}, hdrs)
        assert "Set-Cookie" not in hdrs
        assert "아이디 또는 비밀번호가 다릅니다" in html, (
            "어느 쪽이 틀렸는지 알려주고 있다 — 아이디 탐색을 공짜로 시켜준다")


def test_failure_costs_a_second():
    assert "time.sleep(1.0)" in SRC, (
        "실패 비용이 없다 — 초당 수천 번 무차별 대입이 가능해진다")
