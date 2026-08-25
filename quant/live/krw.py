"""실험 계좌를 원화로도 읽어 준다 — 세 트랙이 **같은 한 곳**을 쓴다.

사장님 지시(2026-08-24): *"각 페이지 당 최종 수익 결과 한국돈으로도
알려줘."*

맞는 지적이었다. 100만 챌린지는 원화로 나오는데 실험 세 트랙은 달러·USDT
로만 나왔다. "9,983 USD"는 한국에서 사는 사람에게 바로 와닿는 숫자가
아니다. 얼마를 벌었는지 잃었는지 매번 머릿속에서 환산해야 한다.

■ 여기서 가장 조심하는 것 — **계좌를 원화로 바꾸는 게 아니다**

감사 212·254가 이 저장소에서 가장 비쌌던 사고다. 한 계좌 안에 원화와
달러가 섞여서, 자산 합계가 진짜 원화 금액이 아니었다. META를 달러 시가로
사서 원화 종가로 평가하는 바람에 100만원 계좌가 7,249만원으로 찍힌 적도
있다(+7,150%).

그래서 이 모듈은 **장부를 건드리지 않는다.** 실험 계좌의 단위는 여전히
USD·USDT이고, 여기서 만드는 원화 값은 **읽기 편하라고 덧붙이는 환산**일
뿐이다. 화면도 그렇게 적어야 한다.

■ 왜 시드와 현재 자산을 **같은 환율**로 바꾸나

이게 이 파일에서 가장 중요한 결정이다.

시드를 그때 환율로, 지금 자산을 오늘 환율로 바꾸면 **환차손익이 성적에
섞인다.** 그런데 이 실험은 환위험을 진 적이 없다 — 달러 계좌 안에서만
사고팔았다. 원/달러가 3% 오른 날 "실험이 3% 벌었다"고 적으면 그건 이
실험이 하지 않은 일을 했다고 말하는 것이다.

그래서 **둘 다 오늘 환율로** 바꾼다. 그러면 퍼센트 수익률은 달러 기준과
정확히 같고, 원화 값은 순수하게 "그래서 이게 우리 돈으로 얼마인가"만
답한다.

■ USDT는 달러로 친다 — 그리고 그 사실을 적는다

USDT는 달러에 연동된 코인이라 1 USDT ≈ 1 USD로 다룬다. 대체로 맞지만
**연동이 깨진 적이 있다**(2023년 3월 한때 0.97까지). 지금 이 환산은 그
위험을 반영하지 않는다 — 그래서 화면이 '가정'이라고 밝힌다. 조용히
1:1로 치면 그건 사실이 아닌 주장을 숫자로 파는 것이다.

■ 모르면 비운다

환율을 못 받으면 ``None``이다. 1.0으로 대신하지 않는다 — 그러면 1만
달러가 1만 원으로 찍힌다.
"""
from __future__ import annotations

# USDT → USD 환산 가정. 1:1이지만 **가정임을 이름으로 남긴다** — 상수가
# 없으면 코드 어디에도 "이건 가정이다"라고 적힌 자리가 없어진다.
USDT_PER_USD = 1.0


def _rate(fetch=None):
    from quant.data.fx import usdkrw
    return usdkrw(fetch=fetch)


def krw_view(equity, start_cash, currency: str = "USD", *,
             rate=None, fetch=None) -> dict | None:
    """달러·USDT 계좌를 원화로 **읽어 주는** 값들.

    돌려주는 것:
        rate        오늘 원/달러
        equity      지금 자산(원)
        start_cash  시드(원) — **같은 환율**로 바꾼 값
        pnl         손익(원) = 자산 − 시드
        assumed_peg USDT를 달러로 친 경우 True

    환율을 모르면 ``None``. 계좌 단위가 이미 원화면 환산할 것이 없으므로
    ``None``이다 — 없는 일을 한 척하지 않는다.
    """
    cur = str(currency or "USD").upper()
    # 아는 통화만 환산한다. 두 경우를 한 줄이 함께 막는다:
    #   · KRW — 이미 원화다. 또 곱하면 자산이 1,380배가 된다.
    #   · 그 밖의 통화 — 달러로 넘겨짚지 않는다(엔이면 10배쯤 틀린다).
    # ⚠️ 예전에는 KRW를 따로 한 줄 더 막았는데, 아래 검사가 이미 걸러내므로
    #    그 줄은 **아무 일도 하지 않았다.** 지키지 않는 가드를 남겨 두면
    #    다음 사람이 그것을 안전장치로 믿는다(변이 시험이 잡아냈다).
    if cur not in ("USD", "USDT"):
        return None
    try:
        eq = float(equity)
        base = float(start_cash)
    except (TypeError, ValueError):
        return None
    if eq != eq or base != base:        # NaN
        return None
    r = rate if rate is not None else _rate(fetch)
    try:
        r = float(r)
    except (TypeError, ValueError):
        return None
    if not (r > 0):
        return None                     # 0이나 음수 환율은 환율이 아니다
    # USDT는 달러에 연동된 코인 — 1:1로 친다(가정).
    usd_eq = eq / USDT_PER_USD if cur == "USDT" else eq
    usd_base = base / USDT_PER_USD if cur == "USDT" else base
    return {
        "rate": round(r, 4),
        "equity": round(usd_eq * r, 0),
        "start_cash": round(usd_base * r, 0),
        # ⚠️ 손익도 **같은 환율**로 낸 값이다. 시드를 옛 환율로 바꾸면
        #    환차손익이 섞여, 이 실험이 지지 않은 위험을 성적에 넣게 된다.
        "pnl": round((usd_eq - usd_base) * r, 0),
        "assumed_peg": (cur == "USDT"),
        "note": ("읽기 편하라고 덧붙인 환산입니다 — 이 계좌의 단위는 "
                 + cur + "이고, 시드와 지금 자산을 **같은 환율**로 바꿨으므로 "
                 "퍼센트 수익률은 " + cur + " 기준과 같습니다. 환율 변동은 "
                 "이 실험의 성적에 들어가지 않습니다."),
    }
