"""선별이 근거 없이 흔들렸다 (감사 165).

`rank_factors`는 후보 종목을 재무 팩터(PER·PBR·ROE)로 교차 비교해 상위
몇 개만 고른다. 여기서 안 뽑힌 종목은 **매매 후보에서 아예 사라진다.**
그 결정이 세 가지 이유로 근거 없이 흔들리고 있었다.

──────────────────────────────────────────────────────────────
① 자료가 없는 것이 '딱 평균'으로 계산됐다

    score = score.add((z * direction).fillna(0.0), fill_value=0.0)
                                     ^^^^^^^^^^^ 결측 → 0 = z점수의 평균

실측(PER·PBR·ROE 3팩터, 후보 4종목):

    완전체_우량 (셋 다 좋음)   뽑힘
    데이터부실  (ROE 하나뿐)   뽑힘   ← 나머지 둘을 '평균'으로 받았다

자료가 부실할수록 극단값 하나로 올라오기 쉬워진다. 팩터를 세 개 보자고
정해 놓고, 실제로는 하나만 보고 뽑는 셈이다.

──────────────────────────────────────────────────────────────
② 잡음 수준의 차이가 만점짜리 신호가 됐다

z-점수는 규모를 지운다. 그래서 종목 간 PER 차이가 **2e-7**이어도
(= 사실상 같은 값) z는 ±1.22로 나온다 — 진짜 신호와 똑같은 세기다.

실측(ROE가 0.05→0.35로 뚜렷한 3종목):

    ROE만 볼 때                       →  C가 압도적
    전부 30.0 근방인 PER 열을 더하면  →  세 종목 점수가 **정확히 0**

의미 없는 열 하나가 진짜 신호를 통째로 지웠다. `std != 0`만 봤기 때문이다
— 0이 아니라고 '차이가 있다'는 뜻은 아니다(감사 159와 같은 질문).

──────────────────────────────────────────────────────────────
③ 동점이면 입력 순서가 종목을 갈랐다

    후보 {X, Y, Z} 순서로 넣으면  →  Z, X 선택
    후보 {Y, X, Z} 순서로 넣으면  →  Z, Y 선택

같은 자료인데 목록에 적은 순서만 바꿔도 다른 종목을 산다(감사 147과 같은
원리). 재현할 수 없는 선택은 검증할 수도 없다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.fundamentals import rank_factors  # noqa: E402
from quant.portfolio import screen_symbols  # noqa: E402

VALUE_QUALITY = {"pe": -1.0, "pb": -1.0, "roe": +1.0}


# ── ① 자료 부실이 상을 받으면 안 된다 ─────────────────────────

SPARSE = {
    "완전체_우량": {"pe": 8.0, "pb": 0.8, "roe": 0.25},
    "완전체_보통": {"pe": 15.0, "pb": 1.5, "roe": 0.10},
    "완전체_나쁨": {"pe": 40.0, "pb": 4.0, "roe": 0.02},
    "데이터부실": {"roe": 0.30},                      # 3팩터 중 1개뿐
}


def test_a_symbol_with_one_factor_does_not_beat_a_documented_one():
    picked = list(rank_factors(SPARSE, VALUE_QUALITY, top_n=2))
    assert "데이터부실" not in picked, (
        f"팩터 3개 중 1개만 있는 종목이 상위 2종목에 들었다: {picked} — "
        "나머지 둘을 '딱 평균'으로 받았기 때문이다")
    assert picked == ["완전체_우량", "완전체_보통"], picked


def test_a_symbol_with_enough_factors_is_still_eligible():
    """대조군 — 조금 빈다고 전부 버리면 후보가 통째로 사라진다."""
    data = dict(SPARSE)
    data["두개있음"] = {"pe": 6.0, "roe": 0.28}        # 3개 중 2개
    picked = list(rank_factors(data, VALUE_QUALITY, top_n=2))
    assert "두개있음" in picked, picked


def test_a_single_factor_request_still_works():
    """대조군 — 팩터를 하나만 달라고 했으면 하나로 판단해야 한다."""
    w = rank_factors({"A": {"roe": 0.3}, "B": {"roe": 0.1}},
                     {"roe": 1.0}, top_n=1)
    assert list(w) == ["A"], w


# ── ② 잡음이 진짜 신호를 지우면 안 된다 ───────────────────────

# ⚠️ 이 자료를 고르는 데 한 번 실패했다. 처음엔 ROE가 고르게 벌어진
#    3종목을 썼는데, 잡음 PER이 ROE를 정확히 상쇄해 점수가 전부 0이 됐는데도
#    **1등은 그대로였다**(1e-8짜리 잔여 오차가 순서를 유지했다). 변이가
#    그대로 통과했다. 피해가 '1등이 바뀌는 것'으로 나타나리라 가정한 것이
#    틀렸다 — 상쇄는 **중간 순위**부터 흔든다.
#
#    그래서 하위 두 종목을 가깝게(0.10 vs 0.11) 두고 상위 2종목을 본다.
NOISE_TRAP = {
    "A": {"roe": 0.10, "pe": 30.0},
    "B": {"roe": 0.11, "pe": 30.0000002},
    "C": {"roe": 0.35, "pe": 30.0000001},
}


def test_the_test_data_is_really_noise():
    """전제 고정 — PER 열이 진짜로 '차이 없음'인가."""
    pes = [r["pe"] for r in NOISE_TRAP.values()]
    spread = max(pes) - min(pes)
    assert 0 < spread < 1e-6, spread
    assert spread / min(pes) < 1e-8, "상대적으로도 무의미해야 한다"


def test_a_meaningless_column_does_not_change_who_gets_bought():
    alone = list(rank_factors(NOISE_TRAP, {"roe": 1.0}, top_n=2))
    with_noise = list(rank_factors(NOISE_TRAP, {"roe": 1.0, "pe": -1.0},
                                   top_n=2))
    assert alone == ["C", "B"], f"전제가 깨졌다 — ROE만 볼 때 상위 2가 {alone}"
    assert with_noise == alone, (
        f"의미 없는 PER 열을 더하니 상위 2종목이 {with_noise}로 바뀐다 — "
        "B가 빠지고 A가 들어온 이유가 2e-7짜리 PER 차이뿐이다")


def test_a_real_second_factor_does_change_the_choice():
    """대조군 — 진짜 차이가 있는 팩터까지 무시하면 스크리너가 눈을 감는다.

    ②의 잡음 PER은 선택을 **안 바꿔야** 하고, 진짜 PER은 **바꿔야** 한다.
    둘 다 확인해야 가드가 '전부 무시'로 도망친 게 아님을 안다.
    """
    data = {
        "A": {"roe": 0.05, "pe": 5.0},      # ROE는 나쁘지만 아주 싸다
        "B": {"roe": 0.20, "pe": 40.0},     # 둘 다 중간
        "C": {"roe": 0.35, "pe": 90.0},     # ROE는 좋지만 아주 비싸다
    }
    assert list(rank_factors(data, {"roe": 1.0}, top_n=1)) == ["C"]
    both = list(rank_factors(data, {"roe": 1.0, "pe": -1.0}, top_n=1))
    assert both != ["C"], "진짜 밸류 차이가 선택에 전혀 반영되지 않는다"
    # 비싼 C와 부실한 A를 둘 다 깎으면 균형 잡힌 B가 남는다
    assert both == ["B"], both


def test_an_identical_column_is_still_ignored():
    """대조군 — 완전히 같은 값(std=0)은 예전부터 제외였다."""
    same = {"A": {"pe": 10.0}, "B": {"pe": 10.0}}
    assert rank_factors(same, {"pe": -1.0}) == {}


# ── ③ 같은 자료면 같은 종목이 나와야 한다 ─────────────────────

TIE = {"X": {"roe": 0.1}, "Y": {"roe": 0.1}, "Z": {"roe": 0.9}}


def test_the_choice_does_not_depend_on_the_input_order():
    forward = list(rank_factors(TIE, {"roe": 1.0}, top_n=2))
    reordered = list(rank_factors(
        {k: TIE[k] for k in ("Y", "X", "Z")}, {"roe": 1.0}, top_n=2))
    assert forward == reordered, (
        f"목록 순서만 바꿨는데 뽑히는 종목이 달라진다: {forward} vs {reordered}")


def test_the_ranking_is_still_by_score_not_by_name():
    """대조군 — 이름순 정렬은 동점을 가를 때만이어야 한다."""
    data = {"ZZZ": {"roe": 0.9}, "AAA": {"roe": 0.1}}
    assert list(rank_factors(data, {"roe": 1.0}, top_n=1)) == ["ZZZ"]


# ── 배분과 배선 ───────────────────────────────────────────────


def test_the_weights_are_a_full_allocation():
    w = rank_factors(SPARSE, VALUE_QUALITY, top_n=2)
    assert sum(w.values()) == pytest.approx(1.0), w
    assert all(v > 0 for v in w.values())


def test_without_top_n_only_positive_scores_are_taken():
    w = rank_factors(SPARSE, VALUE_QUALITY)
    assert w and "완전체_나쁨" not in w, w


def test_the_screener_passes_the_same_judgement_through():
    """배선 — 스크리너를 통과해도 같은 결정이 나오는가."""
    res = screen_symbols(list(SPARSE), factors=VALUE_QUALITY, top_n=2,
                         ratios_fn=lambda s: SPARSE.get(s, {}))
    assert "데이터부실" not in res["selected"], res["selected"]
    assert res["selected"] == list(res["weights"])
    # 자료는 버리지 않고 그대로 돌려줘야 한다 — 왜 안 뽑혔는지 볼 수 있어야 한다
    assert "데이터부실" in res["ratios"]
