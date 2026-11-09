"""사전 등록 실험의 **확정 판정을 판정일에 기계가 낸다** (2026-11-09 감사 361).

사장님: *"영구적이어야 해."* — 그때까지 판정일이 오면 사람이(나) 손으로 재야 했다.
사람이 잊으면 판정은 영영 안 나고, 늦게 재면 판정일 뒤의 자료가 섞인다. 둘 다
사전 등록의 뜻을 무너뜨린다.

■ 하는 일

  판정일(`judge_on`)이 지난 실험마다 **한 번만** 잰다:
    · 판정일까지의 자료만 쓴다(그 뒤 줄은 잘라 낸다).
    · 등록된 통계(짝지은 일수익 차이의 양측 t)와 등록된 보정(본페로니 k)으로.
    · 등록된 채택 보류 조건(낙폭 1.5배 등)을 함께 싣는다.
    · 결과는 `state/final_judgements.json`에 **얼린다** — 다음 날 다시 재지 않는다.
      다시 재면 판정일 뒤 자료로 판정이 바뀔 수 있고, 그건 골대 이동이다.

  판정일 전에 닫은 실험(감사 357)은 **판정하지 않는다** — 그렇다고 적는다.

■ 정직한 한계

  · 고정 기간 t는 정규 근사다(표본 20일 미만이면 판정하지 않고 '표본 부족').
  · 채택 보류 조건은 얼리는 날의 장부로 잰다(판정일 다음 배치 — 대개 하루 차이).
  · 판정은 **채택이 아니다.** 등록의 `on_fail`(현행 유지 + 공개)과 채택은 사장님
    결정이다 — 이 모듈은 판정을 내고 적을 뿐 아무것도 바꾸지 않는다.
"""
from __future__ import annotations

import json
import math
import os
from statistics import NormalDist

FILE = "final_judgements.json"
MIN_DAYS = 20
#: trend_core_live 등록 문구의 기준(텍스트와 같은지 검사가 본다).
TREND_MEETS, TREND_FLOOR, TREND_MDD = 0.5, 0.0, -15.0


def _t_test(diffs: list[float], alpha: float) -> dict:
    n = len(diffs)
    if n < MIN_DAYS:
        return {"n": n, "verdict": "표본 부족", "decided": False}
    mean = sum(diffs) / n
    var = sum((x - mean) ** 2 for x in diffs) / (n - 1)
    sd = math.sqrt(var)
    t = mean / sd * math.sqrt(n) if sd > 0 else 0.0
    p = 2 * (1 - NormalDist().cdf(abs(t)))
    sig = p < alpha
    return {"n": n, "mean_daily_pct": round(mean * 100, 4), "t": round(t, 3),
            "p": round(p, 4), "alpha": round(alpha, 4), "decided": True,
            "verdict": ("앞쪽 우세" if t > 0 else "뒤쪽 우세") if sig else "차이 없음(우연과 구별 안 됨)"}


def _trend_core(exp: dict, state_dir: str) -> dict:
    """본 계좌 추세 코어 — 등록: 비용 후 일수익의 연율 샤프·최대낙폭."""
    path = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    try:
        with open(path, encoding="utf-8") as f:
            hist = json.load(f).get("history") or []
    except (OSError, ValueError):
        return {"verdict": "재료 없음", "code": "no_data", "decided": False}
    rows = [r for r in hist if exp["start"] <= str(r.get("date"))[:10] <= exp["judge_on"]
            and r.get("equity")]
    eq = [float(r["equity"]) for r in rows]
    rets = [b / a - 1 for a, b in zip(eq, eq[1:]) if a > 0]
    if len(rets) < MIN_DAYS:
        return {"n": len(rets), "verdict": "표본 부족", "code": "thin", "decided": False}
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / (len(rets) - 1))
    sharpe = mean / sd * math.sqrt(365) if sd > 0 else 0.0   # 장부는 달력일(코인 포함)
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    mdd_pct = mdd * 100
    if sharpe < TREND_FLOOR or mdd_pct < TREND_MDD:
        v, code = "실패", "fail"
    elif sharpe < TREND_MEETS:
        v, code = "하한 미달", "below_floor"
    else:
        v, code = "기대치에 부합", "meets"
    t = mean / sd * math.sqrt(len(rets)) if sd > 0 else 0.0
    return {"n": len(rets), "sharpe_annual": round(sharpe, 3), "mdd_pct": round(mdd_pct, 2),
            "t_mean_positive": round(t, 3), "verdict": v, "code": code, "decided": True,
            "baseline_6040": "같은 구간 60/40 보유는 주간 엔진 선택 장부의 후보(6040)로 병기"}


def judge_due(state_dir: str = "state", today: str | None = None) -> dict:
    """판정일이 지난 실험을 판정해 얼린다(멱등). 이미 얼린 것은 그대로 돌려준다."""
    import datetime as dt

    from quant.live import sequential as S
    from quant.live.prereg import PREREGISTERED
    from quant.live.track_closure import CLOSED_ON

    today = today or dt.date.today().isoformat()
    path = os.path.join(state_dir, FILE)
    try:
        with open(path, encoding="utf-8") as f:
            done = json.load(f)
    except (OSError, ValueError):
        done = {}
    closed = {"intraday_1h", "cadence_ladder", "limit_shadow", "intraday_us", "us_limit_shadow"}
    changed = False
    for key, exp in PREREGISTERED.items():
        if key in done or today <= str(exp.get("judge_on")):
            continue
        rec = {"name": exp.get("name"), "judge_on": exp["judge_on"],
               "judged_on": today, "on_fail": exp.get("on_fail")}
        if key in closed:
            rec.update({"verdict": "판정 안 함 — 판정일 전에 닫았다", "code": "closed",
                        "decided": False,
                        "closed_on": CLOSED_ON})
        elif key == "trend_core_live":
            rec.update(_trend_core(exp, state_dir))
        else:
            pairs = S._pairs_for(key, state_dir, upto=exp["judge_on"])
            if not pairs:
                rec.update({"verdict": "재료 없음 — 장부를 못 읽었다", "code": "no_data",
                            "decided": False})
            else:
                k = S.registered_comparisons(exp)
                rec["comparisons"] = k
                rec["pairs"] = {n: _t_test(d, float(exp.get("alpha", 0.05)) / k)
                                for n, d in pairs.items()}
                hold = S._adoption_hold(key, state_dir)
                if hold:
                    rec["adoption_hold"] = hold
                rec["decided"] = any(v.get("decided") for v in rec["pairs"].values())
                sig = [n for n, v in rec["pairs"].items()
                       if v.get("verdict", "").endswith("우세")]
                rec["verdict"] = ("표본 부족" if not rec["decided"] else
                                  (f"유의한 차이 {len(sig)}쌍" if sig else
                                   "차이 없음(우연과 구별 안 됨) — 현행 유지"))
                rec["code"] = ("thin" if not rec["decided"] else
                               ("significant" if sig else "no_difference"))
                rec["significant_pairs"] = sig
        done[key] = rec
        changed = True
    if changed:
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(done, f, ensure_ascii=False, indent=1)
    return done
