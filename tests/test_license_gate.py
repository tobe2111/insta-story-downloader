"""라이선스 게이트 계약 검사 — 자동 강제·대화형 입력창·연락처·발급 파이프라인.

핵심 계약:
  ① 빌드에 자물쇠(_license_key/_license_pub)가 구워지면 플래그 없이도 강제된다
  ② 자물쇠·플래그가 없으면(개발·CI·공개 소스) 그대로 통과 — 지장 없다
  ③ 키 입력창: 터미널에서 직접 입력받아 검증하고 license.key로 저장한다
  ④ 안내문에 문의 연락처가 항상 보인다(환경변수로 교체 가능)
  ⑤ 빌드 워크플로가 시크릿 설정 시 자물쇠를 굽는다
  ⑥ 어드민 페이지의 브라우저 발급이 파이썬 검증과 같은 키 형식을 쓴다
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant import licensing  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SECRET = "테스트-발급-비밀-1234"


def _bake_secret(monkeypatch):
    """배포 빌드가 quant/_license_key.py를 구운 상태를 흉내 낸다."""
    mod = types.ModuleType("quant._license_key")
    mod.SECRET = SECRET
    monkeypatch.setitem(sys.modules, "quant._license_key", mod)
    monkeypatch.delenv("QUANT_LICENSE_SECRET", raising=False)
    monkeypatch.delenv("QUANT_REQUIRE_LICENSE", raising=False)
    monkeypatch.delenv("QUANT_LICENSE_OWNER", raising=False)
    monkeypatch.delenv("QUANT_LICENSE_KEY", raising=False)


# ── ①② 자동 강제 조건 ─────────────────────────────────────────


def test_baked_secret_enforces_without_flag(tmp_path, monkeypatch, capsys):
    _bake_secret(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.chdir(tmp_path)                    # 홈/CWD의 실제 키 오염 방지
    monkeypatch.setattr(licensing.Path, "home", staticmethod(lambda: tmp_path))
    assert licensing.require_license(root=str(tmp_path)) is False
    assert "라이선스가 필요" in capsys.readouterr().out


def test_no_lock_no_flag_passes(monkeypatch, tmp_path):
    monkeypatch.delenv("QUANT_REQUIRE_LICENSE", raising=False)
    sys.modules.pop("quant._license_key", None)
    sys.modules.pop("quant._license_pub", None)
    assert licensing.require_license(root=str(tmp_path)) is True


def test_baked_secret_accepts_valid_key_file(tmp_path, monkeypatch):
    _bake_secret(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    owner = "buyer@example.com"
    key = licensing.generate_key(owner, secret=SECRET)
    (tmp_path / "license.key").write_text(
        f"owner: {owner}\nkey: {key}\n", encoding="utf-8")
    assert licensing.require_license(root=str(tmp_path)) is True


# ── ③ 대화형 키 입력창 ─────────────────────────────────────────


def test_prompt_accepts_key_and_saves(tmp_path, monkeypatch, capsys):
    _bake_secret(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(licensing.Path, "home", staticmethod(lambda: tmp_path))
    owner = "buyer@example.com"
    key = licensing.generate_key(owner, secret=SECRET)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter([owner, key])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert licensing.require_license(root=str(tmp_path)) is True
    saved = (tmp_path / "license.key").read_text(encoding="utf-8")
    assert owner in saved and key in saved
    # 저장 후에는 입력 없이 통과한다
    monkeypatch.setattr("builtins.input",
                        lambda prompt="": (_ for _ in ()).throw(AssertionError))
    assert licensing.require_license(root=str(tmp_path)) is True


def test_prompt_rejects_wrong_key(tmp_path, monkeypatch, capsys):
    _bake_secret(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(licensing.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    wrong = iter(["a@b.com", "QUANT-WRONG", "a@b.com", "QUANT-WRONG",
                  "a@b.com", "QUANT-WRONG"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(wrong))
    assert licensing.require_license(root=str(tmp_path)) is False
    assert not (tmp_path / "license.key").exists()


# ── ④ 문의 연락처 ──────────────────────────────────────────────


def test_contact_shown_and_overridable(tmp_path, monkeypatch, capsys):
    _bake_secret(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(licensing.Path, "home", staticmethod(lambda: tmp_path))
    licensing.require_license(root=str(tmp_path))
    assert licensing.DEFAULT_CONTACT in capsys.readouterr().out
    monkeypatch.setenv("QUANT_CONTACT", "help@example.com")
    licensing.require_license(root=str(tmp_path))
    assert "help@example.com" in capsys.readouterr().out


# ── ⑤⑥ 발급 파이프라인 구성 ───────────────────────────────────


def test_build_workflow_bakes_lock_from_secrets():
    y = (ROOT / ".github" / "workflows" / "build-app.yml").read_text(
        encoding="utf-8")
    assert "QUANT_LICENSE_SECRET" in y and "_license_key.py" in y
    assert "QUANT_LICENSE_PUBKEY" in y and "_license_pub.py" in y


def test_worker_admin_gate_and_admin_issues_same_key_format():
    w = (ROOT / "worker.js").read_text(encoding="utf-8")
    assert "ADMIN_ID" in w and "WWW-Authenticate" in w
    a = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
    assert "HMAC" in a and "SHA-256" in a and "slice(0,15)" in a
    assert "QUANT_LICENSE_SECRET" in a          # 빌드 시크릿과 같아야 함을 안내
    # 파이썬 쪽 키 형식이 어드민 JS가 만드는 형식과 같다:
    # QUANT- + base32 24자(6자씩 4그룹)
    key = licensing.generate_key("x@y.com", secret=SECRET)
    assert re.fullmatch(r"QUANT-[A-Z2-7]{6}-[A-Z2-7]{6}-[A-Z2-7]{6}-[A-Z2-7]{6}",
                        key)
