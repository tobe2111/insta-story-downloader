"""증명 가능성 계측 — "지금 관문을 넘으려면 무엇이 필요한가" (2026-08-19).

⚠️ 왜 만들었나. 2026-08-19에 20종목 과최적화 검증이 처음으로 완주했다.
   결과는 이랬다:

       실패 6 · 경고 13 · 미측정 1 · **통과 0**

   그리고 DSR(운이 아니라 실력일 확률) 최고값이 0.16(엔비디아)이었다.
   통과선은 0.95다. 즉 **어떤 종목도 만점(비중 ×1.0)에 닿지 못했다.**

   여기서 두 갈래로 읽을 수 있다. "전략이 나쁘다"와 "관문이 지금 표본으로는
   넘을 수 없게 설정돼 있다". 둘은 대응이 정반대라, 추측하지 말고 **역산**했다.

   DSR은 (표본 길이 T, 누적 시행 횟수 N, 실현 샤프) 세 값으로 정해진다.
   앞의 둘은 장부에 있으니, 남은 하나 — "통과하려면 샤프가 얼마여야 하는가"
   — 를 풀 수 있다. 실측(T=800봉 · N=238회):

       필요 연환산 샤프 ≈ **2.5**

   이건 세계 최상위 펀드가 좋은 해에 내는 숫자다. 즉 지금 구조에서 '통과'는
   사실상 도달 불가능한 칸이고, 계좌는 앞으로도 절반 이하 노출로 굴러간다.

   **그렇다고 관문을 낮추지 않는다.** 결과를 보고 기준을 고치는 것이 정확히
   이 제품이 하지 않겠다고 약속한 일(골대 이동)이다. 대신 이 사실을 숫자로
   공개하고, 정공법 — **표본을 늘리는 것** — 이 무엇인지도 같은 자리에서
   보여 준다. 장중 트랙이 존재하는 이유가 바로 이것이다.
"""
from __future__ import annotations

import json
import math
import os
from statistics import NormalDist

from quant.robustness.deflated_sharpe import expected_max_sharpe
from quant.utils.logging import get_logger

log = get_logger("provable")

_ND = NormalDist()
PERIODS_PER_YEAR = 252.0
DSR_PASS = 0.95            # validation_gate 와 같은 선(여기서 바꾸면 안 된다)

# 표본을 늘리는 길들 — 배수는 '하루에 몇 번 판단하는가'다.
# ⚠️ 일봉 전략을 시간봉으로 다시 재서 T를 부풀리는 것은 반칙이다. 여기 배수는
#    **그 주기로 실제 판단하는 다른 계좌**(장중 트랙)를 뜻한다.
PATHS = (("지금 — 하루 1회 판단 · 3년", 1.0),
         ("종목을 묶어 한 모델로(실효 표본 1.78배)", 1.78),
         ("하루 1회 판단 · 6년", 2.0),
         ("1시간마다 판단 · 3년", 6.0),
         ("15분마다 판단 · 3년", 26.0))


def required_sharpe(bars: int, n_trials: int, alpha: float = DSR_PASS) -> float | None:
    """DSR이 alpha에 닿는 **주기 샤프**를 역산한다(왜도 0·첨도 3 가정).

    가정을 둔 이유: 실제 왜도·첨도는 전략마다 다르고 미래 값은 알 수 없다.
    정규 가정은 대개 **낙관적인 쪽**이다 — 실제 수익 분포는 꼬리가 두꺼워
    같은 샤프에서 DSR이 더 낮게 나온다. 즉 여기 나온 값은 하한이다.
    """
    T = int(bars or 0)
    if T < 4:
        return None
    lo, hi = 0.0, 1.0
    for _ in range(200):
        sr = (lo + hi) / 2.0
        den = math.sqrt(max(1e-12, 1.0 + 0.5 * sr * sr))
        std = math.sqrt(max(1e-12, den * den / (T - 1.0)))
        star = expected_max_sharpe(n_trials, std) if n_trials > 1 else 0.0
        if _ND.cdf((sr - star) * math.sqrt(T - 1.0) / den) < alpha:
            lo = sr
        else:
            hi = sr
    return hi


def annualized(periodic_sharpe: float | None,
               periods_per_year: float = PERIODS_PER_YEAR) -> float | None:
    if periodic_sharpe is None:
        return None
    return periodic_sharpe * math.sqrt(periods_per_year)


def _median(xs: list) -> float | None:
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    n = len(xs)
    return float(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def provability(state_dir: str = "state") -> dict | None:
    """"통과선을 넘으려면 무엇이 필요한가"를 장부 실측으로 답한다.

    못 재면 None — 모르는 것을 숫자로 만들지 않는다.
    """
    try:
        vpath = os.path.join(state_dir, "validation.json")
        cpath = os.path.join(state_dir, "champions.json")
        if not os.path.exists(vpath):
            return None
        with open(vpath, encoding="utf-8") as f:
            val = json.load(f)
        if not isinstance(val, dict) or not val:
            return None
        champs = {}
        if os.path.exists(cpath):
            with open(cpath, encoding="utf-8") as f:
                champs = json.load(f) or {}

        bars = _median([v.get("bars") for v in val.values()
                        if isinstance(v, dict)])
        trials = _median([e.get("trials_total") for e in champs.values()
                          if isinstance(e, dict)])
        dsrs = [v.get("dsr") for v in val.values()
                if isinstance(v, dict) and isinstance(v.get("dsr"), (int, float))]
        if bars is None or not dsrs:
            return None
        n_trials = int(trials or 1)
        need = required_sharpe(int(bars), n_trials)
        paths = []
        for label, mult in PATHS:
            r = required_sharpe(int(bars * mult), n_trials)
            paths.append({"label": label, "bars": int(bars * mult),
                          "required_ann_sharpe": (round(annualized(r), 2)
                                                  if r is not None else None)})
        return {
            "asof": max((str(v.get("asof") or "") for v in val.values()
                         if isinstance(v, dict)), default=""),
            "symbols": len(val),
            "bars_median": int(bars),
            "trials_median": n_trials,
            "dsr_pass": DSR_PASS,
            "dsr_best": round(max(dsrs), 4),
            "dsr_median": round(_median(dsrs) or 0.0, 4),
            "passing": sum(1 for x in dsrs if x >= DSR_PASS),
            # 지금 표본에서 '통과'에 닿으려면 필요한 연환산 샤프
            "required_ann_sharpe": (round(annualized(need), 2)
                                    if need is not None else None),
            "paths": paths,
            # ⚠️ 관문을 낮추는 선택지는 여기 없다. 결과를 보고 기준을 고치는
            #    것이 이 제품이 하지 않겠다고 약속한 일이다.
            "note": "관문(0.95)은 결과를 보고 바꾸지 않는다 — 표본을 늘리는 "
                    "것이 정공법이고, 장중 트랙이 그 실험이다.",
        }
    except Exception as exc:  # noqa: BLE001 — 계측 실패가 배치를 막지 않는다
        log.warning("증명 가능성 계측 실패(건너뜀): %s", exc)
        return None
