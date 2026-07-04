"""HTTP 헬퍼 테스트 — 오류 래핑 + 시크릿 URL 가림 + 리다이렉트 헤더 제거.

브로커·알림 호출측은 대개 RuntimeError만 처리한다. URLError를 그대로 흘리면
예기치 못하게 죽으므로 감싼다. 또한 오류 메시지의 URL에 담긴 API 키를 가려
로그 유출을 막고, 교차 호스트 리다이렉트 시 인증 헤더를 떼어낸다. (표준 라이브러리만)
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils import http


def test_urlerror_wrapped_and_redacted():
    def boom(*a, **kw):
        raise urllib.error.URLError("연결 거부")

    # 이제 _opener.open을 통해 요청하므로 그쪽을 목킹한다.
    with mock.patch.object(http._opener, "open", boom):
        try:
            http.get_json("https://api.stlouisfed.org/x?api_key=SECRET123")
            assert False, "RuntimeError 여야 함"
        except RuntimeError as exc:
            assert "네트워크 오류" in str(exc)
            assert "SECRET123" not in str(exc)      # 키가 메시지에서 가려짐
        except urllib.error.URLError:
            assert False, "URLError가 감싸지지 않고 새어나옴"


def test_httperror_wrapped_with_status_and_redacted():
    def boom(*a, **kw):
        raise urllib.error.HTTPError(
            "https://x?apikey=TOPSECRET", 404, "Not Found", hdrs=None,
            fp=__import__("io").BytesIO(b"nope"))

    with mock.patch.object(http._opener, "open", boom):
        try:
            http.get_json("https://x?apikey=TOPSECRET")
            assert False, "RuntimeError 여야 함"
        except RuntimeError as exc:
            assert "HTTP 404" in str(exc)
            assert "TOPSECRET" not in str(exc)


def test_redact_url_masks_secret_query_values():
    u = ("https://api.stlouisfed.org/fred?series_id=DGS10"
         "&api_key=SECRET123&file_type=json")
    r = http._redact_url(u)
    assert "SECRET123" not in r
    assert "series_id=DGS10" in r and "file_type=json" in r   # 비민감값 유지
    assert "TOP" not in http._redact_url("https://x?apikey=TOP")
    assert "PW" not in http._redact_url("https://x?password=PW&token=TK")
    assert "TK" not in http._redact_url("https://x?password=PW&token=TK")


def test_redirect_strips_auth_headers_cross_host():
    """다른 호스트로 리다이렉트되면 Authorization 등 민감 헤더가 제거된다."""
    handler = http._SafeRedirect()
    req = urllib.request.Request(
        "https://api.example.com/x",
        headers={"Authorization": "Bearer SEKRIT", "Accept": "application/json"})
    new = handler.redirect_request(
        req, __import__("io").BytesIO(b""), 302, "Found", {},
        "https://evil.attacker.com/x")
    assert new is not None
    hdr_keys = {k.lower() for k in new.headers}
    assert "authorization" not in hdr_keys       # 인증 헤더 제거됨
    # 같은 호스트 리다이렉트면 헤더 유지
    same = handler.redirect_request(
        req, __import__("io").BytesIO(b""), 302, "Found", {},
        "https://api.example.com/y")
    assert any(k.lower() == "authorization" for k in same.headers)
