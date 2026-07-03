"""의존성 없는 최소 HTTP 헬퍼 (표준 라이브러리 urllib 사용).

requests 미설치 환경에서도 실거래 브로커/알림이 동작하도록 한다.
HTTPS_PROXY 등 프록시 환경변수는 urllib 기본 opener가 자동 적용한다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: int = 30,
) -> str:
    """요청을 보내고 응답 본문을 원문(str)으로 반환한다."""
    if body is None:
        data = None
    elif isinstance(body, (bytes, str)):
        data = body.encode() if isinstance(body, str) else body
    else:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as exc:  # 서버가 반환한 오류 본문도 파싱해 전달
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    raw = _request("GET", url, headers)
    return json.loads(raw) if raw else {}


def post_json(
    url: str, headers: dict[str, str] | None = None, body: Any = None
) -> dict[str, Any]:
    raw = _request("POST", url, headers, body)
    return json.loads(raw) if raw else {}


def post_text(
    url: str, headers: dict[str, str] | None = None, body: Any = None
) -> str:
    """응답을 JSON으로 파싱하지 않고 원문 그대로 반환한다.

    Slack 웹훅처럼 'ok' 같은 비-JSON 응답을 주는 엔드포인트에 사용.
    """
    return _request("POST", url, headers, body)
