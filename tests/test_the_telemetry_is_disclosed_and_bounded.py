"""사용 원격 측정 — 약관 고지·동의 기반, 자격증명은 절대 안 나간다.

2026-08-18 사장님 지시: 등록 전략과 성과(수익률)를 제작사가 수집하되
**약관에 고지하고 동의를 받는다.**

지켜야 할 약속:
- 동의 기록이 없으면 payload 자체가 None이고, send()는 아무것도 안 보낸다.
- 동의하면 전략 명세 + 성과(수익률·낙폭·자산)가 담긴다.
- **비밀번호·API 키·토큰 등 자격증명은 payload에 절대 없다** — 있으면
  전송 직전 검사가 막는다(동의로도 못 푸는 보안선).
- 동의 화면이 '무엇을 모으는지'를 숨김없이 밝힌다.
- 전송 실패는 본 작업을 막지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant import telemetry as T                          # noqa: E402


def _ledger(state_dir, name, market, symbol, equities, start=10000.0):
    import os
    os.makedirs(state_dir / "paper", exist_ok=True)
    hist = [{"date": f"2026-08-{d + 1:02d}", "equity": e,
             "return_pct": round((e / start - 1) * 100, 2)}
            for d, e in enumerate(equities)]
    (state_dir / "paper" / name).write_text(
        json.dumps({"market": market, "symbol": symbol,
                    "start_cash": start, "history": hist}), "utf-8")


def test_no_consent_sends_nothing(tmp_path):
    _ledger(tmp_path, "a.json", "crypto", "BTC/USDT", [10000, 10100, 10200])
    assert T.build_payload(str(tmp_path)) is None
    note = T.send(str(tmp_path), transport=lambda u, b: pytest.fail("전송됐다"))
    assert "동의 없음" in note


def test_consent_is_recorded_with_an_anonymous_id(tmp_path):
    rec = T.set_consent(str(tmp_path), True, rng=lambda n: "abc12345")
    assert rec["accepted"] and rec["install_id"] == "abc12345"
    st = T.consent_status(str(tmp_path))
    assert st["accepted"] and st["version"] == T.CONSENT_VERSION
    # 철회하면 전송이 멈추지만 설치 식별자는 유지(같은 설치임을 안다)
    T.set_consent(str(tmp_path), False)
    assert not T.consent_status(str(tmp_path))["accepted"]


def test_a_consented_payload_carries_strategies_and_performance(tmp_path):
    _ledger(tmp_path, "a.json", "crypto", "BTC/USDT", [10000, 9800, 10300])
    T.set_consent(str(tmp_path), True, rng=lambda n: "id00")
    p = T.build_payload(str(tmp_path))
    assert p is not None and p["kind"] == "telemetry"
    assert p["install_id"] == "id00"
    perf = {r["key"]: r for r in p["performance"]}
    assert "crypto:BTC/USDT" in perf
    row = perf["crypto:BTC/USDT"]
    assert row["return_pct"] is not None and row["mdd_pct"] is not None
    assert row["days"] == 3


def test_credentials_never_leave_even_by_mistake(tmp_path):
    T.set_consent(str(tmp_path), True)
    # 누가 실수로 자격증명 필드를 넣은 상황을 흉내 — 전송 직전 검사가 막아야.
    bad = {"kind": "telemetry", "install_id": "x", "api_key": "sk-secret"}
    with pytest.raises(ValueError, match="자격증명"):
        T._assert_no_credentials(bad)
    # 정상 payload는 통과
    T._assert_no_credentials({"kind": "telemetry", "strategies": [],
                              "performance": [{"return_pct": 3.0}]})


def test_the_real_payload_has_no_forbidden_keys(tmp_path):
    _ledger(tmp_path, "a.json", "crypto", "BTC/USDT", [10000, 10100])
    T.set_consent(str(tmp_path), True)
    flat = json.dumps(T.build_payload(str(tmp_path)), ensure_ascii=False).lower()
    for banned in T.FORBIDDEN_KEYS:
        assert f'"{banned}"' not in flat, f"{banned}이(가) 전송 본문에 있다"


def test_send_failure_never_raises(tmp_path):
    _ledger(tmp_path, "a.json", "crypto", "BTC/USDT", [10000, 10100])
    T.set_consent(str(tmp_path), True)

    def boom(url, body):
        raise ConnectionError("네트워크 끊김")
    note = T.send(str(tmp_path), transport=boom)
    assert "실패" in note and "영향 없" in note


def test_the_consent_screen_discloses_what_is_collected():
    from quant.web.app import render_consent_page
    html = render_consent_page(state_dir="/nonexistent-consent")
    for must in ("수익률", "전략", "익명", "비밀번호", "API 키", "동의"):
        assert must in html, f"동의 화면이 '{must}'를 밝히지 않는다"
    assert "전송되지 않습니다" in html, "자격증명 제외를 명시하지 않는다"


def test_the_consent_toggle_records(tmp_path):
    from quant.web.app import run_consent_toggle
    run_consent_toggle({"accept": "1"}, state_dir=str(tmp_path))
    assert T.consent_status(str(tmp_path))["accepted"]
    run_consent_toggle({"accept": "0"}, state_dir=str(tmp_path))
    assert not T.consent_status(str(tmp_path))["accepted"]


def test_the_worker_has_a_gated_telemetry_endpoint():
    worker = (ROOT / "worker.js").read_text("utf-8")
    assert '"/api/telemetry"' in worker and "submitTelemetry" in worker
    assert 'prefix: "tele:"' in worker, "어드민 목록이 텔레메트리를 안 읽는다"
    # 저장 목록 API는 어드민 게이트 접두사 아래에 있다
    assert 'url.pathname.startsWith("/api/admin")' in worker
