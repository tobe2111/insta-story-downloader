"""사이트용 상태 문서(`docs/status.json`)를 짓는 자리 (2026-11-10 감사 379).

`quant/live/daily.py`가 4,500줄이었다 — 계좌를 굴리는 일과 화면에 실을 문서를 짓는
일이 한 파일에 있었다. 대기업급 구조로 가는 첫 걸음으로 **문서 짓기**를 떼어 냈다.
동작은 한 글자도 안 바꿨다(옮기기만 했다). `quant.live.daily.write_docs_status`는
그대로 쓸 수 있다(재수출).
"""
from __future__ import annotations

import json
import os

from quant.live.retrain import STATE_DIR
from quant.utils.logging import get_logger

log = get_logger("daily_paper")     # 옮기기 전과 같은 로거 이름


def write_docs_status(state_dir: str = STATE_DIR,
                      docs_path: str = os.path.join("docs", "status.json")) -> dict:
    """state/의 챔피언·페이퍼 기록을 사이트용 status.json 하나로 모은다.

    docs/는 push 때마다 Cloudflare Pages로 자동 배포되므로, 이 파일을 커밋하면
    사용자는 웹사이트만 열어도 매일의 결과를 본다(프로그램 실행 불필요).
    """
    # 장부 계산은 daily가 맡는다 — 부를 때 읽어야 daily에 건 패치·재수출이 그대로 통한다.
    from quant.live.daily import (  # noqa: PLC0415
        GOAL_KRW, PORTFOLIO_START_CASH, START_CASH, _generation_archive, _generation_info,
        _regime_breakdown, chrono, holdings_view, ledger_files, max_drawdown_from_index,
        pending_deposits, principal_of, time_weighted_return, twr_index, weekly_archive,
    )
    from quant.utils.jsonio import atomic_write_json

    status: dict = {"champions": {}, "paper": {}, "updated": None, "swaps": [],
                    "retrain_recent": [],
                    # 유튜브 라이브 주소 — 저장소 변수(QUANT_LIVE_URL)를 설정하면
                    # 사이트에 '라이브 보러가기' 버튼이 자동으로 나타난다
                    "live_url": os.getenv("QUANT_LIVE_URL") or None}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for line in lines[-400:]:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("promoted"):
                # 사이트 차트의 '챔피언 교체' 마커용 — 진화의 서사를 새긴다
                status["swaps"].append({
                    "date": rec.get("asof"),
                    "key": f"{rec.get('market')}:{rec.get('symbol')}",
                    "strategy": rec.get("champion_strategy")})
        for line in lines[-120:]:
            # 탈락자 아카이브 — 몇 명이 도전해 몇 명이 떨어졌는지 그대로 공개.
            # 다중검정 정직성(운 좋은 승자를 얼마나 걸렀는가)의 시각화 재료.
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            status["retrain_recent"].append({
                "asof": rec.get("asof"),
                # ⚠️ **밤의 열쇠** — `asof`는 그 종목의 마지막 봉 날짜다.
                #    이 목록을 '그날 오디션'으로 묶어 읽는 화면이 둘 있는데
                #    (공개 SNS 카드 · 공회전 경보), `asof`로 묶으면 매일 봉이
                #    생기는 코인만 잡히고 주식은 금요일에 멈춰 빠진다.
                #    실측(2026-09-01, 최근 120줄): 8/29 카드가 후보 247명을
                #    발표했는데 그 밤 실제는 1,183명이었고, 8/28은 반대로
                #    한 칸에 네 밤이 섞여 1,332명이 2,283명으로 부풀었다.
                #    옛 줄에는 이 칸이 없다(그때는 안 남겼다) — 읽는 쪽이
                #    `asof`로 되돌아간다. 과거 기록은 고치지 않는다.
                "night": rec.get("night"),
                "key": f"{rec.get('market')}:{rec.get('symbol')}",
                "promoted": bool(rec.get("promoted")),
                "n_candidates": rec.get("n_candidates"),
                # 공회전 표식 — 후보 대부분이 챔피언과 같은 신호라 대결이
                # 성립하지 않은 날. 이게 없으면 '이긴 후보가 없었다'(정상)와
                # '아무것도 비교하지 못했다'(고장)가 화면에서 같아 보인다.
                "vacuous": bool(rec.get("vacuous")),
                "inert": len(rec.get("inert_candidates") or []),
                "trials_total": rec.get("trials_total")})
    champ_file = os.path.join(state_dir, "champions.json")
    if os.path.exists(champ_file):
        with open(champ_file, encoding="utf-8") as f:
            status["champions"] = json.load(f)

    # 실효 독립 베팅 수 — 2026-08-18 외부 검토 ①: "종목 수가 아니라
    # 실제로 몇 개의 독립 베팅인지 공개하라". 진단 전용이며 사이징에는
    # 반영하지 않는다(구조 동결). 실패는 None — 진단이 기록을 막으면 안 된다.
    try:
        from quant.risk.effective_bets import effective_bets
        status["diversification"] = effective_bets(state_dir)
    except Exception:  # noqa: BLE001
        status["diversification"] = None

    # 시장 민감도(감사 331, 2026-10-01 사장님 질문 "시황만 따라가는 것
    # 아니냐") — 계좌마다 지수에 얼마나 따라 움직였나와, 그 몫을 뺀 성적.
    # 표시 전용이다(매매 판단은 이 값을 읽지 않는다). 실패는 None.
    try:
        from quant.reporting.market_beta import market_beta_public
        status["market_beta"] = market_beta_public(state_dir)
    except Exception:  # noqa: BLE001
        status["market_beta"] = None

    # 현금이 남는 이유 · 넘친 예산 재분배 그림자(감사 332). 실패는 None.
    try:
        from quant.live.budget_shadow import budget_shadow_public
        status["budget_shadow"] = budget_shadow_public(state_dir)
    except Exception:  # noqa: BLE001
        status["budget_shadow"] = None

    # 엔진 자동 선택(감사 341) — 지금 엔진을 누가·왜 골랐나. 실패는 None.
    try:
        from quant.portfolio.engine_select import public as engine_select_public
        status["engine_select"] = engine_select_public(state_dir)
    except Exception:  # noqa: BLE001
        status["engine_select"] = None

    try:
        from quant.live.engine_shadow import engine_shadow_public
        status["engine_shadow"] = engine_shadow_public(state_dir)
    except Exception:  # noqa: BLE001
        status["engine_shadow"] = None

    # 저명 투자자 13F(감사 331, 사장님: "홈페이지 각 페이지들에 보여야 해")
    # — 모든 페이지가 이 한 칸을 읽는다. 수집 상태도 함께 싣는다.
    try:
        from quant.reporting.guru13f import guru13f_public
        status["guru13f"] = guru13f_public(state_dir)
    except Exception:  # noqa: BLE001
        status["guru13f"] = None

    # 배분 사다리(2026-08-19) — 같은 신호에 배분 방법만 바꾼 가상 계좌들.
    # 상대 비교 전용 실험이라 본 계좌 판정에는 쓰지 않고, 주의 문구가
    # 요약(note)에 함께 실린다. 실패는 None — 실험이 기록을 막으면 안 된다.
    try:
        from quant.live.alloc_ladder import ladder_public
        status["alloc_ladder"] = ladder_public(state_dir)
    except Exception:  # noqa: BLE001
        status["alloc_ladder"] = None

    # 실험 판정 기준의 사전 등록(2026-08-19) — 골대 이동 방지. 판정일·통계·
    # 문턱이 데이터보다 먼저 공개돼 있어야 몇 달 뒤의 판정이 의심받지 않는다.
    try:
        from quant.live.gen2 import gen2_public
        status["gen2"] = gen2_public(state_dir)
    except Exception:  # noqa: BLE001
        status["gen2"] = None
    try:
        from quant.live.diversity_shadow import diversity_public
        status["diversity_shadow"] = diversity_public(state_dir)
    except Exception:  # noqa: BLE001
        status["diversity_shadow"] = None
    try:
        from quant.live.breadth import breadth
        status["breadth"] = breadth(state_dir)
    except Exception:  # noqa: BLE001 — 계측기가 배치를 못 죽인다
        status["breadth"] = None
    try:
        from quant.live.sequential import sequential_status
        status["sequential"] = sequential_status(state_dir)
    except Exception:  # noqa: BLE001 — 진도 표시가 배치를 못 죽인다
        status["sequential"] = None
    try:
        from quant.live.prereg import public as _prereg_public
        status["prereg"] = _prereg_public()
        # 감사 361 — 판정일이 지난 실험은 기계가 한 번 판정하고 얼린다(사람이 안 잊게).
        try:
            from quant.live.final_judgement import judge_due
            status["prereg"]["final"] = judge_due(state_dir)
        except Exception as exc:  # noqa: BLE001 — 판정 실패가 배치를 죽이지 않는다
            status["prereg"]["final_error"] = str(exc)[:200]
        # 감사 376 — 판정 재료가 앞에서 잘리지 않는가(회차 수 한도 vs 날짜 창).
        try:
            from quant.live.prereg_coverage import coverage as _prereg_coverage
            status["prereg"]["coverage"] = _prereg_coverage(state_dir)
        except Exception as exc:  # noqa: BLE001 — 감시 실패가 배치를 죽이지 않는다
            status["prereg"]["coverage_error"] = str(exc)[:200]
    except Exception:  # noqa: BLE001
        status["prereg"] = None

    # 무제약 그림자 — "제약을 다 풀면?"에 대한 실측 답. 주의 문구(note)가
    # 요약에 함께 실리고 화면이 그대로 읽는다.
    try:
        from quant.live.unshackled import unshackled_public
        status["unshackled"] = unshackled_public(state_dir)
    except Exception:  # noqa: BLE001
        status["unshackled"] = None

    # 수동 킬스위치 상태 — 사장님이 멈춘 날의 공백이 고장처럼 보이지 않게,
    # "왜 기록이 없는지"를 사이트가 말할 수 있는 재료를 싣는다.
    try:
        from quant.live.manual_halt import status as _halt_status
        status["manual_halt"] = _halt_status(state_dir)
    except Exception:  # noqa: BLE001
        status["manual_halt"] = None

    pf_state = None                       # 통합 계좌 원본(세대별 분해 재료)
    # ⚠️ 보관본을 빼지 않으면 같은 키를 **덮어쓴다**(감사 212).
    #    `portfolio_ALL.pre-krw.json`이 알파벳순으로 뒤라, 새 원화
    #    계좌를 열었는데 사이트는 닫힌 옛 계좌를 계속 보여줬다.
    for path in ledger_files(state_dir):
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if st.get("market") == "portfolio":
            pf_state = st
        hist = chrono(st.get("history", []))   # 사이트 차트도 시간순으로
        key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        # 최대낙폭(MDD) — 수익률만 보여주는 화면은 반쪽짜리 정직이다.
        # 킬스위치와 같은 기준(입금 효과 제거)으로 잰다 — 화면과 브레이크가
        # 다른 숫자를 보면 사장님이 보는 낙폭과 시스템이 반응하는 낙폭이
        # 어긋난다(2026-08-11).
        mdd = max_drawdown_from_index(twr_index(
            hist, st.get("deposits") or [],
            start_cash=float(st.get("start_cash", START_CASH))))
        status["paper"][key] = {
            "start_cash": st.get("start_cash", START_CASH),
            "equity": (hist[-1]["equity"] if hist else st.get("cash")),
            "return_pct": (hist[-1].get("return_pct") if hist else 0.0),
            "mdd_pct": round(mdd * 100, 2),
            "history": hist[-90:],            # 사이트에는 최근 90일이면 충분
        }
        # 규칙 유니버스에서 빠진 종목 표식(2026-08-18) — 장부는 남기되,
        # "왜 이 종목만 기록이 멈췄나"가 고장으로 읽히지 않게 사실을 싣는다.
        try:
            from quant.universe import active_targets
            _act = {f"{m}:{s}" for m, s in active_targets(state_dir)}
            if st.get("market") != "portfolio" and key not in _act:
                status["paper"][key]["universe_excluded"] = True
        except Exception:  # noqa: BLE001
            pass
        if st.get("market") == "portfolio":   # 100만 챌린지(100만원 → 1억) 필드
            deposits = st.get("deposits", [])
            sc = float(st.get("start_cash", PORTFOLIO_START_CASH))
            # 자산과 **같은 시점의** 원금만 쓴다(감사 211). 아직 배치가
            # 반영하지 않은 입금을 더하면 그 금액이 그대로 손실로 보인다.
            principal = principal_of(sc, deposits)
            eq_now = float(status["paper"][key]["equity"] or principal)
            status["paper"][key].update({
                "goal": GOAL_KRW,
                "principal": round(principal, 2),
                "pnl": round(eq_now - principal, 2),
                "twr_pct": time_weighted_return(hist, deposits,
                                                start_cash=sc),
                "deposits": deposits[-30:],
            })
            # 접수됐지만 아직 반영 안 된 입금 — 숨기지 않고 밝힌다.
            # 이게 없으면 "92만원 넣었는데 화면이 그대로다"가 된다.
            waiting = pending_deposits(deposits)
            if waiting:
                status["paper"][key]["pending_deposits"] = waiting
            # 계좌를 다시 연 사실 — 사이트 제목이 이걸 읽어 "언제 왜
            # 새로 시작했는지"를 스스로 말한다(감사 212). 안 내보내면
            # 첫 화면이 옛 이야기를 계속 한다.
            if st.get("restarted"):
                status["paper"][key]["restarted"] = st["restarted"]
            # 거래내역 — "언제 얼마에 얼마어치를 샀나". 잔고가 '지금'을
            # 말한다면 이쪽은 '어떻게 여기까지 왔나'를 말한다(증권사도
            # 잔고와 거래내역을 따로 둔다). 기록마다 흩어져 있는 체결을
            # 한 줄로 펴서 최근 것부터 싣는다.
            trades = []
            for rec in reversed(hist):
                for _i, f in enumerate(rec.get("fills") or []):
                    # ⚠️ 체결이 **그 기록 안 몇 번째인가**를 함께 싣는다. 같은
                    #    날 같은 종목을 두 번 팔 수도 있으므로 날짜와 종목만
                    #    으로는 줄을 특정할 수 없다 — 실현 손익을 엉뚱한 줄에
                    #    붙이면 그 표는 증거가 아니라 이야기가 된다.
                    trades.append({**f, "date": rec.get("date"),
                                   "fill_index": _i})
                if len(trades) >= 60:
                    break
            if trades:
                # 판 시점의 손익 — 사장님 요청(2026-08-22). 장부에 적지 않고
                # **되짚어 계산한다**: 지난 매도에는 평균 매입가가 기록돼 있지
                # 않지만, 매수·매도가 전부 남아 있으므로 처음부터 따라가면
                # 복원된다. 기록은 한 글자도 고치지 않는다.
                #
                # ⚠️ 되짚기는 **전체 기록**을 봐야 한다. 최근 60건만 보면
                #    그 앞의 매수를 못 보고 평균 단가가 통째로 틀린다.
                from quant.live.realized import attach_realized
                status["paper"][key]["trades"] = attach_realized(
                    trades[:60], hist)
            # 종목별 잔고 — 사이트는 비중(%)만 보여주고 있었다. "삼성전자에
            # 얼마"에 답하려면 평단·수량·평가금액이 있어야 한다(2026-08-13).
            # 현금까지 함께 내보내야 합이 자산과 맞아떨어진다.
            status["paper"][key]["currency"] = st.get("currency")
            # 마지막 기록에 남은 적용 환율 — 잔고 표가 "1,412.5원/$ 적용"
            # 이라고 밝힐 수 있어야 검산이 가능하다(감사 216).
            if hist and hist[-1].get("fx_usdkrw") is not None:
                status["paper"][key]["fx_usdkrw"] = hist[-1]["fx_usdkrw"]
            status["paper"][key]["holdings"] = holdings_view(st, eq_now)
            # ⚠️ 현금도 **자산과 같은 시점**이어야 한다(감사 211이 여기서
            #    한 번 더 나온다). 장부의 cash에는 아직 반영 안 된 입금이
            #    이미 들어 있어서, 그대로 실으면 표의 합이 자산을 넘어선다:
            #        보유 37,341 + 현금 961,910 = 999,251  ≠  자산 79,251
            #    현금 비중이 1213%로 찍히고 표가 스스로 모순된다.
            #    접수분은 빼고 싣는다 — 그 돈은 pending_deposits로 따로
            #    공개되고, 다음 배치가 자산·현금을 함께 다시 잰다.
            status["paper"][key]["cash"] = round(
                float(st.get("cash") or 0.0)
                - sum(float(d["amount"]) for d in waiting), 2)
            rb = _regime_breakdown(hist)
            if rb:                             # 레짐별 성과 분해(투명성)
                status["paper"][key]["regime_breakdown"] = rb
        if hist:
            status["updated"] = max(status["updated"] or "", hist[-1]["date"])

    # ── 판정이 났으면 **그 자리에서 적용한다**(감사 315) ────────────────
    #
    # 예전에는 판정을 화면에 그리는 데서 끝났고, 실제 조정은 사람이 코드를
    # 고쳐서 했다. 사장님 지시(2026-08-25, "판정을 하면 너가 조정하는 게
    # 아니라 머신러닝측에서 하게끔")로 그 자리를 없앴다. 조치는 결과를 보기
    # **전에** 등록해 둔 것만 걸리고, 되돌리기 어려운 일은 자동으로 하지
    # 않는다(quant/live/adopt.py).
    #
    # ⚠️ 여기 두는 이유: `status["updated"]`(= 마지막 장부 날짜)가 정해진
    #    뒤여야 한다. 앞에 두면 채택 시각을 적을 수 없다 — 처음에 그렇게
    #    썼다가 `bar`라는 없는 이름을 참조해 **매일 조용히 실패할** 뻔했다.
    # ⚠️ 실패해도 하루 기록을 막지 않는다. 다만 조용히 넘기지도 않는다 —
    #    무슨 일이 있었는지 status에 그대로 실린다.
    try:
        from quant.live.adopt import apply_verdicts
        from quant.live.adopt import public as _adopt_pub
        _res = apply_verdicts(state_dir,
                              now=str(status.get("updated") or ""),
                              status=status.get("sequential"))
        for _r in _res["applied"]:
            if _r.get("applied"):
                log.warning("🤖 판정 적용 — %s → %s = %s (%s)",
                            _r["key"], _r["knob"], _r.get("value"), _r["why"])
        for _r in _res["held"]:
            log.warning("🖐 판정이 났지만 자동 적용 대상이 아닙니다 — %s (%s)",
                        _r["key"], _r.get("reason"))
        status["adopted"] = _adopt_pub(state_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("판정 자동 적용 실패: %s", exc)
        status["adopted"] = {"error": str(exc)[:200]}

    # ── 굶는 종목 — 이어달리기가 한 종목을 계속 뒤로 미루고 있지 않은가 ──
    #
    # ⚠️ 한 밤의 '못 돈 종목'으로는 이걸 못 잡는다. 이어달리기는 **설계상**
    #    한 밤에 명단을 다 못 돌아서 그 값이 거의 매일 0이 아니다. 물어야 할
    #    것은 "오늘 다 돌았나"가 아니라 "이 종목이 마지막으로 심사받은 게
    #    언제인가"다(작업 #67이 남긴 숙제).
    try:
        from quant.live.retrain import audition_gaps
        status["audition_gap"] = audition_gaps(state_dir)
    except Exception as exc:                           # noqa: BLE001
        # 못 재는 것을 위반으로 세지 않는다 — 다만 못 쟀다고는 적는다.
        status["audition_gap"] = {"measured": False, "why": str(exc)[:200]}

    # 오늘의 시장 브리핑(표시 전용) — 있으면 사이트에도 싣는다
    from quant.live.briefing import load_briefing
    briefing = load_briefing(state_dir)
    if briefing and briefing.get("items"):
        status["briefing"] = briefing

    # 오늘의 거시(FRED, 표시 전용) — 키 없으면 조용히 생략
    try:
        from quant.live.macro_brief import macro_summary
        m = macro_summary()
        if m:
            status["macro"] = m
    except Exception:  # noqa: BLE001 — 브리핑 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 판정 시계 — 현재 구조 세대의 관찰 일수(구조가 바뀌면 0일부터 다시)
    gen = _generation_info(state_dir)
    if gen:
        # 세대별 기록 아카이브 — 이전 구조 기록을 현 구조 실적과 분리(착시 제거)
        if pf_state:
            arch = _generation_archive(pf_state, gen["since"])
            if arch:
                gen["archive"] = arch
        status["generation"] = gen

    # 새벽 배치의 부분 실패 — '전부 실패'만 예외로 올리던 탓에 절반이 마비된
    # 날도 초록으로 보였다. 실패는 숨길 이유가 없다(2026-08-11 감사).
    rh_path = os.path.join(state_dir, "run_health.json")
    if os.path.exists(rh_path):
        try:
            with open(rh_path, encoding="utf-8") as f:
                status["run_health"] = json.load(f)
        except (OSError, ValueError):
            pass

    # 주간 아카이브 — **셈은 배치가 하고 페이지는 읽기만 한다**(감사 246).
    # 페이지가 자기 복사본으로 계산하던 시절, 그 복사본은 "주간 수익률" 칸에
    # 그 주 **마지막 하루치**를 넣고 있었다(실측 +0.02% vs 사실 -0.02%).
    try:
        wk = weekly_archive(state_dir)
        if wk:
            status["weekly"] = wk
    except Exception:  # noqa: BLE001 — 집계 실패가 사이트 갱신을 막으면 안 된다
        log.warning("주간 아카이브 집계 실패 — 페이지는 '집계 없음'으로 표시된다")

    # 횡단면 증거 — **같은 설정이 몇 종목에서 통했나**(감사 260).
    # 종목별 오디션은 하루에 표본 1개를 쌓지만 이건 20개를 쌓는다. 실측에서
    # 주식(t=+4.37)과 코인(t=-1.76)이 반대 방향으로 갈렸는데, 종목마다 따로
    # 여는 오디션은 그 사실을 영영 볼 수 없다.
    try:
        from quant.live.crosssection import pooled_evidence
        xs = pooled_evidence(state_dir)
        if xs:
            status["crosssection"] = xs
    except Exception:  # noqa: BLE001 — 관찰 지표 실패가 사이트 갱신을 막지 않는다
        log.warning("횡단면 증거 집계 실패 — 이 칸은 비워 둔다")

    # 체결 가정 검증(표시 전용) — 실측 개장 갭 vs 백테스트 슬리피지 가정.
    # 실측이 가정보다 불리하면 그 사실이 그대로 사이트에 공개된다.
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            status["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 검증 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 장중 감시가 **실제로** 얼마나 자주 돌았나(감사 267). 예약값이 아니라
    # 심장박동에서 잰 값이다. 여기서 status에 실어 두는 이유: 경보를 만드는
    # 쪽(flag_watch)이 파일을 직접 읽으면 그 함수가 **저장소의 지금 상태에
    # 묶인다.** 실제로 그렇게 만들었다가, 감시 기록이 쌓이자 아무 상관 없는
    # 검사들이 "경보 없음"을 확인하지 못하고 무너졌다. 재료는 여기서 모으고
    # 판정은 저기서 한다 — 원래 이 파일들이 나눠 갖던 역할이다.
    try:
        from quant.live.guard import (GUARD_INTERVAL_MINUTES,
                                      observed_gap_median,
                                      observed_gap_minutes)
        _gap = observed_gap_minutes(state_dir)
        if _gap is not None:
            # 최악만 실으면 꼬리 하나가 전체를 설명한다 — 중앙값도 함께
            # 싣는다(감사 285). 한도 계산은 계속 최악값이다(안전 쪽).
            _mid = observed_gap_median(state_dir)
            status["guard"] = {"observed_gap_min": round(float(_gap), 1),
                               "interval_min": GUARD_INTERVAL_MINUTES}
            if _mid is not None:
                status["guard"]["median_gap_min"] = round(float(_mid), 1)
    except Exception:  # noqa: BLE001 — 감시 기록이 없어도 사이트는 갱신된다
        pass

    # 사용자 고정(pin) — 설치형 사용자가 심사와 무관하게 자기 전략을 지정한
    # 종목. 화면이 이 사실을 말하지 않으면, 그 성적이 시스템 심사의 결과처럼
    # 읽힌다(우리 공개 계좌에는 고정이 없어 이 칸은 비어 있다).
    try:
        from quant.live.pin import load_pins
        _pins = load_pins(state_dir)
        if _pins:
            status["pins"] = {k: {"name": v.get("name"),
                                  "since": v.get("since")}
                              for k, v in _pins.items()}
    except Exception:  # noqa: BLE001 — 고정 파일 문제로 사이트가 죽으면 안 된다
        pass

    # 야간 검증(PBO·DSR) 장부 — 과최적화 감시가 사이트·경보로 이어지게
    vpath = os.path.join(state_dir, "validation.json")
    if os.path.exists(vpath):
        try:
            with open(vpath, encoding="utf-8") as f:
                status["validation"] = json.load(f)
        except (OSError, ValueError):
            pass

    # 의석 현황 — "최대 3석 분산 운용"이 지금 실제인가(감사 225).
    # 사이트는 이 구조를 현재형으로 약속하고 있었는데 장부는 전 계좌 1석이다.
    # 판단한 쪽(재학습)이 숫자를 남기고 보여주는 쪽은 읽기만 한다 — 오늘 하루
    # 종일 나온 그 처방을 여기에도 적용한다.
    try:
        from quant.live.parliament import seat_census
        from quant.live.retrain import load_champions
        census = seat_census(load_champions(state_dir))
        if census["accounts"]:
            status["parliament"] = census
    except Exception:  # noqa: BLE001 — 표시 항목 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 증명 가능성 — "통과선을 넘으려면 무엇이 필요한가"(2026-08-19).
    # 검증이 처음 완주한 날 통과가 0종목이었다. 나쁜 결과일수록 숨기지 않고
    # **왜 그런지까지** 같은 자리에 싣는다 — 좋은 숫자만 남기는 편집이
    # 이 제품의 정체성을 무너뜨린다.
    try:
        from quant.live.provable import provability
        prov = provability(state_dir)
        if prov:
            status["provable"] = prov
    except Exception:  # noqa: BLE001 — 표시 항목 실패가 사이트 갱신을 막으면 안 된다
        pass
    # 개선 이력 자동 발행(2026-08-23, 사장님 지시) — "스스로 고치는 시스템"의
    # 증거를 홈페이지에 남긴다. 원본은 깃 커밋 이력이고 이 파일은 사본이다.
    # 얕은 체크아웃이면 발행하지 않는다(부분 이력이 전부로 읽힌다).
    try:
        from quant.reporting.changelog import write_changelog
        write_changelog(os.path.dirname(docs_path) or "docs")
    except Exception:  # noqa: BLE001 — 표시 항목 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 휴장일 달력 — **브라우저에도 보낸다**(2026-08-14). 사이트는 파이썬을
    # 못 돌리므로, 배치가 아는 것을 파일로 실어 보내지 않으면 화면은 영영
    # 주말만 아는 상태로 남는다. 그러면 명절 내내 15초마다 시세를 조르고
    # (무료 한도를 아무도 안 보는 날에 태우고), 값이 안 변하는 것이 휴장인지
    # 고장인지 보는 사람도 알 수 없다.
    # 앞으로 60일치만 보낸다 — status.json은 매번 통째로 내려받는 파일이다.
    try:
        from datetime import date as _hdate
        from datetime import timedelta as _htd

        from quant.data.market_calendar import holiday_map
        _hol = holiday_map(state_dir)
        if _hol:
            _from = _hdate.today().isoformat()
            _to = (_hdate.today() + _htd(days=60)).isoformat()
            status["holidays"] = {m: [d for d in days if _from <= d <= _to]
                                  for m, days in _hol.items()}
    except Exception:  # noqa: BLE001 — 표시 항목 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 종목 한글 이름·선정 이유 — 사이트가 코드 대신 이름을 보여줄 수 있게
    from quant.markets import SYMBOL_INFO
    status["symbols"] = SYMBOL_INFO

    atomic_write_json(docs_path, status)
    print(f"🌐 사이트 상태 갱신: {docs_path} (마지막 기록 {status['updated']})")

    # 플래그 파수꾼 — 새로 켜진 자기 고발 플래그(낙관 의심·보정 어긋남·
    # 판정 시계)를 알림 채널(디스코드 등)로도 발송한다. 이미 켜진 건 조용.
    try:
        from quant.live.flag_watch import check_and_notify_flags
        new_flags = check_and_notify_flags(status, state_dir)
        if new_flags:
            print(f"🚩 새 플래그 알림 발송: {', '.join(new_flags)}")
    except Exception:  # noqa: BLE001 — 알림 실패가 사이트 갱신을 막으면 안 된다
        pass
    return status
