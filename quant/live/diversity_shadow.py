"""다양성 가중 그림자 — 같은 의원 신호를 **섞는 비중만** 바꾼 두 가상 계좌.

⚠️ 왜 만들었나(2026-08-23, 사장님 "얘기해준 거 다 하자"). 의회는 의석 비중을
   홀드아웃 점수의 softmax로 정하는데, 이 규칙은 **의원끼리의 상관**을 보지
   않는다. 그래서 seat_census가 '상관까지 본 비중'(alt_weight)을 매일 나란히
   적어 왔고, 두 비중의 평균 거리(weight_gap)를 재 왔다.

   원래 사전 등록한 착수 문턱은 weight_gap ≥ 0.2였다. 실측 첫 값은 0.196
   (5계좌)으로 문턱 **미달**이었으나, 사장님이 대기 없이 조기 착수를 지시해
   지금 만든다. 이 사실을 숨기지 않는다 — 문턱을 낮춘 것이 아니라, 문턱과
   무관하게 "재 보라"는 지시가 있었던 것이다.

무엇을 재나: 의회가 2석 이상이고 alt_weight가 있는 계좌들에서, **같은 의원
신호**를 두 가지 비중으로 섞는다:

    actual    — 지금 실제 비중(softmax·EMA 결과)
    diversity — 상관까지 본 비중(alt_weight — 격자 최대샤프를 균등으로 절반 수축)

둘의 차이는 오직 '섞는 비중'뿐이다. 신호·종목·평가 규약이 전부 같아야
격차가 곧 그 축의 값이다(사이징 사다리의 데드존 공유와 같은 원리).

정직한 규약:
  · 잴 수 있는 계좌(다석 + alt_weight 완비 + 시세)가 없는 날은 **아무것도
    쓰지 않는다** — 빈 회차가 남으면 곡선이 가짜 평평함을 얻는다.
  · alt_weight가 하나라도 없으면 그 계좌는 그날 통째로 뺀다(둘 다에서).
    없는 값을 0이나 균등으로 채우면 '모른다'가 '판단'으로 둔갑한다.
  · 평가는 사다리들과 같은 규약 — 종가 마크 · 전일 목표를 오늘 수익에
    적용(1봉 지연) · 회전율×수수료만 차감. 본 계좌의 변동성 타깃·킬스위치·
    검증 게이트는 없다. 절대 성적이 아니라 **두 트랙의 상대 비교만** 뜻이 있다.
  · 트랙이 2개다 — 우연히 좋아 보이는 승자가 나올 확률도 2배다(다중검정).
  · 본 계좌에는 적용하지 않는다. 의석 비중 규칙은 판정 시계의 축이라
    적용하는 순간 90일 시계가 리셋된다. 판정은 사다리들과 같은 날
    (2026-12-20) 짝지어 비교로 한다.

실패 원칙: 이 실험의 어떤 실패도 본 계좌 배치를 죽이면 안 된다.
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.diversity_shadow")

TRACKS = ("actual", "diversity")
START_CASH = 1_000_000.0
FEE = 0.001            # 회전율당 10bp — 두 계좌 공통(상대 비교 전용)


def _turnover_cost(target: dict, prev: dict, state_dir: str) -> float:
    """회전 × **그 종목 시장의 실측 편도 비용** — 본 계좌와 같은 자.

    2026-09-02 사장님 지시("각 수수료도 고려해서 수익을 생각해야지 — 모든
    투자 마찬가지"). 예전엔 시장 무관 10bp 고정이라 한국·코인은 싸게,
    미국은 비싸게 셌다 — 본 계좌와 나란히 놓는 비교가 기울어 있었다.
    """
    try:
        from quant.live.daily import measured_cost_model
        def _one_way(key: str) -> float:
            return float(measured_cost_model(key.split(":")[0], state_dir).total_one_way())
    except Exception:  # noqa: BLE001 — 비용 조회 실패가 그림자 기록을 막으면 안 된다
        def _one_way(key: str) -> float:
            return FEE
    return sum(abs(float(target.get(k, 0.0)) - float(prev.get(k, 0.0))) * _one_way(k)
               for k in set(target) | set(prev))
DIR = "diversity_shadow"
KEEP_DAYS = 400


def mix_pair(market: str, symbol: str, df_sig,
             state_dir: str = "state") -> tuple[float, float] | None:
    """이 계좌의 (실제 비중 혼합, 다양성 비중 혼합) 마지막 봉 포지션.

    잴 수 없으면 None — 의회가 1석이거나, alt_weight가 하나라도 없거나,
    의원 신호 계산이 실패한 경우. None을 0으로 적지 않는다.
    """
    try:
        from quant.live.retrain import _key, build_strategy, load_champions

        entry = load_champions(state_dir).get(_key(market, symbol)) or {}
        members = entry.get("parliament") or []
        if len(members) < 2:
            return None
        if any(m.get("alt_weight") is None for m in members):
            return None
        pos_a = pos_d = 0.0
        for m in members:
            strat = build_strategy({"strategy": m["strategy"],
                                    "params": dict(m.get("params") or {})})
            s = float(strat.generate_signals(df_sig).iloc[-1])
            pos_a += float(m.get("weight", 0.0)) * s
            pos_d += float(m["alt_weight"]) * s
        return (pos_a, pos_d)
    except Exception as exc:  # noqa: BLE001 — 계측 실패가 본류를 못 막는다
        log.warning("다양성 그림자 혼합 계산 실패(%s:%s, 건너뜀): %s",
                    market, symbol, exc)
        return None


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and "history" in st:
            return st
    except (OSError, ValueError):
        pass
    return {"start_cash": START_CASH, "equity": START_CASH,
            "history": [], "prev_weights": {}, "prev_marks": {}}


def run_diversity_shadow(*, bar: str, pairs: dict, marks: dict,
                         state_dir: str = "state") -> dict | None:
    """하루 1회 — 두 혼합 규칙의 가상 계좌를 한 봉 전진. 같은 봉이면 멱등.

    pairs: key → (actual 혼합 포지션, diversity 혼합 포지션).
    """
    from quant.utils.jsonio import atomic_write_json

    # 시세가 없는 종목은 두 트랙 모두에서 그날 통째로 뺀다 — 값을 매길 수
    # 없는 것을 계좌에 담을 수는 없다.
    usable = {k: (float(a), float(d)) for k, (a, d) in (pairs or {}).items()
              if k in marks}
    if not usable:
        return None
    n = len(usable)

    root = os.path.join(state_dir, DIR)
    os.makedirs(root, exist_ok=True)
    out = {}
    for ti, track in enumerate(TRACKS):
        path = os.path.join(root, f"{track}.json")
        st = _load(path)
        if st["history"] and st["history"][-1].get("date") == bar:
            out[track] = st["history"][-1]            # 같은 봉 재실행 — 멱등
            continue

        # ① 전일 목표를 오늘 수익에 적용(1봉 지연 — 사다리들과 같은 규약)
        ret = 0.0
        pw, pm = st.get("prev_weights") or {}, st.get("prev_marks") or {}
        for k, w in pw.items():
            p0, p1 = pm.get(k), marks.get(k)
            if p0 and p1 and float(p0) > 0:
                ret += float(w) * (float(p1) / float(p0) - 1.0)
        equity = float(st["equity"]) * (1.0 + ret)

        # ② 오늘의 목표 = 혼합 포지션 ÷ 종목 수(균등 슬라이스 — 종목 간
        #    배분 축은 다른 실험이 재고 있다. 여기는 '섞는 비중' 축만 흔든다)
        target = {k: pair[ti] / n for k, pair in usable.items()}
        turnover = sum(abs(target.get(k, 0.0) - float(pw.get(k, 0.0)))
                       for k in set(target) | set(pw))
        equity -= equity * _turnover_cost(target, pw, state_dir)

        keys = set(target) | set(pw)
        st.update({
            "equity": round(equity, 2),
            "prev_weights": {k: round(v, 6) for k, v in target.items()},
            "prev_marks": {k: float(marks[k]) for k in keys if marks.get(k)},
        })
        rec = {"date": bar, "equity": round(equity, 2),
               "return_pct": round((equity / START_CASH - 1) * 100, 3),
               "gross": round(sum(abs(v) for v in target.values()), 4),
               "symbols": n}
        st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
        atomic_write_json(path, st)
        out[track] = rec
    return out


def diversity_public(state_dir: str = "state") -> dict | None:
    """사이트 표시용 — 트랙별 현재 자산·수익률·표본 일수."""
    root = os.path.join(state_dir, DIR)
    if not os.path.isdir(root):
        return None
    rows = {}
    for track in TRACKS:
        st = _load(os.path.join(root, f"{track}.json"))
        if not st["history"]:
            continue
        last = st["history"][-1]
        rows[track] = {"equity": last["equity"],
                       "return_pct": last["return_pct"],
                       "days": len(st["history"])}
    if not rows:
        return None
    from quant.live.daily import cost_basis_bp
    return {"tracks": rows, "cost_basis_bp": cost_basis_bp(state_dir), "note": (
        "의회가 2석 이상인 계좌에서 **같은 의원 신호**를 두 비중으로 섞은 "
        "가상 계좌입니다 — actual은 지금 실제 비중, diversity는 전략 간 "
        "상관까지 본 비중. 종가 평가·수수료만 반영(본 계좌의 안전장치 없음 — "
        "두 트랙의 상대 비교 전용). 착수 문턱(격차 0.2) 미달(0.196) 상태에서 "
        "지시로 조기 시작했음을 함께 적습니다. 판정은 2026-12-20.")}
