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
    strat = default_ensemble() if args.strategy == "ensemble" else get_strategy(args.strategy)
    result = Backtester(strat, periods_per_year=_ppy(args.market)).run(df)
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

    strat = default_ensemble() if args.strategy == "ensemble" \
        else get_strategy(args.strategy)
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
    ln.add_argument("--strategy", default="ml")
    ln.add_argument("--timeframe", default="1d")
    ln.add_argument("--lookback", type=int, default=400)
    ln.add_argument("--accuracy-window", type=int, default=60, dest="accuracy_window")
    ln.add_argument("--cash", type=float, default=10_000.0)
    ln.add_argument("--cycles", type=int, default=0, help="0=무기한, N=N회 후 종료")
    ln.add_argument("--interval", type=int, default=3600, help="사이클 간격(초)")
    ln.add_argument("--state", default="results/autolearn_state.json")
    ln.set_defaults(func=_cmd_learn)

    pl = sub.add_parser("pipeline", help="백테스트+리포트+몬테카를로 통합 실행")
    pl.add_argument("--config", default=None)
    pl.set_defaults(func=_cmd_pipeline)

    return p


def main(argv=None) -> None:
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
