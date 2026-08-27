"""피처도 **기계가 만든다** — 그리고 그 자동화가 룩어헤드를 들여오지 않는다.

사장님 지시(2026-08-27): *"투자 로직은 머신러닝으로 개선을 계속할 수 있게끔
해야지 수동으로 고치는 방향 말고."*

■ 이 파일이 지키는 것

피처 조합을 기계가 지어내게 하면 탐색 공간이 폭발한다. 그 자체는 의도된
것이지만, **딱 하나 절대 들어오면 안 되는 것**이 있다 — 미래를 보는 식이다.

조합 문법이 미래 값을 한 칸이라도 참조하면 그 피처를 쓴 모델은 백테스트에서
비현실적으로 좋아 보이고, **오디션의 모든 관문을 정당하게 통과한다.** 관문은
성적을 보지 데이터의 출처를 보지 않기 때문이다. 그렇게 뽑힌 챔피언은 실계좌에
나가서야 정체가 드러나고, 그때는 이미 돈이 나간 뒤다.

그래서 룩어헤드 검사를 **규칙 문장이 아니라 행동**으로 잰다: 미래 행을
잘라내도 과거 값이 한 개도 안 바뀌는지를 문법의 **모든 연산자**에 대해 본다.

■ 그리고 정직함

자동화되는 것은 **조합**이지 **재료**가 아니다. 새 외부 데이터(VIX·펀딩비·
수급)를 붙이는 일은 여전히 사람이 한다. "전부 자동입니다"는 이 저장소가 가장
싫어하는 종류의 문장이고, 기록이 그렇게 말하면 다음 사람은 남은 손일을
못 본다.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd

from quant.strategies import derive as D

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text("utf-8")
DATES = pd.date_range("2026-01-01", periods=300, freq="D")


def _feats(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(DATES)
    return pd.DataFrame({
        "rsi14": rng.normal(0.5, 0.15, n),
        "vol": np.abs(rng.normal(0.02, 0.005, n)),
        "atr": np.abs(rng.normal(0.03, 0.008, n)),
        "mom20": rng.normal(0, 0.05, n),
    }, index=DATES)


def _every_op_recipe() -> list[str]:
    """문법의 **모든 연산자**를 한 번씩 쓰는 조합식 목록.

    ⚠️ 손으로 적은 목록이 아니다 — ``OPS``에서 만든다. 연산자를 새로 추가하고
       이 목록을 안 고치면, 그 새 연산자는 룩어헤드 검사를 **한 번도 안 받고**
       운용에 들어간다. 검사가 문법과 함께 자라야 한다.
    """
    out = []
    for op in D.OPS:
        if op in D._BINARY:
            out.append(f"{op}:rsi14:vol")
        elif op in D._UNARY_WINDOW:
            out.append(f"{op}:rsi14:20")
        else:
            out.append(f"{op}:rsi14:3")
    return out


# ── ① 룩어헤드 — 이 파일에서 가장 중요한 검사 ─────────────────────────

def test_no_recipe_can_see_the_future():
    """미래 행을 잘라내도 **과거 값이 하나도 안 바뀐다** — 문법 전체에 대해.

    이 검사가 죽으면 조합 피처는 전부 못 믿는다. 미래를 보는 피처는
    백테스트에서 정직하게 좋아 보이므로, 관문이 아니라 여기서 막아야 한다.
    """
    feats = _feats()
    cut = 200
    for recipe in _every_op_recipe():
        full = D._apply_one(feats, recipe)
        assert full is not None, f"문법이 이 식을 못 만든다: {recipe}"
        part = D._apply_one(feats.iloc[:cut], recipe)
        assert part is not None, f"미래를 자르니 식이 죽는다: {recipe}"
        a = full.iloc[:cut].to_numpy()
        b = part.reindex(full.index[:cut]).to_numpy()
        assert np.allclose(a, b, equal_nan=True), (
            f"'{recipe}'가 미래를 본다 — 미래 {len(feats) - cut}행을 잘랐더니 "
            "과거 값이 바뀌었다. 이 피처를 쓴 모델은 백테스트에서 정직하게 "
            "좋아 보이고 모든 관문을 통과한다")


def test_the_lookahead_check_would_actually_catch_one():
    """대조군 — 위 검사가 **진짜 룩어헤드를 잡을 수 있는가**.

    ⚠️ 룩어헤드 검사는 조용히 무력해지기 쉽다. 비교가 언제나 참이 되는
       모양(둘 다 NaN 등)이면 초록인데 아무것도 안 지킨다. 그래서 미래를
       보는 식을 일부러 만들어, 같은 방법이 그것을 잡아내는지 본다.
    """
    feats = _feats()
    cut = 200
    peek = feats["rsi14"].shift(-3)              # 3봉 **뒤**를 당겨 온다
    a = peek.iloc[:cut].to_numpy()
    b = peek.iloc[:cut + 3].iloc[:cut].to_numpy()
    # 자른 쪽에서는 꼬리 3개가 NaN이 되어야 한다 — 같은 방법으로 잡힌다.
    truncated = feats["rsi14"].iloc[:cut].shift(-3)
    assert not np.allclose(a, truncated.to_numpy(), equal_nan=True), (
        "미래를 보는 식을 넣었는데도 검사 방법이 차이를 못 본다 — "
        "룩어헤드 검사가 무력하다")
    assert np.allclose(a, b, equal_nan=True)     # 방법 자체는 정상 동작


# ── ② 기계가 **만든다** (고르지 않는다) ────────────────────────────────

def test_the_machine_invents_recipes_rather_than_picking_from_a_list():
    """조합식이 사람이 적어 둔 목록에서 나오지 않는다.

    다른 탐색 축은 "미리 적어 둔 값 중에서 고르기"다. 이 축만 **값 자체를
    그 자리에서 만든다** — 손잡이를 돌리는 것이 아니라 손잡이를 만드는 장치다.
    """
    from quant.live.retrain import DEFAULT_CHALLENGERS

    vocab = ["rsi14", "vol", "atr", "mom20", "x_vix"]
    made = set()
    for seed in range(40):
        made.update(D.candidate_recipes(vocab, random.Random(seed), 2))
    assert len(made) > 20, f"지어내는 식이 너무 적다: {len(made)}"
    grid = repr(DEFAULT_CHALLENGERS)
    for recipe in made:
        assert recipe not in grid, (
            f"지어낸 식이 이미 격자에 손으로 적혀 있다: {recipe} — "
            "그러면 '기계가 만든다'가 아니라 '사람이 적어 둔 걸 고른다'다")


def test_the_same_night_reproduces_the_same_recipes():
    """같은 시드 → 같은 식. 재현 검증이 그날의 링을 되살릴 수 있어야 한다.

    조합식은 장부의 설정 안에 문자열로 남지만, 도전자는 매일 밤 시드에서
    **다시 만들어진다**. 생성이 결정적이지 않으면 verify가 "결정 불일치"를
    내고, 그 경보는 조작 의심이라는 **틀린 이름**을 달고 울린다.
    """
    vocab = ["rsi14", "vol", "atr", "mom20"]
    a = D.candidate_recipes(vocab, random.Random("2026-08-27:AAPL"), 5)
    b = D.candidate_recipes(vocab, random.Random("2026-08-27:AAPL"), 5)
    assert a == b, f"같은 시드가 다른 식을 냈다: {a} vs {b}"

    from quant.live.retrain import mutate_champion
    champ = {"strategy": "ml", "params": {"model": "logreg",
                                          "derive": ["x:rsi14:vol"]}}
    assert (mutate_champion(champ, seed="2026-08-27:us_stock:AAPL")
            == mutate_champion(champ, seed="2026-08-27:us_stock:AAPL"))


def test_taking_a_feature_away_is_searched_too():
    """**빼 보기**가 탐색에 들어 있다 — 더하기만 하면 영영 안 떨어진다.

    이 저장소가 탐색 축을 표로 바꿀 때 배운 교훈과 같다: 한번 붙은 설정을
    "빼면 더 낫지 않나"라고 아무도 묻지 않으면, 설정은 무거워지기만 한다.
    """
    vocab = ["rsi14", "vol", "atr", "mom20"]
    cur = ["x:rsi14:vol", "z:atr:20", "d:mom20:3"]
    shrank = any(len(D.mutate_recipes(cur, vocab, random.Random(s))) < len(cur)
                 for s in range(60))
    assert shrank, ("60번을 흔들어도 조합 피처가 한 번도 안 줄었다 — "
                    "더하는 것만 탐색하면 한번 붙은 피처는 영영 안 떨어진다")


def test_the_recipe_list_cannot_grow_without_bound():
    """상한이 실제로 걸린다 — 매일 하나씩 붙어 수십 개짜리 설정이 되지 않는다."""
    vocab = ["rsi14", "vol", "atr", "mom20"]
    cur: list[str] = []
    for s in range(200):
        cur = D.mutate_recipes(cur, vocab, random.Random(s))
        assert len(cur) <= D.MAX_DERIVED, (
            f"조합 피처가 상한({D.MAX_DERIVED})을 넘었다: {len(cur)}개 — "
            "피처가 늘수록 과적합 재료가 늘고, 그 대가는 판정의 신뢰도에서 "
            "지불된다")


def test_recipes_never_stack_on_top_of_recipes():
    """조합 위에 조합을 쌓지 않는다 — 아무도 뜻을 설명 못 하는 피처 방지."""
    vocab = ["rsi14", "vol", "d_x_rsi14_vol", "d_z_atr_20"]
    for s in range(50):
        for recipe in D.candidate_recipes(vocab, random.Random(s), 3):
            spec = D.parse(recipe)
            args = [a for a in spec[1:] if isinstance(a, str)]
            assert not any(a.startswith("d_") for a in args), (
                f"조합으로 만든 열을 다시 조합했다: {recipe} — 식이 무한히 "
                "깊어지고, 깊은 식은 재현은 되지만 뜻을 설명할 수 없다")


# ── ③ 없는 재료를 있는 척하지 않는다 ───────────────────────────────────

def test_a_missing_ingredient_leaves_no_column_at_all():
    """재료가 없으면 열이 **아예 없다** — 0으로 채우지 않는다.

    0으로 채우면 모델은 그 열이 있는 줄 알고 학습하는데 실제로는 상수 하나를
    본다. 이 저장소가 이미 겪은 '죽은 피처' 사고와 같은 모양이다(선언은 fs8인데
    실제로는 컬럼이 안 붙어 있던 몇 주).
    """
    feats = _feats()
    out = D.apply_recipes(feats, ["x:rsi14:x_없는재료", "z:rsi14:20"])
    assert D.column_name("z:rsi14:20") in out.columns, "되는 식까지 빠졌다"
    assert D.column_name("x:rsi14:x_없는재료") not in out.columns, (
        "없는 재료를 쓴 식이 열을 만들었다 — 상수 열이 피처인 척한다")


def test_a_constant_recipe_is_dropped():
    """변하지 않는 열은 피처가 아니다 — 학습에 아무 정보도 안 준다."""
    flat = pd.DataFrame({"a": np.ones(len(DATES)), "b": np.ones(len(DATES))},
                        index=DATES)
    out = D.apply_recipes(flat, ["r:a:b", "x:a:b"])
    assert not [c for c in out.columns if str(c).startswith("d_")], (
        f"상수 열이 피처로 들어갔다: {list(out.columns)}")


# ── ④ 배선 — 실제로 모델까지 가는가 ────────────────────────────────────

def _price_frame(seed: int = 0, n: int = 400) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                      index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1_000.0}, index=idx)


def test_the_invented_feature_actually_reaches_the_model():
    """지어낸 식이 **학습에 실제로 들어간다** — 명세만 남고 안 쓰이지 않는다.

    이 저장소가 반복해서 잡아 온 병이 바로 이것이다: 설정에는 적혀 있는데
    실제 경로에서는 한 번도 안 켜지는 장치(감사 127·313). 대조군을 함께 둔다.
    """
    from quant.strategies.ml import MLStrategy

    df = _price_frame()
    with_d = MLStrategy(model="logreg", derive=["x:rsi14:vol", "z:atr:20"])
    with_d.generate_signals(df)
    made = [c for c in with_d.feature_names_ if str(c).startswith("d_")]
    assert len(made) == 2, f"지어낸 식이 학습 피처에 안 들어갔다: {made}"

    without = MLStrategy(model="logreg")
    without.generate_signals(df)
    assert not [c for c in without.feature_names_ if str(c).startswith("d_")], (
        "요청하지 않았는데 조합 피처가 붙었다 — 대조군이 성립하지 않는다")


def test_the_search_axis_is_wired_into_the_nightly_hill_climb():
    """밤 배치의 언덕오르기가 이 축을 **실제로 흔든다**(존재만이 아니라).

    함수가 있는 것과 오디션이 그것을 부르는 것은 다른 일이다 — 사이징 축이
    목록에 없어 184회 동안 한 번도 안 흔들린 사고가 그 차이다.
    """
    from quant.live.retrain import ml_search_axes, mutate_champion

    assert "derive" in ml_search_axes(), "조합 피처 축이 탐색 목록에 없다"
    champ = {"strategy": "ml", "params": {"model": "logreg",
                                          "threshold": 0.55}}
    seen = []
    for day in range(60):
        for cand in mutate_champion(champ, seed=f"2026-09-{day:02d}:us:AAPL"):
            if cand["params"].get("derive"):
                seen.append(cand["params"]["derive"])
    assert seen, ("60일치 언덕오르기가 조합 피처를 한 번도 안 만들었다 — "
                  "축이 목록에만 있고 실제로는 안 흔들린다")


def test_widening_the_feature_space_does_not_widen_the_trial_count():
    """⚠️ 넓어지는 것은 **공간**이지 **시행 횟수**가 아니다.

    후보를 많이 세울수록 우연히 좋아 보이는 것도 늘어난다. 이 저장소는 그
    대가를 결승 문턱에 반영하는데(시행 수에 로그 비례), 시행 수가 늘면
    문턱도 같이 올라가야 정직하다. 여기서는 **애초에 늘리지 않는다**는 쪽을
    택했고, 그 성질이 깨지면 이 검사가 빨간불을 켠다.
    """
    from quant.live.retrain import mutate_champion

    plain = {"strategy": "ml", "params": {"model": "logreg"}}
    loaded = {"strategy": "ml",
              "params": {"model": "logreg",
                         "derive": ["x:rsi14:vol", "z:atr:20"]}}
    for seed in ("2026-09-01:us:AAPL", "2026-09-02:us:AAPL"):
        assert (len(mutate_champion(plain, seed=seed))
                == len(mutate_champion(loaded, seed=seed))), (
            "조합 피처를 든 챔피언이 더 많은 후보를 만든다 — 탐색을 넓혔는데 "
            "시행 수가 같이 늘면 관문이 그만큼 헐거워진다")


# ── ⑤ 기록의 정직함 ────────────────────────────────────────────────────

def test_the_record_says_what_the_machine_cannot_invent():
    """방침 기록이 **자동화되지 않은 부분**을 감추지 않는다.

    기계가 만드는 것은 **조합**이지 **재료**가 아니다. 새 외부 데이터를 붙이는
    일은 여전히 사람이 한다. 기록이 "피처도 전부 자동"이라고 말하면 다음
    사람은 남은 손일의 크기를 잘못 읽는다.
    """
    assert "derive" in CLAUDE_MD, (
        "조합 피처 축이 생겼는데 CLAUDE.md 방침 기록이 안 따라왔다")
    assert "조합" in CLAUDE_MD and "재료" in CLAUDE_MD, (
        "무엇이 자동화되고 무엇이 아닌지(조합 vs 재료)가 기록에 없다 — "
        "'전부 자동입니다'로 읽힌다")
