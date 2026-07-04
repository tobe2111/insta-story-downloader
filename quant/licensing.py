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


def require_license(root: str | None = None) -> bool:
    """QUANT_REQUIRE_LICENSE가 켜졌을 때만 라이선스를 강제한다.

    개발·CI·테스트에서는 기본 비활성(플래그 미설정)이라 아무 지장이 없다.
    배포본에서만 이 플래그를 켜 정품 키를 요구한다. 통과 여부를 반환하고,
    실패 시 구매자에게 보여줄 안내를 출력한다(예외를 던지지 않는다).
    """
    if os.getenv(_ENV_ENFORCE, "").strip().lower() not in ("1", "true", "yes", "on"):
        return True
    if is_licensed(root=root):
        return True
    print(
        "\n🔑 라이선스가 필요합니다(정품 확인).\n"
        f"  프로그램 폴더에 '{_LICENSE_FILE}' 파일을 만들고 구매 시 받은 값을 넣으세요:\n"
        "      owner: 구매시_등록한_이메일\n"
        "      key:   QUANT-XXXXXX-XXXXXX-XXXXXX-XXXXXX\n"
        "  (또는 환경변수 QUANT_LICENSE_OWNER / QUANT_LICENSE_KEY 로 설정)\n")
    return False


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

    print("명령: gen --owner <이메일>   (키 발급, 판매자용 — 개인키 있으면 Ed25519)\n"
          "      gen-keypair            (Ed25519 키쌍 생성, cryptography 필요)\n"
          "      check                  (현재 라이선스 검증)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
