"""백테스트 엔진 (bar-by-bar).

핵심 설계 원칙:
    1. 룩어헤드 편향 방지 — t 시점 종가로 계산한 신호는 t+1 시점부터 반영된다.
       (엔진은 '이번 봉 종가에 결정 → 다음 봉에 보유'를 명시적으로 처리)
    2. 현실 비용 반영 — 수수료 + 슬리피지를 회전율(turnover)에 비례해 차감.
    3. 경로 의존적 손절/익절 — 봉마다 진입가 대비 손익을 확인해 청산.
"""
from __future__ import annotations

import math
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
        intrabar_stops: bool = False,
        next_open_fill: bool = False,
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
        # next_open_fill: 종가에 결정한 비중 변화를 '다음 봉 시가'에 체결한다.
        #
        #   실제 페이퍼·실거래는 주식을 다음 세션 시가에만 체결한다(v0.5.0 회계).
        #   그런데 백테스트는 종가 체결이라, 종가→다음 시가의 개장 갭을 공짜로
        #   건너뛴다. 실측된 그 갭은 한국주식 기준 불리 방향 평균 79bp였다 —
        #   가정 수수료(14bp)의 5배가 넘는데 오디션은 이를 전혀 물지 않았다.
        #   그 결과 '챔피언을 뽑는 세계'가 '돈이 도는 세계'보다 낙관적이었고,
        #   특히 고회전 전략이 부당하게 유리하게 평가됐다(2026-08-11 발견).
        #
        #   구현: 직전 봉에서 결정된 변화분만 시가 기준으로 수익을 계산하고,
        #   기존 보유분은 그대로 종가 기준을 쓴다. 새로 산 몫만 갭을 겪는 것이
        #   현실과 같다. open 컬럼이 없으면 조용히 기존(종가) 동작으로 폴백한다.
        self.next_open_fill = bool(next_open_fill)
        # intrabar_stops: 손절/익절을 봉 '안'의 고저가로 판정하고 스톱 가격에
        #   체결한다(기본 False=기존 종가 판정). 종가 판정은 봉 중간에 스톱선을
        #   관통했다가 종가가 회복하면 스톱을 놓쳐 손실을 과소평가한다 — 실전
        #   스톱 주문은 관통 즉시 체결되므로 켜는 쪽이 더 정직하다. 규칙:
        #   · 손절: 저가(롱)/고가(숏)가 관통 시 스톱 가격 체결, 갭 통과 시
        #     시가 체결(더 불리한 쪽 — 보수적)
        #   · 익절: 목표가 정확히 체결(갭 이익은 반영하지 않음 — 보수적)
        #   · 같은 봉에서 손절·익절 모두 관통하면 순서를 알 수 없으므로 손절 우선
        #   · 트레일링 스톱은 봉 내 극값 갱신 순서가 모호해 기존대로 종가 판정
        self.intrabar_stops = bool(intrabar_stops)

    def _intrabar_stop_fill(self, pos: float, entry: float,
                            o: float, h: float, low_: float) -> float | None:
        """봉 내 손절/익절 관통 여부를 판정해 체결가를 반환한다(미관통 None)."""
        cfg = self.risk.config
        if pos > 0:
            if cfg.stop_loss is not None:
                s = entry * (1.0 - cfg.stop_loss)
                if low_ <= s:
                    return min(o, s)          # 갭 하락이면 시가(더 불리) 체결
            if cfg.take_profit is not None:
                t = entry * (1.0 + cfg.take_profit)
                if h >= t:
                    return t                  # 갭 상승 이익은 반영하지 않음
        elif pos < 0:
            if cfg.stop_loss is not None:
                s = entry * (1.0 + cfg.stop_loss)
                if h >= s:
                    return max(o, s)          # 갭 상승이면 시가(더 불리) 체결
            if cfg.take_profit is not None:
                t = entry * (1.0 - cfg.take_profit)
                if low_ <= t:
                    return t
        return None

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            raise ValueError("빈 데이터로 백테스트할 수 없습니다.")

        target = self.strategy.generate_signals(df)
        desired = self.risk.size_positions(df, target)

        # ⚠️ **신호가 봉과 같은 줄에 서 있는지 확인한다**(감사 184). 예전에는
        #    `desired.to_numpy()`를 그냥 인덱싱했다. 전략이 인덱스가 어긋난
        #    시리즈를 돌려주면 판다스가 `target * scale`에서 **합집합 인덱스**를
        #    만들고, 그 배열을 봉 번호로 읽어 **신호와 봉이 어긋난 채** 계산된다.
        #
        #    실측(하루 밀린 인덱스): 예외도 경고도 없이 총수익률 -7.32%가 나왔다.
        #    그럴듯한 숫자라 사람이 알아챌 방법이 없다.
        #
        #    이 엔진은 **이 저장소의 모든 성적이 나오는 자리**다. 여기서 조용히
        #    어긋나면 오디션·챔피언 선정·사이트 숫자가 전부 그 위에 쌓인다.
        #    외부 피처를 붙이다 reindex 한 번 잘못하면 생기는 일이라, 믿지 않고
        #    확인한다.
        if not desired.index.equals(df.index):
            raise ValueError(
                f"전략 신호의 인덱스가 봉과 다릅니다(신호 {len(desired)}개 · "
                f"봉 {len(df)}개) — 어긋난 채 계산하면 그럴듯한 오답이 나옵니다.")

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
        # 시가 배열은 봉내 스톱과 '다음 시가 체결' 양쪽이 쓴다
        open_ = df["open"].to_numpy() if "open" in df.columns else None
        use_next_open = self.next_open_fill and open_ is not None
        if self.intrabar_stops:
            high = df["high"].to_numpy()
            low = df["low"].to_numpy()

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
        pending_delta = 0.0         # 직전 봉 결정분 — 이번 봉 시가에 체결된다
        pending_entry = False       # 진입가를 이번 봉 시가로 확정해야 하는가
        ruined = False              # 자본이 0 이하로 소진됐는가(회복 불가)

        for i in range(n):
            # 파산한 계좌는 **아무 일도 하지 않는다**(감사 234에서 보강).
            # 예전에는 파산 뒤에도 루프 본문을 계속 돌았고, 보유 0에 무한대
            # 수익률이 곱해져(`0 * inf`) 자본이 NaN이 됐다 — 종가가 0인
            # 프레임에서 실제로 그랬다. 파산은 파산으로 남아야 한다.
            if ruined:
                equity[i] = 0.0
                held[i] = 0.0
                continue
            price = close[i]

            # 0-a) **진입가는 실제 체결가여야 한다**(감사 184). `next_open_fill`은
            #      결정을 종가에 하고 체결은 다음 봉 시가에 한다. 그런데 진입가는
            #      결정 종가로 적어 두고 있었다 — 손절·익절·트레일링이 **한 번도
            #      거래하지 않은 가격**을 기준으로 재진다.
            #
            #      실측(불리 갭 5%, 손절선 -15%): 손절이 체결가 대비 **-20.6%**
            #      에서 발동했다. 갭이 유리한 날은 반대로 일찍 잘린다. 즉 손절선
            #      숫자가 뜻대로 동작하지 않고, 그 오차의 크기는 갭 분포를 따른다
            #      (이 저장소가 실측한 한국주식 평균 불리 갭 79bp).
            #
            #      하필 손절 정책을 오디션으로 고르는 시스템이다 — 기준이 흔들리면
            #      고르는 대상 자체가 흔들린다. 갭을 비용으로 물기로 한 기능인데
            #      정작 스톱은 갭 이전 가격을 보고 있었다.
            if pending_entry:
                if use_next_open and open_[i] > 0 and pos != 0.0:
                    entry = open_[i]
                    extreme = open_[i]
                pending_entry = False

            # 0) 봉 내 손절/익절 (옵션): 고저가가 스톱선을 관통하면 그 자리에서
            #    체결한다. 종가까지의 나머지 움직임은 겪지 않는다(이미 청산).
            intrabar_exit = False
            if self.intrabar_stops and pos != 0.0 and entry > 0.0 and i > 0:
                fill = self._intrabar_stop_fill(pos, entry, open_[i], high[i], low[i])
                if fill is not None and fill > 0.0:
                    # 시가 체결 모델과 함께 쓸 때: 이 봉 시가에 체결된 몫
                    # (pending_delta)은 종가가 아니라 **시가**가 출발점이다.
                    # 예전에는 전량을 close[i-1] 기준으로 계산하고 pending을
                    # 지우지 않아, 아래 1)에서 이미 청산된 포지션에 손익이
                    # 한 번 더 붙었다(2026-08-11 감사에서 발견한 잠재 결함 —
                    # intrabar_stops는 수동 백테스트에서만 켜져 실전 경로에는
                    # 닿지 않았지만, 켜는 순간 숫자가 틀린다).
                    if (use_next_open and abs(pending_delta) > 1e-12
                            and open_[i] > 0):
                        held_before = pos - pending_delta
                        cash_equity *= 1.0 + (
                            held_before * (fill / close[i - 1] - 1.0)
                            + pending_delta * (fill / open_[i] - 1.0))
                    else:
                        cash_equity *= 1.0 + pos * (fill / close[i - 1] - 1.0)
                    exit_cost = cm.turnover_cost(abs(pos), vol[i], price=fill)
                    if dollar_vol is not None:
                        exit_cost += cm.market_impact_cost(
                            abs(pos), cash_equity, dollar_vol[i])
                    cash_equity *= 1.0 - exit_cost
                    pos = 0.0
                    entry = 0.0
                    extreme = 0.0
                    intrabar_exit = True
                    pending_delta = 0.0     # 이미 체결·청산됐다 — 재계상 금지

            # 1) 이전 봉에서 설정한 pos로 이번 봉 수익 실현
            #    (봉 내 청산 시 pos=0이라 자연히 건너뜀 — 부분 수익은 이미 반영)
            if i > 0:
                if (use_next_open and abs(pending_delta) > 1e-12
                        and open_[i] > 0):
                    # 다음 시가 체결: 직전부터 들고 있던 몫은 종가→종가,
                    # 어제 결정해 오늘 시가에 체결된 몫은 시가→종가.
                    held_before = pos - pending_delta
                    cash_equity *= 1.0 + (
                        held_before * (price / close[i - 1] - 1.0)
                        + pending_delta * (price / open_[i] - 1.0))
                else:
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

            # 3) 손절/익절/트레일링 확인 (경로 의존).
            #    intrabar_stops면 고정 손절/익절은 0)에서 이미 처리 — 여기서는
            #    트레일링(종가 판정)만 실질 작동한다(관통 안 한 SL/TP는 종가로도
            #    관통 불가: close ∈ [low, high]).
            pos_after = self.risk.apply_stops(pos, entry, price)
            pos_after = self.risk.apply_trailing_stop(pos_after, extreme, price)
            stop_triggered = (pos_after != pos) or intrabar_exit

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
                cost = cm.turnover_cost(turnover, vol[i], price=price)
                if dollar_vol is not None:
                    cost += cm.market_impact_cost(
                        turnover, cash_equity, dollar_vol[i])
                cash_equity *= 1.0 - cost
                if new_pos == 0.0:
                    entry = 0.0
                    extreme = 0.0
                elif pos == 0.0 or np.sign(new_pos) != np.sign(pos):
                    entry = price      # 신규 진입 또는 방향 전환(임시 — 아래 참조)
                    extreme = price    # 극값도 진입가로 초기화
                    # 다음 봉 시가에 체결된다면 진입가는 그 시가다(감사 184).
                    pending_entry = use_next_open

            # 이번 봉에서 결정된 변화분은 다음 봉 시가에 체결된다(모델링용)
            pending_delta = new_pos - pos
            pos = new_pos

            # 6) **파산 바닥**(감사 184). 자본이 0 이하로 내려가면 그 계좌는 끝이다.
            #    예전에는 음수 자산을 그대로 다음 봉 수익률에 곱했다. 곱하는 수가
            #    음수면 **부호가 다시 뒤집힌다** — 실측: 자산 10,000 → -20,000 →
            #    **+20,000**, 총수익률 **+100%**. 날아간 계좌가 두 배 번 것으로
            #    보고된다. 게다가 그 사이 CAGR은 음수의 분수 거듭제곱이라 NaN이고,
            #    오디션은 NaN·가짜 수익을 걸러내지 않는다 — **파산한 백테스트가
            #    챔피언이 될 수 있다.**
            #
            #    지금 설정(롱 온리·max_position 1.0)에서는 최악의 계수가 정확히
            #    0이라 여기 닿지 않는다. 하지만 `--allow-short`는 지원되는 기능이고
            #    `max_position`은 CLI 인자다 — 둘 중 하나만 켜면 닿는다. 방어는
            #    '지금 닿는 자리'가 아니라 '닿을 수 있는 자리'에 둔다.
            #
            #    ⚠️ **NaN·inf는 파산이 아니다**(2026-08-14 감사 234). 위 판정은
            #    `cash_equity <= 0.0`인데, NaN도 inf도 그 비교에서 False라
            #    **그대로 통과한다.** 실측(종가 한 칸이 NaN인 프레임):
            #
            #        자본곡선 60칸 중 30칸이 NaN · 최종 자산 nan
            #        그런데 보고된 총수익률은 **-10.77%** — 그럴듯한 숫자다
            #
            #    (`compute_metrics`가 NaN 구간을 조용히 버리고 남은 것으로
            #    성적을 냈다. 그쪽도 함께 고쳤다.) inf면 총수익률이 +inf로
            #    나온다. 어느 쪽이든 오디션은 이 후보를 정상으로 받아들인다 —
            #    바로 위 문단이 경고한 '파산한 백테스트가 챔피언이 된다'가
            #    NaN 버전으로 그대로 남아 있었던 셈이다.
            #
            #    0으로 눌러 '파산'으로 처리하지 않는다 — 그건 계산이 망가진
            #    것을 손실로 둔갑시키는 것이다. 낼 수 없는 성적은 내지 않는다.
            if not math.isfinite(cash_equity):
                raise ValueError(
                    f"백테스트 자본이 계산 불가 값이 됐습니다({cash_equity}) — "
                    f"{i}번째 봉. 가격·비용에 NaN·inf가 섞였습니다. 그 구간을 "
                    "버리고 성적을 내면 그럴듯한 오답이 나옵니다.")
            if not ruined and cash_equity <= 0.0:
                ruined = True
            if ruined:
                cash_equity = 0.0
                pos = 0.0
                pending_delta = 0.0
                pending_entry = False
                entry = 0.0
                extreme = 0.0

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
