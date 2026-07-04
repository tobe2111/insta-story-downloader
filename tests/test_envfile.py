""".env 로더/저장 테스트 (순수 stdlib)."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.envfile import load_env_file, parse_env_text, update_env_file


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


def test_roundtrip(tmp_path):
    fp = tmp_path / ".env"
    update_env_file(fp, {"RT_A": "1", "RT_B": "two words"})
    pairs = parse_env_text(fp.read_text(encoding="utf-8"))
    assert pairs["RT_A"] == "1" and pairs["RT_B"] == "two words"


def test_setup_subcommand_registered():
    import quant.cli as cli

    ns = cli.build_parser().parse_args(["setup"])
    assert ns.command == "setup" and callable(ns.func)
