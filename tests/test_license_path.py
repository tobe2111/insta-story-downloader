"""라이선스 발급↔검증 경로 계약 검사 — 파는 물건이 안 열리는 사고를 막는다.

배경(2026-08-11 감사): 키를 **발급**하는 비밀(Cloudflare 시크릿
LICENSE_SECRET)과 배포본이 **검증**하는 비밀(GitHub Secrets
QUANT_LICENSE_SECRET)은 서로 다른 시스템의 값이다. 둘이 어긋나면 판매한 키가
구매자 컴퓨터에서 전부 무효인데, 그걸 알려주는 장치가 어디에도 없었다 —
환불 요청이 와야 아는 구조였다. 게다가 빌드는 비밀을 파일로 구워 넣고
"🔒 자물쇠 포함"이라 로그를 찍을 뿐, **정말 물렸는지 확인하지 않았다**
(비밀에 따옴표 하나만 있어도 모듈이 깨져 무잠금 배포본이 나간다).

핵심 계약:
  ① 발급한 키가 검증을 통과한다(같은 비밀일 때) / 다른 비밀이면 실패한다
  ② 지문은 비밀을 노출하지 않으면서 '같은 비밀인가'를 대조할 수 있다
  ③ 파이썬·워커·어드민 세 곳의 알고리즘이 문자 단위로 같다
  ④ 빌드가 자물쇠를 구운 뒤 실제로 물렸는지 확인하고, 왕복까지 검증한다
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant import licensing  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORKER = (ROOT / "worker.js").read_text(encoding="utf-8")
ADMIN = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
BUILD = (ROOT / ".github" / "workflows" / "build-app.yml").read_text(encoding="utf-8")

SEC_A = "secret-alpha-0123456789"
SEC_B = "secret-bravo-9876543210"


# ── ① 발급 ↔ 검증 왕복 ────────────────────────────────────────


def test_issued_key_verifies_with_same_secret():
    key = licensing.generate_key("Buyer@Example.COM ", secret=SEC_A)
    assert licensing.verify_key("buyer@example.com", key, secret=SEC_A)
    # 이메일 대소문자·공백은 정규화된다(구매 안내 메일 그대로 붙여넣어도 통과)
    assert licensing.verify_key(" BUYER@Example.com ", key, secret=SEC_A)


def test_key_fails_when_verifier_has_a_different_secret():
    """이 실패가 조용히 일어나던 것이 감사에서 잡은 사고 시나리오다."""
    key = licensing.generate_key("buyer@example.com", secret=SEC_A)
    assert not licensing.verify_key("buyer@example.com", key, secret=SEC_B)


def test_key_is_bound_to_the_buyer():
    key = licensing.generate_key("a@example.com", secret=SEC_A)
    assert not licensing.verify_key("b@example.com", key, secret=SEC_A)


# ── ② 지문 ────────────────────────────────────────────────────


def test_fingerprint_is_deterministic_and_secret_specific():
    assert licensing.secret_fingerprint(SEC_A) == licensing.secret_fingerprint(SEC_A)
    assert licensing.secret_fingerprint(SEC_A) != licensing.secret_fingerprint(SEC_B)


def test_fingerprint_does_not_leak_the_secret():
    fp = licensing.secret_fingerprint(SEC_A)
    assert len(fp) == 12 and re.fullmatch(r"[0-9a-f]{12}", fp)
    assert SEC_A not in fp


def test_fingerprint_is_none_without_a_lock(monkeypatch):
    monkeypatch.delenv("QUANT_LICENSE_SECRET", raising=False)
    monkeypatch.delenv("QUANT_LICENSE_PUBKEY", raising=False)
    monkeypatch.setattr(licensing, "_baked_secret_module", lambda: False)
    monkeypatch.setattr(licensing, "_baked_pubkey_module", lambda: False)
    monkeypatch.setattr(licensing, "_resolve_secret", lambda s=None: None)
    monkeypatch.setattr(licensing, "_resolve_public_key", lambda p=None: None)
    assert licensing.lock_fingerprint() is None


def test_lock_fingerprint_reports_which_lock(monkeypatch):
    monkeypatch.setattr(licensing, "_resolve_public_key", lambda p=None: None)
    monkeypatch.setattr(licensing, "_resolve_secret", lambda s=None: SEC_A.encode())
    assert licensing.lock_fingerprint().startswith("hmac:")


# ── ③ 세 구현의 알고리즘 일치 ─────────────────────────────────


def test_worker_and_python_share_the_same_fingerprint_message():
    """문구가 갈리면 지문 대조가 항상 '불일치'로 보여 쓸모없어진다."""
    msg = licensing._FP_MESSAGE.decode()
    assert msg in WORKER
    assert msg in ADMIN


def test_worker_and_python_share_the_same_key_shape():
    # 파이썬: 앞 15바이트 → base32 → 6자 그룹
    key = licensing.generate_key("buyer@example.com", secret=SEC_A)
    assert re.fullmatch(r"QUANT(-[A-Z2-7]{6}){4}", key), key
    # 워커·어드민: slice(0,15) + 6자 그룹 정규식
    for src, name in ((WORKER, "worker.js"), (ADMIN, "admin.html")):
        assert "slice(0, 15)" in src or "slice(0,15)" in src, name
        assert "(.{6})(?=.)" in src, name


def test_fingerprint_truncation_matches_across_implementations():
    assert f"slice(0, {licensing._FP_CHARS})" in WORKER
    assert f"slice(0,{licensing._FP_CHARS})" in ADMIN


def test_worker_issues_byte_identical_keys_to_python():
    """소스 문자열 대조가 아니라 **워커 코드를 실제로 실행**해 대조한다.

    발급은 워커(JS)가, 검증은 배포본(파이썬)이 한다. 두 구현이 한 글자라도
    다르면 판 키가 전부 무효다 — 그래서 눈으로 닮았는지가 아니라 결과가
    같은지를 본다. node가 없는 환경에서는 건너뛴다(CI에는 있다).
    """
    import json
    import shutil
    import subprocess

    if not shutil.which("node"):
        import pytest
        pytest.skip("node 없음 — JS/파이썬 대조 생략")
    helper = ROOT / "tests" / "helpers" / "worker_issue_parity.mjs"
    for secret, owner in ((SEC_A, "Buyer@Example.COM"),
                          (SEC_B, " mixed.Case+tag@Domain.co.kr ")):
        out = subprocess.run(
            ["node", str(helper), secret, owner],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        got = json.loads(out.stdout)
        assert got["key"] == licensing.generate_key(owner, secret=secret)
        assert got["fingerprint"] == "hmac:" + licensing.secret_fingerprint(secret)
        # 발급받은 그 키가 실제로 검증을 통과해야 한다(왕복)
        assert licensing.verify_key(owner, got["key"], secret=secret)


def test_admin_shows_the_fingerprint_for_comparison():
    assert "발급 비밀 지문" in ADMIN
    assert "d.fingerprint" in ADMIN          # 서버 발급 응답도 표시
    assert "fingerprint" in WORKER           # 워커가 실제로 내려준다


# ── ④ 빌드가 자물쇠를 '확인'하는가 ────────────────────────────


def test_build_verifies_the_lock_actually_took():
    """구웠다는 로그가 아니라 물렸다는 사실을 확인해야 한다."""
    assert "_has_baked_credentials()" in BUILD
    assert "빌드 중단" in BUILD


def test_build_bakes_with_safe_python_literals():
    """printf로 따옴표 사이에 끼우면 비밀에 \" 하나로 모듈이 깨진다."""
    assert 'printf \'SECRET = "%s"' not in BUILD
    assert "{val!r}" in BUILD


def test_build_runs_an_issue_verify_roundtrip_on_the_artifact():
    assert "왕복" in BUILD
    assert "license_ok=1" in BUILD           # 진짜 키는 통과
    assert "license_ok=0" in BUILD           # 가짜 키는 차단
    assert "license_required=1" in BUILD     # 자물쇠가 요구 상태


def test_smoke_reports_license_state():
    src = (ROOT / "start.py").read_text(encoding="utf-8")
    for marker in ("license_required=", "license_ok=", "lock_fp="):
        assert marker in src, marker


# ── ⑤ 발급 비밀 취급 ──────────────────────────────────────────


def test_admin_does_not_persist_the_master_secret_forever():
    """발급 비밀은 키를 무제한 위조할 수 있는 마스터 값이다."""
    body = ADMIN.split("function localIssue")[1].split("$(\"lic-gen\")")[0]
    assert "localStorage.setItem(\"lic_secret\"" not in ADMIN
    assert "sessionStorage.setItem(\"lic_secret\"" in body


def test_worker_does_not_wildcard_cors_on_admin_endpoints():
    issue = WORKER.split("async function issueKey")[1].split("\n}")[0]
    assert "Access-Control-Allow-Origin" not in issue
    # 공개 시세는 여전히 열려 있어야 한다(사이트 티커바가 쓴다)
    assert "Access-Control-Allow-Origin" in WORKER


# ── 배포판 실거래 잠금이 실제로 막는가 (감사 61) ──────────────
#
# 변이 시험에서 block_live_in_distribution()의 조건을 무력화해도 아무
# 검사가 실패하지 않았다. 이 잠금은 규제·책임 방어선이다 — 판매·배포본에
# 실계좌 주문 경로가 살아 있으면 구매자가 실거래로 돌리다 손실이 났을 때
# "모의였다"는 방어가 성립하지 않는다.


def _fake_dist(monkeypatch, on: bool):
    """quant._dist_build 를 있는 것처럼(또는 없는 것처럼) 만든다."""
    import sys
    import types

    from quant.utils import dist as d
    if on:
        mod = types.ModuleType("quant._dist_build")
        mod.DISTRIBUTION = True
        monkeypatch.setitem(sys.modules, "quant._dist_build", mod)
    else:
        monkeypatch.delitem(sys.modules, "quant._dist_build", raising=False)
    return d


def test_distribution_build_blocks_live_trading(monkeypatch):
    import pytest

    d = _fake_dist(monkeypatch, True)
    assert d.is_distribution_build() is True
    with pytest.raises(SystemExit) as err:
        d.block_live_in_distribution()
    assert "실거래" in str(err.value)


def test_source_install_is_not_blocked(monkeypatch):
    """소스 설치(깃 클론)에서는 아무것도 잠기지 않는다."""
    d = _fake_dist(monkeypatch, False)
    assert d.is_distribution_build() is False
    d.block_live_in_distribution()          # 예외 없이 통과해야 한다


def test_every_live_entrypoint_calls_the_lock():
    """실거래 진입점이 늘어나면 잠금도 함께 걸려야 한다.

    --live/--real 플래그로 실계좌에 붙는 경로를 모아, 각 경로가
    block_live_in_distribution()을 부르는지 확인한다.
    """
    src = (ROOT / "quant" / "cli.py").read_text(encoding="utf-8")
    live_blocks = src.count("block_live_in_distribution()")
    assert live_blocks >= 3, (
        f"실거래 잠금 호출이 {live_blocks}곳뿐이다 — 진입점이 늘었는데 "
        "잠금을 안 건 경로가 있는지 확인하라")
    start = (ROOT / "start.py").read_text(encoding="utf-8")
    assert "block_live_in_distribution()" in start


# ── Ed25519 서명 라이선스 (감사 63) ───────────────────────────
#
# 커버리지로 보니 Ed25519 경로에 테스트가 **하나도** 없었다. 이건 실제로
# 팔 때 쓰는 방식이다 — 배포본에는 공개키만 들어가므로, 구매자가 실행
# 파일을 뜯어봐도 새 키를 만들 수 없다(HMAC은 비밀이 배포본에 구워지므로
# 뜯으면 무한 발급이 가능하다). 그 성질이 깨져 있어도 아무도 몰랐다.


def _keypair():
    import pytest

    from quant import licensing as L
    if not L.HAS_ED25519:
        pytest.skip("cryptography 미설치")
    return L.gen_keypair()


def test_ed25519_roundtrip(monkeypatch):
    from quant import licensing as L

    priv, pub = _keypair()
    key = L.generate_key_ed25519("구매자A", private_key=priv)
    assert key.startswith(f"{L._PREFIX}-{L._ED_MARK}-")
    assert L.verify_key("구매자A", key, public_key=pub) is True


def test_ed25519_key_is_bound_to_the_buyer():
    from quant import licensing as L

    priv, pub = _keypair()
    key = L.generate_key_ed25519("구매자A", private_key=priv)
    assert L.verify_key("구매자B", key, public_key=pub) is False


def test_ed25519_rejects_a_forged_or_corrupted_key():
    from quant import licensing as L

    priv, pub = _keypair()
    key = L.generate_key_ed25519("구매자A", private_key=priv)
    # ⚠️ 마지막 글자는 건드리지 않는다. Ed25519 서명 64바이트=512비트를
    #    base32(5비트/글자)로 담으면 마지막 글자에 무의미한 3비트가 남아,
    #    그 글자만 바꾼 문자열은 **같은 서명의 다른 표기**가 된다(위조가
    #    아니라 별칭). 실제로 처음엔 그걸 결함으로 착각했다.
    mid = len(key) // 2
    flip = key[:mid] + ("A" if key[mid] != "A" else "B") + key[mid + 1:]
    body = key.rsplit("-", 1)[0]
    for bad in (flip,                                            # 가운데 변조
                body + "-AAAAAAAA",                              # 꼬리 교체
                f"{L._PREFIX}-{L._ED_MARK}-XXXXXXXX",            # 형식만 흉내
                ""):
        assert L.verify_key("구매자A", bad, public_key=pub) is False, bad


def test_a_different_public_key_does_not_accept_the_key():
    from quant import licensing as L

    priv, _ = _keypair()
    _, other_pub = _keypair()
    key = L.generate_key_ed25519("구매자A", private_key=priv)
    assert L.verify_key("구매자A", key, public_key=other_pub) is False


def test_the_distribution_cannot_mint_keys_with_only_the_public_key(monkeypatch):
    """Ed25519를 쓰는 이유 그 자체 — 공개키만으로는 발급이 불가능하다.

    이 성질이 깨지면 배포본을 받은 사람이 스스로 라이선스를 찍어낼 수 있고,
    그러면 판매라는 개념이 성립하지 않는다.
    """
    import pytest

    from quant import licensing as L

    priv, pub = _keypair()
    # 배포본이 가진 것: 공개키뿐. 개인키는 어디에도 없다.
    monkeypatch.delenv(L._ENV_PRIVKEY, raising=False)
    monkeypatch.setenv(L._ENV_PUBKEY, pub)
    monkeypatch.setattr(L, "_resolve_private_key", lambda private_key=None: None)
    with pytest.raises(RuntimeError, match="개인키"):
        L.generate_key_ed25519("무단발급", private_key=None)
    del priv


def test_ed25519_is_preferred_over_hmac_when_a_public_key_exists(monkeypatch):
    """공개키가 설정돼 있으면 Ed25519 키가 HMAC 비밀 없이도 통과한다."""
    from quant import licensing as L

    priv, pub = _keypair()
    key = L.generate_key_ed25519("구매자A", private_key=priv)
    monkeypatch.delenv("QUANT_LICENSE_SECRET", raising=False)
    monkeypatch.setattr(L, "_resolve_secret", lambda secret=None: None)
    assert L.verify_key("구매자A", key, public_key=pub) is True
    # 반대로 HMAC 키는 비밀이 없으면 검증할 수 없다(조용히 통과하면 안 된다)
    assert L.verify_key("구매자A", "QUANT-AAAA-BBBB-CCCC", public_key=pub) is False
