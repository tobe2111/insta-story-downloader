"""라이선스 키(단건 판매용, 영구) 테스트 — 순수 stdlib.

만료·원격차단이 없는 '구매 증명' 키임을 검증한다(구독 게이팅이 아니다).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "licensing", str(Path(__file__).resolve().parent.parent / "quant" / "licensing.py"))
lic = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = lic
_spec.loader.exec_module(lic)

_SECRET = "test-secret-please-keep-long-and-random"


def _clear_env():
    for k in ("QUANT_LICENSE_SECRET", "QUANT_LICENSE_OWNER",
              "QUANT_LICENSE_KEY", "QUANT_REQUIRE_LICENSE"):
        os.environ.pop(k, None)


def test_generate_is_deterministic_and_formatted():
    k1 = lic.generate_key("buyer@email.com", secret=_SECRET)
    k2 = lic.generate_key("buyer@email.com", secret=_SECRET)
    assert k1 == k2                       # 같은 구매자+비밀 → 같은 키(영구·재현)
    assert k1.startswith("QUANT-")
    # 만료/날짜 정보가 키에 없다(구독 아님)
    assert k1.replace("QUANT-", "").replace("-", "").isalnum()


def test_verify_true_for_matching_and_case_insensitive():
    key = lic.generate_key("Buyer@Email.com", secret=_SECRET)
    assert lic.verify_key("buyer@email.com", key, secret=_SECRET)      # 소유자 정규화
    # 대소문자/구분자 달라도 통과
    scrambled = key.lower().replace("-", " ")
    assert lic.verify_key("buyer@email.com", scrambled, secret=_SECRET)


def test_verify_false_for_wrong_owner_or_key():
    key = lic.generate_key("buyer@email.com", secret=_SECRET)
    assert not lic.verify_key("someone-else@email.com", key, secret=_SECRET)
    assert not lic.verify_key("buyer@email.com", "QUANT-AAAAAA-BBBBBB-CCCCCC-DDDDDD",
                              secret=_SECRET)
    # 다른 비밀로 발급된 키는 무효(위조 방지 — 비밀을 모르면 못 만든다)
    other = lic.generate_key("buyer@email.com", secret="different-secret")
    assert not lic.verify_key("buyer@email.com", other, secret=_SECRET)


def test_missing_secret_raises_on_generate():
    _clear_env()
    try:
        lic.generate_key("buyer@email.com")   # 비밀 없음
        assert False, "비밀 없으면 예외여야 함"
    except RuntimeError:
        pass
    finally:
        _clear_env()


def test_load_and_is_licensed_via_env():
    _clear_env()
    os.environ["QUANT_LICENSE_SECRET"] = _SECRET
    os.environ["QUANT_LICENSE_OWNER"] = "buyer@email.com"
    os.environ["QUANT_LICENSE_KEY"] = lic.generate_key("buyer@email.com", secret=_SECRET)
    try:
        assert lic.is_licensed()
        os.environ["QUANT_LICENSE_KEY"] = "QUANT-BADBAD-BADBAD-BADBAD-BADBAD"
        assert not lic.is_licensed()
    finally:
        _clear_env()


def test_license_file_read(tmp_path):
    _clear_env()
    os.environ["QUANT_LICENSE_SECRET"] = _SECRET
    key = lic.generate_key("buyer@email.com", secret=_SECRET)
    (tmp_path / "license.key").write_text(
        f"owner: buyer@email.com\nkey: {key}\n", encoding="utf-8")
    try:
        assert lic.is_licensed(root=str(tmp_path))
    finally:
        _clear_env()


def test_require_license_default_off_and_enforced():
    _clear_env()
    # 플래그 미설정 → 개발/CI: 항상 통과(라이선스 없어도)
    assert lic.require_license() is True

    # 플래그 on + 라이선스 없음 → 차단
    os.environ["QUANT_REQUIRE_LICENSE"] = "1"
    try:
        assert lic.require_license() is False
        # 플래그 on + 유효 라이선스 → 통과
        os.environ["QUANT_LICENSE_SECRET"] = _SECRET
        os.environ["QUANT_LICENSE_OWNER"] = "buyer@email.com"
        os.environ["QUANT_LICENSE_KEY"] = lic.generate_key(
            "buyer@email.com", secret=_SECRET)
        assert lic.require_license() is True
    finally:
        _clear_env()
