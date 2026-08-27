"""야간 자동 재학습 — 챔피언/챌린저 2단계 검증으로 '이길 때만' 교체한다.

매일 밤(GitHub Actions) 또는 수동(python -m quant retrain)으로:
    1. 최신 실데이터를 받는다.
    2. 현재 챔피언 설정과 후보(챌린저) 설정들을 워크포워드 백테스트로 대결시킨다.
    3. 2단계 검증을 모두 통과한 챌린저만 새 챔피언으로 승격한다.
    4. 결정 과정을 전부 기록한다(state/champions.json, state/retrain_history.jsonl).

2단계 검증 — 여러 후보를 시험하면 우연히 좋아 보이는 놈이 꼭 나온다(다중검정).
그래서 데이터를 둘로 자른다:
    선발전(과거 구간): 모든 챌린저 vs 챔피언. t-통계가 임계를 넘는 최고 후보 1명 선발.
    결승전(최근 구간): 선발된 1명만 챔피언과 재대결 — 선발전에서 전혀 보지 못한
                       구간이므로 '운 좋게 뽑힌' 후보는 여기서 대부분 탈락한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 정직한 설명 — 이 루프는 성공률을 '계속 올리지' 않는다.
    재학습의 목적은 모델이 시장 변화에 뒤처지지 않게 하고, 검증을 통과한
    개선만 반영하는 것이다. 방향 예측 정확도의 현실적 상한은 대개 52~55%이며
    어떤 재학습도 그 천장을 뚫지 못한다. 챔피언이 오래 안 바뀌는 것은 고장이
    아니라 정상이다 — 확실히 나은 후보가 없었다는 뜻이고, 그게 이 장치의 일이다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import math
import os
from typing import Callable

from quant.utils.logging import get_logger

log = get_logger("retrain")

STATE_DIR = "state"
CHAMPIONS_FILE = "champions.json"
HISTORY_FILE = "retrain_history.jsonl"

# 선발전 폴드 일관성 게이트의 폴드 수 — **한 자리에서 정한다**(감사 235).
# 예전에는 `nightly_retrain`의 기본값과 장부에 적는 값이 따로 있었고, 장부 쪽은
# 숫자 3이 그냥 박혀 있었다. 한쪽만 바꾸면 장부가 실제와 다른 조건을 말하고,
# `verify`는 그 장부대로 재현하므로 **재현이 어긋난다** — 이 제품이 내세우는
# '조작 불가능'은 재현이 맞을 때만 사실이다(㉞ 같은 판정을 두 곳에서 쓰면
# 언젠가 갈라진다).
SELECT_FOLDS = 3

# 시장별 기본 챔피언 — 첫 실행(기록이 없을 때)의 출발점. 가장 단순하고 견고한
# 로지스틱회귀에서 시작해, 이후는 대결에서 이긴 설정이 이 자리를 물려받는다.
DEFAULT_CHAMPION = {
    "strategy": "ml",
    "params": {"model": "logreg", "threshold": 0.55,
               "train_window": 250, "retrain_every": 20},
}

# 챌린저 후보 격자 — 매일 밤 챔피언에게 도전하는 설정들.
# 후보를 늘릴수록 '우연히 좋아 보이는' 후보도 늘어나므로(다중검정) 소수 정예로
# 유지하고, 결승전(홀드아웃)으로 걸러낸다.
#
# 두 가지 형식을 지원한다:
#   {"model": ...}                 → 챔피언과 같은 전략(ml)의 파라미터 변형
#   {"strategy": 이름, "params": …} → 아예 다른 전략(전통 전략도 참전)
# 전통 전략을 섞는 이유: 퀀트에서 단순한 전략이 ML을 이기는 구간은 흔하다.
# "ML이 시장보다 못한 날"에 자동으로 더 견고한 전략으로 갈아타게 한다.
DEFAULT_CHALLENGERS = [
    {"model": "logreg", "threshold": 0.55},
    {"model": "logreg", "threshold": 0.60},
    {"model": "rf", "threshold": 0.55},
    {"model": "gb", "threshold": 0.55},
    {"model": "gb", "threshold": 0.60},
    {"model": "vote", "threshold": 0.55},
    # 확률 보정 변형 — GBDT류 출력은 대개 과대확신이라, 보정된 확률로
    # 사이징하면 복리 손실이 줄 수 있다. 보정은 엣지를 만들지 않으므로
    # 강제 적용이 아니라 오디션(2단계 관문)을 통과할 때만 챔피언이 된다.
    {"model": "gb", "threshold": 0.55, "calibrate": "isotonic"},
    {"model": "logreg", "threshold": 0.55, "calibrate": "sigmoid"},
    # 라벨 재설계 — '다음 봉 방향'(잡음 큼) 대신 트리플 배리어(±k·변동성
    # 이익/손절 배리어 중 무엇을 먼저 치는가)를 학습하는 변형. 더 나은
    # 라벨이라는 '가설'일 뿐이므로 강제 적용 없이 오디션으로만 승격된다.
    {"model": "gb", "threshold": 0.55, "label": "triple"},
    # 메타라벨링 — 방향은 추세 규칙(종가 vs MA50), ML은 '그 판단이 맞을
    # 확률'만 추정해 크기를 정한다(방향·크기 분업, López de Prado).
    {"model": "logreg", "threshold": 0.55, "label": "triple", "meta": True},
    # 비용 기준 라벨 — "오르기만 하면 1"이 아니라 **왕복 비용을 넘어야 1**
    # (2026-08-20 사장님 지시). 기본 라벨은 편도 0.15%(코인)를 못 넘는
    # 상승도 '맞힘'으로 세는데, 그런 봉은 맞혀도 손해다. 즉 모델이 지금까지
    # "맞히면 이기는 게임"이 아니라 "맞혀도 질 수 있는 게임"을 배우고 있었다.
    #
    # 문턱은 시장별로 계산하지 않고 **숫자로 박는다** — 그래야 verify가
    # 옛 링을 글자 그대로 재구성할 수 있다(재현성이 시장 편의보다 앞선다).
    # 0.0012 = 미국주식 왕복, 0.0030 = 코인·한국주식 왕복. 어느 쪽이 그
    # 종목에 맞는지는 오디션이 고른다.
    #
    # ⚠️ 가설이지 개선이 아니다. 문턱을 올리면 '산다' 라벨이 귀해져 표본이
    #    불균형해지고(실측: 47.6% → 19.8%) 그 자체가 학습을 어렵게 만들 수
    #    있다. 그래서 강제 적용 없이 오디션으로만 승격된다.
    {"model": "gb", "threshold": 0.55, "label": "cost", "label_cost": 0.0012},
    {"model": "gb", "threshold": 0.55, "label": "cost", "label_cost": 0.0030},
    {"model": "logreg", "threshold": 0.55, "label": "cost",
     "label_cost": 0.0030},
    # 표본 시간감쇠 — 최근 표본에 학습 가중을 더 주는 변형(반감기 125봉).
    {"model": "gb", "threshold": 0.55, "sample_weight": "decay"},
    # 피처 가지치기 — 중요도 상위 10개만 남기고 재학습. 피처가 fs7까지 늘어
    # 중복·잡음이 과적합 재료가 되는 것의 반대 레버(추가가 아니라 축소).
    {"model": "gb", "threshold": 0.55, "top_features": 10},
    # 풀링(패널) 학습 — 전 종목 스냅샷을 학습 표본에 합쳐 표본을 ~20배로.
    # 종목당 800봉은 ML 기준 극소 표본이라 이것이 남은 가장 큰 지렛대다.
    # 시장 공통 패턴만 남고 종목 고유 잡음은 씻긴다(패널 모델 — 실무 표준).
    {"model": "gb", "threshold": 0.55, "pool": "peers"},
    {"model": "logreg", "threshold": 0.55, "pool": "peers"},
    # 같은 풀링이지만 **오늘의 유니버스**로 푼다. "peers"는 인과성이 완벽한
    # 대신 스냅샷이 쌓일 때까지(≈6개월) 아무 일도 하지 않는다 — 실측
    # 2026-08-14: 재학습 블록 28/28에서 풀을 못 찾아 챔피언과 신호가 한 봉도
    # 다르지 않았다. 그 사이 종목당 800봉이라는 극소 표본은 그대로다.
    #
    # ⚠️ 이 모드는 **생존 편향**을 감수한다. 가격 행은 학습 상한 이전만 쓰므로
    #    룩어헤드는 없지만, 풀에 든 종목 목록은 '오늘까지 살아남은' 종목이라
    #    사후 정보다. 그래서 강제 적용하지 않고 오디션 후보로만 세운다 —
    #    2단계 관문을 통과할 때만 챔피언이 되고, 승격되면 그 사실이 장부의
    #    파라미터(pool: universe)에 그대로 남아 누구든 알아볼 수 있다.
    {"model": "gb", "threshold": 0.55, "pool": "universe"},
    {"model": "logreg", "threshold": 0.55, "pool": "universe"},
    # 비중을 정하는 방식(sizing) — **오디션이 184회 동안 한 번도 안 흔든 축.**
    #
    # 기본값 "proba"는 확신도에 비례해 산다: 문턱 0.55에서 모델이 "60% 확률로
    # 오른다"고 해도 실제로 사는 것은 자본의 11%다((0.60−0.55)/0.45). 모델
    # 확률이 대부분 0.55~0.60에 몰려 있어 거의 늘 잔돈만 건다.
    #
    # 실측(2026-08-14 스냅샷, 주식 15종목·같은 비용):
    #     시장에 들어가 있던 비율 44.7% · **평균 노출 0.09** (자본의 91%가 현금)
    #                 평균 누적   샤프평균   최대낙폭평균   최악
    #       proba       +9.1%     +0.48      -7.9%      -13.8%
    #       binary     +25.3%     +0.61     -14.5%      -24.7%
    #       그냥 보유   +134%        —       -39.9%      -75.5%
    #
    # 수익도 샤프도 binary가 낫고 낙폭은 보유의 1/3이다. 그렇다고 손으로
    # 갈아치우지 않는다 — 저 숫자는 인샘플이고 한 구간이다. **후보로 세워
    # 2단계 관문을 이기게 한다.** 데이터가 답하지 내가 답하지 않는다.
    {"model": "logreg", "threshold": 0.55, "sizing": "binary"},
    {"model": "gb", "threshold": 0.55, "sizing": "binary"},
    # 문턱을 올리면 덜 자주 들어가되 들어갈 때 더 크게 건다 — 같은 축의
    # 반대편 손잡이라 함께 세워야 무엇이 효과인지 갈린다.
    {"model": "logreg", "threshold": 0.60, "sizing": "binary"},
    {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}},
    {"strategy": "breakout", "params": {"window": 55, "exit_window": 20}},
    # ⭐ 벤치마크를 링에 세운다(2026-08-14). 사이트는 "그냥 보유" 곡선을
    # 그려 보여주는데, **오디션 링에는 그 벤치마크가 없었다.** 그래서
    # 시스템은 구조적으로 "들고 있는 게 낫다"를 발견할 수 없었다.
    #
    # 실측(스냅샷 20종목, 수수료 미반영): ML 샤프 중앙값 0.46 vs 보유 0.81.
    # 예측 자체는 정상(적중률 54.3%)인데 노출이 ~30%뿐이라 상승장에서
    # 구조적으로 진다. 사람이 한 번 알아채고 지나가는 대신, 링에 세워 두면
    # 오디션이 매일 답한다.
    #
    # ⚠️ 보유가 이긴다고 '보유가 옳다'는 뜻은 아니다 — 하락을 그대로 다
    #    맞고(최대낙폭), 이 비교에는 생존 편향이 깔려 있다. 그래서 다른
    #    후보와 똑같은 2단계 관문을 통과해야만 챔피언이 되고, 승격돼도
    #    총노출은 변동성 타깃·킬스위치·검증 게이트가 다시 깎는다.
    {"strategy": "buy_hold", "params": {}},
    # 횡단면 랭킹 — **"오를까?"가 아니라 "누가 더 셀까?"**(감사 259).
    # 지금까지 20종목에 같은 질문을 20번 던졌고 19종목이 같은 챔피언을 썼다.
    # 이건 다른 축이다: 같은 날 20종목을 나란히 세워 상위권일 때만 산다.
    #
    # 실측(2026-08-14 스냅샷, lookback 60·상위 30%):
    #   보유 비율이 종목마다 크게 갈린다 — SPY 9% · NVDA 49% · SK하이닉스 68%
    #   (지금 챔피언은 전 종목이 사실상 같은 신호를 낸다)
    #   샤프도 현 챔피언 평균(+0.48)보다 높다: 삼성 +1.05 · 하이닉스 +0.92
    #
    # ⚠️ 그래도 '그냥 보유'는 못 이긴다(롱온리라 시장 위험을 그대로 진다).
    #    그래서 강제 적용이 아니라 후보로만 세운다 — 2단계 관문이 정한다.
    {"strategy": "cross_rank", "params": {"lookback": 60, "top_frac": 0.3}},
    {"strategy": "cross_rank", "params": {"lookback": 20, "top_frac": 0.3}},
    {"strategy": "cross_rank", "params": {"lookback": 120, "top_frac": 0.5}},
]


def _feature_set() -> str:
    """현재 ML 피처셋 버전 태그 (장부 기록용) — **선언된** 이름표다."""
    from quant.strategies.ml import FEATURE_SET
    return FEATURE_SET


def _features_used(df) -> list[str]:
    """그날 밤 이 종목에 **실제로 붙은** 선택 피처 이름들 (감사 271).

    선언 태그(`feature_set`)와 짝을 이룬다. 둘이 갈라지는 순간이 바로
    "모델이 보는 것이 바뀌었는데 아무도 모르는" 상태다.
    """
    try:
        from quant.strategies.ml import optional_features_from_df
        return sorted(optional_features_from_df(df))
    except Exception:  # noqa: BLE001 — 기록 장치가 재학습을 죽이면 안 된다
        return []


def _key(market: str, symbol: str) -> str:
    return f"{market}:{symbol}"


# ── 탐색 축 등록부 ────────────────────────────────────────────────
#
# 사장님 지시(2026-08-27): *"머신러닝으로 개선을 계속할 수 있게끔 해야지
# 너가 수동으로 고치는 방향 말고."*
#
# 예전에는 이 자리가 ``if axis == "model": … elif …`` 사슬이었다. 그러면
# **기계가 자기 탐색 공간을 읽을 수 없다** — 축이 코드 흐름에 녹아 있어서
# "지금 무엇을 탐색 중인가"를 물어볼 대상이 없었다. 그래서 손잡이를 하나
# 새로 만들 때마다 사람이 사슬에 가지를 하나 더 쳐야 했고, 잊으면 그 축은
# **영원히 탐색되지 않는데 아무 데도 빨간불이 안 떴다.**
#
# 실제로 그 상태였다(2026-08-27 실측): 살아 있는 ML 챔피언 40종목 중
# **6종목이 언덕오르기가 못 건드리는 손잡이 위에 앉아 있었다** —
# ``meta`` 3종목, ``pool`` 3종목. 고정 격자가 그 설정을 한 번 승격시키고
# 나면, 그 뒤로는 "빼 보면 더 나은가"를 아무도 묻지 않았다.
#
# 그래서 사슬을 **표**로 바꾼다. 표는 읽을 수 있고, 읽을 수 있으면 기계가
# 자기 공간의 구멍을 스스로 찾는다(아래 ``ml_search_axes``).

DROP = object()      # 표본이 "이 손잡이를 아예 빼 본다"를 고를 때의 표시

# 라벨 축이 함께 흔드는 종속 손잡이 — 따로 축을 세우지 않는다.
_LABEL_SUBKEYS = {"label_k", "label_horizon"}


def _axis_model(rng, p):
    return {"model": rng.choice(["logreg", "rf", "gb", "vote"])}


def _axis_threshold(rng, p):
    base = float(p.get("threshold", 0.55))
    step = rng.choice([-0.05, -0.02, 0.02, 0.05])
    return {"threshold": round(min(0.70, max(0.52, base + step)), 2)}


def _axis_train_window(rng, p):
    return {"train_window": rng.choice([150, 250, 350, 500])}


def _axis_retrain_every(rng, p):
    return {"retrain_every": rng.choice([10, 20, 40])}


def _axis_label(rng, p):
    """라벨 축 — 배리어 폭(k)·만기(horizon)도 함께 흔들어 탐색."""
    out = {"label": rng.choice(["nextbar", "triple"])}
    if out["label"] == "triple":
        out["label_k"] = rng.choice([1.0, 1.5, 2.0])
        out["label_horizon"] = rng.choice([5, 10, 15])
    return out


def _axis_sizing(rng, p):
    return {"sizing": rng.choice(["proba", "binary"])}


def _axis_sample_weight(rng, p):
    return {"sample_weight": rng.choice([None, "decay"])}


def _axis_calibrate(rng, p):
    return {"calibrate": rng.choice([None, "sigmoid"])}


def _axis_derive(rng, p):
    """조합 피처 축 — **기계가 지어낸 식**을 한 걸음 흔든다(더하기·빼기·바꾸기).

    다른 축과 결이 다르다. 나머지 축은 사람이 미리 적어 둔 **값 목록에서
    고르는** 일이지만, 이 축은 값 자체를 **그 자리에서 만든다.** 손잡이를
    돌리는 것이 아니라 손잡이를 만드는 장치다(2026-08-27 사장님 방침).

    ⚠️ 재료 목록으로 실제 df의 열이 아니라 **이름 목록**을 쓴다. 언덕오르기가
       도는 시점에는 데이터가 없기 때문이다. 그날 없는 열을 가리키는 식은
       피처를 만들 때 조용히 빠지고, 실제로 붙은 열은 장부의 features_used에
       남는다 — 선언과 실제가 갈라지지 않게 재는 장치가 이미 있다.
    """
    from quant.strategies.derive import mutate_recipes
    from quant.strategies.ml import FEATURE_NAMES, OPTIONAL_FEATURES

    vocab = list(FEATURE_NAMES) + list(OPTIONAL_FEATURES)
    out = mutate_recipes(p.get("derive"), vocab, rng)
    return {"derive": out} if out else {"derive": DROP}


# 명시 축 — 범위를 사람이 정해 두는 것이 나은 손잡이들(문턱은 0.52~0.70으로
# 묶어야 하고, 창 길이는 아무 숫자나 되면 곤란하다).
ML_EXPLICIT_AXES = {
    "model": _axis_model,
    "threshold": _axis_threshold,
    "train_window": _axis_train_window,
    "retrain_every": _axis_retrain_every,
    "label": _axis_label,
    "sizing": _axis_sizing,
    "sample_weight": _axis_sample_weight,
    "calibrate": _axis_calibrate,
    # ⚠️ 이 축만 값을 **만든다**(고르지 않는다). 그래서 관측 유도 축이 아니라
    #    명시 축에 둔다 — 관측 유도는 "지금까지 쓰인 값 중에서 고르기"라,
    #    한 번도 안 나온 조합은 영원히 안 나온다.
    "derive": _axis_derive,
}


def _known_ml_param_values() -> dict[str, set]:
    """지금까지 **어디서든 쓰인 적 있는** ML 손잡이와 그 값들을 모은다.

    출처는 고정 격자(DEFAULT_CHALLENGERS)다. 사람이 손으로 후보를 하나
    적어 넣는 순간, 그 손잡이는 **자동으로 탐색 대상이 된다** — 사슬에
    가지를 치는 일을 사람이 기억할 필요가 없어진다.
    """
    seen: dict[str, set] = {}
    for entry in DEFAULT_CHALLENGERS:
        if "strategy" in entry:
            if entry.get("strategy") != "ml":
                continue
            params = entry.get("params", {})
        else:
            params = entry
        for k, v in params.items():
            if k in ML_EXPLICIT_AXES or k in _LABEL_SUBKEYS:
                continue
            try:
                hash(v)
            except TypeError:            # 해시 불가한 값은 표본으로 못 쓴다
                continue
            seen.setdefault(k, set()).add(v)
    return seen


def ml_search_axes(params: dict | None = None) -> dict:
    """지금 탐색 가능한 축 전부 — **명시 축 + 관측에서 유도한 축**.

    ⚠️ 이 함수가 이 파일에서 가장 중요한 한 조각이다. 새 손잡이가 격자나
       현재 챔피언에 나타나는 **그 순간부터** 언덕오르기가 그 축을 흔든다.
       사람이 사슬에 가지를 치지 않아도 된다 — 잊어서 생기는 침묵이 없다.

    유도 축의 표본에는 **DROP(빼 보기)** 이 항상 들어간다. 손잡이를 더하는
    것만 탐색하고 빼는 것은 탐색하지 않으면, 한번 붙은 설정은 영영 안 떨어진다.

    ⚠️ 이것은 후보 **수**를 늘리지 않는다(하루 n개 그대로). 넓어지는 것은
       공간이지 시행 횟수가 아니므로 다중검정 부담이 늘지 않는다 —
       ``confirm_threshold``는 시행 수에 반응하고, 그 수는 그대로다.
    """
    axes = dict(ML_EXPLICIT_AXES)
    observed = _known_ml_param_values()
    for k, vals in (params or {}).items():
        if k not in ML_EXPLICIT_AXES and k not in _LABEL_SUBKEYS:
            try:
                hash(vals)
            except TypeError:
                continue
            observed.setdefault(k, set()).add(vals)
    for key, values in observed.items():
        options = sorted(values, key=repr) + [DROP]
        if len(options) < 2:
            continue
        axes[key] = (lambda k, opts: (lambda rng, p: {k: rng.choice(opts)}))(
            key, options)
    return axes


def mutate_champion(spec: dict, seed: str, n: int = 4) -> list[dict]:
    """현재 챔피언의 '돌연변이' 후보를 만든다 — 진화 탐색의 엔진.

    고정 후보만으로는 그 목록 밖의 설정을 영원히 탐색하지 못한다. 매일 밤
    챔피언 주변을 조금씩 변형한 후보를 새로 만들어 도전시키면, 이긴 변형이
    다음 날의 챔피언이 되고 그 주변을 다시 탐색한다 — 언덕오르기식 진화.
    승격 관문(선발전+결승전)은 그대로이므로 탐색이 넓어져도 과최적화
    방어선은 약해지지 않는다.

    seed(날짜+시장)로 결정적이라 같은 날 재실행해도 같은 후보가 나온다(멱등).
    ⚠️ 진화는 성공률의 끝없는 상승을 만들지 않는다 — 시장이 변하는 한 최적
    설정도 계속 움직이고, 이 탐색은 그 이동을 '따라가는' 장치일 뿐이다.
    """
    import random
    rng = random.Random(f"{seed}:{json.dumps(spec, sort_keys=True)}")
    params = spec.get("params", {})
    out: list[dict] = []
    seen = {json.dumps(spec, sort_keys=True)}
    for _ in range(n * 8):                     # 중복 제거를 감안해 넉넉히 시도
        if len(out) >= n:
            break
        p = dict(params)
        if spec["strategy"] == "ml":
            # ⚠️ "sizing"이 없던 것이 2026-08-16에 드러났다. 이 축 하나가
            #    평균 노출을 0.09로 묶어 자본의 91%를 현금으로 놀렸는데,
            #    오디션 184회가 한 번도 여기를 흔들지 않았다. 없는 축은
            #    영원히 진다 — 탐색 공간에 없으면 이길 기회조차 없다.
            axes = ml_search_axes(p)
            axis = rng.choice(sorted(axes))
            for k, v in axes[axis](rng, p).items():
                if v is DROP:
                    p.pop(k, None)          # 손잡이를 아예 빼 보는 것도 탐색이다
                else:
                    p[k] = v
        else:
            # 수치 파라미터 하나를 곱셈 변형(불리언·문자열은 건드리지 않는다).
            # 잘못된 조합(예: ma_cross fast>=slow)은 생성 단계에서 거르지 않고
            # 대결 루프의 예외 처리에 맡긴다 — 후보 하나의 실패는 무해하다.
            nums = [k for k, v in p.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if not nums:
                break
            k = rng.choice(nums)
            v = p[k] * rng.choice([0.6, 0.8, 1.25, 1.6])
            p[k] = max(2, int(round(v))) if isinstance(p[k], int) else round(v, 4)
        cand = {"strategy": spec["strategy"], "params": p}
        cand_key = json.dumps(cand, sort_keys=True)
        if cand_key not in seen:
            seen.add(cand_key)
            out.append(cand)
    return out


def build_strategy(spec: dict):
    """{"strategy": 이름, "params": {...}} 스펙으로 전략 인스턴스를 만든다.

    특수형 "regime_wrap": 다른 전략(inner)을 레짐 필터로 감싼다 — 약세장·
    고변동성 구간에서 자동 관망하는 변형. 수익을 올리는 장치가 아니라
    대낙폭을 피하는 장치다.
    특수형 "event_wrap": FOMC 등 예고된 거시 이벤트 창(±pad_days)에서
    비중을 줄이는(기본 관망) 변형 — 이벤트 달력이 결정적이라 재현·검증 가능.
    """
    if spec["strategy"] == "regime_wrap":
        from quant.strategies import RegimeFilter
        params = dict(spec.get("params", {}))
        inner = build_strategy(params.pop("inner"))
        return RegimeFilter(inner, **params)
    if spec["strategy"] == "event_wrap":
        from quant.strategies import EventGuard
        params = dict(spec.get("params", {}))
        inner = build_strategy(params.pop("inner"))
        return EventGuard(inner, **params)
    if spec["strategy"] == "stop_wrap":
        from quant.strategies import TrailingStopGuard
        params = dict(spec.get("params", {}))
        inner = build_strategy(params.pop("inner"))
        return TrailingStopGuard(inner, **params)
    if spec["strategy"] == "spec":
        # 사용자가 자료(PDF·유튜브·트레이딩뷰)에서 가져온 명세. **도전자로만**
        # 들어오고, 다른 후보와 똑같은 선발전·결승전·검증 게이트를 거친다.
        # 명세는 데이터라 실행 권한이 없다 — 여기서 코드가 만들어지지 않는다.
        from quant.ingest.spec import SpecStrategy, spec_from_dict
        return SpecStrategy(spec_from_dict(spec["params"]["spec"]))
    from quant.strategies import get_strategy
    return get_strategy(spec["strategy"], **spec.get("params", {}))


def load_champions(state_dir: str = STATE_DIR) -> dict:
    path = os.path.join(state_dir, CHAMPIONS_FILE)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_champions(champions: dict, state_dir: str = STATE_DIR) -> None:
    from quant.utils.jsonio import atomic_write_json
    atomic_write_json(os.path.join(state_dir, CHAMPIONS_FILE), champions)


def append_history(record: dict, state_dir: str = STATE_DIR) -> None:
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, HISTORY_FILE)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def audition_evidence(decision: dict, top: int = 3) -> dict:
    """그날 오디션에서 **실제로 나온 숫자**를 장부용으로 추린다 (감사 235).

    ⚠️ 왜 필요한가. 재학습 기록 159건을 열어 보니 이런 필드만 있었다:

        select_t 2.0 · confirm_t 2.5 · n_candidates 23 · promoted false
        reason "선발전에서 챔피언을 통계적으로 이긴 후보 없음"

    **문턱은 있는데 기록(記錄)이 없다.** 넘어야 할 높이만 적고 실제로 얼마나
    뛰었는지는 아무 데도 없었다. 그래서 답할 수 없는 질문이 쌓였다:

      · 159번 중 승격 1번 — 1등 후보의 t가 1.99였나 0.02였나?
        (앞이면 문턱이 조금 높은 것이고, 뒤면 챌린저 격자가 무의미한 것이다.
         고칠 곳이 완전히 다른데 구분할 방법이 없었다.)
      · 결승전까지 간 12번은 무엇이 모자랐나? 결승 t를 기록하지 않았다.
      · t가 커도 평균 차이가 잔돈이면 갈아탈 이유가 없다 — 효과 크기도 없었다.

    이 저장소는 "판단 근거를 장부에 남긴다"를 정체성으로 내건다. 결정에 쓴
    **전제**(비용·체결 가정)는 이미 남기고 있었는데, 정작 **결과**가 빠져
    있었다.

    파일이 하루 20줄씩 자라므로 상위 `top`개의 t만 남긴다 — '얼마나 가까웠나'
    를 답하는 데는 분포의 머리만 있으면 된다.
    """
    cands = decision.get("candidates") or []

    def _t(c) -> float | None:
        v = c.get("t_stat")
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None

    ranked = sorted((c for c in cands if _t(c) is not None),
                    key=lambda c: _t(c), reverse=True)
    ev: dict = {"top_t": [round(_t(c), 3) for c in ranked[:max(0, top)]]}
    if ranked:
        b = ranked[0]
        spec = b.get("spec") or {}
        ev["best"] = {
            "t": round(_t(b), 3),
            "n": int(b.get("n") or 0),
            # 효과 크기 — t만 보면 '통계적으로 유의한 잔돈'을 못 걸러낸다.
            "mean_diff": round(float(b.get("mean_diff") or 0.0), 8),
            "fold_wins": b.get("fold_wins"),
            "n_folds": b.get("n_folds"),
            "strategy": spec.get("strategy"),
            "params": spec.get("params"),
        }
    fin = decision.get("final")
    if fin:
        ev["final"] = {"t": round(float(fin.get("t_stat") or 0.0), 3),
                       "n": int(fin.get("n") or 0),
                       "mean_diff": round(float(fin.get("mean_diff") or 0.0), 8),
                       "swap": bool(fin.get("swap"))}
    return ev


def _audition_kwargs_from_record(rec: dict) -> dict:
    """장부 기록에서 그날의 오디션 조건을 되살린다(verify 재현용).

    audition_env가 없는 옛 기록은 그때 실제로 쓰던 조건 — 시장별 가정 비용,
    종가 체결, 밴드 0 — 으로 폴백한다. 알고리즘이 진화해도 과거 결정의 재현
    검증이 깨지지 않아야 한다(그게 깨지면 '조작 불가능' 주장도 깨진다).
    """
    from quant.backtest.costs import CostModel
    env = rec.get("audition_env")
    if not env:
        return {"cost_model": CostModel.for_market(rec["market"])}
    return {
        "cost_model": CostModel(fee=float(env["fee"]),
                                slippage=float(env["slippage"])),
        "next_open_fill": bool(env.get("next_open_fill", False)),
        "rebalance_band": float(env.get("rebalance_band", 0.0)),
    }


# ── 선발전은 '선별기'지 '검정'이 아니다 ────────────────────────────────
# 2026-08-14 실측(스냅샷 15종목, 후보 20개): 선발 문턱 2.45 · 결승 문턱 1.03
# 이었고, **결승에 도달한 후보가 15종목에서 0개**였다. 결승전(선발전이 보지
# 못한 최근 구간)은 이 설계의 핵심 방어선인데 한 번도 작동하지 않았다.
#
# 왜 뒤집혔나: 다중검정 보정 sqrt(2·ln N)을 **선발전**에 걸었다. 그런데
# 선발전과 결승전은 **서로 겹치지 않는 구간**을 본다(select_df는 결승 구간을
# 잘라낸다). 겹치지 않는 데이터에서 N개 중 1등을 고른 뒤 그 1명만 검정하면,
# 그 검정은 이미 단일 검정이다 — 같은 날 후보가 몇 명이었든 결승전의 t는
# 귀무가설 아래서 여전히 표준정규다. 코드 주석도 "최종 검정은 1회라 다중검정
# 부풀림이 없다"고 적고 있었는데, 정작 보정은 선발전에 걸려 있었다.
# 즉 **같은 다중성을 두 번 셌고**, 그 대가로 2단계 관문이 통째로 죽었다.
#
# 실측된 대가: ma_cross가 선발 t=1.96 · 3/3 폴드 전승 · 봉당 +5.43bp로 챔피언을
# 이기고도 결승에 못 갔다. 문턱을 1.0으로 내렸을 때 15종목 중 8개가 결승에
# 도달했고, 승격된 설정은 **오디션이 전혀 보지 못한 250봉**에서 3건 중 2건이
# 이겼다(평균 +5.5bp/봉).
#
# ⚠️ 정직한 한계: 15종목·승격 3건은 통계적 증명이 아니다(전체 t≈0.8).
#    이 변경의 근거는 그 숫자가 아니라 **구조**다 — 선별기가 자기가 먹여
#    살리는 검정보다 엄격하면 그 검정은 정의상 아무것도 거르지 못한다.
#    실제 다중성(매일·전 종목 반복)은 결승 문턱(confirm_threshold)이 계속
#    맡는다. 이 값을 다시 올리려면 결승 문턱보다 낮게 유지해야 한다.
SELECT_SCREEN_T = 1.0


def effective_select_t(select_t: float, confirm_t: float,
                       clamp_screen: bool = True) -> float:
    """**실제로 적용되는** 선발 문턱 — 계산하는 곳은 여기 하나뿐이다.

    ⚠️ 왜 함수로 뺐나(2026-08-16 실측). 이 조정은 `nightly_retrain` 안에서만
       일어났고, 장부·콘솔은 **조정 전 값**을 적었다. 그래서 175/175건이
       이렇게 남아 있다:

           기록·화면:  선발 t≥2.52   ← 실제로는 아무도 이 문턱을 넘지 않았다
           실제 적용:  선발 t≥1.03

       조정 자체는 옳다(선별기가 자기가 먹여 살리는 검정보다 엄격하면 그
       검정은 정의상 아무것도 못 거른다 — 위 주석). 틀린 것은 **기록**이다.
       "왜 챔피언이 안 바뀌나"를 2.52로 판단하면 답이 통째로 어긋난다.

       그래서 판정은 한 곳에서만 하고 장부·화면·오디션이 **같은 함수**를
       읽는다 — 두 곳에서 따로 계산하면 언젠가 갈라진다.
    """
    if clamp_screen and select_t > confirm_t:
        return float(confirm_t)
    return float(select_t)


def nightly_retrain(
    df,
    champion_spec: dict,
    challenger_specs: list[dict],
    *,
    build: Callable[[dict], object] = build_strategy,
    panel_specs: list[dict] | None = None,
    confirm_window: int = 120,
    select_t: float = SELECT_SCREEN_T,
    confirm_t: float = 1.0,
    min_obs: int = 60,
    edge: float = 0.0,
    cost_model=None,
    select_folds: int = SELECT_FOLDS,
    next_open_fill: bool = False,
    rebalance_band: float = 0.0,
    clamp_screen: bool = True,
    reality_gate: bool = True,
) -> dict:
    """챔피언 1명 vs 챌린저 N명 — 2단계 검증으로 승격 여부를 결정한다.

    반환 dict의 promoted가 True면 champion(새 스펙)이 함께 담긴다.
    데이터(df)를 인자로 받는 순수 함수라 어떤 전략/데이터로도 테스트 가능하다.

    select_folds ≥ 2면 선발전에 '폴드 일관성 게이트'가 추가된다: 수익 차이를
    연속 등분한 폴드 중 과반에서 이겨야 통과 — 전체 t-통계 하나는 한 구간의
    대박이 만든 착시일 수 있다(CPCV 경량판). 0이면 기존 동작(verify가 옛
    기록을 재현할 때 사용).

    ⚠️ select_t는 **결승 문턱을 넘지 못한다**(SELECT_SCREEN_T 주석 참조).
    선별기가 자기가 먹여 살리는 검정보다 엄격하면 결승전은 정의상 아무것도
    거르지 못하고, 2단계 관문은 이름만 남는다. 넘겨받은 값이 더 크면
    조용히가 아니라 **경고와 함께** 낮춘다.
    """
    from quant.live.champion_challenger import ChampionChallenger

    def _out(result: dict) -> dict:
        """판정 결과에 **패널 재료**를 얹어 돌려준다.

        ``panel_specs``를 넘긴 밤에만 계산한다. 그 설정들이 이 종목의
        홀드아웃에서 낸 (도전자 − 챔피언) 일수익 차를 **날짜와 함께** 담는다 —
        밤 배치가 종목을 돌면서 그것을 모아 "한 설정이 여러 종목에서 함께
        좋은가"를 잰다(``quant.live.panel_gate``).

        ⚠️ **판정이 어떻게 끝났든 재료는 모은다.** 동시검정용 홀드아웃 계산은
           결승까지 간 밤에만 도는데, 결승에 가는 밤은 드물다(장부 실측:
           시행 11,721회 중 결승 186회). 그 자리에서만 주우면 대부분의 밤에
           아무것도 안 모이고, 패널은 최소 종목 수를 몇 달이 지나도 못 채운다.
           그래서 판정이 끝나는 **모든 출구**가 이 자리를 지난다.

        ⚠️ 반대로 ``panel_specs``가 없으면 **한 줄도 더 계산하지 않는다.**
           이건 후보를 홀드아웃에서 한 번 더 재생하는 일이고, 밤 배치는 시간
           예산 안에서 도는 이어달리기다 — 한 종목이 느려지면 그만큼 다른
           종목이 오늘 밤 못 돈다. 재현 검증(verify)도 이 비용을 낼 이유가 없다.

        ⚠️ 담기는 값은 pandas 객체라 **장부에 그대로 적히면 안 된다.**
           장부는 필드를 하나씩 골라 쓰므로 자동으로 새지 않지만, 검사로
           못을 박아 둔다.
        """
        if not panel_specs:
            return result
        try:
            result["panel_diffs"] = holdout_diffs(
                champion_spec, panel_specs, df, confirm_window, build,
                dict(cost_model=cost_model, next_open_fill=next_open_fill,
                     rebalance_band=rebalance_band))
        except Exception as exc:  # noqa: BLE001 — 재료 수집 실패가 판정을 못 죽인다
            log.warning("패널 재료 수집 실패: %s", exc)
            result["panel_diffs"] = {}
        return result

    if len(df) <= confirm_window + min_obs:
        # 이것도 '검증 못 한 날'이다 — 오디션이 아예 열리지 않았으므로
        # 그날의 '챔피언 유지'는 검증 결과가 아니다(공회전과 같은 부류).
        return _out({"promoted": False, "vacuous": True, "reason": (
            f"⚠️ 평가 불가 — 데이터 부족({len(df)}봉)으로 선발전+결승전"
            f"({confirm_window}봉)을 나눌 수 없어 오디션을 열지 못했습니다. "
            "챔피언을 유지하지만 이는 검증 결과가 아닙니다."),
            "candidates": [], "inert": []})

    used = effective_select_t(select_t, confirm_t, clamp_screen)
    if used != select_t:
        log.warning(
            "선발 문턱(%.2f)이 결승 문턱(%.2f)보다 엄격하다 — 결승전이 "
            "무력화된다. 선발 문턱을 %.2f로 낮춘다.",
            select_t, confirm_t, used)
    select_t = used

    select_df = df.iloc[:-confirm_window]      # 선발전: 결승 구간을 전혀 못 본다
    candidates, inert = [], []
    for spec in challenger_specs:
        if "strategy" in spec:                  # 다른 전략(전통 전략 등)의 도전
            full_spec = {"strategy": spec["strategy"],
                         "params": dict(spec.get("params", {}))}
        else:                                   # 챔피언과 같은 전략의 파라미터 변형
            full_spec = {"strategy": champion_spec["strategy"],
                         "params": {**champion_spec.get("params", {}), **spec}}
        if (full_spec["strategy"] == champion_spec["strategy"]
                and full_spec["params"] == champion_spec.get("params", {})):
            continue                            # 챔피언 자신과의 대결은 무의미
        try:
            cc = ChampionChallenger(
                build(champion_spec), build(full_spec),
                min_obs=min_obs, edge=edge, t_threshold=select_t,
                cost_model=cost_model, next_open_fill=next_open_fill,
                rebalance_band=rebalance_band)
            r = cc.evaluate(select_df, folds=select_folds)
        except Exception as exc:  # noqa: BLE001 — 후보 하나의 실패로 전체를 죽이지 않는다
            log.warning("챌린저 평가 실패 %s: %s", spec, exc)
            continue
        if r.get("identical"):
            # 챔피언과 한 봉도 다르지 않은 후보 — 설정만 다르고 하는 일은 같다.
            # 후보로 세지 않는다(문턱·시도 수를 부풀리지 않게). 대신 무엇이
            # 죽어 있었는지 이름을 남긴다 — 조용한 무효화가 감사 127을 몇 주
            # 숨겼고, 여기서도 매일 두 개가 유령처럼 링에 올라와 있었다.
            inert.append(full_spec)
            log.warning("무효 후보(챔피언과 신호 동일) — 오디션에서 제외: %s",
                        json.dumps(full_spec, ensure_ascii=False))
            continue
        candidates.append({"spec": full_spec, **r})

    def _consistent(c: dict) -> bool:
        # 폴드 일관성 게이트 — 과반 폴드에서 이겨야 한다. 폴드 정보가 없으면
        # (select_folds=0 또는 표본 부족) 게이트 없이 통과(기존 동작).
        if "fold_wins" not in c:
            return True
        return c["fold_wins"] >= c["n_folds"] // 2 + 1

    # 공회전 오디션 — 후보 대부분이 챔피언과 같은 신호를 냈다는 것은 그날의
    # 대결이 아무것도 비교하지 못했다는 뜻이다. 실측(2026-08-14): 코인 5종목은
    # 선발 구간이 180봉인데 챔피언의 학습창이 250봉이라 **한 번도 학습하지
    # 못했고**, 후보 19개 중 18개가 신호 0으로 챔피언과 동일했다. 그런데도
    # 장부에는 "후보 19개 — 챔피언 유지. 정상입니다"라고 적혔다.
    # 검증하지 못한 것을 검증했다고 말하는 것이 이 저장소가 가장 경계하는 일이다.
    vacuous = bool(inert) and len(candidates) <= max(1, len(inert) // 4)
    if not candidates:
        # 후보가 하나도 안 남은 두 경로를 구별한다. 둘 다 '검증 못 함'이지만
        # 원인이 다르고, 뭉뚱그리면 고칠 곳을 못 찾는다.
        why = (f"후보 {len(inert)}개가 **전부** 챔피언과 같은 신호를 냈습니다"
               "(대결이 성립하지 않음). 데이터가 짧아 학습창·워밍업을 채우지 "
               "못했을 가능성이 큽니다." if inert else
               "세울 수 있는 후보가 하나도 없었습니다"
               "(후보 목록이 비었거나 전부 평가 중 예외).")
        return _out({"promoted": False, "vacuous": True, "reason": (
            f"⚠️ 평가 불가 — {why} 이날의 오디션은 아무것도 검증하지 "
            "못했습니다 — '이긴 후보가 없다'와 다릅니다."),
            "candidates": candidates, "inert": inert})

    passed = [c for c in candidates if c["swap"] and _consistent(c)]
    if not passed:
        note = (f" ⚠️ 다만 후보 {len(inert) + len(candidates)}개 중 {len(inert)}개는 "
                "챔피언과 신호가 같아 대결 자체가 성립하지 않았습니다."
                if vacuous else " 정상입니다.")
        return _out({"promoted": False, "vacuous": vacuous, "reason": (
            f"선발전에서 챔피언을 통계적으로 이긴 후보 없음"
            f"(실제 대결 {len(candidates)}개) — 챔피언 유지.{note}"),
            "candidates": candidates, "inert": inert})

    best = max(passed, key=lambda c: c["t_stat"])

    # 결승전 — 선발된 1명만, 선발전에서 보지 못한 최근 구간에서 재검증.
    # 후보가 몇 명이었든 최종 검정은 1회라 다중검정 부풀림이 없다.
    cc = ChampionChallenger(
        build(champion_spec), build(best["spec"]),
        min_obs=min(min_obs, confirm_window // 2), edge=edge,
        t_threshold=confirm_t, cost_model=cost_model,
        next_open_fill=next_open_fill, rebalance_band=rebalance_band)
    final = cc.evaluate(df, tail=confirm_window)

    if not final["swap"]:
        return _out({"promoted": False, "reason": (
            "선발전 1위가 결승전(최근 미공개 구간)에서 검증 실패 — 챔피언 유지. "
            "선발전 성적은 우연이었을 가능성이 큽니다."),
            "best_candidate": best, "final": final,
            "candidates": candidates, "inert": inert})

    # 동시검정(현실성 검사) — 결승 t를 넘어도 '후보 N명 중 최고'는 혼자만의
    # 검정이 아니다(2026-08-18). confirm_threshold의 로그+상한 보정은 시도가
    # 아주 많아지면 상한에 붙어 더 오르지 않는다 — 그 빈틈을 여기서 막는다:
    # 오늘 링에 선 **모든** 실제 후보의 홀드아웃 수익 차이를 놓고, "이 중
    # 최고 성적이 순전히 우연으로 나올 확률"을 블록 부트스트랩으로 직접 잰다.
    # 후보가 늘수록 이 확률은 자동으로 커진다 — 상한이 필요 없는 보정이다.
    rc_res = None
    if reality_gate:
        bt = dict(cost_model=cost_model, next_open_fill=next_open_fill,
                  rebalance_band=rebalance_band)
        mat = _holdout_diff_matrix(champion_spec, [c["spec"] for c in candidates],
                                   df, confirm_window, build, bt)
        # ⚠️ 건너뜀에는 **두 종류**가 있고 둘을 섞으면 안 된다(2026-08-27 발견).
        #    · 홀드아웃이 짧다 → 잴 수 없는 것이 사실이다. 생략하고 기록한다.
        #    · 후보가 있는데 **행렬이 비었다** → 재려다 실패한 것이다.
        #      그런데 예전에는 둘 다 "생략"으로 흘러 그대로 승격됐다.
        #      승격 20건 중 19건을 막아 온 관문이 조용히 없어지는 경로였다.
        #    변이 시험이 잡아냈다: holdout_diffs를 빈 dict로 만들어도 아무
        #    검사가 죽지 않았다(놓침 1). 못 잰 것을 통과로 읽지 않는다.
        if mat is None and candidates:
            return _out({"promoted": False, "reality_check": {
                "skipped": True, "broken": True, "reason": (
                    "후보가 있는데 홀드아웃 차이 행렬을 못 만들었습니다 — "
                    "동시검정을 **재려다 실패**한 것이라 생략이 아닙니다. "
                    "관문을 못 건 채로 승격시키지 않습니다.")},
                "reason": (
                    "동시검정을 수행하지 못해 승격 보류 — 재지 못한 것을 "
                    "통과로 읽지 않습니다."),
                "best_candidate": best, "final": final,
                "candidates": candidates, "inert": inert})
        if mat is None or mat.shape[0] < RC_MIN_N:
            rc_res = {"skipped": True, "reason": (
                f"홀드아웃 표본 부족(<{RC_MIN_N}봉) — 동시검정 생략(관문 미적용)")}
        else:
            rc_res = reality_check(mat)
            if rc_res["p"] > RC_ALPHA:
                return _out({"promoted": False, "reality_check": rc_res, "reason": (
                    f"결승 t={final['t_stat']:.2f}는 넘었지만, 오늘 링에 선 "
                    f"{rc_res['n_cand']}개 후보를 **동시에** 놓고 보면 이 정도 "
                    f"성적이 우연으로 나올 확률 p={rc_res['p']:.3f} > "
                    f"{RC_ALPHA} — 승격 보류(부트스트랩 동시검정). 후보를 많이 "
                    "세울수록 하나쯤은 우연히 좋아 보인다는 사실의 값이다."),
                    "best_candidate": best, "final": final,
                    "candidates": candidates, "inert": inert})

    return _out({"promoted": True, "champion": best["spec"], "reality_check": rc_res,
            "reason": (
        f"선발전 t={best['t_stat']:.2f}, 결승전 t={final['t_stat']:.2f} 모두 통과"
        + (f", 동시검정 p={rc_res['p']:.3f}≤{RC_ALPHA}"
           if rc_res and not rc_res.get("skipped") else "")
        + " — 새 챔피언으로 승격."),
        "best_candidate": best, "final": final,
        "candidates": candidates, "inert": inert})


# 하룻밤에 패널로 재는 설정 수 — **짐작이 아니라 실측으로** 정했다
# (한국주식 4~6종목, 스냅샷 2026-08-26, 종목당 오디션 ~71초 기준):
#
#     명단 전체(28개)  → +109%  · 예산 1800초 처리 종목 26 → 12  (반토막)
#     하룻밤 6개       →  +37%  ·                      25 → 18
#     하룻밤 3개       →   +8%  ·                      25 → 23   ← 채택
#
# 전부 매일 재면 각 종목의 오디션 주기가 1.5일에서 3일로 늘어나는데 **화면에는
# 아무 빨간불도 안 뜬다** — 커서에 '못 돈 종목'이 조금 늘 뿐이다. 이 저장소가
# 반복해서 막아 온 종류의 조용한 퇴행이고, 하필 패널 배선이 만들었다.
#
# 그래서 **날짜로 회전**한다: 그날 밤 모든 종목이 **같은 부분집합**을 돌고,
# 며칠에 걸쳐 명단 전체가 한 바퀴 돈다. 패널의 전제("같은 설정을 여러 종목이
# 함께 잰다")는 그대로다 — 나뉘는 것은 종목이 아니라 날짜다.
#
# ⚠️ 비용은 뽑히는 설정에 따라 **고르지 않다**. 6개일 때 +37%가 나온 것은
#    그날 표본에 풀링(pool) ML이 섞였기 때문이다 — 그 설정들은 다른 종목
#    스냅샷을 읽어 학습해서 몇 배 비싸다. 그래서 명단 크기를 조금만 키워도
#    최악의 밤이 크게 나빠질 수 있다. 키울 거면 **다시 재고 키운다.**
#
# ⚠️ 지금 패널은 **기록만** 한다(승격은 종목별 관문이 정한다). 즉 이 8%는
#    아직 이득 없이 내는 비용이다. 관문을 실제로 옮길 때 이 수치를 근거로
#    명단 크기를 다시 정한다.
PANEL_ROSTER_PER_NIGHT = 3


def panel_roster() -> list[dict]:
    """패널에 세울 수 있는 설정 전체 — **모든 종목에서 글자 그대로 같은** 것만.

    ⚠️ 2026-08-27, 실제 스냅샷 32종목으로 연기시험을 돌려 결함을 잡았다.
       처음에는 고정 격자 항목을 그대로 넘겼는데, 격자의 ML 항목은
       ``{"model": "gb", "threshold": 0.55}`` 같은 **덧씌우기 형태**다.
       오디션은 그것을 **그 종목 챔피언의 파라미터 위에** 얹어 해석한다
       (``nightly_retrain``의 full_spec). 그래서 같은 한 줄이 종목마다
       **다른 설정**을 뜻한다 — 챔피언이 종목마다 다르기 때문이다.

       그 상태로 패널에 담으면 "같은 설정이 여러 종목에서 좋았다"가 아니라
       서로 다른 설정들의 평균이 된다. 게다가 덧씌우기 형태는 그 자체로는
       전략을 만들 수 없어(``strategy`` 키가 없다) 홀드아웃 재생이 종목마다
       조용히 실패했다 — 경고만 쌓이고 판정은 계속 도는, 이 저장소가 가장
       싫어하는 종류의 침묵이다.

    ⚠️ 명단은 고정 격자(``DEFAULT_CHALLENGERS``)와 고정 전략형 후보
       (``FIXED_CHALLENGERS``) **둘 다**에서 나온다. 처음에는 앞의 것만
       봤는데, 그러면 패널에 **가장 잘 어울리는 후보들이 빠진다**: 가설
       규칙 여섯 개(월말 수급·PEAD·만기 주간·FOMC 표류·펀딩 과열 회피·
       월말 강제 리밸런싱)는 파라미터까지 전 종목이 동일해서, "이 규칙이
       여러 종목에서 **함께** 도움이 되는가"가 바로 그 규칙들이 답해야 할
       질문이다. 회전 때문에 하룻밤 비용은 안 늘고 한 바퀴 주기만 길어진다.

    그래서 여기서 **절대 설정**으로 못 박는다: 덧씌우기 항목은 그 종목의
    챔피언이 아니라 **기본 챔피언** 위에 얹는다. 그러면 어느 종목에서 재든
    똑같은 한 가지 설정이고, 비교되는 것은 "이 고정 설정이 각 종목의 현
    챔피언을 이기는가"라는 하나의 질문이 된다.

    ⚠️ 어떤 종목에서는 이 설정이 그 종목의 챔피언과 같을 수 있다(차이가
       전부 0). 빼지 않는다 — 그 종목에서 이 설정이 이득이 없다는 것이
       **사실**이고, 사실을 빼면 패널이 낙관 쪽으로 기운다.
    """
    out, seen = [], set()
    for entry in list(DEFAULT_CHALLENGERS) + list(FIXED_CHALLENGERS):
        if "strategy" in entry:
            spec = {"strategy": entry["strategy"],
                    "params": dict(entry.get("params", {}))}
        else:
            spec = {"strategy": "ml",
                    "params": {**DEFAULT_CHAMPION["params"], **entry}}
        key = spec_key(spec)
        if key in seen:
            continue
        seen.add(key)
        out.append(spec)
    return out


def shared_panel_specs(asof: str | None = None) -> list[dict]:
    """오늘 밤 패널로 잴 설정 — 날짜로 회전한 부분집합.

    ⚠️ 시드는 **날짜만** 쓴다(종목이 아니다). 그날 밤 모든 종목이 같은
       부분집합을 돌아야 한 통에 담을 수 있다. 종목별로 다르게 뽑으면
       설정마다 참여 종목이 한둘로 쪼개져 패널이 영원히 최소 종목 수를
       못 채운다 — 비용만 쓰고 아무것도 못 재는 상태가 된다.

    ``asof``가 없으면 전체를 돌려준다(검사·분석용).

    ⚠️ **나중에 이것이 관문이 될 때 다시 볼 것**(작업 #56): 지금 다중검정
       보정은 그날 밤 명단 크기(6개)에만 걸린다. 회전 때문에 며칠에 걸쳐
       28개를 다 재게 되므로, 승격을 패널로 정하는 순간에는 **날짜를 가로질러
       누적된 시도 수**로 보정해야 한다. 그러지 않으면 "매일 6개만 봤다"는
       셈법으로 28개를 뒤진 대가를 안 치르게 된다.
    """
    roster = panel_roster()
    if asof is None or len(roster) <= PANEL_ROSTER_PER_NIGHT:
        return roster
    # ⚠️ **무작위 추출이 아니라 순환이다.** 처음에는 날짜를 시드로 뽑았는데,
    #    복원추출이라 어떤 설정은 2주가 지나도 한 번도 안 뽑혔다(실측: 14일에
    #    46개 중 30개). 그러면 "며칠에 걸쳐 명단 전체를 돈다"는 말이 사실이
    #    아니게 되고, 안 뽑힌 설정은 **영영 안 재질 수도** 있다.
    #    날짜에서 시작 위치를 정해 창을 밀면 ceil(46/3)=16일이면 반드시
    #    한 바퀴가 돈다 — 그리고 여전히 날짜만 보므로 결정적이다.
    import datetime as _dt

    try:
        day_no = _dt.date.fromisoformat(str(asof)[:10]).toordinal()
    except ValueError:
        day_no = abs(hash(str(asof)))          # 날짜를 못 읽어도 결정적으로
    n = len(roster)
    start = (day_no * PANEL_ROSTER_PER_NIGHT) % n
    return [roster[(start + i) % n] for i in range(PANEL_ROSTER_PER_NIGHT)]


def champion_spec(market: str, symbol: str, state_dir: str = STATE_DIR) -> dict:
    """현재 챔피언 스펙을 반환한다. 기록이 없으면 기본 챔피언으로 폴백한다.

    실행파일/새 설치처럼 state/가 없는 환경에서도 항상 동작해야 하므로
    폴백은 조용히 일어난다(기본 챔피언 = ml logreg, MLStrategy 기본값과 동일).

    **사용자 고정(pin)이 있으면 그것이 먼저다** — 설치형 사용자가 확인
    문구까지 타이핑해 "이 전략으로 매매해"라고 명시한 종목은 심사 결과와
    무관하게 그 전략이 맡는다. 챔피언 기록은 계속 쌓인다(고정을 풀면 즉시
    복귀). 크기 결정(킬스위치·변동성 타깃·검증 게이트)은 신호의 출처를
    보지 않으므로 고정돼도 그대로 걸린다.
    """
    from quant.live.pin import pinned_spec
    pin = pinned_spec(market, symbol, state_dir)
    if pin:
        return pin
    entry = load_champions(state_dir).get(_key(market, symbol))
    if entry:
        return {"strategy": entry["strategy"], "params": dict(entry["params"])}
    return {"strategy": DEFAULT_CHAMPION["strategy"],
            "params": dict(DEFAULT_CHAMPION["params"])}


def champion_strategy(market: str, symbol: str, state_dir: str = STATE_DIR):
    """'현재 챔피언'을 위임 실행하는 전략을 반환한다 — 야간 승격을 자동 반영.

    매 신호 계산 전에 state/champions.json을 다시 읽어, 야간 재학습이 챔피언을
    교체했으면 봇 재시작 없이 새 설정으로 갈아탄다(파일 1회 읽기라 비용 무시).
    학습 자체는 위임받은 MLStrategy가 워크포워드로 수행한다.
    """
    from quant.strategies.base import Strategy

    class _Champion(Strategy):
        name = "champion"

        def __init__(self):
            self._spec: dict | None = None
            self._impl = None

        def _refresh(self) -> None:
            # 사용자 고정이 있으면 의회보다도 먼저다 — 사용자가 명시한
            # 전략을 의회가 희석하면 "내 전략으로 매매"가 거짓말이 된다.
            from quant.live.pin import pinned_spec
            pin = pinned_spec(market, symbol, state_dir)
            if pin:
                if pin != self._spec:
                    log.info("📌 사용자 고정 전략 적용: %s",
                             pin["params"]["spec"].get("name"))
                    self._impl = build_strategy(pin)
                    self._spec = pin
                return
            # 의회(다수 의원)가 있으면 혼합 전략으로, 아니면 단일 챔피언으로.
            # 스펙 비교 키에 의회 명단을 포함해 구성 변화도 핫리로드된다.
            entry = load_champions(state_dir).get(_key(market, symbol))
            members = (entry or {}).get("parliament") or []
            if len(members) >= 2:
                spec = {"strategy": "__parliament__", "params": members}
                if spec != self._spec:
                    if self._spec is not None:
                        log.info("🏛 의회 구성 변화 감지 → 새 구성 적용")
                    from quant.live.parliament import ParliamentStrategy
                    self._impl = ParliamentStrategy(members, build_strategy)
                    self._spec = spec
                return
            spec = champion_spec(market, symbol, state_dir)
            if spec != self._spec:
                if self._spec is not None:
                    log.info("🔁 챔피언 교체 감지 → 새 설정 적용: %s", spec["params"])
                self._impl = build_strategy(spec)
                self._spec = spec

        def generate_signals(self, df):
            self._refresh()
            return self._impl.generate_signals(df)

    return _Champion()


def _normalize_challengers(specs: list[dict], champion: dict) -> list[dict]:
    """merge형({"model": ...}) 후보를 챔피언 전략에 맞게 해석한다.

    merge형은 'ml 챔피언의 파라미터 변형'이라는 의미다. 챔피언이 ml이 아닌
    날에도 ML 후보가 링에서 사라지면 안 되므로, 그때는 기본 ml 파라미터 위에
    변형을 얹은 '독립 ml 후보'로 바꿔 참전시킨다.
    """
    if champion["strategy"] == "ml":
        return list(specs)
    out = []
    for spec in specs:
        if "strategy" in spec:
            out.append(spec)
        else:
            out.append({"strategy": "ml",
                        "params": {**DEFAULT_CHAMPION["params"], **spec}})
    return out


def _user_specs(state_dir: str | None) -> list[dict]:
    """사용자가 넣은 전략 명세 → 도전자. 없으면 빈 목록.

    ⚠️ 문제가 있는 명세는 **조용히 건너뛰지 않는다.** 그러면 사용자는 자기
       전략이 매일 밤 링에 선다고 믿는데 실제로는 한 번도 안 선다 — 이
       저장소가 계속 잡아온 바로 그 침묵이다.
    """
    try:
        from quant.ingest.registry import user_challengers
        cands, notes = user_challengers(state_dir)
    except Exception as exc:            # noqa: BLE001
        print(f"  ⚠️ 사용자 전략을 읽지 못했습니다 — {exc}")
        return []
    for note in notes:
        print(f"  ⚠️ {note}")
    if cands:
        print(f"  📎 사용자 전략 {len(cands)}개가 오늘 링에 섭니다 "
              f"(다른 후보와 같은 심사를 받습니다).")
    return cands


# ── 종목이 달라도 **글자 그대로 같은** 고정 후보들 ────────────────────────
#
# 예전에는 이 목록이 build_challengers 안에 인라인으로 흩어져 있었다. 그래서
# 패널 관문(panel_roster)이 이것들을 못 봤다 — 패널은 "한 설정이 여러 종목에서
# 함께 좋은가"를 묻는 장치인데, **가장 잘 어울리는 후보들**(가설 규칙 여섯 개는
# 파라미터까지 전 종목 동일하다)이 명단 밖에 있었던 것이다.
#
# 목록을 여기 한 곳에 두고 양쪽이 같은 출처를 본다. 두 곳에 적으면 언젠가
# 갈라지고, 갈라진 쪽은 조용히 탐색·측정에서 빠진다(FROZEN_IDEAS ①).
#
# ⚠️ 여기 한 줄을 더하면 **두 가지가 동시에 일어난다**: 밤 오디션 링에 서고,
#    패널 명단에도 들어간다. 패널은 날짜로 회전하므로 하룻밤 비용은 안 늘고
#    한 바퀴 도는 주기만 길어진다.
FIXED_CHALLENGERS = [
    # 터틀 트레이딩(사장님 제안 2026-08-18) — 규칙이 완전히 공개된 결정적
    # 추세추종. 시스템1(20/10)과 시스템2(55/20) 둘 다 링에 세운다.
    # 전설이라도 심사는 똑같다 — 이겨야 챔피언이다.
        {"strategy": "turtle", "params": {"entry_window": 20, "exit_window": 10}},
        {"strategy": "turtle", "params": {"entry_window": 55, "exit_window": 20}},
    # 사장님이 공유한 차트 자료(2026-08-18)에서 옮긴 결정적 전략 3종 —
    # 볼린저 두 활용법·파라볼릭 SAR·일목균형표. 링은 넓어지고, 다중검정
    # 문턱은 후보 수만큼 자동으로 올라간다.
        {"strategy": "bollinger", "params": {"mode": "reversion"}},
        {"strategy": "bollinger", "params": {"mode": "squeeze"}},
        {"strategy": "psar", "params": {}},
        {"strategy": "ichimoku", "params": {}},
    # 자동 자료 수집 라운드(2026-08-18, 사장님 승인 "수집 주기적으로 해")가
    # 가져온 첫 도전자 — 듀얼 스러스트(공개 수식, 시가 기준 범위 돌파).
        {"strategy": "dual_thrust", "params": {"window": 4, "k1": 0.5, "k2": 0.5}},
    # 수급 논문 재현(사장님 자료, 2026-08-18) — SOM 군집 + 군집별 통계.
    # 수급 피처가 없는 시장에서는 관망만 내는 무해한 후보다.
        {"strategy": "supply_som", "params": {}},
        # 슈퍼트렌드(2026-08-19 수집 라운드) — ATR 밴드 래칫 추세.
        {"strategy": "supertrend", "params": {"period": 10, "mult": 3.0}},
        # 가치 닻(2026-08-19, KIS 사례 채택) — 자기 역사 대비 저PBR 구간만
        # 보유. 재료(val_pbr)는 한국 주식에만 붙는다 — 없는 시장은 관망.
        {"strategy": "value_anchor", "params": {"quantile": 0.4}},
        # 코너스 RSI(2) — 200일선 위에서만 극단 눌림을 사고 5일선 복귀에
        # 판다(2026-08-19 수집). 진입은 기존 부품 조합으로도 표현되지만
        # **청산이 다르다**(RSI 중심선이 아니라 가격의 단기선 복귀).
        {"strategy": "connors_rsi2",
         "params": {"rsi_period": 2, "entry": 10.0, "exit_ma": 5,
                    "trend_window": 200}},
        # 내부 봉 강도(2026-08-22 수집) — 종가가 **그날 범위의 어디에**
        # 앉았는가. 링의 다른 후보들이 못 보는 정보다(대부분 종가만 보고,
        # 고저가를 보는 것들도 여러 봉에 걸친 극단을 본다).
        {"strategy": "ibs", "params": {"entry": 0.2, "exit": 0.8}},
        # 월말·월초 효과(2026-08-23, 가설 우선 방침의 1호) — 연금·적립식
        # 펀드의 월말 매수는 가격에 둔감하다는 **수급 가설**. 달력만 보는
        # 규칙이라 선견 여지가 0이다. 가설이 틀렸으면 오디션에서 지고,
        # 그 기각도 기록이다.
        {"strategy": "turn_of_month", "params": {"entry_day": 25, "exit_day": 3}},
        # 실적 발표 후 표류(2026-08-23, 가설 우선 2호) — 정보의 점진적
        # 확산 + 기관의 분할 집행이라는 가설. 발표일 컬럼(earn_day)이
        # 없는 시장(한국·코인)은 관망 — 무해하다.
        {"strategy": "pead", "params": {"min_jump": 0.02, "hold_days": 20}},
        # 옵션 만기 주간(2026-08-23, 가설 우선 3호) — 만기가 시키는 결제·
        # 롤오버·헤지 되감기는 가격에 둔감하다는 **수급 가설**. 달력만 보는
        # 규칙(셋째 금요일 주)이라 선견 여지가 0이다.
        {"strategy": "expiry_week", "params": {}},
        # FOMC 사전 표류(2026-08-23, 가설 우선 4호) — 1년 전 공표되는
        # 발표 달력 앞에서 위험 보상·포지션 정리가 몰린다는 가설(루카·묀히).
        # 달력(2020~2026 정례 일정) 밖의 해는 관망 + 경고.
        {"strategy": "fomc_drift", "params": {}},
        # 가설 6호(2026-08-27) — 목표비중 자금의 월말 강제 리밸런싱.
        # 월중 많이 오른 자산은 규정상 팔릴 차례라 피하고, 많이 내린 자산은
        # 규정상 사줄 차례라 산다. 월말 후보(turn_of_month)와 달력은 겹치지만
        # **부호가 있다** — 같은 월말이라도 종목마다 방향이 다르다.
        {"strategy": "rebalance_flow", "params": {}},
        # 펀딩 과열 회피(2026-08-25, 가설 우선 5호) — 과열 펀딩 = 레버리지
        # 롱 쏠림 = 강제 청산(가격에 둔감한 매도) 연쇄에 취약하다는 가설.
        # funding 컬럼이 없는 시장(주식)은 관망 — 무해하다.
        {"strategy": "funding_guard", "params": {"window": 180, "quantile": 0.9}},
]


def build_challengers(current_spec: dict, seed: str,
                      evolve: bool = True,
                      state_dir: str | None = None) -> list[dict]:
    """그날의 도전자 링을 결정적으로 구성한다 (run_retrain과 verify가 공유).

    고정 기본 후보 + 챔피언 돌연변이(시드 결정적) + 레짐/이벤트 래핑 변형
    + **사용자가 자료에서 가져온 명세**(있으면).

    래핑된 챔피언에는 '벗긴 원본'을 도전시켜 되돌아갈 길을 항상 열어 둔다.

    ⚠️ 사용자 명세는 여기 **도전자로** 들어온다. 챔피언으로 바로 가는 길은
       없다 — 검증이 이 제품의 전부인데 새 전략만 그것을 건너뛰면 앞뒤가
       안 맞는다. 그리고 후보가 늘어난 만큼 다중검정 문턱도 같이 올라간다
       (호출부가 `len(challengers)`로 시도 수를 세므로 저절로 따라온다).
    """
    challengers = _normalize_challengers(DEFAULT_CHALLENGERS, current_spec)
    challengers += _user_specs(state_dir)
    challengers += list(FIXED_CHALLENGERS)
    if not evolve:
        return challengers
    challengers += mutate_champion(current_spec, seed=seed)
    if current_spec["strategy"] != "regime_wrap":
        challengers.append({"strategy": "regime_wrap",
                            "params": {"inner": current_spec,
                                       "trend_window": 200}})
        # 변동성 국면 변형(2026-08-19) — 문턱을 그 시장 자신의 과거 분위수로
        # 잡아 코인·주식 체급 차이에 무관하게 이식된다. 사후 대응(킬스위치·
        # 브레이크)과 상호보완인 **사전 축소** 장치. 채택은 오디션이 결정한다.
        challengers.append({"strategy": "regime_wrap",
                            "params": {"inner": current_spec, "use_trend": False,
                                       "vol_quantile": 0.9}})
    else:
        challengers.append(current_spec["params"]["inner"])
    if current_spec["strategy"] != "event_wrap":
        challengers.append({"strategy": "event_wrap",
                            "params": {"inner": current_spec,
                                       "pad_days": 1, "factor": 0.0}})
        # 마이너 캘린더 변형 — 옵션만기·월말에 비중 절반(위험 회피 전용)
        challengers.append({"strategy": "event_wrap",
                            "params": {"inner": current_spec, "pad_days": 0,
                                       "factor": 0.5, "include_minor": True}})
    else:
        challengers.append(current_spec["params"]["inner"])
    if current_spec["strategy"] != "stop_wrap":
        # 트레일링 스톱 변형 — 고점 대비 -10% 되돌림 청산. 스톱은 이익 장치가
        # 아니라(추세장에서는 수익을 깎기도 한다) 오디션으로만 채택된다.
        challengers.append({"strategy": "stop_wrap",
                            "params": {"inner": current_spec, "trail": 0.10}})
    else:
        challengers.append(current_spec["params"]["inner"])
    return challengers


# 풀링 후보가 깨어나는 문턱 — 링이 보는 구간(결승 120봉)을 스냅샷이
# 덮을 수 있게 되는 날부터 참전한다.
POOL_WAKE_DAYS = 120


def _split_sleeping(challengers: list, state_dir: str,
                    min_days: int = POOL_WAKE_DAYS) -> tuple[list, list]:
    """지금 돌 수 있는 후보와 **아직 잠든** 후보로 가른다 (감사 297).

    잠든 후보는 오늘 링에서 빠지고 시도 수에도 안 들어간다. 다만 후보
    목록에서 사라지는 것은 아니다 — 조건이 차면 다음 밤부터 저절로 돌아온다.
    """
    from quant.strategies.ml import pool_ready
    live, asleep = [], []
    for c in challengers:
        p = (c.get("params") or {}) if isinstance(c, dict) else {}
        pool = p.get("pool")
        if pool is not None and not pool_ready(pool, state_dir, min_days):
            asleep.append(c)
        else:
            live.append(c)
    return live, asleep


# ── 다중검정 문턱 — 롤링 윈도 + 상한 ────────────────────────────
# 누적 시도 수가 단조 증가하면 문턱도 영원히 올라가 진화가 완전히 멈춘다.
# 그래서 문턱 계산에는 '최근 1년 시도 수'만 쓰고 상한을 둔다(장부의 누적
# 총계 trials_total은 투명성 표시용으로 계속 쌓는다).
TRIALS_WINDOW_DAYS = 365
CONFIRM_T_CAP = 1.35

# ── 동시검정(현실성 검사) — 상한이 필요 없는 다중검정 보정 ────────────
# confirm_threshold는 로그+상한이라 시도가 아주 많아지면(연 1만+ 시도) 상한에
# 붙어 더 오르지 않는다 — "후보를 더 세워도 문턱이 그대로"인 구간이 생긴다
# (2026-08-18 CI가 실측으로 드러냄). 그래서 결승 통과자에게 한 관문을 더 건다:
# 오늘 링의 **모든** 실제 후보가 홀드아웃에서 낸 (도전자−챔피언) 일수익 차를
# 놓고, 각 후보의 평균을 0으로 옮긴 귀무 세계를 블록 부트스트랩으로 재생해
# "N명 중 최고 t가 이만큼 나올 확률" p를 직접 잰다(화이트 현실성 검사의
# 경량판). 후보가 늘면 귀무 세계의 최고 t도 자연히 커져 p가 정직하게
# 커진다 — 로그 공식도 상한도 필요 없다.
# 시드는 고정 하나(42) — SOM과 같은 원칙: 좋은 결과를 주는 시드 채택 금지.
RC_BOOT = 500          # 부트스트랩 반복 수
RC_BLOCK = 5           # 블록 길이(봉) — 며칠 단위 자기상관 보존
RC_ALPHA = 0.10        # 승격에 요구하는 최대 p — 결승 t 상한(1.35≈p 0.09)과 동급
RC_MIN_N = 20          # 이보다 짧은 홀드아웃이면 검정 자체가 무의미 — 생략 명시
RC_SEED = 42


def reality_check(diffs, *, n_boot: int = RC_BOOT, block: int = RC_BLOCK,
                  seed: int = RC_SEED) -> dict:
    """'후보 N명 중 최고 성적'이 우연으로 나올 확률 p — 완전 결정적.

    diffs: (봉 수 × 후보 수) 행렬. 각 열은 그 후보의 (도전자−챔피언) 일수익 차.
    반환: {"p", "t_max", "n", "n_cand"} — p가 작을수록 우연으로 보기 어렵다.
    """
    import numpy as np

    d = np.asarray(diffs, dtype=float)
    if d.ndim == 1:
        d = d[:, None]
    d = d[~np.isnan(d).any(axis=1)]
    n, k = d.shape
    if n < 3 or k < 1:
        raise ValueError(f"동시검정에 쓸 표본이 없다(n={n}, k={k})")

    def _max_t(mat) -> float:
        m = mat.mean(axis=0)
        se = mat.std(axis=0, ddof=1) / math.sqrt(len(mat))
        # 차이가 상수(분산 0)인 열은 정보가 없다 — t=0으로 둔다(0/0 방지).
        t = np.divide(m, se, out=np.zeros_like(m), where=se > 1e-300)
        return float(t.max())

    t_obs = _max_t(d)
    centered = d - d.mean(axis=0)          # 귀무가설: 아무도 챔피언을 못 이긴다
    rng = np.random.RandomState(seed)
    n_blocks = -(-n // block)              # ceil
    hits = 0
    for _ in range(n_boot):
        starts = rng.randint(0, n, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        if _max_t(centered[idx]) >= t_obs:
            hits += 1
    return {"p": round((1 + hits) / (n_boot + 1), 4),
            "t_max": round(t_obs, 4), "n": n, "n_cand": k}


def spec_key(spec: dict) -> str:
    """설정을 **문자열 하나**로 — 종목을 가로질러 같은 설정을 알아보는 열쇠.

    패널 관문은 "한 **설정**이 여러 종목에서 함께 좋은가"를 묻는다. 그러려면
    종목이 달라도 같은 설정임을 알아봐야 하고, 그 동일성 판정을 한 곳에서만
    한다(같은 규칙을 두 곳에 적으면 언젠가 갈라진다 — FROZEN_IDEAS ①).
    """
    return json.dumps(spec, sort_keys=True, ensure_ascii=False)


def holdout_diffs(champion_spec: dict, specs: list[dict], df,
                  tail: int, build, bt_kwargs: dict) -> dict:
    """후보별 홀드아웃 수익 차를 **날짜 색인 그대로** 돌려준다.

    동시검정(행렬)과 패널 관문(날짜별 횡단 평균)이 **같은 계산을 두 번 돌지
    않도록** 여기 한 곳에서 만든다. 패널은 날짜가 있어야 종목을 가로질러
    같은 날끼리 묶을 수 있고, 동시검정은 날짜가 필요 없어 값만 쓴다.

    평가에 실패한 후보는 빠진다(n_cand가 그만큼 줄어 장부에 남는다).
    """
    from quant.backtest import Backtester

    r_champ = Backtester(build(champion_spec), **bt_kwargs).run(df).returns
    out: dict = {}
    for spec in specs:
        try:
            r_ch = Backtester(build(spec), **bt_kwargs).run(df).returns
        except Exception as exc:  # noqa: BLE001 — 한 후보 실패로 검정을 죽이지 않는다
            log.warning("동시검정 후보 재생 실패 %s: %s", spec, exc)
            continue
        out[spec_key(spec)] = (r_ch - r_champ).iloc[-tail:].fillna(0.0)
    return out


def _holdout_diff_matrix(champion_spec: dict, specs: list[dict], df,
                         tail: int, build, bt_kwargs: dict):
    """오늘 링의 모든 후보를 홀드아웃에서 재생해 수익 차 행렬을 만든다.

    ⚠️ 계산은 ``holdout_diffs``가 한다 — 여기서 다시 백테스트하면 같은 값을
    두 곳에서 만들게 되고, 언젠가 갈라진다.
    """
    import numpy as np

    diffs = holdout_diffs(champion_spec, specs, df, tail, build, bt_kwargs)
    cols = [s.to_numpy() for s in diffs.values()]
    return np.column_stack(cols) if cols else None



def confirm_threshold(trials_recent: int) -> float:
    """결승전(홀드아웃) t-임계 — 최근 시도 수에 로그 비례, 상한 고정."""
    return min(CONFIRM_T_CAP,
               1.0 + 0.5 * math.log10(1 + max(0, trials_recent) / 1000))


def recent_trials(market: str, symbol: str, asof: str,
                  state_dir: str = STATE_DIR,
                  window_days: int = TRIALS_WINDOW_DAYS) -> int:
    """재학습 장부에서 이 종목의 최근 window_days일 도전자 수 합계."""
    path = os.path.join(state_dir, HISTORY_FILE)
    if not os.path.exists(path):
        return 0
    import datetime as _dt
    try:
        cutoff = (_dt.date.fromisoformat(asof)
                  - _dt.timedelta(days=window_days)).isoformat()
    except ValueError:
        return 0
    total = 0
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if (r.get("market") == market and r.get("symbol") == symbol
                    and cutoff <= str(r.get("asof", "")) <= asof):
                total += int(r.get("n_candidates") or 0)
    return total


def verify_retrain(asof: str, *, market: str | None = None,
                   symbol: str | None = None,
                   state_dir: str = STATE_DIR,
                   confirm_window: int = 120,
                   sample: int = 0) -> list[dict]:
    """그날의 재학습 결정을 스냅샷·시드로 재실행해 기록과 대조한다.

    '조작 불가'를 주장이 아니라 사실로 만드는 검증기: 누구나
        python -m quant verify --date 2026-08-06
    로 ① 데이터 해시 일치 ② 같은 링 재구성 ③ 같은 승격 결정을 확인할 수 있다.
    반환: 종목별 {"key", "ok", "detail"} 목록.
    """
    from quant.backtest.costs import CostModel
    from quant.utils.repro import data_sha256, env_fingerprint, load_snapshot

    path = os.path.join(state_dir, HISTORY_FILE)
    results: list[dict] = []
    if not os.path.exists(path):
        return [{"key": "-", "ok": False, "detail": "재학습 기록 파일 없음"}]
    with open(path, encoding="utf-8") as f:
        records = [json.loads(ln) for ln in f.read().splitlines() if ln.strip()]
    todo = [r for r in records if r.get("asof") == asof
            and (market is None or r.get("market") == market)
            and (symbol is None or r.get("symbol") == symbol)]
    if not todo:
        # ⚠️ 기록이 **없는 날**은 재현성 사건이 아니다 (2026-08-18 실측).
        #    광복절 연휴에 배치가 정당하게 기록을 안 남겼는데, 이 자리가
        #    ✘를 돌려줘 "🚨 재현성 감사 불일치 — 조작 불가능 주장이 걸린
        #    문제"라는 최고 수위 경보가 이틀 연속 울렸다. 재현성 감사의
        #    주장은 **존재하는 기록**에 대한 것이다 — 없는 기록은 재현할
        #    수 없는 게 아니라 재현할 것이 없다.
        #
        #    기록의 **부재**를 감시하는 장치는 따로 있다(배치 실패 경보·
        #    멈춘 장부 데드맨). 여기서 또 울리면 같은 사건에 다른 이름의
        #    경보가 두 번 울리고, 그중 하나는 틀린 이름(조작 의심)이다 —
        #    늑대소년이 된 경보는 진짜 조작이 난 날에도 무시된다.
        return [{"key": "-", "ok": True, "no_records": True,
                 "detail": f"{asof} 기록 없음 — 재현할 결정이 없는 날입니다"
                           "(휴장 건너뜀·배치 미실행). 기록의 부재는 배치 "
                           "경보·데드맨이 따로 감시합니다"}]

    # 표본 감사 — 20종목 전체 재현은 몇십 분이 걸려 매일 자동으로 돌리기
    # 어렵다. 날짜를 시드로 결정적으로 골라 매일 다른 종목을 감사하면,
    # 한 주면 전 종목을 훑으면서도 실행 시간은 일정하다.
    # ⚠️ 자른 사실을 결과에 남긴다 — 조용한 표본 축소는 '전부 검증했다'로
    #    읽히고, 그건 이 프로젝트에서 가장 하지 말아야 할 종류의 침묵이다.
    skipped = 0
    if sample and len(todo) > sample:
        import random
        picked = random.Random(f"verify:{asof}").sample(todo, sample)
        skipped = len(todo) - len(picked)
        todo = picked

    if skipped:
        results.append({
            "key": "-", "ok": True,
            "detail": f"표본 감사: {len(todo)}종목만 재현(미검사 {skipped}종목) "
                      f"— 날짜 시드로 매일 다른 표본을 고른다"})

    for rec in todo:
        key = f"{rec['market']}:{rec['symbol']}"
        df = load_snapshot(state_dir, asof, rec["market"], rec["symbol"])
        if df is None:
            results.append({"key": key, "ok": False,
                            "detail": "스냅샷 없음(해시 기록 이전 날짜)"})
            continue
        got_hash = data_sha256(df)
        if rec.get("data_sha256") and got_hash != rec["data_sha256"]:
            results.append({"key": key, "ok": False,
                            "detail": "데이터 해시 불일치 — 스냅샷 변조 의심"})
            continue
        before = rec.get("champion_before")
        if not before:
            results.append({"key": key, "ok": False,
                            "detail": "champion_before 없음(구버전 기록)"})
            continue
        # 사용자 명세는 **장부에 적힌 그날 것**을 쓴다(폴더가 아니라).
        # 옛 기록에는 이 칸이 없다 — 그때는 기능이 없었으므로 빈 목록이
        # 맞다. 폴더를 읽으면 오늘 폴더로 어제를 재현하게 된다.
        challengers = build_challengers(before, seed=rec["mutation_seed"])
        challengers += list(rec.get("user_specs") or [])
        decision = nightly_retrain(
            df, before, challengers, confirm_window=confirm_window,
            select_t=float(rec.get("select_t", 2.0)),
            confirm_t=float(rec.get("confirm_t", 1.0)),
            # 옛 기록(폴드 게이트 이전)은 0으로 재현 — 알고리즘 진화가
            # 과거 결정의 재현 검증을 깨뜨리지 않게 장부 값을 따른다.
            select_folds=int(rec.get("select_folds", 0)),
            # 관문 세대 — v2부터 '선별기는 검정보다 엄격할 수 없다'는 규칙이
            # 생겼다. 옛 기록(v1)은 그 규칙이 없던 세계의 결정이므로 그대로
            # 재현한다. 과거 기록은 고치지 않는다.
            clamp_screen=int(rec.get("gate_version", 1)) >= 2,
            # v3부터 결승 통과자에게 동시검정(현실성 검사)이 붙었다. 옛
            # 기록(v1·v2)은 그 관문이 없던 세계의 결정 — 그대로 재현한다.
            reality_gate=int(rec.get("gate_version", 1)) >= 3,
            # 그날의 오디션 조건을 장부에서 그대로 되살린다. 실측 비용은
            # 날마다 변하므로 '오늘 값'으로 어제 결정을 재생하면 재현이
            # 깨진다 — 결정의 전제는 결정과 함께 보존돼야 한다.
            # 옛 기록(audition_env 이전)은 그때 쓰던 가정 비용으로 폴백.
            **_audition_kwargs_from_record(rec))
        same_promoted = bool(decision["promoted"]) == bool(rec["promoted"])
        same_champion = True
        if decision["promoted"] and rec["promoted"]:
            got = decision["champion"]
            same_champion = (got["strategy"] == rec["champion_strategy"]
                             and got.get("params") == rec.get("champion"))
        ok = same_promoted and same_champion
        env_note = ""
        if rec.get("env") and rec["env"] != env_fingerprint():
            env_note = (" · 주의: 실행 환경이 기록과 다름"
                        f"(기록 {rec['env']} vs 현재 {env_fingerprint()})"
                        " — 불일치 시 조작이 아니라 라이브러리 버전 차이일 수 있음")
        results.append({"key": key, "ok": ok,
                        "detail": (("재현 일치 — 같은 데이터·같은 코드에서 "
                                    "같은 결정" if ok else
                                    f"결정 불일치: 기록 promoted={rec['promoted']}"
                                    f" vs 재실행 {decision['promoted']}")
                                   + env_note)})
    return results


# 마지막 봉이 며칠까지 묵어도 되는가. 코인은 24시간 시장이라 짧고,
# 주식은 주말·연휴가 있어 길다. 넘으면 그 종목은 **실패**로 멈춘다 —
# 묵은 시세로 챔피언을 다시 뽑는 것보다 안 뽑는 쪽이 낫다(감사 284).
MAX_BAR_AGE_DAYS = {"crypto": 2, "": 5}


def _bar_age_days(asof: str, today: str | None = None) -> int | None:
    """마지막 봉이 며칠 묵었나. 날짜를 못 읽으면 None(판단하지 않는다)."""
    import datetime as _dt

    try:
        day = _dt.date.fromisoformat(str(asof)[:10])
        now = (_dt.date.fromisoformat(today) if today else _dt.date.today())
    except (TypeError, ValueError):
        return None
    return (now - day).days


def run_retrain(market: str, symbol: str, *, timeframe: str = "1d",
                limit: int = 800, state_dir: str = STATE_DIR,
                confirm_window: int = 120,
                require_real_data: bool = True,
                evolve: bool = True) -> dict:
    """데이터 수신 → 대결 → 승격/유지 → 기록까지의 야간 재학습 1회분."""
    from quant.data import get_provider

    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=limit)
    if df.empty:
        raise RuntimeError(f"{market}/{symbol}: 데이터 수신 실패")
    if require_real_data and df.attrs.get("synthetic_fallback"):
        raise RuntimeError(
            f"{market}/{symbol}: 실데이터 수신 실패 → 합성 폴백 감지. "
            "가짜 데이터로 재학습·승격하면 안 되므로 중단합니다.")
    if market == "crypto":
        # 펀딩비 컬럼 — ML x_funding 피처 재료. 스냅샷·해시에 함께 보존돼
        # verify가 같은 피처로 그날의 대결을 재현할 수 있다(실패 시 생략).
        from quant.data.funding import attach_funding
        df = attach_funding(df, symbol)
        from quant.data.openinterest import attach_open_interest
        df = attach_open_interest(df, symbol)
    if market in ("us_stock", "kr_stock"):
        # 실적 발표일 표식(earn_day) — PEAD 도전자 전용, 캐시만 읽는다
        # (오프라인). 캐시에 없으면 컬럼 자체가 안 붙고 PEAD는 관망한다.
        # 한국 캐시는 DART 키가 있을 때만 일일 배치가 채운다(2026-08-23).
        from quant.data.earnings import attach_earnings_days
        df = attach_earnings_days(df, symbol, state_dir)
    if market == "kr_stock":
        # 외국인·기관 수급(z-점수) — 한국 주식 고유의 수급 피처(실패 시 생략)
        from quant.data.krx import attach_krx_flows, attach_krx_value
        df = attach_krx_flows(df, symbol)
        # 가치(도전자 전용, 2026-08-19) — val_* 이름이라 챔피언 동결 무관.
        df = attach_krx_value(df, symbol)
    # 크로스에셋 컬럼(x_*) — 시장 바깥의 맥락(BTC/SPY/금리/환율). 펀딩과 같은
    # 원리로 스냅샷·해시에 보존된다(실패 시 조용히 생략 — 선택적 피처).
    from quant.data.crossasset import attach_cross_asset
    df = attach_cross_asset(df, market, symbol)

    champions = load_champions(state_dir)
    key = _key(market, symbol)
    entry = champions.get(key) or {**DEFAULT_CHAMPION, "promotions": 0}
    current_spec = {"strategy": entry["strategy"], "params": entry["params"]}
    asof = str(df.index[-1])[:10]              # 기준 시점 = 데이터 마지막 봉(재현 가능)

    # ⚠️ **묵은 봉이 '오늘 이미 했다'로 읽히고 있었다**(감사 284).
    #    2026-08-16 밤, 코인 5종의 마지막 봉이 **2026-03-04**였다(감사 261의
    #    페이지네이션 결함). 그런데 챔피언의 last_run_asof도 2026-03-04이라
    #    아래 멱등 가드가 그대로 걸렸고, 화면에는 "오늘 이미 재학습함,
    #    건너뜀"이 찍혔다. **'오늘'이 아니라 165일 전이었다.**
    #
    #    그래서 시세 공급이 얼어붙은 165일 동안, 코인 5종은 오디션을 한 번도
    #    열지 못한 채 옛 챔피언으로 **실제 돈을 굴렸고** 배치는 매일 조용했다.
    #    정체 경보(감사 243)가 뒤늦게 잡아 주긴 했지만, 그건 사후 보고다 —
    #    멈춰야 할 자리에서 멈추지 않았다.
    #
    #    개수를 채웠다와 최신까지 받았다가 다르듯, **같은 봉이다**와
    #    **오늘 것이다**도 다르다. 데이터가 묵었으면 조용히 건너뛰지 말고
    #    시끄럽게 실패한다 — 그 종목만 실패로 잡히고 나머지는 계속 돈다.
    if require_real_data:
        _age = _bar_age_days(asof)
        _cap = MAX_BAR_AGE_DAYS.get(market, MAX_BAR_AGE_DAYS[""])
        if _age is not None and _age > _cap:
            raise RuntimeError(
                f"{market}/{symbol}: 마지막 봉이 {asof}로 {_age}일 묵었습니다"
                f"(허용 {_cap}일). 묵은 시세로 챔피언을 다시 뽑지 않습니다 — "
                "시세 공급 경로를 확인하세요.")

    # 멱등 가드 — 같은 봉(같은 날)에 이미 대결했으면 통째로 건너뛴다.
    # 예비(재시도) 크론이 성공한 날을 다시 돌려 기록을 중복시키지 않게 한다.
    if entry.get("last_run_asof") == asof:
        print(f"[{asof}] {market}/{symbol} — 같은 봉으로 이미 재학습함, 건너뜀")
        return {"skipped": True, "key": key, "champion": entry}

    # 도전자 = 고정 기본 후보 + 챔피언 돌연변이(진화 탐색) + 레짐/이벤트 변형.
    # 시드가 날짜+종목이라 결정적 — verify가 같은 링을 재구성할 수 있다.
    challengers = build_challengers(current_spec, seed=f"{asof}:{key}",
                                    evolve=evolve)

    # ── 다중검정 보정 — 오디션을 반복할수록 '운 좋은 승자'가 나올 확률이
    # 커진다. 누적 시도 횟수를 장부에 남기고, 그에 비례해 승격 관문을 높인다.
    #   선발전: **선별기**다. 고정 스크리닝 문턱(SELECT_SCREEN_T)만 쓴다.
    #   결승전: '최근 1년' 시도 수에 로그 비례 + 상한(진화가 영원히 멈추는
    #   것을 방지) — DSR 정신의 보수적 근사. 누적 총계는 표시용으로만 쌓는다.
    #
    # ⚠️ 예전에는 선발전에 sqrt(2·ln N)을 걸었다. 선발전과 결승전은 겹치지
    #    않는 구간을 보므로 **같은 날 후보 수는 결승전을 부풀리지 않는다** —
    #    그 보정을 선발전에 또 거는 것은 같은 다중성을 두 번 세는 것이었고,
    #    그 결과 결승전이 한 번도 작동하지 않았다(2026-08-14 실측 15/15).
    #    진짜 다중성은 '매일 반복'이고 그건 결승 문턱이 계속 맡는다.
    # ⚠️ **못 도는 후보는 '찾아본 것'이 아니다** (2026-08-20 감사 297).
    #    풀링 후보는 스냅샷이 모자라면 풀을 못 만들고 챔피언과 똑같은 신호를
    #    낸다. 그걸 시도 수에 넣으면 문턱만 올라가, 진짜로 뒤져서 찾은
    #    결과까지 같이 깎인다.
    #
    #    실측 2026-08-19: 후보 802개 중 35개가 무동작이었고 그중 13개가
    #    pool="peers"였다(스냅샷 14일치 — 학습 블록 대부분이 자기 시점의
    #    폴더를 못 찾는다).
    #
    #    ⚠️ **후보 목록에서 빼는 것이 아니다**(사장님 지적: "죽은 peers도
    #       나중엔 성과 좋을 수 있는 거 아니야?"). 맞다 — peers는 성과가
    #       나쁜 게 아니라 아직 못 도는 것이고, universe와 달리 생존 편향이
    #       없어 장기적으로는 더 정직한 쪽이다. 스냅샷이 쌓이면 이 관문은
    #       저절로 열리고 그날부터 링에 다시 선다. 지금 빼는 것은 후보가
    #       아니라 **헛세기**다.
    challengers, asleep = _split_sleeping(challengers, state_dir)
    if asleep:
        log.info("아직 못 도는 후보 %d개는 시도 수에서 뺍니다(스냅샷 부족) "
                 "— 목록에는 남고, 쌓이면 다시 링에 섭니다", len(asleep))
    n_cand = len(challengers)
    trials_total = int(entry.get("trials_total", 0)) + n_cand
    entry["trials_total"] = trials_total
    trials_recent = recent_trials(market, symbol, asof, state_dir) + n_cand
    confirm_t_eff = confirm_threshold(trials_recent)
    # 선별기는 자기가 먹여 살리는 검정보다 엄격할 수 없다.
    select_t_eff = min(SELECT_SCREEN_T, confirm_t_eff)
    # ⚠️ **실제로 적용되는** 문턱을 찍는다. 예전에는 조정 전 값(2.52)을 찍어,
    #    아무도 넘은 적 없는 문턱을 매일 화면에 보여줬다.
    select_t_used = effective_select_t(select_t_eff, confirm_t_eff)
    screen_note = ("" if select_t_used == select_t_eff else
                   f" (다중검정 보정값 {select_t_eff:.2f}는 결승 문턱보다 "
                   "엄격해 적용하지 않는다 — 보정은 결승전이 맡는다)")
    print(f"  🔬 다중검정 보정: 오늘 후보 {n_cand}개 · 최근 1년 "
          f"{trials_recent:,}개 · 누적 검증 도전자 {trials_total:,}개 → "
          f"선발(선별) t≥{select_t_used:.2f} · 결승(판정) t≥{confirm_t_eff:.2f}"
          f" (상한 {CONFIRM_T_CAP}){screen_note}")

    # 오디션 환경을 실제 운용 환경과 맞춘다 — '챔피언을 뽑는 세계'와 '돈이
    # 도는 세계'가 다르면, 실제로는 낼 수 없는 성과를 근거로 챔피언이 뽑힌다.
    #   ① 비용: 가정이 아니라 실측(개장 갭 포함). 한국주식은 가정 28bp vs
    #      실측 ~113bp(왕복)로 4배 어긋나 있었다. 단, 갭을 시가 체결로
    #      모델링하는 시장에서는 비용에 또 얹지 않는다(이중 계상 금지).
    #   ② 체결: 다음 세션 시가(주식). 종가 체결은 개장 갭을 공짜로 건너뛴다.
    #   ③ 밴드: 실제 운용의 리밸런스 밴드를 그대로 적용 — 밴드 없이 평가하면
    #      고회전 전략이 부당하게 유리해진다.
    from quant.live.daily import (IMMEDIATE_FILL_MARKETS, _rebalance_band_rel,
                                  measured_cost_model)
    audition_next_open = market not in IMMEDIATE_FILL_MARKETS
    # 갭을 가격으로 겪는(next_open_fill) 시장에 실측 갭을 비용으로까지 더하면
    # 두 번 물린다 — 그래서 모델링 여부를 넘겨 준다(2026-08-11 이중계상 수정).
    audition_cost = measured_cost_model(market, state_dir,
                                        models_gap=audition_next_open,
                                        symbol=symbol)
    audition_band = _rebalance_band_rel(market, state_dir)
    decision = nightly_retrain(df, current_spec, challengers,
                               # 패널 관문 재료 — 여러 종목에 똑같이 서는
                               # 고정 격자 설정만. 판정에는 아직 안 쓰이고
                               # 장부에 나란히 기록된다(사장님 ①안: 관문을
                               # 바꾸되 기존 관문도 계속 남긴다).
                               panel_specs=shared_panel_specs(asof),
                               confirm_window=confirm_window,
                               select_t=select_t_eff,
                               confirm_t=confirm_t_eff,
                               cost_model=audition_cost,
                               next_open_fill=audition_next_open,
                               rebalance_band=audition_band,
                               select_folds=SELECT_FOLDS)

    # 재현성 — 입력 스냅샷 보존 + 해시·시드·환경 지문 기록 → verify로 재검증 가능
    from quant.utils.repro import (code_sha, data_sha256, env_fingerprint,
                                   save_snapshot)
    try:
        save_snapshot(df, state_dir, asof, market, symbol)
    except Exception as exc:  # noqa: BLE001 — 스냅샷 실패가 재학습을 막으면 안 된다
        log.warning("스냅샷 저장 실패 %s: %s", key, exc)

    if decision["promoted"]:
        prev_trials = entry.get("trials_total")
        prev_parliament = entry.get("parliament")
        entry = {**decision["champion"],
                 "promoted_at": asof,
                 "promotions": int(entry.get("promotions", 0)) + 1,
                 "trials_total": prev_trials,
                 "parliament": prev_parliament}

    # ── 의회 갱신 — 교체가 아니라 혼합. 오디션 통과자만 입성하고, 의석
    # 비중은 홀드아웃 성과로 서서히(EMA) 이동한다. 상관 과다 의원은 탈락
    # (다양성 강제). 리더가 strategy/params 자리를 유지해 기존 경로와 호환.
    from quant.live.parliament import update_parliament
    entry["parliament"] = update_parliament(
        entry, df, build=build_strategy,
        # 의석 비중도 오디션과 같은 비용으로 — 여기만 가정을 쓰면 '싸게 평가된
        # 고회전 의원'이 의석을 더 가져간다(같은 격차의 재발).
        cost_model=measured_cost_model(market, state_dir,
                                       models_gap=audition_next_open,
                                       symbol=symbol),
        next_open_fill=audition_next_open,
        rebalance_band=_rebalance_band_rel(market, state_dir),
        confirm_window=confirm_window,
        promoted_spec=decision["champion"] if decision["promoted"] else None,
        # ⚠️ **두 번째 문**(감사 276). 승격은 "챔피언보다 더 나은가"만 묻고,
        #    189회 중 1회만 열렸다 — 그래서 20계좌 전부 1석, 챔피언 19/20이
        #    파라미터까지 동일하다. 종목은 20개인데 모델은 하나다.
        #    오늘 진 후보들을 **다른 질문**에 다시 세운다: "못하지 않으면서
        #    상관이 낮은가." 판정과 관문은 전부 parliament 쪽에 있다 —
        #    여기서 고르면 그 기준이 두 곳에 생긴다(㉞).
        applicants=[{**c["spec"], "select_t": c.get("t_stat")}
                    for c in (decision.get("candidates") or [])])
    leader = entry["parliament"][0]
    entry["strategy"], entry["params"] = leader["strategy"], leader["params"]

    entry["last_run_asof"] = asof              # 멱등 가드 기준(재시도 크론용)
    champions[key] = entry
    save_champions(champions, state_dir)

    # verify 대조용 champion 필드는 '오디션 결정의 결과'를 기록한다 — 의회
    # 리더는 비중 이동으로 결정과 무관하게 바뀔 수 있어 여기 쓰면 안 된다.
    decided = decision["champion"] if decision["promoted"] else current_spec
    append_history({
        "asof": asof, "market": market, "symbol": symbol, "bars": len(df),
        "promoted": decision["promoted"], "reason": decision["reason"],
        "champion": decided["params"],
        "champion_strategy": decided["strategy"],
        "champion_before": current_spec,       # verify가 대결을 재구성할 출발점
        "n_candidates": len(decision.get("candidates", [])),
        # 무효 후보 — 챔피언과 신호가 한 봉도 다르지 않아 링에서 뺀 설정들.
        # 이름을 남긴다: 어떤 기능이 '시험 중'인 척하며 실제로는 꺼져 있었는지
        # 장부만 봐도 드러나야 한다(감사 127의 재발 방지).
        "inert_candidates": decision.get("inert", []),
        # 공회전 표식 — 후보 대부분이 챔피언 사본이라 대결이 성립하지 않은 날.
        # '이긴 후보가 없다'(정상)와 '비교를 못 했다'(고장)는 다른 사건이다.
        "vacuous": bool(decision.get("vacuous")),
        "trials_total": trials_total,
        # select_t = 다중검정 보정이 **요청한** 값(verify 재현 입력).
        # select_t_used = 그날 실제로 후보를 거른 문턱. 둘이 다른 날이 대부분이고,
        # 예전에는 앞의 것만 적어 175/175건이 "선발 t≥2.52"로 남았다 —
        # 아무도 넘은 적 없는 문턱이다(감사 258).
        "select_t": round(select_t_eff, 3), "confirm_t": round(confirm_t_eff, 3),
        "select_t_used": round(effective_select_t(select_t_eff, confirm_t_eff), 3),
        "select_folds": SELECT_FOLDS,  # 폴드 일관성 게이트 — verify 재현용
        # 관문 세대 — v2: 선발전은 선별기, 다중검정 보정은 결승전이 맡는다.
        # v3(2026-08-18): 결승 통과자에게 동시검정(현실성 검사)이 추가됐다 —
        # 오늘 링 전체를 놓고 '최고 성적이 우연일 확률'을 부트스트랩으로 잰다.
        # verify가 옛 결정을 옛 규칙으로 재현하기 위한 표식.
        "gate_version": 3,
        # 동시검정 결과 — 결승까지 간 날만 값이 있다(그 외 None). p가 클수록
        # "후보가 많아 하나쯤 우연히 좋아 보였을" 가능성이 크다는 뜻.
        "reality_check": decision.get("reality_check"),
        # 그날 실제로 나온 숫자(감사 235). 문턱만 적고 기록을 안 적으면
        # "왜 안 바뀌었나"에 장부가 답하지 못한다.
        "audition_result": audition_evidence(decision),
        # 오디션 환경 — verify가 그날의 조건 그대로 재현하기 위한 값들.
        # 비용은 실측이라 날마다 변한다: 오늘 값으로 어제 결정을 재생하면
        # 재현이 깨진다. 결정의 전제를 결정과 함께 남기는 것이 장부의 일이다.
        "audition_env": {
            "fee": round(float(audition_cost.fee), 8),
            "slippage": round(float(audition_cost.slippage), 8),
            "next_open_fill": bool(audition_next_open),
            "rebalance_band": round(float(audition_band), 6),
        },

        "mutation_seed": f"{asof}:{key}",
        # ⚠️ 그날 링에 선 **사용자 명세를 그대로** 남긴다. 사용자가
        #    자료를 추가·삭제하면 폴더는 바뀌지만 어제의 결정은 어제의
        #    링에서 나온 것이다. 폴더를 다시 읽어 재현하면 "재현 실패"가
        #    뜨는데 원인은 결함이 아니라 폴더 변경이고, 그러면 재현
        #    검사가 늑대소년이 된다(감사 습관: 결정의 전제는 결정과
        #    함께 보존한다).
        "user_specs": [c for c in challengers if c.get("strategy") == "spec"],
        "code_sha": code_sha(),
        "data_sha256": data_sha256(df),
        "env": env_fingerprint(),      # 라이브러리 버전 차이로 인한 불일치 판별용
        # 피처셋 태그 — 피처는 '가설 그룹' 단위로 추가되며, 성과 변화가
        # 어느 배치 이후인지 이 태그로 추적한다(피처 중요도로 판단 금지).
        "feature_set": _feature_set(),
        # ⚠️ 위 태그는 **선언**이다 — "이런 피처를 본다"고 사람이 적어 둔
        #    이름표일 뿐, 그날 밤 실제로 붙은 것과 같다는 보장이 없다
        #    (감사 271). 코인 펀딩·미결제약정 3개는 몇 주 동안 하나도 안
        #    붙었는데 태그는 내내 같았고, 그래서 90일 판정 시계도 리셋되지
        #    않았다. 죽은 피처가 되살아나면 **모델이 보는 것이 달라지는데
        #    시계는 그대로** — 90일 뒤에 "그 표본은 섞여 있었다"를 알게 된다.
        #    그래서 그날 밤 **실제로 붙은 선택 피처**를 함께 남긴다.
        "features_used": _features_used(df),
        # 의회 구성 — "챔피언 교체" 대신 "구성 변화"의 서사이자 감사 흔적
        "parliament": [{"strategy": m["strategy"], "weight": m["weight"]}
                       for m in entry.get("parliament", [])],
    }, state_dir)

    label = "🔁 교체" if decision["promoted"] else "🏆 유지"
    print(f"[{asof}] {market}/{symbol} — 챔피언 {label}: "
          f"{champions[key]['strategy']} {champions[key]['params']}")
    print(f"  근거: {decision['reason']}")
    return {"key": key, "asof": asof, "champion": champions[key], **decision}


# 며칠을 건너뛰어야 '주말'이 아니라 '고장'인가 — 정상 주말은 2일, 긴 연휴
# (설·추석·미국 장기 휴장)까지 감안해 5일을 넘으면 설명이 안 된다. 문턱을
# 낮게 잡으면 연휴마다 경보가 울리고, 그러면 진짜 신호와 구별되지 않는다
# (감사 99에서 배운 것 — 매일 울리는 경보는 꺼진 경보와 같다).
STALE_SKIP_DAYS = 5


def stale_targets(skipped: list, state_dir: str = STATE_DIR,
                  today: str | None = None,
                  threshold: int = STALE_SKIP_DAYS) -> dict:
    """건너뛴 종목 중 **주말로 설명되지 않는** 것들 → {키: 며칠째}.

    멱등 가드는 '새 봉이 없으면 건너뛴다'라서, 시세 공급이 얼어붙어도 주말과
    똑같이 조용하다. 챔피언은 며칠째 재검증되지 않은 채 계속 돈을 굴리는데
    장부에는 아무 흔적이 없다 — 감사 220이 매매 쪽에서 잡은 것과 같은 병이
    학습 쪽에 남아 있었다. 마지막으로 실제로 돈 날(last_run_asof)과 오늘의
    간격으로 잰다.
    """
    import datetime as _dt

    if not skipped:
        return {}
    try:
        now = (_dt.date.fromisoformat(today) if today
               else _dt.date.today())
    except ValueError:
        return {}
    champions = load_champions(state_dir)
    out: dict[str, int] = {}
    for key in skipped:
        asof = (champions.get(key) or {}).get("last_run_asof")
        if not asof:
            continue
        try:
            days = (now - _dt.date.fromisoformat(str(asof))).days
        except ValueError:
            continue
        if days > threshold:
            out[key] = days
    return out


# 패널 관문 장부 — 밤마다 한 줄. 종목별 관문 장부(retrain_history)와 **나란히**
# 남는다(사장님 ①안). 나중에 "관문을 바꿔서 결과가 달라진 건가"를 물으면,
# 같은 밤의 두 관문이 각각 뭐라고 했는지 장부만 보고 답할 수 있어야 한다.
PANEL_FILE = "panel_history.jsonl"

# 패널 설정별 t의 **참조** 문턱. 다중검정 보정은 여기 걸지 않는다 — 아래
# 패널 동시검정(설정 개수를 세는 부트스트랩)이 통째로 맡는다. 문턱과
# 부트스트랩 양쪽에 보정을 걸면 같은 다중성을 두 번 세게 되고, 그 실수는
# 이 저장소가 이미 한 번 했다(2026-08-14: 선발전과 결승전에 같은 보정을
# 이중으로 걸어 결승전이 15/15 무력화됐다).
PANEL_T_REF = CONFIRM_T_CAP


def _today_iso() -> str:
    import datetime as _dt

    return _dt.date.today().isoformat()


def record_panel(asof: str, collector, state_dir: str = STATE_DIR,
                 n_symbols_seen: int = 0) -> dict:
    """그날 모은 패널 재료로 판정하고 장부에 한 줄 남긴다 — **기록만 한다.**

    승격 판단은 아직 이 값을 보지 않는다. 사장님 ①안의 조건이 "관문을 바꾸되
    기존 관문도 계속 기록한다"이므로, 먼저 두 관문이 같은 밤에 각각 뭐라고
    하는지를 며칠 쌓는다. 그 대조 없이 관문을 갈아 끼우면, 나중에 성적이
    변했을 때 **관문 때문인지 시장 때문인지 구별할 방법이 없다.**

    다중검정은 문턱이 아니라 **부트스트랩**이 맡는다. 패널 계열을 설정별로
    한 표에 세우고 "설정 N개 중 최고 t가 우연으로 나올 확률"을 직접 잰다 —
    설정을 늘리면 귀무 세계의 최고 t도 같이 커져 p가 정직하게 커진다.
    ⚠️ 세는 것은 **설정 개수**다. 종목 수가 아니다 — 한 설정을 40종목에
       돌리는 것은 40번의 시도가 아니라 한 번의 시도를 정밀하게 재는 것이다.
    """
    verdicts = collector.verdicts(t_threshold=PANEL_T_REF)
    judged = [v for v in verdicts if not v.get("skipped")]
    rec: dict = {
        "asof": asof,
        "n_specs_collected": len(verdicts),
        # 그날 밤 패널에 세운 설정 수(회전 부분집합) — 며칠에 걸쳐 명단
        # 전체가 한 바퀴 돈다. 이 숫자를 안 적으면 나중에 "왜 이 설정이
        # 저 날 장부에 없나"에 답할 수 없다.
        "roster_size": PANEL_ROSTER_PER_NIGHT,
        # 그날 밤 오디션을 **실제로 연** 종목 수. 설정이 0개 판정된 날
        # 이 숫자가 0이면 "밤 배치가 안 돌았다"이고, 0이 아니면 "돌았는데
        # 패널이 재료를 못 모았다"(고장)이다 — 둘은 다른 사건이고 다른
        # 사람이 고쳐야 한다.
        "n_symbols_seen": int(n_symbols_seen),
        "n_specs_judged": len(judged),
        "t_ref": PANEL_T_REF,
        # 판정된 설정만 담는다 — 종목이 모자라 못 잰 것을 '통과'로도
        # '탈락'으로도 세지 않는다(감사 226: 건너뜀은 통과가 아니다).
        "specs": [{
            "spec_key": v["spec_key"], "n_symbols": v["n_symbols"],
            "n_dates": v["n_dates"], "mean_diff": round(v["mean_diff"], 8),
            "t_stat": round(v["t_stat"], 4), "pass_t": bool(v["pass"]),
            "symbol_wins": v["symbol_wins"],
            "symbol_win_rate": round(v["symbol_win_rate"], 4),
            # 이득의 크기를 숫자로 남긴다 — "패널로 바꿨다"는 선언은
            # 이득의 증거가 아니다.
            "variance_gain": round(float((v.get("gain") or {})
                                         .get("variance_gain", 0.0)), 3),
        } for v in judged],
        "skipped": [{"spec_key": v["spec_key"], "reason": v["reason"]}
                    for v in verdicts if v.get("skipped")],
    }
    frame = collector.panel_frame()
    if frame.shape[0] >= RC_MIN_N and frame.shape[1] >= 1:
        rec["reality_check"] = reality_check(frame.to_numpy())
    else:
        rec["reality_check"] = {"skipped": True, "reason": (
            f"패널 표가 {frame.shape[0]}일 x {frame.shape[1]}설정 — 동시검정에 "
            f"필요한 최소 {RC_MIN_N}일에 못 미칩니다(생략이며 통과가 아닙니다)")}
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, PANEL_FILE), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("패널 장부 기록 실패: %s", exc)
    return rec


def run_retrain_all(targets=None, **kwargs) -> dict:
    """**지금 매매하는 전 종목**을 순회 재학습한다 — 한 종목의 실패가 나머지를 막지 않는다.

    반환: {"ok": [키...], "failed": {키: 오류}, "promoted": [키...]}.
    전 종목이 실패했을 때만 예외를 올린다(잡을 크게 실패시켜 조기 경보).
    """
    import time as _time

    # ⚠️ **매매하는 목록과 심사하는 목록이 갈라져 있었다** (2026-08-23 실측).
    #    페이퍼 배치는 `universe.active_targets`(규칙으로 매일 뽑은 40종목)로
    #    매매하는데, 여기 기본값은 손으로 적은 상수 AUTO_TARGETS(20종목)였다.
    #    결과: **22종목이 오디션 한 번 없이 기본 챔피언으로 돈을 받고 있었다.**
    #    그 종목에서 그 전략이 통하는지 아무도 확인한 적이 없는데도.
    #
    #    이 저장소가 반복해서 잡아 온 병(선언과 행동의 불일치)이고, 하필
    #    유니버스를 20 → 40으로 늘린 그 커밋이 만든 것이다. 진실의 출처를
    #    하나로 모은다 — **매매하는 것은 전부 심사한다.**
    #
    #    시간은 아래 이어달리기가 이미 맡는다(그 장치의 주석이 45종목을
    #    예상해 쓰여 있다 — 만들어 두고 목록만 안 바꾼 셈이었다).
    from quant.universe import active_targets
    targets = list(targets or active_targets(kwargs.get("state_dir", STATE_DIR)))

    # ── 시간 예산 + 이어달리기 (2026-08-19, 유니버스 20 → 45종목) ────────
    #
    # ⚠️ 실측: 20종목에 34.5분. 45종목이면 78분쯤인데 잡 한도는 45분이고,
    #    그 한도를 올리면 "재학습이 끝난 뒤에 배치가 시작한다"는 파이프라인
    #    계약이 깨진다(배치가 그날 승격된 챔피언을 놓친다).
    #
    #    그래서 한도를 늘리는 대신 **오늘 못 돈 종목을 내일 먼저 돈다.**
    #    커서를 장부에 남기고 매일 그 지점부터 시작하면, 며칠에 걸쳐 전 종목이
    #    골고루 돌고 어느 날도 잡이 잘리지 않는다. 챔피언 교체는 드문 사건이라
    #    (20종목 누적 1회) 하루 늦게 도는 것의 손해는 작고, 잡이 시간 초과로
    #    통째로 죽어 **아무 종목도 못 도는** 손해가 훨씬 크다.
    #
    #    ⚠️ 잘린 사실은 반드시 기록에 남긴다 — 조용히 줄면 "45종목 다 돌았다"로
    #       읽히고, 그게 이 저장소가 반복해서 막아 온 종류의 거짓말이다.
    budget = float(os.environ.get("QUANT_RETRAIN_BUDGET_SEC") or 0) or None
    state_dir = kwargs.get("state_dir", STATE_DIR)
    cursor_path = os.path.join(state_dir, "retrain_cursor.json")
    start = 0
    if budget:
        try:
            with open(cursor_path, encoding="utf-8") as f:
                last_key = json.load(f).get("next_key")
            keys = [_key(m, s) for m, s in targets]
            if last_key in keys:
                start = keys.index(last_key)
        except (OSError, ValueError, KeyError):
            start = 0
        targets = targets[start:] + targets[:start]     # 이어달리기 순서

    ok, promoted, failed, skipped = [], [], {}, []
    deadline = (_time.monotonic() + budget) if budget else None
    not_reached: list[str] = []
    # 패널 재료 수집기 — 종목을 도는 동안 **설정별로** 초과수익 계열을 쌓는다.
    # ⚠️ 이어달리기 때문에 하룻밤에 전 종목을 못 돈다(시간 예산). 그래서
    #    패널에 서는 종목 수는 그날 실제로 돈 종목 수이고, 장부에 그 숫자를
    #    그대로 남긴다 — "40종목 패널"이라고 적어 두고 실제로는 12종목이면
    #    그건 이 저장소가 반복해서 막아 온 종류의 거짓말이다.
    from quant.live.panel_gate import PanelCollector
    panel = PanelCollector()
    panel_asof = ""
    for idx, (market, symbol) in enumerate(targets):
        key = _key(market, symbol)
        if deadline is not None and _time.monotonic() > deadline:
            not_reached = [_key(m, s) for m, s in targets[idx:]]
            break
        try:
            out = run_retrain(market, symbol, **kwargs)
            # 멱등 가드에 걸린 종목은 오디션을 **한 번도 안 열었다**.
            # 그걸 성공으로 세면 시세가 얼어붙은 날도 장부는 "20/20 성공"이다
            # (감사 226 — "건너뜀은 통과가 아니다"는 이미 변이 시험의 규칙인데
            #  정작 배치 건강 기록에서는 지키지 않고 있었다).
            (skipped if out.get("skipped") else ok).append(key)
            if out.get("promoted"):
                promoted.append(key)
            panel.add(key, out.get("panel_diffs") or {})
            panel_asof = max(panel_asof, str(out.get("asof") or ""))
        except Exception as exc:  # noqa: BLE001
            failed[key] = str(exc)
            log.warning("재학습 실패 %s: %s", key, exc)
            print(f"⚠️ {key}: 재학습 실패 — {exc}")
    if budget:
        # 다음 밤이 이어받을 지점 — 못 돈 첫 종목(다 돌았으면 처음으로).
        try:
            from quant.utils.jsonio import atomic_write_json
            atomic_write_json(cursor_path, {
                "next_key": not_reached[0] if not_reached else None,
                "not_reached": not_reached,
                "budget_sec": budget})
        except Exception:  # noqa: BLE001 — 커서 실패가 재학습을 못 죽인다
            log.warning("재학습 커서 저장 실패")
    # 패널 관문 — 판정하고 **기록만** 한다(승격은 아직 종목별 관문이 정한다).
    # 실패해도 밤 배치를 죽이지 않는다: 이건 아직 관문이 아니라 관측이다.
    # ⚠️ **재료가 하나도 안 모인 밤에도 줄을 남긴다.** 예전에는 `if
    #    panel.specs:`로 감싸서, 재료가 0이면 장부에 아무것도 안 적혔다.
    #    그러면 "패널이 아무것도 못 쟀다"와 "밤 배치가 아예 안 돌았다"가
    #    장부에서 **똑같이 보인다** — 전자는 고장이고 후자는 다른 경보가
    #    맡는 사건인데, 구별할 방법이 없으면 둘 다 늦게 발견된다.
    #    없는 줄은 침묵이고, 침묵은 이 저장소에서 가장 비싼 실패다.
    panel_rec = None
    try:
        panel_rec = record_panel(panel_asof or _today_iso(), panel,
                                 kwargs.get("state_dir", STATE_DIR),
                                 n_symbols_seen=len(ok))
        rc = panel_rec.get("reality_check") or {}
        print(f"  📊 패널 관문(기록 전용): 설정 "
              f"{panel_rec['n_specs_judged']}/"
              f"{panel_rec['n_specs_collected']}개 판정 · "
              f"종목 {panel_rec['n_symbols_seen']} · "
              + ("동시검정 생략" if rc.get("skipped")
                 else f"동시검정 p={rc.get('p')}"))
    except Exception as exc:  # noqa: BLE001 — 관측 실패가 배치를 못 죽인다
        log.warning("패널 관문 기록 실패: %s", exc)

    print(f"\n요약: 성공 {len(ok)} · 교체 {len(promoted)} · 건너뜀 "
          f"{len(skipped)} · 실패 {len(failed)}"
          + (f" · 시간 예산으로 못 돈 종목 {len(not_reached)}"
             f"(내일 먼저 돕니다)" if not_reached else "")
          + (f" ({', '.join(failed)})" if failed else ""))
    # 부분 실패도 장부에 남긴다 — '전부 실패'만 예외로 올리면 19/20이 실패한
    # 날도 잡이 초록이고, 그 종목들은 옛 챔피언을 그대로 쓰면서 아무 흔적도
    # 남지 않는다(2026-08-11 감사).
    state_dir = kwargs.get("state_dir") or STATE_DIR
    from quant.live.daily import _write_run_health
    _write_run_health(state_dir, "retrain", ok, failed, skipped=skipped,
                      stale=stale_targets(skipped, state_dir))
    # ⚠️ 건너뜀은 실패가 아니다 — 예비(재시도) 크론은 정상적으로 전 종목을
    #    건너뛴다. `not ok`만 보면 그 실행이 매번 잡을 빨갛게 만든다.
    if targets and not ok and not skipped:
        raise RuntimeError(f"전 종목 재학습 실패: {failed}")
    return {"ok": ok, "failed": failed, "skipped": skipped,
            "promoted": promoted, "panel": panel_rec}
