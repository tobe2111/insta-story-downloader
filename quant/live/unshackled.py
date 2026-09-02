"""무제약 그림자 — 안전장치를 전부 뗀 가상 계좌 (2026-08-19, 사장님 지시).

사장님 질문 그대로가 이 실험의 존재 이유다: "변동성을 강제로 묶지 않고
수익성을 가장 우선하면 되잖아. 다른 모든 제약들도 마찬가지야."

말로 다투지 않는다 — 같은 신호를 받아 **안전장치 없이** 굴리는 가상
계좌를 본 계좌 옆에 공개해서, 제약이 실제로 무엇을 깎고 무엇을 막는지
곡선이 답하게 한다.

이 계좌에 없는 것(본 계좌에는 있는 것):
    · 변동성 타깃(위험 예산) — 없음. 신호 비중 × 배분 그대로.
    · 킬스위치·서킷브레이커(낙폭 브레이크) — 없음.
    · 검증 게이트(과최적화 검증 실패 종목 감쇠) — 없음.
    · 켈리 상한·실적 가드·어드민 노출 배수 — 없음.
남는 것: 무레버리지(총노출 100% 상한)뿐 — 가상 계좌라도 빚은 못 낸다.

정직한 규약: 종가 평가 · 전일 목표를 오늘 수익에 적용(1봉 지연) ·
회전율×수수료만 차감(배분 사다리와 같은 규약). 본 계좌 판정에는 쓰지
않고, 이 계좌가 이기는 구간이 있어도 그것은 "위험을 더 진 대가"이지
실력의 증거가 아니다 — 판정은 낙폭과 함께 읽어야 한다(MDD 병기).
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.unshackled")

START_CASH = 1_000_000.0
FEE = 0.001


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
FILE = "unshackled.json"
KEEP_DAYS = 400


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and "history" in st:
            return st
    except (OSError, ValueError):
        pass
    return {"start_cash": START_CASH, "equity": START_CASH, "peak": START_CASH,
            "history": [], "prev_weights": {}, "prev_marks": {}}


def run_unshackled(*, bar: str, weights: dict, slices: dict, marks: dict,
                   n_total: int, state_dir: str = "state") -> dict | None:
    """하루 1회 전진. 같은 봉 멱등 · 시세 없는 날 무기록(사다리 규약)."""
    from quant.utils.jsonio import atomic_write_json

    if not marks:
        return None
    path = os.path.join(state_dir, FILE)
    st = _load(path)
    if st["history"] and st["history"][-1].get("date") == bar:
        return st["history"][-1]

    # ① 전일 목표 × 오늘 수익 (1봉 지연)
    ret = 0.0
    pw, pm = st.get("prev_weights") or {}, st.get("prev_marks") or {}
    for k, w in pw.items():
        p0, p1 = pm.get(k), marks.get(k)
        if p0 and p1 and float(p0) > 0:
            ret += float(w) * (float(p1) / float(p0) - 1.0)
    equity = float(st["equity"]) * (1.0 + ret)

    # ② 오늘의 목표 = 신호 × 배분 — 감쇠·게이트·타깃 없음. 무레버리지만.
    target = {k: float(w) * float(slices.get(k, 1.0 / n_total))
              for k, w in weights.items()}
    gross = sum(abs(v) for v in target.values())
    if gross > 1.0:                                # 가상이라도 빚은 못 낸다
        target = {k: v / gross for k, v in target.items()}
        gross = 1.0
    turnover = sum(abs(target.get(k, 0.0) - float(pw.get(k, 0.0)))
                   for k in set(target) | set(pw))
    equity -= equity * _turnover_cost(target, pw, state_dir)

    peak = max(float(st.get("peak") or START_CASH), equity)
    keys = set(target) | set(pw)
    st.update({
        "equity": round(equity, 2), "peak": round(peak, 2),
        "prev_weights": {k: round(v, 6) for k, v in target.items()},
        "prev_marks": {k: float(marks[k]) for k in keys if marks.get(k)},
    })
    # 낙폭은 공용 헬퍼로만 잰다(입금이 생기면 즉석 수식은 고점을 오해한다
    # — 킬스위치가 이미 겪은 결함이라 계약 테스트가 즉석 수식을 금지한다).
    # 이 계좌는 입금이 없으므로 [peak, equity] 지수로 같은 답이 나온다.
    from quant.live.ledger_basics import drawdown_from_index
    dd = drawdown_from_index([peak / START_CASH, equity / START_CASH])
    rec = {"date": bar, "equity": round(equity, 2),
           "return_pct": round((equity / START_CASH - 1) * 100, 3),
           "mdd_pct": round(dd * 100, 2),
           "gross": round(gross, 4)}
    st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
    atomic_write_json(path, st)
    return rec


def unshackled_public(state_dir: str = "state") -> dict | None:
    st = _load(os.path.join(state_dir, FILE))
    if not st["history"]:
        return None
    last = st["history"][-1]
    worst = min((r.get("mdd_pct", 0.0) for r in st["history"]), default=0.0)
    from quant.live.daily import cost_basis_bp
    return {"equity": last["equity"], "return_pct": last["return_pct"],
            "cost_basis_bp": cost_basis_bp(state_dir),
            "days": len(st["history"]), "worst_mdd_pct": round(worst, 2),
            "note": (
        "본 계좌와 같은 신호를 받되 안전장치(변동성 타깃·킬스위치·검증 "
        "게이트·켈리 상한)를 전부 뗀 가상 계좌입니다(무레버리지만 유지). "
        "이 계좌가 앞서는 구간은 실력이 아니라 위험을 더 진 대가일 수 "
        "있습니다 — 반드시 최대낙폭과 함께 읽으세요. 종가 평가·수수료만 "
        "차감이라 본 계좌와 절대 비교는 안 되고, 제약의 효과를 보는 "
        "용도입니다.")}
