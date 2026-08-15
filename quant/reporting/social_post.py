"""SNS 자동 게시 — Threads·Instagram Graph API로 캐러셀(사진 여러 장)을 올린다.

두 플랫폼 모두 Meta의 컨테이너 방식이다:
    ① 이미지마다 아이템 컨테이너 생성(공개 URL 필수 — 우리 사이트가 호스팅)
    ② 캐러셀 컨테이너 생성(children=아이템들, 캡션/텍스트 포함)
    ③ 컨테이너 처리 완료(FINISHED) 확인 후 publish

필요 환경변수(사장님이 GitHub Secrets로 등록해야 실게시가 켜진다):
    THREADS_USER_ID · THREADS_ACCESS_TOKEN     — 스레드
    IG_USER_ID · IG_ACCESS_TOKEN               — 인스타그램(비즈니스/크리에이터 계정)
미설정 플랫폼은 조용히 건너뛴다(콘텐츠 생성까지는 항상 동작) — 자동화가
자격증명 없이도 죽지 않게 하기 위한 명시적 규칙이다.

⚠️ 토큰은 절대 URL 쿼리에 넣지 않고 요청 본문으로 보낸다(로그 유출 방지).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse

from quant.utils.http import get_json, post_json
from quant.utils.logging import get_logger

log = get_logger("social")

THREADS_API = "https://graph.threads.net/v1.0"
IG_API = "https://graph.facebook.com/v21.0"
_FORM = {"Content-Type": "application/x-www-form-urlencoded"}

# 컨테이너 처리 대기 — Meta가 이미지를 받아 검증하는 시간(보통 수 초).
POLL_TRIES = 12
POLL_DELAY = 5


def _safe_error(exc: Exception, limit: int = 300) -> str:
    """게시 실패 사유 — **공개돼도 되는 형태로만** 남긴다 (감사 248).

    ⚠️ 이 문자열은 로그로만 가지 않는다. 아래 `run()`이 결과를
       `posted.json`에 쓰는데 그 파일은 `docs/` 안이라 **공개 사이트에
       그대로 배포된다.** 그리고 이 모듈은 Meta API에 토큰을 **본문(form)**
       으로 보내므로, 오류 응답이 요청을 되울리면 토큰이 그 사유 안에 들어온다.

       가리개 한 겹(감사 170·248)에만 기대지 않는다 — 공개되는 파일에 원문
       예외를 통째로 붓는 것 자체가 위험한 습관이다. 가리고, 자른다.
    """
    from quant.utils.http import redact_secrets

    return redact_secrets(str(exc))[:limit]


def _post(url: str, params: dict, *, http=post_json) -> dict:
    """토큰 포함 파라미터를 본문(form)으로 보내는 POST — URL에 토큰 노출 금지."""
    body = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None})
    return http(url, headers=_FORM, body=body)


def _wait_finished(container_id: str, token: str, api: str, *,
                   http_get=get_json, sleep=time.sleep) -> None:
    """컨테이너가 FINISHED가 될 때까지 대기. ERROR/시간초과면 예외.

    GET은 본문이 없으므로 토큰을 Authorization 헤더로 보낸다(URL 노출 금지).
    """
    url = f"{api}/{container_id}?fields=status_code"
    hdr = {"Authorization": f"Bearer {token}"}
    for _ in range(POLL_TRIES):
        st = str(http_get(url, headers=hdr).get("status_code", ""))
        if st == "FINISHED":
            return
        if st == "ERROR":
            raise RuntimeError(f"컨테이너 처리 실패: {container_id}")
        sleep(POLL_DELAY)
    raise RuntimeError(f"컨테이너 처리 시간 초과: {container_id}")


def _wait_public(urls: list[str], *, tries: int = 30, delay: int = 10,
                 http_get=None, sleep=time.sleep) -> None:
    """이미지 URL들이 공개적으로 200을 줄 때까지 대기(배포 전파 대기).

    커밋 → Cloudflare 배포까지 1~2분 걸린다. Meta API는 URL을 즉시 받아가므로
    404인 채로 게시를 시작하면 컨테이너가 ERROR가 된다.

    ⚠️ 예전에는 `get_text`로 확인했다(감사 172). 그런데 여기 오는 URL은
       **PNG 카드**다. `get_text`는 본문을 UTF-8로 디코드하므로 PNG를 받는
       순간 `UnicodeDecodeError`가 나고, 그건 `RuntimeError`가 아니라
       `ValueError`라 아래 `except`를 그대로 빠져나간다 — **이미지가 정상
       공개된 순간 게시가 통째로 죽었다.** 성공 경로가 곧 실패 경로였다.

       아무도 못 잡은 이유가 분명하다: 이 함수를 부르는 검사가 하나도 없다.
       기존 SNS 검사 8건이 **전부 `wait_public=False`** 로 이 단계를 꺼 놓고
       돌았다(FROZEN_IDEAS ㉜ — 아무도 안 보는 경로).

       이제 본문을 해석하지 않는 `url_ok`로 확인한다.
    """
    from quant.utils.http import url_ok
    fetch = http_get or (lambda u: url_ok(u, timeout=20))
    for u in urls:
        ok = False
        for _ in range(tries):
            try:
                # 주입된 fetch는 '성공하면 아무거나 반환, 실패하면 예외'라는
                # 기존 계약을 쓴다. url_ok는 False를 돌려주므로 둘 다 받는다.
                if fetch(u) is not False:
                    ok = True
                    break
            except Exception:  # noqa: BLE001 — 어떤 실패든 재시도 대상이다
                pass
            sleep(delay)
        if not ok:
            raise RuntimeError(f"이미지가 공개되지 않음(배포 지연/실패?): {u}")


def post_threads(image_urls: list[str], text: str, *, user_id: str,
                 token: str, http=post_json, http_get=get_json,
                 sleep=time.sleep) -> str:
    """스레드에 이미지 게시(1장=단일, 여러 장=캐러셀). 반환: 게시물 ID."""
    if len(image_urls) == 1:
        item = _post(f"{THREADS_API}/{user_id}/threads",
                     {"media_type": "IMAGE", "image_url": image_urls[0],
                      "text": text, "access_token": token}, http=http)
        creation_id = item["id"]
    else:
        children = []
        for u in image_urls:
            item = _post(f"{THREADS_API}/{user_id}/threads",
                         {"media_type": "IMAGE", "image_url": u,
                          "is_carousel_item": "true",
                          "access_token": token}, http=http)
            children.append(item["id"])
        for cid in children:
            _wait_finished(cid, token, THREADS_API, http_get=http_get,
                           sleep=sleep)
        carousel = _post(f"{THREADS_API}/{user_id}/threads",
                         {"media_type": "CAROUSEL",
                          "children": ",".join(children), "text": text,
                          "access_token": token}, http=http)
        creation_id = carousel["id"]
    _wait_finished(creation_id, token, THREADS_API, http_get=http_get,
                   sleep=sleep)
    pub = _post(f"{THREADS_API}/{user_id}/threads_publish",
                {"creation_id": creation_id, "access_token": token}, http=http)
    return str(pub.get("id", creation_id))


def post_instagram(image_urls: list[str], caption: str, *, user_id: str,
                   token: str, http=post_json, http_get=get_json,
                   sleep=time.sleep) -> str:
    """인스타그램에 캐러셀(또는 단일) 게시. 반환: 게시물 ID.

    비즈니스/크리에이터 계정 + 페이스북 페이지 연결이 선행돼야 한다.
    """
    if len(image_urls) == 1:
        item = _post(f"{IG_API}/{user_id}/media",
                     {"image_url": image_urls[0], "caption": caption,
                      "access_token": token}, http=http)
        creation_id = item["id"]
    else:
        children = []
        for u in image_urls:
            item = _post(f"{IG_API}/{user_id}/media",
                         {"image_url": u, "is_carousel_item": "true",
                          "access_token": token}, http=http)
            children.append(item["id"])
        for cid in children:
            _wait_finished(cid, token, IG_API, http_get=http_get, sleep=sleep)
        carousel = _post(f"{IG_API}/{user_id}/media",
                         {"media_type": "CAROUSEL",
                          "children": ",".join(children), "caption": caption,
                          "access_token": token}, http=http)
        creation_id = carousel["id"]
    _wait_finished(creation_id, token, IG_API, http_get=http_get, sleep=sleep)
    pub = _post(f"{IG_API}/{user_id}/media_publish",
                {"creation_id": creation_id, "access_token": token}, http=http)
    return str(pub.get("id", creation_id))


def run(content_dir: str, base_url: str, *, env=os.environ,
        http=post_json, http_get=get_json, sleep=time.sleep,
        wait_public: bool = True) -> dict:
    """콘텐츠 폴더를 읽어 설정된 플랫폼에 게시한다. 반환: 플랫폼별 결과.

    멱등: 같은 폴더에 posted.json이 있으면 **그 안에 성공으로 적힌 플랫폼만**
    건너뛴다. 재시도 크론이 같은 날 두 번 올리는 사고를 막으면서, 실패한
    쪽은 다시 시도하게 하기 위함이다.

    ⚠️ 예전에는 '한 곳이라도 성공하면' 마커를 남기고, 마커가 있으면 폴더를
       통째로 건너뛰었다(감사 54). 스레드는 성공하고 인스타는 실패한 날,
       마커가 남아 재시도가 폴더를 건너뛰므로 **인스타는 그날 영원히 안
       올라간다** — 게시 실패가 '이미 게시됨'으로 둔갑하는 자리였다.
    """
    # 어드민 대시보드 스위치 — 꺼져 있으면 게시하지 않는다(콘텐츠는 이미 생성됨)
    from quant.utils.settings import load_settings
    if not load_settings().get("social_post", True):
        log.info("어드민 설정으로 SNS 게시 꺼짐 — 건너뜀")
        return {"skipped": "disabled_by_admin"}

    marker = os.path.join(content_dir, "posted.json")
    done: set[str] = set()
    if os.path.exists(marker):
        try:
            with open(marker, encoding="utf-8") as f:
                prev = json.load(f)
        except (OSError, ValueError):
            prev = {}
        plats = prev.get("posted_platforms")
        if plats is None:
            # 옛 마커(플랫폼 기록 없음) = 예전 동작 그대로 전부 게시된 것으로 본다.
            # 모르는 상태에서 다시 올리면 중복 게시가 되고, 그건 되돌릴 수 없다.
            done = {"threads", "instagram"}
        else:
            done = {str(p) for p in plats}
        log.info("이미 게시된 플랫폼 — 건너뜀: %s", sorted(done) or "(없음)")

    with open(os.path.join(content_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    images = [f for f in meta["images"]
              if os.path.exists(os.path.join(content_dir, f))]
    if not images:
        return {"skipped": "no_images"}
    rel = os.path.relpath(content_dir, "docs").replace(os.sep, "/")
    urls = [f"{base_url.rstrip('/')}/{rel}/{f}" for f in images]

    def _read(name: str) -> str:
        with open(os.path.join(content_dir, name), encoding="utf-8") as f:
            return f.read()

    results: dict = {"images": urls}
    th_id, th_tok = env.get("THREADS_USER_ID"), env.get("THREADS_ACCESS_TOKEN")
    ig_id, ig_tok = env.get("IG_USER_ID"), env.get("IG_ACCESS_TOKEN")
    if not (th_id and th_tok) and not (ig_id and ig_tok):
        log.info("SNS 자격증명 미설정 — 게시 건너뜀(콘텐츠 생성은 완료됨)")
        return {**results, "skipped": "no_credentials"}

    todo = [p for p in ("threads", "instagram") if p not in done
            and (th_id and th_tok if p == "threads" else ig_id and ig_tok)]
    if not todo:
        return {**results, "skipped": "already_posted"}

    if wait_public:
        _wait_public(urls, sleep=sleep)

    posted = set(done)
    if "threads" in todo:
        try:
            results["threads"] = post_threads(
                urls, _read("caption_threads.txt"), user_id=th_id,
                token=th_tok, http=http, http_get=http_get, sleep=sleep)
            posted.add("threads")
            log.info("스레드 게시 완료: %s", results["threads"])
        except Exception as exc:  # noqa: BLE001 — 한 플랫폼 실패가 다른 쪽을 안 막는다
            results["threads_error"] = _safe_error(exc)
            log.error("스레드 게시 실패: %s", _safe_error(exc))
    elif "threads" in done:
        results["threads"] = "skipped(이미 게시됨)"
    else:
        results["threads"] = "skipped(미설정)"

    if "instagram" in todo:
        try:
            results["instagram"] = post_instagram(
                urls, _read("caption_instagram.txt"), user_id=ig_id,
                token=ig_tok, http=http, http_get=http_get, sleep=sleep)
            posted.add("instagram")
            log.info("인스타그램 게시 완료: %s", results["instagram"])
        except Exception as exc:  # noqa: BLE001
            results["instagram_error"] = _safe_error(exc)
            log.error("인스타그램 게시 실패: %s", _safe_error(exc))
    elif "instagram" in done:
        results["instagram"] = "skipped(이미 게시됨)"
    else:
        results["instagram"] = "skipped(미설정)"

    # 멱등 마커 — **성공한 플랫폼만** 적는다. 실패한 쪽은 적히지 않으므로
    # 다음 재시도가 그 플랫폼만 다시 올린다(중복 없이, 누락도 없이).
    results["posted_platforms"] = sorted(posted)
    if posted:
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(marker, results)
    return results
