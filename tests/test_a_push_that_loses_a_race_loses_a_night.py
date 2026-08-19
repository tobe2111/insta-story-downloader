"""**경합에 진 push는 그날 밤을 통째로 버린다** (2026-08-19).

⚠️ 실측 사고. 야간 검증이 2026-08-16·17·18 **사흘 연속** 실패했다. 그런데
   검증 자체는 멀쩡히 돌았다 — 20종목을 다 계산하고, 위험 리포트까지 만들고,
   커밋도 했다. 죽은 곳은 마지막 한 줄이었다.

       [main fdcc5ab] 야간 검증 기록: 2026-08-18 [skip actions]
        2 files changed, 219 insertions(+), 9 deletions(-)
        ! [rejected]  main -> main (fetch first)
       ##[error]Process completed with exit code 1.

   장중 감시가 5분마다 main에 커밋을 쌓는다. 그 사이 리모트가 앞서가면
   맨몸 `git push`는 거부된다. 다른 배치들은 전부 `git pull --rebase` 뒤
   재시도하는 고리를 갖고 있었는데, **검증 잡 하나만 없었다.**

   대가가 컸다. 검증이 사흘 못 들어와서 20종목 중 18종목이 '미측정'으로
   남았고, 그 종목들은 매일 자동으로 비중이 절반으로 깎였다. 계좌가 조심스러운
   이유가 '신중해서'가 아니라 **재 볼 장치가 밀려서**였는데, 화면에는 그냥
   '검증 기록이 없습니다'라고만 나왔다.

이 저장소가 스스로 적어 둔 두 문장 그대로다.
  ① 같은 규칙을 두 곳에 나눠 적으면 언젠가 한 곳이 갈라진다.
  ⑭ 고친 결함은 **형제를 찾기 전까지** 고친 게 아니다.

그래서 여기서는 규칙을 한 곳에 못 박는다: **main에 push하는 워크플로는
전부 같은 모양이어야 한다.** 새 워크플로를 만들 때 이 고리를 빠뜨리면
그 PR에서 걸린다 — 사흘 뒤 밤이 아니라.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"


def _push_steps():
    """(워크플로 이름, 단계 이름, 스크립트) — main에 push하는 단계 전부."""
    out = []
    for path in sorted(WF.glob("*.yml")):
        wf = yaml.safe_load(path.read_text("utf-8")) or {}
        for job in (wf.get("jobs") or {}).values():
            for st in (job.get("steps") or []):
                run = str(st.get("run") or "")
                if "git push" in run:
                    out.append((path.name, str(st.get("name") or "?"), run))
    return out


PUSH_STEPS = _push_steps()
IDS = [f"{n}::{s}" for n, s, _ in PUSH_STEPS]


def test_there_are_pushing_workflows_to_protect():
    """전제 고정 — 대상이 사라지면 아래 검사가 조용히 전부 통과한다."""
    assert len(PUSH_STEPS) >= 6, PUSH_STEPS


@pytest.mark.parametrize("name,step,run", PUSH_STEPS, ids=IDS)
def test_it_rebases_before_pushing(name, step, run):
    """맨몸 push는 리모트가 한 발 앞서 있기만 해도 거부된다."""
    assert "git pull --rebase" in run, (
        f"{name} / {step}: 다시 맞춰 보지 않고 그대로 밀어붙인다 — 장중 감시가 "
        "5분마다 커밋을 쌓는 저장소에서는 언젠가 반드시 거부되고, 그날 계산은 "
        "통째로 버려진다(2026-08-16~18 사흘 실측)")
    assert run.index("git pull --rebase") < run.index("git push"), (
        f"{name} / {step}: 맞춰 보기가 push보다 뒤에 있다 — 순서가 뒤집히면 "
        "고리가 있어도 없는 것과 같다")


@pytest.mark.parametrize("name,step,run", PUSH_STEPS, ids=IDS)
def test_it_retries_more_than_once(name, step, run):
    """한 번만 맞춰 보면 그 순간에 또 밀리면 끝이다.

    경합은 드물게 나는 일이 아니라 **자주 나는 일**이다 — 5분 간격 감시와
    야간 배치가 같은 가지를 쓴다.
    """
    assert "for i in 1 2 3 4" in run or "until" in run, (
        f"{name} / {step}: 재시도 고리가 없다 — 한 번 밀리면 그날 기록이 사라진다")
    assert "sleep" in run, (
        f"{name} / {step}: 쉬지 않고 곧바로 다시 민다 — 같은 경합에 그대로 "
        "다시 걸린다")


@pytest.mark.parametrize("name,step,run", PUSH_STEPS, ids=IDS)
def test_a_failed_push_is_loud(name, step, run):
    """조용히 실패하면 '오늘은 쓸 게 없었다'와 구별되지 않는다."""
    tail = run[run.rindex("git push"):]
    # ⚠️ `::error::`만으로는 부족하다. 그건 로그에 빨간 줄을 **찍을 뿐**
    #    잡을 실패시키지 않는다 — 알림도 안 가고 목록에는 초록으로 남는다.
    #    처음 이 검사를 그렇게 느슨하게 썼더니, `exit 1`을 `exit 0`으로
    #    바꾸는 변이를 그대로 통과시켰다(설명은 남아 있고 행동만 사라진
    #    상태 — 이 저장소가 반복해서 걸린 바로 그 함정).
    assert "exit 1" in tail, (
        f"{name} / {step}: 네 번 다 밀려도 잡이 초록으로 끝난다 — 사흘을 "
        "잃고도 아무도 모른다. 빨간 글씨를 찍는 것과 실패로 끝나는 것은 "
        "다른 일이다")
