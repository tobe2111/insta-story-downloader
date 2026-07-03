"""파라미터 최적화 + 워크포워드 검증 예제.

사용법:
    python examples/run_optimize.py
    python examples/run_optimize.py --market crypto --symbol BTC/USDT --strategy ma_cross

이 스크립트는 두 가지를 함께 보여준다:
    1) 전체 구간 그리드 서치 (in-sample 최적값) — 참고용
    2) 워크포워드 검증 (out-of-sample) — 실전에서 기대할 '진짜' 성과
IS 성적과 OOS 성적의 격차가 크다면, 그 전략은 과최적화된 것이다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data import get_provider
from quant.optimize import grid_search, walk_forward
from quant.strategies import MeanReversion, Momentum, MovingAverageCross

_STRATS = {
    "ma_cross": (MovingAverageCross, {"fast": [5, 10, 20], "slow": [40, 60, 120]}),
    "momentum": (Momentum, {"lookback": [30, 60, 90, 120]}),
    "mean_reversion": (MeanReversion, {"window": [10, 20, 30], "z": [1.5, 2.0, 2.5]}),
}


def main() -> None:
    p = argparse.ArgumentParser(description="파라미터 최적화 + 워크포워드 검증")
    p.add_argument("--market", default="synthetic")
    p.add_argument("--symbol", default="DEMO")
    p.add_argument("--timeframe", default="1d")
    p.add_argument("--limit", type=int, default=800)
    p.add_argument("--strategy", default="ma_cross", choices=list(_STRATS))
    p.add_argument("--objective", default="sharpe")
    p.add_argument("--is-window", type=int, default=250)
    p.add_argument("--oos-window", type=int, default=125)
    args = p.parse_args()

    ppy = 365 if args.market in ("crypto", "synthetic") else 252
    cls, grid = _STRATS[args.strategy]
    df = get_provider(args.market).get_ohlcv(args.symbol, args.timeframe, limit=args.limit)
    print(f"데이터: {len(df)}개 봉  전략: {args.strategy}")

    # 1) 전체 구간 그리드 서치 (참고 — 과최적화 위험!)
    gs = grid_search(df, cls, grid, objective=args.objective, periods_per_year=ppy)
    print("\n[1] 전체구간 최적 파라미터 (in-sample, 참고용)")
    print(f"    파라미터: {gs['best_params']}")
    print(f"    {args.objective}: {gs['best_score']:.3f}")

    # 2) 워크포워드 검증 (진짜 성과)
    wf = walk_forward(
        df, cls, grid,
        is_window=args.is_window, oos_window=args.oos_window,
        objective=args.objective, periods_per_year=ppy,
    )
    print("\n[2] 워크포워드 검증 결과 (out-of-sample, 진짜 성과)")
    print("-" * 32)
    print(wf["oos_metrics"].pretty())
    print("-" * 32)
    print(f"검증 구간 수: {len(wf['segments'])}")
    for seg in wf["segments"]:
        print(f"  {seg['oos_start'][:10]} | params={seg['params']} "
              f"| IS샤프={seg['is_sharpe']} → OOS샤프={seg['oos_sharpe']}")
    print("\n⚠️ IS와 OOS 격차가 크면 과최적화입니다. OOS 성적을 믿으세요.")


if __name__ == "__main__":
    main()
