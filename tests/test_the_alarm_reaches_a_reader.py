"""경보가 **사람이 읽는 곳**에 닿는가 (감사 336).

2026-10-04~09, dead man's switch가 매일 디스코드로 "재학습 커밋이 없다"고
울렸는데 아무도 안 읽었다(감사 334 정정). 문밖으로 나가는 것과 읽히는 것은
다른 사건이다. 그래서 깃허브 이슈 '경보함'을 하나 더 둔다 — 깃허브는 저장소
주인에게 이슈·멘션을 이메일로 보낸다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.notifications as nt  # noqa: E402

WF = ROOT / ".github" / "workflows"


def _steps(text: str):
    """`- name:` 단위로 자른 스텝 본문."""
    parts = re.split(r"\n\s+- (?:name|uses):", text)
    return parts[1:]


def test_every_failure_alarm_also_opens_the_issue_box():
    missing = []
    for path in sorted(WF.glob("*.yml")):
        for step in _steps(path.read_text("utf-8")):
            if "failure() || cancelled()" not in step or "MSG=" not in step:
                continue
            if "ALERT_GITHUB_TOKEN: ${{ github.token }}" not in step \
                    or "자동매매 경보함" not in step:
                missing.append(path.name)
    assert not missing, f"경보함 배선이 빠진 실패 경보: {missing}"


def test_workflows_that_carry_the_token_may_write_issues():
    bad = [p.name for p in WF.glob("*.yml")
           if "ALERT_GITHUB_TOKEN" in p.read_text("utf-8")
           and "issues: write" not in p.read_text("utf-8")]
    assert not bad, f"issues: write 권한이 없는데 경보함을 쓰려는 워크플로: {bad}"


def test_notifier_comments_on_an_open_box_or_opens_one(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=30):
        calls.append(("GET", url))
        return state["issues"]

    def fake_post(url, headers=None, body=None):
        calls.append(("POST", url, body))
        return {}

    import quant.utils.http as h
    monkeypatch.setattr(h, "get_json", fake_get)
    monkeypatch.setattr(nt, "post_json", fake_post)
    n = nt.GitHubIssueNotifier("tok", "o/r")

    state = {"issues": [{"number": 7, "title": "다른 이슈"}]}
    assert n.send("킬스위치 발동") is True
    assert calls[-1][1].endswith("/repos/o/r/issues")
    assert calls[-1][2]["title"] == n.TITLE
    assert "@o 킬스위치 발동" in calls[-1][2]["body"]

    state = {"issues": [{"number": 9, "title": n.TITLE}]}
    assert n.send("또 발동") is True
    assert calls[-1][1].endswith("/issues/9/comments")
    assert calls[-1][2]["body"] == "@o 또 발동"


def test_failure_is_not_reported_as_delivered(monkeypatch):
    import quant.utils.http as h

    def boom(*a, **k):
        raise RuntimeError("HTTP 403 https://api.github.com/x")

    monkeypatch.setattr(h, "get_json", boom)
    assert nt.GitHubIssueNotifier("tok", "o/r").send("x") is False


def test_notifier_is_wired_when_the_token_is_present(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "SLACK_WEBHOOK_URL", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    m = nt.get_notifier()
    chans = getattr(m, "notifiers", [])
    assert any(isinstance(c, (nt.GitHubIssueNotifier, nt.DeferredNotifier))
               for c in chans)
