"""Dead man's switch 계약 검사 — '실행되지 않은 실패'를 잡는 감시가 존재한다.

핵심 계약:
  ① 독립 워크플로가 모든 배치·재시도 종료 후 매일 돈다
  ② 잡의 가동이 아니라 '장부 기록 커밋의 존재'를 확인한다(재학습+페이퍼 둘 다)
  ③ 누락 시 디스코드/텔레그램 경보 — 파이썬 의존성 없이 curl만 사용
  ④ 수동 실행(workflow_dispatch)으로 언제든 점검 가능
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
YML = (ROOT / ".github" / "workflows" / "deadman.yml").read_text(encoding="utf-8")


def test_runs_daily_after_all_batches_and_retries():
    # ⚠️ 예전에는 여기서 크론 문자열 '"30 23 * * *"'를 그대로 못 박았다.
    #    값을 고정하기만 하고 **그 값이 실제로 통하는지**는 아무도 안 봤다 —
    #    그래서 SNS 항목이 하루짜리 누락을 구조적으로 못 잡는 상태가 살아
    #    있었다(감사 104). 여기서는 '매일 한 번 · 수동 실행 가능'만 보고,
    #    시각과 창이 실제로 맞물리는지는 tests/test_deadman_window.py가
    #    시각 산술로 검사한다.
    import yaml
    wf = yaml.safe_load(YML)
    sched = (wf.get(True) or wf.get("on") or {})["schedule"]
    assert len(sched) == 1, f"감시는 하루 한 번이어야 한다: {sched}"
    assert re.fullmatch(r"\d+ \d+ \* \* \*", sched[0]["cron"]), sched
    assert "workflow_dispatch" in YML


def test_checks_ledger_commits_not_job_status():
    assert "야간 재학습 기록" in YML        # 재학습 커밋 존재 확인
    assert "매일 자동 페이퍼 기록" in YML   # 페이퍼 커밋 존재 확인
    assert "SNS 게시 콘텐츠" in YML         # SNS 콘텐츠 커밋 존재 확인
    # 창 길이도 값을 못 박지 않는다 — 시각과 함께 맞물려야 의미가 있다.
    assert re.search(r'--since="\d+ hours ago"', YML)


def test_alerts_via_discord_and_telegram_with_curl_only():
    assert "DISCORD_WEBHOOK_URL" in YML and "TELEGRAM_BOT_TOKEN" in YML
    assert "curl" in YML
    assert "pip install" not in YML         # 경보 경로는 의존성 0
    assert "if: failure()" in YML


def test_deadman_watches_sns_and_site_freshness():
    """감시 범위 확장 — SNS 콘텐츠 커밋과 배포 사이트 신선도까지 본다."""
    assert "SNS 게시 콘텐츠" in YML


def test_site_check_separates_unreachable_from_stale():
    """접속 실패와 내용 낡음은 원인이 다르다 — 라벨로 구분해 알린다."""
    assert "사이트접속불가" in YML and "사이트반영낡음" in YML


def test_batch_commits_skip_github_but_not_cloudflare():
    """배치 커밋은 '[skip actions]'만 쓴다 — '[skip ci]'는 Cloudflare 배포까지
    건너뛰어, 개발 푸시 없는 날 사이트가 조용히 낡는다(2026-08-10 실제 사고)."""
    for name in ("daily-paper", "nightly-retrain", "social-post",
                 "deposit", "kr-live"):
        y = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text("utf-8")
        for line in y.splitlines():
            if "git commit -m" in line:
                assert "[skip ci]" not in line, f"{name}: [skip ci] 금지"
                assert "[skip actions]" in line, f"{name}: [skip actions] 필요"
    assert "status.json" in YML and "1 day ago" in YML


def test_daily_paper_sends_external_heartbeat():
    """외부 하트비트 2중화 — 성공 시 HEARTBEAT_URL 핑(미설정 시 무해)."""
    y = (ROOT / ".github" / "workflows" / "daily-paper.yml").read_text(
        encoding="utf-8")
    assert "HEARTBEAT_URL" in y and "if: success()" in y


def test_no_pipe_into_grep_under_pipefail():
    """회귀 방지 — pipefail 아래 `| grep -q`는 매치 순간 SIGPIPE 오탐을 낸다.

    2026-08-09 첫 실행 사고: 4개 검사가 전부 '찾았기 때문에 실패' 판정.
    출력을 변수로 받아 히어스트링(<<<)으로 검사해야 한다.
    """
    yml = (ROOT / ".github" / "workflows" / "deadman.yml").read_text(
        encoding="utf-8")
    assert "| grep -q" not in yml
    assert "<<<" in yml                     # 히어스트링 검사 방식 사용
