"""배분 사다리 — 같은 신호에 배분 방법만 바꾼 가상 계좌들을 나란히 (2026-08-19).

이 시스템은 "어떤 종목을"(오디션)과 "언제"(주기 사다리)는 측정으로
진화시키면서, "얼마씩 나눌까"(배분)는 HRP 고정 규칙이었고 한 번도
검증대에 선 적이 없다. 여기서 그 비대칭을 끝낸다: 본 계좌가 만든 **같은
신호·같은 데이터**에 배분 방법만 바꿔 가상 계좌 4개를 나란히 굴린다.

    hrp      — 현행(계층적 리스크 패리티)
    erc      — 위험기여도 균등
    equal    — 자본 균등(1/n)
    inv_vol  — 역변동성(변동성이 큰 종목일수록 적게)

정직한 규약 (읽는 사람이 반드시 알아야 할 것):
  · 이 실험은 **배분 간 상대 비교 전용**이다. 본 계좌의 나머지 층
    (변동성 타깃·킬스위치·검증 게이트·켈리 상한·확신도 틸트)은 여기 없다 —
    슬라이스 효과를 격리하려고 전부 공통 기준선으로 뺐다. 따라서 이
    계좌들의 절대 성적을 본 계좌와 비교하면 안 된다.
  · 평가: 종가 마크 · 전일 목표를 오늘 수익에 적용(1봉 지연) ·
    회전율×수수료만 차감. 슬리피지 없음 — 네 계좌가 같은 규약이라
    상대 비교는 공정하다.
  · 트랙이 4개다 — 우연히 좋아 보이는 승자가 나올 확률도 4배다.
    판정은 곡선이 충분히 갈라진 뒤(수개월)에나 의미가 있다.
  · 본 계좌 판정(90일 관문)에는 쓰지 않는다.

실패 원칙: 이 실험의 어떤 실패도 본 계좌 배치를 죽이면 안 된다 —
호출부(daily.py)가 예외를 삼키고 사유만 남긴다.
"""
from __future__ import annotations

import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.alloc_ladder")

ALLOC_METHODS = ("hrp", "erc", "equal", "inv_vol")
START_CASH = 1_000_000.0
FEE = 0.001            # 회전율당 10bp — 네 계좌 공통(상대 비교 전용)


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
DIR = "alloc_ladder"
KEEP_DAYS = 400


def _inv_vol_slices(rets_map: dict, n_total: int) -> dict | None:
    """역변동성 슬라이스 — ERC와 같은 데이터 규약(40일 이상), 상한 3/n."""
    vols = {}
    for key, s in rets_map.items():
        s = s.dropna()
        if len(s) >= 40:
            v = float(s.tail(90).std())
            if v > 0:
                vols[key] = 1.0 / v
    if len(vols) < 2:
        return None
    tot = sum(vols.values())
    budget = len(vols) / n_total
    cap = 3.0 / n_total
    return {k: min(v / tot * budget, cap) for k, v in vols.items()}


def method_slices(method: str, weights: dict, rets_map: dict,
                  n_total: int) -> dict:
    """방법별 슬라이스 — 실패·퇴화 시 균등 폴백(현행 사다리와 같은 규약).

    hrp·erc는 본 계좌가 쓰는 **바로 그 함수**를 부른다(같은 규칙 한 곳) —
    여기 복사해 두면 반드시 어긋난다.
    """
    from quant.live.hrp import is_allocation
    s = None
    if method == "hrp":
        from quant.live.daily import _hrp_slices
        s = _hrp_slices(rets_map, n_total)
        s = s if is_allocation(s) else None
    elif method == "erc":
        from quant.live.daily import _erc_slices
        s = _erc_slices(rets_map, n_total)
        s = s if is_allocation(s) else None
    elif method == "inv_vol":
        s = _inv_vol_slices(rets_map, n_total)
    return s or {k: 1.0 / n_total for k in weights}


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


def run_alloc_ladder(*, bar: str, weights: dict, rets_map: dict,
                     marks: dict, n_total: int,
                     state_dir: str = "state") -> dict | None:
    """하루 1회 — 방법별 가상 계좌를 한 봉 전진시킨다. 같은 봉이면 멱등."""
    from quant.utils.jsonio import atomic_write_json

    if not marks:
        # 시세가 없는 날은 아무것도 쓰지 않는다 — 빈 회차가 기록으로 남으면
        # 곡선이 가짜 평평함을 얻는다(주기 사다리에서 배운 규칙).
        return None
    root = os.path.join(state_dir, DIR)
    os.makedirs(root, exist_ok=True)
    out = {}
    for method in ALLOC_METHODS:
        path = os.path.join(root, f"{method}.json")
        st = _load(path)
        if st["history"] and st["history"][-1].get("date") == bar:
            out[method] = st["history"][-1]          # 같은 봉 재실행 — 멱등
            continue

        # ① 전일 목표를 오늘 수익에 적용(1봉 지연 — 본 계좌와 같은 방향의 규약)
        ret = 0.0
        pw, pm = st.get("prev_weights") or {}, st.get("prev_marks") or {}
        for k, w in pw.items():
            p0, p1 = pm.get(k), marks.get(k)
            if p0 and p1 and float(p0) > 0:
                ret += float(w) * (float(p1) / float(p0) - 1.0)
        equity = float(st["equity"]) * (1.0 + ret)

        # ② 오늘의 목표 비중 = 신호 비중 × 방법별 슬라이스
        sl = method_slices(method, weights, rets_map, n_total)
        target = {k: float(w) * float(sl.get(k, 1.0 / n_total))
                  for k, w in weights.items()}
        turnover = sum(abs(target.get(k, 0.0) - float(pw.get(k, 0.0)))
                       for k in set(target) | set(pw))
        equity -= equity * _turnover_cost(target, pw, state_dir)

        keys = set(target) | set(pw)
        st.update({
            "equity": round(equity, 2),
            "prev_weights": {k: round(v, 6) for k, v in target.items()},
            "prev_marks": {k: float(marks[k]) for k in keys
                           if marks.get(k)},
        })
        rec = {"date": bar, "equity": round(equity, 2),
               "return_pct": round((equity / START_CASH - 1) * 100, 3),
               "gross": round(sum(abs(v) for v in target.values()), 4)}
        st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
        atomic_write_json(path, st)
        out[method] = rec
    return out


def ladder_public(state_dir: str = "state") -> dict | None:
    """사이트 표시용 요약 — 방법별 현재 자산·수익률·표본 일수."""
    root = os.path.join(state_dir, DIR)
    if not os.path.isdir(root):
        return None
    rows = {}
    for method in ALLOC_METHODS:
        st = _load(os.path.join(root, f"{method}.json"))
        if not st["history"]:
            continue
        last = st["history"][-1]
        rows[method] = {"equity": last["equity"],
                        "return_pct": last["return_pct"],
                        "days": len(st["history"])}
    if not rows:
        return None
    from quant.live.daily import cost_basis_bp
    return {"tracks": rows, "cost_basis_bp": cost_basis_bp(state_dir), "note": (
        "같은 신호에 배분 방법만 바꾼 가상 계좌들입니다(종가 평가·수수료만, "
        "본 계좌의 변동성 타깃·킬스위치 등은 없음 — 배분 간 상대 비교 전용). "
        "트랙이 4개라 우연히 좋아 보이는 승자가 나올 확률도 4배입니다 — "
        "판정은 곡선이 충분히 갈라진 뒤에만 의미가 있습니다.")}
