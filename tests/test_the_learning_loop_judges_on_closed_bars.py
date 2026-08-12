"""자동학습 루프도 **완성된 봉으로 판단하는가** (감사 151).

감사 71이 세운 규칙은 이것이다.

    완성된 정보로 판단하고, 지금 가격에 체결한다.

코인은 24시간 시장이라 UTC 일봉의 '오늘' 봉이 **항상** 진행 중이다.
실측(2026-08-07~09, 코인 5종목 15봉):

    종가가 확정 봉과 다른 봉 : 15 / 15
    고저 레인지 축소         : 평균 36.2% · 최대 88.6%

레인지가 36% 짧게 잡히면 변동성 추정이 낮아지고, 변동성 타깃 사이징의
**분모가 작아져 목표보다 큰 비중이 실린다.**

그런데 그 규칙은 `daily.py`에만 걸려 있었다. `AutoLearner`는 원본 프레임을
그대로 모델에 넣고 있었고, 거기서 나온 적중률이 대시보드에 그대로 나갔다.
같은 규칙이 경로마다 다르면 그 자체가 다음 결함이다(FROZEN_IDEAS ㉜).

무행동 밴드도 같다 — `daily.py`는 5%p 밴드를 쓰는데 이 루프는 밴드 없이
매 사이클 미세 조정을 냈다. 페이퍼라도 수수료를 계산에 넣는 이상 결과가
다르게 나온다.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.broker import PaperBroker  # noqa: E402
from quant.live.autolearn import AutoLearner  # noqa: E402
from quant.risk import RiskManager  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402


class _Recorder(Strategy):
    """모델이 **실제로 본 마지막 봉**을 기록하는 가짜 전략."""

    name = "recorder"

    def __init__(self):
        self.seen: list = []

    def generate_signals(self, df):
        self.seen.append(df.index[-1])
        return pd.Series(1.0, index=df.index)


def _frame_with_todays_bar() -> pd.DataFrame:
    """마지막 봉이 **오늘(진행 중)**인 UTC 일봉 — 코인 제공자가 주는 모양."""
    today = dt.datetime.now(dt.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    idx = pd.date_range(end=today, periods=200, freq="D")
    rng = np.random.default_rng(3)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.01, len(idx))))
    return pd.DataFrame({"open": close, "high": close * 1.02,
                         "low": close * 0.98, "close": close,
                         "volume": 1e6}, index=idx)


class _P:
    """고정 시세."""

    def __init__(self, df):
        self.df = df

    def get_ohlcv(self, *a, **k):
        return self.df.copy()


class _Wobbling(_Recorder):
    """사이클마다 **목표 비중**을 조금씩 흔드는 전략.

    ⚠️ 두 번 헛짚었다. 처음엔 고정 시세로 밴드를 확인하려 했는데, 목표
       수량이 한 번 맞으면 그다음부터 delta가 0이라 밴드가 있든 없든
       주문이 없었다. 그다음엔 **가격**을 흔들었는데 그것도 아니었다 —
       비중 1.0으로 꽉 찬 계좌는 가격이 60% 움직여도 목표 수량이 그대로다
       (목표 수량 = 비중 × 자산 ÷ 가격이고, 자산도 같은 비율로 움직인다).

       밴드가 재는 건 **비중의 변화**다. 그래서 신호를 흔든다.
    """

    def __init__(self, values):
        super().__init__()
        self.values = list(values)
        self.i = -1

    def generate_signals(self, df):
        self.seen.append(df.index[-1])
        self.i += 1
        return pd.Series(self.values[self.i % len(self.values)], index=df.index)


def _learner(df, market, strategy=None, **kw):
    return AutoLearner(data=_P(df), strategy=strategy or _Recorder(),
                       broker=PaperBroker(cash=1_000_000.0),
                       risk=RiskManager(), symbol="BTC/USDT",
                       market=market, **kw)


# ── 판단 프레임 ───────────────────────────────────────────────


def test_the_in_progress_bar_is_kept_out_of_the_model():
    df = _frame_with_todays_bar()
    lr = _learner(df, market="crypto")
    lr.cycle()

    seen = lr.strategy.seen[-1]
    assert seen != df.index[-1], (
        f"모델이 진행 중인 봉({seen})을 마지막 행으로 받았다 — 레인지가 "
        "36% 짧게 잡혀 변동성 타깃의 분모가 작아진다")
    assert seen == df.index[-2], f"한 봉만 빼야 한다 — {seen}"


def test_the_fill_price_is_still_the_current_price():
    """대조군 — 판단만 뒤로 물리고 **체결가는 지금 가격**이어야 한다.

    둘 다 뒤로 물리면 '어제 가격에 오늘 체결한 척'하는 백테스트가 된다.
    """
    df = _frame_with_todays_bar()
    lr = _learner(df, market="crypto")
    rec = lr.cycle()
    assert abs(rec["price"] - float(df["close"].iloc[-1])) < 1e-9, (
        f"체결가 {rec['price']}가 현재가 {float(df['close'].iloc[-1])}가 아니다")


def test_a_stock_frame_is_not_trimmed():
    """주식 제공자는 이미 미완결 봉을 버린다 — 여기서 또 빼면 하루를 잃는다."""
    df = _frame_with_todays_bar()
    lr = _learner(df, market="kr_stock")
    lr.cycle()
    assert lr.strategy.seen[-1] == df.index[-1], (
        "주식 프레임까지 잘라내면 가장 최신 정보를 버리는 것이다")


def test_without_a_market_it_warns_instead_of_pretending(caplog):
    """시장을 모르면 판정할 수 없다 — 조용히 옛 동작으로 돌아가면 안 된다."""
    df = _frame_with_todays_bar()
    lr = _learner(df, market=None)
    with caplog.at_level("WARNING"):
        lr.cycle()
    assert any("미완결" in r.message or "market" in r.message
               for r in caplog.records), (
        f"경고 없이 원본을 썼다 — 기록: {[r.message for r in caplog.records]}")


# ── 적중률이 판단과 같은 프레임에서 나오는가 ──────────────────


def test_the_hit_rate_is_measured_on_what_the_model_saw():
    """적중률을 다른 프레임으로 재면 '무엇을 보고 맞혔는지'가 어긋난다."""
    df = _frame_with_todays_bar()
    lr = _learner(df, market="crypto")
    rec = lr.cycle()
    # 판단 프레임 199봉 → '다음 봉 방향'을 아는 짝은 198개다.
    # 원본(200봉)으로 재면 199개가 되어, **모델이 못 본 진행 중인 봉의
    # 수익률로 성적을 하나 더 매긴다.** 실측 차이: n 198 vs 199,
    # 적중률 0.5354 vs 0.5377.
    assert rec["n"] == len(df) - 2, (
        f"적중률 표본이 {rec['n']}개 — 판단 프레임 199봉이면 198개여야 한다. "
        "모델이 못 본 봉으로 성적을 매기고 있다")


# ── 무행동 밴드 ───────────────────────────────────────────────


def test_the_loop_uses_the_same_rebalance_band_as_the_batch():
    """밴드가 없으면 매 사이클 잔조정으로 왕복 수수료만 확정 지불한다."""
    from quant.live.daily import REBALANCE_BAND

    df = _frame_with_todays_bar()
    # 비중 0.579 ↔ 0.596 (1.7%p) — 밴드 5%p 안에서만 흔들린다
    lr = _learner(df, market="crypto", strategy=_Wobbling([0.50, 0.52]))
    lr.cycle()
    before = len(lr.broker.order_log)
    assert before >= 1, "첫 사이클에서도 주문이 없으면 이 검사가 헛돈다"
    for _ in range(6):
        lr.cycle()
    after = len(lr.broker.order_log)
    assert after == before, (
        f"목표 비중이 밴드({REBALANCE_BAND:.0%}) 안에서만 흔들리는데 "
        f"{after - before}건을 더 냈다 — 밴드가 안 걸렸다")


def test_a_real_move_still_gets_through_the_band():
    """대조군 — 밴드가 진짜 변화까지 막으면 그건 덫이다."""
    df = _frame_with_todays_bar()
    # 비중 0.579 ↔ 1.000 (42%p) — 밴드를 훌쩍 넘는다
    lr = _learner(df, market="crypto", strategy=_Wobbling([0.50, 1.0]))
    lr.cycle()
    before = len(lr.broker.order_log)
    for _ in range(3):
        lr.cycle()
    assert len(lr.broker.order_log) > before, (
        "비중이 42%p 움직이는데도 주문이 안 나간다 — 밴드가 덫이 됐다")
