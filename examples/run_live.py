"""페이퍼/실거래 트레이딩 실행 예제.

사용법:
    # 페이퍼 트레이딩 (안전, 권장) — 5회 사이클만 데모
    python examples/run_live.py --paper --market crypto --symbol BTC/USDT --iters 5

    # 실거래 (⚠️ 실제 자금! 환경변수 EXCHANGE_API_KEY/EXCHANGE_SECRET 필요)
    python examples/run_live.py --live --symbol BTC/USDT
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.broker import get_broker
from quant.data import get_provider
from quant.live import LiveTrader
from quant.risk import RiskConfig, RiskManager
from quant.strategies import get_strategy


def main() -> None:
    p = argparse.ArgumentParser(description="퀀트 실시간/페이퍼 트레이딩")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--paper", action="store_true", help="페이퍼 트레이딩(기본)")
    mode.add_argument("--live", action="store_true", help="실거래 (주의!)")
    p.add_argument("--market", default="crypto")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--strategy", default="ma_cross")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--interval", type=int, default=3600, help="사이클 간격(초)")
    p.add_argument("--iters", type=int, default=None, help="반복 횟수(기본: 무한)")
    p.add_argument("--state", default="results/state.json", help="상태 저장 경로")
    p.add_argument("--dashboard", default="results/dashboard.html",
                   help="모니터링 대시보드 HTML 경로 (브라우저로 열어두면 30초마다 갱신)")
    args = p.parse_args()

    ppy = 365 if args.market in ("crypto", "synthetic") else 252
    data = get_provider(args.market)
    strategy = get_strategy(args.strategy)
    risk = RiskManager(RiskConfig(periods_per_year=ppy, stop_loss=0.15))

    # 시장 → 실거래 브로커 매핑
    _live_mode = {"crypto": "crypto_live", "us_stock": "us_live", "kr_stock": "kr_live"}

    if args.live:
        if args.market not in _live_mode:
            print(f"'{args.market}' 시장은 실거래를 지원하지 않습니다.")
            return
        confirm = input("⚠️ 실거래 모드입니다. 실제 자금이 사용됩니다. 계속? (yes 입력): ")
        if confirm.strip().lower() != "yes":
            print("취소되었습니다.")
            return
        broker = get_broker(_live_mode[args.market])
    else:
        broker = get_broker("paper", cash=args.capital)
        print("📝 페이퍼 트레이딩 모드 (실제 자금 사용 안 함)")

    trader = LiveTrader(
        data, strategy, broker, risk, args.symbol, args.timeframe,
        state_path=args.state, dashboard_path=args.dashboard,
        mode="live" if args.live else "paper",
    )
    print(f"📊 모니터링 대시보드: {args.dashboard} (브라우저로 열어두세요)")
    trader.run(interval_sec=args.interval, max_iters=args.iters)


if __name__ == "__main__":
    main()
