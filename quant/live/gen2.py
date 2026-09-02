"""2세대 그림자 — **다 사지 않고, 좋은 것에 더 싣는다** (2026-08-19, 사장님 지시).

    "종목이 는다고 해서 그걸 다 살 필요는 없잖아. 그 많은 종목 중에서 가장
     매매를 했을 때 수익이 높을 것이라 기대하는 것을 매매하는 거지."

맞는 말이고, 상위권 운용사들이 실제로 하는 방식이다. 본 계좌(1세대)는
이렇게 돈다:

    신호가 켜진 종목에 **똑같이** 나눠 담는다(1/n 균등 조각).

그래서 확신이 강한 종목이나 겨우 문턱을 넘은 종목이나 **같은 금액**을 받는다.
45종목이면 하나당 2.2%씩이라, 정말 좋은 기회에도 2.2%밖에 못 싣는다.

2세대는 두 가지가 다르다:

    ① **줄 세워 상위 K개만** 담는다 — 나머지는 안 산다(현금).
    ② **점수에 비례해** 싣는다 — 확신이 두 배면 금액도 두 배.

점수는 지어내지 않고 **본 계좌가 이미 계산한 것들**로 만든다:

    점수 = 신호 세기 × 검증 등급 계수 × 횡단면 순위 틸트

    · 신호 세기: 챔피언이 낸 비중(0~1). 확신이 없으면 애초에 낮다.
    · 검증 등급: 과최적화 검증 결과. '실패'는 0, '미측정'은 절반 —
      "통과가 아니라 모른다"를 점수에도 그대로 반영한다.
    · 횡단면 틸트: 같은 날 다른 종목 대비 상대 순위(본 계좌의 xsec_tilt).

⚠️ **왜 그림자인가.** 배분 방식은 '얼마를 어떻게 사고파는가'라서, 본 계좌에
   바로 넣으면 판정 시계가 0으로 리셋된다(구조 세대 축 ②). 사장님이 "무슨
   수정을 해도 시계는 리셋되면 안 된다"고 하셨으므로, 2세대는 본 계좌 옆에서
   따로 굴리고 **판정일에 이기면 그때 졸업**시킨다. 실제 운용사도 새 모델은
   항상 페이퍼로 먼저 돌린다.

⚠️ 집중은 공짜가 아니다. 상위 K개에 몰면 맞을 때 더 벌고 틀릴 때 더 잃는다 —
   그래서 이 계좌도 최대낙폭을 함께 기록하고, 판정은 수익률과 낙폭을 같이
   읽어야 한다. "집중이 낫다"는 결론이 나와도 그건 위험을 더 진 대가일 수 있다.

정직한 규약(배분 사다리·무제약 그림자와 동일): 종가 평가 · 전일 목표를 오늘
수익에 적용(1봉 지연) · 회전율×수수료만 차감 · 같은 봉 멱등 · 시세 없는 날 무기록.
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.gen2")

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
FILE = "gen2.json"
KEEP_DAYS = 400

# 몇 개에 집중할 것인가 — 사전 등록값(prereg)과 같아야 한다.
TOP_K = 8

# 검증 등급 → 점수 계수. 본 계좌의 감쇠 규칙과 같은 뜻을 쓴다:
# '실패'는 아예 0, '미측정'은 절반("통과가 아니라 모른다").
GRADE_SCALE = {"통과": 1.0, "주의": 0.7, "미측정": 0.5, "실패": 0.0}


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


def score_symbols(weights: dict, grades: dict | None = None,
                  tilt: dict | None = None) -> dict:
    """종목별 점수 — 클수록 확신이 크다. 음수·0은 후보에서 빠진다.

    지어낸 점수가 아니라 본 계좌가 이미 계산한 값들의 곱이다. 새 규칙을
    여기서 발명하면 '배분 방식의 효과'에 '새 규칙의 효과'가 섞인다.
    """
    grades, tilt = grades or {}, tilt or {}
    out = {}
    for k, w in (weights or {}).items():
        s = max(0.0, float(w))
        if s <= 0:
            continue
        g = grades.get(k)
        if isinstance(g, dict):                  # 장부 형식: {"grade": ..., }
            g = g.get("grade")
        s *= GRADE_SCALE.get(str(g), 1.0 if g is None else 0.5)
        t = tilt.get(k)
        if t is not None:
            try:
                s *= max(0.0, float(t))
            except (TypeError, ValueError):
                pass
        if s > 0:
            out[k] = s
    return out


def concentrate(scores: dict, top_k: int = TOP_K) -> dict:
    """상위 K개만 남기고 **점수에 비례해** 비중을 준다(합계 1 이하).

    ⚠️ 동점 처리를 이름순으로 고정한다 — 그러지 않으면 같은 입력이 날마다
       다른 포트폴리오를 만들고, 그러면 이 실험은 재현할 수 없다.
    """
    if not scores:
        return {}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:max(1, top_k)]
    total = sum(v for _, v in ranked)
    if total <= 0:
        return {}
    return {k: v / total for k, v in ranked}


def run_gen2(*, bar: str, weights: dict, marks: dict,
             grades: dict | None = None, tilt: dict | None = None,
             top_k: int = TOP_K, state_dir: str = "state") -> dict | None:
    """하루 1회 전진. 같은 봉 멱등 · 시세 없는 날 무기록(그림자 계좌 규약)."""
    from quant.utils.jsonio import atomic_write_json

    if not marks:
        return None
    path = os.path.join(state_dir, FILE)
    st = _load(path)
    if st["history"] and st["history"][-1].get("date") == bar:
        return st["history"][-1]

    # ① 전일 목표 × 오늘 수익 (1봉 지연 — 오늘 정한 비중은 내일부터 번다)
    ret = 0.0
    pw, pm = st.get("prev_weights") or {}, st.get("prev_marks") or {}
    for k, w in pw.items():
        p0, p1 = pm.get(k), marks.get(k)
        if p0 and p1 and float(p0) > 0:
            ret += float(w) * (float(p1) / float(p0) - 1.0)
    equity = float(st["equity"]) * (1.0 + ret)

    # ② 오늘의 목표 = 줄 세워 상위 K개, 점수 비례
    target = concentrate(score_symbols(weights, grades, tilt), top_k)
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
    # 낙폭은 공용 헬퍼로만 잰다(즉석 수식은 입금이 생기면 고점을 오해한다 —
    # 킬스위치가 이미 겪은 결함이라 계약 테스트가 즉석 수식을 금지한다).
    from quant.live.ledger_basics import drawdown_from_index
    dd = drawdown_from_index([peak / START_CASH, equity / START_CASH])
    rec = {"date": bar, "equity": round(equity, 2),
           "return_pct": round((equity / START_CASH - 1) * 100, 3),
           "mdd_pct": round(dd * 100, 2),
           "n_held": len(target), "top_k": int(top_k),
           "picks": {k: round(v, 4) for k, v in
                     sorted(target.items(), key=lambda kv: -kv[1])}}
    st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
    atomic_write_json(path, st)
    return rec


def gen2_public(state_dir: str = "state") -> dict | None:
    st = _load(os.path.join(state_dir, FILE))
    if not st["history"]:
        return None
    last = st["history"][-1]
    worst = min((r.get("mdd_pct", 0.0) for r in st["history"]), default=0.0)
    from quant.live.daily import cost_basis_bp
    return {"equity": last["equity"], "return_pct": last["return_pct"],
            "cost_basis_bp": cost_basis_bp(state_dir),
            "days": len(st["history"]), "worst_mdd_pct": round(worst, 2),
            "n_held": last.get("n_held"), "top_k": last.get("top_k"),
            "picks": last.get("picks") or {},
            "note": (
        "본 계좌는 신호가 켜진 종목에 **똑같이** 나눠 담습니다(균등 조각). "
        "이 그림자는 같은 신호를 받되 **줄을 세워 상위 몇 개에만**, 그것도 "
        "점수에 비례해 담습니다 — 확신이 두 배면 금액도 두 배입니다. "
        "집중은 공짜가 아니라서 맞을 때 더 벌고 틀릴 때 더 잃습니다. "
        "반드시 최대낙폭과 함께 읽으세요. 종가 평가·수수료만 차감이라 본 "
        "계좌와 절대 비교는 안 되고, 배분 방식의 효과를 보는 용도입니다.")}
