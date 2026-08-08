"""Dead man's switch 계약 검사 — '실행되지 않은 실패'를 잡는 감시가 존재한다.

핵심 계약:
  ① 독립 워크플로가 모든 배치·재시도 종료 후(23:30 UTC) 매일 돈다
  ② 잡의 가동이 아니라 '장부 기록 커밋의 존재'를 확인한다(재학습+페이퍼 둘 다)
  ③ 누락 시 디스코드/텔레그램 경보 — 파이썬 의존성 없이 curl만 사용
  ④ 수동 실행(workflow_dispatch)으로 언제든 점검 가능
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
YML = (ROOT / ".github" / "workflows" / "deadman.yml").read_text(encoding="utf-8")


def test_runs_daily_after_all_batches_and_retries():
    assert '"30 23 * * *"' in YML          # 본실행 20:30 + 재시도 22:00 이후
    assert "workflow_dispatch" in YML


def test_checks_ledger_commits_not_job_status():
    assert "야간 재학습 기록" in YML        # 재학습 커밋 존재 확인
    assert "매일 자동 페이퍼 기록" in YML   # 페이퍼 커밋 존재 확인
    assert "26 hours ago" in YML            # 하루 + 재시도 여유 창


def test_alerts_via_discord_and_telegram_with_curl_only():
    assert "DISCORD_WEBHOOK_URL" in YML and "TELEGRAM_BOT_TOKEN" in YML
    assert "curl" in YML
    assert "pip install" not in YML         # 경보 경로는 의존성 0
    assert "if: failure()" in YML


def test_deadman_watches_sns_and_site_freshness():
    """감시 범위 확장 — SNS 콘텐츠 커밋과 배포 사이트 신선도까지 본다."""
    assert "SNS 게시 콘텐츠" in YML
    assert "status.json" in YML and "1 day ago" in YML


def test_daily_paper_sends_external_heartbeat():
    """외부 하트비트 2중화 — 성공 시 HEARTBEAT_URL 핑(미설정 시 무해)."""
    y = (ROOT / ".github" / "workflows" / "daily-paper.yml").read_text(
        encoding="utf-8")
    assert "HEARTBEAT_URL" in y and "if: success()" in y
