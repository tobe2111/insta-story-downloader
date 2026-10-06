"""넘친 예산 재분배 그림자 — 버리는 것과 다시 나누는 것을 나란히 잰다 (감사 332).

사장님 질문(2026-10-01): *"현금은 왜 계속 이 비율로 들고있는거야?"* → 답을
들은 뒤(2026-10-06): *"둘 다 진행."*

본 계좌의 배분은 HRP 예산에 확신도 기울기를 곱한 뒤 **종목당 상한(3/n)을
넘는 몫을 버린다**(`daily.py`: "상한 초과분은 재분배하지 않고 버림 —
보수적"). HRP는 덜 흔들리는 자산(채권·달러·물가채)에 예산을 몰아주므로,
그 버림이 매일 자본의 절반 안팎이었다(2026-09-30 실측: 예산 합 0.51).

버리는 것이 나쁜지는 **말로 정하지 않는다.** 그건 '무엇을 얼마나 사는가'를
바꾸는 일이라 사장님 방침(2026-08-27: 투자 로직은 기계가 개선한다)상 손으로
바꾸지 않는다. 대신 같은 신호를 받는 가상 계좌 둘을 나란히 굴린다:

    discard       지금 규칙 — 상한을 넘친 예산을 버린다
    redistribute  넘친 몫을 상한에 안 걸린 종목들에 비례해 다시 나눈다
                  (물 채우기 — 다시 나눈 결과도 상한을 넘지 않는다)

**두 계좌의 차이는 그것 하나뿐이다.** 신호·변동성 타깃·브레이크·실적 가드·
검증 게이트·켈리 상한은 본 계좌와 **같은 식**(`daily._final_weight`)을 쓰고,
변동성 타깃의 배수는 각 계좌가 자기 예산으로 다시 잰다(예산이 바뀌면 위험도
바뀐다 — 같은 배수를 쓰면 재분배 쪽이 목표보다 큰 위험을 진다).

정직한 규약(다른 그림자와 같다):
  · 종가 평가 · 전일 목표를 오늘 수익에 적용(1봉 지연) · 회전 × 실측 편도
    비용(`shadow_cost`) 차감 · 무레버리지(총노출 100% 상한).
  · 정수 주 맞추기는 **두 계좌 모두 안 한다** — 둘에 같은 조건을 거는 것이
    목적이라 본 계좌와의 절대 비교는 안 된다. 비교는 두 계좌 사이에서만.
  · 판정은 `prereg.PREREGISTERED["budget_shadow"]`에 데이터보다 먼저 박았다.
  · ⚠️ 재분배 쪽이 이겨도 **본 계좌 적용은 자동이 아니다** — 배분 규칙은
    구조 세대 축이라 판정일 경계에서 별도 공지 후에만 넘어간다.
  · ⚠️ 이 실험은 **넘친 예산**만 다룬다. 같은 날 다른 큰 몫 — 검증 게이트가
    0으로 만드는 종목에 예산이 가 있는 것 — 은 이 실험이 바꾸지 않는다.
"""
from __future__ import annotations

import json
import os

from quant.live import shadow_clock as clock
from quant.live import shadow_cost
from quant.utils.logging import get_logger

log = get_logger("live.budget_shadow")

START_CASH = 1_000_000.0
FILE = "budget_shadow.json"
KEEP_DAYS = 400
ARMS = ("discard", "redistribute")


def redistribute(raw: dict, cap: float, budget: float | None = None) -> dict:
    """넘친 몫을 상한에 안 걸린 종목들에 비례해 다시 나눈다(물 채우기).

    raw: 상한 전 예산(음수는 0으로 본다). budget: 나눌 총액(기본: raw의 합).
    돌려주는 예산은 **어느 종목도 cap을 넘지 않고**, 합은 budget을 넘지
    않는다(전부 상한에 걸리면 합이 budget보다 작을 수 있다 — 그 몫은 정말로
    갈 곳이 없다). 예산이 0인 종목은 받지 않는다 — 배분 방식이 '이 종목에는
    주지 말라'고 한 판단을 재분배가 뒤집으면 안 된다.
    """
    pos = {k: max(0.0, float(v)) for k, v in (raw or {}).items()}
    left = float(sum(pos.values()) if budget is None else budget)
    out = {k: 0.0 for k in pos}
    free = {k: v for k, v in pos.items() if v > 0}
    while free and left > 1e-15:
        tot = sum(free.values())
        scale = left / tot
        over = [k for k, v in free.items() if v * scale >= cap - 1e-15]
        if not over:
            for k, v in free.items():
                out[k] = v * scale
            break
        for k in over:
            out[k] = cap
            left -= cap
            del free[k]
    return out


def discard(raw: dict, cap: float) -> dict:
    """지금 규칙 — 상한을 넘친 몫을 버린다(`daily.py`와 같은 식)."""
    return {k: min(max(0.0, float(v)), cap) for k, v in (raw or {}).items()}


def arm_targets(*, weights: dict, slices: dict, cap: float, rets_map: dict,
                tgt_vol: float, final) -> tuple[dict, float]:
    """한 계좌의 오늘 목표 비중과 그 계좌의 변동성 배수.

    final(key, w, slice, vscale) — 본 계좌와 같은 최종 비중 식.
    """
    from quant.risk.portfolio_vol import vol_scale
    base = {k: float(w) * slices.get(k, 0.0) for k, w in weights.items()}
    vs, _ = vol_scale(base, rets_map, tgt_vol)
    tgt = {k: float(final(k, float(w), slices.get(k, 0.0), vs))
           for k, w in weights.items()}
    tgt = {k: max(-cap, min(cap, v)) for k, v in tgt.items()}   # 종목 상한
    gross = sum(abs(v) for v in tgt.values())
    if gross > 1.0:                                  # 가상이라도 빚은 못 낸다
        tgt = {k: v / gross for k, v in tgt.items()}
    return tgt, float(vs)


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and "history" in st:
            return st
    except (OSError, ValueError):
        pass
    return {"arms": {a: {"equity": START_CASH, "peak": START_CASH,
                         "prev_weights": {}} for a in ARMS},
            "prev_marks": {}, "history": []}


def run_budget_shadow(*, bar: str, weights: dict, raw_slices: dict, cap: float,
                      rets_map: dict, tgt_vol: float, final, marks: dict,
                      state_dir: str = "state") -> dict | None:
    """하루 1회 전진. 같은 봉 멱등 · 과거로 가는 봉은 쓰지 않는다."""
    from quant.live.ledger_basics import drawdown_from_index
    from quant.utils.jsonio import atomic_write_json

    if not marks or not weights:
        return None
    path = os.path.join(state_dir, FILE)
    st = _load(path)
    move = clock.step(st["history"], bar)
    if move == clock.SAME:
        return st["history"][-1]
    if move == clock.BACKWARDS:
        log.error("예산 재분배 그림자: 판정일이 과거로 갔다 — 기록 %s → 지금 %s. "
                  "쓰지 않는다.", st["history"][-1].get("date"), bar)
        return None

    keyed = {k: raw_slices.get(k, 0.0) for k in weights}
    budget = sum(max(0.0, float(v)) for v in keyed.values())
    budgets = {"discard": discard(keyed, cap),
               "redistribute": redistribute(keyed, cap, budget)}
    pm = st.get("prev_marks") or {}
    rec = {"date": bar, "budget_raw": round(budget, 4), "arms": {}}
    for arm in ARMS:
        a = st["arms"].setdefault(arm, {"equity": START_CASH,
                                        "peak": START_CASH,
                                        "prev_weights": {}})
        # ① 전일 목표 × 오늘 수익(1봉 지연)
        ret = 0.0
        pw = a.get("prev_weights") or {}
        for k, w in pw.items():
            p0, p1 = pm.get(k), marks.get(k)
            if p0 and p1 and float(p0) > 0:
                ret += float(w) * (float(p1) / float(p0) - 1.0)
        equity = float(a["equity"]) * (1.0 + ret)
        # ② 오늘의 목표 — 예산만 다르고 나머지는 본 계좌와 같은 식
        tgt, vs = arm_targets(weights=weights, slices=budgets[arm], cap=cap,
                              rets_map=rets_map, tgt_vol=tgt_vol, final=final)
        equity -= equity * shadow_cost.turnover_cost(tgt, pw, state_dir)
        peak = max(float(a.get("peak") or START_CASH), equity)
        dd = drawdown_from_index([peak / START_CASH, equity / START_CASH])
        a.update({"equity": round(equity, 2), "peak": round(peak, 2),
                  "prev_weights": {k: round(v, 6) for k, v in tgt.items()
                                   if abs(v) > 0}})
        rec["arms"][arm] = {
            "equity": round(equity, 2),
            "return_pct": round((equity / START_CASH - 1) * 100, 3),
            "day_ret": round(ret, 6),
            "mdd_pct": round(dd * 100, 2),
            "budget": round(sum(budgets[arm].values()), 4),
            "gross": round(sum(abs(v) for v in tgt.values()), 4),
            "vscale": round(vs, 4),
        }
    keys = set(pm) | set(marks)
    st["prev_marks"] = {k: float(marks[k]) for k in keys if marks.get(k)}
    st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
    atomic_write_json(path, st)
    return rec


def paired_diffs(history: list) -> list[float]:
    """재분배 − 버림의 일수익 차이(짝지은 관측). 첫 줄은 전일 목표가 없어 뺀다."""
    rows = sorted(history or [], key=lambda r: str(r.get("date") or ""))
    out = []
    for i, r in enumerate(rows):
        if i == 0:
            continue
        a = (r.get("arms") or {})
        if "discard" in a and "redistribute" in a:
            out.append(float(a["redistribute"].get("day_ret", 0.0))
                       - float(a["discard"].get("day_ret", 0.0)))
    return out


def budget_shadow_public(state_dir: str = "state") -> dict | None:
    """status.json 탑재용 — 두 계좌의 현재, 차이의 크기와 우연 여부."""
    import math

    st = _load(os.path.join(state_dir, FILE))
    if not st["history"]:
        return None
    last = clock.latest_row(st["history"])
    diffs = paired_diffs(st["history"])
    n = len(diffs)
    t = None
    mean_bp = None
    if n >= 2:
        m = sum(diffs) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in diffs) / (n - 1))
        mean_bp = round(m * 1e4, 2)
        t = round(m / sd * math.sqrt(n), 2) if sd > 0 else None
    arms = {}
    for arm in ARMS:
        rows = [r["arms"][arm] for r in st["history"] if arm in (r.get("arms") or {})]
        cur = (last.get("arms") or {}).get(arm) or {}
        arms[arm] = {
            "equity": cur.get("equity"),
            "return_pct": cur.get("return_pct"),
            "worst_mdd_pct": round(min((x.get("mdd_pct", 0.0) for x in rows),
                                       default=0.0), 2),
            "avg_budget": round(sum(x.get("budget", 0.0) for x in rows)
                                / len(rows), 4) if rows else None,
            "avg_gross": round(sum(x.get("gross", 0.0) for x in rows)
                               / len(rows), 4) if rows else None,
        }
    from quant.live.daily import cost_basis_bp
    from quant.live.prereg import PREREGISTERED
    reg = PREREGISTERED.get("budget_shadow") or {}
    return {
        "arms": arms,
        "days": clock.distinct_days(st["history"]),
        "paired": {"n": n, "mean_bp_per_day": mean_bp, "t": t},
        "judge_on": reg.get("judge_on"),
        "cost_basis_bp": cost_basis_bp(state_dir),
        **({"mixed_rows": {"why": clock.MIXED_WHY, **ooo}}
           if (ooo := clock.out_of_order(st["history"])) else {}),
        "note": ("같은 신호·같은 안전장치에 넘친 예산의 처리만 다른 가상 계좌 "
                 "둘입니다. 판정 전의 차이는 운일 수 있습니다 — 판정은 등록된 "
                 "날에 등록된 기준으로만 합니다."),
    }
