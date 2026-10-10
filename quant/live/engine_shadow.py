"""엔진 후보 여섯을 **실제 장부로** 나란히 굴린다 (감사 342).

사장님(2026-10-10): "모두 진행해" — 엔진 선택(감사 341)의 후속 셋 중 ③.

엔진 선택기는 과거 **시뮬레이션**만 보고 고른다. 같은 코드·같은 비용이지만,
실제 배치가 받는 시세·체결 시점·환율과는 다를 수 있다. 그래서 후보 여섯을
매일 배치 안에서 **가상 계좌**로 굴린다 — 시뮬레이션과 실제가 어긋나면 그
차이가 숫자로 드러난다.

■ 규칙(본 계좌와 같은 자)

  · 목표: 그 후보의 목표 비중(`engine_select.candidate_targets`), 검증과 같은
    주기(`engine_select.target_day` — 금요일 또는 끝난 달).
  · 수익: 어제 보유 × 오늘 **원화 평가가**(환율 변화 포함) 변화. 보유는 가격을
    따라 표류한다.
  · 매매: 목표와 보유의 차가 밴드(2%)보다 클 때만 고친다. 청산(목표 0)은 항상.
  · 비용: 종목별 실측 편도(`shadow_cost`) + 미국 자산 **순매매**에 환전 비용
    (`tax_kr.fx_charge`와 같은 셈).
  · 시계: 같은 봉은 한 번, 과거로 가는 봉은 쓰지 않는다(`shadow_clock`).

■ 정직한 한계

  · 정수 주·최소 주문을 안 맞춘다(비중 그대로) — 본 계좌보다 약간 매끄럽다.
  · 본 계좌 회차에서만 돈다(대조군 신호가 섞이면 안 된다).
  · 판정을 정하는 장치가 아니다 — 선택기는 여전히 장기 시뮬레이션으로 고른다.
    이 장부는 "그 시뮬레이션이 지금 실제와 맞는가"를 보는 계측기다.
"""
from __future__ import annotations

import json
import logging
import os

from quant.live import shadow_clock as clock
from quant.live import shadow_cost

log = logging.getLogger(__name__)

FILE = "engine_shadow.json"
START = 1_000_000.0
BAND = 0.02
KEEP_DAYS = 400


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and "history" in st:
            return st
    except (OSError, ValueError):
        pass
    return {"arms": {}, "prev_marks": {}, "history": []}


def rebalance(held: dict, target: dict, band: float = BAND) -> dict:
    """밴드 안이면 그대로, 청산은 항상 — 시뮬레이션(`trend_core.simulate`)과 같은 규칙."""
    new = dict(held)
    for k in set(held) | set(target):
        t = float(target.get(k, 0.0))
        cur = float(held.get(k, 0.0))
        if t == 0.0 and cur != 0.0:
            new[k] = 0.0
        elif abs(t - cur) >= band:
            new[k] = t
    return {k: v for k, v in new.items() if abs(v) > 1e-12}


def fx_cost(held: dict, new: dict, spread: float) -> float:
    net = sum(float(new.get(k, 0.0)) - float(held.get(k, 0.0))
              for k in set(held) | set(new) if k.startswith("us_stock:"))
    return abs(net) * spread


def run_engine_shadow(*, bar: str, closes_map: dict, weights: dict,
                      marks: dict, active: str | None,
                      state_dir: str = "state") -> dict | None:
    """하루 1회 전진. 같은 봉 멱등 · 과거로 가는 봉은 쓰지 않는다."""
    from quant.live.ledger_basics import drawdown_from_index
    from quant.live.tax_kr import fx_spread
    from quant.portfolio import engine_select as E
    from quant.portfolio import trend_core as T
    from quant.utils.jsonio import atomic_write_json

    if not marks or not weights:
        return None
    path = os.path.join(state_dir, FILE)
    st = _load(path)
    move = clock.step(st["history"], bar)
    if move == clock.SAME:
        return st["history"][-1]
    if move == clock.BACKWARDS:
        log.error("엔진 후보 그림자: 판정일이 과거로 갔다 — 기록 %s → 지금 %s. "
                  "쓰지 않는다.", st["history"][-1].get("date"), bar)
        return None
    closes = T.align_business_days(
        {k: v for k, v in closes_map.items() if k in weights})
    if closes.empty:
        return None
    spread = fx_spread(state_dir)
    pm = st.get("prev_marks") or {}
    rec = {"date": bar, "active": active, "arms": {}}
    for name in E.CANDIDATES:
        a = st["arms"].setdefault(name, {"equity": START, "peak": START,
                                         "held": {}})
        held = {k: float(v) for k, v in (a.get("held") or {}).items()}
        # ① 어제 보유 × 오늘 평가가 변화(원화 — 환율 포함). 보유는 표류한다.
        rets = {}
        for k in held:
            p0, p1 = pm.get(k), marks.get(k)
            rets[k] = (float(p1) / float(p0) - 1.0) if p0 and p1 and float(p0) > 0 else 0.0
        port = sum(w * rets[k] for k, w in held.items())
        equity = float(a["equity"]) * (1.0 + port)
        if 1.0 + port > 0:
            held = {k: w * (1.0 + rets[k]) / (1.0 + port) for k, w in held.items()}
        # ② 오늘의 목표(검증과 같은 주기) → 밴드 → 비용
        tgt, cfg = E.candidate_targets(closes, name)
        day = E.target_day(tgt.index, cfg.rebalance)
        row = tgt.loc[day].fillna(0.0)
        target = {k: float(row.get(k, 0.0)) for k in weights
                  if abs(float(row.get(k, 0.0))) > 0}
        new = rebalance(held, target)
        cost = (shadow_cost.turnover_cost(new, held, state_dir)
                + fx_cost(held, new, spread))
        equity *= (1.0 - cost)
        peak = max(float(a.get("peak") or START), equity)
        dd = drawdown_from_index([peak / START, equity / START])
        a.update({"equity": round(equity, 2), "peak": round(peak, 2),
                  "held": {k: round(v, 6) for k, v in new.items()}})
        rec["arms"][name] = {
            "equity": round(equity, 2),
            "return_pct": round((equity / START - 1) * 100, 3),
            "day_ret": round(port, 6),
            "cost_pct": round(cost * 100, 4),
            "mdd_pct": round(dd * 100, 2),
            "gross": round(sum(abs(v) for v in new.values()), 4),
        }
    keys = set(pm) | set(marks)
    st["prev_marks"] = {k: float(marks[k]) for k in keys if marks.get(k)}
    st["history"] = (st["history"] + [rec])[-KEEP_DAYS:]
    atomic_write_json(path, st)
    return rec


def engine_shadow_public(state_dir: str = "state") -> dict | None:
    """status.json 탑재용 — 후보마다 그림자 계좌의 지금 성적."""
    from quant.portfolio import engine_select as E

    st = _load(os.path.join(state_dir, FILE))
    if not st["history"]:
        return None
    last = clock.latest_row(st["history"])
    arms = {}
    for name in E.CANDIDATES:
        rows = [r["arms"][name] for r in st["history"]
                if name in (r.get("arms") or {})]
        cur = (last.get("arms") or {}).get(name) or {}
        if not rows:
            continue
        arms[name] = {
            "label": E.LABELS[name],
            "equity": cur.get("equity"),
            "return_pct": cur.get("return_pct"),
            "worst_mdd_pct": round(min(x.get("mdd_pct", 0.0) for x in rows), 2),
            "cost_pct": round(sum(x.get("cost_pct", 0.0) for x in rows), 3),
            "avg_gross": round(sum(x.get("gross", 0.0) for x in rows) / len(rows), 4),
        }
    from quant.live.daily import cost_basis_bp
    return {"since": str(st["history"][0].get("date")),
            "asof": last.get("date"), "active": last.get("active"),
            "days": clock.distinct_days(st["history"]), "arms": arms,
            "cost_basis_bp": cost_basis_bp(state_dir)}
