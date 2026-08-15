"""확률 보정 개입 준비 — '보정 어긋남'이 통계로 확정된 확률대만 경험 보정한다.

배경: 사이트는 확률대별 실제 적중률과 윌슨 95% 신뢰구간을 보여주고, 표본
30건 이상인데 예측 확률이 신뢰구간 밖이면 '⚠️ 보정 어긋남'을 띄운다(관찰).
이 모듈은 그 다음 단계다 — 장부의 (새벽 예측확률, 다음 날 실제 방향) 짝으로
확률대별 경험 보정표를 만들고, 어긋남이 '확정된' 확률대에 한해 보정된 확률을
계산한다.

⚠️ 원칙: 이 보정은 매매(사이징)에 개입하지 않는다 — 기록·표시 전용이다.
   장부에 prob_up_cal로 병기되어 "모델은 65%라지만 경험상 52%"를 사이트가
   보여줄 수 있게 한다. 사이징 개입은 사장님 승인 후 별도로 켠다(보정은
   엣지를 만들지 않는다 — 과대확신의 복리 손실을 줄일 뿐이다).

판정 규칙(사이트 플래그와 동일 정신, 구간만 고정 빈으로):
   확률을 폭 0.10의 고정 구간([0.5,0.6) 등)으로 나누고, 구간 표본이
   MIN_INTERVENE_SAMPLES 이상이면서 평균 예측확률이 실제 적중률의 윌슨
   95% 신뢰구간 밖이면 '어긋남 확정' — 그 구간의 보정값은 실제 적중률이다.
"""
from __future__ import annotations

import math

from quant.live.explain import _wilson_ci

# 개입(보정값 병기)을 확정하는 최소 표본 — 관찰 플래그(사이트)와 같은 30건.
# 25건(표시 최소)보다 높게 잡는 이유: 표시는 참고지만 보정값은 '모델이
# 틀렸다'는 주장이라 더 강한 증거를 요구한다.
MIN_INTERVENE_SAMPLES = 30
BIN_WIDTH = 0.10


def _bin_of(prob: float, bins: int) -> int:
    """확률이 몇 번째 구간에 드는가 — **표를 만들 때와 적용할 때가 같아야 한다.**

    ⚠️ 감사 150 이전에는 두 곳이 달랐다. 표는 `min(int(p*bins), bins-1)`로
       p=1.0을 마지막 구간에 넣어 **증거로 세었는데**, 적용은
       `lo <= p < hi`라 p=1.0이 **어느 구간에도 안 걸렸다.**

           예측 0.97 · 실제 적중률 0.50 · 표본 80 → 어긋남 확정
           prob 0.970 → 보정 0.50 (개입)
           prob 0.999 → 보정 0.50 (개입)
           prob 1.000 → 보정 1.00 (개입 없음)   ← 가장 과신한 값만 빠져나간다

       "100% 오른다"는 모델의 말이 경험 보정을 통째로 피해 간다. 하필 가장
       위험한 값이다. 판정을 한 함수로 모아 두 곳이 갈라질 수 없게 한다.

    범위 밖(음수·1 초과)은 양 끝 구간으로 잡는다 — 모르는 값을 만들지 않는다.
    """
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(p):
        return 0
    return max(0, min(int(p * bins), bins - 1))


def collect_pairs(histories: list, holidays: dict | None = None) -> list:
    """장부 목록에서 (예측확률, **다음 세션** 상승 여부) 짝을 전부 모은다.

    짝짓기 규칙은 해설(`_band_pairs`)과 **같은 함수**를 쓴다 —
    `ledger_basics.next_session_pairs`. 규칙이 같아야 사이트 플래그와 이
    보정이 같은 데이터로 같은 결론을 낸다.

    ⚠️ 예전에는 두 곳이 각자 `zip(history, history[1:])`를 적고 있었다
       (감사 247). 규칙이 같다고 **주석에 적혀만** 있었고, 둘 다 기록이
       하루 빠진 구간에서 이틀치 움직임을 하루 예측의 성적으로 세고 있었다.
       이 함수의 결과는 화면에 **표시되는 확률 자체를 바꾼다**(prob_up_cal).

    histories는 `(시장, 장부)` 짝의 목록이다 — 시장을 모르면 세션 판정을
    할 수 없다. 옛 형태(장부만의 목록)도 받는다(그때는 안 거른다).
    """
    from quant.live.ledger_basics import next_session_pairs

    pairs = []
    for item in histories or []:
        market, history = item if isinstance(item, tuple) else (None, item)
        rows, _dropped = next_session_pairs(history, market, holidays)
        for a, b in rows:
            p = a.get("prob_up")
            pa, pb = a.get("price"), b.get("price")
            if p is None or pa in (None, 0) or pb is None:
                continue
            pairs.append((float(p), 1.0 if float(pb) > float(pa) else 0.0))
    return pairs


def calibration_table(histories: list, bin_width: float = BIN_WIDTH,
                      min_n: int = MIN_INTERVENE_SAMPLES,
                      holidays: dict | None = None) -> list[dict]:
    """확률대별 보정표 — 구간마다 표본·예측평균·실제비율·CI·확정 여부.

    반환: [{"lo", "hi", "n", "pred_mean", "actual", "ci_lo", "ci_hi",
            "confirmed"}] (표본 있는 구간만). confirmed는 n≥min_n이면서
    pred_mean이 [ci_lo, ci_hi] 밖일 때만 True.
    """
    pairs = collect_pairs(histories, holidays)
    bins = max(1, round(1.0 / bin_width))
    sums = [[0.0, 0.0, 0] for _ in range(bins)]      # [예측합, 상승합, 수]
    for p, hit in pairs:
        k = _bin_of(p, bins)
        sums[k][0] += p
        sums[k][1] += hit
        sums[k][2] += 1
    out = []
    for k, (ps, hs, n) in enumerate(sums):
        if n == 0:
            continue
        pred, actual = ps / n, hs / n
        lo, hi = _wilson_ci(actual, n)
        out.append({
            "lo": k / bins, "hi": (k + 1) / bins, "n": n,
            "pred_mean": round(pred, 4), "actual": round(actual, 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
            "confirmed": bool(n >= min_n and not (lo <= pred <= hi)),
        })
    return out


def recalibrated_prob(prob: float | None, histories: list,
                      table: list[dict] | None = None,
                      holidays: dict | None = None) -> tuple[float | None, bool]:
    """오늘 확률의 경험 보정값을 계산한다 — (보정 확률, 개입 여부).

    확률이 '어긋남 확정' 구간에 들면 그 구간의 실제 적중률을 반환하고
    active=True. 아니면 원래 확률 그대로 active=False — 증거가 없는 곳에서는
    모델의 말을 그대로 둔다.
    """
    if prob is None:
        return None, False
    if table is None:
        table = calibration_table(histories, holidays=holidays)
    p = float(prob)
    if not math.isfinite(p):
        return prob, False
    bins = max(1, round(1.0 / BIN_WIDTH))
    k = _bin_of(p, bins)                    # 표와 **같은** 구간 판정(감사 150)
    for row in table:
        if row["confirmed"] and _bin_of(row["lo"], bins) == k:
            return row["actual"], True
    return p, False
