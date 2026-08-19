"""통합 커맨드라인 인터페이스.

여러 예제 스크립트 대신 하나의 진입점으로 주요 기능을 실행한다:

    python -m quant backtest --strategy ma_cross --report results/r.html
    python -m quant sweep --market crypto --symbol BTC/USDT
    python -m quant web --port 8000
    python -m quant pipeline            # 백테스트+리포트+몬테카를로

무거운(pandas) 임포트는 각 명령 실행 시에만 일어나므로 --help는 즉시 뜬다.
"""
from __future__ import annotations

import argparse
import copy as _copy
import pathlib as _pathlib


def _data_note(df, market: str) -> str:
    """이 분석이 **어떤 데이터** 위에서 나왔는지 한 줄로 밝힌다 (감사 250).

    ⚠️ 표식은 예전부터 있었다 — `df.attrs["synthetic_fallback"]`. 그런데 그걸
       읽는 곳이 **설정 마법사 한 군데뿐**이었다. 분석 명령 다섯(백테스트·
       민감도·검증·비용·A/B)은 전부 무시했다.

       그 결과가 고약하다. 네트워크가 막힌 환경에서 시세 수집이 실패하면
       합성(지어낸) 가격으로 폴백하는데, 그 사실은 stderr 경고 한 줄로
       지나가고 **결과 본문은 진짜와 똑같이 생겼다.** 실측:

           2026-08-15 `quant costcheck` — 모든 거래소 실패 → 합성 폴백
             "수수료 0에서의 총수익률: 44.22%"
             "비교적 비용에 견고한 편이다."
           `quant backtest` — 같은 폴백
             "총수익률 33.44% · 샤프 2.10 · 승률 57.21%"

       지어낸 가격 위의 샤프 2.10이다. 사이트는 같은 사실을 "합성 데이터
       폴백 N종목 — 이 종목의 그날 기록은 실제 시장이 아닙니다"라고 크게
       말하고(감사 ㉜), 매매 경로는 아예 거부한다. **분석 도구만 조용했다.**

    `--market synthetic`은 사용자가 스스로 고른 연습용이라 말투가 다르다 —
    다만 백테스트의 기본 시장이 synthetic이므로 그 경우도 말한다.
    """
    if bool(getattr(df, "attrs", {}).get("synthetic_fallback")):
        return ("⚠️ 이 결과는 **합성(지어낸) 데이터**입니다 — 실제 시세를 받지 "
                "못해 폴백했습니다.\n"
                "   아래 숫자는 시장에서 일어난 일이 아닙니다. 전략 판단의 "
                "근거로 쓰지 마세요.")
    if market == "synthetic":
        return ("ℹ️ 연습용 모의 데이터입니다(--market synthetic) — 실제 "
                "시장이 아닙니다.")
    src = str(getattr(df, "attrs", {}).get("source") or "").strip()
    return f"📡 데이터: 실제 시세{f' · {src}' if src else ''}"


def _ppy(market: str) -> int:
    return 365 if market in ("crypto", "synthetic") else 252


def _cmd_backtest(args) -> None:
    from quant.backtest import Backtester
    from quant.data import get_provider
    from quant.strategies import default_ensemble, get_strategy

    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe, limit=args.limit)

    # 데이터 품질 스캔 — 무결성 위반이 있으면 경고만 출력한다 (비파괴, 실행은 계속).
    # 오염된 데이터 위의 백테스트는 그럴듯한 거짓말이 되므로 먼저 알려준다.
    print(_data_note(df, args.market))
    from quant.data.quality import is_severe, quality_report, scan_ohlcv
    findings = scan_ohlcv(df)
    if is_severe(findings):
        print("\n⚠️ 데이터 품질 경고 — 아래 항목을 확인한 뒤 결과를 해석하세요.")
        print(quality_report(df, findings))

    strat = default_ensemble() if args.strategy == "ensemble" else get_strategy(args.strategy)
    cost_model = None
    if args.market_costs:
        from quant.backtest.costs import CostModel
        cost_model = CostModel.for_market(args.market)
        print(f"💸 시장 비용 프리셋({args.market}): 수수료 {cost_model.fee:.4%} · "
              f"슬리피지 {cost_model.slippage:.4%} (편도, 근사)")
    result = Backtester(
        strat, periods_per_year=_ppy(args.market),
        cost_model=cost_model,
        rebalance_band=args.rebalance_band,
        stop_cooldown=args.stop_cooldown,
        dd_throttle=args.dd_throttle, dd_band=args.dd_band,
        intrabar_stops=args.intrabar_stops,
    ).run(df)
    print(f"\n=== {args.strategy} · {args.symbol} ({len(df)}봉) ===")
    print(result.summary())
    if args.report:
        from quant.reporting import generate_report
        out = generate_report(result, args.report, title=f"{args.strategy} · {args.symbol}")
        print(f"\n📄 리포트: {out}")
    print("⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.")


def _cmd_sweep(args) -> None:
    from quant.data import get_provider
    from quant.optimize import sensitivity_grid
    from quant.reporting import generate_heatmap
    from quant.strategies import MovingAverageCross

    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe, limit=args.limit)
    print(_data_note(df, args.market))
    fast, slow = [5, 10, 15, 20, 30, 40], [50, 60, 80, 100, 150, 200]
    grid = sensitivity_grid(df, MovingAverageCross, "fast", fast, "slow", slow,
                            objective=args.objective, periods_per_year=_ppy(args.market))
    out = generate_heatmap(fast, slow, grid, x_label="fast", y_label="slow",
                           objective=args.objective, path=args.out)
    print(f"📊 히트맵: {out}\n💡 넓은 초록 고원=견고, 외딴 점=과최적화")


def _cmd_web(args) -> None:
    from quant.web.server import run_server

    if getattr(args, "open", False):
        import threading
        import time
        import webbrowser

        url = f"http://{args.host}:{args.port}"

        def _open():
            time.sleep(1.5)
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_open, daemon=True).start()
    run_server(args.host, args.port)


def _cmd_learn(args) -> None:
    from quant.broker import PaperBroker
    from quant.data import get_provider
    from quant.live import AutoLearner
    from quant.risk import RiskManager
    from quant.strategies import default_ensemble, get_strategy

    if args.strategy == "champion":
        # 야간 재학습이 뽑은 현재 챔피언을 사용 — 승격되면 재시작 없이 자동 반영
        from quant.live.retrain import champion_spec, champion_strategy
        strat = champion_strategy(args.market, args.symbol)
        print(f"🏆 현재 챔피언 사용: {champion_spec(args.market, args.symbol)['params']}"
              " (야간 재학습이 교체하면 자동 반영됩니다)")
    elif args.strategy == "ensemble":
        strat = default_ensemble()
    else:
        strat = get_strategy(args.strategy)
    learner = AutoLearner(
        data=get_provider(args.market, cached=True),
        strategy=strat,
        broker=PaperBroker(cash=args.cash),
        risk=RiskManager(),
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback=args.lookback,
        accuracy_window=args.accuracy_window,
        state_path=args.state,
        # 시장을 넘겨야 미완결 봉을 뺄 수 있다(감사 151). 안 넘기면
        # 코인의 '오늘' 진행 중인 봉이 그대로 모델에 들어간다.
        market=args.market,
    )
    cycles = None if args.cycles <= 0 else args.cycles
    print(f"🔁 자동 페이퍼 학습 시작: {args.strategy} · {args.symbol} "
          f"(주기 {args.interval}s, {'무기한' if cycles is None else str(cycles)+'회'})")
    print("⚠️ 정확도는 50~55%에서 오르내립니다. 100%로 오르지 않습니다 — 그게 정상입니다.")
    print(f"📺 대시보드: python -m quant web --open  →  감시 탭에서 {args.state} 확인")
    learner.run(cycles=cycles, interval_sec=args.interval)


def _notify_extra(message: str) -> None:
    """텔레그램/슬랙이 환경변수로 설정돼 있으면 그 채널로만 알린다(콘솔 중복 방지).

    설정이 없으면 조용히 아무것도 안 한다 — 야간 자동화 잡에서 알림은 옵션이다.
    GitHub Secrets에 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID를 넣으면 켜진다.

    ⚠️ `QUANT_DEFER_NOTICE=1`이면 **보내지 않고 쌓아 둔다**(감사 283).
       배치는 ①계산 →②알림 →③장부 관문 →④커밋 순서인데, ③에서 죽으면
       ②는 이미 나간 뒤다. 2026-08-17 밤 실제로 그랬다 — 폰에는
       "자산 999,078원", "챔피언 교체 SPY·QQQ"가 남았는데 장부에는
       그런 일이 없다. 커밋이 끝난 뒤 `quant notify --flush`가 내보낸다.

       ⚠️ 그 판단은 **여기 있지 않다**(감사 287). 처음에는 여기 있었는데,
          알림이 나가는 길이 이 함수 하나가 아니었다 — 플래그 파수꾼은
          알림기를 직접 부른다. 같은 규칙이 두 곳에 있으면 반드시
          갈라진다(FROZEN_IDEAS ①). 이제 `get_notifier()`가 미루는 밤에
          바깥 채널 대신 대기열을 돌려주므로, 어느 길로 오든 한 문을 지난다.
    """
    try:
        from quant.live.notifications import ConsoleNotifier, get_notifier
        n = get_notifier()
        extra = [c for c in getattr(n, "notifiers", [])
                 if not isinstance(c, ConsoleNotifier)]
        for c in extra:
            c.send(message)
    except Exception as exc:  # noqa: BLE001 — 알림 실패가 본 작업을 죽이면 안 된다
        print(f"(알림 전송 실패: {exc})")


def _cmd_paper_daily(args) -> None:
    from quant.live.daily import (
        run_daily_paper, run_daily_paper_all, write_docs_status,
    )

    # 수동 킬스위치 — 사장님이 조종석에서 멈춰 둔 날은 아무 주문도 내지
    # 않고 장부도 건드리지 않는다. 다만 status.json은 갱신해서(스위치
    # 상태가 실린다) 사이트가 "왜 오늘 기록이 없는지"를 말할 수 있게 한다.
    from quant.live.manual_halt import gate_message
    _halt = gate_message(args.state_dir)
    if _halt:
        print(_halt)
        if args.docs:
            write_docs_status(args.state_dir)
        return

    common = dict(timeframe=args.timeframe, lookback=args.lookback,
                  state_dir=args.state_dir,
                  require_real_data=not args.allow_synthetic)
    # 규칙 유니버스 — 매월 1회 재계산(2026-08-18). 실패해도 배치를 막지
    # 않고 직전 구성이 유지된다(사유는 스냅샷에 기록).
    try:
        from quant.universe import due as _uni_due, rebuild as _uni_rebuild
        if _uni_due(args.state_dir):
            snap = _uni_rebuild(args.state_dir)
            print(f"🗺 규칙 유니버스 재계산 — {len(snap['targets'])}종목 "
                  f"(기준일 {snap['asof']})")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 유니버스 재계산 실패 — 직전 구성 유지: {exc}")

    if args.all:
        from quant.live.daily import run_daily_portfolio
        from quant.universe import active_targets as _uni_targets
        print(f"📅 매일 자동 페이퍼 — 전체 {len(_uni_targets(args.state_dir))}종목"
              " (챔피언 추종)")
        out = run_daily_paper_all(**common)
        lines = [f"  {k}: 자산 {r['equity']:,.0f} ({r['return_pct']:+.2f}%)"
                 for k, r in out["records"].items() if not r.get("skipped")]
        # ⚠️ 문턱 0.25는 대표본 관행이라 최근 60거래일 기준에는 맞지 않는다
        #    (감사 99). 드리프트가 없어도 29%가 넘긴다 — 그러면 경보가 매일
        #    울려서 진짜 신호와 구별되지 않는다. 같은 표본 크기의 귀무분포와
        #    견줘 등급을 매기고, 잣대도 함께 찍는다.
        from quant.live.daily import drift_grade, drift_reference
        drifted = [(k, r["drift_psi"], g)
                   for k, r in out["records"].items()
                   if (g := drift_grade(r.get("drift_psi")))
                   and "드리프트" in g]
        if drifted:
            ref = drift_reference()
            lines.append(
                f"  ⚠️ 드리프트 경보(표본 {ref['n_new']}일 기준 상위 5% = "
                f"PSI≥{ref['p95']}): "
                + ", ".join(f"{k} {v:.2f}({g})" for k, v, g in drifted)
                + " — 시장 분포가 학습 시점과 달라짐, 판단 신뢰도 주의")
        try:                                     # 통합 분산 계좌(실전과 가장 유사)
            prec = run_daily_portfolio(**common)
            if prec and not prec.get("skipped"):
                pct_txt = (f" · 무작위 1,000개 중 상위 "
                           f"{100 - prec['random_pctile']:.0f}%"
                           if prec.get("random_pctile") is not None else "")
                lines.append(f"  📦 통합 분산 계좌: 자산 {prec['equity']:,.0f} "
                             f"({prec['return_pct']:+.2f}%){pct_txt}")
                if float(prec.get("risk_scale", 1.0)) < 1.0:
                    lines.append(
                        f"  🛑 킬스위치 작동: 낙폭 {prec.get('drawdown_pct')}%"
                        f" → 총 노출 {float(prec['risk_scale']):.0%}로 제한"
                        " (회복 시 단계 복귀)")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 통합 포트폴리오 실패 — {exc}")
        try:
            # 섀도 대조군 — 진화(오디션) 없이 최초 기본 챔피언으로 고정한 계좌.
            # 오디션 시스템이 실제로 가치를 더하는지 증명하는 유일한 방법이다.
            srec = run_daily_portfolio(**common, use_champions=False,
                                       state_file="portfolio_SHADOW.json")
            if srec and not srec.get("skipped"):
                lines.append(f"  🕯 섀도(진화 없음): 자산 {srec['equity']:,.0f} "
                             f"({srec['return_pct']:+.2f}%)")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 섀도 대조군 실패 — {exc}")
        # 실패 알림은 lines가 비어도 나가야 한다 — 전 종목이 휴장·스킵이면
        # lines가 비는데, 예전에는 그때 실패 목록까지 함께 삼켜졌다.
        if lines or out["failed"]:
            _notify_extra("📅 100만 챌린지 오늘 기록\n" + "\n".join(lines)
                          + (f"\n⚠️ 실패 {len(out['failed'])}종목: "
                             f"{', '.join(out['failed'])}"
                             if out["failed"] else ""))
    else:
        print(f"📅 매일 자동 페이퍼: {args.market}/{args.symbol} (챔피언 전략 추종)")
        rec = run_daily_paper(args.market, args.symbol, **common)
        if rec and not rec.get("skipped"):
            _notify_extra(
                f"📅 페이퍼 {args.market}/{args.symbol} [{rec['date']}] "
                f"자산 {rec['equity']:,.0f} ({rec['return_pct']:+.2f}%) · "
                f"비중 {rec['weight']:+.2f}")
    if args.docs:
        write_docs_status(args.state_dir)
    # 사용 원격 측정 — **동의한 경우에만** 등록 전략·성과를 제작사로 보낸다
    # (2026-08-18, 약관 고지 기반). 동의 없으면 send()가 스스로 아무것도
    # 하지 않는다. 실패는 배치를 막지 않는다.
    try:
        from quant.telemetry import send as _tsend
        print(_tsend(args.state_dir))
    except Exception as exc:  # noqa: BLE001
        print(f"(텔레메트리 생략: {exc})")
    print("⚠️ 페이퍼(모의) 운용입니다 — 실제 돈이 오가지 않으며, "
          "결과가 좋아도 미래 수익 보장이 아닙니다.")


def _cmd_deposit(args) -> None:
    # ⚠️ **가벼운 쪽에서 가져온다**(2026-08-13). `quant.live.daily`에서
    #    부르면 매매 엔진 전체(numpy·pandas)가 딸려 와서, 의존성이 없는
    #    워크플로에서 입금이 통째로 죽는다 — 실제로 죽었다:
    #        ModuleNotFoundError: No module named 'numpy'
    #    입금 자체는 날짜·JSON·산술이 전부다. 감사 102와 같은 사고다.
    from quant.live.ledger_basics import add_deposit

    out = add_deposit(args.amount, args.memo, state_dir=args.state_dir)
    _notify_extra(f"💝 후원 매칭 입금 +{out['deposit']['amount']:,.0f}원 "
                  f"({out['deposit']['memo'] or '메모 없음'}) — "
                  f"누적 원금 {out['principal']:,.0f}원")
    print("⚠️ 후원금 자체를 굴리는 것이 아니라, 같은 금액만큼 가상 계좌 원금을 "
          "늘리는 '매칭' 이벤트입니다(대가·지분 없음).")


def _cmd_redenominate(args) -> None:
    """통합 계좌를 원화 계좌로 다시 연다 (감사 212) — 되돌릴 수 없다."""
    from quant.live.ledger_basics import redenominate_to_krw

    if not args.yes:
        print("⚠️ 통합 계좌를 닫고 원화 계좌를 새로 엽니다. 옛 장부는 "
              "portfolio_ALL.pre-krw.json 으로 그대로 보관되지만, 현재 "
              "보유·현금은 새 계좌로 이어지지 않습니다.")
        if input("계속하려면 '원화'를 입력하세요: ").strip() != "원화":
            print("취소했습니다.")
            return
    out = redenominate_to_krw(args.state_dir, args.principal,
                              state_file=args.state_file)
    _notify_extra(f"🔁 통합 계좌를 원화 기준으로 다시 열었습니다 — 원금 "
                  f"{out['start_cash']:,.0f}원 (감사 212: 해외 종목 환율 미반영)")


def _cmd_live_daily(args) -> None:
    """하루 1회 실거래 집행 — 기본 모의투자, 실전은 이중 안전장치."""
    if args.real:
        from quant.utils.dist import block_live_in_distribution
        block_live_in_distribution()     # 배포판: 실거래 금지(소스 설치 전용)
    from quant.live.daily_live import run_daily_live
    run_daily_live(paper=not args.real, state_dir=args.state_dir,
                   broker_name=args.broker)


def _cmd_live_check(args) -> None:
    """실거래 준비 진단 — 주문 없이 키·인증·잔고 확인."""
    from quant.live.daily_live import check_readiness
    print("\n🔍 실거래 전환 준비 진단"
          + (" (실전 도메인)" if args.real else " (모의투자 도메인)"))
    rows = list(check_readiness(paper=not args.real, broker_name=args.broker))
    ok_all = True
    for name, ok, note in rows:
        print(f"  {'✅' if ok else '❌'} {name}: {note}")
        ok_all = ok_all and ok
    # 점검 항목이 하나도 없으면 '전부 통과'가 아니라 '점검하지 못함'이다.
    # 빈 목록이 True로 남으면 아무것도 확인하지 않고 실거래를 허용한다.
    if not rows:
        print("  ❌ 점검 항목이 하나도 없습니다 — 진단이 돌지 않았습니다"
              f"(브로커 이름 확인: {args.broker!r})")
        ok_all = False
    if ok_all:
        print("\n✅ 준비 완료 — live-daily로 모의투자 리허설을 시작할 수 "
              "있습니다.")
        return
    # ⚠️ 종료코드로도 실패를 말한다(2026-08-11 감사 87). 예전에는 화면에만
    #    "미비 항목이 있습니다"를 찍고 0(성공)으로 끝냈다. 그런데 이 명령은
    #    kr-live 워크플로에서 **실거래 집행 바로 앞 단계**에 놓여 있다 —
    #    GitHub Actions는 단계가 실패해야 잡을 멈추므로, 0을 돌려주면
    #    키가 없거나 인증이 만료돼도 다음 단계가 그대로 실주문을 낸다.
    #    장치가 있고 이름도 '진단'이고 관문 자리에 있는데 막지 않았다.
    raise SystemExit(
        "\n❌ 미비 항목이 있습니다 — 'python -m quant setup'으로 키를 "
        "등록하세요.\n   (실거래 집행 앞 관문이므로 실패로 끝냅니다)")


def _cmd_live(args) -> None:
    """실시간 루프 — 야간 진화 챔피언을 실제 계좌에 반영한다 (기본은 페이퍼).

    안전 원칙:
      · 기본 모드는 페이퍼(가짜 돈). --real + 타이핑 확인을 모두 거쳐야 실전.
      · 실전은 안전장치가 기본으로 켜진다: 일일 손실 킬스위치, 최대낙폭
        서킷브레이커, 최대 비중 상한, 주식 장시간 가드, 견고 주문(재시도).
      · 챔피언 자동 추종: 야간 재학습이 챔피언을 교체하면 재시작 없이
        다음 사이클부터 새 전략이 적용된다 — '그 능력'이 실전에 이어진다.
    """
    from quant.utils.envfile import load_env_file
    load_env_file()                      # setup 마법사가 저장한 API 키 로드

    from quant.broker import RobustBroker, get_broker
    from quant.data import get_provider
    from quant.live import LiveTrader
    from quant.live.circuit_breaker import BreakerConfig, CircuitBreaker
    from quant.live.notifications import get_notifier
    from quant.markets import LIVE_BROKER_FOR_MARKET, SCHEDULED_MARKETS
    from quant.risk import RiskConfig, RiskManager

    data = get_provider(args.market)
    symbols = [s.strip() for s in (args.symbols or "").split(",") if s.strip()]
    if args.strategy == "champion":
        from quant.live.retrain import champion_spec, champion_strategy
        if symbols:
            # 다중 종목 — 종목마다 그 종목의 챔피언을 위임 실행(핫리로드 포함)
            strategy = lambda sym: champion_strategy(args.market, sym)  # noqa: E731
            for sym in symbols:
                spec = champion_spec(args.market, sym)
                print(f"챔피언({sym}): {spec['strategy']} {spec['params']}")
        else:
            strategy = champion_strategy(args.market, args.symbol)
            spec = champion_spec(args.market, args.symbol)
            print(f"챔피언 자동 추종: {spec['strategy']} {spec['params']}")
        print("   야간 재학습이 챔피언을 교체하면 재시작 없이 자동 반영됩니다.")
    else:
        from quant.strategies import get_strategy
        strategy = get_strategy(args.strategy)

    notifier = get_notifier()
    risk = RiskManager(RiskConfig(periods_per_year=_ppy(args.market),
                                  stop_loss=0.15,
                                  max_position=args.max_weight))

    if args.real:
        from quant.utils.dist import block_live_in_distribution
        block_live_in_distribution()     # 배포판: 실거래 금지(소스 설치 전용)
        if args.market not in LIVE_BROKER_FOR_MARKET:
            raise SystemExit(f"'{args.market}' 시장은 실거래를 지원하지 않습니다. "
                             f"지원: {sorted(LIVE_BROKER_FOR_MARKET)}")
        print("\n⚠️ 실전 모드 — 실제 자금으로 주문합니다.")
        print(f"   안전장치: 일일 손실 킬스위치 -{args.daily_max_loss:.0%} · "
              f"최대낙폭 서킷 -{args.max_drawdown:.0%} · "
              f"최대 비중 {args.max_weight:.0%} · 주문 재시도/체결 확인")
        print("   ⚠️ 갭·급변 구간에서는 한도를 넘는 손실이 날 수 있습니다(보장 아님).")
        print("   잃어도 되는 소액으로만 시작하세요. 수익 보장은 없습니다.")
        try:
            confirm = input("계속하려면 '실전' 두 글자를 입력: ").strip()
        except EOFError:                 # 파이프/스크립트 실행 — 실전 진입 금지
            confirm = ""
        if confirm != "실전":
            print("취소되었습니다.")
            return
        inner = get_broker(LIVE_BROKER_FOR_MARKET[args.market])
        is_stock = args.market in SCHEDULED_MARKETS
        broker = RobustBroker(
            inner, retries=3, backoff=2.0,
            confirm_fills=is_stock,
            fill_timeout=90.0 if is_stock else 0.0,
            fill_poll_interval=3.0)
        mode = "live"
    else:
        broker = get_broker("paper", cash=args.capital)
        mode = "paper"
        print("📝 페이퍼 모드 (실제 자금 사용 안 함) — 실전은 --real")

    # 일일 손실은 킬스위치가, 최대낙폭은 서킷브레이커가 담당(역할 중복 없음)
    breaker = CircuitBreaker(BreakerConfig(max_daily_loss=None,
                                           max_drawdown=args.max_drawdown),
                             notifier=notifier)
    market_guard = (args.market
                    if (args.real and args.market in SCHEDULED_MARKETS) else None)
    if symbols:
        # 같은 시장의 여러 종목을 한 계좌로 분산 운용(역변동성 배분)
        from quant.live.multi import MultiTrader
        state = args.state
        if state == "results/state.json":       # 감시 탭이 읽는 다중 상태 경로
            state = "results/multi_state.json"
        trader = MultiTrader(
            data, strategy, broker, symbols, args.timeframe,
            state_path=state, dashboard_path=args.dashboard,
            notifier=notifier, circuit_breaker=breaker, mode=mode,
            daily_max_loss=args.daily_max_loss, market=market_guard)
    else:
        trader = LiveTrader(
            data, strategy, broker, risk, args.symbol, args.timeframe,
            state_path=args.state, dashboard_path=args.dashboard,
            notifier=notifier, circuit_breaker=breaker, mode=mode,
            daily_max_loss=args.daily_max_loss, market=market_guard)
    print(f"📺 감시: 웹 조종석 '감시' 탭 또는 {args.dashboard}")
    trader.run(interval_sec=args.interval, max_iters=args.iters)


def _cmd_notify(args) -> None:
    """미뤄 둔 알림을 **지금** 내보낸다 (감사 283).

    커밋·푸시가 끝난 뒤에만 부른다. 그전에 죽으면 대기열은 그대로 버려지고
    실패 경보만 나간다 — **저장된 것만 방송한다.**
    """
    from quant.live import notice_queue

    if args.discard:
        n = len(notice_queue.pending())
        notice_queue.discard()
        print(f"🗑 미뤄 둔 알림 {n}건을 버렸습니다(저장되지 않은 일이라 방송하지 않습니다).")
        return
    if not args.flush:
        print(f"미뤄 둔 알림 {len(notice_queue.pending())}건 "
              f"({notice_queue.queue_path()}). 보내려면 --flush.")
        return

    # 여기서는 대기를 끄고 보낸다 — 안 그러면 자기 자신을 다시 쌓는다.
    import os
    os.environ.pop(notice_queue.ENV_DEFER, None)
    sent = notice_queue.flush(_notify_extra)
    print(f"📨 미뤄 둔 알림 {sent}건을 보냈습니다." if sent
          else "보낼 알림이 없습니다.")


def _cmd_verify(args) -> None:
    from quant.live.retrain import verify_retrain

    scope = (f"{args.market}/{args.symbol}"
             if args.symbol else "전체 종목")
    print(f"🔍 재현성 검증: {args.date} · {scope}")
    out = verify_retrain(args.date, market=args.market or None,
                         symbol=args.symbol or None,
                         state_dir=args.state_dir,
                         sample=int(getattr(args, "sample", 0) or 0))
    for r in out:
        print(f"  {'✔' if r['ok'] else '✘'} {r['key']}: {r['detail']}")
    if all(r["ok"] for r in out):
        print("✅ 모든 결정이 재현되었습니다 — 같은 데이터·같은 코드에서 "
              "같은 결과가 나옵니다.")
    else:
        print("⚠️ 일부 검증 실패 — 위 상세를 확인하세요.")
        raise SystemExit(1)


def _cmd_briefing(args) -> None:
    from quant.live.briefing import collect_briefing

    collect_briefing(args.state_dir)
    print("⚠️ 브리핑은 표시 전용입니다 — 매매 판단에 사용되지 않습니다.")


def _cmd_social_content(args) -> None:
    from quant.reporting.social import prune_old, write_content

    from quant.reporting.social import PublishedContentChanged
    try:
        meta = write_content(docs_dir=args.docs_dir,
                             site_url=args.site_url,
                             force=getattr(args, "force", False))
    except PublishedContentChanged as exc:
        # 과거 공개 글을 조용히 바꾸느니 소리 내어 실패한다(감사 86).
        raise SystemExit(f"❌ {exc}")
    removed = prune_old(docs_dir=args.docs_dir, keep=args.keep)
    print(meta["dir"])                    # 워크플로가 이 경로를 받아 캡처한다
    if removed:
        print(f"오래된 게시 폴더 {len(removed)}개 정리: {', '.join(removed)}")


def _cmd_social_post(args) -> None:
    import json as _json

    from quant.reporting.social_post import run

    results = run(args.dir, args.base_url)
    print(_json.dumps(results, ensure_ascii=False, indent=2))
    if results.get("threads_error") and results.get("instagram_error"):
        raise SystemExit(1)               # 전 플랫폼 실패만 잡 실패로 처리


def _cmd_weekly(args) -> None:
    from quant.live.daily import format_weekly, weekly_summary

    text = format_weekly(weekly_summary(args.state_dir))
    print(text)
    if not args.no_notify:
        _notify_extra(text)


def _cmd_walkforward(args) -> None:
    from quant.live.walkforward import format_walkforward, walkforward_report

    rep = walkforward_report(args.state_dir, bars=args.bars,
                             fetch=not args.offline)
    text = format_walkforward(rep)
    print(text)
    if not args.no_notify:
        # 만들어 놓고 아무도 부르지 않는 보고서는 없는 보고서다(주간 워크플로
        # 주석과 같은 이유) — 사이트를 안 열어도 숫자가 도착해야 한다.
        _notify_extra(text)
    if args.save:
        import json as _json
        import os as _os
        _os.makedirs(_os.path.dirname(args.save) or ".", exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            _json.dump(rep, f, ensure_ascii=False, indent=1)
        print(f"\n💾 저장: {args.save}")


def _cmd_web_passwd(args) -> None:
    """조종석 로그인 설정 — 비밀번호는 화면에도, 파일에도 평문으로 안 남는다."""
    import getpass

    from quant.web.auth import set_credentials

    user = input("아이디(이메일 등): ").strip()
    if not user:
        print("아이디가 비어 있습니다 — 중단합니다.")
        raise SystemExit(1)
    pw = getpass.getpass("비밀번호(입력해도 화면에 안 보입니다): ")
    pw2 = getpass.getpass("확인을 위해 한 번 더: ")
    if pw != pw2:
        print("두 입력이 다릅니다 — 중단합니다.")
        raise SystemExit(1)
    if len(pw) < 8:
        print("8자 이상으로 해주세요 — 중단합니다.")
        raise SystemExit(1)
    set_credentials(user, pw)
    print("🔐 저장했습니다(.env — 해시만 저장, 커밋 금지 목록). "
          "웹 조종석을 다시 켜면 로그인 화면이 뜹니다.")


def _cmd_intraday_round(args) -> None:
    """장중 도전자 1회 — 본 계좌와 분리된 실험 트랙(가상 USDT)."""
    import datetime as dt

    from quant.live.intraday_challenger import run_intraday_round

    # 수동 킬스위치는 실험 트랙에도 걸린다 — 본 계좌만 멈추고 실험이 계속
    # 돌면, 사장님이 "다 멈췄다"고 믿는 동안 매매가 계속되는 셈이다.
    from quant.live.manual_halt import gate_message
    _halt = gate_message(args.state_dir)
    if _halt:
        print(_halt)
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    v = run_intraday_round(now, state_dir=args.state_dir,
                           docs_dir=args.docs_dir)
    print(f"🏃 장중 도전자 — 자산 {v['equity']:,.2f} USDT "
          f"({v['return_pct']:+.2f}%) · 이번 회차 체결 {v['trades']}건 · "
          f"건너뜀 {v['skipped']}종목 · 누적 비용 {v['cost_paid']:,.2f} USDT")


def _cmd_guard(args) -> None:
    """장중 감시 1회 — 새벽 배치를 기다리지 않고 지금 낙폭을 잰다.

    ⚠️ 지금(현물·레버리지 없음)은 이 명령이 **없어도 안전하다** — 자산이 0
       아래로 안 가기 때문이다. 이건 레버리지를 열기 위한 준비이고, 동시에
       "우리는 얼마나 자주 보고 있는가"를 실측으로 남기는 장치다.
       그 실측이 없으면 레버리지 한도를 계산할 수 없다(risk/leverage_gate).
    """
    import datetime as dt
    import json as _json
    import os as _os

    from quant.live.guard import (check_ledger_freshness, guard_once,
                                  observed_gap_minutes)
    from quant.live.ledger_basics import chrono

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    # 본 계좌 장부 신선도 — 새벽 배치가 죽으면 그 배치의 경보도 함께
    # 죽으므로(2026-08-16~18 사흘 실측), 살아 있는 이 루프가 대신 잰다.
    # 낙폭 감시보다 먼저 부른다 — 아래 장부 읽기가 실패해도 이건 돌아야 한다.
    stale = check_ledger_freshness(args.state_dir)
    if stale:
        print(f"   {stale['message']}")
    path = _os.path.join(args.state_dir, "paper", args.state_file)
    try:
        with open(path, encoding="utf-8") as f:
            st = _json.load(f)
    except (OSError, _json.JSONDecodeError) as exc:
        print(f"❌ 장부를 읽지 못했습니다({path}): {exc}")
        raise SystemExit(1) from exc

    hist = chrono(st.get("history") or [])
    eqs = [float(r["equity"]) for r in hist if r.get("equity") is not None]
    if not eqs:
        print("기록이 없어 낙폭을 잴 수 없습니다 — 심장박동만 남깁니다.")
        from quant.live.guard import record_heartbeat
        record_heartbeat(now, state_dir=args.state_dir)
        return

    v = guard_once(eqs[-1], max(eqs), float(st.get("risk_scale", 1.0)),
                   now_iso=now, state_dir=args.state_dir)
    gap = observed_gap_minutes(args.state_dir, now_iso=now)
    print(f"🛡️ 장중 감시 — {v.reason}")
    print(f"   관측된 최악 감시 간격: "
          + (f"{gap:,.0f}분" if gap is not None else "아직 모름(기록이 모자람)"))
    if v.acted:
        # ⚠️ 노출 축소를 **장부에 적는다.** 감시가 판단만 하고 장부를 안
        #    고치면 다음 배치가 옛 노출로 되돌린다 — 그러면 이 감시는
        #    '선언만 하는 장치'가 된다(이 저장소가 가장 경계하는 것).
        st["risk_scale"] = v.scale
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(path, st)
        print(f"   → 장부의 노출 배수를 {v.scale:.0%}로 낮췄습니다.")


def _cmd_ingest(args) -> None:
    """내 자료 → 전략 명세 → 도전자 등록.

    ⚠️ 여기서 등록되는 것은 **도전자**다. 등록했다고 그 전략으로 매매하지
       않는다 — 매일 밤 다른 후보들과 같은 심사(선발전·결승전)를 받고,
       이겨야 챔피언이 된다. 그게 이 제품이 파는 것이다.
    """
    from quant.ingest.extract import extract_spec
    from quant.ingest.registry import save_spec
    from quant.ingest.sources import SourceError, load_any

    try:
        loaded = load_any(args.ref)
    except SourceError as exc:
        print(f"❌ 자료를 읽지 못했습니다.\n\n{exc}")
        raise SystemExit(1) from exc

    print(f"📄 {loaded.source.get('kind')} · {loaded.source.get('ref')} — "
          f"글자 {len(loaded.text):,}자")
    result = extract_spec(loaded.text, title=args.name or loaded.title,
                          source=loaded.source)
    if not result.ok:
        # ⚠️ 이게 이 명령의 **정상적인 결과 중 하나**다. 투자 자료 대부분에는
        #    검증 가능한 규칙이 없고, 그때 억지로 만들어 내면 그건 자료의
        #    전략이 아니라 우리가 지어낸 전략이다.
        print(f"\n🔍 문장 {result.sentences_seen:,}개를 봤지만 "
              f"**실행 가능한 규칙을 찾지 못했습니다.**\n")
        for r in result.reasons:
            print(f"  · {r}\n")
        print("전략을 만들지 않았습니다 — 없는 규칙을 지어내지 않습니다.")
        raise SystemExit(2)

    print("\n✅ 이렇게 읽었습니다:\n")
    print(result.spec.summary())
    print("\n  근거가 된 문장:")
    for c in list(result.spec.entry) + list(result.spec.exit):
        print(f"    · \"{c.quote[:90]}\"")
    for note in result.spec.notes:
        print(f"\n  ⚠️ {note}")

    if args.dry_run:
        print("\n(--dry-run: 저장하지 않았습니다)")
        return
    path = save_spec(result.spec, state_dir=args.state_dir or None)
    print(f"\n💾 저장: {path}")
    print("\n이제 매일 밤 재학습에서 **도전자로** 링에 섭니다. 등록만으로는 "
          "매매하지 않습니다 — 다른 후보와 같은 2단계 심사를 이기고, 과최적화 "
          "검증까지 통과해야 실제 비중을 받습니다. 대부분은 떨어집니다.")


def _cmd_pin(args) -> None:
    """내 전략 고정 — 성적표를 먼저 보여주고, 확인 문구를 타이핑해야 고정.

    전략은 사용자의 것, 브레이크는 우리의 것: 고정해도 킬스위치·변동성
    타깃·검증 게이트·레버리지 금지선은 그대로 걸린다.
    """
    from quant.live.pin import ACK_PHRASE, save_pin, scorecard

    for line in scorecard(args.market, args.symbol, args.name,
                          state_dir=args.state_dir):
        print(line)
    print(f"\n고정하려면 다음 문구를 그대로 입력하세요:\n  {ACK_PHRASE}")
    typed = input("> ").strip()
    try:
        entry = save_pin(args.market, args.symbol, args.name, typed,
                         state_dir=args.state_dir)
    except ValueError as exc:
        print(f"❌ {exc}")
        raise SystemExit(1) from exc
    print(f"\n📌 고정됨: {args.market}/{args.symbol} ← {entry['name']} "
          f"({entry['since']}부터)")
    print("   오디션은 계속 돕니다 — 성적표가 매일 갱신되고, `unpin`으로 "
          "언제든 시스템 판단으로 돌아갈 수 있습니다.")


def _cmd_unpin(args) -> None:
    from quant.live.pin import remove_pin

    if remove_pin(args.market, args.symbol, state_dir=args.state_dir):
        print(f"↩️ 고정 해제: {args.market}/{args.symbol} — 다음 실행부터 "
              "시스템 챔피언 판단이 복귀합니다.")
    else:
        print(f"고정돼 있지 않습니다: {args.market}/{args.symbol}")


def _cmd_pins(args) -> None:
    from quant.live.pin import load_pins

    pins = load_pins(args.state_dir)
    if not pins:
        print("고정된 전략이 없습니다 — 모든 종목이 심사(오디션) 결과를 따릅니다.")
        return
    for key, v in sorted(pins.items()):
        print(f"📌 {key} ← {v.get('name')} ({v.get('since')}부터) — "
              "심사 결과가 아니라 사용자 지정입니다")


def _cmd_retrain(args) -> None:
    from quant.live.retrain import run_retrain

    target = "전체 종목(AUTO_TARGETS)" if args.all else f"{args.market}/{args.symbol}"
    print(f"🌙 야간 재학습: {target} "
          f"(결승전 {args.confirm_window}봉, 기록: {args.state_dir}/)")
    print("⚠️ 챔피언이 안 바뀌는 날이 대부분입니다 — 확실히 나은 후보가 없었다는 "
          "뜻이고, 그게 이 장치가 일하는 방식입니다.")
    common = dict(timeframe=args.timeframe, limit=args.limit,
                  state_dir=args.state_dir, confirm_window=args.confirm_window,
                  require_real_data=not args.allow_synthetic)
    if args.all:
        from quant.live.retrain import run_retrain_all
        out = run_retrain_all(**common)
        if out["promoted"]:                     # 교체는 드문 사건 — 폰으로 알린다
            _notify_extra("🔁 챔피언 교체: " + ", ".join(out["promoted"]))
        if out["failed"]:
            _notify_extra("⚠️ 재학습 실패 종목: " + ", ".join(out["failed"]))
        return
    out = run_retrain(args.market, args.symbol, **common)
    if out.get("promoted"):                     # 교체는 드문 사건 — 폰으로 알린다
        c = out["champion"]
        _notify_extra(
            f"🔁 챔피언 교체: {args.market}/{args.symbol} → "
            f"{c['strategy']} {c['params']}\n근거: {out['reason']}")


# validate/웹 최적화가 공유하는 전략별 기본 그리드 — 단일 출처(quant.markets).
from quant.markets import STRATEGY_GRIDS as _VALIDATE_GRIDS


def _cmd_validate(args) -> None:
    """워크포워드(+DSR) → PBO → CPCV를 한 번에 돌려 '이 전략을 믿어도 되는가'를
    한 화면으로 보여준다. 셋 다 과최적화 탐지 도구다 — 통과해도 수익 보장이 아니다."""
    import json as _json

    # ── 전 종목 모드 ────────────────────────────────────────────────
    # ⚠️ 2026-08-14까지 야간 검증은 **BTC와 SPY 두 종목만** 돌았다. 종목
    #    목록이 워크플로 YAML에 손으로 박혀 있었기 때문이다. 운용은 8종목에서
    #    20종목으로 늘었는데 검증은 따라가지 않았고, 나머지 18종목은 PBO·DSR이
    #    **한 번도 계산된 적이 없었다.** 그런데도 제품 문서는 "검증을 통과한
    #    전략만 씁니다"라고 말하고 있었다.
    #
    #    목록을 코드(AUTO_TARGETS)가 갖게 해 같은 표류를 막는다 — 운용 대상을
    #    늘리면 검증도 자동으로 따라온다.
    if getattr(args, "all_targets", False):
        from quant.markets import AUTO_TARGETS
        failed = []
        for i, (mk, sym) in enumerate(AUTO_TARGETS, 1):
            print(f"\n{'=' * 62}\n[{i}/{len(AUTO_TARGETS)}] {mk}:{sym}\n{'=' * 62}")
            one = _copy.copy(args)
            one.market, one.symbol, one.all_targets = mk, sym, False
            # ⚠️ 리포트 경로에 종목 이름을 넣는다. 안 그러면 20종목이 **같은
            #    파일에 차례로 덮어써서** 마지막 종목 것만 남는다 — 파일은
            #    있고 이름도 맞으니 아무도 눈치채지 못하고, 그 리포트를 열어
            #    본 사람은 다른 19종목이 그렇다고 읽는다.
            if getattr(one, "report", None):
                rp = _pathlib.Path(one.report)
                safe = f"{mk}_{sym}".replace("/", "").replace(".", "_")
                one.report = str(rp.with_name(f"{rp.stem}_{safe}{rp.suffix}"))
            try:
                _cmd_validate(one)
            except Exception as exc:  # noqa: BLE001
                # 한 종목의 실패로 나머지 19종목의 검증을 잃지 않는다.
                # 실패는 삼키지 않고 끝에 모아 보고하고, 종료코드로 드러낸다 —
                # 조용히 넘어가면 그 종목은 '미측정'인 채 절반 감쇠만 받고
                # 아무도 이유를 모른다.
                print(f"❌ {mk}:{sym} 검증 실패: {type(exc).__name__}: {exc}")
                failed.append(f"{mk}:{sym} ({type(exc).__name__})")
        print(f"\n{'=' * 62}")
        print(f"전 종목 검증 완료: 성공 {len(AUTO_TARGETS) - len(failed)}"
              f"/{len(AUTO_TARGETS)}")
        if failed:
            print("실패: " + ", ".join(failed))
            raise SystemExit(
                f"검증 실패 {len(failed)}종목 — 그 종목들은 '미측정'으로 "
                "남아 비중이 절반으로 깎입니다.")
        return

    from quant.data import get_provider
    from quant.optimize import (cpcv, cpcv_report, grid_search, robust_best,
                                stability_report, stability_scores,
                                walk_forward)
    from quant.robustness import param_returns_matrix, pbo, pbo_report
    from quant.strategies import get_strategy

    grid = (_json.loads(args.grid) if args.grid
            else _VALIDATE_GRIDS.get(args.strategy))
    if not grid:
        print(f"'{args.strategy}'의 기본 그리드가 없습니다. --grid JSON으로 지정하세요."
              f" (기본 지원: {', '.join(_VALIDATE_GRIDS)})")
        return
    strategy_cls = type(get_strategy(args.strategy))
    ppy = _ppy(args.market)
    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe,
                                             limit=args.limit)
    print(f"\n=== 검증: {args.strategy} · {args.symbol} ({len(df)}봉) ===")
    print(_data_note(df, args.market))
    print(f"그리드: {grid}")

    # 1) 워크포워드 + DSR (다중검정 보정 샤프 신뢰도)
    print("\n[1/4] 워크포워드 (롤링 IS→OOS)")
    dsr_value = None
    # 다중검정 보정의 N — 이 검증 그리드가 아니라 **그 챔피언을 뽑기까지
    # 실제로 시도한 횟수**를 쓴다. 장부(retrain_history)에 종목별 도전자 수가
    # 누적돼 있다. 기록이 없으면 그리드 크기로 폴백(옛 동작).
    try:
        import datetime as _dt

        from quant.live.retrain import recent_trials
        ledger_trials = recent_trials(args.market, args.symbol,
                                      _dt.date.today().isoformat())
    except Exception:  # noqa: BLE001 — 장부 조회 실패가 검증을 막지 않는다
        ledger_trials = 0
    # 돌지 못한 검증의 **이유**를 모은다(감사 249) — 아래에서 장부에 실린다.
    skipped: dict[str, str] = {}
    try:
        wf = walk_forward(df, strategy_cls, grid, is_window=args.is_window,
                          oos_window=args.oos_window, embargo=args.embargo,
                          periods_per_year=ppy, extra_trials=ledger_trials)
        m = wf["oos_metrics"]
        print(f"  OOS 샤프 {m.sharpe:.2f} · 총수익 {m.total_return:.2%} · "
              f"최대낙폭 {m.max_drawdown:.2%} · 구간 {len(wf['segments'])}개")
        dsr_value = float(wf["dsr"])
        print(f"  DSR(시행 {wf['n_trials']}회 보정): {wf['dsr']:.2f} "
              f"{'— 실력 가능성' if wf['dsr'] >= 0.95 else '— 운일 수 있음(0.95 미만)'}")
    except ValueError as exc:
        print(f"  건너뜀: {exc}")
        skipped["dsr"] = str(exc)[:200]

    # 2) PBO — IS 1등이 OOS에서 동전던지기인지
    print("\n[2/4] PBO (백테스트 과적합 확률)")
    pbo_value = None
    try:
        mat = param_returns_matrix(df, strategy_cls, grid, periods_per_year=ppy)
        pbo_res = pbo(mat, n_blocks=args.pbo_blocks)
        pbo_value = float(pbo_res.get("pbo")) if isinstance(pbo_res, dict) \
            else float(getattr(pbo_res, "pbo", None) or 0.0)
        print("  " + pbo_report(pbo_res).replace("\n", "\n  "))
    except (ValueError, TypeError, AttributeError) as exc:
        print(f"  건너뜀: {exc}")
        skipped["pbo"] = str(exc)[:200]

    # 3) CPCV — 여러 OOS 경로의 분포
    #
    # ⚠️ 이 결과는 **계산하고 출력한 뒤 버려지고 있었다**(2026-08-14 발견).
    #    문서는 "3중 관문(DSR·PBO·CPCV)"이라 말하고 통과 기준까지 적어 뒀는데
    #    ("가장 나쁜 경로에서도 플러스"), 그 값이 장부에 저장되지 않아
    #    **어떤 판단에도 닿지 않았다.** DSR·PBO를 게이트에 붙이면서 확인했다.
    print("\n[3/4] CPCV (다중 OOS 경로 분포)")
    cpcv_worst = None
    cpcv_min_sharpe = None
    try:
        cv = cpcv(df, strategy_cls, grid, n_groups=args.cpcv_groups,
                  n_test=2, embargo=args.embargo, periods_per_year=ppy)
        print("  " + cpcv_report(cv).replace("\n", "\n  "))
        cpcv_worst = float(cv["worst_path_return"])
        cpcv_min_sharpe = float(cv["sharpe_min"])
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  건너뜀: {exc}")
        skipped["cpcv"] = str(exc)[:200]

    # 4) 파라미터 안정성 — 1등이 '넓은 고원'인가 '외딴 봉우리'인가
    #
    # ⚠️ 이 도구(quant/optimize/stability.py)는 만들어져 있었는데 **부르는
    #    곳이 한 곳도 없었다**(감사 157). 오디션은 2단계 검증으로 봉우리를
    #    막지만, 사장님이 손으로 그리드를 볼 때 쓸 창구가 없었다.
    #    검증 3종이 "이 성적이 운인가"를 묻는다면 이건 "이 **파라미터**가
    #    운인가"를 묻는다 — 옆칸으로 한 스텝만 옮겨도 무너지는 설정은
    #    데이터가 조금만 달라져도 무너진다.
    print("\n[4/4] 파라미터 안정성 (고원 vs 외딴 봉우리)")
    peak_only = None
    try:
        gs = grid_search(df, strategy_cls, grid, periods_per_year=ppy)
        scored = stability_scores(gs["results"])
        print("  " + stability_report(scored).replace("\n", "\n  "))
        rb = robust_best(scored)
        peak_only = bool(rb is not None and rb != gs["best_params"])
    except (ValueError, TypeError, KeyError) as exc:
        print(f"  건너뜀: {exc}")
        skipped["stability"] = str(exc)[:200]

    # 검증 결과를 장부에 남긴다 — 과최적화 감시가 콘솔에만 찍히고 사라지면
    # 아무것도 막지 못한다. 저장된 값은 flag_watch가 매일 읽어 경보한다.
    if getattr(args, "save", None):
        import os as _os

        from quant.utils.jsonio import atomic_write_json
        path, prev = args.save, {}
        if _os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    prev = _json.load(f)
            except (OSError, ValueError):
                prev = {}
        prev[f"{args.market}:{args.symbol}"] = {
            "strategy": args.strategy, "bars": len(df),
            # ⚠️ 날짜가 없으면 검증 게이트가 **만료를 판정할 수 없다**
            #    (2026-08-14). 며칠 멈춘 검증이 통과 도장을 계속 찍어 주는
            #    것을 막으려면 '언제 잰 값인가'가 기록에 있어야 한다.
            #    결정 봉의 날짜를 쓴다 — 실행 시각이 아니라 데이터의 시각이
            #    이 판정의 기준이다.
            "asof": str(df.index[-1])[:10] if len(df) else None,
            "dsr": dsr_value, "pbo": pbo_value,
            # 3중 관문의 세 번째 — 통과 기준은 "가장 나쁜 경로에서도 플러스".
            # 2026-08-14까지 이 값은 화면에만 찍히고 사라졌다.
            "cpcv_worst_return": cpcv_worst,
            "cpcv_min_sharpe": cpcv_min_sharpe,
            # ⚠️ **왜 없는지도 남긴다**(감사 249). 예전에는 못 잰 값이 그냥
            #    null로 남고 이유는 콘솔에만 찍혔다. 그러면 사이트는 "안
            #    돌았다"와 "돌았는데 문제없다"를 구별할 수 없다 — 리포트
            #    페이지는 그 구별을 이미 하고 있었다("판정 불가", 감사 52).
            "skipped": dict(skipped) or None,
            # 원점수 1등과 견고성 1등이 다른가 — True면 그 파라미터는
            # '외딴 봉우리'일 수 있다(감사 157). 콘솔에만 찍히면 아무것도
            # 막지 못하므로 장부에 남겨 flag_watch가 읽게 한다.
            "peak_only": peak_only,
        }
        atomic_write_json(path, prev)
        print(f"\n💾 검증 결과 저장: {path}")

    if getattr(args, "report", None):
        from quant.reporting import render_validation_report
        out = render_validation_report(
            df, strategy_cls, grid, path=args.report,
            title=f"{args.strategy} · {args.symbol} 검증",
            is_window=args.is_window, oos_window=args.oos_window,
            embargo=args.embargo, pbo_blocks=args.pbo_blocks,
            cpcv_groups=args.cpcv_groups, periods_per_year=ppy)
        print(f"\n📄 검증 리포트(그래프): {out}")

    print("\n⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다. "
          "다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.")


# setup 마법사가 안내하는 API 키 그룹. (그룹명, 설명, 필요한 이유, [(env, 안내, 비밀?)])
# ⚠️ 백테스트·검증·페이퍼 트레이딩은 키가 '하나도' 필요 없다 — 실거래·알림·
#    보조 데이터에만 필요하다. 키 발급 자체는 계좌 소유자 본인 인증이 필요해
#    본인만 할 수 있고, 이 마법사는 발급받은 키를 안전하게 저장하는 부분을 맡는다.
_SETUP_GROUPS = [
    ("암호화폐 실거래 (ccxt — 바이낸스/업비트 등)",
     "실거래 주문에만 필요. 발급: 거래소 웹 → API 관리 (출금 권한은 끄세요!)",
     [("EXCHANGE_API_KEY", "API 키", False),
      ("EXCHANGE_SECRET", "시크릿", True),
      ("EXCHANGE_PASSWORD", "패스프레이즈(거래소에 따라, 없으면 엔터)", True)]),
    ("미국주식 실거래 (Alpaca)",
     "발급: alpaca.markets → Paper/Live API 키",
     [("ALPACA_API_KEY", "API 키", False),
      ("ALPACA_SECRET", "시크릿", True)]),
    ("한국주식 실거래 (한국투자증권 KIS)",
     "발급: KIS Developers → 앱 등록",
     [("KIS_APP_KEY", "앱 키", False),
      ("KIS_APP_SECRET", "앱 시크릿", True),
      ("KIS_CANO", "계좌번호(앞 8자리)", False),
      ("KIS_ACNT_PRDT_CD", "계좌상품코드(뒤 2자리, 보통 01)", False)]),
    ("알림 (텔레그램)",
     "봇 생성: @BotFather → 토큰. chat_id: @userinfobot",
     [("TELEGRAM_BOT_TOKEN", "봇 토큰", True),
      ("TELEGRAM_CHAT_ID", "챗 ID", False)]),
    ("보조 데이터 (선택)",
     "FRED(거시, fred.stlouisfed.org)·FMP(재무, financialmodelingprep.com) — 무료 발급",
     [("FRED_API_KEY", "FRED 키(없으면 엔터)", True),
      ("FMP_API_KEY", "FMP 키(없으면 엔터)", True)]),
]


def _cmd_setup(args) -> None:
    """대화형 API 키 설정 — 물어보고, .env에 안전하게 저장하고, 연결을 확인한다."""
    import getpass

    from quant.utils.envfile import load_env_file, update_env_file

    print("\n🔑 API 키 설정 마법사")
    print("─" * 46)
    print("· 백테스트·검증·페이퍼 트레이딩에는 키가 전혀 필요 없습니다.")
    print("· 키 '발급'은 계좌 본인 인증이 필요해 직접 하셔야 하지만,")
    print("  발급 후 입력·저장·확인은 여기서 한 번에 끝납니다.")
    print("· 저장 위치: .env (git 미포함 · 리눅스/맥은 본인만 읽기 권한)")
    print("· 각 그룹은 건너뛸 수 있습니다(엔터).\n")

    load_env_file()          # 기존 값을 알아야 '이미 설정됨'을 표시할 수 있다
    import os
    updates: dict[str, str] = {}
    for title, guide, fields in _SETUP_GROUPS:
        print(f"\n■ {title}")
        print(f"  {guide}")
        use = input("  설정할까요? [y/N] ").strip().lower()
        if use not in ("y", "yes"):
            continue
        for env, label, secret in fields:
            cur = " (이미 설정됨 — 엔터=유지)" if os.getenv(env) else ""
            prompt = f"  {label} [{env}]{cur}: "
            val = (getpass.getpass(prompt) if secret else input(prompt)).strip()
            if val:
                updates[env] = val

    if not updates:
        print("\n변경 없음 — 종료합니다.")
        return
    private = update_env_file(".env", updates)
    os.environ.update(updates)      # 이번 세션의 연결 확인에 바로 반영
    print(f"\n✅ {len(updates)}개 키를 .env에 저장했습니다 (git 미포함).")
    # 권한은 '확인한 사실'만 말한다. 예전에는 chmod 성공 여부와 무관하게
    # "권한 600"이라 단언했다 — 지켜지지 않은 보안 약속은 느슨한 권한보다
    # 위험하다(2026-08-11 감사 ㊾).
    if private:
        print("   파일 권한: 600 (본인만 읽기) — 확인됨")
    elif os.name != "posix":
        print("   ⚠️ 파일 권한: 윈도우에서는 '본인만 읽기'를 보장할 수 없습니다.")
        print("      .env 를 다른 사람이 쓰는 계정과 공유되지 않는 폴더에 두세요.")
    else:
        print("   ⚠️ 파일 권한을 600으로 조이지 못했습니다 — 같은 기계의 다른")
        print("      사용자가 키를 읽을 수 있습니다. `chmod 600 .env` 를 직접 실행하세요.")

    # 연결 확인 (best-effort — 실패해도 저장은 유지)
    if any(k.startswith("EXCHANGE_") for k in updates):
        try:
            from quant.data import get_provider
            df = get_provider("crypto").get_ohlcv("BTC/USDT", "1d", limit=5)
            fb = bool(df.attrs.get("synthetic_fallback"))
            print("🔌 거래소 시세 연결: " + ("⚠️ 폴백(네트워크/키 확인)" if fb else "✅ 정상"))
        except Exception as exc:  # noqa: BLE001
            print(f"🔌 거래소 연결 확인 실패: {exc}")
    if "TELEGRAM_BOT_TOKEN" in updates:
        try:
            from quant.live.notifications import TelegramNotifier
            TelegramNotifier(
                os.getenv("TELEGRAM_BOT_TOKEN", updates.get("TELEGRAM_BOT_TOKEN", "")),
                os.getenv("TELEGRAM_CHAT_ID", updates.get("TELEGRAM_CHAT_ID", "")),
            ).send("🔑 Quant 설정 마법사 — 알림 연결 확인")
            print("📨 텔레그램: 테스트 메시지를 보냈습니다(수신 확인하세요).")
        except Exception as exc:  # noqa: BLE001
            print(f"📨 텔레그램 확인 실패: {exc}")
    print("\n⚠️ 키는 절대 커밋·공유하지 마세요. 실거래 키는 출금 권한을 꺼두세요.")


def _cmd_webhook(args) -> None:
    """트레이딩뷰 등의 알림 웹훅을 받아 주문을 실행한다(기본 페이퍼, 보안 필수)."""
    import os

    from quant.broker import RobustBroker, get_broker
    from quant.data import get_provider
    from quant.live.webhook import (
        TRADINGVIEW_IPS,
        WebhookExecutor,
        run_webhook_server,
    )

    secret = os.getenv("QUANT_WEBHOOK_SECRET", "")
    if not secret:
        print("❌ 환경변수 QUANT_WEBHOOK_SECRET(공유 비밀키)이 필요합니다.\n"
              "   인증 없는 주문 엔드포인트는 누구나 내 계좌로 주문을 낼 수 있어 "
              "실행할 수 없습니다.\n   예: export QUANT_WEBHOOK_SECRET='아주-긴-무작위-문자열'")
        return

    from quant.markets import LIVE_BROKER_FOR_MARKET as _live_mode, SCHEDULED_MARKETS
    is_stock = args.market in SCHEDULED_MARKETS
    if args.live:
        from quant.utils.dist import block_live_in_distribution
        block_live_in_distribution()     # 배포판: 실거래 금지(소스 설치 전용)
        if args.market not in _live_mode:
            print(f"'{args.market}' 시장은 실거래를 지원하지 않습니다.")
            return
        c = input("⚠️ 실거래 웹훅입니다. 외부 신호가 실제 자금으로 주문을 냅니다. "
                  "계속? (yes 입력): ")
        if c.strip().lower() != "yes":
            print("취소되었습니다.")
            return
        inner = get_broker(_live_mode[args.market])
        broker = RobustBroker(inner, retries=3, backoff=2.0,
                              confirm_fills=is_stock,
                              fill_timeout=90.0 if is_stock else 0.0)
        mode = "live"
    else:
        broker = get_broker("paper", cash=args.cash)
        mode = "paper"
        print("📝 페이퍼 모드 — 실제 자금 사용 안 함")

    # 페이로드에 price가 없을 때 쓰는 현재가 조회(선택). 트레이딩뷰는 {{close}}를
    # 실어 보내는 것을 권장(네트워크 조회 없이 즉시 실행).
    provider = get_provider(args.market)

    def price_fn(symbol: str) -> float:
        # 합성 폴백 시세로 주문 수량을 정하면 안 된다(감사 85).
        # 거래소 조회가 전부 실패하면 GBM 난수 걷기(시작가 100)가
        # 오는데, 그 가격으로 수량을 계산하면 실제와 수십만 배
        # 어긋난다. 0.0을 주면 실행기가 "현재가를 얻지 못함"으로
        # 주문을 거부한다 — 모를 때는 주문하지 않는다.
        from quant.data.guard import last_real_price
        return last_real_price(provider, symbol, args.timeframe)

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    executor = WebhookExecutor(
        broker, symbols=symbols, market=(args.market if is_stock else None),
        rebalance_band=args.rebalance_band, max_weight=args.max_weight,
        allow_short=args.allow_short, price_fn=price_fn)

    allow_ips = None
    if args.tradingview_ips:
        allow_ips = set(TRADINGVIEW_IPS)
    elif args.allow_ips:
        allow_ips = {ip.strip() for ip in args.allow_ips.split(",") if ip.strip()}

    print(f"🔌 웹훅 서버 시작 ({mode}) — {args.host}:{args.port}")
    print("   Pine Script 알림 메시지(JSON) 예시:")
    print('   {"secret":"<비밀키>","action":"long","symbol":"'
          f'{(symbols or ["BTC/USDT"])[0]}","price":{{{{close}}}}}}')
    if not allow_ips:
        print("   ⚠️ IP 허용목록 미설정 — --tradingview-ips 권장(공식 IP만 허용).")
    if not args.max_age:
        # 재전송 차단은 5분 창이라, 그보다 오래된 캡처 신호는 통과한다.
        # 신선도 검사를 켜면 그 구멍이 닫힌다 — 다만 페이로드에 timestamp가
        # 있어야 하므로 기본값으로 켜면 기존 알림이 전부 400이 된다.
        # 그래서 켜지 않되 **꺼져 있다는 사실은 말한다**(2026-08-11 감사).
        print("   ⚠️ 신선도 검사 꺼짐 — 5분 지난 캡처 신호도 통과합니다. "
              "알림 JSON에 \"timestamp\": {{timenow}} 를 넣고 --max-age 300 "
              "을 주면 막힙니다.")
    print("   ⚠️ 이 포트를 인터넷에 열 때는 HTTPS(리버스 프록시) 뒤에 두세요.")
    run_webhook_server(executor, host=args.host, port=args.port, secret=secret,
                       allow_ips=allow_ips, replay=True,
                       max_age_sec=args.max_age)


def _cmd_journal(args) -> None:
    """봇 상태 파일에서 실거래/페이퍼 성과를 복기한다(거래 단위 통계)."""
    from quant.live.journal import review_report, review_state_file

    # periods_per_year를 넘기지 않는다 — 복기 통계에는 연율화 지표가 없어서
    # 그 값이 쓰이는 자리가 없었다(감사 174). 계산해 넘기기만 하면 사장님이
    # 시장을 고르면 뭔가 달라진다고 오해하게 된다.
    review = review_state_file(args.state)
    print(f"\n=== 거래 복기: {args.state} ===")
    print(review_report(review))
def _cmd_costcheck(args) -> None:
    """손익분기 비용 분석 — 이 전략이 실전 수수료를 이길 수 있는지 폭로한다.
    손익분기 수수료가 시장 비용보다 낮으면 고회전 전략의 환상이다."""
    from quant.backtest.cost_sensitivity import (
        break_even_cost,
        cost_sensitivity_report,
        cost_sweep,
    )
    from quant.data import get_provider
    from quant.strategies import get_strategy

    ppy = _ppy(args.market)
    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe,
                                             limit=args.limit)
    factory = lambda: get_strategy(args.strategy)  # noqa: E731 — 상태 없는 새 전략
    fees = [0.0, 0.0005, 0.001, 0.002, 0.005]
    print(f"\n=== 손익분기 비용: {args.strategy} · {args.symbol} ({len(df)}봉) ===")
    print(_data_note(df, args.market))
    sweep = cost_sweep(df, factory, fees, periods_per_year=ppy)
    be = break_even_cost(df, factory, periods_per_year=ppy)
    print(cost_sensitivity_report(sweep, be))


def _cmd_compare(args) -> None:
    """전략 A/B 유의성 검정 — 차이가 노이즈인지 실제 개선인지 구분한다."""
    from quant.data import get_provider
    from quant.robustness import ab_test, compare_report
    from quant.strategies import get_strategy

    ppy = _ppy(args.market)
    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe,
                                             limit=args.limit)
    fa = lambda: get_strategy(args.strategy_a)  # noqa: E731
    fb = lambda: get_strategy(args.strategy_b)  # noqa: E731
    print(f"\n=== A/B 비교: A={args.strategy_a} vs B={args.strategy_b} · "
          f"{args.symbol} ({len(df)}봉) ===")
    print(_data_note(df, args.market))
    result = ab_test(df, fa, fb, periods_per_year=ppy)
    print(compare_report(result))


def _cmd_pipeline(args) -> None:
    import runpy
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "examples" / "run_config.py"
    sys.argv = ["run_config.py"] + (["--config", args.config] if args.config else [])
    runpy.run_path(str(script), run_name="__main__")


def _default_journal_state() -> str:
    """복기 대상 기본 경로 — 실제로 굴리는 통합 계좌를 먼저 본다.

    통합 계좌 장부가 있으면 그것을, 없으면 개발용 learn 봇 상태로 폴백한다.
    """
    import os as _os
    pf = _os.path.join("state", "paper", "portfolio_ALL.json")
    return pf if _os.path.exists(pf) else _os.path.join("results", "state.json")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quant", description="퀀트 트레이딩 CLI")
    sub = p.add_subparsers(dest="command")

    bt = sub.add_parser("backtest", help="전략 백테스트 실행")
    bt.add_argument("--market", default="synthetic")
    bt.add_argument("--symbol", default="DEMO")
    bt.add_argument("--timeframe", default="1d")
    bt.add_argument("--limit", type=int, default=500)
    bt.add_argument("--strategy", default="ma_cross")
    bt.add_argument("--report", default=None, help="HTML 리포트 저장 경로")
    bt.add_argument("--rebalance-band", type=float, default=0.0,
                    dest="rebalance_band",
                    help="리밸런스 데드밴드(권장 0.02~0.05). 미세 조정 거래를 "
                         "생략해 왕복비용을 아낀다. 0=비활성")
    bt.add_argument("--stop-cooldown", type=int, default=0, dest="stop_cooldown",
                    help="스톱 발동 후 N봉 재진입 금지(채찍질 비용 방지). 0=비활성")
    bt.add_argument("--dd-throttle", action="store_true", dest="dd_throttle",
                    help="자산곡선이 자체 MA 하회 시 익스포저 축소")
    bt.add_argument("--dd-band", type=float, default=0.0, dest="dd_band",
                    help="트로틀 히스테리시스 밴드(예: 0.01). 0=즉시 전환")
    bt.add_argument("--intrabar-stops", action="store_true", dest="intrabar_stops",
                    help="손절/익절을 봉 내 고저가로 판정(실전에 더 가까움 — "
                         "종가 판정은 봉 중간 관통을 놓쳐 손실을 과소평가)")
    bt.add_argument("--market-costs", action="store_true", dest="market_costs",
                    help="시장별 현실 비용 프리셋 적용(한국주식 거래세 등 — "
                         "근사치, 본인 브로커 기준 확인 필요)")
    bt.set_defaults(func=_cmd_backtest)

    sw = sub.add_parser("sweep", help="파라미터 민감도 히트맵")
    sw.add_argument("--market", default="synthetic")
    sw.add_argument("--symbol", default="DEMO")
    sw.add_argument("--timeframe", default="1d")
    sw.add_argument("--limit", type=int, default=800)
    sw.add_argument("--objective", default="sharpe")
    sw.add_argument("--out", default="results/heatmap.html")
    sw.set_defaults(func=_cmd_sweep)

    web = sub.add_parser("web", help="로컬 웹 UI 실행")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--open", action="store_true", help="브라우저 자동 열기")
    web.set_defaults(func=_cmd_web)

    ln = sub.add_parser("learn", help="자동 페이퍼 트레이딩 + 지속 재학습 + 정확도 추적")
    ln.add_argument("--market", default="synthetic")
    ln.add_argument("--symbol", default="DEMO")
    ln.add_argument("--strategy", default="champion",
                    help="champion(기본, 야간 재학습 챔피언 자동 추종) | ml | "
                         "ensemble | 개별 전략 이름")
    ln.add_argument("--timeframe", default="1d")
    ln.add_argument("--lookback", type=int, default=400)
    ln.add_argument("--accuracy-window", type=int, default=60, dest="accuracy_window")
    ln.add_argument("--cash", type=float, default=10_000.0)
    ln.add_argument("--cycles", type=int, default=0, help="0=무기한, N=N회 후 종료")
    ln.add_argument("--interval", type=int, default=3600, help="사이클 간격(초)")
    ln.add_argument("--state", default="results/autolearn_state.json")
    ln.set_defaults(func=_cmd_learn)

    va = sub.add_parser(
        "validate",
        help="과최적화 검증 3종(워크포워드+DSR·PBO·CPCV)을 한 번에 실행")
    va.add_argument("--market", default="synthetic")
    va.add_argument("--symbol", default="DEMO")
    va.add_argument("--all", action="store_true", dest="all_targets",
                    help="운용 대상 전 종목(quant.markets.AUTO_TARGETS)을 "
                         "차례로 검증한다 — 종목 목록을 워크플로가 아니라 "
                         "코드가 갖게 해, 종목을 늘려도 검증이 따라온다")
    va.add_argument("--timeframe", default="1d")
    va.add_argument("--limit", type=int, default=800)
    va.add_argument("--strategy", default="ma_cross",
                    help=f"기본 그리드 지원: {', '.join(_VALIDATE_GRIDS)}")
    va.add_argument("--grid", default=None,
                    help='파라미터 그리드 JSON (예: \'{"fast":[5,10],"slow":[40,60]}\')')
    va.add_argument("--is-window", type=int, default=250, dest="is_window")
    va.add_argument("--oos-window", type=int, default=125, dest="oos_window")
    va.add_argument("--embargo", type=int, default=5)
    va.add_argument("--pbo-blocks", type=int, default=10, dest="pbo_blocks")
    va.add_argument("--save", default=None,
                    help="검증 결과(DSR·PBO)를 JSON 장부에 누적 저장 "
                         "(예: state/validation.json) — flag_watch가 읽어 경보한다")
    va.add_argument("--cpcv-groups", type=int, default=6, dest="cpcv_groups")
    va.add_argument("--report", default=None,
                    help="검증 결과를 그래프 HTML 리포트로 저장(예: results/validate.html)")
    va.set_defaults(func=_cmd_validate)

    pd_ = sub.add_parser(
        "paper-daily",
        help="매일 1사이클 자동 페이퍼 운용 — 챔피언 추종, 상태 이어받기(멱등)")
    pd_.add_argument("--market", default="crypto")
    pd_.add_argument("--symbol", default="BTC/USDT")
    pd_.add_argument("--timeframe", default="1d")
    pd_.add_argument("--lookback", type=int, default=400)
    pd_.add_argument("--state-dir", default="state", dest="state_dir")
    pd_.add_argument("--docs", action="store_true",
                     help="docs/status.json 갱신(사이트에 결과 표시)")
    pd_.add_argument("--allow-synthetic", action="store_true",
                     help="합성 폴백 데이터 허용(테스트 전용)")
    pd_.add_argument("--all", action="store_true",
                     help="AUTO_TARGETS 전 종목 순회(야간 자동화용)")
    pd_.set_defaults(func=_cmd_paper_daily)

    ld = sub.add_parser(
        "live-daily",
        help="하루 1회 국내주식 실거래 집행 — 페이퍼와 같은 결정을 KIS 계좌로 "
             "(기본 모의투자, 실전은 --real + QUANT_LIVE_REAL=1)")
    ld.add_argument("--real", action="store_true",
                    help="실전 계좌 사용(환경변수 QUANT_LIVE_REAL=1 필요)")
    ld.add_argument("--broker", default=None, choices=["kis", "kiwoom"],
                    help="증권사 선택(기본: QUANT_KR_BROKER 환경변수 → kis)")
    ld.add_argument("--state-dir", default="state", dest="state_dir")
    ld.set_defaults(func=_cmd_live_daily)

    lc = sub.add_parser(
        "live-check",
        help="실거래 전환 준비 진단 — 키·인증·잔고를 주문 없이 확인")
    lc.add_argument("--real", action="store_true", help="실전 도메인으로 진단")
    lc.add_argument("--broker", default=None, choices=["kis", "kiwoom"],
                    help="증권사 선택(기본: QUANT_KR_BROKER 환경변수 → kis)")
    lc.set_defaults(func=_cmd_live_check)

    dp = sub.add_parser(
        "deposit",
        help="100만 챌린지 매칭 입금 (100만원→1억) — 후원 금액만큼 통합 계좌 원금 증액")
    dp.add_argument("--amount", type=float, required=True, help="입금액(원)")
    dp.add_argument("--memo", default="", help="예: '슈퍼챗 ○○님'")
    dp.add_argument("--state-dir", default="state", dest="state_dir")
    dp.set_defaults(func=_cmd_deposit)

    rd = sub.add_parser(
        "redenominate",
        help="통합 계좌를 원화 계좌로 다시 연다 (감사 212) — 한 번만 실행")
    rd.add_argument("--principal", type=float, required=True,
                    help="새 원화 계좌의 원금(원)")
    rd.add_argument("--state-dir", default="state", dest="state_dir")
    rd.add_argument("--state-file", default="portfolio_ALL.json",
                    dest="state_file",
                    help="섀도 대조군은 portfolio_SHADOW.json (감사 215)")
    rd.add_argument("--yes", action="store_true",
                    help="확인 없이 실행 (워크플로용)")
    rd.set_defaults(func=_cmd_redenominate)

    lv = sub.add_parser(
        "live",
        help="실시간 루프 — 챔피언(야간 진화) 자동 추종 · 기본 페이퍼, --real 시 실전")
    lv.add_argument("--market", default="crypto")
    lv.add_argument("--symbol", default="BTC/USDT")
    lv.add_argument("--symbols", default="",
                    help='같은 시장 다중 종목 분산 운용 — 예: "BTC/USDT,ETH/USDT,SOL/USDT"')
    lv.add_argument("--timeframe", default="1d",
                    help="1d=챔피언 검증과 같은 일봉 기준(권장)")
    lv.add_argument("--strategy", default="champion",
                    help="champion=야간 재학습 챔피언 자동 추종(기본), 또는 전략 이름")
    lv.add_argument("--real", action="store_true",
                    help="⚠️ 실거래 — 실제 자금. 타이핑 확인을 거칩니다")
    lv.add_argument("--capital", type=float, default=10_000.0,
                    help="페이퍼 모드 시작 자금(실전에서는 무시 — 계좌 잔고 사용)")
    lv.add_argument("--max-weight", type=float, default=0.5, dest="max_weight",
                    help="자산 대비 최대 포지션 비중 (기본 0.5 = 절반)")
    lv.add_argument("--daily-max-loss", type=float, default=0.03,
                    dest="daily_max_loss",
                    help="일일 손실 킬스위치 한도 (기본 0.03 = -3%%)")
    lv.add_argument("--max-drawdown", type=float, default=0.15,
                    dest="max_drawdown",
                    help="최대낙폭 서킷브레이커 한도 (기본 0.15 = -15%%)")
    lv.add_argument("--interval", type=int, default=3600, help="사이클 간격(초)")
    lv.add_argument("--iters", type=int, default=None, help="반복 횟수(기본 무한)")
    lv.add_argument("--state", default="results/state.json",
                    help="상태 저장 경로(웹 조종석 감시 탭이 읽음)")
    lv.add_argument("--dashboard", default="results/dashboard.html")
    lv.set_defaults(func=_cmd_live)

    vf = sub.add_parser(
        "verify",
        help="재현성 검증 — 스냅샷·시드로 그날의 재학습 결정을 재실행해 대조")
    vf.add_argument("--date", required=True, help="예: 2026-08-06")
    vf.add_argument("--market", default="", help="비우면 전체")
    vf.add_argument("--symbol", default="", help="비우면 전체")
    vf.add_argument("--state-dir", default="state", dest="state_dir")
    vf.add_argument("--sample", type=int, default=0,
                    help="종목 표본 수(0=전체). 날짜 시드로 결정적 선택 — "
                         "매일 다른 표본이라 한 주면 전 종목을 훑는다")
    vf.set_defaults(func=_cmd_verify)

    nt = sub.add_parser(
        "notify",
        help="미뤄 둔 알림 내보내기 — 커밋·푸시가 끝난 뒤에만 부른다(감사 283)")
    nt.add_argument("--flush", action="store_true", help="쌓인 알림을 보낸다")
    nt.add_argument("--discard", action="store_true",
                    help="쌓인 알림을 버린다(저장되지 않은 일은 방송하지 않는다)")
    nt.set_defaults(func=_cmd_notify)

    bf = sub.add_parser(
        "briefing",
        help="시장 브리핑 수집(무료 RSS) — 방송·사이트 표시 전용, 판단 미사용")
    bf.add_argument("--state-dir", default="state", dest="state_dir")
    bf.set_defaults(func=_cmd_briefing)

    wk = sub.add_parser(
        "weekly",
        help="주간 요약 — 시장별 주간 수익·최악일·챔피언 교체 이력(텔레그램 전송)")
    wk.add_argument("--state-dir", default="state", dest="state_dir")
    wk.add_argument("--no-notify", action="store_true",
                    help="텔레그램 전송 없이 출력만")
    wk.set_defaults(func=_cmd_weekly)

    wf = sub.add_parser(
        "walkforward",
        help="긴 검증 — 챔피언 설정을 최장 과거에 적용한 구간별 성적"
             "(생존 편향 고지 포함, 승격에 쓰지 않는 관찰값)")
    wf.add_argument("--state-dir", default="state", dest="state_dir")
    wf.add_argument("--bars", type=int, default=2500,
                    help="목표 봉 수(기본 2,500 ≈ 주식 10년)")
    wf.add_argument("--offline", action="store_true",
                    help="네트워크 없이 저장된 스냅샷만 사용")
    wf.add_argument("--save", default=None,
                    help="결과 JSON 저장 경로(예: docs/walkforward.json)")
    wf.add_argument("--no-notify", action="store_true",
                    help="알림 전송 없이 출력만")
    wf.set_defaults(func=_cmd_walkforward)

    sc = sub.add_parser(
        "social-content",
        help="SNS 게시 콘텐츠 생성 — 캡션(인스타/스레드)·메타를 docs/social/에 쓴다")
    sc.add_argument("--docs-dir", default="docs", dest="docs_dir")
    sc.add_argument("--site-url", dest="site_url",
                    default="https://quant.jiwon-1a2.workers.dev")
    sc.add_argument("--keep", type=int, default=14,
                    help="보관할 날짜 폴더 수(오래된 것 정리)")
    sc.add_argument("--force", action="store_true",
                    help="이미 공개된 날의 캡션을 덮어쓴다 — 과거 기록을 "
                         "바꾸는 행위이므로 의도적일 때만 쓸 것(감사 86)")
    sc.set_defaults(func=_cmd_social_content)

    sp = sub.add_parser(
        "social-post",
        help="SNS 게시 실행 — Threads/Instagram API (환경변수 미설정 시 건너뜀)")
    sp.add_argument("--dir", required=True, help="콘텐츠 폴더(docs/social/<날짜>)")
    sp.add_argument("--base-url", dest="base_url",
                    default="https://quant.jiwon-1a2.workers.dev")
    sp.set_defaults(func=_cmd_social_post)

    rt = sub.add_parser(
        "retrain",
        help="야간 자동 재학습 — 챔피언/챌린저 2단계 검증, 이길 때만 교체")
    rt.add_argument("--market", default="crypto")
    rt.add_argument("--symbol", default="BTC/USDT")
    rt.add_argument("--timeframe", default="1d")
    rt.add_argument("--limit", type=int, default=800)
    rt.add_argument("--confirm-window", type=int, default=120,
                    dest="confirm_window",
                    help="결승전(최근 미공개 구간) 봉 수")
    rt.add_argument("--state-dir", default="state", dest="state_dir")
    rt.add_argument("--allow-synthetic", action="store_true",
                    help="합성 폴백 데이터 허용(테스트 전용 — 실서비스 금지)")
    rt.add_argument("--all", action="store_true",
                    help="AUTO_TARGETS 전 종목 순회(야간 자동화용)")
    rt.set_defaults(func=_cmd_retrain)

    ig = sub.add_parser(
        "ingest",
        help="내 자료(PDF·유튜브·트레이딩뷰)에서 전략을 뽑아 도전자로 등록")
    ig.add_argument("ref", help="PDF 경로 · 유튜브 주소 · .pine · .txt/.md")
    ig.add_argument("--name", default="", help="전략 이름(생략 시 파일명)")
    ig.add_argument("--state-dir", default="", dest="state_dir",
                    help="명세를 저장할 곳(생략 시 ./specs_user)")
    ig.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="저장하지 않고 무엇이 뽑혔는지만 본다")
    ig.set_defaults(func=_cmd_ingest)

    pn = sub.add_parser(
        "pin",
        help="내 전략을 이 종목에 고정 — 심사와 무관하게 내 전략으로 매매"
             "(설치형 사용자용, 성적표 확인 + 타이핑 확인 필요)")
    pn.add_argument("--market", required=True)
    pn.add_argument("--symbol", required=True)
    pn.add_argument("--name", required=True, help="ingest로 저장한 전략 이름")
    pn.add_argument("--state-dir", default="state", dest="state_dir")
    pn.set_defaults(func=_cmd_pin)

    up = sub.add_parser("unpin", help="고정 해제 — 시스템 챔피언 판단이 즉시 복귀")
    up.add_argument("--market", required=True)
    up.add_argument("--symbol", required=True)
    up.add_argument("--state-dir", default="state", dest="state_dir")
    up.set_defaults(func=_cmd_unpin)

    ps = sub.add_parser("pins", help="지금 고정된 전략 목록")
    ps.add_argument("--state-dir", default="state", dest="state_dir")
    ps.set_defaults(func=_cmd_pins)

    gd = sub.add_parser(
        "guard",
        help="장중 감시 1회 — 지금 자산으로 낙폭을 재고 킬스위치를 즉시 적용")
    gd.add_argument("--state-dir", default="state", dest="state_dir")
    gd.add_argument("--state-file", default="portfolio_ALL.json",
                    dest="state_file")
    gd.set_defaults(func=_cmd_guard)

    wp = sub.add_parser(
        "web-passwd",
        help="웹 조종석 로그인 설정 — 아이디·비밀번호(해시로만 저장)")
    wp.set_defaults(func=_cmd_web_passwd)

    ir = sub.add_parser(
        "intraday-round",
        help="장중 도전자 1회 — 챔피언 규칙을 1시간봉에 적용하는 분리 실험"
             "(가상 USDT · 본 계좌와 무관)")
    ir.add_argument("--state-dir", default="state", dest="state_dir")
    ir.add_argument("--docs-dir", default="docs", dest="docs_dir")
    ir.set_defaults(func=_cmd_intraday_round)

    st = sub.add_parser("setup", help="API 키 대화형 설정(.env 저장 + 연결 확인)")
    st.set_defaults(func=_cmd_setup)

    wh = sub.add_parser(
        "webhook",
        help="트레이딩뷰 등 알림 웹훅 수신 → 주문 실행(기본 페이퍼, 비밀키 필수)")
    wh.add_argument("--market", default="crypto")
    wh.add_argument("--symbols", default=None,
                    help="허용 종목(쉼표 구분). 미지정 시 전체 허용")
    wh.add_argument("--timeframe", default="1h")
    wh.add_argument("--live", action="store_true", help="실거래(⚠️ 실제 자금)")
    wh.add_argument("--cash", type=float, default=10_000.0, help="페이퍼 초기자본")
    wh.add_argument("--host", default="0.0.0.0")
    wh.add_argument("--port", type=int, default=8100)
    wh.add_argument("--rebalance-band", type=float, default=0.02,
                    dest="rebalance_band")
    wh.add_argument("--max-weight", type=float, default=1.0, dest="max_weight",
                    help="신호당 최대 목표 비중(0~1)")
    wh.add_argument("--allow-short", action="store_true", dest="allow_short")
    wh.add_argument("--tradingview-ips", action="store_true", dest="tradingview_ips",
                    help="트레이딩뷰 공식 IP만 허용(권장)")
    wh.add_argument("--allow-ips", default=None, dest="allow_ips",
                    help="허용 발신 IP 목록(쉼표 구분). 리버스 프록시 뒤면 생략")
    wh.add_argument("--max-age", type=float, default=0.0, dest="max_age",
                    help=">0이면 payload timestamp가 이 초보다 오래되면 거부")
    wh.set_defaults(func=_cmd_webhook)

    jn = sub.add_parser("journal", help="봇 상태 파일에서 거래 성과 복기(거래 단위 통계)")
    # ⚠️ 기본값이 results/state.json이었다(감사 67). 그 파일은 개발용 `learn`
    #    봇이 쓰는 것이고, 실제로 돈을 굴리는 통합 계좌는
    #    state/paper/portfolio_ALL.json에 쌓인다. 즉 사장님이 `quant journal`을
    #    치면 매일 매매가 도는데도 "아직 완결된 거래가 없습니다"만 나왔다 —
    #    복기 도구가 실제 장부가 아닌 빈 파일을 보고 있었다.
    jn.add_argument("--state", default=_default_journal_state())
    jn.add_argument("--market", default="crypto")
    jn.set_defaults(func=_cmd_journal)
    cc = sub.add_parser(
        "costcheck",
        help="손익분기 비용 분석(수수료 스윕+손익분기) — 비용을 이기는지 확인")
    cc.add_argument("--market", default="crypto")
    cc.add_argument("--symbol", default="BTC/USDT")
    cc.add_argument("--timeframe", default="1d")
    cc.add_argument("--limit", type=int, default=500)
    cc.add_argument("--strategy", default="ma_cross")
    cc.set_defaults(func=_cmd_costcheck)

    cm = sub.add_parser(
        "compare",
        help="전략 A/B 유의성 검정 — 차이가 노이즈인지 실제 개선인지")
    cm.add_argument("--market", default="crypto")
    cm.add_argument("--symbol", default="BTC/USDT")
    cm.add_argument("--timeframe", default="1d")
    cm.add_argument("--limit", type=int, default=500)
    cm.add_argument("--strategy-a", default="ma_cross", dest="strategy_a")
    cm.add_argument("--strategy-b", default="momentum", dest="strategy_b")
    cm.set_defaults(func=_cmd_compare)

    pl = sub.add_parser("pipeline", help="백테스트+리포트+몬테카를로 통합 실행")
    pl.add_argument("--config", default=None)
    pl.set_defaults(func=_cmd_pipeline)

    return p


def main(argv=None) -> None:
    # .env 자동 로딩 — setup 마법사로 저장한 API 키를 매번 export하지 않아도
    # 모든 명령에서 쓸 수 있다. 셸에서 직접 export한 값이 항상 우선한다.
    from quant.utils.envfile import load_env_file
    load_env_file()

    # 사용자 전략 폴더(strategies_user/ 또는 QUANT_STRATEGY_DIR)를 불러와 등록한다.
    # 이러면 내 전략을 --strategy <이름>·validate·웹 드롭다운에서 바로 쓸 수 있다.
    try:
        from quant.strategies import load_user_strategies
        load_user_strategies()
    except Exception:  # noqa: BLE001 — 사용자 전략 오류가 CLI 전체를 막지 않게
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return
    # 배포본(QUANT_REQUIRE_LICENSE=1)에서만 정품 키를 강제한다. 개발·CI·테스트에선
    # 플래그 미설정이라 항상 통과하므로 지장이 없다. GUI(web)뿐 아니라 CLI 진입점도
    # 동일하게 게이팅해 라이선스 우회 경로를 막는다.
    from quant.licensing import require_license

    if not require_license():
        raise SystemExit(1)
    args.func(args)
