"""1회용(영구) 라이선스 키 — 단건 판매 보조 도구.

⚠️ 이것은 '구매 증명(proof-of-purchase)'용 경량 라이선스다. 구독·만료·원격차단이
   아니라, 한 번 구매하면 '영구히 유효'한 키다(단건 판매 모델). 매달 껐다 켜는
   구독 게이팅은 의도적으로 만들지 않는다 — 미등록 상태의 유료 자동투자 서비스는
   국내 자본시장법상 위법 소지가 크기 때문이다.

정직한 한계(반드시 이해할 것):
    · 프로그램을 코드/실행파일로 배포하면 '검증 비밀'도 함께 배포된다. 마음먹은
      사람은 비밀을 추출해 키를 위조하거나 검증 코드를 아예 제거할 수 있다. 즉
      이건 완전한 복제방지(DRM)가 아니라 '정품 확인 + 캐주얼 공유 억제' 수준이다.
      (배포된 코드에 건 잠금은 원리상 우회 가능하다.)
    · 더 강한 보호가 필요하면 대칭키(HMAC) 대신 비대칭 서명(Ed25519)을 쓴다.
      이 모듈은 `cryptography` 패키지가 '있으면' Ed25519를 지원한다(선택 의존성).
      없으면 조용히 HMAC만 쓴다 — 기본 배포는 여전히 의존성 0이다.
      · HMAC(대칭): 검증 비밀이 배포본에 들어가므로 추출하면 키를 '위조'할 수 있다.
      · Ed25519(비대칭): 배포본에는 '공개키'만 들어가므로 키 위조는 불가능하다.
        단, 검증 코드를 제거하는 우회는 여전히 가능하다(DRM이 아니다).

── Ed25519 사용법(선택, `pip install cryptography` 필요) ────────────────
    1) 키쌍을 한 번 만든다(개인키는 판매자만 보관, 절대 배포·커밋 금지):
       python -m quant.licensing gen-keypair
    2) 출력된 공개키를 배포본의 quant/_license_pub.py 에 넣는다:
           PUBLIC_KEY = "base64-공개키"
       (또는 환경변수 QUANT_LICENSE_PUBKEY)
    3) 키 발급은 동일하게 gen 명령 — 개인키(QUANT_LICENSE_PRIVKEY)가 설정돼
       있으면 자동으로 Ed25519 서명 키를 발급한다:
       python -m quant.licensing gen --owner buyer@email.com
    구매자 쪽 사용법은 HMAC 키와 완전히 동일하다(license.key / 환경변수).
    Ed25519 키에도 만료·구독 정보는 없다 — 영구 키다.

판매 시 법적 주의(한국):
    · '수익 보장' 문구는 절대 금지(사기죄 직행). 이 프로그램은 수익을 보장하지 않는다.
    · 백테스트/리서치 '도구' 판매로 포지셔닝할 것. 유료 매매신호 지속제공·일임 금지.
    · 판매 전 핀테크 변호사에게 '유사투자자문업 신고' 필요 여부를 확인할 것.

── 판매자(seller) 사용법 ────────────────────────────────────────────────
    1) 강한 비밀을 한 번 정해 안전하게 보관한다(유출 시 위조 가능).
       export QUANT_LICENSE_SECRET='아주-긴-무작위-문자열'
    2) 구매자마다 키를 발급한다(구매 이메일 등에 묶임):
       python -m quant.licensing gen --owner buyer@email.com
    3) 배포본에는 비밀을 quant/_license_key.py(깃 미포함)에 넣어 함께 빌드한다:
           SECRET = "아주-긴-무작위-문자열"
       그리고 QUANT_REQUIRE_LICENSE=1 로 배포하면 정품 키를 요구한다.

── 구매자(buyer) 사용법 ─────────────────────────────────────────────────
    프로그램 폴더에 license.key 파일을 만들고 발급받은 값을 넣는다:
        owner: buyer@email.com
        key:   QUANT-XXXXXX-XXXXXX-XXXXXX-XXXXXX
    (또는 환경변수 QUANT_LICENSE_OWNER / QUANT_LICENSE_KEY)

비밀 해석 순서: 함수 인자 → 환경변수 QUANT_LICENSE_SECRET → quant/_license_key.SECRET
공개키 해석 순서: 함수 인자 → 환경변수 QUANT_LICENSE_PUBKEY → quant/_license_pub.PUBLIC_KEY
개인키 해석 순서: 함수 인자 → 환경변수 QUANT_LICENSE_PRIVKEY → quant/_license_priv.PRIVATE_KEY
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import sys
from pathlib import Path

_PREFIX = "QUANT"
_ENV_SECRET = "QUANT_LICENSE_SECRET"
_ENV_OWNER = "QUANT_LICENSE_OWNER"
_ENV_KEY = "QUANT_LICENSE_KEY"
_ENV_ENFORCE = "QUANT_REQUIRE_LICENSE"
_ENV_PUBKEY = "QUANT_LICENSE_PUBKEY"      # Ed25519 공개키(base64) — 배포본에 포함 가능
_ENV_PRIVKEY = "QUANT_LICENSE_PRIVKEY"    # Ed25519 개인키(base64) — 판매자만 보관
_LICENSE_FILE = "license.key"
_ED_MARK = "ED1"                          # Ed25519 키 형식 표식(QUANT-ED1-...)

# `cryptography`는 '선택' 의존성이다 — 없으면 Ed25519 기능만 꺼지고 HMAC은 그대로.
# BaseException까지 잡는 이유: 깨진 설치본(_cffi_backend 누락 등)은 ImportError가
# 아니라 pyo3 PanicException(BaseException 계열)을 던질 수 있다. 선택 기능 때문에
# 프로그램 전체가 죽어서는 안 된다.
try:
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey as _EdPriv,
        Ed25519PublicKey as _EdPub,
    )
    HAS_ED25519 = True
except BaseException:  # noqa: BLE001 - 미설치/깨진 설치 모두 HMAC 폴백
    HAS_ED25519 = False


def _resolve_secret(secret: str | None = None) -> bytes | None:
    """비밀을 인자→환경변수→내장 모듈 순으로 찾는다(없으면 None)."""
    if secret:
        return secret.encode()
    env = os.getenv(_ENV_SECRET)
    if env:
        return env.encode()
    try:  # 판매자가 배포 전 생성하는 깃 미포함 모듈
        from quant import _license_key  # type: ignore
        val = getattr(_license_key, "SECRET", "")
        if val:
            return str(val).encode()
    except Exception:  # noqa: BLE001
        pass
    return None


def _normalize_owner(owner: str) -> str:
    return (owner or "").strip().lower()


def _canon(key: str) -> str:
    """대소문자·구분자 무시 정규화(공백/하이픈 제거, 대문자화)."""
    return re.sub(r"[^A-Z0-9]", "", (key or "").upper())


def generate_key(owner: str, secret: str | None = None) -> str:
    """구매자 식별자(이메일/이름)에 묶인 영구 라이선스 키를 만든다(판매자용).

    같은 (owner, secret)면 항상 같은 키가 나온다(결정론적). 만료 정보는 없다.
    """
    sec = _resolve_secret(secret)
    if not sec:
        raise RuntimeError(
            "라이선스 비밀이 없습니다. QUANT_LICENSE_SECRET 환경변수를 설정하거나 "
            "generate_key(owner, secret=...)로 전달하세요.")
    dig = hmac.new(sec, _normalize_owner(owner).encode(), hashlib.sha256).digest()
    body = base64.b32encode(dig[:15]).decode().rstrip("=")   # 24 base32 문자
    groups = "-".join(body[i:i + 6] for i in range(0, len(body), 6))
    return f"{_PREFIX}-{groups}"


# ── Ed25519 비대칭 서명(선택적) ─────────────────────────────────────────


def _resolve_public_key(public_key: str | None = None) -> str | None:
    """Ed25519 공개키(base64)를 인자→환경변수→내장 모듈 순으로 찾는다."""
    if public_key:
        return public_key
    env = os.getenv(_ENV_PUBKEY)
    if env:
        return env
    try:  # 판매자가 배포 전 생성하는 공개키 모듈(공개키는 배포돼도 안전)
        from quant import _license_pub  # type: ignore
        val = getattr(_license_pub, "PUBLIC_KEY", "")
        if val:
            return str(val)
    except Exception:  # noqa: BLE001
        pass
    return None


def _resolve_private_key(private_key: str | None = None) -> str | None:
    """Ed25519 개인키(base64)를 인자→환경변수→내장 모듈 순으로 찾는다.

    개인키는 판매자만 보관한다 — 배포본·깃에 절대 넣지 말 것(.gitignore 참고).
    """
    if private_key:
        return private_key
    env = os.getenv(_ENV_PRIVKEY)
    if env:
        return env
    try:  # 판매자 로컬 전용 모듈(깃 미포함)
        from quant import _license_priv  # type: ignore
        val = getattr(_license_priv, "PRIVATE_KEY", "")
        if val:
            return str(val)
    except Exception:  # noqa: BLE001
        pass
    return None


def gen_keypair() -> tuple[str, str]:
    """Ed25519 키쌍을 만들어 (개인키 base64, 공개키 base64)를 반환한다(판매자용).

    `cryptography` 패키지가 필요하다. 개인키 유출 시 누구나 키를 발급할 수
    있으므로 비밀번호 관리자 수준으로 보관할 것.
    """
    if not HAS_ED25519:
        raise RuntimeError(
            "Ed25519에는 cryptography 패키지가 필요합니다: pip install cryptography")
    priv = _EdPriv.generate()
    priv_raw = priv.private_bytes(
        _ser.Encoding.Raw, _ser.PrivateFormat.Raw, _ser.NoEncryption())
    pub_raw = priv.public_key().public_bytes(
        _ser.Encoding.Raw, _ser.PublicFormat.Raw)
    return base64.b64encode(priv_raw).decode(), base64.b64encode(pub_raw).decode()


def generate_key_ed25519(owner: str, private_key: str | None = None) -> str:
    """구매자 식별자를 개인키로 서명한 영구 라이선스 키를 만든다(판매자용).

    HMAC 키와 마찬가지로 만료 정보가 없다(단건 판매·영구). 배포본에는 공개키만
    들어가므로, 이 키는 개인키 없이는 위조할 수 없다(검증 코드 제거는 별개).
    """
    if not HAS_ED25519:
        raise RuntimeError(
            "Ed25519에는 cryptography 패키지가 필요합니다: pip install cryptography")
    pk = _resolve_private_key(private_key)
    if not pk:
        raise RuntimeError(
            "Ed25519 개인키가 없습니다. gen-keypair로 생성한 뒤 "
            f"{_ENV_PRIVKEY} 환경변수로 설정하세요.")
    key = _EdPriv.from_private_bytes(base64.b64decode(pk))
    sig = key.sign(_normalize_owner(owner).encode())
    body = base64.b32encode(sig).decode().rstrip("=")     # base32: 대소문자 무관
    groups = "-".join(body[i:i + 8] for i in range(0, len(body), 8))
    return f"{_PREFIX}-{_ED_MARK}-{groups}"


def _verify_ed25519(owner: str, key: str, public_key: str) -> bool:
    """Ed25519 서명 키를 공개키로 검증한다(형식이 다르거나 실패하면 False)."""
    if not HAS_ED25519:
        return False
    c = _canon(key)
    marker = _PREFIX + _ED_MARK                            # "QUANTED1"
    if not c.startswith(marker):
        return False
    body = c[len(marker):]
    try:
        sig = base64.b32decode(body + "=" * (-len(body) % 8))
        pub = _EdPub.from_public_bytes(base64.b64decode(public_key))
        pub.verify(sig, _normalize_owner(owner).encode())
        return True
    except Exception:  # noqa: BLE001 - 서명 불일치·형식 오류 모두 무효
        return False


def verify_key(owner: str, key: str, secret: str | None = None,
               public_key: str | None = None) -> bool:
    """키가 해당 구매자에게 유효한지 검증한다.

    공개키가 설정돼 있으면 Ed25519 서명을 먼저 확인하고, 아니면(또는 형식이
    다르면) 기존 HMAC 키를 상수시간 비교로 검증한다 — 두 방식 키가 공존 가능.
    """
    pub = _resolve_public_key(public_key)
    if pub and _verify_ed25519(owner, key, pub):
        return True
    try:
        expected = generate_key(owner, secret)
    except RuntimeError:
        return False
    return hmac.compare_digest(_canon(expected), _canon(key))


# ── 자물쇠 지문 — '발급하는 비밀'과 '검증하는 비밀'이 같은지 확인하는 장치 ──
#
# 배경(2026-08-11 감사에서 발견): 키를 발급하는 곳(Cloudflare 시크릿
# LICENSE_SECRET)과 검증하는 곳(빌드에 구워지는 GitHub Secrets
# QUANT_LICENSE_SECRET)은 서로 다른 시스템의 다른 값이다. 둘이 어긋나면
# **발급한 키가 구매자 컴퓨터에서 전부 무효**가 되는데, 그 사실을 알려주는
# 장치가 어디에도 없었다 — 환불 요청이 와야 아는 구조였다.
#
# 지문은 비밀 자체를 노출하지 않으면서 '같은 비밀인가'만 대조하게 해준다.
# 비밀을 역산할 수 없고(HMAC 단방향), 짧게 잘라도 대조 목적에는 충분하다.
_FP_MESSAGE = b"quant-license-fingerprint"
_FP_CHARS = 12


def _fp(material: bytes) -> str:
    return hmac.new(material, _FP_MESSAGE, hashlib.sha256).hexdigest()[:_FP_CHARS]


def secret_fingerprint(secret: str | None = None) -> str | None:
    """HMAC 발급 비밀의 지문(비밀 노출 없음). 비밀이 없으면 None."""
    sec = _resolve_secret(secret)
    return _fp(sec) if sec else None


def pubkey_fingerprint(public_key: str | None = None) -> str | None:
    """Ed25519 공개키의 지문. 공개키가 없으면 None."""
    pub = _resolve_public_key(public_key)
    return _fp(pub.encode()) if pub else None


def lock_fingerprint() -> str | None:
    """지금 이 실행본이 '무엇으로 검증하는가'의 지문 — 없으면 None(자물쇠 없음).

    발급 쪽(어드민 화면)이 보여주는 지문과 이 값이 다르면, 발급한 키는
    이 배포본에서 통과하지 못한다. 판매 전에 반드시 대조할 것.
    """
    pub = pubkey_fingerprint()
    if pub:
        return f"ed25519:{pub}"
    sec = secret_fingerprint()
    return f"hmac:{sec}" if sec else None


def _read_license_file(path: Path) -> tuple[str, str]:
    owner = key = ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "", ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
        elif "=" in line:
            k, _, v = line.partition("=")
        else:
            continue
        k, v = k.strip().lower(), v.strip()
        if k in ("owner", "name", "email"):
            owner = v
        elif k in ("key", "license"):
            key = v
    return owner, key


def load_license(root: str | None = None) -> tuple[str, str]:
    """환경변수 또는 license.key 파일에서 (owner, key)를 읽는다."""
    owner = os.getenv(_ENV_OWNER, "")
    key = os.getenv(_ENV_KEY, "")
    if owner and key:
        return owner, key
    for base in [root, os.getcwd(), str(Path.home())]:
        if not base:
            continue
        fo, fk = _read_license_file(Path(base) / _LICENSE_FILE)
        if fo and fk:
            return fo, fk
    return owner, key


def is_licensed(secret: str | None = None, root: str | None = None) -> bool:
    owner, key = load_license(root)
    return bool(owner and key and verify_key(owner, key, secret))


_ENV_CONTACT = "QUANT_CONTACT"
DEFAULT_CONTACT = "urteam.corp@gmail.com"      # 키 구매·문의 연락처(기본값)


def contact() -> str:
    """구매·문의 연락처 — 환경변수로 바꿀 수 있고 기본값은 판매자 메일."""
    return os.getenv(_ENV_CONTACT, "").strip() or DEFAULT_CONTACT


def _has_baked_credentials() -> bool:
    """배포본에 검증 자물쇠(HMAC 비밀 또는 Ed25519 공개키)가 포함됐는가.

    빌드가 시크릿으로 quant/_license_key.py 또는 quant/_license_pub.py를 구워
    넣으면 True — 이때는 플래그 없이도 자동으로 정품 키를 요구한다.
    (공개 소스 체크아웃에는 이 파일들이 없어(깃 미포함) 강제되지 않는다.)
    """
    return _baked_secret_module() or _baked_pubkey_module()


def _baked_secret_module() -> bool:
    try:
        from quant import _license_key  # type: ignore
        return bool(getattr(_license_key, "SECRET", ""))
    except Exception:  # noqa: BLE001
        return False


def _baked_pubkey_module() -> bool:
    try:
        from quant import _license_pub  # type: ignore
        return bool(getattr(_license_pub, "PUBLIC_KEY", ""))
    except Exception:  # noqa: BLE001
        return False


def prompt_license(root: str | None = None, tries: int = 3) -> bool:
    """터미널에서 키를 직접 입력받아 검증·저장한다(대화형 키 입력창).

    성공하면 license.key 파일로 저장해 다음 실행부터 묻지 않는다.
    비대화형(파이프·서비스)에서는 즉시 False — 조용히 멈추지 않게 한다.
    """
    if not sys.stdin.isatty():
        return False
    print(f"  (구매·문의: {contact()})\n")
    for i in range(tries):
        try:
            owner = input("  구매 시 등록한 이메일: ").strip()
            key = input("  라이선스 키(QUANT-…): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if owner and key and verify_key(owner, key):
            base = Path(root or os.getcwd())
            path = base / _LICENSE_FILE
            try:
                # ⚠️ 라이선스 키는 비밀이다 — 사신 분이 돈을 낸 그 값이다.
                #    예전에는 평범한 write_text로 저장해 0o644가 됐고, 같은
                #    기계의 다른 사용자가 읽어 그대로 쓸 수 있었다(감사 76).
                #    .env의 API 키는 ㊾에서 조여 놓고 정작 파는 물건을
                #    열어 둔 셈이었다.
                from quant.utils.envfile import write_private
                private = write_private(path, f"owner: {owner}\nkey:   {key}\n")
                print(f"\n✅ 정품 확인 완료 — {path} 에 저장했습니다. "
                      "다음 실행부터 묻지 않습니다.")
                if not private:
                    # 확인한 사실만 말한다 — 지키지 못한 약속은 하지 않는다.
                    print("   ⚠️ 이 파일을 '본인만 읽기'로 조이지 못했습니다. 여러 "
                          "사람이 쓰는 기계라면 키가 노출될 수 있습니다"
                          + (" (`chmod 600 %s`)." % path if os.name == "posix"
                             else " (윈도우에서는 보장되지 않습니다)."))
                print()
            except OSError:
                print("\n✅ 정품 확인 완료 (파일 저장은 실패 — 환경변수로 설정하세요)\n")
            return True
        print(f"  ❌ 키가 올바르지 않습니다 ({i + 1}/{tries}) — 이메일과 키를 "
              "구매 안내 메일 그대로 입력하세요.")
    print(f"\n  키를 찾을 수 없나요? 문의: {contact()}\n")
    return False


def require_license(root: str | None = None) -> bool:
    """배포본(자물쇠 포함) 또는 QUANT_REQUIRE_LICENSE 설정 시 정품 키를 강제한다.

    · 강제 조건: 빌드에 검증 자물쇠가 구워져 있거나(자동), 플래그가 켜져 있을 때.
      개발·CI·테스트(자물쇠 없음·플래그 없음)는 그대로 통과 — 지장 없다.
    · 키가 없으면 터미널에서 직접 입력받는다(대화형 키 입력창, 문의 연락처 표시).
      통과 여부를 반환하고 예외를 던지지 않는다.
    """
    enforce = (os.getenv(_ENV_ENFORCE, "").strip().lower()
               in ("1", "true", "yes", "on")) or _has_baked_credentials()
    if not enforce:
        return True
    if is_licensed(root=root):
        return True
    print(
        "\n🔑 라이선스가 필요합니다(정품 확인 — 1인 1키).\n"
        f"  프로그램 폴더에 '{_LICENSE_FILE}' 파일을 만들고 구매 시 받은 값을 넣거나,\n"
        "  아래에 직접 입력하세요:\n"
        "      owner: 구매시_등록한_이메일\n"
        "      key:   QUANT-XXXXXX-XXXXXX-XXXXXX-XXXXXX\n"
        f"  🛒 키 구매·분실 문의: {contact()}\n")
    return prompt_license(root=root)


def _cli(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "help"
    rest = args[1:]

    def opt(*names: str) -> str:
        for name in names:
            for a in rest:
                if a.startswith(name + "="):
                    return a.split("=", 1)[1]
            if name in rest:
                i = rest.index(name)
                if i + 1 < len(rest):
                    return rest[i + 1]
        return ""

    if cmd in ("gen", "generate"):
        owner = opt("--owner", "--email", "--name")
        if not owner:
            print("사용법: python -m quant.licensing gen --owner buyer@email.com")
            return 2
        try:
            # 개인키가 설정돼 있으면 Ed25519(위조 불가) 우선, 아니면 HMAC.
            if HAS_ED25519 and _resolve_private_key():
                key = generate_key_ed25519(owner)
                print("(Ed25519 서명 키 — 배포본에는 공개키가 설정돼 있어야 검증됨)")
            else:
                key = generate_key(owner)
        except RuntimeError as exc:
            print(f"오류: {exc}")
            return 1
        print(f"owner: {owner}\nkey:   {key}")
        return 0

    if cmd in ("gen-keypair", "keypair"):
        try:
            priv, pub = gen_keypair()
        except RuntimeError as exc:
            print(f"오류: {exc}")
            return 1
        print(
            "Ed25519 키쌍이 생성되었습니다.\n\n"
            "① 개인키 — 판매자만 보관(절대 배포·커밋 금지, 유출 시 키 발급 가능):\n"
            f"   export {_ENV_PRIVKEY}='{priv}'\n\n"
            "② 공개키 — 배포본에 포함(공개돼도 안전, 검증만 가능):\n"
            "   quant/_license_pub.py 파일에:\n"
            f"       PUBLIC_KEY = \"{pub}\"\n"
            f"   (또는 환경변수 {_ENV_PUBKEY})\n")
        return 0

    if cmd in ("check", "verify"):
        owner, key = load_license()
        ok = bool(owner and key and verify_key(owner, key))
        print(f"owner={owner or '(없음)'} → {'✅ 유효' if ok else '❌ 무효/없음'}")
        return 0 if ok else 1

    if cmd in ("fingerprint", "fp"):
        fp = lock_fingerprint()
        if not fp:
            print("자물쇠 없음 — 이 실행본은 라이선스를 요구하지 않습니다.")
            return 1
        print(f"lock_fingerprint: {fp}\n"
              "  어드민 키 발급 화면에 표시된 지문과 같아야 합니다.\n"
              "  다르면 발급한 키는 이 배포본에서 통과하지 못합니다.")
        return 0

    print("명령: gen --owner <이메일>   (키 발급, 판매자용 — 개인키 있으면 Ed25519)\n"
          "      gen-keypair            (Ed25519 키쌍 생성, cryptography 필요)\n"
          "      check                  (현재 라이선스 검증)\n"
          "      fingerprint            (이 실행본의 자물쇠 지문 — 발급 쪽과 대조)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
