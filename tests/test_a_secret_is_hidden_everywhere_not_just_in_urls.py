"""비밀 가리개가 '?'나 '&' 뒤에서만 작동했다 (감사 248).

오류 메시지에서 키를 가리는 규칙이 이랬습니다:

    r"([?&](?:api_key|apikey|access_token|token|…)=)[^&#\\s]*"

**앞에 `?`나 `&`가 있어야만** 가립니다. 그런데 이 저장소는 Meta API에
토큰을 **본문(form)**으로 보냅니다(`_post` — "URL에 토큰 노출 금지").
오류 응답이 그 본문을 되울리면 토큰은 문자열 맨 앞이나 따옴표 뒤에 오고,
그때는 가리개가 **한 글자도 지우지 않았습니다.**

실측(가리개를 통과시킨 문자열):

    {"error":{"message":"Invalid: access_token=EAAG…"}}   ← 그대로 노출
    access_token=EAAG…&media_type=IMAGE                   ← 그대로 노출

    (반면 ?access_token=… 은 정상적으로 가려졌습니다)

그리고 이 문자열은 **로그로만 가지 않습니다.** SNS 게시 결과는
`posted.json`에 쓰이는데, 그 경로는 `docs/social/<날짜>/` — 저장소에
커밋되고 **공개 사이트에 배포되는 폴더**입니다. 실제로 그 폴더의 파일들이
git에 들어 있습니다.

즉 로그 유출이 아니라 **공개 게시**입니다.

두 겹으로 막습니다:
  ① 가리개가 줄 시작·공백·따옴표·괄호 뒤에서도 작동한다(감사 170의 연장 —
     "가릴 거면 모든 통로를 가려야 한다").
  ② 공개되는 파일에는 원문 예외를 붓지 않는다. 가리고, 자른다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting.social_post import _safe_error  # noqa: E402
from quant.utils.http import redact_secrets  # noqa: E402

SECRET = "EAAGsuperSecretTokenValue123"


# ── 가리개: 어디에 있어도 가리는가 ────────────────────────────

@pytest.mark.parametrize("text", [
    f'{{"error":{{"message":"Invalid: access_token={SECRET}"}}}}',   # 따옴표 뒤
    f"access_token={SECRET}&media_type=IMAGE",                       # 줄 맨 앞
    f"HTTP 400 x: access_token={SECRET}",                            # 공백 뒤
    f"HTTP 400 https://x?access_token={SECRET}",                     # 예전에도 되던 것
    f"body=[access_token={SECRET}]",                                 # 대괄호 뒤
    f"params={{token={SECRET}}}",                                    # 중괄호 뒤
    f"a=1,api_key={SECRET}",                                         # 쉼표 뒤
    f"APIKEY={SECRET}",                                              # 대문자
])
def test_the_secret_is_hidden_wherever_it_sits(text):
    out = redact_secrets(text)
    assert SECRET not in out, f"가리개를 통과했다: {out}"
    assert "***" in out


def test_it_does_not_eat_the_rest_of_the_json():
    """값만 가린다 — 뒤 문장까지 별표로 덮으면 원인을 못 읽는다."""
    out = redact_secrets(
        f'{{"error":{{"message":"Invalid: access_token={SECRET}",'
        f'"code":190,"type":"OAuthException"}}}}')
    assert "OAuthException" in out and '"code":190' in out, out


def test_an_innocent_message_is_untouched():
    """대조군 — 비밀이 없으면 아무것도 안 바꾼다."""
    msg = "네트워크 오류 https://graph.threads.net/v1: timed out"
    assert redact_secrets(msg) == msg


def test_a_word_that_merely_contains_token_is_not_a_false_positive():
    """대조군 — 'broken=1' 같은 값을 통째로 지우면 원인이 사라진다."""
    assert redact_secrets("broken=1&retry=2") == "broken=1&retry=2"


# ── 공개되는 파일에 무엇을 쓰는가 ─────────────────────────────

def test_the_publish_error_is_redacted_before_it_is_stored():
    got = _safe_error(RuntimeError(
        f'HTTP 400: {{"error":"bad","body":"access_token={SECRET}"}}'))
    assert SECRET not in got, got


def test_the_publish_error_is_truncated():
    """공개 파일에 예외 원문을 통째로 붓지 않는다."""
    got = _safe_error(RuntimeError("가" * 5000))
    assert len(got) <= 300


def test_the_reason_still_says_something_useful():
    """가리는 것과 지우는 것은 다르다 — 원인은 남아야 한다."""
    got = _safe_error(RuntimeError("HTTP 429 rate limited"))
    assert "429" in got and "rate limited" in got


def test_the_marker_file_never_carries_a_raw_exception(tmp_path, monkeypatch):
    """실제로 `posted.json`을 만들어 본다 — 그 파일이 공개된다."""
    import quant.reporting.social_post as sp
    import quant.utils.settings as us

    content = tmp_path / "docs" / "social" / "2026-08-15"
    content.mkdir(parents=True)
    (content / "01_card.png").write_bytes(b"\x89PNG")
    (content / "meta.json").write_text(json.dumps({"images": ["01_card.png"]}),
                                       "utf-8")
    (content / "caption_threads.txt").write_text("본문", "utf-8")
    (content / "caption_instagram.txt").write_text("본문", "utf-8")

    monkeypatch.setattr(us, "load_settings",
                        lambda path=us.SETTINGS_PATH: {
                            "trading_paused": False, "exposure_scale": 1.0,
                            "social_post": True, "note": "",
                            "portfolio_target_vol": None})

    def _boom(*a, **k):
        raise RuntimeError(
            f'HTTP 400: {{"error":"bad","body":"access_token={SECRET}"}}')

    monkeypatch.setattr(sp, "post_threads", _boom)
    monkeypatch.setattr(sp, "post_instagram", lambda *a, **k: "ig_1")
    monkeypatch.chdir(tmp_path)

    out = sp.run(str(content), "https://example.test",
                 env={"THREADS_USER_ID": "t", "THREADS_ACCESS_TOKEN": SECRET,
                      "IG_USER_ID": "i", "IG_ACCESS_TOKEN": SECRET},
                 wait_public=False)
    assert "threads_error" in out, f"이 검사의 전제가 깨졌다: {out}"
    marker = content / "posted.json"
    assert marker.exists(), "마커가 안 써졌다 — 이 검사가 헛돈다"
    body = marker.read_text("utf-8")
    assert SECRET not in body, (
        f"공개되는 파일에 토큰이 그대로 있다:\n{body[:400]}")


def test_the_marker_lives_in_a_published_folder():
    """이 감사의 전제 — 그 파일이 정말 공개되는 곳에 있는가."""
    src = (ROOT / "quant" / "reporting" / "social_post.py").read_text("utf-8")
    assert 'os.path.relpath(content_dir, "docs")' in src, (
        "게시 폴더가 docs/ 아래가 아니라면 이 감사의 전제를 다시 봐야 한다")
