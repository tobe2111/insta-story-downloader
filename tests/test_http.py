"""HTTP 헬퍼 테스트 — 네트워크 오류가 일관되게 RuntimeError로 감싸지는지 검증.

브로커·알림 호출측은 대개 RuntimeError만 처리한다. URLError(DNS·연결거부·타임아웃)를
그대로 흘리면 예기치 못하게 죽으므로 반드시 감싸야 한다. (표준 라이브러리만 사용)
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils import http


def test_urlerror_wrapped_as_runtimeerror():
    def boom(*a, **kw):
        raise urllib.error.URLError("연결 거부")

    with mock.patch.object(http.urllib.request, "urlopen", boom):
        try:
            http.get_json("https://example.invalid/x")
            assert False, "RuntimeError 여야 함"
        except RuntimeError as exc:
            assert "네트워크 오류" in str(exc)
        except urllib.error.URLError:
            assert False, "URLError가 감싸지지 않고 새어나옴"


def test_httperror_wrapped_with_status():
    def boom(*a, **kw):
        raise urllib.error.HTTPError(
            "https://x", 404, "Not Found", hdrs=None,
            fp=__import__("io").BytesIO(b"nope"))

    with mock.patch.object(http.urllib.request, "urlopen", boom):
        try:
            http.get_json("https://x")
            assert False, "RuntimeError 여야 함"
        except RuntimeError as exc:
            assert "HTTP 404" in str(exc)
