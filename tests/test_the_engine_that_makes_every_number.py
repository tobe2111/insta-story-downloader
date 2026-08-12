"""엔진이 조용히 틀리면 모든 성적이 그 위에 쌓인다 (감사 184).

`quant/backtest/engine.py`는 **이 저장소의 모든 숫자가 나오는 자리**인데
변이 항목이 1건뿐이었다(1,813줄짜리 web/app.py와 함께 가장 얇은 축).
깊게 파 보니 결함 셋이 나왔다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① **신호와 봉이 어긋나도 그냥 계산했다.**

    want = desired.to_numpy()      # 인덱스 확인 없음

전략이 인덱스가 밀린 시리즈를 돌려주면 판다스가 `target * scale`에서
**합집합 인덱스**를 만들고, 그 배열을 봉 번호로 읽는다. 실측(하루 밀린
인덱스): 예외도 경고도 없이 총수익률 -7.32%. **그럴듯해서 사람이 못 잡는다.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
② **파산 바닥이 없었다.** 자본이 0 이하로 내려가도 계속 곱했다. 곱하는
   수가 음수면 **부호가 다시 뒤집힌다.** 실측:

       자산 10,000 → -20,000 → **+20,000**,  총수익률 **+100%**

   날아간 계좌가 두 배 번 것으로 보고된다. 그 사이 CAGR은 음수의 분수
   거듭제곱이라 NaN이고, 오디션은 NaN도 가짜 수익도 안 거른다 —
   **파산한 백테스트가 챔피언이 될 수 있다.**

   지금 설정(롱 온리·max_position 1.0)에서는 최악의 계수가 정확히 0이라
   닿지 않는다. 하지만 `--allow-short`는 지원되는 기능이고 `max_position`은
   CLI 인자다. 방어는 '지금 닿는 자리'가 아니라 '닿을 수 있는 자리'에 둔다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
③ **`next_open_fill`일 때 손절 기준가가 체결가가 아니라 결정가였다.**
   (이건 오디션 경로에 **실제로 켜져 있다.**)

   결정은 종가에 하고 체결은 다음 봉 시가에 하는데, 진입가는 결정 종가로
   적었다. 손절·익절·트레일링이 **한 번도 거래하지 않은 가격**을 기준으로
   재진다. 실측(불리 갭 5%, 손절선 -15%):

       예전:  체결가 대비 **-20.60%** 에서 발동
       지금:  체결가 대비 -15.63% (남는 0.63%는 봉 단위 판정의 이산성)

   갭이 유리한 날은 반대로 일찍 잘린다. 하필 **손절 정책을 오디션으로
   고르는** 시스템이라, 기준이 흔들리면 고르는 대상 자체가 흔들린다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.engine import Backtester  # noqa: E402
from quant.risk import RiskConfig, RiskManager  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402


class _Const(Strategy):
    name = "const"

    def __init__(self, v: float):
        self.v = v

    def generate_signals(self, df):
        return pd.Series(self.v, index=df.index)


def _frame(closes, opens=None):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    o = list(opens if opens is not None else closes)
    return pd.DataFrame(
        {"open": o,
         "high": [max(a, b) for a, b in zip(o, closes)],
         "low": [min(a, b) for a, b in zip(o, closes)],
         "close": list(closes), "volume": [1e9] * len(closes)}, index=idx)


def _fixed(**kw):
    return RiskManager(RiskConfig(sizing="fixed", max_position=1.0, **kw))


# ── ① 신호가 봉과 같은 줄에 서 있는가 ─────────────────────────


class _Shifted(Strategy):
    name = "shifted"

    def generate_signals(self, df):
        s = pd.Series(0.0, index=df.index)
        s.iloc[len(s) // 2:] = 1.0
        return s.shift(1, freq="D")          # 인덱스가 df와 어긋난다


def test_a_signal_that_does_not_line_up_with_the_bars_is_refused():
    """어긋난 채 계산하면 그럴듯한 오답이 나온다 — 사람이 잡을 수 없다."""
    df = _frame([100.0 + i for i in range(50)])
    with pytest.raises(ValueError, match="인덱스"):
        Backtester(_Shifted()).run(df)


def test_a_normally_aligned_signal_still_runs():
    """대조군 — 늘 거부하면 엔진이 통째로 죽는다."""
    df = _frame([100.0 + i for i in range(50)])
    got = Backtester(_Const(1.0), risk=_fixed(stop_loss=None)).run(df)
    assert len(got.equity) == len(df)
    assert got.metrics.total_return > 0


# ── ② 파산 바닥 ───────────────────────────────────────────────


def _blowup():
    """숏 보유 중 +300% → +200%. 옛 코드에서는 부호가 두 번 뒤집혔다."""
    return _frame([100.0] * 25 + [400.0, 1200.0] + [1200.0] * 3)


def test_a_wiped_out_account_is_not_reported_as_a_gain():
    got = Backtester(_Const(-1.0), risk=_fixed(stop_loss=None),
                     fee=0.0, slippage=0.0).run(_blowup())
    assert float(got.equity.min()) >= 0.0, (
        f"자산이 음수가 됐다 — 다음 봉에 곱하면 부호가 뒤집힌다: "
        f"{list(got.equity)[24:28]}")
    assert got.metrics.total_return == pytest.approx(-1.0), (
        f"파산인데 총수익률이 {got.metrics.total_return:.2%}다")


def test_a_ruined_account_stays_ruined_and_stops_trading():
    got = Backtester(_Const(-1.0), risk=_fixed(stop_loss=None),
                     fee=0.0, slippage=0.0).run(_blowup())
    tail = got.equity.iloc[26:]
    assert (tail == 0.0).all(), f"파산 후 자산이 되살아났다: {list(tail)}"
    assert (got.positions.iloc[26:] == 0.0).all(), "파산 후에도 포지션을 잡는다"


def test_the_metrics_of_a_ruined_run_are_numbers_not_nan():
    """NaN이면 오디션 정렬에서 조용히 이기거나 조용히 사라진다."""
    m = Backtester(_Const(-1.0), risk=_fixed(stop_loss=None),
                   fee=0.0, slippage=0.0).run(_blowup()).metrics
    for name in ("total_return", "cagr", "max_drawdown", "sharpe"):
        assert np.isfinite(getattr(m, name)), f"{name}이 NaN/inf다: {m}"
    assert m.max_drawdown == pytest.approx(-1.0)


def test_a_healthy_run_is_untouched_by_the_ruin_floor():
    """대조군 — 바닥을 깔았다고 정상 계좌가 달라지면 안 된다."""
    df = _frame([100.0 * (1.01 ** i) for i in range(60)])
    got = Backtester(_Const(1.0), risk=_fixed(stop_loss=None),
                     fee=0.0, slippage=0.0).run(df)
    assert float(got.equity.min()) > 0
    assert got.metrics.total_return == pytest.approx(
        df["close"].iloc[-1] / df["close"].iloc[0] - 1.0, rel=1e-6)


# ── ③ 진입가는 실제 체결가인가 ────────────────────────────────


class _EnterAndHold(Strategy):
    name = "enter"

    def generate_signals(self, df):
        s = pd.Series(0.0, index=df.index)
        s.iloc[5:] = 1.0
        return s


def _gap_frame(gap: float, n: int = 40):
    """봉 6의 시가가 봉 5 종가보다 gap만큼 벌어진 뒤 서서히 하락."""
    close = [100.0] * 6 + [100.0 * (0.98 ** i) for i in range(n - 6)]
    opens = list(close)
    opens[6] = close[5] * (1.0 + gap)
    return _frame(close, opens)


def _stop_loss_from_fill(gap: float) -> float:
    df = _gap_frame(gap)
    got = Backtester(_EnterAndHold(), risk=_fixed(stop_loss=0.15),
                     fee=0.0, slippage=0.0, next_open_fill=True).run(df)
    exit_i = next(i for i in range(6, len(df)) if got.positions.iloc[i] == 0.0)
    fill = float(df["open"].iloc[6])
    return float(df["close"].iloc[exit_i]) / fill - 1.0


def test_the_stop_is_measured_from_the_price_we_actually_paid():
    """불리한 갭에 산 날, 손절이 -15%가 아니라 -20.6%에서 걸렸다."""
    got = _stop_loss_from_fill(0.05)
    assert got == pytest.approx(-0.15, abs=0.02), (
        f"체결가 대비 {got:.2%}에서 손절됐다 — 결정가를 기준으로 재고 있다")


def test_a_favourable_gap_does_not_cut_the_position_early():
    """대조군 — 유리한 갭에서는 반대 방향으로 어긋난다(늦게가 아니라 일찍)."""
    got = _stop_loss_from_fill(-0.05)
    assert got == pytest.approx(-0.15, abs=0.02), (
        f"체결가 대비 {got:.2%}에서 손절됐다")


def test_without_next_open_fill_the_close_is_the_fill():
    """대조군 — 종가 체결 모델에서는 결정가가 곧 체결가라 달라지면 안 된다."""
    df = _gap_frame(0.05)
    got = Backtester(_EnterAndHold(), risk=_fixed(stop_loss=0.15),
                     fee=0.0, slippage=0.0, next_open_fill=False).run(df)
    exit_i = next(i for i in range(6, len(df)) if got.positions.iloc[i] == 0.0)
    entry = float(df["close"].iloc[5])
    assert float(df["close"].iloc[exit_i]) / entry - 1.0 == pytest.approx(
        -0.15, abs=0.02)
