"""플래그 파수꾼 — 사이트 표시 전용이던 경고가 새로 켜지면 알림으로도 쏜다.

사이트의 자기 고발 플래그(백테스트 낙관 의심·보정 어긋남·판정 시계
리셋/만료)는 매일 새벽 status.json에 계산되지만, 사장님이 사이트를 열어야
보인다. 이 모듈은 플래그 집합을 state/flag_state.json에 기억해 두고,
'새로 켜진' 플래그만 알림 채널(디스코드·텔레그램·슬랙 — 환경변수에 설정된
곳 전부)로 발송한다. 이미 켜져 있던 플래그는 조용하다 — 매일 같은 경고를
반복하면 경고가 소음이 된다. 꺼졌다가 다시 켜지면 다시 알린다.
"""
from __future__ import annotations

import json
import os


# 장부가 이 일수 이상 안 늘면 '배치가 멈췄다'로 본다. 통합 계좌에는 24시간
# 시장(코인)이 들어 있어 주말·휴일에도 매일 늘어야 한다 — 그래서 2일이면
# 이미 사건이다.
LEDGER_STALE_DAYS = 2


def _ledger_age(last: dict, today: str | None = None) -> tuple[str | None, int | None]:
    """장부 마지막 기록의 (날짜, 며칠 전인가). 못 재면 (None, None).

    ⚠️ 왜 필요한가 (2026-08-17, 감사 264). 이 파일의 경보들은 전부
       `history[-1]`을 읽으면서 **그 기록이 오늘 것인지 묻지 않았다.**
       그래서 배치가 커밋을 못 하면 며칠 전 기록의 경고가 매일 현재형으로
       나간다. 실제로 그랬다 — 2026-08-16 밤, 이미 이틀 전에 되돌린
       `cash_short`(감사 254 통화 사고)가 "지금 구조에서는 나올 수 없는
       값입니다"라며 다시 나갔다.

       오래된 경보를 **끄지는 않는다** — 아직 안 고쳤을 수도 있다. 대신
       언제 것인지 밝힌다. 그리고 장부가 멈춘 것 자체를 따로 알린다.
    """
    import datetime as _dt

    day = str(last.get("date") or "")[:10]
    if not day:
        return None, None
    try:
        d0 = _dt.date.fromisoformat(day)
        d1 = (_dt.date.fromisoformat(today) if today else _dt.date.today())
    except ValueError:
        return day, None
    return day, (d1 - d0).days


def _as_of(message: str, day: str | None, age: int | None) -> str:
    """오늘 기록이 아니면 언제 것인지 앞에 붙인다."""
    if day and age is not None and age >= 1:
        return f"[{day} 기록 · {age}일 전] {message}"
    return message


def _measured_cost_note(n: int) -> str:
    """실측 비용이 이미 적용 중인지 사실대로 말한다.

    ⚠️ 예전 문구는 "표본 30건 이상 유지 시 비용 프리셋 상향 검토"였는데,
    코드는 10건에서 이미 실측 비용으로 갈아타고 있었다(감사 66). 경보를
    읽는 사람은 '아직 아무 일도 안 일어났다'고 믿지만 오디션의 비용
    모델은 이미 바뀐 뒤다. 문턱은 코드에서 직접 읽어 온다.
    """
    from quant.live.daily import MEASURED_COST_MIN_SAMPLES as _MIN
    if n >= _MIN:
        return (f"표본 {_MIN}건을 넘겨 **오디션 비용 모델은 이미 실측값으로 "
                f"전환된 상태**입니다(가정이 아니라 실측으로 후보를 겨룹니다).")
    return (f"표본이 {_MIN}건을 넘으면 오디션 비용 모델이 자동으로 실측값으로 "
            f"전환됩니다(현재 {n}건 — 아직 가정을 씁니다).")


def _current_flags(status: dict, today: str | None = None) -> dict[str, str]:
    """status.json 재료에서 지금 켜져 있는 플래그를 {키: 알림 문구}로 모은다.

    ⚠️ **받은 것만 본다.** 파일을 직접 읽지 않는다 — 2026-08-16에 장중 감시
    기록을 여기서 읽게 만들었다가, 그 기록이 쌓이자 감시와 아무 상관 없는
    검사들까지 "경보 없음"을 확인하지 못하고 무너졌다. 판정하는 함수가
    바깥 상태를 몰래 읽으면 그 함수는 더 이상 값으로 확인할 수 없다.
    재료를 모으는 일은 daily.py(status를 만드는 쪽)가 한다.
    """
    flags: dict[str, str] = {}

    # ① 체결 가정 검증 — 실측 불리 갭이 백테스트 가정을 초과(낙관 의심)
    fc = status.get("fill_check") or {}
    for market, r in (fc.get("markets") or {}).items():
        if r.get("optimistic"):
            flags[f"optimistic:{market}"] = (
                f"⚠️ 체결 가정 검증: {market} 실측 불리 갭 평균 "
                f"{r['mean_adverse_bp']}bp > 백테스트 가정 {r['assumed_bp']}bp "
                f"(표본 {r['n']}건) — 백테스트가 낙관적일 수 있습니다. "
                + _measured_cost_note(int(r.get("n") or 0)))

    # ② 보정 어긋남 — 예측확률이 실제 적중률의 신뢰구간 밖(표본 확정 구간만)
    try:
        from quant.live.calibration_guard import calibration_table
        hists = [(p.get("history") or [])
                 for k, p in (status.get("paper") or {}).items()
                 if not k.startswith("portfolio")]
        for row in calibration_table(hists):
            if row["confirmed"]:
                key = f"miscal:{int(row['lo'] * 100)}-{int(row['hi'] * 100)}"
                flags[key] = (
                    f"⚠️ 보정 어긋남 확정: 예측 {int(row['lo'] * 100)}~"
                    f"{int(row['hi'] * 100)}% 구간의 실제 상승 비율 "
                    f"{row['actual'] * 100:.0f}% (표본 {row['n']}건, 95% CI "
                    f"{row['ci_lo'] * 100:.0f}~{row['ci_hi'] * 100:.0f}%) — "
                    f"사이트에 경험 보정값 병기 중(사이징 개입 없음).")
    except Exception:  # noqa: BLE001 — 보정표 실패가 다른 플래그를 막으면 안 된다
        pass

    # ③ 회전율 비용 — 비용이 기대수익을 넘으면 엣지가 있든 없든 수익이 없다.
    #    2026-08-11 실측에서 일 37% 회전 → 연 40% 비용 vs 기대수익 8.8%였다.
    #    밴드·평활·쿨다운으로 고쳤지만 효과는 미검증 — 그래서 매일 감시한다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = [r for r in (p.get("history") or []) if r.get("turnover")]
        recent = hist[-20:]
        if len(recent) < 10:
            continue                       # 표본이 얇으면 판정하지 않는다
        # ⚠️ 이 경보는 2026-08-12 감사 119부터 **죽어 있었다**(감사 136).
        #    그때 장부의 `turnover.ratio`(= 체결 종목 수 ÷ 후보 수)를
        #    `symbols_ratio`로 이름을 바꾸고 진짜 회전율 `traded`를
        #    추가했는데, **소비처를 찾지 않았다.** 여기 `.get("ratio")`가
        #    없는 키를 읽어 `or 0.0`으로 0이 되고, 비용이 늘 0이라 경보가
        #    한 번도 울릴 수 없었다 — 조용히 0을 읽는 코드는 고장을
        #    '이상 없음'처럼 보이게 한다.
        #    (FROZEN_IDEAS ⑭ 고친 결함은 형제를 찾기 전까지 고친 게 아니다.
        #     그 계명을 적은 회차에 내가 어겼다.)
        #
        #    비용은 '몇 종목을 건드렸나'가 아니라 '얼마어치를 사고팔았나'에
        #    비례하므로 `traded`(Σ|Δ적용노출|)만 쓴다. 없는 날은 **세지
        #    않는다** — 0으로 치면 옛 기록이 경보를 희석한다.
        vals = [r["turnover"].get("traded") for r in recent]
        vals = [float(v) for v in vals if isinstance(v, (int, float))]
        if len(vals) < 10:
            continue           # 금액 기준 표본이 얇으면 판정하지 않는다
        avg = sum(vals) / len(vals)
        # 가중평균 왕복 비용 43bp(코인 30·미국 12·한국 실측 93 기준 근사)
        annual_cost = avg * 252 * 0.0043
        vt = (hist[-1].get("vol_target") or {}) if hist else {}
        expected = float(vt.get("target") or 0.12)   # 샤프 1.0 가정
        if annual_cost > expected:
            flags["turnover_cost"] = (
                f"⚠️ 회전율 경보: 최근 {len(recent)}일 평균 {avg * 100:.0f}%/일 "
                f"→ 연 비용 약 {annual_cost * 100:.0f}%가 기대수익 "
                f"{expected * 100:.0f}%를 넘습니다. 비용이 엣지를 먹는 구조 — "
                f"밴드·쿨다운을 더 넓히거나 고비용 시장(한국주식) 비중을 "
                f"재검토해야 합니다.")

    # ③-2 실현 불가 보유 — 소수점 매매가 없는 시장(국내주식)에서 배정금액이
    #     1주 값에 못 미치면, 장부의 그 줄은 실계좌에서 재현할 수 없다.
    #     기록만 남기고 아무도 안 읽으면 감사 135의 반복이다 — 읽는 사람을 둔다.
    #     구조적 조건이라 매일 바뀌지 않으므로, 플래그 키에 종목 수를 넣어
    #     '수가 바뀔 때'만 다시 알린다(같은 상태로 매일 울리면 아무도 안 본다).
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        bad = ((hist[-1].get("lot_infeasible") if hist else None) or {})
        if not bad:
            continue
        names = ", ".join(sorted(bad))
        flags[f"lot_infeasible:{len(bad)}"] = (
            f"⚠️ 실현 불가 보유 {len(bad)}종목: {names} — 소수점 매매가 없는 "
            f"시장인데 배정금액이 1주 값에 못 미칩니다(예: "
            f"{next(iter(bad.values()))['budget']:,.0f}원 배정 / 1주 "
            f"{next(iter(bad.values()))['price']:,.0f}원). 이 줄들은 실계좌에서 "
            f"재현할 수 없습니다 — 유니버스 조정이나 정수 주 강제를 검토하세요.")

    # ③-3 "나오면 안 되는 값"이 나왔다 (감사 260).
    #
    #     장부에는 구조상 절대 안 나와야 하는 칸이 둘 있다.
    #       cash_short   — 현금이 모자라 브로커가 거부한 주문. 레버리지
    #                      금지선·수수료 버퍼·매도 우선이 셋 다 막고 있다.
    #       fill_refused — 체결가와 평가가격의 자릿수가 안 맞아 막은 주문.
    #                      통화 환산이 어딘가에서 빠졌다는 뜻이다.
    #     둘 다 주석에는 "나오면 안 되는 값"이라고 적혀 있었는데 **아무도
    #     보지 않았다.** 2026-08-15에 cash_short가 실제로 찍혔고, 그것이
    #     자산 7,249만원 사고의 가장 이른 신호였다 — 새벽 5시 30분에
    #     장부에 남았고, 반나절 뒤 사람이 우연히 볼 때까지 조용했다.
    #     화면에 띄우는 것만으로는 부족하다. 화면은 열어야 보인다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        last = (p.get("history") or [{}])[-1]
        # 이 아래 경보들은 전부 '마지막 기록'을 읽는다. 그 기록이 오늘 것인지
        # 먼저 묻는다 — 안 물으면 며칠 전 사고가 매일 현재형으로 나간다.
        _day, _age = _ledger_age(last, today)
        if _age is not None and _age >= LEDGER_STALE_DAYS:
            # 장부가 멈춘 것 **자체**가 사건이다. 배치 실패 경보는 워크플로가
            # 따로 보내지만, 그 채널이 죽으면(감사 263) 아무도 모른다.
            flags[f"ledger_stalled:{key}:{_age}"] = (
                f"🚨 장부가 {_age}일째 안 늘고 있습니다(마지막 기록 {_day}). "
                f"새벽 배치가 기록을 남기지 못했다는 뜻입니다 — 아래 경고들은 "
                f"오늘이 아니라 그날의 상태입니다. 배치 로그를 확인하세요.")
        cs = last.get("cash_short") or []
        if cs:
            names = ", ".join(str(r.get("key")) for r in cs)
            flags[f"cash_short:{key}:{len(cs)}"] = _as_of(
                f"🚨 현금 부족으로 거부된 주문 {len(cs)}건: {names} — 지금 "
                f"구조에서는 나올 수 없는 값입니다. 레버리지 금지선·수수료 "
                f"버퍼·매도 우선 순서 중 하나가 새고 있다는 뜻이고, 계좌는 "
                f"이유 없이 계획보다 덜 산 채로 굴러갑니다.", _day, _age)
        # 증거금 없이 팔려다 잘린 주문(감사 264). **현금 부족과 다른 사고다** —
        # 계좌가 덜 산 게 아니라 **계획보다 덜 판** 것이고, 그 종목의 실제
        # 노출은 장부의 목표와 다르다. 같은 이름으로 묶으면 원인을 잘못 짚는다.
        sr = last.get("short_refused") or []
        if sr:
            names = ", ".join(str(r.get("key")) for r in sr)
            flags[f"short_refused:{key}:{len(sr)}"] = _as_of(
                f"🚨 증거금이 모자라 잘린 공매도 {len(sr)}건: {names} — 장부의 "
                f"목표 노출과 계좌의 실제 보유가 그만큼 어긋나 있습니다. 숏은 "
                f"아직 링에 없어야 하므로, 이 값이 찍혔다면 전략이나 증거금 "
                f"설정 중 하나가 예상과 다릅니다.", _day, _age)
        # 요청보다 적은 표본으로 판단한 종목(감사 261). 성적이 나쁜 것이
        # 아니라 **성적을 말할 근거가 얇은** 상태다 — 이걸 모르면 300봉으로
        # 낸 결론을 800봉짜리 확신으로 읽는다. 종목 수가 바뀔 때만 다시
        # 알린다(같은 상태로 매일 울리면 아무도 안 본다).
        bs = last.get("bars_short") or {}
        if bs:
            worst = min(bs.items(), key=lambda kv: kv[1]["got"] / kv[1]["asked"])
            flags[f"bars_short:{key}:{len(bs)}"] = _as_of(
                f"⚠️ 표본이 모자란 채로 판단한 종목 {len(bs)}개 — 예: "
                f"{worst[0]} {worst[1]['got']}/{worst[1]['asked']}봉. "
                f"데이터 제공처가 요청한 만큼 주지 않았거나 상장 이력이 "
                f"짧습니다. 이 종목들의 성적·과최적화 지표는 표본 부족의 "
                f"산물일 수 있습니다(2026-08-15까지 코인 5종목이 800봉 "
                f"요청에 300봉으로 굴러갔습니다).", _day, _age)
        fr = last.get("fill_refused") or {}
        if fr:
            names = ", ".join(sorted(fr))
            flags[f"fill_refused:{key}:{len(fr)}"] = _as_of(
                f"🚨 자릿수가 맞지 않아 거부된 체결 {len(fr)}건: {names} — "
                f"체결가와 평가가격이 같은 통화가 아닌 것으로 보입니다. "
                f"2026-08-15에 이 상태로 100만원 계좌가 7,249만원으로 "
                f"기록됐습니다(감사 254). 대기 주문은 남아 있으므로 고치기 "
                f"전까지 그 종목은 매일 거부됩니다.", _day, _age)

    # ③-4 장중 감시가 **예약대로 안 돌고 있다** (감사 262).
    #
    #     guard.yml은 15분마다 돌게 예약돼 있지만, 공용 러너는 촘촘한 cron을
    #     크게 밀거나 건너뛴다. 2026-08-16 실측 최악 간격은 **558분**이었다.
    #     레버리지 한도는 이미 실측 간격으로 계산하므로 안전 쪽으로 기울지만,
    #     **그 사실이 사람에게 닿지 않으면 문서와 대외 문구가 계속 "15분마다
    #     봅니다"라고 말한다** — 이 저장소가 가장 싫어하는 상태다.
    #     심장박동은 매 회차 기록됐고, 아무도 그것을 읽지 않았다.
    #
    #     ⚠️ 이 판정의 재료는 **status가 실어다 준다**(2026-08-16). 처음에는
    #        여기서 심장박동 파일을 직접 읽었는데, 그러자 이 함수가 저장소의
    #        지금 상태에 묶였다 — 감시 기록이 쌓이자 감시와 아무 상관 없는
    #        검사들까지 "경보 없음"을 확인하지 못하고 무너졌다. **판정하는
    #        함수는 자기가 받은 것만 봐야 한다.** 재료 수집은 daily.py가 한다.
    try:
        from quant.live.guard import GUARD_LATE_FACTOR
        g = status.get("guard") or {}
        gap = g.get("observed_gap_min")
        interval = float(g.get("interval_min") or 0.0)
        limit = interval * GUARD_LATE_FACTOR
        booked = f"{interval:g}"                   # 15.0이 아니라 15로 읽히게
        if gap is not None and interval > 0 and gap > limit:
            flags[f"guard_late:{int(gap // 60)}h"] = (
                f"⚠️ 장중 감시가 예약대로 돌지 않습니다 — 예약 {booked}분 "
                f"간격인데 실제로 관측된 최악 간격은 **{gap:,.0f}분**"
                f"({gap / 60:.1f}시간)입니다. 레버리지 한도는 실측 간격으로 "
                f"계산하므로 안전 쪽으로 기울지만, 문서·대외 문구에서 "
                f"'{booked}분마다 본다'고 말하면 안 됩니다.")
    except Exception:  # noqa: BLE001 — 감시 기록이 없어도 다른 플래그는 살린다
        pass

    # ④ 킬스위치 — 통합 계좌가 낙폭으로 노출을 줄인 순간은 즉시 알아야 할
    #    사건이다. 단계가 더 내려가면(0.75→0.5) 키가 바뀌어 다시 알리고,
    #    1.0 복귀는 조용히 플래그만 끈다(복귀 후 재발동 시 재알림).
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        last = hist[-1] if hist else {}
        rs = last.get("risk_scale")
        if rs is not None and float(rs) < 1.0:
            dd = last.get("drawdown_pct")
            dd_txt = f" (낙폭 {dd}%)" if dd is not None else ""
            flags[f"killswitch:{key}:{rs}"] = (
                f"🛡 킬스위치 발동: 통합 계좌 노출을 {float(rs) * 100:.0f}%로 "
                f"축소{dd_txt} — 낙폭 단계별 자동 브레이크입니다. 회복 시 "
                f"단계적으로 복귀합니다(수동 개입 불필요).")

    # ⑤ 과최적화 감시 — 야간 검증(PBO·DSR)이 콘솔에만 찍히고 사라지던 것을
    #    장부에 남겨 여기서 읽는다. PBO는 'IS 1등이 OOS에서 동전던지기일 확률'
    #    이라 0.5를 넘으면 백테스트 우위가 과적합일 가능성이 높다는 뜻이다.
    #    (예전에는 아무도 안 쓰는 ma_cross를 검증하고 있었다 — 2026-08-11 수정)
    for key, r in (status.get("validation") or {}).items():
        pbo = r.get("pbo")
        if pbo is not None and float(pbo) > 0.5:
            flags[f"overfit:{key}"] = (
                f"⚠️ 과최적화 의심: {key}({r.get('strategy')}) PBO "
                f"{float(pbo) * 100:.0f}% — 백테스트 1등이 실전에서 동전던지기일 "
                f"확률입니다. 파라미터 탐색을 줄이거나 표본을 늘려야 합니다.")
        dsr = r.get("dsr")
        if dsr is not None and float(dsr) < 0.95:
            flags[f"dsr_low:{key}"] = (
                f"⚠️ 실력 미확인: {key}({r.get('strategy')}) DSR "
                f"{float(dsr):.2f} — 다중검정 보정 후 '운이 아니다'라고 말할 "
                f"신뢰도(0.95)에 못 미칩니다.")
        # 파라미터가 '외딴 봉우리'인가(감사 157). PBO·DSR이 "이 **성적**이
        # 운인가"를 묻는다면 이건 "이 **파라미터**가 운인가"를 묻는다 —
        # 옆칸으로 한 스텝만 옮겨도 무너지는 설정은 데이터가 조금만 달라져도
        # 무너진다. 지표가 셋 다 통과해도 이건 따로 걸릴 수 있다.
        # ⚠️ **돌지 못한 검증은 통과가 아니다**(감사 249). 위 두 규칙은
        #    `is not None`으로 시작해서, 값이 없는 항목에 대해 **아무 말도
        #    안 했다.** 리포트 페이지는 같은 상황을 이미 "판정 불가 — 돌지
        #    못한 검증이 있음"이라고 쓰고 있었다(감사 52). 같은 사실을
        #    한 화면은 말하고 다른 화면은 침묵했다.
        #
        #    실측(2026-08-15 장부): crypto:BTC/USDT는 DSR이 null인데(봉 300개
        #    — 표본 부족) 사이트에는 PBO 경보만 떴다. 읽는 사람은 나머지가
        #    통과한 줄로 읽는다.
        why = r.get("skipped") or {}
        def _unmeasured(k, _r=r):
            return _r.get(k) is None        # 0.0은 '못 쟀다'가 아니라 '측정된 0'

        missing = [k for k in ("dsr", "pbo") if _unmeasured(k)]
        if missing:
            names = {"dsr": "DSR(다중검정 보정)", "pbo": "PBO(과적합 확률)"}
            detail = " · ".join(
                f"{names[k]}: {why.get(k) or '이유 미기록'}" for k in missing)
            flags[f"validation_missing:{key}"] = (
                f"⚠️ 판정 불가: {key}({r.get('strategy')}) — 검증 "
                f"{len(missing)}종이 돌지 못했습니다({detail}). "
                f"통과가 아니라 **재지 못한 것**입니다 — 다른 지표가 초록이어도 "
                f"이 종목은 아직 검증되지 않았습니다.")

        if r.get("peak_only"):
            flags[f"lonely_peak:{key}"] = (
                f"⚠️ 외딴 봉우리 의심: {key}({r.get('strategy')}) — 원점수 1등과 "
                f"이웃 평균 1등 파라미터가 다릅니다. 그 설정은 파라미터를 한 "
                f"칸만 옮겨도 무너질 수 있습니다.")

    # ⑥ 피처 유실 — 외부 소스(야후·바이낸스·FRED·KRX)가 죽으면 피처가
    #    조용히 줄어드는데 장부에는 같은 fs8로 기록된다. 그러면 판정 시계가
    #    매일 다른 구조를 재게 된다(2026-08-11 발견). 어느 소스가 통째로
    #    빠졌는지 알린다 — 한 종목만 빠진 것은 시장 차이라 경보하지 않는다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        fh = (hist[-1].get("feature_health") if hist else None) or {}
        gone = fh.get("missing_everywhere") or []
        if gone:
            flags["features_missing:" + ",".join(sorted(gone))] = (
                f"⚠️ 피처 유실: {len(gone)}개가 전 종목에서 빠졌습니다 "
                f"({', '.join(gone)}). 외부 데이터 소스 장애일 가능성이 큽니다 — "
                f"장부에는 같은 구조 태그로 기록되지만 모델은 다른 피처로 "
                f"학습·판단합니다.")

    # ⑦ 새벽 배치 부분 실패 — '전 종목 실패'만 예외로 올리던 탓에 20종목 중
    #    19개가 실패한 날도 잡은 초록이었다(2026-08-11 발견). 실패한 종목은
    #    그날 판단·기록이 통째로 없고 옛 챔피언을 그대로 쓴다.
    for kind, r in (status.get("run_health") or {}).items():
        n = int(r.get("failed") or 0)
        if not n:
            continue
        keys = ", ".join((r.get("failed_keys") or [])[:5])
        more = "…" if len(r.get("failed_keys") or []) > 5 else ""
        err = next(iter((r.get("errors") or {}).values()), "")
        label = {"paper": "페이퍼", "retrain": "재학습"}.get(kind, kind)
        flags[f"run_failed:{kind}:{r.get('date')}:{n}"] = (
            f"⚠️ {label} 부분 실패: {r.get('date')} {n}종목 실패 "
            f"(성공 {r.get('ok')}) — {keys}{more}. "
            f"실패 종목은 그날 기록이 없고 이전 판단을 그대로 씁니다."
            + (f"\n첫 오류: {err}" if err else ""))

    # ⑦-② 며칠째 건너뛰는 종목 — 멱등 가드는 '새 봉이 없으면 조용히
    #      건너뛴다'라서, 시세 공급이 얼어붙어도 주말과 똑같이 침묵한다.
    #      그동안 챔피언은 재검증 없이 계속 돈을 굴린다(감사 226).
    #      주말·연휴로 설명되는 정체는 애초에 stale에 담기지 않는다 —
    #      매일 울리는 경보는 꺼진 경보와 같기 때문이다(감사 99).
    for kind, r in (status.get("run_health") or {}).items():
        stale = r.get("stale") or {}
        if not stale:
            continue
        label = {"paper": "페이퍼", "retrain": "재학습"}.get(kind, kind)
        worst = int(r.get("max_stale_days") or max(stale.values()))
        # 배치마다 세는 단위가 다르다(감사 243) — 재학습은 달력 일수, 페이퍼는
        # 거래일. 화면이 단위를 지어내면 주말 이틀이 '이틀 장애'로 읽힌다.
        unit = str(r.get("stale_unit") or "일")
        names = ", ".join(f"{k}({v}{unit})" for k, v in
                          sorted(stale.items(), key=lambda kv: -kv[1])[:5])
        flags[f"run_stale:{kind}:{r.get('date')}:{len(stale)}"] = (
            f"⚠️ {label} 정체: {len(stale)}종목이 최장 {worst}{unit}째 새 봉을 "
            f"받지 못해 건너뛰고 있습니다 — {names}. 주말·연휴로는 설명되지 "
            f"않는 간격이라 시세 공급 장애일 가능성이 큽니다. 건너뛴 종목은 "
            f"오디션을 한 번도 열지 못한 채 옛 챔피언으로 계속 운용됩니다.")

    # ⑦-③ 공회전 오디션 — 후보가 링에 오르긴 했는데 **전부 챔피언과 같은
    #      신호**를 낸 날. 장부에는 "후보 19개"라고 적히고 사이트에는 오디션이
    #      정상 진행된 것처럼 보이지만, 실제로는 아무것도 비교하지 못했다.
    #      실측(2026-08-14): 코인 5종목은 스냅샷이 300봉인데 선발 구간이
    #      180봉이라 챔피언(학습창 250봉)이 한 번도 학습하지 못했고, 후보
    #      19개 중 18개가 신호 0이었다. '이긴 후보가 없다'(정상)와
    #      '비교를 못 했다'(고장)를 화면에서 구별하기 위한 경보다.
    vac = [r for r in (status.get("retrain_recent") or []) if r.get("vacuous")]
    if vac:
        day = max((r.get("asof") or "") for r in vac)
        today = [r for r in vac if (r.get("asof") or "") == day]
        names = ", ".join(str(r.get("key")) for r in sorted(
            today, key=lambda r: str(r.get("key")))[:5])
        more = "…" if len(today) > 5 else ""
        flags[f"audition_vacuous:{day}:{len(today)}"] = (
            f"⚠️ 오디션 공회전: {day} {len(today)}종목에서 후보 대부분이 "
            f"챔피언과 **같은 신호**를 냈습니다 — {names}{more}. 대결이 성립하지 "
            f"않았으므로 그날의 '챔피언 유지'는 검증 결과가 아닙니다. "
            f"데이터가 짧아 학습창·워밍업을 못 채웠을 가능성이 큽니다.")

    # ⑧ 종목 스킵 — 데이터 장애로 빠진 종목은 그날 관망(포지션 유지)이라
    #    조용히 지나간다. 하지만 20종목 중 다섯만 남은 날은 '20종목 분산'이
    #    아니라 5종목 집중이고, 그건 완전히 다른 위험이다(2026-08-11).
    #    소수 스킵(휴장·상장폐지 등)은 정상이라 1/4 이상일 때만 알린다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        ch = (hist[-1].get("champion") if hist else None) or {}
        gone = ch.get("skipped") or []
        planned = int(ch.get("planned") or 0) or (len(gone) + int(ch.get("symbols") or 0))
        if not gone or not planned or len(gone) * 4 < planned:
            continue
        why = ch.get("skipped_why") or {}
        first = next(iter(why.values()), "")
        flags[f"symbols_skipped:{hist[-1].get('date')}:{len(gone)}"] = (
            f"⚠️ 종목 스킵 과다: {planned}종목 중 {len(gone)}개가 빠져 "
            f"{int(ch.get('symbols') or 0)}종목으로 운용했습니다 "
            f"({', '.join(gone[:5])}{'…' if len(gone) > 5 else ''}). "
            f"분산이 계획보다 얕아진 날입니다 — 데이터 소스 장애일 수 있습니다."
            + (f"\n첫 사유: {first}" if first else ""))

    # ⑨ 데이터 품질 — 무결성 위반(중복·음수가격·OHLC 모순)은 그 종목을
    #    아예 스킵시키므로 여기 오지 않는다. 여기서 보는 것은 '사람이 맥락으로
    #    판단할' 스파이크다: 하루 ±20%가 넘는 봉이 갑자기 늘면 분할·배당
    #    미조정일 가능성이 크고, 그러면 수익률이 통째로 거짓이 된다.
    #    (품질 검사 자체가 수동 백테스트에서만 돌던 것을 2026-08-11에
    #     새벽 배치로 옮겼다 — 정작 매매하는 쪽이 검사받지 않고 있었다.)
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        dq = (hist[-1].get("data_quality") if hist else None) or {}
        spikes = int(dq.get("spikes") or 0)
        if spikes <= 0:
            continue
        prev = [int(((r.get("data_quality") or {}).get("spikes") or 0))
                for r in hist[-8:-1]]
        base = max(prev) if prev else 0
        if spikes > max(3, base * 2):
            flags[f"data_spikes:{hist[-1].get('date')}:{spikes}"] = (
                f"⚠️ 가격 스파이크 급증: 전 종목 합계 {spikes}건 "
                f"(최근 기준 {base}건) — 하루 ±20% 넘는 봉이 갑자기 늘었습니다. "
                f"분할·배당 미조정일 가능성이 크고, 그렇다면 수익률 계산이 "
                f"통째로 어긋납니다. 해당 종목의 원본 시세를 확인하세요.")

    # ⑩ 판정 시계 — 새 구조 세대 시작(리셋)과 90일 만료는 각각 한 번만 알린다
    gen = status.get("generation")
    if gen:
        fs, days, target = gen["feature_set"], gen["days"], gen["target_days"]
        flags[f"generation:{fs}"] = (
            f"🕰 판정 시계 리셋: 새 구조({fs}) 관찰 {days}일차/{target}일 "
            f"({gen['since']}~). 이전 구조 기록은 아카이브로 분리됐고, "
            f"엣지 판정은 시계가 다 돌 때까지 유보합니다.")
        if days >= target:
            flags[f"generation_done:{fs}"] = (
                f"🎯 판정 시계 만료: 구조({fs}) 관찰 {days}일 완료 — "
                f"엣지 유무를 통계로 판정할 때가 됐습니다.")
    return flags


def check_and_notify_flags(status: dict, state_dir: str = "state",
                           today: str | None = None) -> list[str]:
    """새로 켜진 플래그만 알림 발송하고 현재 집합을 저장한다. 반환: 새 키들."""
    from quant.utils.jsonio import atomic_write_json

    path = os.path.join(state_dir, "flag_state.json")
    prev: set[str] = set()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                prev = set(json.load(f).get("flags") or [])
        except (OSError, ValueError):
            prev = set()
    cur = _current_flags(status, today)
    new = [k for k in cur if k not in prev]
    # 전송에 실패한 경보는 '보냈다'로 적지 않는다 — 적으면 다음 실행부터
    # '이미 켜져 있던 플래그'로 분류돼 **영원히 다시 오지 않는다**. 웹훅이
    # 한 번 죽은 날 하필 킬스위치가 발동하면 그 사실을 끝내 모르게 된다
    # (2026-08-11 감사에서 발견). 실패분은 빼 두고 다음 실행에 다시 시도한다.
    failed: set[str] = set()
    if new:
        from quant.live.notifications import get_notifier
        notifier = get_notifier()
        for k in new:
            if notifier.send(cur[k]) is False:   # None(구식 구현)은 성공 취급
                failed.add(k)
    atomic_write_json(path, {"flags": sorted(set(cur) - failed)})
    return [k for k in new if k not in failed]
