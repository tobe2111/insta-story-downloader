"""**저장된 것만 방송한다** (감사 283).

사장님이 디스코드 화면을 보여 주셨다(2026-08-18).

    07:52  📦 통합 분산 계좌: 자산 999,078 (-0.09%)
    08:23  🔁 챔피언 교체: us_stock:SPY, us_stock:QQQ
    08:23  🚨 [Quant] 'Nightly Retrain' 실패 (2026-08-17)

앞의 둘은 **저장되지 않았다.** 그날 장부는 2026-08-15에 멈춰 있고
`state/champions.json`의 마지막 수정은 08-16이다. 계산은 됐지만 그 뒤
장부 관문이 죽어 커밋이 막혔다(감사 280).

배치 순서가 ①계산 →②알림 →③장부 관문 →④커밋이라, ③에서 죽으면 ②는
이미 나간 뒤였다. 그래서 사장님 폰에는 **일어나지 않은 일**이 사실처럼
남았다. 같은 메시지 아래 실패 경보가 함께 있었지만 사람은 위부터 읽는다.

이 저장소가 반복해서 지켜 온 규칙과 정면으로 어긋난다 — **모르는 것과
아닌 것은 다르다.** "저장될 예정"과 "저장됐다"도 다르다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import notice_queue as NQ  # noqa: E402

WF = ROOT / ".github" / "workflows"

# 장부를 커밋하는 배치들 — 여기서 알림이 먼저 나가면 사고가 반복된다.
LEDGER_JOBS = sorted(p.name for p in WF.glob("*.yml")
                     if "ledger_gate.py" in p.read_text("utf-8"))


@pytest.fixture(autouse=True)
def _queue(tmp_path, monkeypatch):
    monkeypatch.setenv(NQ.ENV_PATH, str(tmp_path / "q.jsonl"))
    monkeypatch.delenv(NQ.ENV_DEFER, raising=False)


# ── ① 대기열 자체 ────────────────────────────────────────────────

def test_there_are_ledger_jobs_to_protect():
    """전제 고정 — 대상이 사라지면 아래 검사가 조용히 전부 통과한다."""
    assert len(LEDGER_JOBS) >= 3, LEDGER_JOBS


def test_it_stages_instead_of_sending_while_deferring(monkeypatch):
    from quant import cli

    sent: list[str] = []
    monkeypatch.setattr(cli, "get_notifier", lambda: None, raising=False)
    monkeypatch.setenv(NQ.ENV_DEFER, "1")
    cli._notify_extra("자산 999,078원")
    assert NQ.pending() == ["자산 999,078원"], NQ.pending()
    assert sent == [], "미루기로 했는데 그대로 보냈다"


def test_without_deferring_it_does_not_touch_the_queue():
    """대조군 — 평소(사람이 손으로 돌릴 때)는 즉시 보내고 쌓지 않는다.

    이게 없으면 "항상 쌓아 두기만 한다"도 통과하고, 그러면 알림이
    영영 안 나간다.
    """
    from quant import cli

    cli._notify_extra("바로 보내는 알림")
    assert NQ.pending() == [], "미루기가 꺼져 있는데 대기열에 쌓았다"


def test_flush_sends_everything_then_clears():
    NQ.stage("가")
    NQ.stage("나")
    got: list[str] = []
    assert NQ.flush(got.append) == 2
    assert got == ["가", "나"], got
    assert NQ.pending() == [], "보낸 뒤에도 대기열이 남았다 — 다음 밤에 또 나간다"


def test_a_dropped_queue_broadcasts_nothing():
    """관문에서 죽은 밤 — 대기열은 버려지고 **아무것도 나가지 않는다.**"""
    NQ.stage("자산 999,078원")
    NQ.discard()
    got: list[str] = []
    assert NQ.flush(got.append) == 0
    assert got == [], f"저장되지 않은 일이 방송됐다: {got}"


def test_a_broken_line_does_not_swallow_the_rest():
    """한 줄이 깨져도 나머지는 나간다 — 조용한 소실을 막는다."""
    NQ.stage("가")
    p = NQ.queue_path()
    p.write_text(p.read_text("utf-8") + "{망가진 줄\n", encoding="utf-8")
    NQ.stage("나")
    assert NQ.pending() == ["가", "나"], NQ.pending()


def test_the_queue_never_lands_in_the_ledger():
    """대기열이 커밋에 섞이면 '저장된 것만 방송한다'가 헷갈린다."""
    import subprocess

    r = subprocess.run(["git", "check-ignore", NQ.DEFAULT_PATH],
                       cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, (
        f"{NQ.DEFAULT_PATH}가 .gitignore에 없다 — 알림 대기열이 장부에 남는다")


# ── ② 배치가 실제로 그렇게 도는가 ────────────────────────────────

@pytest.mark.parametrize("name", LEDGER_JOBS)
def test_the_batch_defers_its_notices(name):
    wf = yaml.safe_load((WF / name).read_text("utf-8"))
    env = {**(wf.get("env") or {})}
    for job in (wf.get("jobs") or {}).values():
        env.update(job.get("env") or {})
    assert str(env.get(NQ.ENV_DEFER, "")).strip() in ("1", "true", "yes", "on"), (
        f"{name}이 알림을 미루지 않는다 — 관문에서 죽어도 숫자가 먼저 나간다")


@pytest.mark.parametrize("name", LEDGER_JOBS)
def test_the_flush_happens_after_the_push(name):
    """보내는 자리가 **푸시 뒤**여야 한다. 앞이면 미룬 의미가 없다.

    ⚠️ 파일 전체에서 글자 위치를 세면 안 된다 — 머리말 주석이 먼저 걸린다.
       이 저장소가 네 번 겪은 함정이라(감사 183·199·204·㊿+㊽) 반사적으로
       **구조를 파싱한다**: 푸시하는 그 단계의 스크립트 안에서 본다.
    """
    wf = yaml.safe_load((WF / name).read_text("utf-8"))
    runs = [str(st.get("run") or "")
            for job in (wf.get("jobs") or {}).values()
            for st in (job.get("steps") or [])]
    step = next((r for r in runs if "git push origin HEAD:main" in r), None)
    assert step, f"{name}: 푸시하는 단계를 못 찾았다 — 검사가 낡았다"
    assert "quant notify --flush" in step, (
        f"{name}이 미뤄 둔 알림을 푸시하는 그 단계에서 안 보낸다 — "
        "쌓기만 하면 알림이 영영 사라진다")
    assert step.index("git push origin HEAD:main") < step.index("quant notify --flush"), (
        f"{name}: 알림 전송이 푸시보다 앞에 있다 — 미룬 의미가 없다")


@pytest.mark.parametrize("name", LEDGER_JOBS)
def test_the_gate_still_runs_before_the_commit(name):
    """전제 고정 — 관문이 커밋 뒤로 밀리면 이 설계 전체가 무의미하다."""
    src = (WF / name).read_text("utf-8")
    assert src.index("scripts/ledger_gate.py") < src.index('git commit -m'), (
        f"{name}: 장부 관문이 커밋보다 뒤에 있다")
