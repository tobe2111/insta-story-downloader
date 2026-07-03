"""파라미터 민감도 스윕 → 히트맵 생성 예제.

두 파라미터(예: 단기MA × 장기MA)를 격자로 훑어 성과 지형을 그린다.
넓은 초록 고원이면 견고, 외딴 점이면 과최적화.

사용법:
    python examples/run_sweep.py
    python examples/run_sweep.py --market crypto --symbol BTC/USDT --objective calmar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import get_provider
from quant.optimize import sensitivity_grid
from quant.reporting import generate_heatmap
from quant.strategies import MovingAverageCross


def main() -> None:
    p = argparse.ArgumentParser(description="파라미터 민감도 히트맵")
    p.add_argument("--market", default="synthetic")
    p.add_argument("--symbol", default="DEMO")
    p.add_argument("--timeframe", default="1d")
    p.add_argument("--limit", type=int, default=800)
    p.add_argument("--objective", default="sharpe")
    p.add_argument("--out", default="results/heatmap.html")
    args = p.parse_args()

    ppy = 365 if args.market in ("crypto", "synthetic") else 252
    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe, limit=args.limit)

    fast_values = [5, 10, 15, 20, 30, 40]
    slow_values = [50, 60, 80, 100, 150, 200]

    grid = sensitivity_grid(
        df, MovingAverageCross,
        x_param="fast", x_values=fast_values,
        y_param="slow", y_values=slow_values,
        objective=args.objective, periods_per_year=ppy,
    )

    out = generate_heatmap(
        x_values=fast_values, y_values=slow_values, grid=grid,
        x_label="단기 MA(fast)", y_label="장기 MA(slow)",
        objective=args.objective,
        title=f"MA 교차 민감도 · {args.symbol}",
        path=args.out,
    )
    print(f"📊 히트맵 저장: {out}")
    print("💡 넓은 초록 고원 = 견고. 외딴 점 = 과최적화 위험.")


if __name__ == "__main__":
    main()
