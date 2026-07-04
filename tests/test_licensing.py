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


# ── Ed25519(선택적) — cryptography가 없거나 깨졌으면 건너뛴다 ─────────────
# unittest.SkipTest는 pytest에서도 skip으로 처리된다(stdlib만으로 스킵 가능).


def _require_ed25519():
    if not lic.HAS_ED25519:
        import unittest
        raise unittest.SkipTest("cryptography 미설치/사용 불가 — Ed25519 테스트 건너뜀")


def test_ed25519_keypair_sign_verify():
    _require_ed25519()
    priv, pub = lic.gen_keypair()
    key = lic.generate_key_ed25519("Buyer@Email.com", private_key=priv)
    assert key.startswith("QUANT-ED1-")
    # 소유자 정규화 + 대소문자/구분자 무시(base32라 가능)
    assert lic.verify_key("buyer@email.com", key, public_key=pub)
    assert lic.verify_key("buyer@email.com", key.lower().replace("-", " "),
                          public_key=pub)
    # 만료/날짜 정보가 키에 없다(영구 키 — 구독 아님)
    assert key.replace("QUANT-", "").replace("-", "").isalnum()


def test_ed25519_rejects_wrong_owner_or_key():
    _require_ed25519()
    priv, pub = lic.gen_keypair()
    key = lic.generate_key_ed25519("buyer@email.com", private_key=priv)
    assert not lic.verify_key("someone-else@email.com", key, public_key=pub)
    # 다른 개인키로 서명된 키는 무효(공개키만 배포되므로 위조 불가)
    priv2, _ = lic.gen_keypair()
    forged = lic.generate_key_ed25519("buyer@email.com", private_key=priv2)
    assert not lic.verify_key("buyer@email.com", forged, public_key=pub)


def test_ed25519_falls_back_to_hmac_for_hmac_keys():
    _require_ed25519()
    _, pub = lic.gen_keypair()
    # 공개키가 설정돼 있어도 기존 HMAC 키는 그대로 유효해야 한다(공존).
    hkey = lic.generate_key("buyer@email.com", secret=_SECRET)
    assert lic.verify_key("buyer@email.com", hkey, secret=_SECRET, public_key=pub)
    assert not lic.verify_key("buyer@email.com", hkey, secret="다른-비밀",
                              public_key=pub)


def test_ed25519_is_licensed_via_env():
    _require_ed25519()
    _clear_env()
    priv, pub = lic.gen_keypair()
    key = lic.generate_key_ed25519("buyer@email.com", private_key=priv)
    os.environ["QUANT_LICENSE_PUBKEY"] = pub
    os.environ["QUANT_LICENSE_OWNER"] = "buyer@email.com"
    os.environ["QUANT_LICENSE_KEY"] = key
    try:
        assert lic.is_licensed()                       # HMAC 비밀 없이도 통과
        os.environ["QUANT_LICENSE_OWNER"] = "other@email.com"
        assert not lic.is_licensed()
    finally:
        os.environ.pop("QUANT_LICENSE_PUBKEY", None)
        _clear_env()


def test_gen_keypair_raises_without_cryptography():
    if lic.HAS_ED25519:
        import unittest
        raise unittest.SkipTest("cryptography 사용 가능 — 폴백 경로는 해당 없음")
    # cryptography가 없으면 명확한 오류로 안내하고, HMAC 경로는 영향이 없어야 한다.
    try:
        lic.gen_keypair()
        assert False, "cryptography 없으면 예외여야 함"
    except RuntimeError:
        pass
    assert lic.verify_key("buyer@email.com",
                          lic.generate_key("buyer@email.com", secret=_SECRET),
                          secret=_SECRET)


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
