"""SNS 자동 게시 계약 검사 — 캡션 정직성·스레드 글자 제한·API 호출 순서·멱등.

핵심 계약:
  ① 캡션은 장부 숫자를 그대로 쓰고, 모의투자 고지·사이트 링크가 항상 포함된다
  ② 스레드 캡션은 500자 제한을 절대 넘지 않는다
  ③ 캐러셀 게시는 아이템 컨테이너 → 캐러셀 → publish 순서를 지킨다
  ④ 자격증명이 없으면 게시를 조용히 건너뛴다(콘텐츠 생성은 항상 동작)
  ⑤ posted.json 마커가 있으면 재실행해도 중복 게시하지 않는다(멱등)
  ⑥ 한 플랫폼의 실패가 다른 플랫폼 게시를 막지 않는다
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.reporting.social import (  # noqa: E402
    CAPTURE_PLAN,
    THREADS_TEXT_LIMIT,
    build_captions,
    prune_old,
    write_content,
)
from quant.reporting.social_post import run  # noqa: E402

STATUS = {
    "updated": "2026-08-05T21:48:00Z",
    "paper": {"portfolio:ALL": {"history": [
        {"date": "2026-08-05", "equity": 79512.3, "return_pct": -0.61,
         "twr_pct": -0.61, "weight": 0.31, "risk_scale": 1.0,
         "alloc": {"crypto:BTC/USDT": 0.08, "us_stock_NVDA": 0.0,
                   "kr_stock:005930.KS": 0.05},
         "champion": {"symbols": 20}},
    ]},
        # 종목 장부 — 캡션은 "그날 실제로 든 종목"만 말한다(감사 91). 예산만
        # 보고 이름을 부르면 관망한 종목까지 방송된다.
        "crypto:BTC/USDT": {"history": [{"date": "2026-08-05",
                                         "weight": 0.19}]},
        "kr_stock:005930.KS": {"history": [{"date": "2026-08-05",
                                            "weight": 0.12}]},
    },
    "retrain_recent": [
        {"asof": "2026-08-05", "promoted": True},
        {"asof": "2026-08-05", "promoted": False},
        {"asof": "2026-08-04", "promoted": False},
    ],
    "symbols": {"crypto:BTC/USDT": {"name": "비트코인", "why": "-"},
                "kr_stock:005930.KS": {"name": "삼성전자", "why": "-"}},
}


# ── ① 캡션 정직성 ───────────────────────────────────────────────


def test_captions_honest_and_complete():
    caps = build_captions(STATUS, site_url="https://example.com")
    for text in (caps["instagram"], caps["threads"]):
        assert "모의투자" in text                    # 고지 필수
        assert "https://example.com" in text          # 사이트 링크 필수
        assert "-0.61%" in text                       # 마이너스도 그대로
        assert "보장" in text                         # '보장 없음' 계열 문구
    assert caps["date"] == "2026-08-05"
    assert "비트코인" in caps["instagram"]            # 배분 상위 하이라이트
    # 그날 재학습만 집계(2개 중 1개 교체) — 서사 문장에 반영된다
    assert "2개 종목을 재학습" in caps["instagram"]
    assert "1개 종목의 전략이 교체" in caps["instagram"]


def test_caption_kill_switch_disclosed():
    """킬스위치 발동 중이면 캡션에 숨기지 않고 표시한다."""
    st = json.loads(json.dumps(STATUS))
    st["paper"]["portfolio:ALL"]["history"][-1]["risk_scale"] = 0.5
    caps = build_captions(st)
    assert "킬스위치" in caps["instagram"]


# ── ② 스레드 글자 제한 ─────────────────────────────────────────


def test_threads_caption_within_limit_even_with_long_data():
    st = json.loads(json.dumps(STATUS))
    st["symbols"] = {f"m:S{i}": {"name": "아주아주아주아주긴종목이름" * 3,
                                 "why": "-"} for i in range(30)}
    st["paper"]["portfolio:ALL"]["history"][-1]["alloc"] = {
        f"m:S{i}": 0.01 for i in range(30)}
    caps = build_captions(st)
    assert len(caps["threads"]) <= THREADS_TEXT_LIMIT
    assert "모의투자" in caps["threads"]              # 줄여도 고지는 남는다


# ── 콘텐츠 파일 생성 + 보관 정리 ────────────────────────────────


def test_write_content_and_prune(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.json").write_text(
        json.dumps(STATUS, ensure_ascii=False), encoding="utf-8")
    meta = write_content(docs_dir=str(docs), site_url="https://example.com")
    d = Path(meta["dir"])
    assert d.name == "2026-08-05"
    assert (d / "caption_instagram.txt").exists()
    assert (d / "caption_threads.txt").exists()
    assert json.loads((d / "meta.json").read_text(encoding="utf-8"))[
        "images"] == [f for f, _ in CAPTURE_PLAN]
    # 보관 정리: keep=2로 오래된 폴더가 지워진다
    for day in ("2026-08-01", "2026-08-02", "2026-08-03"):
        (docs / "social" / day).mkdir()
    removed = prune_old(docs_dir=str(docs), keep=2)
    assert "2026-08-01" in removed and "2026-08-02" in removed
    assert (docs / "social" / "2026-08-05").exists()


# ── ③④⑤⑥ 게시 흐름 (가짜 HTTP로 호출 순서 검증) ───────────────


def _content_dir(tmp_path, with_images=True) -> str:
    d = tmp_path / "docs" / "social" / "2026-08-05"
    d.mkdir(parents=True)
    (d / "caption_instagram.txt").write_text("ig 캡션", encoding="utf-8")
    (d / "caption_threads.txt").write_text("th 캡션", encoding="utf-8")
    (d / "meta.json").write_text(json.dumps(
        {"date": "2026-08-05", "images": [f for f, _ in CAPTURE_PLAN],
         "pages": {}}), encoding="utf-8")
    if with_images:
        for f, _ in CAPTURE_PLAN:
            (d / f).write_bytes(b"png")
    return str(d)


class _FakeHTTP:
    """호출을 기록하고 컨테이너 ID를 차례로 발급하는 가짜 Meta API."""

    def __init__(self):
        self.posts: list[tuple[str, str]] = []      # (url, body)
        self.n = 0

    def post(self, url, headers=None, body=None):
        self.posts.append((url, body or ""))
        self.n += 1
        return {"id": f"C{self.n}"}

    def get(self, url, headers=None):
        return {"status_code": "FINISHED"}


def test_run_skips_without_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _content_dir(tmp_path)
    fake = _FakeHTTP()
    out = run(d, "https://example.com", env={}, http=fake.post,
              http_get=fake.get, sleep=lambda s: None, wait_public=False)
    assert out["skipped"] == "no_credentials"
    assert not fake.posts                            # 네트워크 호출 0회
    assert not os.path.exists(os.path.join(d, "posted.json"))


def test_run_posts_carousel_in_order_and_marks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _content_dir(tmp_path)
    fake = _FakeHTTP()
    env = {"THREADS_USER_ID": "u1", "THREADS_ACCESS_TOKEN": "tok1",
           "IG_USER_ID": "u2", "IG_ACCESS_TOKEN": "tok2"}
    out = run(d, "https://example.com", env=env, http=fake.post,
              http_get=fake.get, sleep=lambda s: None, wait_public=False)
    assert "threads" in out and "instagram" in out
    urls = [u for u, _ in fake.posts]
    # 플랫폼당 호출 수 = 아이템 N + 캐러셀 1 + publish 1 (N=카드 수)
    n_items = len(CAPTURE_PLAN)
    th = [u for u in urls if "graph.threads.net" in u]
    ig = [u for u in urls if "graph.facebook.com" in u]
    assert len(th) == n_items + 2 and th[-1].endswith("/threads_publish")
    assert len(ig) == n_items + 2 and ig[-1].endswith("/media_publish")
    # 캐러셀 본문에 children 3개가 담긴다
    car_bodies = [b for u, b in fake.posts if "CAROUSEL" in b]
    assert len(car_bodies) == 2
    assert all(b.count("C") >= 3 for b in car_bodies)
    # 토큰은 URL이 아니라 본문/헤더에만 있다(로그 유출 방지)
    assert all("tok1" not in u and "tok2" not in u for u in urls)
    # 멱등 마커
    assert os.path.exists(os.path.join(d, "posted.json"))
    # ⑤ 재실행 → 중복 게시 없음
    n_before = len(fake.posts)
    out2 = run(d, "https://example.com", env=env, http=fake.post,
               http_get=fake.get, sleep=lambda s: None, wait_public=False)
    assert out2["skipped"] == "already_posted"
    assert len(fake.posts) == n_before


def test_run_one_platform_failure_does_not_block_other(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _content_dir(tmp_path)

    calls = {"n": 0}

    def flaky_post(url, headers=None, body=None):
        calls["n"] += 1
        if "graph.threads.net" in url:
            raise RuntimeError("HTTP 400 토큰 만료")
        return {"id": f"C{calls['n']}"}

    fake = _FakeHTTP()
    env = {"THREADS_USER_ID": "u1", "THREADS_ACCESS_TOKEN": "tok1",
           "IG_USER_ID": "u2", "IG_ACCESS_TOKEN": "tok2"}
    out = run(d, "https://example.com", env=env, http=flaky_post,
              http_get=fake.get, sleep=lambda s: None, wait_public=False)
    assert "threads_error" in out                    # 스레드는 실패 기록
    assert out.get("instagram")                      # 인스타는 성공
    assert os.path.exists(os.path.join(d, "posted.json"))
    # 마커에는 성공한 플랫폼만 적힌다 — 실패한 스레드는 재시도 대상으로 남는다
    assert out["posted_platforms"] == ["instagram"]


def test_retry_reposts_only_the_failed_platform(tmp_path, monkeypatch):
    """부분 실패한 날의 재시도가 실패한 쪽만 다시 올린다 (감사 54).

    예전에는 '한 곳이라도 성공하면' posted.json을 남기고, 마커가 있으면
    폴더를 통째로 건너뛰었다. 스레드는 성공하고 인스타가 실패한 날,
    재시도 크론이 폴더를 건너뛰므로 **인스타는 그날 영원히 안 올라간다.**
    게시 실패가 '이미 게시됨'으로 둔갑하는 자리였다.
    """
    monkeypatch.chdir(tmp_path)
    d = _content_dir(tmp_path)
    env = {"THREADS_USER_ID": "u1", "THREADS_ACCESS_TOKEN": "tok1",
           "IG_USER_ID": "u2", "IG_ACCESS_TOKEN": "tok2"}

    n = {"i": 0}
    broken_ig = {"on": True}

    def post(url, headers=None, body=None):
        n["i"] += 1
        if broken_ig["on"] and "graph.facebook.com" in url:
            raise RuntimeError("HTTP 400 인스타 토큰 만료")
        return {"id": f"C{n['i']}"}

    fake = _FakeHTTP()
    kw = dict(http=post, http_get=fake.get, sleep=lambda s: None,
              wait_public=False)
    out1 = run(d, "https://example.com", env=env, **kw)
    assert out1["posted_platforms"] == ["threads"]
    assert "instagram_error" in out1

    # 토큰을 고친 뒤 재시도 — 인스타만 올라가고 스레드는 다시 안 올린다
    broken_ig["on"] = False
    calls_before = n["i"]
    out2 = run(d, "https://example.com", env=env, **kw)
    assert out2.get("instagram") and "instagram_error" not in out2
    assert out2["threads"] == "skipped(이미 게시됨)"
    assert out2["posted_platforms"] == ["instagram", "threads"]
    # 새 호출은 전부 인스타 쪽이어야 한다(스레드 중복 게시 없음)
    assert n["i"] > calls_before

    # 3회차 — 둘 다 끝났으니 아무것도 안 한다
    calls_before = n["i"]
    out3 = run(d, "https://example.com", env=env, **kw)
    assert out3["skipped"] == "already_posted"
    assert n["i"] == calls_before


def test_legacy_marker_without_platforms_is_treated_as_fully_posted(
        tmp_path, monkeypatch):
    """플랫폼 기록이 없는 옛 마커는 '전부 게시됨'으로 본다(중복 게시 금지)."""
    monkeypatch.chdir(tmp_path)
    d = _content_dir(tmp_path)
    with open(os.path.join(d, "posted.json"), "w", encoding="utf-8") as f:
        json.dump({"threads": "T1", "instagram": "I1"}, f)
    fake = _FakeHTTP()
    out = run(d, "https://example.com",
              env={"THREADS_USER_ID": "u1", "THREADS_ACCESS_TOKEN": "t",
                   "IG_USER_ID": "u2", "IG_ACCESS_TOKEN": "t"},
              http=fake.post, http_get=fake.get, sleep=lambda s: None,
              wait_public=False)
    assert out["skipped"] == "already_posted"
    assert not fake.posts


def test_run_no_images_skips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _content_dir(tmp_path, with_images=False)
    out = run(d, "https://example.com",
              env={"THREADS_USER_ID": "u", "THREADS_ACCESS_TOKEN": "t"},
              wait_public=False)
    assert out["skipped"] == "no_images"


def test_capture_plan_is_instagram_cardnews():
    """캡처 계획이 사이트 캡처가 아니라 4:5 카드뉴스 전용 템플릿이다."""
    from quant.reporting.social import CARD_SIZE
    assert CARD_SIZE == (1080, 1350)                 # 인스타 4:5
    assert all(p.startswith("sns_card.html?n=") for _, p in CAPTURE_PLAN)
    yml = (Path(__file__).resolve().parent.parent / ".github" / "workflows"
           / "social-post.yml").read_text(encoding="utf-8")
    assert "--window-size=1080,1350" in yml and "sns_card.html?n=${i}" in yml
    assert len(CAPTURE_PLAN) == 8                    # 8장 스토리
    card = (Path(__file__).resolve().parent.parent / "docs"
            / "sns_card.html").read_text(encoding="utf-8")
    assert "1080px" in card and "1350px" in card
    assert "모의투자" in card                         # 카드에도 고지 필수
