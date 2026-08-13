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


# ── 입금 효과를 제거한 성장 지수 ──────────────────────────────────
# ⚠️ 원래 `daily.py`에 있었다. 여기로 옮긴 이유(감사 197): **판정을 쓰는
#    곳이 장부만이 아니었다.** 조종석(reporting/dashboard.py)과 감시 탭
#    (web/app.py의 브라우저 JS)이 자산 곡선을 직접 읽어 손익·낙폭을 따로
#    계산하고 있었고, 그쪽에는 입금 보정이 없었다. 그런데 이 계산을 daily.py
#    에서 가져오려면 numpy·pandas가 딸려 온다(감사 102에서 SNS 게시가 죽은
#    바로 그 이유). 무거워서 안 쓰고 각자 계산한 것이다.
#    가볍게 만들어 놓으면 아무도 베껴 쓸 이유가 없다 — 표준 라이브러리만
#    쓰는 이 파일이 제 자리다. `daily.py`는 그대로 재수출한다.

def twr_index(history: list[dict], deposits: list[dict],
              start_cash: float = START_CASH) -> list[float]:
    """입금 효과를 제거한 누적 성장 지수(시작 1.0) 시계열.

    구간수익 r_t = (자산_t − 그날 입금액) / 자산_{t−1} − 1 을 연쇄 곱한다.
    입금 날짜가 기록일 사이면 '그 이후 첫 기록일'에 귀속시킨다(보수적).

    수익률뿐 아니라 **낙폭**도 이 지수 위에서 재야 한다(2026-08-11 감사).
    자산(equity) 고점 대비로 재면 입금이 고점을 끌어올려, 손실이 그대로인데
    낙폭이 0으로 보인다 — 그러면 킬스위치가 입금 때문에 풀린다.
    """
    history = chrono(history)
    if not history:
        return []
    flows: dict[str, float] = {}
    dates = [r["date"] for r in history]
    for d in deposits or []:
        target = next((dt for dt in dates if dt >= d["date"]), None)
        if target is not None:
            flows[target] = flows.get(target, 0.0) + float(d["amount"])
    out: list[float] = []
    idx, prev = 1.0, float(start_cash)
    for r in history:
        eq = float(r["equity"])
        if prev > 0:
            idx *= max(0.0, (eq - flows.get(r["date"], 0.0)) / prev)
        prev = eq
        out.append(idx)
    return out


def drawdown_from_index(index: list[float]) -> float:
    """성장 지수 시계열의 현재 낙폭(비율, 0 이하)."""
    if not index:
        return 0.0
    peak = max(index)
    return (index[-1] / peak - 1) if peak > 0 else 0.0


def max_drawdown_from_index(index: list[float]) -> float:
    """성장 지수 시계열의 최대낙폭(비율, 0 이하)."""
    peak, mdd = 0.0, 0.0
    for v in index:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1)
    return mdd


def time_weighted_return(history: list[dict], deposits: list[dict],
                         start_cash: float = START_CASH) -> float:
    """시간가중 수익률(%) — 입금(원금 증액)의 효과를 제거한 순수 운용 실력."""
    idx = twr_index(history, deposits, start_cash)
    return round((idx[-1] - 1) * 100, 2) if idx else 0.0


def _record_date(rec: dict) -> str:
    """기록의 날짜 — 장부는 "date", 조종석·감시 탭 상태는 "time"을 쓴다.

    모양이 다르다는 이유로 각자 계산하기 시작하면 두 화면이 같은 사실에
    대해 다른 수익률을 말하게 된다. 모양만 여기서 맞춘다.
    """
    return str(rec.get("date") or rec.get("time") or "")[:10]


def equity_curve_kpis(state: dict) -> dict:
    """조종석·감시 탭이 함께 쓰는 자산 KPI — {current, pnl, max_drawdown}.

    pnl·max_drawdown은 분수다(0.05 = +5%, -0.25 = -25%).

    ⚠️ **입금은 실력이 아니다**(감사 197). 예전에는 두 화면이 각자
    `cur / start - 1.0`로 계산했다. 자산 곡선을 그대로 읽으므로 원금을
    넣으면 그게 통째로 수익이 된다. 실측:

        8만원 → (92만원 입금) → 95만원
        화면   : 손익 **+1087.50%**
        사실   : 100만 → 95만 = **-5.00%**

    낙폭도 같이 거짓이 된다 — 입금이 고점을 끌어올려 **그 직전의 손실이
    낙폭에서 지워진다**(감사 ㊿에서 킬스위치가 입금 때문에 풀리던 것과
    같은 계열이고, `twr_index` 독스트링이 이미 경고한 내용이다).

    사이트 입금 안내문은 "입금이 실력처럼 보이지 않습니다"라고 약속한다.
    장부는 지키고 있었고 **두 화면만 그 약속 밖에 있었다.**

    잘려나간 과거(history_summary)의 start·peak·max_drawdown을 이어받는
    것은 그대로다 — 그게 없으면 저장 상한에 걸린 날부터 최대낙폭이 저절로
    좋아진다(감사 ㊿).
    """
    history = [h for h in (state.get("history") or []) if isinstance(h, dict)]
    equity = [float(h.get("equity", 0.0) or 0.0) for h in history]
    if not equity:
        return {"current": 0.0, "pnl": 0.0, "max_drawdown": 0.0}
    summ = state.get("history_summary") or {}
    cur = equity[-1]
    start = summ.get("start")
    if not isinstance(start, (int, float)) or start != start:
        start = equity[0]
    start = float(start)
    peak = summ.get("peak")
    if not isinstance(peak, (int, float)) or peak != peak:
        peak = start
    max_dd = float(summ.get("max_drawdown") or 0.0)
    for e in equity:
        peak = max(peak, e)
        max_dd = min(max_dd, e / peak - 1.0 if peak else 0.0)
    pnl = cur / start - 1.0 if start else 0.0

    # 입금 기록이 있을 때만 다시 잰다 — 없으면 성장 지수가 자산 곡선과
    # 같으므로 계산을 바꿀 이유가 없다(평소 수익률은 그대로여야 한다).
    deposits = state.get("deposits") or []
    if deposits:
        recs = [{"date": _record_date(h), "equity": e}
                for h, e in zip(history, equity)]
        idx = twr_index(recs, deposits, start_cash=start)
        if idx:
            pnl = idx[-1] - 1.0
            max_dd = min(max_dd, max_drawdown_from_index(idx))
    return {"current": cur, "pnl": pnl, "max_drawdown": max_dd}
