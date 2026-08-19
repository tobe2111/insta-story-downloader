"""\"그냥 보유했다면 얼마였나\" — 이 단계에서 유일하게 의미 있는 점수.

⚠️ 왜 이 파일이 생겼나 (2026-08-17, 감사 276).
   첫 화면은 "손해 −2,802원(−0.28%)"만 말하고 있었다. 그런데 같은 기간
   전 종목을 그냥 사서 들고만 있었다면 **1,005,900원**이었다. 즉 진짜
   성적은 −2,802원이 아니라 **−8,702원(−0.87%p)**이다.

   이 구별이 중요한 이유. 이 저장소가 지금 증명하려는 것은 "1억"이 아니다 —
   변동성 타깃 12%로는 100배까지 40년이 걸린다는 산수를 README가 이미 적어
   두었다. 증명하려는 것은 **"그냥 보유보다 낫다"** 하나다. 그렇다면 점수판도
   그 질문에 답해야 한다. 절대 수익만 크게 적으면 시장이 오른 날은 실력처럼
   보이고 내린 날은 억울해 보인다.

기준선은 장부의 ``price``(첫날 전 종목 균등 매수 지수)다 — 사이트 차트가
이미 그 값으로 점선을 그린다. **새로 만들지 않는다.**

브라우저 짝은 ``docs/assets/benchmark.js``이고, 두 구현이 같은 답을 내는지는
``tests/test_the_score_is_measured_against_holding.py``가 값으로 확인한다.
"""

from __future__ import annotations

import math


def vs_hold(history: list | None, principal, cost_rate=0.0) -> dict | None:
    """전략 vs '첫날 균등 매수 후 보유'. 못 재면 None.

    반환: ``{"hold", "diff", "diff_pct", "ahead", "cost_rate"}``
      hold      그냥 보유했다면 지금 얼마인가(원)
      diff      전략 − 보유(원). 음수면 지고 있다.
      diff_pct  같은 것을 %p로
      ahead     앞서고 있는가
      cost_rate 기준선이 실제로 문 진입 비용률(0이면 안 물었다는 뜻)

    ⚠️ 하나라도 없으면 **답을 지어내지 않는다.** 기준선을 모르는데
       "이겼다/졌다"를 적는 것이 이 사이트에서 가장 하면 안 되는 일이다.

    ⚠️ **그냥 보유도 살 때 한 번은 돈을 낸다** (2026-08-19 사장님 승인).
       예전에는 ``cost_rate``가 없어 기준선이 비용을 한 푼도 안 물었다.
       그런데 우리 성적(``equity``)은 수수료·세금·미끄러짐을 전부 문 뒤의
       값이다. 같은 자에 눈금이 둘이었고, 그 자로 잰 "그냥 보유보다 낫다"가
       이 제품이 증명하려는 **단 하나의 주장**이었다.

       무는 것은 **편도 한 번**이다 — 그냥 보유는 사고 나면 팔지 않고,
       우리도 아직 들고 있는 몫은 파는 비용을 안 물었다. 양쪽 다 '지금
       들고 있는 상태'를 재므로 진입 비용만 맞추면 눈금이 같아진다.

       비율은 **여기서 고르지 않는다.** 장부가 그날 바구니의 시장 구성으로
       계산해 ``bench_cost_rate``로 남긴 값을 부르는 쪽이 넘긴다 — 화면이
       제 마음대로 유리한 숫자를 고르지 못하게.

       기울기는 우리 쪽에 유리하다(기준선이 낮아진다). 그래서 결과에
       ``cost_rate``를 함께 돌려준다 — 화면이 "사는 값 포함"이라고 말할
       자격이 있는지를 값으로 확인할 수 있게.
    """
    h = history or []
    if len(h) < 2:
        return None
    try:
        base = float(principal)
        p0 = float((h[0] or {}).get("price"))
        last = h[-1] or {}
        pn = float(last.get("price"))
        eq = float(last.get("equity"))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (base, p0, pn, eq)):
        return None
    if not (base > 0 and p0 > 0 and pn > 0):
        return None
    try:
        c = float(cost_rate or 0.0)
    except (TypeError, ValueError):
        c = 0.0
    if not (math.isfinite(c) and 0.0 <= c < 1.0):
        c = 0.0
    # 비용을 물고 산 몫만 시장을 탄다.
    hold = base * (1.0 - c) * pn / p0
    if not (hold > 0):
        return None
    diff = eq - hold
    return {"hold": hold, "diff": diff,
            "diff_pct": (eq / hold - 1) * 100.0, "ahead": diff >= 0,
            "cost_rate": c}
