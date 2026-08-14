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
    {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}},
    {"strategy": "breakout", "params": {"window": 55, "exit_window": 20}},
]


def _feature_set() -> str:
    """현재 ML 피처셋 버전 태그 (장부 기록용)."""
    from quant.strategies.ml import FEATURE_SET
    return FEATURE_SET


def _key(market: str, symbol: str) -> str:
    return f"{market}:{symbol}"


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
            axis = rng.choice(["model", "threshold", "train_window",
                               "retrain_every", "calibrate", "label",
                               "sample_weight"])
            if axis == "model":
                p["model"] = rng.choice(["logreg", "rf", "gb", "vote"])
            elif axis == "threshold":
                base = float(p.get("threshold", 0.55))
                step = rng.choice([-0.05, -0.02, 0.02, 0.05])
                p["threshold"] = round(min(0.70, max(0.52, base + step)), 2)
            elif axis == "train_window":
                p["train_window"] = rng.choice([150, 250, 350, 500])
            elif axis == "retrain_every":
                p["retrain_every"] = rng.choice([10, 20, 40])
            elif axis == "label":
                # 라벨 축 — 배리어 폭(k)·만기(horizon)도 함께 흔들어 탐색
                p["label"] = rng.choice(["nextbar", "triple"])
                if p["label"] == "triple":
                    p["label_k"] = rng.choice([1.0, 1.5, 2.0])
                    p["label_horizon"] = rng.choice([5, 10, 15])
            elif axis == "sample_weight":
                p["sample_weight"] = rng.choice([None, "decay"])
            else:
                p["calibrate"] = rng.choice([None, "sigmoid"])
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


def nightly_retrain(
    df,
    champion_spec: dict,
    challenger_specs: list[dict],
    *,
    build: Callable[[dict], object] = build_strategy,
    confirm_window: int = 120,
    select_t: float = 2.0,
    confirm_t: float = 1.0,
    min_obs: int = 60,
    edge: float = 0.0,
    cost_model=None,
    select_folds: int = SELECT_FOLDS,
    next_open_fill: bool = False,
    rebalance_band: float = 0.0,
) -> dict:
    """챔피언 1명 vs 챌린저 N명 — 2단계 검증으로 승격 여부를 결정한다.

    반환 dict의 promoted가 True면 champion(새 스펙)이 함께 담긴다.
    데이터(df)를 인자로 받는 순수 함수라 어떤 전략/데이터로도 테스트 가능하다.

    select_folds ≥ 2면 선발전에 '폴드 일관성 게이트'가 추가된다: 수익 차이를
    연속 등분한 폴드 중 과반에서 이겨야 통과 — 전체 t-통계 하나는 한 구간의
    대박이 만든 착시일 수 있다(CPCV 경량판). 0이면 기존 동작(verify가 옛
    기록을 재현할 때 사용).
    """
    from quant.live.champion_challenger import ChampionChallenger

    if len(df) <= confirm_window + min_obs:
        return {"promoted": False, "reason": (
            f"데이터 부족({len(df)}봉) — 선발전+결승전({confirm_window}봉)을 "
            "나눌 수 없어 챔피언을 유지합니다."), "candidates": []}

    select_df = df.iloc[:-confirm_window]      # 선발전: 결승 구간을 전혀 못 본다
    candidates = []
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
        candidates.append({"spec": full_spec, **r})

    def _consistent(c: dict) -> bool:
        # 폴드 일관성 게이트 — 과반 폴드에서 이겨야 한다. 폴드 정보가 없으면
        # (select_folds=0 또는 표본 부족) 게이트 없이 통과(기존 동작).
        if "fold_wins" not in c:
            return True
        return c["fold_wins"] >= c["n_folds"] // 2 + 1

    passed = [c for c in candidates if c["swap"] and _consistent(c)]
    if not passed:
        return {"promoted": False, "reason": (
            f"선발전에서 챔피언을 통계적으로 이긴 후보 없음"
            f"(후보 {len(candidates)}개) — 챔피언 유지. 정상입니다."),
            "candidates": candidates}

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
        return {"promoted": False, "reason": (
            "선발전 1위가 결승전(최근 미공개 구간)에서 검증 실패 — 챔피언 유지. "
            "선발전 성적은 우연이었을 가능성이 큽니다."),
            "best_candidate": best, "final": final, "candidates": candidates}

    return {"promoted": True, "champion": best["spec"], "reason": (
        f"선발전 t={best['t_stat']:.2f}, 결승전 t={final['t_stat']:.2f} 모두 통과 "
        "— 새 챔피언으로 승격."),
        "best_candidate": best, "final": final, "candidates": candidates}


def champion_spec(market: str, symbol: str, state_dir: str = STATE_DIR) -> dict:
    """현재 챔피언 스펙을 반환한다. 기록이 없으면 기본 챔피언으로 폴백한다.

    실행파일/새 설치처럼 state/가 없는 환경에서도 항상 동작해야 하므로
    폴백은 조용히 일어난다(기본 챔피언 = ml logreg, MLStrategy 기본값과 동일).
    """
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


def build_challengers(current_spec: dict, seed: str,
                      evolve: bool = True) -> list[dict]:
    """그날의 도전자 링을 결정적으로 구성한다 (run_retrain과 verify가 공유).

    고정 기본 후보 + 챔피언 돌연변이(시드 결정적) + 레짐/이벤트 래핑 변형.
    래핑된 챔피언에는 '벗긴 원본'을 도전시켜 되돌아갈 길을 항상 열어 둔다.
    """
    challengers = _normalize_challengers(DEFAULT_CHALLENGERS, current_spec)
    if not evolve:
        return challengers
    challengers += mutate_champion(current_spec, seed=seed)
    if current_spec["strategy"] != "regime_wrap":
        challengers.append({"strategy": "regime_wrap",
                            "params": {"inner": current_spec,
                                       "trend_window": 200}})
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


# ── 다중검정 문턱 — 롤링 윈도 + 상한 ────────────────────────────
# 누적 시도 수가 단조 증가하면 문턱도 영원히 올라가 진화가 완전히 멈춘다.
# 그래서 문턱 계산에는 '최근 1년 시도 수'만 쓰고 상한을 둔다(장부의 누적
# 총계 trials_total은 투명성 표시용으로 계속 쌓는다).
TRIALS_WINDOW_DAYS = 365
CONFIRM_T_CAP = 1.35


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
        return [{"key": "-", "ok": False,
                 "detail": f"{asof} 기록 없음(--date 확인)"}]

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
        challengers = build_challengers(before, seed=rec["mutation_seed"])
        decision = nightly_retrain(
            df, before, challengers, confirm_window=confirm_window,
            select_t=float(rec.get("select_t", 2.0)),
            confirm_t=float(rec.get("confirm_t", 1.0)),
            # 옛 기록(폴드 게이트 이전)은 0으로 재현 — 알고리즘 진화가
            # 과거 결정의 재현 검증을 깨뜨리지 않게 장부 값을 따른다.
            select_folds=int(rec.get("select_folds", 0)),
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
    if market == "kr_stock":
        # 외국인·기관 수급(z-점수) — 한국 주식 고유의 수급 피처(실패 시 생략)
        from quant.data.krx import attach_krx_flows
        df = attach_krx_flows(df, symbol)
    # 크로스에셋 컬럼(x_*) — 시장 바깥의 맥락(BTC/SPY/금리/환율). 펀딩과 같은
    # 원리로 스냅샷·해시에 보존된다(실패 시 조용히 생략 — 선택적 피처).
    from quant.data.crossasset import attach_cross_asset
    df = attach_cross_asset(df, market, symbol)

    champions = load_champions(state_dir)
    key = _key(market, symbol)
    entry = champions.get(key) or {**DEFAULT_CHAMPION, "promotions": 0}
    current_spec = {"strategy": entry["strategy"], "params": entry["params"]}
    asof = str(df.index[-1])[:10]              # 기준 시점 = 데이터 마지막 봉(재현 가능)

    # 멱등 가드 — 같은 봉(같은 날)에 이미 대결했으면 통째로 건너뛴다.
    # 예비(재시도) 크론이 성공한 날을 다시 돌려 기록을 중복시키지 않게 한다.
    if entry.get("last_run_asof") == asof:
        print(f"[{asof}] {market}/{symbol} — 오늘 이미 재학습함, 건너뜀")
        return {"skipped": True, "key": key, "champion": entry}

    # 도전자 = 고정 기본 후보 + 챔피언 돌연변이(진화 탐색) + 레짐/이벤트 변형.
    # 시드가 날짜+종목이라 결정적 — verify가 같은 링을 재구성할 수 있다.
    challengers = build_challengers(current_spec, seed=f"{asof}:{key}",
                                    evolve=evolve)

    # ── 다중검정 보정 — 오디션을 반복할수록 '운 좋은 승자'가 나올 확률이
    # 커진다. 누적 시도 횟수를 장부에 남기고, 그에 비례해 승격 관문을 높인다.
    #   선발전: 그날 후보 수 N의 기대 최댓값 근사 sqrt(2·ln N) 이상을 요구
    #   결승전: '최근 1년' 시도 수에 로그 비례 + 상한(진화가 영원히 멈추는
    #   것을 방지) — DSR 정신의 보수적 근사. 누적 총계는 표시용으로만 쌓는다.
    n_cand = len(challengers)
    trials_total = int(entry.get("trials_total", 0)) + n_cand
    entry["trials_total"] = trials_total
    trials_recent = recent_trials(market, symbol, asof, state_dir) + n_cand
    select_t_eff = max(2.0, math.sqrt(2 * math.log(max(2, n_cand))))
    confirm_t_eff = confirm_threshold(trials_recent)
    print(f"  🔬 다중검정 보정: 오늘 후보 {n_cand}개 · 최근 1년 "
          f"{trials_recent:,}개 · 누적 검증 도전자 {trials_total:,}개 → "
          f"선발 t≥{select_t_eff:.2f} · 결승 t≥{confirm_t_eff:.2f}"
          f" (상한 {CONFIRM_T_CAP})")

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
                                        models_gap=audition_next_open)
    audition_band = _rebalance_band_rel(market, state_dir)
    decision = nightly_retrain(df, current_spec, challengers,
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
                                       models_gap=audition_next_open),
        next_open_fill=audition_next_open,
        rebalance_band=_rebalance_band_rel(market, state_dir),
        confirm_window=confirm_window,
        promoted_spec=decision["champion"] if decision["promoted"] else None)
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
        "trials_total": trials_total,
        "select_t": round(select_t_eff, 3), "confirm_t": round(confirm_t_eff, 3),
        "select_folds": SELECT_FOLDS,  # 폴드 일관성 게이트 — verify 재현용
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
        "code_sha": code_sha(),
        "data_sha256": data_sha256(df),
        "env": env_fingerprint(),      # 라이브러리 버전 차이로 인한 불일치 판별용
        # 피처셋 태그 — 피처는 '가설 그룹' 단위로 추가되며, 성과 변화가
        # 어느 배치 이후인지 이 태그로 추적한다(피처 중요도로 판단 금지).
        "feature_set": _feature_set(),
        # 의회 구성 — "챔피언 교체" 대신 "구성 변화"의 서사이자 감사 흔적
        "parliament": [{"strategy": m["strategy"], "weight": m["weight"]}
                       for m in entry.get("parliament", [])],
    }, state_dir)

    label = "🔁 교체" if decision["promoted"] else "🏆 유지"
    print(f"[{asof}] {market}/{symbol} — 챔피언 {label}: "
          f"{champions[key]['strategy']} {champions[key]['params']}")
    print(f"  근거: {decision['reason']}")
    return {"key": key, "champion": champions[key], **decision}


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


def run_retrain_all(targets=None, **kwargs) -> dict:
    """AUTO_TARGETS 전체를 순회 재학습한다 — 한 종목의 실패가 나머지를 막지 않는다.

    반환: {"ok": [키...], "failed": {키: 오류}, "promoted": [키...]}.
    전 종목이 실패했을 때만 예외를 올린다(잡을 크게 실패시켜 조기 경보).
    """
    from quant.markets import AUTO_TARGETS
    targets = targets or AUTO_TARGETS

    ok, promoted, failed, skipped = [], [], {}, []
    for market, symbol in targets:
        key = _key(market, symbol)
        try:
            out = run_retrain(market, symbol, **kwargs)
            # 멱등 가드에 걸린 종목은 오디션을 **한 번도 안 열었다**.
            # 그걸 성공으로 세면 시세가 얼어붙은 날도 장부는 "20/20 성공"이다
            # (감사 226 — "건너뜀은 통과가 아니다"는 이미 변이 시험의 규칙인데
            #  정작 배치 건강 기록에서는 지키지 않고 있었다).
            (skipped if out.get("skipped") else ok).append(key)
            if out.get("promoted"):
                promoted.append(key)
        except Exception as exc:  # noqa: BLE001
            failed[key] = str(exc)
            log.warning("재학습 실패 %s: %s", key, exc)
            print(f"⚠️ {key}: 재학습 실패 — {exc}")
    print(f"\n요약: 성공 {len(ok)} · 교체 {len(promoted)} · 건너뜀 "
          f"{len(skipped)} · 실패 {len(failed)}"
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
            "promoted": promoted}
