"""잠든 후보를 빼는 장치가 **실제로 작동한다** (2026-08-27 장부 실측).

■ 붙여 놓고 한 번도 작동한 적이 없었다

감사 297(2026-08-20)이 만든 장치다. 취지는 이렇다 — 스냅샷이 모자라 풀을
못 만드는 후보는 챔피언과 똑같은 신호를 내는데, 그걸 시도 수에 넣으면
다중검정 문턱만 올라가 **진짜로 뒤져서 찾은 결과까지 같이 깎인다.**

그런데 코드가 이랬다:

    p = (c.get("params") or {}) if isinstance(c, dict) else {}
    pool = p.get("pool")

링에는 두 가지 모양이 섞여 있다:

    온전형   {"strategy": "ml", "params": {"model": "gb", "pool": "peers"}}
    덧씌우기 {"model": "gb", "pool": "peers"}          ← params 키가 없다

**이 장치가 지키려던 바로 그 후보들**(고정 격자의 ML 항목)이 덧씌우기형이다.
그래서 ``pool``이 언제나 ``None``으로 읽혔고, 잠든 후보는 **0개**로 나왔다.

■ 장부가 그대로 보여 준다

장치를 붙인 2026-08-20 **이후에도** ``pool="peers"``가 무동작으로 계속
잡혔다:

    2026-08-24  34종목 중 29
    2026-08-25  13종목 중  7
    2026-08-26  32종목 중 30

즉 매일 밤 거의 모든 종목에서 **못 도는 후보가 링에 서서** 시도 수를
부풀리고 백테스트 시간을 썼다. 고장 난 안전장치와 조용한 실패가 서로를
가려 준 전형적인 모양이고, 화면에는 아무 빨간불도 안 떴다.

■ 그래서 이 파일은 **모양이 섞여 있다는 사실 자체**를 검사한다

"덧씌우기형에서도 손잡이를 읽는가"를 한 번 확인하는 것으로는 부족하다.
같은 착각이 다른 장치에서 또 일어날 수 있으므로, 링에 실제로 두 모양이
섞여 있다는 것과 그 둘을 같은 방식으로 해석한다는 것을 함께 못 박는다.
"""
from __future__ import annotations

import json

from quant.live.retrain import (POOL_WAKE_DAYS, _split_sleeping,
                                build_challengers, effective_params)

CHAMPION = {"strategy": "ml",
            "params": {"model": "logreg", "threshold": 0.55}}


def test_a_merge_form_candidate_is_recognised_as_sleeping(tmp_path):
    """덧씌우기형 후보의 ``pool``을 **읽는다** — 이 결함의 재현 검사.

    스냅샷이 하나도 없는 폴더를 주면 ``peers``는 잘 수밖에 없다. 예전
    코드는 이 상황에서도 "잠든 후보 0개"라고 답했다.
    """
    ring = [{"model": "gb", "threshold": 0.55, "pool": "peers"},
            {"model": "gb", "threshold": 0.55}]
    live, asleep = _split_sleeping(ring, str(tmp_path), champion=CHAMPION)
    assert len(asleep) == 1, (
        f"덧씌우기형의 pool을 못 읽는다 — 잠든 후보 {len(asleep)}개 "
        "(이 장치가 지키려던 바로 그 모양이다)")
    assert asleep[0]["pool"] == "peers"
    assert live == [{"model": "gb", "threshold": 0.55}]


def test_the_full_form_still_works(tmp_path):
    """대조군 — 온전형도 여전히 잡힌다(고치면서 반대쪽을 깨지 않았는가)."""
    ring = [{"strategy": "ml", "params": {"model": "gb", "pool": "peers"}},
            {"strategy": "ml", "params": {"model": "gb"}}]
    live, asleep = _split_sleeping(ring, str(tmp_path), champion=CHAMPION)
    assert len(asleep) == 1 and len(live) == 1


def test_a_candidate_that_can_run_is_not_put_to_sleep(tmp_path):
    """대조군 — 돌 수 있으면 **안 재운다**.

    ⚠️ 위 검사들만 있으면 "전부 재운다"도 통과한다. 그러면 링이 통째로
       비고, 그건 관문이 아니라 정전이다.
    """
    ring = [{"model": "gb", "threshold": 0.55},
            {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}},
            {"model": "gb", "pool": [{"x": 1}]}]      # 직접 주입한 풀은 항상 준비됨
    live, asleep = _split_sleeping(ring, str(tmp_path), champion=CHAMPION)
    assert not asleep, f"돌 수 있는 후보를 재웠다: {asleep}"
    assert len(live) == 3


def test_a_pool_inherited_from_the_champion_is_seen_too(tmp_path):
    """챔피언이 든 손잡이도 **덧씌우기형에 얹혀** 실제로 돈다.

    덧씌우기형은 챔피언 파라미터 **위에** 얹힌다. 챔피언이 ``pool``을 들고
    있으면 그 후보도 풀을 쓰게 된다 — 후보 자신에게 그 글자가 없어도.
    후보만 들여다보면 그 사실이 안 보인다.
    """
    champ = {"strategy": "ml",
             "params": {"model": "logreg", "pool": "peers"}}
    ring = [{"threshold": 0.60}]                       # pool을 안 적었다
    live, asleep = _split_sleeping(ring, str(tmp_path), champion=champ)
    assert len(asleep) == 1, (
        "챔피언에서 물려받은 pool을 못 본다 — 후보만 보면 안 보이는 자리다")
    assert not live


def test_the_ring_really_does_mix_both_shapes():
    """링에 **두 모양이 실제로 섞여 있다** — 이 검사의 전제.

    ⚠️ 섞여 있지 않다면 위 검사들은 있지도 않은 상황을 지키는 것이고,
       그건 안전장치가 아니라 장식이다. 전제가 사라지면 빨간불이 뜨게 한다.
    """
    ring = build_challengers(CHAMPION, seed="2026-08-27:us_stock:AAPL",
                             evolve=False)
    merge = [c for c in ring if "strategy" not in c]
    full = [c for c in ring if "strategy" in c]
    assert merge and full, (
        f"링이 한 모양뿐이다(덧씌우기 {len(merge)} · 온전형 {len(full)}) — "
        "이 파일의 검사들이 지키는 상황이 사라졌다")
    assert any(c.get("pool") for c in merge), (
        "덧씌우기형 중에 pool을 든 것이 없다 — 이 결함이 났던 자리가 사라졌다")


def test_the_nightly_batch_passes_the_champion_in():
    """밤 배치가 **챔피언을 함께 넘긴다**(배선 확인).

    함수가 챔피언을 받을 수 있는 것과 밤 배치가 그것을 넘기는 것은 다른
    일이다 — 안 넘기면 물려받은 손잡이는 다시 안 보인다.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "quant" / "live"
           / "retrain.py").read_text("utf-8")
    body = src[src.index("def run_retrain("):]
    call = body[body.index("_split_sleeping("):]
    call = call[:call.index(")\n")]
    assert "champion=" in call, (
        "밤 배치가 잠든 후보 판정에 챔피언을 안 넘긴다 — 챔피언에서 물려받은 "
        "손잡이가 다시 안 보이게 된다")


def test_effective_params_reads_both_shapes():
    """두 모양을 **같은 방식으로** 해석한다 — 착각이 반복되지 않게.

    이 결함의 뿌리는 "링에 한 모양만 있다"는 착각이었다. 해석을 한 함수로
    모아 두면 다음 장치는 그 함수를 쓰기만 하면 된다.
    """
    champ = {"strategy": "ml", "params": {"model": "logreg", "pool": "peers"}}
    assert effective_params({"threshold": 0.6}, champ) == {
        "model": "logreg", "pool": "peers", "threshold": 0.6}
    assert effective_params({"strategy": "ml", "params": {"model": "gb"}},
                            champ) == {"model": "gb"}, (
        "온전형인데 챔피언 값이 섞였다 — 온전형은 그 자체로 완결이다")
    assert effective_params({}, None) == {}
    assert effective_params("전략이 아님") == {}


def test_the_sleeping_threshold_is_still_the_documented_one():
    """문턱이 조용히 바뀌지 않았는지 — 숫자가 바뀌면 기록도 바뀌어야 한다."""
    assert POOL_WAKE_DAYS == 120, (
        f"잠 깨는 문턱이 {POOL_WAKE_DAYS}일로 바뀌었다 — 기록과 함께 바꿀 것")


def test_sleeping_candidates_do_not_inflate_the_trial_count():
    """잠든 후보는 **시도 수에서 빠진다** — 이 장치의 존재 이유다.

    다중검정 문턱은 "얼마나 뒤졌나"에 비례해 올라간다. 못 도는 후보를 시도
    수에 넣으면 문턱만 올라가고, 진짜로 뒤져서 찾은 결과까지 같이 깎인다.
    """
    import tempfile

    ring = [{"model": "gb", "pool": "peers"},
            {"model": "gb", "threshold": 0.6},
            {"model": "rf", "threshold": 0.6}]
    with tempfile.TemporaryDirectory() as empty:
        live, asleep = _split_sleeping(ring, empty, champion=CHAMPION)
    assert len(live) == 2 and len(asleep) == 1
    # 시도 수로 세는 것은 live 쪽이다(호출부 계약: n_cand = len(challengers)).
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "quant" / "live"
           / "retrain.py").read_text("utf-8")
    body = src[src.index("def run_retrain("):]
    i = body.index("_split_sleeping(")
    after = body[i:i + 800]
    assert "n_cand = len(challengers)" in after, (
        "잠든 후보를 가른 뒤에 시도 수를 세지 않는다 — 가른 뜻이 없다")
    assert json.dumps(asleep, ensure_ascii=False)  # 기록 가능한 형태여야 한다
