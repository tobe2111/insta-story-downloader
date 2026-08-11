"""장부의 **기본 상수와 순수 계산** — 무거운 의존성 없이 쓸 수 있는 조각.

왜 따로 두는가 (2026-08-11 감사 102):

SNS 게시 워크플로에는 `pip install` 단계가 없다. 캡션을 만들고 카드를
찍어 커밋하는 게 전부라 numpy·pandas가 필요 없었기 때문이다. 그런데
같은 날 감사 89에서 "종목 수와 시작금을 산문에 박지 말고 코드에서
읽어라"를 고치면서 캡션이 이렇게 되었다:

    from quant.live.daily import PORTFOLIO_START_CASH   # ← daily는 numpy를 쓴다

숫자 하나를 읽으려고 매매 엔진 전체를 끌어온 셈이다. 개발 환경과 CI에는
numpy가 있어 검사는 전부 통과했고, **그날 밤 실제 게시만 죽었다**:

    ModuleNotFoundError: No module named 'numpy'

그래서 캡션이 쓰는 것들만 여기 모은다. 이 파일은 **표준 라이브러리 외에
아무것도 import하지 않는다** — tests/test_social_path_stays_light.py가
numpy·pandas를 막아 놓고 캡션 생성을 돌려 그 사실을 강제한다.

`quant.live.daily`는 여기서 다시 내보내므로 기존 import 경로는 그대로 쓴다.
"""

from __future__ import annotations

# 개별 종목 계좌 시작금 — 종목마다 독립 계좌로 참고용 기록을 쌓는다.
START_CASH = 10_000.0

# 8마일 챌린지 — 통합 계좌 시작금. 8종목 × 만원 = 8만원 (영화 8 Mile 오마주).
PORTFOLIO_START_CASH = 80_000.0

# 8마일 챌린지 목표 (8만원 → 1억)
GOAL_KRW = 100_000_000


def chrono(history: list[dict]) -> list[dict]:
    """기록을 날짜 오름차순으로 — 파생 수치는 시간순을 전제한다.

    ⚠️ 왜 필요한가(2026-08-11 장부 무결성 검사에서 발견): 한국주식 6종목의
    기록 배열이 08-05 → **08-07 → 08-06** → 08-10 순으로 어긋나 있었다.
    원인은 데이터 소스가 한때 아직 닫히지도 않은 08-07 봉을 먼저 내보낸 것
    (그래서 _drop_unclosed를 추가했다). 값 자체는 그날의 진짜 기록이지만
    **배열 순서**가 뒤집혀 있어, 하루치 수익률·낙폭·최고·최악일처럼 '직전
    날'을 참조하는 계산이 엉뚱한 날을 전날로 잡는다.

    저장된 기록은 건드리지 않는다 — "과거를 고치지 않는다"는 약속이 먼저다.
    대신 읽는 쪽에서 시간순으로 정렬해 계산한다. 값은 그대로고 순서만 바로잡는
    것이라 재계산이 아니며, 어긋난 배열은 장부에 증거로 남는다.
    """
    return sorted(history or [], key=lambda r: str(r.get("date", "")))


def day_return_pct(history: list[dict], deposits: list[dict],
                   start_cash: float = START_CASH) -> float | None:
    """마지막 기록일의 **하루치** 수익률(%) — 입금 효과 제거(TWR과 같은 식).

    왜 따로 두는가(2026-08-11 감사에서 발견): 기록의 return_pct는 원금 대비
    **누적** 수익률인데, SNS 캡션이 그것을 "오늘 X%"라고 읽고 있었다. 지금은
    누적이 -0.06%라 차이가 안 보이지만, 누적이 +40%가 되면 매일 "오늘 +40%"를
    방송하게 된다 — 정직성이 유일한 자산인 채널에서 가장 치명적인 거짓말이다.
    숫자는 산문이 아니라 장부에서 나와야 하므로, 하루치도 장부에 남긴다.
    """
    history = chrono(history)
    if not history:
        return None
    flows: dict[str, float] = {}
    dates = [r["date"] for r in history]
    for d in deposits or []:
        target = next((dt for dt in dates if dt >= d["date"]), None)
        if target is not None:
            flows[target] = flows.get(target, 0.0) + float(d["amount"])
    prev = float(history[-2]["equity"]) if len(history) >= 2 else float(start_cash)
    if prev <= 0:
        return None
    last = history[-1]
    eq = float(last["equity"]) - flows.get(last["date"], 0.0)
    return round((eq / prev - 1) * 100, 2)
