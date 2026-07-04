"""거래 원장(trade ledger) — 자본곡선/포지션에서 개별 라운드트립 거래를 추출한다.

포지션이 0에서 벗어나면 진입, 0으로 돌아오거나 방향이 바뀌면 청산으로 본다.
각 거래의 손익은 보유 구간의 전략 자본곡선 비율로 계산하므로 사이징·비용이
모두 반영된다. 이렇게 뽑은 거래 단위 통계(기대값·평균손익·거래별 이익팩터)는
'한 번의 매매가 평균적으로 얼마를 버는가'를 알려준다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    side: str            # 'long' | 'short'
    return_pct: float    # 거래 손익률 (사이징·비용 반영)
    bars_held: int


def extract_trades(equity: pd.Series, positions: pd.Series) -> list[Trade]:
    """자본곡선과 포지션 시계열에서 라운드트립 거래 목록을 만든다."""
    pos = positions.to_numpy()
    eq = equity.to_numpy()
    idx = positions.index
    n = len(pos)
    trades: list[Trade] = []

    i = 0
    while i < n:
        if pos[i] == 0:
            i += 1
            continue
        side_sign = np.sign(pos[i])
        start = i
        while i < n and pos[i] != 0 and np.sign(pos[i]) == side_sign:
            i += 1
        end = i - 1  # 구간의 마지막 보유 봉

        # 엔진 규약: held[t]로 정한 포지션의 시장 손익은 t+1봉에 실현된다.
        # 따라서 마지막 보유봉(end)의 손익과 청산 비용은 eq[end+1]에 반영된다.
        # exit을 eq[end]로 잡으면 마지막 봉 손익·청산비용을 통째로 빠뜨린다.
        #
        # 진입 기준(entry_eq): 직전 봉이 '관망'이면 eq[start-1]을 써야 진입비용이
        # 포함된다. 하지만 직전 봉이 '반대 포지션'(플립: 롱→숏 등)이면 eq[start-1]→
        # eq[start] 구간은 이전 포지션의 마지막 방향성 손익이라 이전 거래 몫이다.
        # 그걸 이 거래에 넣으면 플립 봉이 두 거래에 이중 계상된다 → eq[start] 사용.
        flipped = start > 0 and pos[start - 1] != 0
        entry_eq = eq[start] if (start == 0 or flipped) else eq[start - 1]
        exit_eq = eq[end + 1] if end + 1 < n else eq[end]  # 데이터 끝이면 미실현
        ret = (exit_eq / entry_eq - 1.0) if entry_eq else 0.0
        trades.append(Trade(
            entry_time=str(idx[start]),
            exit_time=str(idx[end]),
            side="long" if side_sign > 0 else "short",
            return_pct=float(ret),
            bars_held=int(end - start + 1),
        ))
    return trades


def trade_stats(trades: list[Trade]) -> dict:
    """거래 목록에서 거래 단위 통계를 계산한다."""
    if not trades:
        return {"num_trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "expectancy": 0.0, "profit_factor": 0.0, "avg_bars_held": 0.0}

    rets = [t.return_pct for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    if gross_loss > 0:
        pf = gross_win / gross_loss
    else:
        pf = float("inf") if gross_win > 0 else 0.0

    return {
        "num_trades": len(trades),
        "win_rate": len(wins) / len(rets),
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
        "expectancy": sum(rets) / len(rets),   # 거래 1회당 평균 기대손익
        "profit_factor": pf,
        "avg_bars_held": sum(t.bars_held for t in trades) / len(trades),
    }


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    """거래 목록을 DataFrame으로 변환한다 (CSV 저장·분석용)."""
    return pd.DataFrame([asdict(t) for t in trades])
