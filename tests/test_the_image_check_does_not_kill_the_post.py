"""이미지가 **정상 공개된 순간** SNS 게시가 죽었다 (감사 172).

게시 직전에 `_wait_public`이 카드 이미지가 공개됐는지 확인한다. 커밋 →
Cloudflare 배포까지 1~2분 걸리는데, 404인 채로 Meta에 URL을 넘기면 컨테이너가
ERROR가 되기 때문이다. 좋은 장치인데 확인 방법이 틀렸다.

    from quant.utils.http import get_text
    fetch = http_get or (lambda u: get_text(u, timeout=20))
    ...
        try:
            fetch(u)
            ok = True
        except RuntimeError:      # ← 여기로 안 온다
            sleep(delay)

여기 오는 URL은 **PNG 카드**(`01_card.png` … 8장)다. `get_text`는 응답 본문을
UTF-8로 디코드하는데, PNG의 첫 바이트 `0x89`는 UTF-8 시작 바이트가 아니다.

    UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89 in position 0

그리고 `UnicodeDecodeError`는 `ValueError`지 **`RuntimeError`가 아니다.**
그래서 재시도 그물을 그대로 빠져나가 `run_social_post` 밖으로 튀어나간다.

방향이 거꾸로다:

    이미지가 아직 없다(404) → HttpError(RuntimeError) → 잡힘 → 재시도  ✅
    이미지가 정상 공개됨(200) → UnicodeDecodeError → **게시 전체 실패**  ❌

**성공 경로가 곧 실패 경로였다.**

──────────────────────────────────────────────────────────────
왜 아무도 못 잡았나 — 이 단계를 켜고 도는 검사가 하나도 없었다

기존 SNS 검사 8건이 **전부 `wait_public=False`** 로 이 단계를 꺼 놓고 돈다.
게시 파이프라인은 촘촘히 검사돼 있는데, 하필 실전에서만 켜지는 이 한 단계가
검사 그물 밖에 있었다(FROZEN_IDEAS ㉜ — 아무도 안 보는 경로).

고침: 본문을 해석하지 않는 `url_ok`로 확인한다. 응답 코드만 본다.
"""

from __future__ import annotations

import io
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.utils.http as H  # noqa: E402
from quant.reporting.social_post import _wait_public  # noqa: E402

# PNG 매직 넘버 — 0x89로 시작해 UTF-8로 디코드되지 않는다
PNG_BYTES = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Serving:
    """이미지를 정상적으로 내주는 서버."""

    def __init__(self, body=PNG_BYTES, status=200):
        self.body, self.status = body, status

    def open(self, req, timeout=None):
        r = _Resp(self.body)
        r.status = self.status
        return r


class _NotFound:
    def open(self, req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)


class _Down:
    def open(self, req, timeout=None):
        raise urllib.error.URLError("connection refused")


@pytest.fixture
def opener(monkeypatch):
    def _set(obj):
        monkeypatch.setattr(H, "_opener", obj)
    return _set


# ── 전제: 이 바이트는 정말 UTF-8로 안 읽힌다 ──────────────────


def test_a_png_cannot_be_decoded_as_text():
    with pytest.raises(UnicodeDecodeError) as e:
        PNG_BYTES.decode()
    assert not isinstance(e.value, RuntimeError), (
        "UnicodeDecodeError가 RuntimeError였다면 예전 코드도 잡았을 것이다")


# ── 본체: 이미지가 있으면 통과해야 한다 ───────────────────────


def test_a_published_image_lets_the_post_proceed(opener):
    """감사 172의 본체 — 여기서 죽으면 그날 게시가 통째로 안 나간다."""
    opener(_Serving())
    _wait_public(["https://site/social/01_card.png"], tries=3, delay=0,
                 sleep=lambda s: None)      # 예외가 없으면 통과


def test_the_checker_reads_the_status_not_the_body(opener):
    """부품 검사 — url_ok는 바이너리에도 True를 줘야 한다."""
    opener(_Serving())
    assert H.url_ok("https://site/x.png") is True


# ── 대조군: 없는 이미지는 여전히 막아야 한다 ──────────────────


@pytest.mark.parametrize("server,label", [(_NotFound, "404"), (_Down, "네트워크 끊김")])
def test_a_missing_image_still_blocks_the_post(opener, server, label):
    opener(server())
    with pytest.raises(RuntimeError, match="공개되지 않음"):
        _wait_public(["https://site/social/01_card.png"], tries=2, delay=0,
                     sleep=lambda s: None)


@pytest.mark.parametrize("server,label", [(_NotFound, "404"), (_Down, "네트워크 끊김")])
def test_url_ok_is_false_when_the_image_is_not_there(opener, server, label):
    opener(server())
    assert H.url_ok("https://site/x.png") is False, label


@pytest.mark.parametrize("status", [304, 403, 500])
def test_a_non_2xx_response_is_not_treated_as_published(opener, status):
    """응답 객체가 예외 없이 돌아오는 경우도 있다 — 그때는 상태코드로 판단한다.

    ⚠️ 처음엔 이 검사를 '예외를 던지는 서버'로 썼다가 변이를 놓쳤다.
       urllib은 4xx·5xx에 HTTPError를 **던지므로**, 예외를 던지는 가짜로는
       상태코드 검사 줄이 한 번도 안 돈다. 프록시·커스텀 핸들러·304처럼
       **예외 없이 응답이 돌아오는 경로**로 자극해야 그 줄이 실행된다.
    """
    opener(_Serving(body=b"nope", status=status))
    assert H.url_ok("https://site/x.png") is False, status


def test_a_2xx_response_is_treated_as_published(opener):
    """대조군 — 정상 응답까지 막으면 게시가 영영 안 나간다."""
    for status in (200, 201, 299):
        opener(_Serving(status=status))
        assert H.url_ok("https://site/x.png") is True, status


# ── 주입 계약: 기존 검사들이 쓰던 방식이 계속 통해야 한다 ─────


def test_an_injected_fetcher_that_returns_nothing_still_counts_as_success():
    """기존 계약 — 주입된 fetch는 '성공하면 반환, 실패하면 예외'다.

    `url_ok`는 False를 돌려주므로 두 방식을 다 받아야 한다. 반환값이 None인
    가짜를 '실패'로 읽으면 기존 검사들이 통째로 깨진다.
    """
    seen: list[str] = []
    _wait_public(["https://site/a.png"], tries=1, delay=0,
                 http_get=lambda u: seen.append(u), sleep=lambda s: None)
    assert seen == ["https://site/a.png"]


def test_an_injected_fetcher_returning_false_means_not_ready():
    with pytest.raises(RuntimeError, match="공개되지 않음"):
        _wait_public(["https://site/a.png"], tries=2, delay=0,
                     http_get=lambda u: False, sleep=lambda s: None)


def test_every_image_is_checked_not_just_the_first(opener):
    """카드는 8장이다 — 한 장만 보고 넘어가면 나머지가 404여도 게시한다."""
    seen: list[str] = []
    _wait_public([f"https://site/{i}.png" for i in range(8)], tries=1, delay=0,
                 http_get=lambda u: seen.append(u) or True, sleep=lambda s: None)
    assert len(seen) == 8, seen


# ── 배선: 실전 경로가 이 단계를 켜는가 ────────────────────────


def test_the_real_run_turns_this_check_on():
    """기존 검사 8건이 전부 wait_public=False로 이 단계를 꺼 놓고 돈다.

    실전 기본값이 True라는 사실을 못 박아 둔다 — 여기가 False로 바뀌면
    404인 이미지를 Meta에 넘기게 된다.
    """
    import inspect

    from quant.reporting.social_post import run

    default = inspect.signature(run).parameters["wait_public"].default
    assert default is True, "실전 경로에서 이미지 공개 확인이 꺼져 있다"
