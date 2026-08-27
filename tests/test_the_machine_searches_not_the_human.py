"""투자 로직의 개선은 **기계가 찾는다** (2026-08-27 사장님 지시).

사장님: *"투자 로직의 경우에는 머신러닝으로 개선을 계속할 수 있게끔 해야지
너가 수동으로 고치는 방향 말고."*

■ 무엇이 이미 기계의 일인가

판정(누가 이기는가)은 오래전부터 기계가 한다 — 밤마다 오디션이 돌고,
2단계 관문(선발전 → 결승전)을 통과한 후보만 챔피언이 된다. 후보 만들기도
일부는 기계가 한다 — ``mutate_champion()``이 챔피언 주변을 변형해 매일 밤
새 도전자를 세운다(언덕오르기).

■ 그런데 **탐색 축**은 사람이 그린다 — 그리고 그것이 조용히 낡는다

기계는 주어진 축 위에서만 움직인다. 축 목록에 없는 손잡이는 **이길 기회조차
없다.** 실제로 당했다: ``sizing`` 축이 목록에 없던 동안 오디션 184회가 한
번도 그 축을 흔들지 못했고, 그사이 자본의 91%가 현금으로 놀았다. 아무도
"고장"이라고 부르지 않았다 — 검사도, 화면도, 성적도 정상으로 보였다.
**없는 축은 실패로 나타나지 않는다. 그냥 영원히 아무 일도 안 일어난다.**

그래서 이 검사는 **축 목록 자체를 계약으로 본다.** 축이 늘거나 줄면
CLAUDE.md의 방침 기록이 함께 갱신돼야 한다. 문서와 코드가 갈라지면 다음
사람은 "이미 다 자동"이라고 읽고 남은 손일을 못 본다.

■ 그리고 넓힌 만큼 관문이 따라 올라가야 한다

탐색을 넓히면 우연히 좋아 보이는 후보도 함께 늘어난다. 이 저장소는 그 대가를
결승 문턱에 반영한다(``confirm_threshold`` — 최근 시도 수에 로그 비례).
그 연결이 끊기면 자동화는 개선 장치가 아니라 **과최적화 기계**가 된다.
문자열이 아니라 **동작**으로 확인한다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RETRAIN = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text("utf-8")


def _search_axes() -> list[str]:
    """지금 흔들 수 있는 ML 탐색 축 — **함수에게 직접 묻는다.**

    ⚠️ 예전에는 이 목록을 소스에서 정규식으로 긁었다. 그때는 축이
       ``if/elif`` 사슬에 녹아 있어서 그것 말고는 방법이 없었다. 사슬을
       표로 바꾼 이유가 바로 이것이다 — **기계가 자기 탐색 공간을 읽을 수
       있어야** 구멍을 스스로 찾는다. 이제 물어보면 대답한다.
    """
    from quant.live.retrain import ml_search_axes

    return sorted(ml_search_axes())


def test_the_machine_generates_challengers_every_night():
    """후보 만들기가 사람 손에만 있지 않다 — 배선까지 확인한다.

    함수가 존재하는 것과 밤 배치가 그것을 부르는 것은 다른 일이다.
    """
    assert "def mutate_champion(" in RETRAIN, "자동 후보 생성기가 없다"
    assert "challengers += mutate_champion(" in RETRAIN, (
        "생성기가 있지만 오디션이 그것을 쓰지 않는다 — 링에 못 올라간다")


def test_the_policy_record_lists_every_search_axis():
    """CLAUDE.md의 방침 기록이 **실제 탐색 축**과 일치한다.

    이 검사가 지키는 것은 코드가 아니라 **기록의 정직함**이다. 축을 하나
    늘려 놓고 문서를 안 고치면, 다음 사람은 남은 손일의 크기를 잘못 읽는다.
    반대로 축을 지우고 문서를 안 고치면 '이미 탐색 중'이라고 거짓말한다.
    """
    axes = _search_axes()
    assert len(axes) >= 5, f"탐색 축이 이상하게 적다: {axes}"
    missing = [a for a in axes if a not in CLAUDE_MD]
    assert not missing, (
        f"탐색 축이 늘었는데 CLAUDE.md 방침 기록이 안 따라왔다: {missing} — "
        "기록이 실제보다 좁게 말하면 남은 손일을 잘못 읽는다")


def test_widening_the_search_tightens_the_gate():
    """시도가 늘면 결승 문턱이 **실제로** 올라간다 (문자열 아님).

    ⚠️ 대조군이 핵심이다. "보정이 있다"는 문자열은 보정이 **0을 반환해도**
       그대로 초록이다. 값이 실제로 커지는지를 본다.
    """
    from quant.live.retrain import confirm_threshold

    few, many = confirm_threshold(0), confirm_threshold(20_000)
    assert many > few, (
        f"시도가 20,000회로 늘어도 결승 문턱이 그대로다({few} → {many}) — "
        "탐색을 넓히면 그만큼 우연도 늘어나는데 관문이 안 따라 올라간다")
    assert confirm_threshold(50_000) >= confirm_threshold(5_000), (
        "문턱이 시도 수에 대해 단조가 아니다")


def test_the_gate_does_not_run_away_to_infinity():
    """대조군 — 문턱이 상한 없이 오르면 **아무도 승격 못 하는 링**이 된다.

    영원히 안 바뀌는 챔피언은 '보수적'이 아니라 고장이다. 위 검사만 있으면
    "문턱을 무한히 올린다"도 통과한다.
    """
    from quant.live.retrain import CONFIRM_T_CAP, confirm_threshold

    assert confirm_threshold(10_000_000) <= CONFIRM_T_CAP, (
        "결승 문턱에 상한이 없다 — 시도가 쌓이면 링이 영원히 잠긴다")


def test_the_policy_says_which_part_is_still_by_hand():
    """방침 기록이 **아직 사람이 하는 일**을 감추지 않는다.

    "전부 자동입니다"는 이 저장소가 가장 싫어하는 종류의 문장이다.
    지금 손으로 유지되는 것 셋(고정 격자·피처셋·가설 규칙)이 기록에
    이름으로 남아 있어야 한다.
    """
    for hand in ("DEFAULT_CHALLENGERS", "fs1", "가설 우선"):
        assert hand in CLAUDE_MD, (
            f"방침 기록이 아직 손으로 하는 일을 안 적는다: {hand}")
