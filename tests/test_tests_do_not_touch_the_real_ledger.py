"""감사 377 — 검사가 진짜 `state/`·`docs/`를 바꾸면 그 세션이 실패한다."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path, body: str):
    """루트 conftest를 복사한 작은 저장소에서 검사 하나를 돌린다."""
    (tmp_path / "conftest.py").write_text((ROOT / "conftest.py").read_text("utf-8"), "utf-8")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "ledger.json").write_text("{}", "utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "test_x.py").write_text(textwrap.dedent(body), "utf-8")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "test_x.py"], cwd=tmp_path, capture_output=True, text=True)


def test_a_test_that_writes_into_state_fails_the_session(tmp_path):
    r = _run(tmp_path, """
        from pathlib import Path
        def test_writes():
            (Path(__file__).parent / "state" / "prereg_coverage.json").write_text("{}")
    """)
    assert r.returncode != 0, r.stdout
    assert "prereg_coverage.json" in r.stdout and "감사 377" in r.stdout


def test_a_test_that_edits_a_ledger_fails_the_session(tmp_path):
    r = _run(tmp_path, """
        from pathlib import Path
        def test_edits():
            (Path(__file__).parent / "state" / "ledger.json").write_text('{"x": 1}')
    """)
    assert r.returncode != 0 and "ledger.json" in r.stdout


def test_a_clean_test_passes(tmp_path):
    r = _run(tmp_path, """
        def test_ok(tmp_path):
            (tmp_path / "a.json").write_text("{}")
    """)
    assert r.returncode == 0, r.stdout


def test_the_provenance_check_runs_on_a_copy():
    src = (ROOT / "tests" / "test_site_provenance.py").read_text("utf-8")
    assert 'write_docs_status(str(ROOT / "state")' not in src


def test_the_failure_names_the_test_file(tmp_path):
    r = _run(tmp_path, """
        from pathlib import Path
        def test_writes():
            (Path(__file__).parent / "state" / "flag_state.json").write_text("{}")
    """)
    assert r.returncode != 0 and "test_x" in r.stdout and "flag_state.json" in r.stdout


def test_a_file_changed_and_restored_is_not_an_alarm(tmp_path):
    """변이 도구의 부분 실행은 파일을 바꿨다가 되돌린다 — 수정 시각만 바뀐다."""
    r = _run(tmp_path, """
        from pathlib import Path
        def test_touch():
            p = Path(__file__).parent / "state" / "ledger.json"
            old = p.read_text()
            p.write_text("mutated")
            p.write_text(old)
    """)
    assert r.returncode == 0, r.stdout
