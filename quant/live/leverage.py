"""배율을 사람이 아니라 **기록이** 정한다.

사장님 지시(2026-08-25): *"그 조정은 그냥 수익률과 성공률이 높게만 나오면
되는거야. 실시간으로 조정은 이 프로그램 자체에서 머신러닝에서 할 일이고."*

맞는 지적이었다. 배율 상한을 3으로 할지 2로 할지 사람이 매번 정하는 것은
근거 없는 손질이고, 그 손질이 쌓이면 "그때그때 좋아 보이는 값"을 고른
장부가 된다 — 이 저장소가 가장 경계하는 사후 선택이다.

■ 그런데 "수익률이 높게 나온 배율"을 고르면 안 된다

이 구별이 이 파일의 전부다.

지난 기록에서 **가장 많이 번 배율**을 고르는 것은 학습이 아니라 과최적화다.
같은 잡음을 두 번 믿는 것이고, 하필 그 잡음에 배율까지 얹는다. 2026-08-24
실측: 이 시스템의 실전 적중률은 45.8%(95% 구간 36.7~55.2%)로 **우연과
구별되지 않는다.** 그 상태에서 "수익률 최대"를 좇으면 동전 던지기에
3배를 태우게 된다 — 계좌가 사라지는 가장 흔한 방식이다.

그래서 여기서는 두 가지를 지킨다:

  ① **위험 대비**로 잰다. 같은 수익이라도 요동이 크면 배율을 안 준다.
  ② **우연을 배제한 뒤에만** 올린다. 평균 수익률의 95% 신뢰구간 하한이
     0을 넘어야 한다 — 점추정이 양수라는 이유로 올리면, 우리가 그토록
     걸러낸 '운 좋은 승자'가 우리 자신이 된다.

이건 본 계좌가 목표 변동성을 올릴 때 쓰는 규율(quant/risk/portfolio_vol.py
의 `edge_proven`)과 같은 생각이다. 새로 발명하지 않고 같은 잣대를 쓴다.

■ 내릴 때는 즉시, 올릴 때는 천천히

비대칭이 핵심이다. 낙폭이 깊어지면 **그 자리에서** 1배로 내려온다.
올리는 데는 표본이 쌓여야 한다. 반대로 만들면(빨리 올리고 늦게 내리고)
한 번의 폭락으로 끝난다.

■ 이건 더 버는 장치가 아니다

배율은 결과를 **크게** 만드는 장치다 — 좋은 쪽으로도, 나쁜 쪽으로도.
증거가 없으면 1배이고, 1배는 실패가 아니라 "아직 걸 이유가 없다"는
정직한 답이다.
"""
from __future__ import annotations

import math

# 배율을 논하기 전에 필요한 최소 회차. 이보다 얇으면 무조건 1배다.
MIN_ROUNDS = 120

# 낙폭이 이보다 깊으면 즉시 1배 — 회복될 때까지 크게 걸지 않는다.
DRAWDOWN_STOP = 0.10

# 신뢰구간 z (95%).
Z = 1.96

# 회차 수익률의 요동이 이보다 작으면 **위험을 잰 것이 아니다.**
#
# ⚠️ 왜 0이 아니라 크기를 정했나(감사 209와 같은 실수를 피하려고). 처음에는
#    `std <= 0`으로 막았는데, 완벽히 일정하게 오르는 곡선의 표준편차는
#    정확히 0이 아니라 **1e-16쯤**(부동소수 잡음)이다. 그러면
#
#        비율 = 평균 / 요동 = 29,765,668,388,892
#
#    이 되어 '완벽한 전략'이 상한을 통째로 가져간다. 합성 데이터·멈춘 시세·
#    검사용 곡선이 정확히 이 모양이고, 하필 그때 최대 배율이 나간다.
#
#    진짜 시장은 이렇게 움직이지 않는다 — 이 트랙의 실측 요동은 0.44%다.
#    0.0001%(1e-6) 아래는 시장이 아니라 고장이거나 가짜다.
MIN_STD = 1e-6


def round_returns(curve: list) -> list:
    """자산 곡선 → 회차별 수익률. 못 읽는 점은 조용히 건너뛴다."""
    vals = []
    for p in (curve or []):
        v = None
        if isinstance(p, dict):
            v = p.get("equity")
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            v = p[1]
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v > 0:
            vals.append(v)
    return [vals[i] / vals[i - 1] - 1.0 for i in range(1, len(vals))]


def drawdown(curve: list) -> float:
    """지금까지의 고점 대비 낙폭(양수). 못 재면 0.0."""
    peak = 0.0
    dd = 0.0
    for p in (curve or []):
        v = p.get("equity") if isinstance(p, dict) else (
            p[1] if isinstance(p, (list, tuple)) and len(p) >= 2 else None)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak)
    return dd


def evidence(curve: list) -> dict:
    """이 트랙이 스스로 증명한 것 — 위험 대비 성과와 그 신뢰구간.

    돌려주는 ``proven``은 **평균 회차 수익률의 95% 하한이 0을 넘을 때만**
    True다. 평균이 양수라는 것만으로는 아무것도 증명되지 않는다.
    """
    r = round_returns(curve)
    n = len(r)
    if n < 2:
        return {"n": n, "mean": None, "std": None, "lo": None,
                "proven": False, "why": "표본이 없다"}
    mean = sum(r) / n
    var = sum((x - mean) ** 2 for x in r) / (n - 1)
    std = math.sqrt(max(0.0, var))
    if std < MIN_STD:
        # 요동이 없으면 위험 대비를 잴 수 없다. 잴 수 없으면 안 올린다.
        return {"n": n, "mean": mean, "std": std, "lo": None,
                "proven": False,
                "why": "요동이 사실상 없다 — 위험 대비를 잴 수 없다"}
    se = std / math.sqrt(n)
    lo = mean - Z * se                  # 평균 수익률의 95% 하한
    return {
        "n": n, "mean": mean, "std": std, "lo": lo,
        # 위험 대비 성과(회차 단위 샤프 비슷한 값) — 표시·배율 산정용.
        "ratio": mean / std,
        "proven": bool(n >= MIN_ROUNDS and lo > 0.0),
        "why": ("" if n >= MIN_ROUNDS and lo > 0.0 else
                (f"표본 {n}회차 < {MIN_ROUNDS}" if n < MIN_ROUNDS else
                 "평균 수익률의 95% 하한이 0 이하 — 우연과 구별되지 않는다")),
    }


def adaptive_max_leverage(curve: list, *, hard_cap: float,
                          drawdown_stop: float = DRAWDOWN_STOP) -> dict:
    """지금 이 트랙이 **허락받은** 배율 상한과 그 이유.

    ⚠️ 여기서 정하는 것은 **상한**이지 실제 배율이 아니다. 실제 배율은
       여전히 신호의 확신에 비례한다 — 확신 없는 날은 상한이 3이어도 1배다.

    규칙:
      · 기본은 1.0 — 증명 전에는 안 올린다.
      · 낙폭이 기준보다 깊으면 **즉시** 1.0. 회복까지 크게 걸지 않는다.
      · 증명됐으면 위험 대비 성과에 비례해 상한까지 올린다. 다만 한 번에
        상한으로 뛰지 않는다 — 비율이 좋을수록 천천히 다가간다.
    """
    try:
        cap = float(hard_cap)
    except (TypeError, ValueError):
        return {"max_leverage": 1.0, "why": "상한 설정을 읽을 수 없다",
                "proven": False}
    if not (cap > 1.0):
        return {"max_leverage": 1.0, "why": "상한이 1배 이하 — 배율 없음",
                "proven": False}
    dd = drawdown(curve)
    if dd >= float(drawdown_stop):
        # ⚠️ 내리는 것은 증거를 기다리지 않는다. 기다리면 늦는다.
        return {"max_leverage": 1.0, "proven": False, "drawdown": round(dd, 4),
                "why": (f"낙폭 {dd * 100:.1f}% — 기준 "
                        f"{float(drawdown_stop) * 100:.0f}%를 넘어 1배로 "
                        "내렸습니다. 회복될 때까지 크게 걸지 않습니다")}
    ev = evidence(curve)
    if not ev["proven"]:
        return {"max_leverage": 1.0, "proven": False, "drawdown": round(dd, 4),
                "n": ev["n"], "why": ev["why"] + " — 1배로 둡니다"}
    # 증명됐다. 위험 대비 성과가 좋을수록 상한에 가까워진다.
    # 회차 단위 비율 0.05(꽤 좋은 값)에서 상한에 닿게 눈금을 잡는다 —
    # 눈금을 모델이 절대 못 가는 자리에 두면 장치가 안 켜진다(감사 310).
    reach = max(0.0, min(1.0, float(ev["ratio"]) / 0.05))
    lev = 1.0 + (cap - 1.0) * reach
    return {"max_leverage": round(lev, 4), "proven": True,
            "drawdown": round(dd, 4), "n": ev["n"],
            "ratio": round(float(ev["ratio"]), 6),
            "why": (f"표본 {ev['n']}회차 · 평균 수익률의 95% 하한이 0을 "
                    f"넘었습니다 · 위험 대비 {ev['ratio']:.4f} → 상한 "
                    f"{lev:.2f}배")}
