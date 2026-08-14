"""SNS 자동 게시 콘텐츠 생성 — 매일의 장부를 카드·캡처·설명글로 만든다.

매일 아침(자동화) 스레드·인스타그램에 올릴 재료를 만든다:
    1. 이미지 계획: 카드 썸네일(오늘의 성적표) + 사이트 페이지 캡처 여러 장
       — 실제 스크린샷은 워크플로의 헤드리스 크롬이 찍는다(이 모듈은 계획만).
    2. 설명글(캡션): 장부(status.json)에서 그날의 숫자를 읽어 정직하게 쓴다.
       인스타용(김)과 스레드용(500자 제한) 두 벌.

⚠️ 정직 원칙 — 캡션은 절대 수익을 약속하지 않는다. 모의투자임을 매번 밝히고,
   실제 장부 숫자(마이너스 포함)를 그대로 쓴다. 잘 나온 날만 올리는 선택 편향도
   없다: 매일 그날의 숫자가 그대로 나간다. 이것이 이 채널의 정체성이다.
"""
from __future__ import annotations

import json
import os

# 게시 이미지 계획 — (파일명, 사이트 상대경로). 워크플로가 이 순서대로 캡처한다.
# 사이트 화면 캡처가 아니라 인스타그램 카드뉴스 비율(4:5, 1080×1350)로
# 디자인된 전용 템플릿(sns_card.html)을 촬영한다. 3장 구성:
#   ①표지(훅) ②오늘의 숫자 ③새벽의 오디션 ④배분 ⑤판단의 속
#   ⑥확률 채점 ⑦왜 믿나 ⑧내일 예고·CTA — 페이지마다 메시지 하나씩
CAPTURE_PLAN = [(f"{i:02d}_card.png", f"sns_card.html?n={i}")
                for i in range(1, 9)]          # 8장 스토리 카드뉴스

# 카드뉴스 캔버스 크기 — 인스타 피드 최적(4:5). 워크플로 캡처 창 크기와 일치.
CARD_SIZE = (1080, 1350)

DEFAULT_SITE_URL = "https://quant.jiwon-1a2.workers.dev"
THREADS_TEXT_LIMIT = 500

HASHTAGS = "#퀀트 #AI투자 #모의투자 #알고리즘트레이딩 #8마일챌린지"


def _fmt_won(v: float) -> str:
    return f"{v:,.0f}원"


def _held_on(status: dict, key: str, date: str) -> bool:
    """그날 그 종목을 **실제로 들고 있었나** (종목 장부의 비중 > 0).

    기록이 없으면 False — 확인 못 한 것을 "샀다"고 방송하지 않는다.
    """
    hist = ((status.get("paper") or {}).get(key) or {}).get("history") or []
    for rec in reversed(hist):
        if rec.get("date") == date:
            return float(rec.get("weight") or 0.0) > 0
    return False


def _invested_ratio(port: dict, last: dict):
    """**실제로 시장에 나가 있는 비율** — 잔고에서 잰다 (감사 238).

    사이트의 "돈이 지금 어디 있나"와 **같은 출처**(장부의 holdings)를 쓴다.
    같은 값을 두 곳에서 따로 계산하면 언젠가 갈라진다(㉞).

    잔고가 없는 옛 기록에서는 None — 모르는 것을 목표로 대신하지 않는다.
    """
    holdings = port.get("holdings")
    equity = last.get("equity") or port.get("equity")
    try:
        equity = float(equity)
    except (TypeError, ValueError):
        return None
    if not holdings or equity <= 0:
        return None
    total = 0.0
    for h in holdings:
        try:
            total += float(h.get("value") or 0.0)
        except (TypeError, ValueError):
            continue
    return max(0.0, min(1.0, total / equity))


def _pending_weight(last: dict):
    """다음 세션 시가에 체결되기를 기다리는 비중 — 차이의 큰 몫이다."""
    pend = last.get("pending_next_open") or {}
    if not isinstance(pend, dict) or not pend:
        return None
    try:
        return sum(abs(float(v)) for v in pend.values())
    except (TypeError, ValueError):
        return None


def _today_numbers(status: dict) -> dict:
    """status.json에서 캡션에 쓸 그날의 숫자를 뽑는다 (없는 값은 None)."""
    port = (status.get("paper") or {}).get("portfolio:ALL") or {}
    hist = port.get("history") or []
    last = hist[-1] if hist else {}
    date = last.get("date") or status.get("updated", "")[:10]
    # 그날의 재학습 결과 — 교체/유지 수 (retrain_recent에서 그날 것만 집계)
    recent = [r for r in (status.get("retrain_recent") or [])
              if r.get("asof") == date]
    swaps = sum(1 for r in recent if r.get("promoted"))
    # 배분 상위 종목 — "오늘 AI가 어디에 실었나"의 하이라이트.
    # ⚠️ alloc은 **배분 예산**이라 모델이 관망한 종목에도 붙어 있다. 그대로
    #    쓰면 그날 한 주도 안 산 종목이 "오늘 배분 상위"로 나간다(감사 91).
    #    장부의 applied(종목별 실제 적용 노출)를 쓰고, 그게 없는 옛 기록은
    #    그날 종목 장부의 비중이 0인 종목을 뺀다.
    names = status.get("symbols") or {}
    applied = last.get("applied") or {}
    src = applied or (last.get("alloc") or {})
    keep = (list(src) if applied
            else [k for k in src if _held_on(status, k, date)])
    top = sorted(((k, src[k]) for k in keep), key=lambda kv: -kv[1])[:3]
    # ⚠️ **아직 안 산 종목에는 그렇게 적는다**(감사 238). 주식은 다음 세션
    #    시가에 체결되므로 오늘 목표를 잡아도 오늘은 한 주도 없다. 실측
    #    2026-08-14 캡션: "배분 상위: 솔라나 · 아마존 · 리플" — 아마존은
    #    그때 **한 주도 없었다.** 감사 91이 alloc→applied로 고친 것과 같은
    #    결함의 남은 절반이다(그때는 '관망 종목이 끼는 것'만 막았다).
    _pending = set(last.get("pending_next_open") or {})
    top_names = [(names.get(k, {}).get("name") or k.split(":")[-1])
                 + ("(대기)" if k in _pending else "")
                 for k, v in top if v > 0]
    return {
        "date": date,
        "equity": last.get("equity"),
        # ⚠️ 시작금을 **코드 상수**에서 읽으면 안 된다(감사 218). 그 상수는
        #    새 계좌를 만들 때의 기본값(8만원)이지 지금 계좌의 원금이 아니다.
        #    매칭 입금으로 원금이 100만원이 되고 계좌가 원화로 다시 열린
        #    뒤에도 캡션은 "가짜 돈 8만원으로 시작해"라고 나갈 참이었다 —
        #    사이트 산문은 같은 이유로 이미 고쳤는데 **캡션만 남아 있었다.**
        #    방송에 나가는 글이라 사이트보다 오히려 더 위험하다.
        "principal": port.get("principal"),
        "start_cash": port.get("start_cash"),
        "restarted": port.get("restarted"),
        # 누적(원금 대비)과 하루치는 절대 섞으면 안 된다 — 훅은 하루치를 쓴다.
        # 옛 기록에는 day_pct가 없어 그때는 history로 직접 계산한다.
        "return_pct": last.get("return_pct"),
        "day_pct": (last.get("day_pct") if last.get("day_pct") is not None
                    else _day_pct_from_history(hist, port)),
        "twr_pct": last.get("twr_pct"),
        "gross": last.get("weight"),
        # ⚠️ **위 gross는 '목표'다. 실제로 시장에 나가 있는 돈이 아니다**
        #    (2026-08-14 감사 238). 캡션은 이 값을 "총노출 46%"라고 불렀는데
        #    같은 날 계좌가 실제로 들고 있던 것은 **27.2%**였다. 차이는
        #    주식의 다음 시가 대기(13.9%p)와, 밴드·쿨다운으로 아직 목표까지
        #    채우지 못한 기존 보유다.
        #
        #    사이트는 2026-08-13에 이미 고쳤다 — "투자 중 271,475원(27.2%) ·
        #    현금 728,372원(72.8%)"에 "오늘 목표 노출은 45.6%"를 덧붙인다.
        #    **캡션만 남아 있었다.** 감사 218에서 시작금이 그랬고(산문은
        #    고쳤는데 캡션은 8만원), 감사 113·114에서 카드와 캡션이 서로
        #    번갈아 빠졌다. 같은 실수의 세 번째 거울이다.
        #
        #    방송에 나가는 글이라 사이트보다 오히려 더 위험하다 — 사이트는
        #    옆에 설명이 붙지만 캡션은 숫자 하나만 읽히기 때문이다.
        "invested": _invested_ratio(port, last),
        "pending_w": _pending_weight(last),
        "risk_scale": last.get("risk_scale", 1.0),
        # 사람의 개입 — 장부에는 "숨기지 않고 기록한다"고 남기면서 방송에는
        # 없었다(감사 96). 이 시스템에서 사람이 결과를 바꿀 수 있는 유일한
        # 통로다. 빼면 '전부 자동'이라는 주장 자체가 거짓이 된다.
        "paused": bool(last.get("paused")),
        "exposure_scale": last.get("exposure_scale"),
        "n_symbols": (last.get("champion") or {}).get("symbols"),
        # 실제로 든 종목 수 — 후보 수와 다르다(2026-08-12 감사 114).
        # 감사 113에서 **카드**를 고치면서 캡션을 놓쳤다. 89에서는 반대로
        # 캡션을 고치고 카드를 놓쳤었다 — 같은 실수의 거울이다.
        # ⚠️ **실제로 든 종목 수**다(감사 238에서 다시 좁혔다). 예전에는
        #    applied 키 수를 셌는데 거기엔 다음 시가 대기 종목이 들어 있어,
        #    한 주도 없는 날에도 "7종목 보유"라고 나갔다(실측 2026-08-14:
        #    실제 보유 5 · 캡션 7).
        "n_held": (len(port["holdings"]) if port.get("holdings")
                   else (len(keep) if applied else sum(
                       1 for k in src if src[k] > 0
                       and _held_on(status, k, date)))),
        "retrain_total": len(recent),
        "retrain_swaps": swaps,
        "top_names": top_names,
        "day_no": len(hist),
    }


def _day_pct_from_history(hist: list, port: dict) -> float | None:
    """장부에 day_pct가 없던 시절 기록의 폴백 — 같은 식으로 다시 계산한다."""
    if not hist:
        return None
    try:
        from quant.live.ledger_basics import day_return_pct
        return day_return_pct(hist, port.get("deposits") or [],
                              start_cash=float(port.get("start_cash")
                                               or hist[0].get("principal")
                                               or 80_000))
    except Exception:  # noqa: BLE001 — 숫자 하나 때문에 게시가 죽으면 안 된다
        return None


def _hook(x: dict) -> str:
    """첫 줄(훅) — 그날 실제로 일어난 일에서 나온다. 과장 금지, 데이터 결정적.

    잘 쓴 훅은 감탄사가 아니라 '숨기지 않는 태도'다: 손실이 나면 손실이
    첫 줄이다. 그게 이 계정을 다른 수익 인증 계정과 다르게 만든다.
    """
    r = x.get("day_pct")
    if x["risk_scale"] < 1.0:
        return ("킬스위치가 작동 중입니다. 손실이 한도를 넘으면 시스템이 "
                "스스로 물러나는 게 규칙이고, 오늘이 그 날입니다.")
    if r is None:
        return "오늘의 장부를 공개합니다."
    if r <= -1.0:
        return (f"오늘 {r:+.2f}%. 아픈 날도 그대로 올립니다 — "
                "그게 이 계정의 규칙입니다.")
    if r < 0:
        return f"오늘 {r:+.2f}%. 이 마이너스도 기록의 일부입니다."
    if r == 0:
        return "오늘은 거의 움직이지 않았습니다. 지루한 날도 기록입니다."
    if r < 1.0:
        return f"오늘 {r:+.2f}%. 작지만, 하루하루가 쌓여야 복리입니다."
    return (f"오늘 {r:+.2f}%. 좋은 날이지만 하루로는 아무것도 "
            "증명되지 않습니다 — 분포가 증명합니다.")


def build_captions(status: dict, site_url: str = DEFAULT_SITE_URL) -> dict:
    """장부 숫자로 인스타/스레드 캡션을 만든다. 반환: {"instagram", "threads", "date"}.

    구조(수동 게시에도 그대로 쓸 수 있는 완성 원고):
        훅(그날의 사건) → 실험 소개 한 줄 → 숫자 블록 → 오늘 AI가 한 일 →
        정직 고지 → 링크·태그.
    스레드는 500자 제한이 있어 짧은 판을 따로 만든다(자르다 만 문장 금지).
    """
    x = _today_numbers(status)
    date = x["date"] or "오늘"
    day = f"D+{x['day_no']}" if x["day_no"] else ""
    eq = _fmt_won(x["equity"]) if x["equity"] is not None else "—"
    # 누적(원금 대비)과 하루치를 분리해서 쓴다 — 예전에는 누적을 "오늘"이라
    # 불렀고, 누적이 커질수록 매일 같은 큰 숫자를 방송하게 되는 구조였다.
    ret = (f"{x['return_pct']:+.2f}%" if x["return_pct"] is not None else "—")
    dp = (f"{x['day_pct']:+.2f}%" if x.get("day_pct") is not None else None)
    day_line = f" · 오늘 {dp}" if dp else ""
    twr = (f"{x['twr_pct']:+.2f}%" if x.get("twr_pct") is not None else None)
    gross = (f"{x['gross'] * 100:.0f}%" if x["gross"] is not None else "—")
    # ⚠️ **실제 투자 비율을 앞에 쓴다**(감사 238). 캡션은 목표(gross) 하나만
    #    말했고, 읽는 사람은 그 숫자만큼 돈이 시장에 나가 있다고 읽는다.
    #    실측 2026-08-14: 목표 46% · 실제 27%. 사이트는 이미 둘을 구분해
    #    말하고 있었는데 캡션만 남아 있었다.
    inv = x.get("invested")
    if inv is None:
        # 잔고를 모르는 옛 기록 — 목표를 실제인 것처럼 말하지 않는다.
        money = f"목표 노출 {gross}"
    else:
        money = f"투자 중 {inv * 100:.0f}% · 현금 {(1 - inv) * 100:.0f}%"
        if x["gross"] is not None and abs(x["gross"] - inv) > 0.02:
            pw = x.get("pending_w")
            why = (f"다음 시가 대기 {pw * 100:.0f}%p 포함"
                   if pw else "아직 목표까지 안 채움")
            money += f" (오늘 목표 {gross} — {why})"
    tops = " · ".join(x["top_names"]) if x["top_names"] else "전 종목 관망"
    # 종목 수와 시작금은 산문에 박지 않는다 — 설정이 바뀌면 SNS만 조용히
    # 거짓말을 하게 된다(사이트에 같은 결함이 있어 이미 계약 검사로 막았다).
    from quant.live.ledger_basics import PORTFOLIO_START_CASH
    from quant.markets import AUTO_TARGETS
    n_sym = x.get("n_symbols") or len(AUTO_TARGETS)
    # '분산'이라 적으면 후보 전부에 퍼져 있는 것처럼 읽힌다. 절반이 관망인
    # 날도 있으므로 **보유 수와 후보 수를 나눠** 적는다(감사 114 · 91 계열).
    n_held = x.get("n_held")
    spread = (f"오늘 {n_held}종목 보유 / 후보 {n_sym}종목"
              if isinstance(n_held, int) else f"{n_sym}종목 후보")
    # 장부의 원금이 먼저, 없을 때만 코드 기본값(감사 218).
    _p = x.get("principal")
    if not isinstance(_p, (int, float)) or _p <= 0:
        _p = PORTFOLIO_START_CASH
    start_won = (f"{_p / 10_000:,.0f}만원" if _p >= 10_000 and _p % 10_000 == 0
                 else f"{_p:,.0f}원")
    # 계좌를 다시 연 날은 그 사실이 먼저다(감사 218). 기록이 0일인데
    # "자산 —"만 나가면 읽는 사람은 고장으로 읽는다 — 사실은 새 출발이다.
    rs = x.get("restarted") or {}
    restart_line = ""
    if rs.get("date") and not x.get("equity"):
        restart_line = (
            f"\n🔁 {rs['date']} 계좌를 원화 기준으로 다시 열었습니다 — "
            f"첫 기록은 다음 새벽 배치부터입니다. 이전 기록은 지우지 않고 "
            f"그대로 공개합니다.")
    kill = ("" if x["risk_scale"] >= 1.0 else
            f"\n🛑 킬스위치 — 낙폭 한도 초과로 노출 {x['risk_scale']:.0%} 제한")
    # 사람이 손을 댄 날은 그 사실도 같은 글에 나간다(감사 96).
    hands = []
    if x.get("paused"):
        hands.append("신규 주문 일시정지(보유 유지)")
    xs = x.get("exposure_scale")
    if isinstance(xs, (int, float)) and abs(float(xs) - 1.0) > 1e-9:
        hands.append(f"노출 배수 {float(xs):.0%}")
    owner = ("\n✋ 사람의 개입 — " + " · ".join(hands)
             + ". 이 날의 성적은 전략만의 결과가 아닙니다") if hands else ""

    # "오늘 AI가 한 일" — 교체가 있으면 교체가 뉴스, 없으면 유지가 뉴스다
    if not x["retrain_total"]:
        work = "오늘 새벽 재학습 기록이 없습니다(휴장 또는 지연)."
    elif x["retrain_swaps"]:
        work = (f"오늘 새벽 {x['retrain_total']}개 종목을 재학습해 "
                f"{x['retrain_swaps']}개 종목의 전략이 교체됐습니다. "
                "교체는 2단계 검증(선발전+결승전)을 통과했을 때만 일어납니다.")
    else:
        work = (f"오늘 새벽 {x['retrain_total']}개 종목을 재학습했지만 "
                "챔피언을 이긴 후보가 없어 전부 유지 — 교체가 없는 날이 "
                "정상입니다. 확실히 나은 것만 바꾸는 게 규칙이니까요.")

    twr_line = f" · 실력지표(TWR) {twr}" if twr else ""
    ig = (
        f"{_hook(x)}\n"
        f"\n"
        f"📊 8마일 챌린지 {day} — {date}\n"
        f"가짜 돈 {start_won}으로 시작해 매일 새벽 AI가 스스로 재학습·매매하는 "
        f"공개 실험. 목표는 1억이 아니라, '이 과정 전체를 숨김없이 "
        f"보여주는 것'입니다.\n"
        f"\n"
        f"💰 자산 {eq} (누적 {ret}{day_line}){twr_line}\n"
        f"📈 {money} · {spread}(코인·한국·미국)\n"
        f"🎯 오늘 배분 상위: {tops}{kill}{owner}{restart_line}\n"
        f"\n"
        f"🤖 {work}\n"
        f"\n"
        f"⚠️ 모의투자(페이퍼)입니다. 수익을 보장하지 않으며, 방향 적중률의 "
        f"현실적 상한은 52~55%입니다. 잘된 날만 골라 올리지 않습니다 — "
        f"매일, 그날 숫자가 그대로 나갑니다. 판단·장부·코드 전부가 "
        f"공개돼 있어 누구든 검증할 수 있습니다.\n"
        f"\n"
        f"🔗 {site_url}\n"
        f"{HASHTAGS}"
    )

    # 스레드는 500자 제한이라 짧은 판을 쓰되, **실제가 앞**이라는 규칙은 같다.
    short_money = (f"투자 {inv * 100:.0f}%(목표 {gross})" if inv is not None
                   else f"목표 노출 {gross}")
    th = (
        f"{_hook(x)}\n"
        f"\n"
        f"📊 8마일 챌린지 {day} · {date}\n"
        f"💰 {eq} (누적 {ret}{day_line}) · {short_money}\n"
        f"🎯 배분 상위: {tops}{kill}{owner}\n"
        f"⚠️ 모의투자 — 수익 보장 없음. 매일 그날 숫자 그대로.\n"
        f"🔗 {site_url}"
    )
    if len(th) > THREADS_TEXT_LIMIT:      # 링크·고지는 지키고 하이라이트를 줄인다
        # ⚠️ 킬스위치와 사람의 개입은 '하이라이트'가 아니라 **고지**다
        #    (2026-08-11 감사 97). 둘이 배분 상위 줄에 붙어 있던 탓에
        #    길이가 넘치면 같이 잘려 나갔다 — 쓸 말이 많은 날(교체가 많고
        #    종목명이 긴 날)일수록 경고가 사라지는 구조였다. 주석은 원래
        #    "고지는 지킨다"고 적혀 있었는데 코드가 그러지 않았다.
        th = (
            f"📊 8마일 챌린지 {day} · {date}\n"
            f"💰 {eq} (누적 {ret}{day_line}){kill}{owner}\n"
            f"⚠️ 모의투자 — 수익 보장 없음. 매일 그날 숫자 그대로.\n"
            f"🔗 {site_url}"
        )
    return {"instagram": ig, "threads": th, "date": date}


class PublishedContentChanged(RuntimeError):
    """이미 공개된 날의 글을 다시 쓰려 했다 — 과거는 고치지 않는다."""


def write_content(docs_dir: str = "docs",
                  site_url: str = DEFAULT_SITE_URL,
                  *, force: bool = False) -> dict:
    """docs/social/<날짜>/ 에 캡션·메타를 쓴다. 반환: meta(dict).

    이미지 파일은 워크플로의 헤드리스 크롬이 CAPTURE_PLAN대로 같은 폴더에
    찍는다. 폴더가 날짜별이라 URL이 매일 달라 CDN 캐시 문제도 없다.

    ⚠️ 이미 있는 날의 캡션이 **달라지면 거부한다**(2026-08-11 감사 86).
    그 폴더는 '그날 세상에 내보낸 글'의 기록이다. 예전에는 아무 경고 없이
    덮어썼는데, 캡션 코드가 바뀐 뒤 이 명령을 한 번 돌리면 **과거 게시물이
    조용히 다른 글로 바뀐다.** 실제로 그렇게 만들어 봤다:

        (그날 실제로 나간 글)  오늘 -0.06%  ← 누적을 '오늘'이라 부르던 결함
        (재생성한 글)          오늘 -0.05%  ← 오늘 고친 뒤의 올바른 값

    후자로 덮으면 아카이브가 **하지 않은 말을 했다고** 기록한다. 정직성이
    유일한 자산인 채널에서 그건 숫자 하나가 틀린 것보다 나쁘다. 고칠 것이
    있으면 과거를 고치는 게 아니라 docs/trust.html에 공시한다.

    내용이 **같으면** 조용히 지나간다(같은 날 재실행은 정상 흐름).
    정말 바꿔야 하면 force=True — 다만 그건 의도적인 행위여야 한다.
    """
    with open(os.path.join(docs_dir, "status.json"), encoding="utf-8") as f:
        status = json.load(f)
    caps = build_captions(status, site_url)
    date = caps["date"]
    out_dir = os.path.join(docs_dir, "social", date)

    if not force:
        changed = []
        for name, text in (("caption_instagram.txt", caps["instagram"]),
                           ("caption_threads.txt", caps["threads"])):
            fp = os.path.join(out_dir, name)
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding="utf-8") as f:
                    old = f.read()
            except OSError:
                continue
            if old != text:
                changed.append(name)
        if changed:
            raise PublishedContentChanged(
                f"{date} 의 캡션이 이미 있고 내용이 달라집니다({', '.join(changed)}).\n"
                "그 폴더는 '그날 세상에 내보낸 글'의 기록입니다 — 덮어쓰면 "
                "아카이브가 하지 않은 말을 했다고 기록합니다.\n"
                "고칠 것이 있으면 과거를 고치지 말고 docs/trust.html에 "
                "공시하세요. 정말 다시 쓰려면 --force 를 주세요.")

    os.makedirs(out_dir, exist_ok=True)
    meta = {
        "date": date,
        "site_url": site_url,
        "images": [f for f, _ in CAPTURE_PLAN],
        "pages": {f: p for f, p in CAPTURE_PLAN},
    }
    for name, text in (("caption_instagram.txt", caps["instagram"]),
                       ("caption_threads.txt", caps["threads"])):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(text)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    # latest.json — 어드민의 '오늘의 SNS 콘텐츠' 카드가 읽는 포인터.
    # 수동 게시 흐름: 어드민 열기 → 캡션 복사 → 이미지 저장 → 업로드 끝.
    latest = {**meta, "path": f"social/{date}",
              "captions": {"instagram": caps["instagram"],
                           "threads": caps["threads"]}}
    with open(os.path.join(docs_dir, "social", "latest.json"), "w",
              encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    return {**meta, "dir": out_dir}


def prune_old(docs_dir: str = "docs", keep: int = 14) -> list[str]:
    """오래된 게시 폴더를 지운다(저장소 무한 성장 방지). 반환: 지운 폴더명."""
    import shutil
    root = os.path.join(docs_dir, "social")
    if not os.path.isdir(root):
        return []
    dirs = sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
    removed = []
    for d in dirs[:-keep] if len(dirs) > keep else []:
        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
        removed.append(d)
    return removed
