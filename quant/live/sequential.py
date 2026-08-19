"""조기 판정 — **언제 봐도 유효한** 순차검정 (2026-08-19, 사장님 지시).

    "석달보다 더 기간을 최대한 단축시킬 수 있는 방법은?"

⚠️ 먼저 왜 지금까지 안 봤는가. 고정 판정일(90일) 방식은 **딱 한 번만**
   봐야 유의수준이 지켜진다. 매일 들여다보며 "지금 이겼네"를 찾으면,
   진짜 차이가 없어도 언젠가는 우연히 문턱을 넘는다 — 거짓 승리 확률이
   5%가 아니라 수십 %까지 오른다(반복 훔쳐보기 문제). 그래서 이 저장소는
   판정일 전에는 아예 판정하지 않는다고 못 박아 왔다.

⚠️ 그런데 **훔쳐볼 권리를 미리 사 두는** 방법이 있다. 경계선을 데이터가
   쌓이기 전에 박아 두면, 매일 봐도 거짓 승리 확률이 약속한 값을 넘지
   않는다(Ville 부등식 · Robbins 정규혼합 신뢰수열). 효과가 크면 30~45일에
   경계를 넘어 조기 판정이 나고, 효과가 작으면 원래 판정일까지 그대로 간다.

   **속도는 효과 크기로 산다** — 이 방법이 없던 우위를 만들어 주지 않는다.

여기 구현한 것(정규혼합 신뢰수열):

    S_t = Σ x_i,  경계 = sqrt( (t + ρ) · σ̂² · ln( (t+ρ)/(ρ·α²) ) )
    |S_t| 가 경계를 넘으면 "0이 아니다"라고 말할 수 있다.

    ρ(rho)는 '어느 표본 크기에서 가장 예민할지'를 정하는 조율값이다. 결과를
    보고 고르면 그 순간 이 보장이 깨지므로 **사전 등록값을 쓴다**(prereg).

⚠️ 짝지어 비교가 전제다. 두 계좌의 **같은 날짜 수익률 차이**를 재면 시장
   등락이 상쇄돼 잡음이 크게 준다 — 같은 기간으로 더 예민하게 볼 수 있다.
   서로 다른 날짜를 섞어 비교하면 이 이점이 사라진다.

정직한 한계:
    · 일수익 차이가 독립·동일분포에 가깝다는 가정이다. 실제 시장은 변동성
      군집이 있어 완전한 가정은 아니다 — 그래서 경계를 넉넉히 잡고(보수적),
      최소 관찰일수 아래에서는 어떤 판정도 내리지 않는다.
    · 조기 판정이 나도 그것은 **실험 계좌 사이의 비교**다. 본 계좌 챔피언
      승격은 별도 관문(오디션·동시검정)이 맡는다.
"""
from __future__ import annotations

import math

MIN_DAYS_DEFAULT = 20        # 이보다 얇으면 어떤 판정도 내리지 않는다
RHO_DEFAULT = 30.0           # 조율값 — 30일 근방에서 가장 예민하게


def paired_daily_returns(a: list[dict], b: list[dict],
                         key: str = "equity") -> list[float]:
    """같은 **날짜**의 일수익 차이(A − B). 짝이 안 맞는 날은 버린다.

    날짜를 맞추지 않고 두 수열을 그냥 빼면 시장 등락이 상쇄되지 않아,
    이 검정이 노리는 잡음 감소가 통째로 사라진다.
    """
    def _series(rows):
        out = {}
        for r in rows or []:
            d, v = r.get("date") or r.get("time"), r.get(key)
            if d is None or v is None:
                continue
            out[str(d)[:10]] = float(v)          # 하루 여러 회차면 마지막 값
        return out

    sa, sb = _series(a), _series(b)
    days = sorted(set(sa) & set(sb))
    diffs = []
    for prev, cur in zip(days, days[1:]):
        if sa[prev] > 0 and sb[prev] > 0:
            diffs.append((sa[cur] / sa[prev] - 1.0) - (sb[cur] / sb[prev] - 1.0))
    return diffs


def boundary(n: int, var: float, alpha: float, rho: float) -> float:
    """정규혼합 경계 — 누적합 |S_t|가 이 값을 넘으면 '0이 아니다'."""
    if n <= 0 or var <= 0:
        return float("inf")
    inner = (n + rho) / (rho * alpha * alpha)
    if inner <= 1.0:
        return float("inf")
    return math.sqrt((n + rho) * var * math.log(inner))


def verdict(diffs: list[float], *, alpha: float = 0.05,
            rho: float = RHO_DEFAULT,
            min_days: int = MIN_DAYS_DEFAULT) -> dict:
    """지금 시점의 판정. **경계를 넘기 전에는 언제나 '진행 중'이다.**

    돌려주는 것: 상태·표본수·누적합·경계·남은 비율(진도).
    """
    n = len(diffs)
    if n < min_days:
        return {"state": "표본 부족", "n": n, "min_days": min_days,
                "reason": f"최소 {min_days}일 관찰 전에는 판정하지 않습니다"}
    mean = sum(diffs) / n
    var = sum((x - mean) ** 2 for x in diffs) / max(1, n - 1)
    s = sum(diffs)
    b = boundary(n, var, alpha, rho)
    if var <= 0:
        return {"state": "진행 중", "n": n, "reason": "차이의 변동이 0 — 판정 불가"}
    state = "진행 중"
    if abs(s) >= b:
        state = "조기 판정: 우세" if s > 0 else "조기 판정: 열세"
    return {"state": state, "n": n, "sum": round(s, 8),
            "boundary": round(b, 8), "mean_daily_pct": round(mean * 100, 5),
            "progress": round(min(1.0, abs(s) / b), 4) if b > 0 else 0.0,
            "alpha": alpha, "rho": rho}


def _load(path: str) -> dict:
    import json
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sequential_status(state_dir: str = "state") -> dict | None:
    """지금 돌고 있는 비교들의 조기 판정 진도 — 사전 등록값으로만 잰다.

    ⚠️ 조율값·유의수준을 여기서 새로 고르지 않는다(prereg에서 읽는다).
       고르는 순간 '언제 봐도 유효'라는 보장이 깨진다.
    ⚠️ 데이터가 얇으면 얇다고 말한다 — 빈칸으로 두면 "그런 일이 없었다"로
       읽힌다(이 저장소가 반복해 지켜 온 구분).
    """
    import os

    from quant.live.prereg import SEQUENTIAL as CFG

    kw = {"alpha": float(CFG["alpha"]), "rho": float(CFG["rho"]),
          "min_days": int(CFG["min_days"])}
    out: dict = {"registered": CFG, "pairs": {}}

    # ① 배분 사다리 — 현행(HRP) 대비 대안 3종
    base = _load(os.path.join(state_dir, "alloc_ladder", "hrp.json"))
    for alt in ("erc", "equal", "inv_vol"):
        other = _load(os.path.join(state_dir, "alloc_ladder", f"{alt}.json"))
        d = paired_daily_returns(base.get("history") or [],
                                 other.get("history") or [])
        if d or (base.get("history") and other.get("history")):
            out["pairs"][f"alloc:hrp-{alt}"] = verdict(d, **kw)

    # ② 주기 사다리 — 본 트랙(1시간) 대비 촘촘한 주기
    ch = _load(os.path.join(state_dir, "intraday", "challenger.json"))
    for tf in ("15m", "5m"):
        tr = _load(os.path.join(state_dir, "intraday", f"track_{tf}.json"))
        d = paired_daily_returns(ch.get("rounds") or [], tr.get("rounds") or [])
        if d or (ch.get("rounds") and tr.get("rounds")):
            out["pairs"][f"cadence:1h-{tf}"] = verdict(d, **kw)

    # ③ 미국 주기 사다리 — 같은 규약
    us = _load(os.path.join(state_dir, "intraday", "us_challenger.json"))
    for tf in ("15m", "5m"):
        tr = _load(os.path.join(state_dir, "intraday", f"us_track_{tf}.json"))
        d = paired_daily_returns(us.get("rounds") or [], tr.get("rounds") or [])
        if d or (us.get("rounds") and tr.get("rounds")):
            out["pairs"][f"us_cadence:1h-{tf}"] = verdict(d, **kw)

    if not out["pairs"]:
        return None
    out["note"] = (
        "경계를 넘으면 그 시점에 조기 판정이 납니다. 넘기 전에는 '진행 중'이며, "
        "진행 중은 '아직 모른다'이지 '차이가 없다'가 아닙니다. 이 경계는 "
        "결과를 보기 전에 등록했고, 매일 들여다봐도 거짓 승리 확률이 5%를 "
        "넘지 않는다는 것을 시뮬레이션 검사로 확인합니다.")
    return out
