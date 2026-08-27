"""언덕오르기가 **헛수고 후보**를 만들지 않는다 (2026-08-27 장부 실측).

■ 무엇이 잘못돼 있었나

밤마다 챔피언 주변을 흔들어 후보 4개를 만든다. 그런데 실측해 보니 그중
**16.8%가 챔피언과 하는 일이 완전히 같았다**(실제 챔피언 × 14일 × 4개 =
2,240개 중 376개).

원인은 한 줄이다. 중복 판정을 **JSON 문자열**로 했다.

    챔피언:  {"model": "logreg", ...}
    후보:    {"model": "logreg", ..., "sample_weight": null}

``sample_weight``의 기본값이 ``None``이라 두 설정은 **하는 일이 같다.**
그런데 글자가 다르니 '새 후보'로 통과했다. ``calibrate: null`` ·
``label: "nextbar"`` · ``sizing: "proba"``도 같은 모양이다 — 전부 축이
"이미 기본 위치인 손잡이를 기본 위치로 돌린" 경우다.

■ 왜 이것이 조용한 손실인가

하루에 흔들 수 있는 손잡이는 **4개뿐**이다. 그중 하나가 매일 아무 일도
안 하면 탐색 예산의 1/6이 사라진다. 그런데 어디에도 빨간불이 안 뜬다 —
오디션은 그것을 '무효 후보'로 정확히 걸러 내고 링에서 뺀다. 즉 **장치는
정상으로 보이고, 없어지는 것은 기회뿐**이다. 이 저장소가 반복해서 잡아
온 종류의 침묵이다.

■ 과거 기록은 고치지 않는다

수정하면 그날의 링 구성이 달라진다. 그래서 장부에 세대(``challenger_version``)
를 남기고, 재현 검증은 **그 기록이 적힌 세대의 규칙으로** 재생한다
(``gate_version``·``select_folds``와 같은 방식). 옛 결정은 옛 세계의
결정이고, 그것을 오늘 규칙으로 다시 재면 재현 검사가 늑대소년이 된다.
"""
from __future__ import annotations

import json

import pytest

from quant.live.retrain import (build_challengers, default_params,
                                mutate_champion, strip_default_params)

CHAMPION = {"strategy": "ml",
            "params": {"model": "logreg", "threshold": 0.55,
                       "train_window": 250, "retrain_every": 20,
                       "label": "triple", "meta": True}}


def _behaviour_key(spec: dict) -> str:
    return json.dumps(strip_default_params(spec), sort_keys=True)


def test_no_challenger_does_exactly_what_the_champion_already_does():
    """흔든 후보 중 챔피언과 **하는 일이 같은** 것이 하나도 없다.

    이 검사가 지키는 것은 성적이 아니라 **탐색 예산**이다. 하루 4개뿐인
    기회를 아무 일도 안 하는 후보가 가져가면, 그만큼 진짜 탐색이 안 된다.
    """
    base = _behaviour_key(CHAMPION)
    wasted, total = 0, 0
    for day in range(1, 31):
        for cand in mutate_champion(CHAMPION, seed=f"2026-09-{day:02d}:us:AAPL"):
            total += 1
            if _behaviour_key(cand) == base:
                wasted += 1
    assert total > 50, f"후보가 너무 적어 검사가 헛돈다: {total}"
    assert wasted == 0, (
        f"{total}개 중 {wasted}개가 챔피언과 하는 일이 같다 "
        f"({100 * wasted / total:.1f}%) — 하루 4개뿐인 탐색 기회를 "
        "아무 일도 안 하는 후보가 가져간다")


def test_the_old_behaviour_is_still_reachable_for_reproducing_old_nights():
    """대조군 겸 재현 보장 — 옛 세대 규칙으로도 만들 수 있다.

    ⚠️ 위 검사만 있으면 "그냥 후보를 안 만든다"도 통과한다. 그리고 더
       중요하게, 과거 기록을 재현하려면 **그때의 링**을 되살릴 수 있어야
       한다. 옛 결정을 오늘 규칙으로 재면 재현 검사가 늑대소년이 된다.
    """
    base = _behaviour_key(CHAMPION)
    differed = wasted_in_old = 0
    for day in range(1, 31):
        seed = f"2026-09-{day:02d}:us:AAPL"
        old = mutate_champion(CHAMPION, seed=seed, strip_defaults=False)
        new = mutate_champion(CHAMPION, seed=seed)
        assert old and new, "후보를 아예 안 만든다"
        differed += old != new
        wasted_in_old += sum(1 for c in old if _behaviour_key(c) == base)
    assert differed, (
        "옛 세대와 새 세대가 30일 내내 같은 링을 만든다 — 세대를 나눈 뜻이 없다")
    assert wasted_in_old, (
        "옛 세대에서도 헛수고 후보가 안 나온다 — 이 검사가 무엇을 고쳤는지 "
        "증명하지 못한다(고친 것이 없거나, 대조가 성립하지 않는다)")


def test_the_ledger_records_which_generation_built_the_ring():
    """장부에 세대가 남고, 재현 검증이 **그것을 따른다**.

    안 남기면 옛 기록을 오늘 규칙으로 재현하게 되고, 결정이 달라진 이유가
    '조작 의심'이라는 **틀린 이름**으로 경보에 실린다.
    """
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "quant" / "live"
           / "retrain.py").read_text("utf-8")
    assert '"challenger_version": 2,' in src, "장부에 세대 표식이 없다"
    verify = src[src.index("def verify_retrain("):]
    call = verify[verify.index("build_challengers("):]
    call = call[:call.index(")\n")]
    assert "challenger_version" in call, (
        "재현 검증이 그날의 도전자 세대를 안 본다 — 옛 결정을 오늘 규칙으로 "
        "재생하면 재현 검사가 늑대소년이 된다")
    assert re.search(r'rec\.get\("challenger_version",\s*1\)', call), (
        "옛 기록(세대 표식이 없던 시절)의 기본값이 v1이 아니다")


def test_defaults_come_from_the_class_not_from_a_hand_written_table():
    """기본값은 **전략 클래스에게 직접 묻는다** — 손으로 적은 표를 안 쓴다.

    표를 두면 생성자 기본값이 바뀔 때 따라가지 않고, 그때부터 '하는 일이
    같은' 판정이 조용히 틀려진다.
    """
    from quant.strategies.ml import MLStrategy

    got = default_params("ml")
    assert got, "ml 전략의 기본값을 못 읽었다"
    import inspect
    sig = inspect.signature(MLStrategy.__init__)
    for name, prm in sig.parameters.items():
        if prm.default is not inspect.Parameter.empty:
            assert got[name] == prm.default, f"기본값이 클래스와 다르다: {name}"


def test_stripping_never_changes_what_a_spec_does():
    """정규화는 **하는 일을 안 바꾼다** — 기본값과 같은 것만 지운다.

    기본값과 **다른** 값을 지우면 그 순간 설정의 뜻이 바뀌고, 장부에 적힌
    것과 실제로 돈 것이 갈라진다.
    """
    spec = {"strategy": "ml",
            "params": {"model": "gb", "threshold": 0.62,
                       "sample_weight": None,          # 기본값 → 지워진다
                       "calibrate": "sigmoid",         # 기본값 아님 → 남는다
                       "top_features": 0,              # 기본값 → 지워진다
                       "meta": True,                   # 기본값 아님 → 남는다
                       "min_train": 50}}               # 기본값 → 지워진다
    out = strip_default_params(spec)["params"]
    for gone in ("sample_weight", "top_features", "min_train"):
        assert gone not in out, f"기본값인데 안 지워졌다: {gone}"
    assert out["calibrate"] == "sigmoid" and out["meta"] is True
    assert out["model"] == "gb" and out["threshold"] == 0.62

    # ⚠️ 기본값과 **같은** 값은 지워져도 하는 일이 안 바뀐다 — 그 사실을
    #    두 설정으로 만든 전략이 같은 신호를 내는지로 확인한다(문자열 아님).
    import numpy as np
    import pandas as pd

    from quant.live.retrain import build_strategy

    idx = pd.date_range("2026-01-01", periods=300, freq="D")
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300))),
                      index=idx)
    df = pd.DataFrame({"open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close,
                       "volume": 1_000.0}, index=idx)
    verbose = {"strategy": "ml",
               "params": {"model": "logreg", "sample_weight": None,
                          "calibrate": None, "sizing": "proba"}}
    lean = strip_default_params(verbose)
    a = build_strategy(verbose).generate_signals(df)
    b = build_strategy(lean).generate_signals(df)
    assert np.allclose(a.to_numpy(), b.to_numpy(), equal_nan=True), (
        "기본값을 지웠더니 신호가 달라졌다 — 정규화가 하는 일을 바꿨다")


def test_an_unknown_strategy_loses_nothing():
    """모르는 전략의 설정은 **한 글자도 안 지운다**.

    래퍼나 사용자 명세는 생성자가 다른 전략을 품고 있어 기본값을 그렇게
    읽을 수 없다. 모를 때 지우는 쪽을 택하면, 사용자가 적어 넣은 값이
    조용히 사라진다 — 되돌릴 수 없는 종류의 실수다.
    """
    spec = {"strategy": "이런전략없음", "params": {"a": 1, "b": None}}
    assert strip_default_params(spec) == spec
    wrapped = {"strategy": "regime_wrap",
               "params": {"inner": CHAMPION, "trend_window": 200}}
    assert strip_default_params(wrapped)["params"]["inner"] == CHAMPION


def test_the_nightly_ring_still_carries_the_same_number_of_mutations():
    """⚠️ 고쳐서 **후보 수가 늘어나면 안 된다** — 그건 관문을 헐겁게 한다.

    헛수고를 없앤 자리에 새 후보가 들어오는 것은 의도한 바다(탐색 예산
    회복). 하지만 **개수 자체가 늘면** 다중검정 부담이 커지고, 그러면
    이득의 일부를 관문 헐거워짐으로 돌려주는 셈이 된다.
    """
    for seed in ("2026-09-01:us:AAPL", "2026-09-02:crypto:BTC/USDT"):
        assert (len(mutate_champion(CHAMPION, seed=seed))
                == len(mutate_champion(CHAMPION, seed=seed,
                                       strip_defaults=False))), (
            "헛수고를 없앴더니 후보 수가 달라졌다 — 다중검정 부담이 바뀐다")


def test_the_ring_builder_passes_the_generation_through():
    """밤 배치가 만드는 링에도 이 규칙이 **실제로 걸린다**(배선 확인)."""
    champ = dict(CHAMPION)
    new = build_challengers(champ, seed="2026-09-01:us:AAPL")
    old = build_challengers(champ, seed="2026-09-01:us:AAPL",
                            strip_defaults=False)
    assert new != old, (
        "링 구성기가 세대를 그냥 흘려보낸다 — 함수에만 있고 밤 배치에는 "
        "안 걸린 것이다")
    base = _behaviour_key(CHAMPION)
    same = [c for c in new
            if c.get("strategy") == "ml" and _behaviour_key(c) == base]
    assert not same, f"링에 챔피언과 하는 일이 같은 후보가 남아 있다: {same}"


@pytest.mark.parametrize("strategy", ["ma_cross", "breakout", "rsi"])
def test_other_strategies_are_not_disturbed(strategy):
    """ML이 아닌 전략의 변형은 **하던 대로** 만들어진다(회귀 방지)."""
    spec = {"strategy": strategy,
            "params": dict(default_params(strategy))}
    spec["params"] = {k: v for k, v in spec["params"].items()
                      if isinstance(v, (int, float))
                      and not isinstance(v, bool)} or {"window": 20}
    got = mutate_champion(spec, seed="2026-09-01:us:AAPL")
    assert got, f"{strategy} 변형이 하나도 안 나온다"
    for cand in got:
        assert cand["strategy"] == strategy
