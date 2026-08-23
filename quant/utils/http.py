"""의존성 없는 최소 HTTP 헬퍼 (표준 라이브러리 urllib 사용).

requests 미설치 환경에서도 실거래 브로커/알림이 동작하도록 한다.
HTTPS_PROXY 등 프록시 환경변수는 urllib 기본 opener가 자동 적용한다.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# 응답 본문 상한(악의적/오작동 서버의 초대형 응답으로 인한 메모리 고갈 방지).
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024   # 32MB (API JSON엔 넉넉)

# 쿼리스트링에 담긴 비밀(FRED api_key, FMP apikey 등)을 오류 메시지에서 가린다.
# 예외 메시지가 로그로 새어도 키가 노출되지 않도록 소스에서 방어한다.
# ⚠️ 예전에는 앞에 `?`나 `&`가 **있어야만** 가렸다(감사 248). 그런데 이
#    저장소는 Meta API에 토큰을 **본문(form)**으로 보낸다 — 오류 응답이 그
#    본문을 되울리면 `access_token=EAAG...`가 문자열 맨 앞이나 따옴표 뒤에
#    오고, 그때는 가리개가 한 글자도 안 지웠다:
#
#        {"error":{"message":"Invalid: access_token=EAAG…"}}   ← 그대로 노출
#        access_token=EAAG…&media_type=IMAGE                   ← 그대로 노출
#
#    그리고 이 문자열은 로그로만 가지 않는다. SNS 게시 결과(posted.json)는
#    `docs/` 안에 쓰여 **공개 사이트에 그대로 배포된다.**
#    이제 줄 시작·공백·따옴표·괄호 뒤에서도 가린다. 값의 끝도 따옴표에서
#    끊는다 — 안 그러면 JSON 뒷부분까지 통째로 별표가 된다.
_SECRET_QS = re.compile(
    r"(?i)(^|[?&\s\"'{,\[])((?:api[_-]?key|apikey|access[_-]?token|token|"
    r"app[_-]?secret|app[_-]?key|secret[_-]?key|secret|password|passwd|pwd|"
    r"crtfc[_-]?key|"    # DART 인증키 — 이름이 일반 패턴 밖이라 명시(2026-08-23)
    r"sig|signature)=)[^&#\s\"'}\]]*")

# 다른 호스트로 리다이렉트될 때 떼어낼 민감 헤더(인증정보 유출 방지).
_SENSITIVE_HEADERS = {
    "authorization", "cookie", "apca-api-key-id", "apca-api-secret-key",
    "appkey", "appsecret", "secretkey", "api-id", "x-api-key",
}


def redact_secrets(text: str) -> str:
    """문자열에서 비밀값을 가린다 — URL·오류 본문·게시 결과 어디서든.

    가릴 거면 **모든 통로**를 가려야 한다(감사 170·248). 하나라도 열려
    있으면 나머지를 가린 노력이 통째로 무의미하다.
    """
    return _SECRET_QS.sub(r"\1\2***", str(text))


def _redact_url(url: str) -> str:
    return redact_secrets(url)


class HttpError(RuntimeError):
    """HTTP 상태코드를 들고 다니는 오류. RuntimeError라 기존 except와 호환된다.

    왜 필요한가(감사 55): 호출부가 '404 = 자원 없음'과 '401/500/타임아웃 =
    모르겠음'을 구분해야 하는데, 예전에는 둘 다 그냥 RuntimeError였다.
    us_live.get_position이 그 구분 없이 모든 실패를 '포지션 없음(0주)'으로
    처리하고 있었다 — 토큰이 만료된 실거래 계좌에서 보유를 0으로 읽으면
    목표 비중만큼 **다시 사서** 포지션이 두 배가 된다.

    status는 HTTP 응답 코드, 네트워크 오류(DNS·연결거부·타임아웃)는 None.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """교차 호스트 리다이렉트 시 인증 헤더를 제거한다.

    urllib 기본 동작은 3xx 리다이렉트에 원 요청 헤더(Authorization 등)를 그대로
    실어 보낸다. 상단 API가 공격자 호스트로 302하면 인증정보가 유출되므로,
    호스트가 바뀌면 민감 헤더를 떼어낸다.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            old = urllib.parse.urlsplit(req.full_url)
            nxt = urllib.parse.urlsplit(newurl)
            # ⚠️ **호스트만 보면 안 된다**(감사 170). 예전에는 netloc만
            #    비교해서, 같은 호스트로의 **스킴 강등**(https → http)이
            #    "같은 곳이니 괜찮다"로 통과했다. 실측:
            #
            #        https://api.example.com/v1 → http://api.example.com/v2
            #            Authorization·X-Api-Key 그대로 유지 → **평문 전송**
            #
            #    여기 실려 나가는 것은 실거래 자격증명이다(알파카 APCA 키,
            #    KIS appkey/appsecret, 웹훅 토큰). 리다이렉트 한 번으로
            #    도청 가능한 채널에 키가 나간다.
            #
            #    업그레이드(http → https)는 흔하고 안전하므로 막지 않는다.
            downgrade = old.scheme == "https" and nxt.scheme != "https"
            if old.netloc != nxt.netloc or downgrade:
                for h in [k for k in new.headers if k.lower() in _SENSITIVE_HEADERS]:
                    del new.headers[h]
        return new


# 프록시(환경변수) 처리는 유지하되 리다이렉트 핸들러만 안전판으로 교체한다.
_opener = urllib.request.build_opener(_SafeRedirect())


# 우리가 밝히는 신원. 디스코드·깃허브 등 다수 API가 User-Agent를 요구하거나
# 없으면 봇으로 보고 막는다(감사 263 — 클라우드플레어 1010으로 경보가 전부
# 죽었다). 연락처를 함께 적는 것이 이런 API의 관례다.
USER_AGENT = "quant-bot/1.0 (+https://github.com/tobe2111/insta-story-downloader)"


def _with_agent(headers: dict[str, str] | None) -> dict[str, str]:
    """신원을 붙인 헤더 — **이 규칙은 여기 한 곳에만 둔다.**

    호출자가 직접 지정했으면 그것을 존중한다(API가 특정 UA를 요구할 수 있다).
    지정하지 않았을 때만 우리 이름을 붙인다.
    """
    sent = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in sent):
        sent["User-Agent"] = USER_AGENT
    return sent


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
    # ⚠️ **User-Agent를 안 보내면 경보가 통째로 죽는다** (2026-08-17, 감사 263).
    #    urllib의 기본값은 `Python-urllib/3.x`이고, 클라우드플레어 뒤에 있는
    #    서비스(디스코드가 그렇다)는 그 서명을 봇으로 보고 막는다:
    #
    #        2026-08-16 야간 배치 로그 —
    #        디스코드 알림 실패: HTTP 403 … error code: 1010   (× 8건 전부)
    #
    #    1010은 "브라우저 서명 기반 차단"이다. 즉 킬스위치·낙폭·배치 실패·
    #    과최적화 경보가 **마지막 한 걸음에서 전부 조용히 죽고 있었다.**
    #    감사 175 덕분에 '보냈다'로 기록되지는 않아 매일 재시도했지만,
    #    매일 같은 이유로 막혔으니 사장님께는 한 건도 도착하지 않았다.
    #
    #    호출자가 직접 지정했으면 그것을 존중한다(API가 특정 UA를 요구할 수
    #    있다). 지정하지 않았을 때만 우리 이름을 붙인다.
    return _request_raw(method, url, headers, data, timeout).decode()


def _request_raw(
    method: str,
    url: str,
    headers: dict[str, str] | None,
    data: bytes | None,
    timeout: int,
) -> bytes:
    """요청을 보내고 응답 본문을 **바이트**로 반환한다(zip 등 비텍스트용).

    상한·리다이렉트 방어·비밀 가림은 텍스트 경로와 완전히 같다 — 바이너리
    경로만 방어를 지나치면 감사 178이 반대쪽 문으로 재발한다.
    """
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=_with_agent(headers))
    try:
        with _opener.open(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise RuntimeError(f"응답이 너무 큽니다(>{_MAX_RESPONSE_BYTES}B): "
                                   f"{_redact_url(url)}")
            return raw
    except urllib.error.HTTPError as exc:  # 서버가 반환한 오류 본문도 파싱해 전달
        # ⚠️ **본문도 가려야 한다**(감사 170). URL은 가리면서 서버가 돌려준
        #    본문은 그대로 실었다. 그런데 API 오류 응답은 요청 URL을 되울리는
        #    일이 흔하다 — `{"error":"Invalid API key","request":"...apikey=..."}`.
        #    그러면 이 모듈이 URL에서 애써 가린 키가 바로 옆 칸으로 다시
        #    새어 나가 로그에 남는다. 가릴 거면 두 통로를 다 가려야 한다.
        detail = _redact_url(exc.read().decode(errors="replace")[:2000])
        raise HttpError(f"HTTP {exc.code} {_redact_url(url)}: {detail}",
                        status=exc.code) from exc
    except urllib.error.URLError as exc:  # DNS·연결거부·타임아웃 등 네트워크 오류
        # HTTPError가 아닌 URLError를 그대로 흘리면 호출측(대개 RuntimeError만
        # 처리)이 놓쳐 예기치 못하게 죽는다. 일관되게 RuntimeError로 감싼다.
        # status=None = '서버 응답을 못 받았다' — 404(없음)와 구분된다.
        raise HttpError(f"네트워크 오류 {_redact_url(url)}: {exc.reason}") from exc


def get_json(url: str, headers: dict[str, str] | None = None,
             timeout: int = 30) -> dict[str, Any]:
    raw = _request("GET", url, headers, timeout=timeout)
    return json.loads(raw) if raw else {}


def get_text(url: str, headers: dict[str, str] | None = None,
             timeout: int = 30) -> str:
    """GET 응답 본문을 원문(str)으로 반환한다 — RSS/XML 등 비-JSON용."""
    return _request("GET", url, headers, timeout=timeout)


def get_bytes(url: str, headers: dict[str, str] | None = None,
              timeout: int = 30) -> bytes:
    """GET 응답 본문을 바이트로 반환한다 — zip 등 비텍스트용(같은 방어)."""
    return _request_raw("GET", url, headers, None, timeout)


def post_json(
    url: str, headers: dict[str, str] | None = None, body: Any = None
) -> dict[str, Any]:
    raw = _request("POST", url, headers, body)
    return json.loads(raw) if raw else {}


def url_ok(url: str, timeout: int = 20,
           headers: dict[str, str] | None = None) -> bool:
    """URL이 지금 공개적으로 응답하는가 — **본문을 해석하지 않는다.**

    ⚠️ 이미지 같은 바이너리를 `get_text`로 확인하면 안 된다(감사 172).
       `get_text`는 본문을 UTF-8로 디코드하는데, PNG의 첫 바이트 0x89는
       UTF-8 시작 바이트가 아니라 **UnicodeDecodeError**가 난다. 그건
       `RuntimeError`가 아니라 `ValueError`라, 호출부가 쳐 놓은
       `except RuntimeError` 재시도 그물을 그대로 빠져나간다.

       결과가 고약하다 — 이미지가 **정상적으로 공개된 순간** 확인 단계가
       죽는다. 성공 경로가 곧 실패 경로다.

    반환: 2xx면 True, 그 외(4xx·5xx·네트워크 오류)면 False. 예외를 던지지
    않으므로 호출부는 '되면 True'만 보면 된다.
    """
    # ⚠️ 이 함수는 `_request`를 안 거친다 — 그래서 감사 263의 User-Agent 배선이
    #    여기만 빠졌었다. 검사가 그 사실을 잡았다. 신원을 붙이는 규칙은 한
    #    곳(`_with_agent`)에만 두고 두 통로가 함께 읽는다.
    req = urllib.request.Request(url, method="GET", headers=_with_agent(headers))
    try:
        with _opener.open(req, timeout=timeout) as resp:
            resp.read(1)          # 헤더만 주는 서버 대비 — 딱 1바이트
            return 200 <= int(getattr(resp, "status", 200) or 200) < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def post_text(
    url: str, headers: dict[str, str] | None = None, body: Any = None
) -> str:
    """응답을 JSON으로 파싱하지 않고 원문 그대로 반환한다.

    Slack 웹훅처럼 'ok' 같은 비-JSON 응답을 주는 엔드포인트에 사용.
    """
    return _request("POST", url, headers, body)
