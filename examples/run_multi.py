"""다중 종목 실시간 동시 운용 예제 (알림 + 견고한 주문 + 대시보드).

사용법:
    # 페이퍼 (안전) — 여러 코인 동시 운용, 3회 사이클 데모
    python examples/run_multi.py --paper --market crypto \
        --symbols BTC/USDT ETH/USDT SOL/USDT --iters 3

    # 실거래 (⚠️ 실제 자금)
    python examples/run_multi.py --live --market us_stock --symbols AAPL MSFT NVDA

알림을 켜려면 환경변수를 설정하세요:
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  또는  SLACK_WEBHOOK_URL
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import PaperBroker, RobustBroker, get_broker
from quant.data import get_provider
from quant.live import MultiTrader, get_notifier
from quant.strategies import default_ensemble


def main() -> None:
    p = argparse.ArgumentParser(description="다중 종목 실시간 운용")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--paper", action="store_true")
    mode.add_argument("--live", action="store_true")
    p.add_argument("--market", default="crypto")
    p.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--allocation", default="inverse_vol")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--interval", type=int, default=3600)
    p.add_argument("--iters", type=int, default=None)
    p.add_argument("--state", default="results/multi_state.json")
    p.add_argument("--dashboard", default="results/multi_dashboard.html")
    args = p.parse_args()

    _live_mode = {"crypto": "crypto_live", "us_stock": "us_live", "kr_stock": "kr_live"}
    notifier = get_notifier()

    if args.live:
        if args.market not in _live_mode:
            print(f"'{args.market}'는 실거래 미지원"); return
        if input("⚠️ 실거래 모드. 실제 자금이 사용됩니다. 계속? (yes): ").strip().lower() != "yes":
            print("취소됨"); return
        inner = get_broker(_live_mode[args.market])
        mode_label = "live"
    else:
        inner = PaperBroker(cash=args.capital)
        mode_label = "paper"
        print("📝 페이퍼 모드 (실제 자금 사용 안 함)")

    # 견고한 주문 래퍼 (재시도 + 최종 실패 시 알림)
    broker = RobustBroker(inner, retries=3, backoff=2.0, notifier=notifier)

    trader = MultiTrader(
        data=get_provider(args.market),
        strategy=default_ensemble(),
        broker=broker,
        symbols=args.symbols,
        timeframe=args.timeframe,
        allocation=args.allocation,
        state_path=args.state,
        dashboard_path=args.dashboard,
        notifier=notifier,
        mode=mode_label,
    )
    print(f"📊 대시보드: {args.dashboard} | 종목: {', '.join(args.symbols)}")
    trader.run(interval_sec=args.interval, max_iters=args.iters)


if __name__ == "__main__":
    main()
