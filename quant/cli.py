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


def _ppy(market: str) -> int:
    return 365 if market in ("crypto", "synthetic") else 252


def _cmd_backtest(args) -> None:
    from quant.backtest import Backtester
    from quant.data import get_provider
    from quant.strategies import default_ensemble, get_strategy

    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe, limit=args.limit)

    # 데이터 품질 스캔 — 무결성 위반이 있으면 경고만 출력한다 (비파괴, 실행은 계속).
    # 오염된 데이터 위의 백테스트는 그럴듯한 거짓말이 되므로 먼저 알려준다.
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

    common = dict(timeframe=args.timeframe, lookback=args.lookback,
                  state_dir=args.state_dir,
                  require_real_data=not args.allow_synthetic)
    if args.all:
        from quant.live.daily import run_daily_portfolio
        from quant.markets import AUTO_TARGETS
        print(f"📅 매일 자동 페이퍼 — 전체 {len(AUTO_TARGETS)}종목 (챔피언 추종)")
        out = run_daily_paper_all(**common)
        lines = [f"  {k}: 자산 {r['equity']:,.0f} ({r['return_pct']:+.2f}%)"
                 for k, r in out["records"].items() if not r.get("skipped")]
        try:                                     # 통합 분산 계좌(실전과 가장 유사)
            prec = run_daily_portfolio(**common)
            if prec and not prec.get("skipped"):
                lines.append(f"  📦 통합 분산 계좌: 자산 {prec['equity']:,.0f} "
                             f"({prec['return_pct']:+.2f}%)")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 통합 포트폴리오 실패 — {exc}")
        if lines:
            _notify_extra("📅 만원 챌린지 오늘 기록\n" + "\n".join(lines)
                          + (f"\n⚠️ 실패: {', '.join(out['failed'])}"
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
    print("⚠️ 페이퍼(모의) 운용입니다 — 실제 돈이 오가지 않으며, "
          "결과가 좋아도 미래 수익 보장이 아닙니다.")


def _cmd_weekly(args) -> None:
    from quant.live.daily import format_weekly, weekly_summary

    text = format_weekly(weekly_summary(args.state_dir))
    print(text)
    if not args.no_notify:
        _notify_extra(text)


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

    from quant.data import get_provider
    from quant.optimize import cpcv, cpcv_report, walk_forward
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
    print(f"그리드: {grid}")

    # 1) 워크포워드 + DSR (다중검정 보정 샤프 신뢰도)
    print("\n[1/3] 워크포워드 (롤링 IS→OOS)")
    try:
        wf = walk_forward(df, strategy_cls, grid, is_window=args.is_window,
                          oos_window=args.oos_window, embargo=args.embargo,
                          periods_per_year=ppy)
        m = wf["oos_metrics"]
        print(f"  OOS 샤프 {m.sharpe:.2f} · 총수익 {m.total_return:.2%} · "
              f"최대낙폭 {m.max_drawdown:.2%} · 구간 {len(wf['segments'])}개")
        print(f"  DSR(시행 {wf['n_trials']}회 보정): {wf['dsr']:.2f} "
              f"{'— 실력 가능성' if wf['dsr'] >= 0.95 else '— 운일 수 있음(0.95 미만)'}")
    except ValueError as exc:
        print(f"  건너뜀: {exc}")

    # 2) PBO — IS 1등이 OOS에서 동전던지기인지
    print("\n[2/3] PBO (백테스트 과적합 확률)")
    try:
        mat = param_returns_matrix(df, strategy_cls, grid, periods_per_year=ppy)
        print("  " + pbo_report(pbo(mat, n_blocks=args.pbo_blocks))
              .replace("\n", "\n  "))
    except ValueError as exc:
        print(f"  건너뜀: {exc}")

    # 3) CPCV — 여러 OOS 경로의 분포
    print("\n[3/3] CPCV (다중 OOS 경로 분포)")
    try:
        cv = cpcv(df, strategy_cls, grid, n_groups=args.cpcv_groups,
                  n_test=2, embargo=args.embargo, periods_per_year=ppy)
        print("  " + cpcv_report(cv).replace("\n", "\n  "))
    except ValueError as exc:
        print(f"  건너뜀: {exc}")

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
    print("· 저장 위치: .env (git 미포함, 본인만 읽기 권한)")
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
    update_env_file(".env", updates)
    os.environ.update(updates)      # 이번 세션의 연결 확인에 바로 반영
    print(f"\n✅ {len(updates)}개 키를 .env에 저장했습니다 (권한 600, git 미포함).")

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
        df = provider.get_ohlcv(symbol, args.timeframe, limit=2)
        return float(df["close"].iloc[-1]) if len(df) else 0.0

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
    print("   ⚠️ 이 포트를 인터넷에 열 때는 HTTPS(리버스 프록시) 뒤에 두세요.")
    run_webhook_server(executor, host=args.host, port=args.port, secret=secret,
                       allow_ips=allow_ips, replay=True,
                       max_age_sec=args.max_age)


def _cmd_journal(args) -> None:
    """봇 상태 파일에서 실거래/페이퍼 성과를 복기한다(거래 단위 통계)."""
    from quant.live.journal import review_report, review_state_file

    review = review_state_file(args.state, periods_per_year=_ppy(args.market))
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
    result = ab_test(df, fa, fb, periods_per_year=ppy)
    print(compare_report(result))


def _cmd_pipeline(args) -> None:
    import runpy
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "examples" / "run_config.py"
    sys.argv = ["run_config.py"] + (["--config", args.config] if args.config else [])
    runpy.run_path(str(script), run_name="__main__")


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

    wk = sub.add_parser(
        "weekly",
        help="주간 요약 — 시장별 주간 수익·최악일·챔피언 교체 이력(텔레그램 전송)")
    wk.add_argument("--state-dir", default="state", dest="state_dir")
    wk.add_argument("--no-notify", action="store_true",
                    help="텔레그램 전송 없이 출력만")
    wk.set_defaults(func=_cmd_weekly)

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
    jn.add_argument("--state", default="results/state.json")
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
