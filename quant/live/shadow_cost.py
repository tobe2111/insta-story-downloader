"""그림자 계좌 넷이 함께 쓰는 회전 비용 — **한 곳에만 적는다** (2026-09-08).

■ 왜 옮겼나

배분 사다리 · 2세대 · 무제약 · 다양성 그림자가 **글자까지 똑같은**
`_turnover_cost`를 각자 하나씩 들고 있었다(실측: 네 벌이 동일). 이 저장소는
그 모양을 이미 한 번 정리했다 —

    "찾는 방법은 **one_of 한 곳에만** 있다. 예전에는 같은 사전·규칙 조회를
     여기와 one_of 두 곳에 적어 뒀는데, 그러면 언젠가 갈라진다."

실제로 갈라졌다. 2026-09-03에 한국 ETF의 증권거래세를 빼면서 *"체결·밴드·
오디션·공개 자료가 전부 종목을 넘겨받는다"*고 적었는데, **네 벌 전부가
종목을 버리고 있었다**(`key.split(":")[0]` — 시장만 쓰고 종목은 흘린다).

■ 그래서 얼마였나 (2026-09-08 실측)

`is_etf`는 종목을 모르면 **주식으로 본다**(비싼 쪽 = 보수적). 그래서 운용
한국 12종목 중 ETF 6종목이 6.5bp 대신 **14.0bp** — **2.15배**를 물었다.

    069500 · 132030 · 133690 · 148070 · 228790 · 273130

⚠️ 방향이 '보수적'이라 늦게 잡혔다. **보수적인 것과 옳은 것은 다르다** —
2026-09-03에 같은 문장을 적어 놓고 그날 배선을 반만 했다.
"""
from __future__ import annotations

#: 비용 모델을 못 부를 때 쓰는 값(회전율당 편도). 그림자 넷이 같은 값을
#: 쓰던 것을 그대로 옮겼다 — 상대 비교 전용이라 절대값에 뜻이 없다.
FALLBACK_ONE_WAY = 0.001


def one_way(key: str, state_dir: str, fallback: float = FALLBACK_ONE_WAY) -> float:
    """`"시장:종목"` 한 칸의 실측 편도 비용.

    ⚠️ **종목을 끝까지 넘긴다.** 시장만 넘기면 ETF가 주식 요율을 문다
    (위 실측 참조). 이 함수가 존재하는 이유의 절반이 그것이다.
    """
    try:
        from quant.live.daily import measured_cost_model
    except Exception:  # noqa: BLE001 — 비용 조회 실패가 그림자 기록을 막으면 안 된다
        return fallback
    market, _, symbol = str(key).partition(":")
    try:
        return float(measured_cost_model(
            market, state_dir, symbol=symbol or None).total_one_way())
    except Exception:  # noqa: BLE001 — 같은 이유
        return fallback


def turnover_cost(target: dict, prev: dict, state_dir: str,
                  fallback: float = FALLBACK_ONE_WAY) -> float:
    """회전 × **그 종목의 실측 편도 비용** — 본 계좌와 같은 자.

    2026-09-02 사장님 지시("각 수수료도 고려해서 수익을 생각해야지 — 모든
    투자 마찬가지"). 예전엔 시장 무관 10bp 고정이라 한국·코인은 싸게,
    미국은 비싸게 셌다 — 본 계좌와 나란히 놓는 비교가 기울어 있었다.
    """
    return sum(abs(float(target.get(k, 0.0)) - float(prev.get(k, 0.0)))
               * one_way(k, state_dir, fallback)
               for k in set(target) | set(prev))
