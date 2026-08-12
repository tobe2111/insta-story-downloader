"""리다이렉트 한 번에 실거래 키가 평문으로 나갔다 (감사 170).

`quant/utils/http.py`는 이 시스템이 바깥과 말하는 유일한 통로다. 알파카
APCA 키, KIS appkey/appsecret, 디스코드·슬랙 웹훅 토큰이 전부 이 헤더에
실린다. 그래서 이 파일은 처음부터 두 가지를 약속하고 있었다 —
"교차 호스트 리다이렉트에서 인증 헤더를 뗀다", "오류 메시지에서 키를 가린다".

두 약속 다 반쪽이었다.

──────────────────────────────────────────────────────────────
① 호스트만 보고 **스킴 강등**을 놓쳤다

    same_host = (urlsplit(req.full_url).netloc == urlsplit(newurl).netloc)
    if not same_host:
        ...민감 헤더 제거...

`netloc`은 호스트:포트다. 스킴(https/http)이 안 들어간다. 그래서 같은
호스트로의 **https → http** 리다이렉트가 "같은 곳이니 괜찮다"로 통과했다.

    실측  https://api.example.com/v1 → http://api.example.com/v2
          Authorization·X-Api-Key 그대로 유지  → **평문 전송**

상대 서버가 302 한 번만 내려 주면(또는 중간자가 그렇게 만들면) 실거래
자격증명이 도청 가능한 채널로 나간다.

② URL은 가리면서 **서버가 준 본문은 안 가렸다**

    detail = exc.read().decode(errors="replace")[:2000]
    raise HttpError(f"HTTP {exc.code} {_redact_url(url)}: {detail}")

API 오류 응답은 요청을 되울리는 일이 흔하다 —
`{"error":"Invalid API key","request":"...?apikey=SUPERSECRET123"}`.
그러면 왼쪽 칸에서 애써 가린 키가 바로 오른쪽 칸으로 새어 로그에 남는다.

가릴 거면 **두 통로를 다 가려야 한다.** 한쪽만 가린 것은 가렸다는 착각만
만든다.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.utils.http import _SafeRedirect, _redact_url  # noqa: E402

SECRET_HEADERS = {
    "Authorization": "Bearer SECRET-TOKEN",
    "X-Api-Key": "KEY123",
    "APCA-API-KEY-ID": "APCA-ID",
    "appsecret": "KIS-SECRET",
}


class _FakeBody:
    def read(self, *a):
        return b""


def _redirect(old: str, new: str):
    req = urllib.request.Request(old, headers={**SECRET_HEADERS,
                                               "Accept": "application/json"})
    out = _SafeRedirect().redirect_request(req, _FakeBody(), 302, "Found", {}, new)
    assert out is not None
    kept = sorted(k for k in out.headers
                  if k.lower() in {h.lower() for h in SECRET_HEADERS})
    return out, kept


# ── ① 자격증명이 따라가면 안 되는 곳 ─────────────────────────


def test_a_scheme_downgrade_strips_the_credentials():
    """이것이 감사 170 — 같은 호스트라도 http로 내려가면 평문이다."""
    _, kept = _redirect("https://api.example.com/v1",
                        "http://api.example.com/v2")
    assert kept == [], (
        f"https에서 http로 내려가는데 {kept}가 그대로 따라간다 — 평문 전송이다")


def test_a_cross_host_redirect_still_strips_the_credentials():
    """대조군 — 원래 막던 것이 계속 막혀야 한다."""
    _, kept = _redirect("https://api.example.com/v1", "https://evil.net/steal")
    assert kept == [], kept


@pytest.mark.parametrize("old,new", [
    ("https://api.example.com/v1", "https://api.example.com:8443/v2"),  # 포트 변경
    ("https://api.example.com/v1", "https://sub.api.example.com/v2"),   # 서브도메인
])
def test_any_change_of_destination_strips_the_credentials(old, new):
    _, kept = _redirect(old, new)
    assert kept == [], (old, new, kept)


# ── 대조군: 정당한 리다이렉트까지 망가뜨리면 안 된다 ──────────


def test_the_same_secure_destination_keeps_the_credentials():
    """같은 호스트·같은 https면 인증이 유지돼야 한다 — 아니면 API가 통째로 깨진다."""
    _, kept = _redirect("https://api.example.com/v1",
                        "https://api.example.com/v2")
    assert len(kept) == len(SECRET_HEADERS), kept


def test_an_upgrade_to_https_keeps_the_credentials():
    """http → https 승격은 흔하고 안전하다. 이것까지 막으면 과잉이다."""
    _, kept = _redirect("http://api.example.com/v1",
                        "https://api.example.com/v2")
    assert len(kept) == len(SECRET_HEADERS), kept


def test_ordinary_headers_are_never_stripped():
    """민감하지 않은 헤더까지 떼면 요청이 깨진다."""
    out, _ = _redirect("https://api.example.com/v1", "http://api.example.com/v2")
    assert any(k.lower() == "accept" for k in out.headers), dict(out.headers)


# ── ② 오류 메시지의 두 통로 ───────────────────────────────────


LEAKY = "https://api.example.com/v3?apikey=SUPERSECRET123&sym=AAPL"


def test_the_url_is_redacted():
    assert "SUPERSECRET123" not in _redact_url(LEAKY)
    assert "sym=AAPL" in _redact_url(LEAKY), "가릴 것만 가려야 한다"


def test_the_error_body_is_redacted_too():
    """서버가 요청 URL을 되울리면 키가 본문 쪽으로 새어 나간다."""
    body = '{"error":"Invalid API key","request":"' + LEAKY + '"}'
    assert "SUPERSECRET123" not in _redact_url(body), (
        "URL은 가리면서 서버가 준 본문은 안 가린다 — 같은 키가 옆 칸으로 샌다")


@pytest.mark.parametrize("param", [
    "api_key", "apikey", "access_token", "token", "secret", "password", "signature",
])
def test_every_known_secret_parameter_is_covered(param):
    url = f"https://x.example.com/y?{param}=TOPSECRET&ok=1"
    assert "TOPSECRET" not in _redact_url(url), param


def test_the_redaction_is_applied_where_the_error_is_raised():
    """배선 — 부품(_redact_url)이 아니라 예외를 만드는 자리를 본다."""
    src = (ROOT / "quant" / "utils" / "http.py").read_text("utf-8")
    assert "_redact_url(exc.read()" in src, (
        "오류 본문이 가려지지 않은 채 예외 메시지에 들어간다")


# ── 상태 파일 임시 이름 (형제) ────────────────────────────────


def test_the_atomic_write_uses_a_process_unique_temp_name():
    """고정 이름 .tmp를 두 프로세스가 동시에 밟으면, 원자적으로 '반쪽'이 완성된다.

    캐시 쪽(감사 162)에서 같은 것을 고쳤다. 상태 JSON은 장부가 사는 곳이라
    같은 규칙을 지켜야 한다.
    """
    src = (ROOT / "quant" / "utils" / "jsonio.py").read_text("utf-8")
    assert "os.getpid()" in src, "임시 파일 이름이 프로세스마다 다르지 않다"


def test_the_state_write_is_still_atomic_and_nan_safe(tmp_path):
    """대조군 — 임시 이름을 바꾸다 원자성·NaN 안전을 깨면 안 된다."""
    import json
    import math

    from quant.utils.jsonio import atomic_write_json

    p = tmp_path / "state.json"
    atomic_write_json(p, {"a": float("nan"), "b": [1.0, float("inf")], "c": "ok"})
    got = json.loads(p.read_text(encoding="utf-8"))
    assert got == {"a": None, "b": [1.0, None], "c": "ok"}, got
    assert not list(tmp_path.glob("*.tmp")), "임시 파일이 남았다"
    assert not math.isnan(0.0)          # (sanity)
