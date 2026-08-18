"""사용 원격 측정(텔레메트리) — 약관에 고지하고 동의받아 제작사로 보낸다.

2026-08-18 사장님 지시: 고객이 등록한 전략과 **성과(수익률)**를 제작사가
파악할 수 있게 한다. 단 **약관에 명시하고 동의를 받는다** — 몰래 수집은
이 제품의 정체성(투명성)과 개인정보보호법 양쪽에 어긋나므로 하지 않는다.

이 모듈이 지키는 경계:
  · **동의 없이는 한 바이트도 나가지 않는다.** consent.json에 수락 기록이
    있을 때만 payload를 만들고 전송한다.
  · **보안 자격증명은 절대 담지 않는다.** 비밀번호·증권사/거래소 API 키·
    세션 토큰·.env는 payload 생성 자체에서 제외된다(수집 대상이 아니라
    '남의 계좌 열쇠'라, 모으면 제작사가 해킹·배상 책임을 진다). 이건
    동의로도 풀 수 없는 선이다.
  · 전송 실패는 본 작업(매매·기록)을 막지 않는다.

보내는 것: 설치 식별자(익명 랜덤), 앱 버전, 동의 시각, 등록 전략 명세,
계좌별 성과 요약(수익률·최대낙폭·자산·기록 길이).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

CONSENT_FILE = "consent.json"
CONSENT_VERSION = "2026-08-18"
SITE_URL = "https://quant.jiwon-1a2.workers.dev"

# 이 키가 payload 어디에 있으면 유출이다 — 전송 직전 검사가 확인한다.
FORBIDDEN_KEYS = ("password", "passwd", "secret", "api_key", "apikey",
                  "appkey", "appsecret", "token", "private_key", "seed_phrase")


def consent_path(state_dir: str) -> str:
    return os.path.join(state_dir, CONSENT_FILE)


def consent_status(state_dir: str = "state") -> dict:
    """동의 상태. accepted가 False면 아무것도 보내지 않는다."""
    try:
        with open(consent_path(state_dir), encoding="utf-8") as f:
            d = json.load(f)
        return {"accepted": bool(d.get("accepted")),
                "at": d.get("at"), "version": d.get("version"),
                "install_id": d.get("install_id")}
    except (OSError, ValueError):
        return {"accepted": False, "at": None, "version": None,
                "install_id": None}


def set_consent(state_dir: str, accepted: bool, *, rng=None) -> dict:
    """동의를 기록한다. 최초 동의 때 익명 설치 식별자를 한 번 만든다."""
    from quant.utils.jsonio import atomic_write_json
    cur = consent_status(state_dir)
    install_id = cur.get("install_id")
    if accepted and not install_id:
        import secrets
        install_id = (rng or secrets.token_hex)(8)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    rec = {"accepted": bool(accepted), "at": now,
           "version": CONSENT_VERSION, "install_id": install_id}
    os.makedirs(state_dir, exist_ok=True)
    atomic_write_json(consent_path(state_dir), rec)
    return rec


def _app_version() -> str:
    try:
        return open("VERSION", encoding="utf-8").read().strip()
    except OSError:
        return ""


def _performance(state_dir: str) -> list[dict]:
    """계좌별 성과 요약 — 장부에서 직접. 자격증명은 애초에 여기 없다."""
    from quant.live.ledger_basics import (
        chrono, ledger_files, max_drawdown_from_index, twr_index)
    out = []
    for path in ledger_files(state_dir):
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        hist = chrono(st.get("history") or [])
        if not hist:
            continue
        deposits = st.get("deposits") or []
        start_cash = float(st.get("start_cash", 0.0) or 0.0)
        try:
            mdd = max_drawdown_from_index(twr_index(hist, deposits, start_cash=start_cash))
        except Exception:  # noqa: BLE001 — 성과 계산 실패가 텔레메트리를 막지 않는다
            mdd = None
        out.append({
            "key": f"{st.get('market', '?')}:{st.get('symbol', '?')}",
            "return_pct": hist[-1].get("return_pct"),
            "equity": hist[-1].get("equity"),
            "mdd_pct": round(mdd * 100, 2) if mdd is not None else None,
            "days": len(hist),
        })
    return out


def build_payload(state_dir: str = "state") -> dict | None:
    """동의했을 때만 payload를 만든다. 아니면 None."""
    st = consent_status(state_dir)
    if not st.get("accepted"):
        return None
    from quant.ingest.registry import load_specs
    specs, _reasons = load_specs(state_dir)
    payload = {
        "kind": "telemetry",
        "install_id": st.get("install_id"),
        "app_version": _app_version(),
        "consent": {"at": st.get("at"), "version": st.get("version")},
        "strategies": [s.to_dict() for s in specs],
        "performance": _performance(state_dir),
    }
    _assert_no_credentials(payload)
    return payload


def _assert_no_credentials(payload: dict) -> None:
    """전송 직전 마지막 방어선 — 금지 키가 섞였으면 전송을 막는다.

    payload 생성 경로가 자격증명을 만들지 않도록 설계돼 있지만, 나중에
    누가 필드를 늘리다 실수로 넣을 수 있다. 그 실수가 조용히 유출되지
    않도록, 직렬화한 문자열에서 금지 키를 직접 찾는다.
    """
    flat = json.dumps(payload, ensure_ascii=False).lower()
    for banned in FORBIDDEN_KEYS:
        if f'"{banned}"' in flat or f"{banned}=" in flat:
            raise ValueError(
                f"텔레메트리에 자격증명으로 보이는 키('{banned}')가 있다 — "
                "전송을 막았다(동의로도 풀 수 없는 보안선).")


def send(state_dir: str = "state", *, transport=None) -> str:
    """동의 시 payload를 제작사로 보낸다. 결과 한 줄을 돌려준다."""
    payload = build_payload(state_dir)
    if payload is None:
        return "텔레메트리: 동의 없음 — 아무것도 전송하지 않았습니다."
    import urllib.request as _rq
    url = (os.getenv("QUANT_SITE_URL") or SITE_URL).rstrip("/") + "/api/telemetry"
    body = json.dumps(payload, ensure_ascii=False)
    try:
        if transport is not None:
            status, _resp = transport(url, body)
        else:
            req = _rq.Request(url, data=body.encode("utf-8"),
                              headers={"Content-Type": "application/json"},
                              method="POST")
            with _rq.urlopen(req, timeout=6) as r:
                status = r.status
        if status == 200:
            return "텔레메트리: 전송됐습니다(동의하신 범위)."
        return f"텔레메트리: 실패(HTTP {status}) — 본 작업에는 영향 없습니다."
    except Exception as exc:  # noqa: BLE001 — 전송 실패가 매매/기록을 막지 않는다
        return f"텔레메트리: 실패({type(exc).__name__}) — 본 작업에는 영향 없습니다."
