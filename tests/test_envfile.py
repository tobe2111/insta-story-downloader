""".env 로더/저장 테스트 (순수 stdlib)."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.envfile import (
    is_private,
    load_env_file,
    parse_env_text,
    update_env_file,
)


def test_parse_basic_quotes_comments():
    text = ('# 주석\n'
            'A=1\n'
            'B="hello world"\n'
            "C='single'\n"
            '\n'
            'BAD LINE\n'
            '=novalue\n'
            'D=va=lue\n')
    p = parse_env_text(text)
    assert p == {"A": "1", "B": "hello world", "C": "single", "D": "va=lue"}


def test_load_does_not_override_shell(tmp_path):
    fp = tmp_path / ".env"
    fp.write_text("TEST_ENVFILE_X=file\nTEST_ENVFILE_Y=file\n", encoding="utf-8")
    os.environ["TEST_ENVFILE_X"] = "shell"
    os.environ.pop("TEST_ENVFILE_Y", None)
    try:
        n = load_env_file(fp)
        assert n == 1                                  # Y만 들어감
        assert os.environ["TEST_ENVFILE_X"] == "shell"  # 셸 값 우선
        assert os.environ["TEST_ENVFILE_Y"] == "file"
    finally:
        os.environ.pop("TEST_ENVFILE_X", None)
        os.environ.pop("TEST_ENVFILE_Y", None)


def test_load_missing_file_returns_zero(tmp_path):
    assert load_env_file(tmp_path / "no_such.env") == 0


def test_update_preserves_comments_and_other_keys(tmp_path):
    fp = tmp_path / ".env"
    fp.write_text("# 내 메모\nKEEP=old\nCHANGE=old\n", encoding="utf-8")
    update_env_file(fp, {"CHANGE": "new", "ADDED": "v", "EMPTY": ""})
    text = fp.read_text(encoding="utf-8")
    assert "# 내 메모" in text and "KEEP=old" in text
    assert "CHANGE=new" in text and "CHANGE=old" not in text
    assert "ADDED=v" in text and "EMPTY" not in text   # 빈 값은 저장 안 함


def test_update_creates_file_with_owner_only_perms(tmp_path):
    fp = tmp_path / ".env"
    update_env_file(fp, {"K": "v"})
    mode = stat.S_IMODE(fp.stat().st_mode)
    assert mode == 0o600                               # 본인만 읽기/쓰기


def test_secret_never_visible_to_others_even_momentarily(tmp_path, monkeypatch):
    """키가 '느슨한 권한으로 쓰였다가 나중에 조여지는' 창(window)이 없어야 한다.

    예전 구현은 write_text(umask대로 0o644) → chmod(0o600) 순서였다. 그
    사이 짧은 순간 같은 기계의 다른 사용자가 API 키를 읽을 수 있었다.
    umask를 일부러 0으로 풀어(0o666이 되도록) 파일이 생성 시점부터
    0o600인지 확인한다.
    """
    if os.name != "posix":
        return
    old = os.umask(0)
    try:
        fp = tmp_path / ".env"
        update_env_file(fp, {"EXCHANGE_SECRET": "s3cr3t"})
        assert stat.S_IMODE(fp.stat().st_mode) == 0o600
    finally:
        os.umask(old)


def test_update_reports_privacy_truthfully(tmp_path):
    """update_env_file은 '조였다고 말하기' 대신 '조여졌는지'를 돌려준다.

    예전에는 chmod 실패를 `except OSError: pass`로 삼킨 뒤, 마법사가
    무조건 "권한 600"이라 출력했다 — 지켜지지 않은 보안 약속이다.
    """
    fp = tmp_path / ".env"
    assert update_env_file(fp, {"K": "v"}) is (os.name == "posix")

    if os.name != "posix":
        return
    # 예전 버전이 남긴 느슨한 파일도 갱신 시 조여진다.
    loose = tmp_path / "loose.env"
    loose.write_text("OLD=1\n", encoding="utf-8")
    os.chmod(loose, 0o644)
    assert is_private(loose) is False
    assert update_env_file(loose, {"NEW": "2"}) is True
    assert stat.S_IMODE(loose.stat().st_mode) == 0o600
    assert "OLD=1" in loose.read_text(encoding="utf-8")   # 기존 키 보존


def test_setup_wizard_does_not_hardcode_permission_claim():
    """마법사 출력이 확인 없이 '권한 600'이라 단언하지 않는지 본다."""
    src = Path(__file__).resolve().parent.parent / "quant" / "cli.py"
    text = src.read_text(encoding="utf-8")
    assert "권한 600, git 미포함" not in text
    assert "private = update_env_file" in text


def test_roundtrip(tmp_path):
    fp = tmp_path / ".env"
    update_env_file(fp, {"RT_A": "1", "RT_B": "two words"})
    pairs = parse_env_text(fp.read_text(encoding="utf-8"))
    assert pairs["RT_A"] == "1" and pairs["RT_B"] == "two words"


def test_setup_subcommand_registered():
    import quant.cli as cli

    ns = cli.build_parser().parse_args(["setup"])
    assert ns.command == "setup" and callable(ns.func)
