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

# ── 문턱 두 개, 질문 두 개 (감사 159) ──────────────────────────
#
# 처음엔 상수 하나로 두 가지를 재고 있었는데 그게 틀렸다.
#
#   ① "이 분산은 부동소수 잡음인가"        — 패널 안 최대 분산 대비 비교
#   ② "이 계열에 쓸 만한 분산이 있는가"    — 그 계열의 크기 대비 비교
#
# ①은 아주 엄격해야 한다. 진짜로 조용한 자산(저유동 ETF)을 잡음으로 몰면
# 배분에서 통째로 지워지고, 그건 가드가 덫이 되는 것이다(FROZEN_IDEAS ④).
#
# ②는 훨씬 느슨해야 한다. 표준편차가 평균의 100만분의 1인 계열은 잡음이든
# 아니든 **샤프를 말할 수 없다.** 실측으로 매일 정확히 +0.005%씩 오르는
# 계열(예금형 ETF·MMF)의 std/평균 비율이 2.3e-12였는데, ①의 문턱(1e-12)으로는
# 간발의 차로 통과해 몬테카를로 샤프가 8,130,000,000,000이 나왔다.
#
# 참고 — 실제 계열의 std/|평균| 비율
#     일별 주식·코인   10 ~ 1000
#     아주 매끈한 채권  1 이상
#     예금형(위 사례)   2e-12          ← 1e-6보다 여섯 자리 아래

# ① 부동소수 잡음 판정(분산 대 분산). 배분기가 쓴다.
REL_EPS = 1e-12

# ② 쓸 만한 분산이 있는가(표준편차 대 계열의 크기). 샤프류가 쓴다.
#    1e-6은 현실의 어떤 계열보다도 1000배 이상 아래라 오판 여지가 없다.
SHARPE_REL_EPS = 1e-6


def degenerate_spread(sd: float, scale: float,
                      rel_eps: float = SHARPE_REL_EPS) -> bool:
    """이 표준편차를 샤프의 분모로 써도 되는가 — 안 되면 True.

    scale: 그 계열의 크기(보통 |평균| 또는 평균 절대값). 크기를 모르면
           1.0을 넘겨 절대 기준으로 판정한다.
    rel_eps: 기본은 ②(SHARPE_REL_EPS). 분산 대 분산을 재는 자리는
             REL_EPS를 명시적으로 넘긴다 — 위 주석의 두 질문 참고.
    """
    try:
        sd = float(sd)
        scale = abs(float(scale))
    except (TypeError, ValueError):
        return True
    if not math.isfinite(sd) or sd <= 0.0:
        return True
    return sd <= float(rel_eps) * max(scale, 1e-300)


def safe_sharpe(mean: float, sd: float, scale: float | None = None) -> float:
    """퇴화한 계열이면 0.0, 아니면 mean/sd.

    '모르면 숫자를 만들지 않는다' — 분산이 없는 계열의 샤프는 무한대가
    아니라 **판정 불가**다. 0은 '나쁘다'가 아니라 '근거 없음'을 뜻한다.
    """
    if degenerate_spread(sd, abs(mean) if scale is None else scale):
        return 0.0
    return float(mean) / float(sd)
