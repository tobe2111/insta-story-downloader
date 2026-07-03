"""의존성 없는 최소 HTTP 헬퍼 (표준 라이브러리 urllib 사용).

requests 미설치 환경에서도 실거래 브로커가 동작하도록 한다.
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
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # 서버가 반환한 오류 본문도 파싱해 전달
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return _request("GET", url, headers)


def post_json(
    url: str, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    return _request("POST", url, headers, body)
