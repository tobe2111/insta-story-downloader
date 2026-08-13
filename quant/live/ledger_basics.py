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

import json
import os

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


# ── 입금의 '정산' — 언제부터 이 돈이 자산에 들어있나 (감사 211) ──────
#
# ⚠️ 왜 필요한가(2026-08-13, 실제 92만원 입금에서 터졌다):
#
#   입금은 **즉시** 장부의 현금(cash)에 들어간다. 그런데 화면이 읽는
#   `equity`는 **마지막 새벽 배치가 남긴 기록**이다. 그 사이(입금 직후 ~
#   다음 배치)에는 원금만 늘고 자산은 그대로다:
#
#       원금 80,000 → 1,000,000  ·  자산 79,250 (08-12 기록 그대로)
#       화면 손익   : **-920,749원**
#       사실       : -749원
#
#   감사 197의 정확한 **거울상**이다. 그때는 입금이 수익으로 보였고,
#   여기서는 입금이 손실로 보인다. 원인은 하나 — **자산과 원금을 서로
#   다른 시점에서 재는 것.** 둘은 같은 순간에 재야 한다.
#
# 왜 날짜 비교로 풀 수 없나: 기록의 날짜는 **마지막 완성 봉**이라 달력
# 날짜보다 뒤처진다(주말·휴장이면 며칠씩). 08-13 입금을 08-12 봉 기록과
# 날짜로 비교하면 "아직 안 들어왔다"가 되는데, 정작 배치는 그 현금을
# 포함해 자산을 계산한다 — 이번엔 반대로 **+1149%**가 뜬다.
#
# 그래서 날짜가 아니라 **사실**을 적는다. 자산을 실제로 다시 잰 배치가
# 그 봉 이름을 입금 기록에 도장처럼 찍는다(`settled_bar`). 찍히기 전은
# '접수됨', 찍힌 뒤가 '반영됨'이다. 금액·날짜·메모는 그대로다 —
# "과거를 고치지 않는다"는 약속은 **기록한 사실**에 대한 것이고, 정산
# 표시는 그 사실에 붙는 새 사실이다(수표에 결제 도장을 찍는 것과 같다).

def is_settled(dep: dict) -> bool:
    """이 입금이 이미 자산(equity)에 반영됐는가.

    `settled_bar`가 없으면 아직 어느 기록에도 안 들어간 돈이다.
    """
    return bool(dep.get("settled_bar"))


def settled_deposits(deposits: list[dict]) -> list[dict]:
    """자산에 이미 반영된 입금만."""
    return [d for d in deposits or [] if is_settled(d)]


def pending_deposits(deposits: list[dict]) -> list[dict]:
    """접수됐지만 아직 자산에 반영되지 않은 입금 — 화면이 밝혀야 할 것."""
    return [d for d in deposits or [] if not is_settled(d)]


def principal_of(start_cash: float, deposits: list[dict]) -> float:
    """자산과 **같은 시점의** 원금 = 시작금 + 정산된 입금.

    아직 반영되지 않은 입금을 여기 더하면 그 금액이 그대로 손실로 보인다.
    """
    return float(start_cash) + sum(float(d["amount"])
                                   for d in settled_deposits(deposits))


def _flow_date(dep: dict) -> str:
    """현금흐름을 귀속시킬 날짜 — 정산된 봉이 있으면 그 봉.

    TWR도 같은 함정에 빠진다. 입금 날짜(08-13)로 귀속처를 찾으면 기록일
    (08-12)보다 뒤라 **귀속처가 없어** 흐름이 통째로 무시되고, 다음 배치에서
    자산만 92만원 뛴 것으로 보여 실력이 +1149%로 기록된다. 배치가 찍어 준
    봉 이름이 있으면 그것이 정답이다 — 그 봉의 자산에 실제로 들어간 돈이다.
    """
    return str(dep.get("settled_bar") or dep.get("date") or "")


def _flows_by_date(history: list[dict], deposits: list[dict]) -> dict[str, float]:
    """기록일별 입금 유입액 — 기록일 사이의 입금은 '그 이후 첫 기록일'로."""
    flows: dict[str, float] = {}
    dates = [r["date"] for r in history]
    for d in deposits or []:
        want = _flow_date(d)
        target = next((dt for dt in dates if dt >= want), None)
        if target is not None:
            flows[target] = flows.get(target, 0.0) + float(d["amount"])
    return flows


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
    flows = _flows_by_date(history, deposits)
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
    flows = _flows_by_date(history, deposits)
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


# 보관된 옛 장부를 알아보는 표시. 파일 이름에 이것이 들어가면 **살아 있는
# 계좌가 아니다.**
#
# ⚠️ 왜 이름으로 가르는가: 보관본은 옛 장부의 **바이트 복사본**이라 안에
#    "나는 보관본이다"라고 적을 수가 없다 — 적는 순간 과거를 고치는 것이
#    된다. 그래서 표시는 파일 이름에만 붙인다.
#
# ⚠️ 왜 이 함수가 필요한가(만들자마자 실측): 장부를 읽는 세 곳이 전부
#    `state/paper/*.json`을 통째로 훑는다. 보관본 `portfolio_ALL.pre-krw.json`은
#    안에 `market: "portfolio"`가 그대로 있고 파일 이름이 알파벳순으로 **뒤에**
#    와서, 같은 키(`portfolio:ALL`)를 덮어썼다. 그 결과 새 원화 계좌를 열었는데
#    사이트는 **닫힌 옛 계좌**(7일치·자산 79,251원)를 계속 보여줬다.
ARCHIVE_MARK = ".pre-"


def is_archive(filename: str) -> bool:
    """보관된 옛 장부인가 — 살아 있는 계좌 목록에서 빼야 한다."""
    return ARCHIVE_MARK in os.path.basename(filename)


def redenominate_to_krw(state_dir: str, principal_krw: float,
                        *, today: str | None = None) -> dict:
    """통합 계좌를 **진짜 원화 계좌로** 다시 연다 (감사 212).

    왜 '환산'이 아니라 '다시 여는가': 옛 계좌는 되살릴 수가 없다. 가격만
    달러였던 게 아니라, 그 가격으로 판 돈이 **현금에 섞여 있다.** 현금
    41,910'원' 중 얼마가 진짜 원화이고 얼마가 달러였는지 장부에 남아 있지
    않다. 환율을 소급해 곱하면 그건 환산이 아니라 **과거를 지어내는 것**이다.

    그래서 옛 장부는 손대지 않고 그대로 파일로 남기고(`portfolio_ALL.pre-krw
    .json`), 새 원화 계좌를 연다. 사이트는 옛 기록을 이전 세대로 계속
    공개한다 — 실패한 기간을 지우지 않는 것이 이 프로젝트의 약속이다.

    ⚠️ **두 번 돌면 안 된다.** 이미 원화 계좌면 거절한다. 자동 마이그레이션으로
    만들지 않은 이유도 같다 — 매일 도는 배치가 계좌를 다시 여는 일은
    한 번의 실수로 전 기록을 날린다. 사람이 한 번 부르는 명령이어야 한다.
    """
    import shutil
    from datetime import date as _date

    from quant.utils.jsonio import atomic_write_json

    principal_krw = float(principal_krw)
    if principal_krw <= 0:
        raise ValueError("원금은 0원보다 커야 합니다.")

    path = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"통합 장부가 없습니다: {path}")
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    if old.get("currency") == "KRW":
        raise RuntimeError(
            "이미 원화 계좌입니다 — 다시 열지 않습니다. 두 번 돌면 "
            "지금 계좌의 기록이 통째로 사라집니다.")

    archive = os.path.join(state_dir, "paper", "portfolio_ALL.pre-krw.json")
    if os.path.exists(archive):
        raise RuntimeError(f"이전 계좌 보관 파일이 이미 있습니다: {archive}")
    shutil.copy2(path, archive)          # 옛 장부는 한 글자도 고치지 않는다

    day = today or _date.today().isoformat()
    hist = chrono(old.get("history") or [])
    new = {
        "market": old.get("market", "portfolio"),
        "symbol": old.get("symbol", "ALL"),
        "currency": "KRW",
        "start_cash": principal_krw,
        "cash": principal_krw,
        "positions": {}, "base_prices": {},
        "last_bar": None, "history": [], "deposits": [],
        # 왜 새로 열었는지를 장부 자신이 말한다 — 사이트·조종석이 읽는다.
        "restarted": {
            "date": day,
            "why": ("해외 종목 가격을 원화로 환산하지 않아 한 계좌에 원화와 "
                    "달러가 섞여 있었습니다(감사 212). 옛 자산 금액은 진짜 "
                    "원화가 아니었고 환위험도 빠져 있었습니다. 소급 환산은 "
                    "과거를 지어내는 일이라, 옛 장부는 그대로 보관하고 "
                    "원화 계좌를 새로 엽니다."),
            "archive": os.path.basename(archive),
            "prior_days": len(hist),
            "prior_last_date": (hist[-1].get("date") if hist else None),
            # 옛 자산은 단위가 섞인 값이라 원화로 비교할 수 없다. 숫자를
            # 옮기지 않고 '비교 불가'라고 적는다.
            "prior_equity_note": "단위 혼재 — 원화로 환산 불가",
        },
    }
    atomic_write_json(path, new)
    print(f"🔁 통합 계좌를 원화로 다시 열었습니다 — 원금 {principal_krw:,.0f}원")
    print(f"   옛 장부 보관: {archive} (기록 {len(hist)}일, 고치지 않음)")
    return new


def holdings_view(state: dict, equity: float | None = None) -> list[dict]:
    """종목별 **잔고** — 증권사 잔고 화면과 같은 항목으로 편다.

    왜 필요한가(2026-08-13): 사이트는 종목별 **비중(%)**만 보여줬다. 비중은
    "얼마를 넣었나"에 답하지 못한다 — 32%가 25,527원인지 알려면 자산을 알고
    곱해야 하고, 그나마도 **평단·수량·평가손익**은 어디에도 없었다. 장부에는
    다 있는데 사이트로 나가지 않은 것이다.

    항목은 증권사 잔고와 같게 맞춘다(사장님이 아는 화면이 곧 표준이다):
        보유수량 · 평균매입가 · 현재가 · 매입금액 · 평가금액 · 평가손익 · 수익률

    ⚠️ 현재가는 장부가 **마지막으로 알던 값**이다(`last_price_bar`가 언제
    것인지 함께 낸다). 실시간이 아니고, 그렇게 말해야 한다.
    """
    rows: list[dict] = []
    for key, p in (state.get("positions") or {}).items():
        qty = float(p.get("quantity") or 0.0)
        if qty == 0.0:
            continue
        avg = float(p.get("avg_price") or 0.0)
        # 시세를 못 받은 종목은 매입가로 평가된다 — 손익 0으로 보이는 그
        # 상태를 숨기지 않는다(감사 152와 같은 자리).
        px = p.get("last_price")
        marked = px is not None
        px = float(px if marked else avg)
        cost, value = qty * avg, qty * px
        rows.append({
            "key": key,
            "quantity": qty,
            "avg_price": avg,
            "last_price": px,
            "cost": round(cost, 2),
            "value": round(value, 2),
            "pnl": round(value - cost, 2),
            "pnl_pct": round((px / avg - 1) * 100, 2) if avg > 0 else None,
            "as_of": p.get("last_price_bar"),
            "marked": marked,
        })
    rows.sort(key=lambda r: -r["value"])
    if equity is None:
        equity = float(state.get("cash") or 0.0) + sum(r["value"] for r in rows)
    for r in rows:
        r["weight"] = round(r["value"] / equity, 6) if equity else 0.0
    return rows


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


# ── 매칭 입금 ────────────────────────────────────────────────────
# ⚠️ 원래 `daily.py`에 있었다. 여기로 옮긴 이유(2026-08-13): **입금 워크플로가
#    numpy 때문에 죽었다.**
#
#        python -m quant deposit --amount 920000 ...
#        → ModuleNotFoundError: No module named 'numpy'
#
#    이 함수는 numpy를 한 줄도 쓰지 않는다(날짜·JSON·산술이 전부). 그런데
#    `daily.py`에 얹혀 있어서, 부르는 순간 매매 엔진 전체가 딸려 왔다.
#
#    **감사 102와 똑같은 사고다.** 그때는 SNS 캡션이 숫자 하나를 읽으려고
#    `daily.py`를 임포트해 밤중에 게시가 죽었고, 그래서 이 파일이 생겼다.
#    교훈을 적어 두고 파일까지 만들어 놓고도, 정작 **다음에 추가된 함수는
#    또 무거운 쪽에 놓였다.** 규칙은 만드는 것보다 지키는 것이 어렵다.
#
#    판단 기준은 간단하다: **numpy·pandas를 쓰지 않는 함수는 여기 둔다.**
#    `quant.live.daily`가 그대로 재수출하므로 기존 import 경로는 안 바뀐다.

def add_deposit(amount: float, memo: str = "", *, state_dir: str = "state",
                date: str | None = None) -> dict:
    """후원 '매칭' 입금 — 통합 계좌의 원금을 늘린다 (8마일 챌린지 · 8만원 → 1억).

    ⚠️ 법적 구조(반드시 유지): 시청자의 후원금 자체를 굴리는 것이 아니다.
    후원은 대가·지분 없는 방송 후원이고, 운영자가 '같은 금액만큼' 가상 계좌
    원금을 늘리는 이벤트다. 이 구조를 바꾸면(타인 자금 운용) 유사수신·무인가
    집합투자 위험이 생긴다.

    모든 입금은 장부(deposits)에 기록되어 git 커밋으로 공개된다 — 수익률
    계산은 원금과 손익을 분리해(TWR) 입금이 실력처럼 보이지 않게 한다.
    """
    from datetime import date as _date

    from quant.utils.jsonio import atomic_write_json

    amount = float(amount)
    if not (0 < amount <= 10_000_000):
        raise ValueError("입금액은 0원 초과 1,000만원 이하여야 합니다.")

    path = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    else:
        st = {"market": "portfolio", "symbol": "ALL",
              "start_cash": PORTFOLIO_START_CASH,
              "cash": PORTFOLIO_START_CASH, "positions": {}, "base_prices": {},
              "last_bar": None, "history": [], "deposits": []}

    entry = {"date": date or _date.today().isoformat(),
             "amount": round(amount, 2), "memo": str(memo)[:80]}
    st.setdefault("deposits", []).append(entry)
    st["cash"] = float(st.get("cash", 0.0)) + amount
    atomic_write_json(path, st)

    sc = float(st.get("start_cash", PORTFOLIO_START_CASH))
    # 접수 총액(현금에는 이미 들어갔다)과 **자산에 반영된 원금**은 다르다.
    # 화면이 쓰는 것은 뒤쪽이다 — 자세한 이유는 이 파일 위쪽 '입금의 정산'.
    committed = sc + sum(d["amount"] for d in st["deposits"])
    principal = principal_of(sc, st["deposits"])
    print(f"💝 매칭 입금 +{amount:,.0f}원 ({entry['memo'] or '메모 없음'}) — "
          f"누적 원금 {committed:,.0f}원 / 목표 {GOAL_KRW:,}원")
    print("   ⏳ 자산에 반영되는 것은 다음 새벽 배치입니다 — 그때까지 "
          f"화면의 원금은 {principal:,.0f}원으로 남습니다(손익 왜곡 방지).")
    return {"deposit": entry, "principal": principal,
            "committed": committed, "goal": GOAL_KRW}
