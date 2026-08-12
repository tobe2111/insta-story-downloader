"""실거래 키가 든 파일을 제자리에서 자르고 있었다 (감사 190).

`quant/utils/envfile.py`는 `.env`를 쓴다 — 바이낸스·KIS·알파카 실거래 키가
들어 있는 파일이다. 보안(0o600, 노출되는 순간 없애기)은 감사 ㊾에서 꼼꼼히
다뤘는데, **쓰기가 실패했을 때**는 아무도 안 봤다.

    fd = os.open(fp, O_WRONLY | O_CREAT | O_TRUNC, 0o600)   # 제자리에서 자른다

대상 파일을 먼저 자르고 그 위에 쓴다. 쓰기가 중간에 실패하면(디스크 가득·
중단) 그 자리에 **빈 파일만 남는다.** 실측:

    원본 .env    BINANCE_KEY=... · KIS_APP_SECRET=...
    쓰기 실패 후  ''                ← 키가 통째로 사라진다

감사 162에서 **캐시**에는 원자적 쓰기(임시 파일 → os.replace)를 넣었다.
정작 실거래 키가 든 파일은 제자리 자르기였다 — 형제를 안 찾은 자리다(⑭).
캐시는 다시 받으면 되지만 API 키는 사장님이 거래소에서 재발급받아야 한다.

곁들여: 원자 교체를 쓰면 **기존 파일 권한 문제도 같이 풀린다.** 예전에는
"이미 있던 파일은 O_CREAT의 mode가 안 먹으니" 뒤에서 chmod로 조였는데,
갈아 끼우는 파일이 처음부터 0o600이라 그 자리가 필요 없어졌다.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.utils.envfile as E  # noqa: E402

KEYS = "BINANCE_KEY=real-live-key\nKIS_APP_SECRET=another-secret\n"


def _boom(*_a, **_k):
    raise OSError(28, "No space left on device")


# ── 실패해도 원본을 잃지 않는가 ───────────────────────────────


def test_a_failed_update_leaves_the_existing_keys_intact(tmp_path, monkeypatch):
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")
    monkeypatch.setattr(E, "_write_private", _boom)
    with pytest.raises(OSError):
        E.update_env_file(fp, {"NEW_KEY": "x"})
    assert fp.read_text(encoding="utf-8") == KEYS, (
        "쓰기가 실패했는데 원본 키가 사라졌다")


def test_a_crash_inside_the_writer_still_leaves_the_original(tmp_path,
                                                             monkeypatch):
    """진짜 위험한 건 '쓰는 도중' 죽는 경우다 — 자르고 나서 실패하는 자리."""
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")

    real_open = os.open

    def _open_then_die(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        os.close(fd)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "open", _open_then_die)
    with pytest.raises(OSError):
        E.write_private(fp, "새 내용")
    monkeypatch.undo()
    assert fp.read_text(encoding="utf-8") == KEYS, (
        "쓰기 도중 죽었는데 원본이 잘렸다 — 제자리에서 자르고 있다")


def test_no_temporary_file_is_left_behind(tmp_path, monkeypatch):
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")
    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        E.write_private(fp, "새 내용")
    monkeypatch.undo()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != ".env"]
    assert leftovers == [], f"임시 파일이 남았다(키가 든 채로): {leftovers}"
    assert fp.read_text(encoding="utf-8") == KEYS


# ── 대조군: 정상 경로가 여전히 옳은가 ─────────────────────────


def test_a_normal_update_keeps_other_keys_and_comments(tmp_path):
    fp = tmp_path / ".env"
    fp.write_text("# 내 메모\nBINANCE_KEY=old\nOTHER=keep\n", encoding="utf-8")
    assert E.update_env_file(fp, {"BINANCE_KEY": "new"}) is True
    got = fp.read_text(encoding="utf-8")
    assert "# 내 메모" in got and "OTHER=keep" in got
    assert "BINANCE_KEY=new" in got and "old" not in got


def test_the_result_is_owner_only_even_if_the_old_file_was_loose(tmp_path):
    """예전 버전이 0o644로 남긴 파일도 교체와 함께 조여져야 한다."""
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")
    os.chmod(fp, 0o644)
    assert E.update_env_file(fp, {"NEW_KEY": "x"}) is True
    assert stat.S_IMODE(os.stat(fp).st_mode) == 0o600, oct(
        stat.S_IMODE(os.stat(fp).st_mode))


def test_a_brand_new_file_is_owner_only_from_the_start(tmp_path):
    fp = tmp_path / "license.key"
    assert E.write_private(fp, "owner: x\nkey: y\n") is True
    assert stat.S_IMODE(os.stat(fp).st_mode) == 0o600


def test_nothing_to_update_does_not_touch_the_file(tmp_path):
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")
    os.chmod(fp, 0o600)
    before = os.stat(fp).st_mtime_ns
    assert E.update_env_file(fp, {"EMPTY": ""}) is True
    assert os.stat(fp).st_mtime_ns == before
    assert fp.read_text(encoding="utf-8") == KEYS


# ── 파서와 정직성 ─────────────────────────────────────────────


def test_the_parser_ignores_comments_and_strips_quotes():
    got = E.parse_env_text(
        '# 주석\n\nA=1\nB="두 겹"\nC=\'홑\'\n나쁜키!=x\n=빈키\nD=\n')
    assert got == {"A": "1", "B": "두 겹", "C": "홑", "D": ""}


def test_the_shell_wins_over_the_file(tmp_path, monkeypatch):
    """셸에서 export한 값이 파일보다 우선한다 — 관례이자 안전장치다."""
    fp = tmp_path / ".env"
    fp.write_text("Q_TEST_ONE=from_file\nQ_TEST_TWO=from_file\n",
                  encoding="utf-8")
    monkeypatch.setenv("Q_TEST_ONE", "from_shell")
    assert E.load_env_file(fp) == 1
    assert os.environ["Q_TEST_ONE"] == "from_shell"
    assert os.environ["Q_TEST_TWO"] == "from_file"


def test_cannot_verify_is_not_reported_as_safe(tmp_path, monkeypatch):
    """윈도우에서는 POSIX 권한이 의미가 없다 — '모른다'를 '안전'으로 반올림하지 않는다."""
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")
    os.chmod(fp, 0o600)
    assert E.is_private(fp) is True
    monkeypatch.setattr(os, "name", "nt")
    assert E.is_private(fp) is False


def test_a_loose_file_is_reported_as_loose(tmp_path):
    fp = tmp_path / ".env"
    fp.write_text(KEYS, encoding="utf-8")
    for mode in (0o644, 0o640, 0o604):
        os.chmod(fp, mode)
        assert E.is_private(fp) is False, oct(mode)
    assert E.is_private(tmp_path / "없는파일") is False
