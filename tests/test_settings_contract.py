"""설정 계약 검사 — '아무도 못 돌리는 손잡이'를 구조적으로 막는다.

배경(2026-08-11 감사에서 발견): load_settings()는 화이트리스트다. 명시적으로
옮겨 담지 않은 키는 조용히 버려진다. 그래서 그날 새로 만든 리스크 손잡이
(portfolio_target_vol / risk_override_ack)는 코드가 읽어도 **영원히 None**이고,
어드민에는 입력칸조차 없었다. 기능은 '구현'됐지만 실제로는 존재하지 않았다.

이 테스트는 그 결함 계열 전체를 막는다:
  ① 코드가 읽는 모든 설정 키가 DEFAULTS에 있다(없으면 항상 None)
  ② load_settings()가 그 키를 실제로 반환한다(화이트리스트 누락 방지)
  ③ 어드민 화면에서 켤 수 있고, 저장 payload에도 실려 나간다
  ④ 값 검증·클램프가 작동한다(오타가 리스크가 되면 안 된다)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.settings import (  # noqa: E402
    DEFAULTS,
    MAX_TARGET_VOL,
    MIN_TARGET_VOL,
    load_settings,
)

ROOT = Path(__file__).resolve().parent.parent
QUANT = ROOT / "quant"
ADMIN = ROOT / "docs" / "admin.html"

# 표시 전용(코드가 읽지 않는) 키 — ①의 역방향 검사에서 제외한다
_DISPLAY_ONLY = {"note"}


def _settings_keys_read_in_code() -> set[str]:
    """quant/ 전체에서 설정 객체를 통해 읽는 키를 모은다.

    load_settings()로 만든 변수를 파일 단위로 추적한 뒤 그 변수의 .get("키")를
    수집한다 — 체이닝(load_settings().get(...))도 함께 잡는다.
    """
    keys: set[str] = set()
    for path in QUANT.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "load_settings" not in src:
            continue
        keys |= set(re.findall(r'load_settings\([^)]*\)\.get\(\s*"([a-z_]+)"',
                               src))
        varnames = set(re.findall(r'(\w+)\s*=\s*load_settings\(', src))
        for var in varnames:
            keys |= set(re.findall(rf'\b{var}\.get\(\s*"([a-z_]+)"', src))
            keys |= set(re.findall(rf'\b{var}\[\s*"([a-z_]+)"\s*\]', src))
    return keys


# ── ① 읽는 키는 반드시 DEFAULTS에 ─────────────────────────────


def test_every_key_read_in_code_exists_in_defaults():
    read = _settings_keys_read_in_code()
    assert read, "설정을 읽는 코드를 하나도 못 찾았다 — 탐지기가 고장났다"
    missing = read - set(DEFAULTS)
    assert not missing, (
        f"코드가 읽지만 DEFAULTS에 없다(항상 None이 된다): {sorted(missing)}")


def test_load_settings_returns_every_default_key():
    """화이트리스트 누락 방지 — DEFAULTS에 넣고 옮겨 담기를 잊는 실수를 잡는다."""
    s = load_settings("config/__nonexistent__.json")
    assert set(s) == set(DEFAULTS)


def test_declared_knobs_are_actually_read_somewhere():
    """DEFAULTS에만 있고 아무도 안 읽는 죽은 키를 잡는다(표시 전용 제외)."""
    read = _settings_keys_read_in_code()
    dead = set(DEFAULTS) - read - _DISPLAY_ONLY
    assert not dead, f"선언만 되고 코드가 안 읽는 설정: {sorted(dead)}"


# ── ③ 어드민에서 실제로 돌릴 수 있는가 ────────────────────────


def test_admin_page_exposes_every_setting():
    html = ADMIN.read_text(encoding="utf-8")
    for key in DEFAULTS:
        assert f'id="{key}"' in html, f"어드민에 입력칸이 없다: {key}"


def test_admin_save_payload_includes_every_setting():
    html = ADMIN.read_text(encoding="utf-8")
    body = html.split('$("save").onclick')[1]
    for key in DEFAULTS:
        assert re.search(rf'\b{key}\s*:', body), (
            f"어드민 저장 payload에 빠졌다(저장해도 사라진다): {key}")


# ── ④ 검증·클램프 ─────────────────────────────────────────────


def _write(tmp_path, obj) -> str:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_target_vol_is_clamped_to_sane_range(tmp_path):
    hi = load_settings(_write(tmp_path, {"portfolio_target_vol": 99.0}))
    assert hi["portfolio_target_vol"] == MAX_TARGET_VOL
    lo = load_settings(_write(tmp_path, {"portfolio_target_vol": -1.0}))
    assert lo["portfolio_target_vol"] == MIN_TARGET_VOL


def test_blank_or_garbage_target_vol_falls_back_to_code_default(tmp_path):
    for bad in ("", None, "abc", {}):
        s = load_settings(_write(tmp_path, {"portfolio_target_vol": bad}))
        assert s["portfolio_target_vol"] is None, bad


def test_override_defaults_off_and_is_explicit(tmp_path):
    assert load_settings(_write(tmp_path, {}))["risk_override_ack"] is False
    on = load_settings(_write(tmp_path, {"risk_override_ack": True}))
    assert on["risk_override_ack"] is True


# ── ⑤ 손잡이가 실제로 리스크를 움직이는가(끝단 확인) ──────────


def test_target_vol_setting_actually_changes_the_target(tmp_path, monkeypatch):
    """설정 → target_vol_now() 반영. 미입증 상태에서는 잠금이 걸린다."""
    from quant.risk import portfolio_vol as pv

    cfg = dict(DEFAULTS)
    cfg["portfolio_target_vol"] = 0.25
    monkeypatch.setattr("quant.utils.settings.load_settings",
                        lambda *a, **k: cfg)

    # 미입증 + 승인 없음 → 검증 목표로 잘린다
    target, proven, _ = pv.target_vol_now(str(tmp_path))
    assert not proven
    assert target == pv.VERIFY_TARGET_VOL

    # 소유자 승인 → 설정값이 그대로 적용된다
    cfg["risk_override_ack"] = True
    target, _, why = pv.target_vol_now(str(tmp_path))
    assert target == 0.25
    assert "소유자 우회" in why
