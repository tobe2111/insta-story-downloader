"""교차 검증의 판정이 **인자 순서에 흔들리지 않는가** (감사 210).

`compare_sources(df_a, df_b)`는 두 데이터 소스가 어긋나는지 본다. 그런데
상대 차이를 `|a-b| / |a|`로 재고 있었다 — **첫 번째 인자를 기준**으로
삼은 것이다. 그래서 같은 두 소스를 순서만 바꿔 넣으면 결론이 뒤집혔다:

    a=100, b=110, tolerance=0.095
      |100-110| / 100 = 0.100   → ok=False   "어긋났다"
      |110-100| / 110 = 0.0909  → ok=True    "괜찮다"

같은 데이터, 다른 결론이다. 이 함수의 존재 이유가 "한 소스만 믿지 않는다"인데,
어느 소스를 먼저 적었는지가 판정을 바꾸면 그 자체가 믿을 수 없는 판정이다.

게다가 분모가 `|a|`라 **a가 0이면 inf**가 됐다. 옛 주석은 "발생 시 inf로
드러나게 두어 오염을 숨기지 않는다"고 적었지만, inf는 `> tolerance`라
'어긋남'으로 처리된다 — 즉 **비교할 수 없는 것을 비교 실패로** 부르고 있었다.
둘은 다르다. 0 vs 5는 진짜로 다른 값이고, 0 vs 0은 비교가 불가능한 것이다.

지금은 `max(|a|,|b|)`로 잰다: 대칭이고, 1을 넘지 않으며, 한쪽이 0이어도
터지지 않는다. 둘 다 0인 봉만 비교 불가로 따로 세고, 그런 봉이 있으면
통과라고 말하지 않는다 — **'검증 못 함'은 '통과'가 아니다.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.crosscheck import compare_sources  # noqa: E402


def _df(vals, start="2026-08-01"):
    idx = pd.date_range(start, periods=len(vals), freq="D")
    return pd.DataFrame({"close": [float(v) for v in vals]}, index=idx)


# ── 순서를 바꿔도 같은 결론 ────────────────────────────────────

def test_the_verdict_does_not_flip_when_the_arguments_swap():
    """이 결함을 정확히 재현하던 숫자."""
    a, b = _df([100.0, 100.0]), _df([110.0, 100.0])
    fwd = compare_sources(a, b, tolerance=0.095)
    rev = compare_sources(b, a, tolerance=0.095)
    assert fwd["ok"] == rev["ok"], (
        f"인자 순서만 바꿨는데 판정이 뒤집혔다 — {fwd['ok']} vs {rev['ok']}")
    assert fwd["max_rel_diff"] == pytest.approx(rev["max_rel_diff"]), (
        "상대 차이 자체가 비대칭이다")
    # 옛 식(|a| 분모)은 이 자리에서 0.100 / 0.0909로 갈라져 판정이 뒤집혔다.
    # 대칭 분모에서는 양쪽 모두 10/110 = 0.0909다.
    assert fwd["max_rel_diff"] == pytest.approx(10 / 110)

    # 그리고 문턱을 그 아래로 내리면 **양쪽 다** 걸려야 한다 — 대칭이라는
    # 말은 "둘 다 통과"가 아니라 "둘이 같은 답"이라는 뜻이다.
    strict_f = compare_sources(a, b, tolerance=0.05)
    strict_r = compare_sources(b, a, tolerance=0.05)
    assert strict_f["ok"] is False and strict_r["ok"] is False


@pytest.mark.parametrize("pair", [
    ([100.0], [110.0]), ([1.0], [3.0]), ([50.0], [49.5]),
    ([0.0], [5.0]), ([7.0], [7.0]), ([1e-9], [1.0]),
])
def test_symmetry_holds_across_many_shapes(pair):
    """한 쌍만 맞추는 것으로는 대칭을 증명하지 못한다."""
    a, b = _df(pair[0]), _df(pair[1])
    fwd, rev = compare_sources(a, b), compare_sources(b, a)
    assert fwd["ok"] == rev["ok"], pair
    assert fwd["n_exceed"] == rev["n_exceed"], pair
    if fwd["max_rel_diff"] == fwd["max_rel_diff"]:      # NaN이 아니면
        assert fwd["max_rel_diff"] == pytest.approx(rev["max_rel_diff"]), pair


# ── 대조군: 멀쩡한 경우까지 막으면 안 된다 ─────────────────────

def test_two_agreeing_sources_still_pass():
    """대칭으로 바꾸느라 '일치'를 '불일치'로 만들면 아무 소용이 없다."""
    a, b = _df([100.0, 200.0, 300.0]), _df([100.05, 200.1, 299.9])
    got = compare_sources(a, b, tolerance=0.01)
    assert got["ok"] is True, got
    assert got["n_exceed"] == 0 and got["n_unverifiable"] == 0


def test_a_real_disagreement_is_still_caught():
    a, b = _df([100.0, 200.0]), _df([100.0, 260.0])
    got = compare_sources(a, b, tolerance=0.01)
    assert got["ok"] is False and got["n_exceed"] == 1


# ── 비교 불가와 비교 실패는 다르다 ────────────────────────────

def test_zero_against_a_price_is_a_real_disagreement():
    """0 vs 5는 비교가 되는 값이다 — 완전히 다르다고 말해야 한다."""
    got = compare_sources(_df([0.0]), _df([5.0]), tolerance=0.01)
    assert got["max_rel_diff"] == pytest.approx(1.0), (
        "예전에는 여기서 inf가 나왔다(분모가 |a|였다)")
    assert got["ok"] is False and got["n_unverifiable"] == 0


def test_zero_against_zero_is_unverifiable_not_a_pass():
    """둘 다 0이면 비교할 수가 없다 — 그것을 '통과'라 부르면 안 된다."""
    got = compare_sources(_df([0.0, 100.0]), _df([0.0, 100.0]), tolerance=0.01)
    assert got["n_unverifiable"] == 1
    assert got["ok"] is False, (
        "비교 못 한 봉이 있는데 통과라고 말한다 — 검증 못 함은 통과가 아니다")


def test_all_matching_prices_without_zeros_do_pass():
    """대조군 — 0이 없으면 완전 일치는 당연히 통과다."""
    got = compare_sources(_df([100.0, 200.0]), _df([100.0, 200.0]))
    assert got["ok"] is True and got["n_unverifiable"] == 0


# ── 겹침이 없으면 통과가 아니다 (기존 계약 유지) ───────────────

def test_no_overlap_is_not_a_pass():
    a = _df([100.0], start="2026-08-01")
    b = _df([100.0], start="2026-09-01")
    got = compare_sources(a, b)
    assert got["n_common"] == 0 and got["ok"] is False


def test_missing_column_is_not_a_pass():
    a = _df([100.0])
    b = pd.DataFrame({"open": [100.0]}, index=a.index)
    assert compare_sources(a, b)["ok"] is False
