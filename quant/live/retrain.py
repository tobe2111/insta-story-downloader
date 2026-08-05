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
    {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}},
    {"strategy": "breakout", "params": {"window": 55, "exit_window": 20}},
]


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
                               "retrain_every", "calibrate"])
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
    cost_model=None,
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
                cost_model=cost_model)
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
        t_threshold=confirm_t, cost_model=cost_model)
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

    # 도전자 = 고정 기본 후보 + 챔피언 돌연변이(진화 탐색) + 레짐 변형.
    # 돌연변이 시드가 날짜라 매일 다른 주변을 탐색하고, 같은 날 재실행은
    # 같은 후보를 만든다.
    challengers = _normalize_challengers(DEFAULT_CHALLENGERS, current_spec)
    if evolve:
        challengers += mutate_champion(current_spec, seed=f"{asof}:{key}")
        if current_spec["strategy"] != "regime_wrap":
            # 현 챔피언에 레짐 필터를 씌운 변형 — 하락장이 오면 진화 루프가
            # '관망할 줄 아는 챔피언'으로 스스로 갈아탈 수 있게 한다.
            challengers.append({"strategy": "regime_wrap",
                                "params": {"inner": current_spec,
                                           "trend_window": 200}})
        else:
            # 챔피언이 이미 레짐 래핑이면 '벗긴 원본'을 도전시킨다 — 필터가
            # 더는 도움이 안 되는 국면에서 되돌아갈 길을 항상 열어 둔다.
            challengers.append(current_spec["params"]["inner"])
        if current_spec["strategy"] != "event_wrap":
            # FOMC 등 예고된 이벤트 창에서 관망하는 변형 — 이벤트 달력이
            # 결정적이라 백테스트 검증이 가능하고, 관문을 통과할 때만 승격된다.
            challengers.append({"strategy": "event_wrap",
                                "params": {"inner": current_spec,
                                           "pad_days": 1, "factor": 0.0}})
        else:
            # 이미 이벤트 래핑이면 '벗긴 원본'을 도전시킨다 — 필터가 더는
            # 도움이 안 되면 되돌아갈 길을 열어 둔다.
            challengers.append(current_spec["params"]["inner"])

    # 시장별 현실적 거래비용으로 대결 — 비용을 빼면 회전율 높은 전략이 과대평가된다
    from quant.backtest.costs import CostModel
    decision = nightly_retrain(df, current_spec, challengers,
                               confirm_window=confirm_window,
                               cost_model=CostModel.for_market(market))

    if decision["promoted"]:
        entry = {**decision["champion"],
                 "promoted_at": asof,
                 "promotions": int(entry.get("promotions", 0)) + 1}
    entry["last_run_asof"] = asof              # 멱등 가드 기준(재시도 크론용)
    champions[key] = entry
    save_champions(champions, state_dir)

    append_history({
        "asof": asof, "market": market, "symbol": symbol, "bars": len(df),
        "promoted": decision["promoted"], "reason": decision["reason"],
        "champion": champions[key]["params"],
        "champion_strategy": champions[key]["strategy"],
        "n_candidates": len(decision.get("candidates", [])),
    }, state_dir)

    label = "🔁 교체" if decision["promoted"] else "🏆 유지"
    print(f"[{asof}] {market}/{symbol} — 챔피언 {label}: "
          f"{champions[key]['strategy']} {champions[key]['params']}")
    print(f"  근거: {decision['reason']}")
    return {"key": key, "champion": champions[key], **decision}


def run_retrain_all(targets=None, **kwargs) -> dict:
    """AUTO_TARGETS 전체를 순회 재학습한다 — 한 종목의 실패가 나머지를 막지 않는다.

    반환: {"ok": [키...], "failed": {키: 오류}, "promoted": [키...]}.
    전 종목이 실패했을 때만 예외를 올린다(잡을 크게 실패시켜 조기 경보).
    """
    from quant.markets import AUTO_TARGETS
    targets = targets or AUTO_TARGETS

    ok, promoted, failed = [], [], {}
    for market, symbol in targets:
        key = _key(market, symbol)
        try:
            out = run_retrain(market, symbol, **kwargs)
            ok.append(key)
            if out.get("promoted"):
                promoted.append(key)
        except Exception as exc:  # noqa: BLE001
            failed[key] = str(exc)
            log.warning("재학습 실패 %s: %s", key, exc)
            print(f"⚠️ {key}: 재학습 실패 — {exc}")
    print(f"\n요약: 성공 {len(ok)} · 교체 {len(promoted)} · 실패 {len(failed)}"
          + (f" ({', '.join(failed)})" if failed else ""))
    if targets and not ok:
        raise RuntimeError(f"전 종목 재학습 실패: {failed}")
    return {"ok": ok, "failed": failed, "promoted": promoted}
