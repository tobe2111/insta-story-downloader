"""모든 워크플로 잡에 매달림 방어가 걸려 있는가 (감사 77).

배경: `ea3695b5`의 PR CI에서 test(3.12)가 **45분을 매달린 뒤** 실패로 끝났다.
같은 커밋의 push 실행은 정상 통과했으니 코드 결함이 아니라 멈춤이었다 —
테스트 단계가 `in_progress`인 채로 잡이 종료됐고 이후 단계는 `pending`이었다.

**그리고 로그가 남지 않아 원인을 끝내 보지 못했다.** 그게 이 검사의 이유다.
`timeout-minutes`가 있으면 GitHub가 깔끔히 끊으면서 로그를 보존한다 — 다음에
또 나면 어느 검사에서 멈췄는지 볼 수 있다.

CI만의 문제가 아니었다. 감사 시점에 **13개 잡 중 11개가 무제한**이었고,
거기에는 8만원을 굴리는 `daily-paper`와 실거래 `kr-live`가 포함돼 있었다.
그 배치가 매달리면 **그날 매매가 조용히 없어진다** — 실패 경보도 안 뜬다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# 실측 기준으로 정한 상한(2026-08-11). 지나치게 크면 방어가 의미를 잃고,
# 지나치게 작으면 정상 실행을 죽인다.
MAX_ALLOWED = 120


def _jobs():
    for f in sorted(WF.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for name, job in (doc.get("jobs") or {}).items():
            yield f.name, name, job


ALL_JOBS = list(_jobs())


def test_there_are_jobs_to_check():
    """검사 대상이 0건이면 아래 검사들이 조용히 전부 통과한다."""
    assert len(ALL_JOBS) >= 10, ALL_JOBS


@pytest.mark.parametrize("wf,name,job",
                         ALL_JOBS, ids=[f"{w}:{n}" for w, n, _ in ALL_JOBS])
def test_every_job_bounds_its_runtime(wf, name, job):
    """새 잡을 만들 때 이 규칙이 빠지는 것을 막는다.

    규칙이 사람 기억에만 있으면 다음 잡에서 또 빠진다 — UTF-8 규칙이 정확히
    그렇게 빠져서 v0.17.0 윈도우 빌드가 깨졌고, 그 교훈을 적은 당일에
    새로 만든 publish 잡에서 내가 또 빠뜨렸다.
    """
    t = job.get("timeout-minutes")
    assert t, f"{wf}:{name} 에 timeout-minutes가 없다 — 매달리면 무제한으로 탄다"
    assert isinstance(t, int) and 0 < t <= MAX_ALLOWED, \
        f"{wf}:{name} 의 timeout-minutes={t} 가 비현실적이다"


def test_the_money_batches_are_bounded_tightly():
    """8만원을 굴리는 배치는 특히 짧게 — 멈춘 채 오래 있으면 안 된다.

    daily-paper 실측: 최근 14회 최대 4.1분(중앙 1.9분).
    """
    tight = {"daily-paper.yml": 45, "kr-live.yml": 45, "deposit.yml": 30}
    seen = set()
    for wf, name, job in ALL_JOBS:
        if wf in tight:
            seen.add(wf)
            assert job["timeout-minutes"] <= tight[wf], \
                f"{wf}:{name} 이 너무 느슨하다 ({job['timeout-minutes']}분)"
    assert seen == set(tight), f"확인하려던 워크플로가 사라졌다: {set(tight) - seen}"


def test_job_timeout_covers_its_longest_step():
    """단계에 걸린 timeout보다 잡의 timeout이 커야 한다.

    반대면 단계가 자기 몫을 다 쓰기도 전에 잡이 죽어, 정상 실행이
    실패로 보고된다.
    """
    for wf, name, job in ALL_JOBS:
        step_max = max((s.get("timeout-minutes") or 0)
                       for s in (job.get("steps") or [{}]))
        if step_max:
            assert job["timeout-minutes"] > step_max, (
                f"{wf}:{name} 잡 {job['timeout-minutes']}분 ≤ "
                f"단계 {step_max}분 — 정상 실행이 죽는다")


# ── 파이프가 실패를 가리지 않는가 (감사 88) ────────────────────
#
# GitHub의 기본 셸은 `bash -e {0}` 로 **pipefail이 없다.** 그래서
# `python ... | tee log.txt` 는 파이프라인의 마지막 명령(tee)의 종료코드를
# 쓰고, 앞 명령이 실패해도 단계가 초록으로 끝난다.
#
# `| tee` 를 쓰는 단계 9곳 중 8곳은 `shell: bash` 를 선언해 안전했는데
# (그러면 GitHub이 `-e -o pipefail` 로 돌린다), **하필 kr-live의 실거래
# 집행 단계 하나만 빠져 있었다** — 실거래가 실패해도 잡이 성공으로 끝났다.

def _piped_steps():
    out = []
    for f in sorted(WF.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        top = ((doc.get("defaults") or {}).get("run") or {}).get("shell")
        for jn, job in (doc.get("jobs") or {}).items():
            jd = ((job.get("defaults") or {}).get("run") or {}).get("shell") or top
            for s in job.get("steps") or []:
                run = str(s.get("run") or "")
                if "| tee" in run or "| head" in run:
                    out.append((f.name, s.get("name") or jn,
                                s.get("shell") or jd, run))
    return out


PIPED = _piped_steps()


def test_there_are_piped_steps_to_check():
    assert PIPED, "파이프 단계를 하나도 못 찾았다 — 아래 검사가 무의미해진다"


@pytest.mark.parametrize("wf,name,shell,run", PIPED,
                         ids=[f"{w}:{n}" for w, n, _s, _r in PIPED])
def test_a_pipe_never_hides_a_failure(wf, name, shell, run):
    """파이프 앞 명령이 실패하면 단계도 실패해야 한다."""
    explicit = "pipefail" in run
    assert shell == "bash" or explicit, (
        f"{wf} / {name}: shell 미선언(기본 `bash -e`)이라 pipefail이 없다 — "
        "파이프 앞 명령이 실패해도 단계가 초록으로 끝난다. "
        "`shell: bash` 를 넣거나 `set -o pipefail` 을 쓸 것")
