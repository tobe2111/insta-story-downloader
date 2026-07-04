"""회전율 제거 3종 테스트 — 리밸런스 데드밴드·스톱 쿨다운·dd_throttle 히스테리시스.

이 장치들은 '예측 개선'이 아니라 '확정 비용 환급'이다: 기대수익 0인 미세 조정
거래를 생략해 왕복비용을 아낀다. 검증도 그에 맞게 — 회전율(거래 수)이 실제로
줄고, 기본값(0)에서는 기존 결과와 비트 단위로 동일한지를 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.backtest import Backtester
from quant.data import SyntheticDataProvider
from quant.risk import RiskConfig, RiskManager
from quant.strategies.base import Strategy

_DF = SyntheticDataProvider(seed=42).get_ohlcv("TR", "1d", limit=400)


class _Jitter(Strategy):
    """매 봉 목표 비중이 미세하게 흔들리는 전략(vol targeting·proba 사이징 모사)."""
    name = "jitter"
    allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        rng = np.random.default_rng(3)
        w = 0.6 + 0.01 * rng.standard_normal(len(df))   # 0.6 근처 ±1% 지터
        return pd.Series(np.clip(w, 0.0, 1.0), index=df.index)


def _no_stop_risk():
    return RiskManager(RiskConfig(stop_loss=None, take_profit=None,
                                  trailing_stop=None, sizing="fixed"))


def _num_trades(res) -> int:
    return int((res.positions.diff().fillna(res.positions) != 0).sum())


# ── 데드밴드 ─────────────────────────────────────────────────────────────────

def test_band_zero_is_bit_identical():
    """rebalance_band=0(기본)은 기존 결과와 비트 단위로 동일하다."""
    a = Backtester(_Jitter(), risk=_no_stop_risk()).run(_DF)
    b = Backtester(_Jitter(), risk=_no_stop_risk(), rebalance_band=0.0).run(_DF)
    assert (a.equity.to_numpy() == b.equity.to_numpy()).all()
    assert (a.positions.to_numpy() == b.positions.to_numpy()).all()


def test_band_cuts_turnover_and_saves_cost():
    """지터 전략에서 밴드는 거래 수를 줄이고, 최종 자산을 늘린다(비용 환급)."""
    base = Backtester(_Jitter(), risk=_no_stop_risk()).run(_DF)
    band = Backtester(_Jitter(), risk=_no_stop_risk(), rebalance_band=0.05).run(_DF)
    assert _num_trades(band) < _num_trades(base)
    # 지터는 정보가 없으므로 밴드가 아끼는 비용이 그대로 남는다
    assert band.equity.iloc[-1] > base.equity.iloc[-1]


def test_band_exit_always_executes():
    """청산(목표=0)은 밴드보다 작아도 반드시 실행된다(잔여 포지션 방지)."""
    class TinyThenExit(Strategy):
        name = "tiny"
        allow_short = False

        def generate_signals(self, df):
            w = np.zeros(len(df))
            w[10:20] = 0.5       # 진입
            w[20:25] = 0.03      # 밴드(0.05)보다 작은 목표로 축소
            # 25부터 0 → 청산은 반드시 일어나야 한다
            return pd.Series(w, index=df.index)

    res = Backtester(TinyThenExit(), risk=_no_stop_risk(),
                     rebalance_band=0.05).run(_DF)
    assert res.positions.iloc[30:].abs().max() == 0.0   # 잔여 포지션 없음


# ── 스톱 쿨다운 ──────────────────────────────────────────────────────────────

def _crash_df():
    """상승 후 급락하는 결정론적 가격 — 스톱을 확실히 발동시킨다."""
    n = 120
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    price = np.concatenate([
        np.linspace(100, 130, 40),
        np.linspace(130, 80, 20),     # -38% 급락 → stop_loss=0.15 발동
        np.linspace(80, 90, 60),
    ])
    return pd.DataFrame({"open": price, "high": price * 1.005,
                         "low": price * 0.995, "close": price,
                         "volume": 1.0}, index=idx)


class _AlwaysLong(Strategy):
    name = "always"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def test_cooldown_blocks_reentry():
    """쿨다운 N봉 동안은 스톱 발동 후 재진입하지 않는다."""
    d = _crash_df()
    risk = RiskManager(RiskConfig(stop_loss=0.15, take_profit=None,
                                  trailing_stop=None, sizing="fixed"))
    no_cd = Backtester(_AlwaysLong(), risk=risk, stop_cooldown=0).run(d)
    cd = Backtester(_AlwaysLong(), risk=risk, stop_cooldown=10).run(d)

    pos_no, pos_cd = no_cd.positions.to_numpy(), cd.positions.to_numpy()
    stops = [i for i in range(1, len(d)) if pos_no[i - 1] != 0 and pos_no[i] == 0]
    assert stops, "스톱이 발동해야 하는 시나리오"
    s = stops[0]
    # 쿨다운 없음: 신호가 항상 1이므로 다음 봉 즉시 재진입(채찍질)
    assert pos_no[s + 1] != 0.0
    # 쿨다운 10봉: s+1..s+10 동안 관망
    assert (pos_cd[s + 1: s + 11] == 0.0).all()
    # 쿨다운은 거래 수를 줄인다(재진입 채찍질 제거)
    assert _num_trades(cd) <= _num_trades(no_cd)


def test_cooldown_zero_is_bit_identical():
    d = _crash_df()
    risk = RiskManager(RiskConfig(stop_loss=0.15, sizing="fixed"))
    a = Backtester(_AlwaysLong(), risk=risk).run(d)
    b = Backtester(_AlwaysLong(), risk=risk, stop_cooldown=0).run(d)
    assert (a.equity.to_numpy() == b.equity.to_numpy()).all()


# ── dd_throttle 히스테리시스 ─────────────────────────────────────────────────

def test_dd_band_reduces_throttle_flips():
    """히스테리시스 밴드는 자본이 MA 근처에서 진동할 때 포지션 플립을 줄인다."""
    kw = dict(risk=_no_stop_risk(), dd_throttle=True, dd_window=20)
    flat = Backtester(_Jitter(), **kw).run(_DF)
    hyst = Backtester(_Jitter(), **kw, dd_band=0.01).run(_DF)
    # 트로틀 전환 = 포지션이 0.5배 스케일을 오가는 것 → 큰 |Δpos| 개수로 근사
    def flips(res):
        d = res.positions.diff().abs()
        return int((d > 0.2).sum())     # 0.6→0.3 스케일 전환급 변화만 센다
    assert flips(hyst) <= flips(flat)


def test_dd_band_zero_is_bit_identical():
    kw = dict(risk=_no_stop_risk(), dd_throttle=True, dd_window=20)
    a = Backtester(_Jitter(), **kw).run(_DF)
    b = Backtester(_Jitter(), **kw, dd_band=0.0).run(_DF)
    assert (a.equity.to_numpy() == b.equity.to_numpy()).all()


# ── 브로커/포트폴리오 데드밴드 ───────────────────────────────────────────────

def test_broker_target_weight_band_skips_small_adjust():
    from quant.broker import PaperBroker

    b = PaperBroker(cash=10_000, fee=0.0)
    b.market_order("X", "buy", 50, 100.0)          # 비중 0.5 보유
    # 목표 0.51 → |Δ|=0.01 < 밴드 0.02 → 주문 생략
    assert b.target_weight("X", 0.51, 100.0, 10_000.0,
                           rebalance_band=0.02) is None
    # 목표 0.6 → |Δ|=0.1 ≥ 밴드 → 주문 실행
    assert b.target_weight("X", 0.6, 100.0, 10_000.0,
                           rebalance_band=0.02) is not None
    # 청산은 밴드보다 작아도 실행
    b2 = PaperBroker(cash=10_000, fee=0.0)
    b2.market_order("Y", "buy", 1, 100.0)          # 비중 0.01
    assert b2.target_weight("Y", 0.0, 100.0, 10_000.0,
                            rebalance_band=0.05) is not None


def test_portfolio_band_reduces_turnover():
    from quant.portfolio import PortfolioBacktester
    from quant.strategies import MovingAverageCross

    data = {s: SyntheticDataProvider(seed=i).get_ohlcv(s, "1d", limit=300)
            for i, s in enumerate(["A", "B", "C"])}
    base = PortfolioBacktester(MovingAverageCross(), allocation="inverse_vol").run(data)
    band = PortfolioBacktester(MovingAverageCross(), allocation="inverse_vol",
                               rebalance_band=0.03).run(data)
    # 종목별 |Δ비중| 합(실제 비용이 부과되는 회전율)으로 비교한다. 총노출의
    # 변동은 종목 간 상쇄로 밴드 적용 시 오히려 늘 수도 있어 대용으로 부적합.
    # 밴드 경로의 체결 점프는 (삼각부등식) 목표 이동 합을 넘지 못하므로 항상 ≤.
    assert float(band.turnover.sum()) <= float(base.turnover.sum())
    # 기본값(0)은 기존과 동일
    zero = PortfolioBacktester(MovingAverageCross(), allocation="inverse_vol",
                               rebalance_band=0.0).run(data)
    assert (zero.equity.to_numpy() == base.equity.to_numpy()).all()
