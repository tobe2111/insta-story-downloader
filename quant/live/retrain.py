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
import os
from typing import Callable

from quant.utils.logging import get_logger

log = get_logger("retrain")

STATE_DIR = "state"
CHAMPIONS_FILE = "champions.json"
HISTORY_FILE = "retrain_history.jsonl"

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
DEFAULT_CHALLENGERS = [
    {"model": "logreg", "threshold": 0.55},
    {"model": "logreg", "threshold": 0.60},
    {"model": "rf", "threshold": 0.55},
    {"model": "gb", "threshold": 0.55},
    {"model": "gb", "threshold": 0.60},
    {"model": "vote", "threshold": 0.55},
]


def _key(market: str, symbol: str) -> str:
    return f"{market}:{symbol}"


def build_strategy(spec: dict):
    """{"strategy": 이름, "params": {...}} 스펙으로 전략 인스턴스를 만든다."""
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
) -> dict:
    """챔피언 1명 vs 챌린저 N명 — 2단계 검증으로 승격 여부를 결정한다.

    반환 dict의 promoted가 True면 champion(새 스펙)이 함께 담긴다.
    데이터(df)를 인자로 받는 순수 함수라 어떤 전략/데이터로도 테스트 가능하다.
    """
    from quant.live.champion_challenger import ChampionChallenger

    if len(df) <= confirm_window + min_obs:
        return {"promoted": False, "reason": (
            f"데이터 부족({len(df)}봉) — 선발전+결승전({confirm_window}봉)을 "
            "나눌 수 없어 챔피언을 유지합니다."), "candidates": []}

    select_df = df.iloc[:-confirm_window]      # 선발전: 결승 구간을 전혀 못 본다
    candidates = []
    for spec in challenger_specs:
        full_spec = {"strategy": champion_spec["strategy"],
                     "params": {**champion_spec.get("params", {}), **spec}}
        if full_spec["params"] == champion_spec.get("params", {}):
            continue                            # 챔피언 자신과의 대결은 무의미
        try:
            cc = ChampionChallenger(
                build(champion_spec), build(full_spec),
                min_obs=min_obs, edge=edge, t_threshold=select_t)
            r = cc.evaluate(select_df)
        except Exception as exc:  # noqa: BLE001 — 후보 하나의 실패로 전체를 죽이지 않는다
            log.warning("챌린저 평가 실패 %s: %s", spec, exc)
            continue
        candidates.append({"spec": full_spec, **r})

    passed = [c for c in candidates if c["swap"]]
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
        t_threshold=confirm_t)
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


def run_retrain(market: str, symbol: str, *, timeframe: str = "1d",
                limit: int = 800, state_dir: str = STATE_DIR,
                confirm_window: int = 120,
                require_real_data: bool = True) -> dict:
    """데이터 수신 → 대결 → 승격/유지 → 기록까지의 야간 재학습 1회분."""
    from quant.data import get_provider

    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=limit)
    if df.empty:
        raise RuntimeError(f"{market}/{symbol}: 데이터 수신 실패")
    if require_real_data and df.attrs.get("synthetic_fallback"):
        raise RuntimeError(
            f"{market}/{symbol}: 실데이터 수신 실패 → 합성 폴백 감지. "
            "가짜 데이터로 재학습·승격하면 안 되므로 중단합니다.")

    champions = load_champions(state_dir)
    key = _key(market, symbol)
    entry = champions.get(key) or {**DEFAULT_CHAMPION, "promotions": 0}
    champion_spec = {"strategy": entry["strategy"], "params": entry["params"]}

    decision = nightly_retrain(df, champion_spec, DEFAULT_CHALLENGERS,
                               confirm_window=confirm_window)
    asof = str(df.index[-1])[:10]              # 기준 시점 = 데이터 마지막 봉(재현 가능)

    if decision["promoted"]:
        entry = {**decision["champion"],
                 "promoted_at": asof,
                 "promotions": int(entry.get("promotions", 0)) + 1}
        champions[key] = entry
        save_champions(champions, state_dir)
    elif key not in champions:                 # 첫 실행: 기본 챔피언을 명시적으로 기록
        champions[key] = entry
        save_champions(champions, state_dir)

    append_history({
        "asof": asof, "market": market, "symbol": symbol, "bars": len(df),
        "promoted": decision["promoted"], "reason": decision["reason"],
        "champion": champions[key]["params"],
        "n_candidates": len(decision.get("candidates", [])),
    }, state_dir)

    label = "🔁 교체" if decision["promoted"] else "🏆 유지"
    print(f"[{asof}] {market}/{symbol} — 챔피언 {label}: "
          f"{champions[key]['params']}")
    print(f"  근거: {decision['reason']}")
    return {"key": key, "champion": champions[key], **decision}
