"""고객 등록 전략의 어드민 수집 — 동의한 것만, 개인정보 없이 (2026-08-18).

사장님 지시: "고객들이 등록하는 자료들은 내 어드민 대시보드에서도 확보".

지켜야 할 약속:
- **동의 체크박스를 켠 제출만** 전송된다 — 기본값은 보내지 않음.
- 보내는 것은 전략 명세와 앱 버전뿐 — 개인정보·계좌·성적이 실리지 않는다.
- 전송 실패는 등록을 막지 않는다 — 결과만 정직하게 화면에 적힌다.
- 워커는 수집함(KV) 미설정을 조용히 삼키지 않고 이유를 돌려준다.
- 어드민 목록 API는 어드민 게이트 뒤에 있다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.ingest.extract import extract_spec              # noqa: E402
from quant.web import mystrategy as MS                     # noqa: E402

WORKER = (ROOT / "worker.js").read_text("utf-8")
ADMIN = (ROOT / "docs" / "admin.html").read_text("utf-8")

_MATERIAL = "20일 이동평균이 60일 이동평균을 위로 돌파하면 매수한다. " \
            "종가가 20일 이동평균 아래로 내려오면 매도한다."


def _spec():
    r = extract_spec(_MATERIAL, title="공유 검사용")
    assert r.ok
    return r.spec


def test_consent_is_required_before_anything_is_sent(monkeypatch):
    """체크박스 없이 저장하면 전송 코드가 **불리지도 않는다.**"""
    calls = []
    monkeypatch.setattr(MS, "_share_spec",
                        lambda spec, transport=None: calls.append(1) or "?")
    html = MS.run_ingest_html(
        {"text": _MATERIAL, "name": "t", "save": "1"},
        state_dir=str(_tmp()))
    assert "저장됐습니다" in html
    assert not calls, "동의 없이 제작사로 전송됐다 — 신뢰 위반"


def test_a_consented_save_sends_spec_and_nothing_personal(tmp_path):
    sent = {}

    def transport(url, payload):
        sent["url"], sent["payload"] = url, payload
        return 200, "{\"ok\": true}"

    note = MS._share_spec(_spec(), transport=transport)
    assert "전송됐습니다" in note
    assert sent["url"].endswith("/api/submit-spec")
    doc = json.loads(sent["payload"])
    assert doc["spec"]["entry"], "규칙 없는 빈 껍데기를 보냈다"
    # 개인정보·계좌 관련 키가 실리면 안 된다 — 명세와 버전뿐이어야 한다.
    flat = json.dumps(doc, ensure_ascii=False)
    for banned in ("email", "cash", "equity", "token", "password"):
        assert banned not in flat.lower(), f"{banned}이(가) 전송 본문에 있다"


def test_share_failure_never_blocks_registration(monkeypatch):
    """수집함이 죽어 있어도 등록은 성공하고, 실패는 화면에 정직하게 적힌다."""
    monkeypatch.setattr(
        MS, "_share_spec",
        lambda spec, transport=None: "제작사 공유: 실패(수집함 미설정) — 등록에는 영향 없습니다.")
    html = MS.run_ingest_html(
        {"text": _MATERIAL, "name": "t", "save": "1", "share": "1"},
        state_dir=str(_tmp()))
    assert "저장됐습니다" in html and "실패(수집함 미설정)" in html


def test_the_failure_reason_comes_from_the_server(monkeypatch):
    note = MS._share_spec(_spec(), transport=lambda u, p: (
        503, json.dumps({"error": "수집함 미설정 — KV 연결 필요"})))
    assert "수집함 미설정" in note and "영향 없" in note


def test_the_preview_form_carries_the_consent_checkbox():
    html = MS.run_ingest_html({"text": _MATERIAL, "name": "t"},
                              state_dir=str(_tmp()))
    assert 'name="share"' in html and "선택" in html, (
        "동의 체크박스가 없다 — 동의 없는 수집이 되거나 수집 자체가 안 된다")
    assert 'checked' not in html.split('name="share"')[1][:80], (
        "동의가 기본 켜짐이다 — 선택이 아니라 통보가 된다")


def test_the_worker_guards_and_lists():
    """워커 계약 — 문자열 봉인(JS는 pytest가 실행하지 못한다).

    · /api/submit-spec 경로와 KV 미설정 시의 정직한 거절이 있다
    · 어드민 목록은 /api/admin/ 접두사 아래(= adminGate 뒤)에 있다
    · 제출 본문에는 크기 상한이 있다
    """
    assert '"/api/submit-spec"' in WORKER
    assert "SUBMISSIONS" in WORKER and "수집함 미설정" in WORKER
    assert '"/api/admin/submissions"' in WORKER
    assert 'url.pathname.startsWith("/api/admin")' in WORKER
    assert "SUBMIT_MAX_BYTES" in WORKER


def test_the_admin_page_shows_the_submissions():
    assert "고객 등록 전략" in ADMIN and "/api/admin/submissions" in ADMIN
    assert "동의한" in ADMIN, "어드민 화면이 '동의한 제출만'임을 말하지 않는다"


def _tmp():
    import tempfile
    return tempfile.mkdtemp()
