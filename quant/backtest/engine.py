"""백테스트 엔진 (bar-by-bar).

핵심 설계 원칙:
    1. 룩어헤드 편향 방지 — t 시점 종가로 계산한 신호는 t+1 시점부터 반영된다.
       (엔진은 '이번 봉 종가에 결정 → 다음 봉에 보유'를 명시적으로 처리)
    2. 현실 비용 반영 — 수수료 + 슬리피지를 회전율(turnover)에 비례해 차감.
    3. 경로 의존적 손절/익절 — 봉마다 진입가 대비 손익을 확인해 청산.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant.backtest.metrics import Metrics, compute_metrics
from quant.risk import RiskConfig, RiskManager
from quant.strategies.base import Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    positions: pd.Series
    metrics: Metrics
    df: pd.DataFrame
    benchmark: pd.Series | None = None  # 단순 매수후보유(buy & hold) 자본곡선

    @property
    def benchmark_return(self) -> float:
        """벤치마크(매수후보유) 총수익률."""
        if self.benchmark is None or len(self.benchmark) < 2:
            return 0.0
        return float(self.benchmark.iloc[-1] / self.benchmark.iloc[0] - 1.0)

    @property
    def excess_return(self) -> float:
        """전략 총수익률 − 벤치마크 총수익률 (초과수익). 음수면 그냥 보유가 나았다는 뜻."""
        return self.metrics.total_return - self.benchmark_return

    def summary(self) -> str:
        lines = [self.metrics.pretty()]
        if self.benchmark is not None:
            lines.append(f"매수후보유 : {self.benchmark_return:>10.2%}")
            verdict = "✅ 벤치마크 초과" if self.excess_return >= 0 else "⚠️ 벤치마크 하회"
            lines.append(f"초과수익   : {self.excess_return:>10.2%}  {verdict}")
        return "\n".join(lines)

    def trades(self) -> list:
        """자본곡선/포지션에서 추출한 개별 라운드트립 거래 목록."""
        from quant.backtest.trades import extract_trades

        return extract_trades(self.equity, self.positions)

    def trade_stats(self) -> dict:
        """거래 단위 통계(기대값·평균손익·거래별 이익팩터 등)."""
        from quant.backtest.trades import trade_stats

        return trade_stats(self.trades())

    def to_frame(self) -> pd.DataFrame:
        """자본곡선·수익률·포지션(·벤치마크)을 하나의 DataFrame으로 반환한다."""
        data = {
            "equity": self.equity,
            "returns": self.returns,
            "position": self.positions,
        }
        if self.benchmark is not None:
            data["benchmark"] = self.benchmark
        return pd.DataFrame(data)

    def to_csv(self, path: str) -> str:
        """결과를 CSV로 저장한다 (엑셀 등에서 추가 분석용). 저장 경로를 반환."""
        from pathlib import Path

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(out, index_label="time")
        return str(out)


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        risk: RiskManager | None = None,
        initial_capital: float = 10_000.0,
        fee: float = 0.001,        # 편도 수수료 0.1%
        slippage: float = 0.0005,  # 슬리피지 0.05%
        periods_per_year: int = 365,
        cost_model=None,
        vol_window: int = 20,
        dd_throttle: bool = False,
        dd_window: int = 50,
        dd_cut: float = 0.5,
        rebalance_band: float = 0.0,
        stop_cooldown: int = 0,
        dd_band: float = 0.0,
    ):
        from quant.backtest.costs import CostModel

        self.strategy = strategy
        self.risk = risk or RiskManager(RiskConfig(periods_per_year=periods_per_year))
        self.initial_capital = initial_capital
        self.fee = fee
        self.slippage = slippage
        self.periods_per_year = periods_per_year
        # cost_model 미지정 시 기존 fee/slippage로 구성 → 동작 하위 호환
        self.cost_model = cost_model or CostModel(fee=fee, slippage=slippage)
        self.vol_window = vol_window
        # 자산곡선 트레이딩: 실현 자산이 자체 이동평균(dd_window)을 하회하면
        # 익스포저를 dd_cut배로 줄인다(낙폭 국면에서 기계적으로 리스크 축소).
        self.dd_throttle = dd_throttle
        self.dd_window = max(2, dd_window)
        self.dd_cut = min(1.0, max(0.0, dd_cut))
        # ── 회전율 제거 3종 (기본 0 = 기존 동작과 비트 단위 동일) ──────────────
        # rebalance_band: |목표-현재| 비중 차가 이 밴드 미만이면 거래를 생략한다.
        #   vol targeting·앙상블 가중·proba 사이징은 매 봉 미세하게 달라지는데,
        #   그 미세 조정은 기대수익 0에 왕복비용만 확정 지불하는 거래다. 밴드는
        #   그 비용을 결정론적으로 환급한다(예측 개선이 아니라 비용 수학).
        #   권장 0.02~0.05. ⚠️ 밴드 폭을 그리드로 최적화하지 말 것(과최적화) —
        #   비용률에서 유도한 값으로 고정할 것. 청산(목표=0)은 밴드와 무관하게
        #   항상 실행된다(잔여 포지션이 영구히 남는 것 방지).
        self.rebalance_band = max(0.0, rebalance_band)
        # stop_cooldown: 손절/트레일링 발동 후 N봉 동안 재진입을 금지한다.
        #   신호가 그대로면 스톱 다음 봉에 즉시 같은 포지션으로 복귀해 '청산+재진입'
        #   왕복비용만 내는 채찍질(whipsaw)이 된다. 쿨다운은 그 확정 낭비를 막는다.
        self.stop_cooldown = max(0, int(stop_cooldown))
        # dd_band: 자산곡선 트로틀의 히스테리시스 밴드. 자본이 MA 근처에서 진동하면
        #   트로틀이 매 봉 0.5↔1.0으로 플립되어 |Δpos|=0.5×|want| 회전율 폭탄이
        #   된다. MA×(1-band) 하회 시 축소, MA×(1+band) 상회 시 복귀, 사이에서는
        #   직전 상태를 유지한다. 0이면 기존(즉시 전환) 동작.
        self.dd_band = max(0.0, dd_band)

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            raise ValueError("빈 데이터로 백테스트할 수 없습니다.")

        target = self.strategy.generate_signals(df)
        desired = self.risk.size_positions(df, target)

        close = df["close"].to_numpy()
        want = desired.to_numpy()
        cm = self.cost_model
        # 봉별 최근 변동성(변동성 비례 슬리피지·비용용)
        vol = (df["close"].pct_change().rolling(self.vol_window).std()
               .fillna(0.0).to_numpy())
        # 봉별 거래대금(시장충격 비용용). volume 컬럼이 없으면 충격 비용은 0으로
        # 과소추정됨을 인지할 것. 이 봉 자체의 거래대금을 쓰는 것은 체결 시점의
        # 유동성 근사이며 신호 생성에는 쓰이지 않으므로 룩어헤드가 아니다.
        dollar_vol = (
            (df["close"] * df["volume"]).to_numpy()
            if "volume" in df.columns else None
        )
        bar_ts = df.index  # 봉 타임스탬프(펀딩 실데이터 조회용)

        n = len(df)
        equity = np.empty(n)
        held = np.zeros(n)

        cash_equity = self.initial_capital
        pos = 0.0        # 현재 보유 비중
        entry = 0.0      # 진입가
        extreme = 0.0    # 보유 중 유리한 방향 극값(롱=최고가, 숏=최저가) — 트레일링용
        eq_hist: list[float] = []   # 자산곡선 트레이딩용 실현 자산 이력
        throttled = False           # dd_throttle 히스테리시스 상태(축소 국면 여부)
        cooldown = 0                # 스톱 발동 후 남은 재진입 금지 봉 수

        for i in range(n):
            price = close[i]

            # 1) 이전 봉에서 설정한 pos로 이번 봉 수익 실현
            if i > 0:
                bar_ret = price / close[i - 1] - 1.0
                cash_equity *= 1.0 + pos * bar_ret

            # 1-b) 봉당 보유 비용(펀딩·숏 차입) 차감 (음수면 펀딩 수취로 가산)
            if pos != 0.0:
                hold = cm.holding_cost(pos, vol[i], ts=bar_ts[i])
                if hold != 0.0:
                    cash_equity *= 1.0 - hold

            # 1-c) 자산곡선 트레이딩: 실현 자산이 자체 MA 하회 시 익스포저 축소.
            #      equity[i]까지의 '과거 실현' 자산만 사용 → 룩어헤드 없음.
            throttle = 1.0
            if self.dd_throttle:
                eq_hist.append(cash_equity)
                if len(eq_hist) >= self.dd_window:
                    ma = sum(eq_hist[-self.dd_window:]) / self.dd_window
                    if self.dd_band > 0.0:
                        # 히스테리시스: 하단 이탈 시 축소, 상단 회복 시 복귀,
                        # 밴드 안에서는 직전 상태 유지(플립플롭 회전율 방지)
                        if cash_equity < ma * (1.0 - self.dd_band):
                            throttled = True
                        elif cash_equity > ma * (1.0 + self.dd_band):
                            throttled = False
                        if throttled:
                            throttle = self.dd_cut
                    elif cash_equity < ma:
                        throttle = self.dd_cut

            # 2) 보유 중이면 유리한 극값 갱신 (트레일링 스톱 기준점)
            if pos > 0:
                extreme = max(extreme, price)
            elif pos < 0:
                extreme = min(extreme, price)

            # 3) 손절/익절/트레일링 확인 (경로 의존)
            pos_after = self.risk.apply_stops(pos, entry, price)
            pos_after = self.risk.apply_trailing_stop(pos_after, extreme, price)
            stop_triggered = pos_after != pos

            # 4) 다음 봉에 보유할 목표 결정 (자산곡선 트로틀 반영)
            new_pos = 0.0 if stop_triggered else float(want[i]) * throttle

            # 4-b) 스톱 쿨다운: 발동 직후 N봉은 신규 진입 금지. 상태 신호(예:
            #      ma_cross)는 스톱 다음 봉에도 같은 방향을 유지하므로, 쿨다운이
            #      없으면 '청산+재진입' 왕복비용만 내고 원위치하는 채찍질이 된다.
            if stop_triggered:
                cooldown = self.stop_cooldown
            elif cooldown > 0:
                new_pos = 0.0
                cooldown -= 1

            # 4-c) 리밸런스 데드밴드: 미세 조정 거래 생략(확정 비용 환급).
            #      청산(목표=0)은 항상 실행 — 밴드 밑 잔여 포지션이 영구히
            #      남는 것을 막는다. 진입·확대·축소만 밴드로 거른다.
            if (self.rebalance_band > 0.0 and new_pos != 0.0
                    and abs(new_pos - pos) < self.rebalance_band):
                new_pos = pos

            # 5) 회전율에 따른 거래비용 차감 (변동성 비례 슬리피지 + 시장충격)
            turnover = abs(new_pos - pos)
            if turnover > 1e-12:
                cost = cm.turnover_cost(turnover, vol[i])
                if dollar_vol is not None:
                    cost += cm.market_impact_cost(
                        turnover, cash_equity, dollar_vol[i])
                cash_equity *= 1.0 - cost
                if new_pos == 0.0:
                    entry = 0.0
                    extreme = 0.0
                elif pos == 0.0 or np.sign(new_pos) != np.sign(pos):
                    entry = price      # 신규 진입 또는 방향 전환
                    extreme = price    # 극값도 진입가로 초기화

            pos = new_pos
            equity[i] = cash_equity
            held[i] = pos

        equity_s = pd.Series(equity, index=df.index, name="equity")
        returns_s = equity_s.pct_change().fillna(0.0).rename("returns")
        positions_s = pd.Series(held, index=df.index, name="position")

        metrics = compute_metrics(
            equity_s, returns_s, positions_s, self.periods_per_year
        )
        # 매수후보유(buy & hold) 벤치마크: 첫 봉에 전액 매수해 그대로 보유
        benchmark = (self.initial_capital * df["close"] / df["close"].iloc[0]).rename(
            "benchmark"
        )
        return BacktestResult(
            equity_s, returns_s, positions_s, metrics, df, benchmark
        )
