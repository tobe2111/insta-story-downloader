"""개선 이력 자동 발행 — "스스로 고친다"의 증거를 홈페이지에 (2026-08-23).

사장님 지시: *"홈페이지에 자동으로 매번 알고리즘 개선해나가는 것도 기록으로
남기는건?"* 지금까지 개선 이력은 내부 문서에만 쌓였다 — 읽는 사람에게는
주장만 있고 기록이 없었다.

설계 원칙: 사람이 따로 적는 일지는 반드시 갈라진다. 그래서 **이미 존재하는
단일 진실(깃 커밋 이력)**에서 자동으로 뽑는다. 개선이 머지되는 순간 기록은
이미 있고, 밤 배치는 사본을 만들 뿐이다.

지켜야 할 약속:
- 자동 배치의 운행 기록([skip 표식 커밋)은 뺀다 — 개선이 아니다.
- **얕은 복제에서는 발행하지 않는다** — 이력의 일부만 보이는 체크아웃에서
  파일을 만들면 "이게 전부"로 읽힌다. 그날은 기존 파일을 그대로 둔다.
- 사람 커밋이 하나도 안 보이면 발행하지 않는다 — 빈 목록이 기존 기록을
  덮으면 "개선이 없었다"로 읽힌다.
- 밤 배치에 배선돼 있고, 실패해도 본 배치를 못 막는다.
- 워크플로 체크아웃이 전체 이력을 받는다(fetch-depth: 0).
- 화면 카드는 파일이 없으면 조용히 숨는다(발행 전 첫 방문자에게 빈 카드
  금지).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting import changelog as CL                 # noqa: E402


def _fake_git(responses: dict):
    """{첫 인자: stdout} — 등록 안 된 호출은 실패(returncode 1)로 돌려준다."""
    def run(cmd, **kw):
        r = mock.Mock()
        key = cmd[1]                     # ["git", "<subcmd>", ...]
        if key in responses:
            r.returncode, r.stdout = 0, responses[key]
        else:
            r.returncode, r.stdout = 1, ""
        return r
    return run


_LOG = ("2026-08-23|가설 우선 방침 1호 — 월말·월초 효과 (#267)\n"
        "2026-08-23|🛡️ 장중 감시 기록 [skip actions]\n"
        "2026-08-22|매일 자동 페이퍼 기록: 2026-08-22 [skip actions]\n"
        "2026-08-22|측정 장치 다섯 (#264)\n")


def test_bot_commits_are_not_improvements():
    with mock.patch.object(subprocess, "run",
                           _fake_git({"rev-parse": "false\n", "log": _LOG})):
        es = CL.collect_entries()
    assert [e["title"] for e in es] == [
        "가설 우선 방침 1호 — 월말·월초 효과 (#267)", "측정 장치 다섯 (#264)"], es
    assert es[0]["date"] == "2026-08-23"


def test_a_shallow_clone_publishes_nothing(tmp_path):
    """이력의 일부만 보이는데 발행하면 그게 전부로 읽힌다."""
    old = tmp_path / "changelog.json"
    old.write_text('{"count": 99}', "utf-8")
    with mock.patch.object(subprocess, "run",
                           _fake_git({"rev-parse": "true\n", "log": _LOG})):
        assert CL.collect_entries() is None
        assert CL.write_changelog(str(tmp_path)) is None
    assert json.loads(old.read_text("utf-8"))["count"] == 99, (
        "얕은 복제인데 기존 파일을 덮었다")


def test_no_git_at_all_publishes_nothing(tmp_path):
    with mock.patch.object(subprocess, "run", _fake_git({})):
        assert CL.write_changelog(str(tmp_path)) is None
    assert not (tmp_path / "changelog.json").exists()


def test_an_all_bot_history_does_not_erase_the_record(tmp_path):
    """사람 커밋이 안 보이는 날 빈 목록으로 덮으면 '개선이 없었다'가 된다."""
    old = tmp_path / "changelog.json"
    old.write_text('{"count": 99}', "utf-8")
    bots = "2026-08-23|🛡️ 장중 감시 기록 [skip actions]\n"
    with mock.patch.object(subprocess, "run",
                           _fake_git({"rev-parse": "false\n", "log": bots})):
        assert CL.write_changelog(str(tmp_path)) is None
    assert json.loads(old.read_text("utf-8"))["count"] == 99


def test_publishing_writes_what_it_saw(tmp_path):
    with mock.patch.object(subprocess, "run",
                           _fake_git({"rev-parse": "false\n", "log": _LOG})):
        p = CL.write_changelog(str(tmp_path))
    assert p and p["count"] == 2 and p["asof"] == "2026-08-23"
    d = json.loads((tmp_path / "changelog.json").read_text("utf-8"))
    assert d["entries"][0]["date"] >= d["entries"][-1]["date"], "최신이 위가 아니다"
    assert "자동" in d["note"], "일지가 아니라 사본임을 안 밝힌다"


def test_the_batch_publishes_it_without_being_hostage():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    i = src.find("write_changelog(")
    assert i > 0, "밤 배치가 개선 이력을 발행하지 않는다"
    assert "except Exception" in src[i:i + 300], (
        "발행 실패가 본 배치를 죽일 수 있다")


def test_the_workflow_fetches_the_whole_history():
    wf = (ROOT / ".github" / "workflows" / "daily-paper.yml").read_text("utf-8")
    assert "fetch-depth: 0" in wf, (
        "체크아웃이 얕다 — 발행기가 매일 밤 조용히 건너뛴다")
    assert "docs/changelog.json" in wf, "발행한 파일을 커밋하지 않는다"


def test_the_card_hides_until_the_file_exists():
    page = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert 'id="changelog"' in page
    i = page.find('id="changelog"')
    assert "display:none" in page[i - 200:i + 200], (
        "발행 전 첫 방문자가 빈 카드를 본다")
    assert 'fetch("changelog.json")' in page, "카드가 발행 파일을 읽지 않는다"
    assert "사람이 따로 적는 일지가 아니라" in page, (
        "이 기록이 자동 사본임을 화면이 안 밝힌다")
