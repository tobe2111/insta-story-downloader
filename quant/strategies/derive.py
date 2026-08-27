"""피처를 **기계가 만든다** — 있는 재료를 조합해 새 피처를 짓는 작은 문법.

사장님 지시(2026-08-27): *"투자 로직은 머신러닝으로 개선을 계속할 수 있게끔
해야지 수동으로 고치는 방향 말고."* 그 방침을 피처에 적용한 것이다.

■ 무엇이 사람 손에 남아 있었나

피처 묶음 ``fs1``~``fs8``은 **새 묶음이 생길 때마다 사람이 손으로 적었다.**
그래서 새 재료를 붙이는 속도가 사람이 앉아 있는 시간에 묶여 있었다.

■ 무엇을 자동화하고, 무엇은 못 하는가 (정직하게)

자동화되는 것은 **조합**이지 **재료**가 아니다.

- ⭕ **조합** — 이미 df에 있는 열을 서로 곱하고, 나누고, 표준화하고,
  늦추는 것. 이건 규칙이라 기계가 만들 수 있다.
- ❌ **재료** — VIX·펀딩비·외국인 수급 같은 **새 외부 데이터**. 기계는
  세상에 없는 데이터를 상상해 낼 수 없다. 새 소스를 붙이는 일은 여전히
  사람이 한다(그리고 그 사실을 CLAUDE.md에 계속 적어 둔다).

"전부 자동입니다"는 이 저장소가 가장 싫어하는 종류의 문장이다.

■ ⚠️ 문법이 **인과적**이어야 한다 — 룩어헤드가 여기로 들어오면 끝이다

조합 문법이 미래 값을 한 칸이라도 참조하면, 그 피처를 쓴 모델은 백테스트에서
비현실적으로 좋아 보이고 **오디션의 모든 관문을 정당하게 통과한다.** 관문은
성적을 보지 데이터의 출처를 보지 않기 때문이다.

그래서 여기 있는 모든 연산은 ``shift``·``rolling``·``diff``처럼 **그 봉까지의
정보만** 쓴다. 그리고 검사가 그것을 규칙이 아니라 **행동**으로 확인한다:
미래 행을 잘라내도 과거 값이 한 개도 안 바뀌는지 문법 전체에 대해 잰다.

■ ⚠️ 넓히는 것은 공짜가 아니다

조합의 가짓수는 열 개수의 제곱으로 늘어난다. 후보를 많이 세울수록 우연히
좋아 보이는 것도 늘어나므로, **하루에 세우는 후보 수는 늘리지 않는다** —
넓어지는 것은 탐색 공간이지 시행 횟수가 아니다(축을 표로 바꿀 때와 같은
원칙). 그리고 한 설정이 들고 갈 수 있는 조합 피처 수에도 상한을 둔다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 한 설정이 들고 갈 수 있는 조합 피처의 최대 개수.
# ⚠️ 상한이 없으면 언덕오르기가 매일 하나씩 붙여 수십 개짜리 설정이 된다.
#    피처가 늘수록 과적합 재료가 늘고, 그 대가는 성적이 아니라 **판정의
#    신뢰도**에서 지불된다(이미 top_features 가지치기를 만든 이유가 그것이다).
MAX_DERIVED = 6

# 조합에 쓸 창 길이 — 짧은 것(주 단위)부터 긴 것(분기 단위)까지.
_WINDOWS = (10, 20, 60)
_LAGS = (1, 3, 5)

# 문법의 연산자. 값은 (인자 개수, 창 인자를 받는가).
#   z  : 이동 표준화(z-점수) — 수준이 아니라 '평소보다 얼마나 특이한가'
#   rk : 이동 백분위 순위 — z와 달리 극단값에 안 휘둘린다
#   d  : k봉 차분 — 수준이 아니라 변화
#   lag: k봉 전 값 — 반응이 늦게 오는 재료를 맞춰 준다
#   r  : 두 열의 비 — 스케일을 지운 상대 크기
#   x  : 두 열의 곱 — 상호작용(선형 모델이 스스로 못 만드는 것)
_UNARY_WINDOW = ("z", "rk")
_UNARY_LAG = ("d", "lag")
_BINARY = ("r", "x")
OPS = _UNARY_WINDOW + _UNARY_LAG + _BINARY


def parse(recipe: str) -> tuple | None:
    """조합식 문자열을 (연산자, 인자...)로 푼다. 모양이 틀리면 None."""
    parts = str(recipe).split(":")
    if len(parts) != 3:
        return None
    op, a, b = parts
    if op in _UNARY_WINDOW or op in _UNARY_LAG:
        try:
            return (op, a, int(b))
        except ValueError:
            return None
    if op in _BINARY:
        return (op, a, b)
    return None


def column_name(recipe: str) -> str:
    """조합 피처의 열 이름 — 조합식 그 자체를 이름으로 쓴다.

    ⚠️ 이름을 따로 짓지 않는 이유: 이름과 식이 갈라지면 장부만 보고
       "그날 모델이 무엇을 봤는가"를 되짚을 수 없다. 이름이 곧 명세다.
    """
    return "d_" + str(recipe).replace(":", "_").replace("/", "")


def _apply_one(feats: pd.DataFrame, recipe: str) -> pd.Series | None:
    """조합식 하나를 계산한다. 재료가 없거나 뜻이 없으면 None(조용히 뺀다).

    ⚠️ 재료가 없을 때 **0으로 채우지 않는다.** 그러면 모델은 그 열이 있는
       줄 알고 학습하는데 실제로는 상수 하나를 본다 — 이 저장소가 이미 겪은
       '죽은 피처' 사고와 같은 모양이다. 없으면 아예 없어야 하고, 그날 실제로
       붙은 열은 장부의 features_used에 그대로 남는다.
    """
    spec = parse(recipe)
    if spec is None:
        return None
    op = spec[0]
    if op in _BINARY:
        _, a, b = spec
        if a not in feats.columns or b not in feats.columns or a == b:
            return None
        sa = pd.to_numeric(feats[a], errors="coerce")
        sb = pd.to_numeric(feats[b], errors="coerce")
        out = (sa * sb) if op == "x" else (sa / sb.replace(0.0, np.nan))
    else:
        _, a, k = spec
        if a not in feats.columns or k <= 0:
            return None
        sa = pd.to_numeric(feats[a], errors="coerce")
        if op == "lag":
            out = sa.shift(k)
        elif op == "d":
            out = sa.diff(k)
        elif op == "z":
            mu = sa.rolling(k).mean()
            sd = sa.rolling(k).std()
            out = (sa - mu) / sd.replace(0.0, np.nan)
        else:                                    # rk — 이동 백분위 순위
            out = sa.rolling(k).apply(
                lambda w: float((w[:-1] < w[-1]).mean()) if len(w) > 1 else
                np.nan, raw=True)
    out = out.replace([np.inf, -np.inf], np.nan)
    # 뜻이 없는 열은 뺀다: 전부 결측이거나, 변하지 않는 상수.
    valid = out.dropna()
    if len(valid) < 30 or float(valid.std()) <= 0:
        return None
    return out


def apply_recipes(feats: pd.DataFrame, recipes) -> pd.DataFrame:
    """피처 행렬에 조합 피처를 덧붙인다 — 계산 가능한 것만.

    상한(``MAX_DERIVED``)을 넘는 조합식은 **앞에서부터** 잘린다. 조용히
    자르지 않으려면 자른 사실이 보여야 하는데, 여기서는 장부의
    features_used(그날 실제로 붙은 열)가 그 역할을 한다.
    """
    if not recipes:
        return feats
    out = feats
    added = 0
    for recipe in list(recipes)[:MAX_DERIVED]:
        col = column_name(recipe)
        if col in out.columns:
            continue
        series = _apply_one(feats, recipe)
        if series is None:
            continue
        if out is feats:
            out = feats.copy()
        out[col] = series
        added += 1
    return out


def candidate_recipes(columns, rng, n: int = 1) -> list[str]:
    """있는 열에서 **새 조합식을 지어낸다** — 기계가 손잡이를 만드는 자리.

    ``rng``는 ``random.Random``이다(오디션의 언덕오르기가 쓰는 것). 날짜+종목
    시드로 결정적이라, 같은 날 재실행하면 같은 식이 나오고 재현 검증이
    그날의 링을 그대로 되살릴 수 있다.

    ⚠️ 무엇을 재료로 삼는가가 중요하다. 이미 조합으로 만들어진 열(``d_``)을
       다시 조합하면 식이 무한히 깊어지고, 깊은 식은 재현은 되지만 **아무도
       뜻을 설명할 수 없는** 피처가 된다. 한 겹만 허용한다.
    """
    base = sorted(str(c) for c in columns if not str(c).startswith("d_"))
    if len(base) < 2:
        return []
    out: list[str] = []
    for _ in range(max(0, int(n))):
        op = str(rng.choice(list(OPS)))
        if op in _BINARY:
            a = str(rng.choice(base))
            b = str(rng.choice([c for c in base if c != a]))
            out.append(f"{op}:{a}:{b}")
        elif op in _UNARY_WINDOW:
            out.append(f"{op}:{rng.choice(base)}:{rng.choice(list(_WINDOWS))}")
        else:
            out.append(f"{op}:{rng.choice(base)}:{rng.choice(list(_LAGS))}")
    return out


def mutate_recipes(current, columns, rng) -> list[str]:
    """조합식 목록을 한 걸음 흔든다 — 더하기 · 빼기 · 바꾸기.

    ⚠️ **빼기가 반드시 있어야 한다.** 더하는 것만 탐색하면 한번 붙은 피처는
       영영 안 떨어지고, 설정은 시간이 갈수록 무거워지기만 한다. 이 저장소가
       탐색 축을 표로 바꿀 때 배운 것과 같은 교훈이다.
    """
    cur = [str(r) for r in (current or [])]
    moves = ["add", "drop", "swap"] if cur else ["add"]
    if len(cur) >= MAX_DERIVED:
        moves = ["drop", "swap"]
    move = str(rng.choice(moves))
    if move == "add":
        new = candidate_recipes(columns, rng, 1)
        return cur + [r for r in new if r not in cur]
    idx = int(rng.randrange(len(cur)))
    if move == "drop":
        return cur[:idx] + cur[idx + 1:]
    new = candidate_recipes(columns, rng, 1)
    return cur[:idx] + new + cur[idx + 1:]
