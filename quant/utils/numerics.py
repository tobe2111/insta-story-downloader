"""수치 퇴화 판정 — '표준편차가 0'을 부동소수로 판별하면 안 된다 (감사 146).

무슨 일이 있었나. 샤프를 계산하는 코드는 전부 이렇게 막고 있었다.

    sd = r.std(ddof=1)
    if sd <= 0:          # 또는  if sd > 0:  /  .replace(0.0, np.nan)
        ...

그런데 **값이 전부 같아도 표준편차가 정확히 0이 아니다.**

    np.full(100, 0.001).std(ddof=1)  ==  2.18e-19     (0이 아니다!)

그래서 가드가 통과되고,

    샤프 = 0.001 / 2.18e-19 = 4.59e15
    DSR  = 1.0                          ← "확실한 실력"

매 봉 똑같이 오르는 계열(관망 중 고정 비용, 거래정지된 시세, 아주 짧은
검증 구간에서 우연히 같은 값이 나온 경우)이 **검증 3종을 만점으로 통과**한다.
그리고 그 판정이 엣지 입증 게이트를 풀어 목표 변동성을 12%→20%로 올린다.

0과의 비교는 부동소수에서 거의 언제나 틀린다. **크기에 견주어** 봐야 한다.
"""
from __future__ import annotations

import math

# 상대 오차 기준. 수익률의 크기 대비 이보다 작은 분산은 '없는 것'으로 본다.
# 실제 계열의 표준편차는 평균의 최소 수 배수 이상이므로 안전한 여유가 있다
# (일별 수익 평균 0.1% · 표준편차 1% → 비율 10, 문턱 1e-12와 12자리 차이).
REL_EPS = 1e-12


def degenerate_spread(sd: float, scale: float) -> bool:
    """이 표준편차를 샤프의 분모로 써도 되는가 — 안 되면 True.

    scale: 그 계열의 크기(보통 |평균| 또는 평균 절대값). 크기를 모르면
           1.0을 넘겨 절대 기준으로 판정한다.
    """
    try:
        sd = float(sd)
        scale = abs(float(scale))
    except (TypeError, ValueError):
        return True
    if not math.isfinite(sd) or sd <= 0.0:
        return True
    return sd <= REL_EPS * max(scale, 1e-300)


def safe_sharpe(mean: float, sd: float, scale: float | None = None) -> float:
    """퇴화한 계열이면 0.0, 아니면 mean/sd.

    '모르면 숫자를 만들지 않는다' — 분산이 없는 계열의 샤프는 무한대가
    아니라 **판정 불가**다. 0은 '나쁘다'가 아니라 '근거 없음'을 뜻한다.
    """
    if degenerate_spread(sd, abs(mean) if scale is None else scale):
        return 0.0
    return float(mean) / float(sd)
