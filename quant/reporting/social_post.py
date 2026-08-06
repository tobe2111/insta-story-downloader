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
    """
    from quant.utils.http import get_text
    fetch = http_get or (lambda u: get_text(u, timeout=20))
    for u in urls:
        ok = False
        for _ in range(tries):
            try:
                fetch(u)
                ok = True
                break
            except RuntimeError:
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

    멱등: 같은 폴더에 posted.json이 있으면(이미 게시됨) 통째로 건너뛴다 —
    재시도 크론이 같은 날 두 번 올리는 사고를 막는다. 플랫폼 하나의 실패가
    다른 플랫폼 게시를 막지 않는다(독립 시도, 실패는 결과에 기록).
    """
    marker = os.path.join(content_dir, "posted.json")
    if os.path.exists(marker):
        log.info("이미 게시된 폴더 — 건너뜀: %s", content_dir)
        return {"skipped": "already_posted"}

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

    if wait_public:
        _wait_public(urls, sleep=sleep)

    if th_id and th_tok:
        try:
            results["threads"] = post_threads(
                urls, _read("caption_threads.txt"), user_id=th_id,
                token=th_tok, http=http, http_get=http_get, sleep=sleep)
            log.info("스레드 게시 완료: %s", results["threads"])
        except Exception as exc:  # noqa: BLE001 — 한 플랫폼 실패가 다른 쪽을 안 막는다
            results["threads_error"] = str(exc)
            log.error("스레드 게시 실패: %s", exc)
    else:
        results["threads"] = "skipped(미설정)"

    if ig_id and ig_tok:
        try:
            results["instagram"] = post_instagram(
                urls, _read("caption_instagram.txt"), user_id=ig_id,
                token=ig_tok, http=http, http_get=http_get, sleep=sleep)
            log.info("인스타그램 게시 완료: %s", results["instagram"])
        except Exception as exc:  # noqa: BLE001
            results["instagram_error"] = str(exc)
            log.error("인스타그램 게시 실패: %s", exc)
    else:
        results["instagram"] = "skipped(미설정)"

    # 성공한 게시가 하나라도 있으면 멱등 마커를 남긴다(재실행 중복 방지).
    if any(k in results and "skipped" not in str(results[k])
           for k in ("threads", "instagram")):
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(marker, results)
    return results
