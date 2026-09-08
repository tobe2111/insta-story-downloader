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
import re

MIN_DAYS_DEFAULT = 20        # 이보다 얇으면 어떤 판정도 내리지 않는다
RHO_DEFAULT = 30.0           # 조율값 — 30일 근방에서 가장 예민하게


def paired_daily_returns(a: list[dict], b: list[dict],
                         key: str = "equity") -> list[float]:
    """같은 **날짜**의 일수익 차이(A − B). 짝이 안 맞는 날은 버린다.

    날짜를 맞추지 않고 두 수열을 그냥 빼면 시장 등락이 상쇄되지 않아,
    이 검정이 노리는 잡음 감소가 통째로 사라진다.
    """
    def _series(rows):
        # ⚠️ **쓴 순서와 봉 순서가 갈릴 수 있다**(2026-09-07 실측). 그림자 실험
        #    장부에는 한때 본 계좌와 섀도 대조군 두 계좌가 함께 썼고, 대조군의
        #    줄은 **더 과거 날짜인데 뒤에 적혔다**. 그대로 "마지막 값"을 쓰면
        #    그 날짜의 자산이 **다른 계좌의 값**이 되고, 앞뒤 날과 이어 붙인
        #    일수익은 두 계좌의 자산을 엮은 **지어낸 수익률**이 된다.
        #    실측: 배분 사다리 짝비교 16개 관측 중 **2개**가 그랬다(최대 8.3bp).
        #
        #    그래서 **뒤로 간 줄은 건너뛴다.** 같은 날짜의 여러 회차(장중
        #    트랙)는 그대로 마지막 값을 쓴다 — 그건 정상이고, 뒤로 간 것만
        #    사고다. 이 구별이 없으면 장중 트랙의 하루 여러 회차가 통째로
        #    날아간다.
        out, high = {}, None
        for r in rows or []:
            d, v = r.get("date") or r.get("time"), r.get(key)
            if d is None or v is None:
                continue
            day = str(d)[:10]
            if high is not None and day < high:
                continue                          # 뒤로 간 줄 — 다른 계좌의 것
            # 여기 닿았다는 것은 day >= high 라는 뜻이라 그냥 올린다.
            # ⚠️ 부등호가 `<=`가 되면 **같은 날의 뒤 회차가 통째로 버려진다** —
            #    장중 트랙은 하루에 수십 번 돈다.
            high = day
            out[day] = float(v)                   # 하루 여러 회차면 마지막 값
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


# ── 등록이 정한 것을 **등록에서 읽는다** ──────────────────────────
#
# ⚠️ 2026-09-07에 여기가 세 군데 갈라져 있었다(실측):
#
#   ① 등록은 배분 사다리·주기 사다리에 **본페로니 3**을 선언했는데,
#      경계는 α=0.05 **그대로** 쓰고 있었다. 보정이 빠지면 경계가 낮아져
#      **거짓 승리 쪽으로** 느슨해진다 — 조기 판정이 존재하는 이유가
#      "훔쳐봐도 5%를 안 넘는다"인데 그 약속이 지켜지지 않고 있었다.
#   ② ``SEQUENTIAL["applies_to"]``의 6개 중 **4개**(지정가 그림자 둘 ·
#      2세대 집중 · 사이징 사다리)는 **한 번도 계산된 적이 없었다.**
#      그중 2세대 집중은 등록 문구가 "조기 판정 경계 적용"이라고 직접
#      적고 있다. 주기 사다리도 등록된 3쌍 중 2쌍만 돌았다(15m-5m 누락).
#   ③ 반대로 미국 주기 사다리는 **등록에 없는데** 돌고 있었다. 등록은
#      그것을 "참고 진단"이라 부른다 — 등록된 판정과 같은 칸에 두면
#      읽는 사람이 구별할 수 없다.
#
# 그래서 유의수준을 손으로 적지 않는다. **등록 문구에서 센다** — 문구와
# 코드가 갈리면 그건 정의상 골대 이동이다.

_BONFERRONI = re.compile(r"본페로니\s*(\d+)")


def registered_comparisons(exp: dict) -> int:
    """이 실험이 등록한 **동시 비교 수**. 손 목록이 아니라 등록 문구에서."""
    text = str((exp or {}).get("correction") or "")
    if "보정 없음" in text:
        return 1
    m = _BONFERRONI.search(text)
    if m:
        return max(1, int(m.group(1)))
    raise ValueError(f"등록의 보정 문구를 못 읽었다: {text!r}")


def _shadow_rows(rounds: list[dict]) -> list[dict]:
    """지정가 그림자의 자산 계열 — 본 트랙과 **같은 회차 기록 안**에 산다.

    그림자는 활성화 순간 본 계좌를 복제하므로, 겹치는 회차만 맞대면
    차이는 순수하게 체결 방식의 효과다(등록: "두 계좌 자산 차이").
    """
    out = []
    for r in rounds or []:
        sh = r.get("limit_shadow") or {}
        if isinstance(sh, dict) and sh.get("equity") is not None:
            out.append({"time": r.get("time"), "equity": sh["equity"]})
    return out


def _pair(name: str, a: list[dict], b: list[dict]) -> dict:
    """장부가 **양쪽 다 있을 때만** 비교를 연다.

    ⚠️ 이 가드가 없으면 ``missing``이 영영 안 채워진다 — 장부가 없어도
       빈 목록으로 짝이 만들어져 '표본 부족'으로 보이기 때문이다.
       "아직 얇다"와 "장부 자체가 없다"는 다른 사건이고, 뒤의 것이
       **아무 말 없이 사라지는 것**이 이 파일이 오늘 고친 병 그 자체다.
       (2026-09-07: 이 구멍을 내가 새로 만들었고 변이 시험이 잡았다.)
    """
    d = paired_daily_returns(a, b)
    return {name: d} if (d or (a and b)) else {}


def _pairs_for(key: str, state_dir: str) -> dict[str, list[float]]:
    """한 등록 실험이 맞대는 장부 쌍들 — 이름 → 일수익 차이.

    ⚠️ 재료가 없으면 **빈 dict**를 돌려준다. 부르는 쪽이 "못 잤다"고
       적는다 — 조용히 빠지면 "그런 비교가 원래 없었다"로 읽힌다.
    """
    import os

    j = lambda *p: os.path.join(state_dir, *p)          # noqa: E731

    if key == "alloc_ladder":
        base = _load(j("alloc_ladder", "hrp.json")).get("history") or []
        out: dict = {}
        for alt in ("erc", "equal", "inv_vol"):
            out |= _pair(f"alloc:hrp-{alt}", base,
                         _load(j("alloc_ladder", f"{alt}.json")).get("history") or [])
        return out

    if key == "sizing_ladder":
        base = _load(j("sizing_ladder", "current.json")).get("history") or []
        out = {}
        for alt in ("half", "kelly", "allin"):
            out |= _pair(f"sizing:current-{alt}", base,
                         _load(j("sizing_ladder", f"{alt}.json")).get("history") or [])
        return out

    if key == "cadence_ladder":
        # ⚠️ 등록은 **3쌍**이다(1h-15m · 1h-5m · **15m-5m**). 셋째가 빠져
        #    있었는데 보정은 3으로 선언돼 있었다 — 재지도 않는 비교의 값을
        #    치르면서 정작 그 비교는 없는 상태였다.
        one = _load(j("intraday", "challenger.json")).get("rounds") or []
        m15 = _load(j("intraday", "track_15m.json")).get("rounds") or []
        m5 = _load(j("intraday", "track_5m.json")).get("rounds") or []
        return (_pair("cadence:1h-15m", one, m15)
                | _pair("cadence:1h-5m", one, m5)
                | _pair("cadence:15m-5m", m15, m5))

    if key in ("limit_shadow", "us_limit_shadow"):
        name = "challenger.json" if key == "limit_shadow" else "us_challenger.json"
        rounds = _load(j("intraday", name)).get("rounds") or []
        return _pair(f"{key}:market-limit", rounds, _shadow_rows(rounds))

    if key == "gen2_concentration":
        # 등록: "본 계좌 대비 일수익 차이 · 조기 판정 경계 적용".
        # ⚠️ 본 계좌에 입금이 있으면 그날 수익률이 가짜로 뛴다 — 입금이
        #    있는 장부로는 재지 않는다(감사 211에서 배운 자리).
        main = _load(j("paper", "portfolio_ALL.json"))
        if main.get("deposits"):
            return {}
        return _pair("gen2:main-concentrated",
                     _load(j("gen2.json")).get("history") or [],
                     main.get("history") or [])

    return {}


def _max_drawdown_pct(rows: list[dict], days: set | None = None) -> float:
    """자산 곡선에서 직접 센 **최대낙폭**(음수 %).

    ⚠️ 장부의 ``drawdown_pct``·``mdd_pct``는 **그날의 낙폭**이지 최대낙폭이
       아니다(2026-09-07 실측: 본 계좌 계열이 0 → −0.53 → −0.28로 오르내린다).
       등록이 말하는 것은 최대낙폭이므로 그 값을 그대로 쓰면 안 된다.
    """
    from quant.live.ledger_basics import max_drawdown_from_index

    eqs = []
    for r in rows or []:
        day = str(r.get("date") or r.get("time") or "")[:10]
        if days is not None and day not in days:
            continue
        try:
            eqs.append(float(r.get("equity")))
        except (TypeError, ValueError):
            continue
    if not eqs or eqs[0] <= 0:
        return 0.0
    # 공용 헬퍼는 **성장 지수**(1.0에서 출발)를 받는다. 그림자 계좌는 입금이
    # 없으므로 창 첫 값으로 나누면 그대로 지수가 된다.
    # ⚠️ 낙폭 식을 손으로 다시 쓰면 안 된다 — 감사 197이 그 계산을 한 곳으로
    #    모은 이유이고, 검사가 직접 잡는다. 실제로 여기서 한 번 잡혔다
    #    (2026-09-08 CI). 검사는 **주석의 예시 문구까지** 잡으므로 그 식을
    #    글자로 적어 두지도 않는다.
    return max_drawdown_from_index([e / eqs[0] for e in eqs]) * 100.0


def _mdd_hold(rule: str, cand: list[dict], base: list[dict]) -> dict:
    """낙폭 배수 조항 — **겹치는 날만** 놓고 잰다.

    기간이 다르면 낙폭 비교가 곧 '누가 더 오래 굴렀나' 비교가 된다.
    """
    days = ({str(r.get("date") or r.get("time") or "")[:10] for r in cand or []}
            & {str(r.get("date") or r.get("time") or "")[:10] for r in base or []})
    if not days:
        return {"rule": rule, "measured": None,
                "why": "겹치는 날이 없어 낙폭을 맞대지 못합니다"}
    c = abs(_max_drawdown_pct(cand, days))
    b = abs(_max_drawdown_pct(base, days))
    if b <= 0:
        return {"rule": rule, "mdd_pct": round(c, 3), "base_mdd_pct": 0.0,
                "measured": None, "days": len(days),
                "why": "현행의 최대낙폭이 0이라 배수를 못 잽니다"}
    return {"rule": rule, "mdd_pct": round(c, 3), "base_mdd_pct": round(b, 3),
            "ratio": round(c / b, 2), "days": len(days), "held": c > b * 1.5}


def _adoption_hold(key: str, state_dir: str) -> dict | None:
    """등록이 **미리 심어 둔 채택 보류 조건** — 이겼다고 곧 채택이 아니다.

    등록 원문이 직접 적어 둔 조건이다(예: *"지정가가 이겨도 미체결율 20%
    초과면 채택 보류 — 체결 안 되는 이득은 이득이 아닙니다"*). 판정만
    싣고 이 조건을 안 실으면, 화면의 '우세'가 곧 채택으로 읽힌다.

    ⚠️ 못 재는 조건은 **못 잰다고 적는다.** 조용히 빼면 "조건이 없었다"와
       구별되지 않는다 — 이 저장소가 반복해 지켜 온 구분이다.
    """
    import os

    if key in ("limit_shadow", "us_limit_shadow"):
        name = "challenger.json" if key == "limit_shadow" else "us_challenger.json"
        sh = (_load(os.path.join(state_dir, "intraday", name))
              .get("limit_shadow") or {})
        f = int(sh.get("filled_total") or 0)
        u = int(sh.get("unfilled_total") or 0)
        rule = "미체결율 20% 초과면 채택 보류 — 체결 안 되는 이득은 이득이 아닙니다"
        if f + u == 0:
            return {"rule": rule, "measured": None,
                    "why": "아직 주문이 없어 미체결율을 못 잽니다"}
        pct = round(u / (f + u) * 100, 1)
        return {"rule": rule, "unfilled_pct": pct, "filled": f, "unfilled": u,
                "held": pct > 20.0}

    if key == "gen2_concentration":
        return _mdd_hold(
            "최대낙폭이 본 계좌의 1.5배를 넘으면 채택 보류 — 수익이 위험을 "
            "사서 온 것이면 승리가 아닙니다",
            (_load(os.path.join(state_dir, "gen2.json")).get("history") or []),
            (_load(os.path.join(state_dir, "paper", "portfolio_ALL.json"))
             .get("history") or []))

    if key == "sizing_ladder":
        # ⚠️ 이 장부에는 낙폭 **칸**이 없다. 그렇다고 못 재는 것이 아니다 —
        #    자산 곡선이 있으므로 거기서 직접 센다. 칸이 없다는 이유로
        #    "못 잽니다"라고 적을 뻔했다(2026-09-07).
        base = _load(os.path.join(state_dir, "sizing_ladder", "current.json"))
        worst, name = None, None
        for alt in ("half", "kelly", "allin"):
            h = _mdd_hold("이겨도 최대낙폭이 현행의 1.5배를 넘으면 채택 보류",
                          (_load(os.path.join(state_dir, "sizing_ladder",
                                              f"{alt}.json")).get("history") or []),
                          base.get("history") or [])
            if h and h.get("ratio") is not None and (
                    worst is None or h["ratio"] > worst["ratio"]):
                worst, name = h, alt
        if worst is None:
            return {"rule": "이겨도 최대낙폭이 현행의 1.5배를 넘으면 채택 보류",
                    "measured": None,
                    "why": "현행 곡선의 낙폭이 0이라 배수를 못 잽니다"}
        return {**worst, "worst_track": name}

    return None


#: 등록에는 없지만 나란히 재는 참고 진단 — **판정이 아니다.**
#: 등록(intraday_us)이 스스로 "주기 사다리는 참고 진단"이라고 적어 두었다.
#: 그래도 경계는 형제(주기 사다리)와 **같은 보정**으로 잡는다 — 참고라고
#: 해서 더 느슨한 자를 쓰면 그 숫자가 더 자주 '이겼다'고 말한다.
_REFERENCE = {"us_cadence": ("cadence_ladder", "intraday")}


def sequential_status(state_dir: str = "state") -> dict | None:
    """지금 돌고 있는 비교들의 조기 판정 진도 — 사전 등록값으로만 잰다.

    ⚠️ 조율값·유의수준을 여기서 새로 고르지 않는다(prereg에서 읽는다).
       고르는 순간 '언제 봐도 유효'라는 보장이 깨진다.
    ⚠️ 데이터가 얇으면 얇다고 말한다 — 빈칸으로 두면 "그런 일이 없었다"로
       읽힌다(이 저장소가 반복해 지켜 온 구분).
    ⚠️ 등록된 실험은 **빠짐없이** 여기를 지난다. 재료가 없으면 ``missing``
       에 적는다 — 목록을 손으로 유지하면 잊는다(2026-09-07 실측: 6개 중
       4개가 아무 말 없이 빠져 있었다).
    """
    import os

    from quant.live.prereg import PREREGISTERED, SEQUENTIAL as CFG

    alpha0, rho = float(CFG["alpha"]), float(CFG["rho"])
    min_days = int(CFG["min_days"])
    out: dict = {"registered": CFG, "pairs": {}, "missing": {}}

    for key in CFG["applies_to"]:
        exp = PREREGISTERED.get(key) or {}
        m = registered_comparisons(exp)
        pairs = _pairs_for(key, state_dir)
        if not pairs:
            out["missing"][key] = "재료 없음 — 이 실험의 장부를 아직 못 읽었습니다"
            continue
        hold = _adoption_hold(key, state_dir)
        for name, diffs in pairs.items():
            v = verdict(diffs, alpha=alpha0 / m, rho=rho, min_days=min_days)
            v["experiment"] = key
            v["comparisons"] = m
            if hold:
                v["adoption_hold"] = hold
            out["pairs"][name] = v

    # 참고 진단 — 등록된 판정과 **같은 칸에 두되 이름표를 단다**.
    us = _load(os.path.join(state_dir, "intraday", "us_challenger.json"))
    ref_m = registered_comparisons(PREREGISTERED.get("cadence_ladder") or {})
    for tf in ("15m", "5m"):
        tr = _load(os.path.join(state_dir, "intraday", f"us_track_{tf}.json"))
        d = paired_daily_returns(us.get("rounds") or [], tr.get("rounds") or [])
        if d or (us.get("rounds") and tr.get("rounds")):
            v = verdict(d, alpha=alpha0 / ref_m, rho=rho, min_days=min_days)
            v.update({"experiment": "intraday_us", "comparisons": ref_m,
                      "reference": True,
                      "why": "등록된 조기 판정이 아니라 참고 진단입니다"})
            out["pairs"][f"us_cadence:1h-{tf}"] = v

    if not out["pairs"] and not out["missing"]:
        return None
    out["note"] = (
        "경계를 넘으면 그 시점에 조기 판정이 납니다. 넘기 전에는 '진행 중'이며, "
        "진행 중은 '아직 모른다'이지 '차이가 없다'가 아닙니다. 이 경계는 "
        "결과를 보기 전에 등록했고, 매일 들여다봐도 거짓 승리 확률이 5%를 "
        "넘지 않는다는 것을 시뮬레이션 검사로 확인합니다. 한 실험이 여러 쌍을 "
        "재면 등록된 본페로니 보정만큼 경계가 올라갑니다.")
    return out
