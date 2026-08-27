"""탐색 공간이 **스스로 넓어지는가** (2026-08-27 사장님 지시 구현).

사장님: *"머신러닝으로 개선을 계속할 수 있게끔 해야지 너가 수동으로 고치는
방향 말고."*

■ 무엇이 문제였나

언덕오르기(``mutate_champion``)는 주어진 축 위에서만 움직인다. 그 축이
``if/elif`` 사슬에 녹아 있어서, 손잡이를 새로 만들 때마다 사람이 사슬에
가지를 쳐야 했다. 잊으면 그 축은 영원히 탐색되지 않는데 **아무 데도 빨간불이
안 떴다** — 없는 축은 실패로 나타나지 않고 그냥 아무 일도 안 일어난다.

실측(2026-08-27): 살아 있는 ML 챔피언 40종목 중 **6종목**이 그런 손잡이
위에 앉아 있었다(``meta`` 3 · ``pool`` 3). 고정 격자가 한 번 승격시킨 뒤로는
"빼 보면 더 나은가"를 아무도 묻지 않았다.

■ 그래서 무엇을 지키는가

  ① 사람이 격자에 손잡이를 하나 적으면 **그 순간부터 탐색된다**(자동 유도).
  ② 챔피언이 들고 있는 손잡이는 **전부** 탐색 가능해야 한다 — 못 흔드는
     손잡이 위에 앉은 챔피언이 다시 생기면 빨간불.
  ③ 빼 보기가 표본에 있다 — 더하는 것만 탐색하면 한번 붙은 설정은 영영
     안 떨어진다.
  ④ 넓어지는 것은 **공간이지 시행 횟수가 아니다** — 후보 수가 늘면
     다중검정 부담이 늘어 관문이 헛빡빡해진다.
"""
from __future__ import annotations

import json
from pathlib import Path

from quant.live.retrain import (DROP, ML_EXPLICIT_AXES, mutate_champion,
                                ml_search_axes)

ROOT = Path(__file__).resolve().parent.parent

CHAMP = {"strategy": "ml",
         "params": {"model": "gb", "threshold": 0.55, "train_window": 250,
                    "retrain_every": 20, "pool": "universe", "meta": True}}


def test_a_knob_written_into_the_grid_becomes_searchable():
    """격자에 적힌 손잡이는 **사슬에 가지를 안 쳐도** 탐색된다."""
    axes = ml_search_axes()
    for knob in ("pool", "top_features", "label_cost"):
        assert knob in axes, (
            f"격자에 있는 손잡이 {knob!r}를 언덕오르기가 못 흔든다 — "
            "탐색 공간에 없으면 이길 기회조차 없다")
    assert set(ML_EXPLICIT_AXES) <= set(axes), "명시 축이 사라졌다"


def test_no_live_champion_sits_on_an_unsearchable_knob():
    """살아 있는 챔피언이 **못 흔드는 손잡이** 위에 앉아 있지 않다.

    이 검사가 실제 사고를 잡는다. 챔피언은 승격될 때마다 새 손잡이를 얻을
    수 있고(고정 격자가 준다), 그 손잡이의 축이 없으면 그날부터 그 종목의
    탐색은 조용히 좁아진다.
    """
    path = ROOT / "state" / "champions.json"
    if not path.exists():
        return
    champs = json.loads(path.read_text("utf-8"))
    sub = {"label_k", "label_horizon"}      # 라벨 축이 함께 흔드는 종속 손잡이
    stuck = []
    for key, spec in champs.items():
        if spec.get("strategy") != "ml":
            continue
        axes = ml_search_axes(spec.get("params", {}))
        for knob in spec.get("params", {}):
            if knob not in axes and knob not in sub:
                stuck.append(f"{key}: {knob}")
    assert not stuck, (
        "챔피언이 언덕오르기가 못 건드리는 손잡이 위에 앉아 있다 — 그 축은 "
        f"영원히 탐색되지 않는다: {stuck}")


def test_removing_a_knob_is_also_explored():
    """**빼 보기**가 표본에 있다 — 더하기만 탐색하면 설정이 영영 안 떨어진다."""
    axes = ml_search_axes(CHAMP["params"])

    class _Rng:
        def __init__(self): self.seen = []
        def choice(self, opts): self.seen = list(opts); return opts[0]

    rng = _Rng()
    axes["meta"](rng, CHAMP["params"])
    assert DROP in rng.seen, "meta 축의 표본에 '빼 보기'가 없다"


def test_the_champion_really_gets_mutated_on_the_new_axes():
    """대조군 — 축이 **표에 있는 것**과 실제로 흔들리는 것은 다른 일이다."""
    touched = set()
    for d in range(1, 31):
        for cand in mutate_champion(CHAMP, seed=f"2026-09-{d:02d}:x"):
            p = cand["params"]
            for knob in ("pool", "meta"):
                if p.get(knob) != CHAMP["params"][knob]:
                    touched.add(knob)
    assert touched == {"pool", "meta"}, (
        f"30일을 돌려도 새 축이 실제로 안 흔들렸다: 흔든 것 {touched}")


def test_widening_the_space_does_not_widen_the_trial_count():
    """공간을 넓히는 것이 **시행 횟수**를 늘리지 않는다.

    ⚠️ 이 검사가 이 파일의 안전장치다. 후보 수가 늘면 우연히 좋아 보이는
       후보도 늘고, 결승 문턱(``confirm_threshold``)이 시행 수에 반응하므로
       관문이 헛빡빡해진다. 넓히는 것은 **어디를 파는가**이지 **몇 번 파는가**가
       아니다.
    """
    assert len(mutate_champion(CHAMP, seed="2026-08-27:x")) <= 4, (
        "하루 후보 수가 늘었다 — 다중검정 부담이 함께 늘어난다")


def test_the_search_is_still_deterministic():
    """같은 날 재실행하면 같은 후보 — 재현성이 시장 편의보다 앞선다."""
    a = mutate_champion(CHAMP, seed="2026-08-27:us_stock:SPY")
    b = mutate_champion(CHAMP, seed="2026-08-27:us_stock:SPY")
    assert a == b, "같은 씨앗인데 후보가 달라졌다 — verify가 옛 링을 못 되살린다"
    assert a != mutate_champion(CHAMP, seed="2026-08-28:us_stock:SPY"), (
        "날짜가 바뀌어도 같은 후보다 — 탐색이 제자리걸음이다")
