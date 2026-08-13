"""전략 신호기 8종의 계약을 못 박는다 (감사 169).

전수조사에서 이 여덟 파일을 같은 눈으로 훑었다. **결함은 못 찾았다.**
그 사실 자체를 여기에 적어 둔다 — "안 봤다"와 "보고 깨끗했다"는 다르다.

확인한 것

  ① 인과성(룩어헤드 없음) — 시계열을 중간에서 자르고 다시 계산했을 때
     앞부분 신호가 한 봉도 달라지지 않는가. 8종 × 롱/숏 = 16가지 모두 통과.
     이게 이 가족에서 돈이 걸린 유일한 성질이다.
  ② 거래정지 구간(가격이 완전히 멈춘 20봉)에서 신호가 폭주하지 않는가.
  ③ 각 전략이 **자기 규칙대로** 신호를 내는가 — 아래 손으로 만든 자료로.
  ④ allow_short=False일 때 절대 음수 비중이 나오지 않는가.

③이 핵심이다. 이 파일들에는 지금까지 변이 시험이 한 건도 없었다. 즉
누가 부등호를 뒤집어도 스위트가 초록이었다. 규칙을 손으로 아는 자료로
고정해 두면, 규칙이 바뀌는 순간 검사가 깨진다.

기본 파라미터(레지스트리 기준)를 그대로 쓴다 — 실제로 도는 설정이 아니면
고정할 값어치가 없다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies import get_strategy, list_strategies  # noqa: E402

NAMES = [n for n in list_strategies() if n != "ml"]


def _frame(close: list[float] | np.ndarray, span: float = 0.004) -> pd.DataFrame:
    c = pd.Series(np.asarray(close, dtype=float),
                  index=pd.date_range("2024-01-01", periods=len(close), freq="D"))
    return pd.DataFrame({"open": c, "high": c * (1 + span), "low": c * (1 - span),
                         "close": c, "volume": 1e6}, index=c.index)


def _ramp(n: int, rate: float, start: float = 100.0) -> list[float]:
    return [start * (1.0 + rate) ** i for i in range(n)]


# ── ① 인과성: 과거 신호가 미래 데이터에 안 흔들리는가 ─────────


@pytest.fixture(scope="module")
def noisy() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    return _frame(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 300))))


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("shorts", [False, True])
def test_a_past_signal_never_changes_when_the_future_arrives(name, shorts, noisy):
    """이 가족에서 돈이 걸린 유일한 성질이다.

    시계열을 k봉에서 잘라 다시 계산했을 때 앞 k봉의 신호가 달라지면, 그
    전략은 결정 시점에 없던 정보를 쓴 것이다 — 백테스트만 잘 나오고 실전에서
    재현되지 않는다.
    """
    strat = get_strategy(name, allow_short=shorts)
    full = strat.generate_signals(noisy)
    for k in (120, 200, 260):
        part = strat.generate_signals(noisy.iloc[:k])
        diff = (full.iloc[:k] - part).abs()
        assert float(diff.max()) < 1e-12, (
            f"{name}(allow_short={shorts}): {k}봉까지만 주면 앞부분 신호가 "
            f"{int((diff > 1e-12).sum())}봉 달라진다 — 미래를 봤다")


# ── ② 공통 계약 ───────────────────────────────────────────────


@pytest.mark.parametrize("name", NAMES)
def test_a_long_only_strategy_never_returns_a_short(name, noisy):
    sig = get_strategy(name, allow_short=False).generate_signals(noisy)
    assert float(sig.min()) >= 0.0, f"{name}가 숏 금지인데 {sig.min()}을 냈다"


@pytest.mark.parametrize("name", NAMES)
def test_the_signal_is_bounded_and_aligned(name, noisy):
    sig = get_strategy(name, allow_short=True).generate_signals(noisy)
    assert list(sig.index) == list(noisy.index), f"{name}: 인덱스가 어긋난다"
    assert not sig.isna().any(), f"{name}: NaN 신호가 남았다"
    assert float(sig.abs().max()) <= 1.0, f"{name}: 비중이 1을 넘는다"


@pytest.mark.parametrize("name", NAMES)
def test_a_halted_symbol_does_not_make_the_signal_thrash(name):
    """거래정지·상하한가로 가격이 완전히 멈춘 구간에서도 조용해야 한다."""
    rng = np.random.default_rng(3)
    p = list(100 * np.exp(np.cumsum(rng.normal(0.002, 0.012, 60))))
    p += [p[-1]] * 20                                   # 완전 보합
    sig = get_strategy(name).generate_signals(_frame(p))
    during = sig.iloc[60:80]
    assert during.nunique() <= 2, (
        f"{name}: 가격이 멈췄는데 신호가 {during.nunique()}가지로 요동친다")


# ── ③ 각자 자기 규칙대로 내는가 (손으로 아는 자료) ────────────


def test_ma_cross_follows_the_faster_average():
    """fast(20) > slow(60)이면 롱. 꾸준히 오르면 반드시 그렇게 된다."""
    up = _frame(_ramp(150, +0.01))
    assert float(get_strategy("ma_cross").generate_signals(up).iloc[-1]) == 1.0
    down = _frame(_ramp(150, -0.01))
    assert float(get_strategy("ma_cross", allow_short=True)
                 .generate_signals(down).iloc[-1]) == -1.0
    assert float(get_strategy("ma_cross").generate_signals(down).iloc[-1]) == 0.0


def test_momentum_follows_the_lookback_return():
    """90봉 전보다 높으면 롱, 낮으면 숏."""
    up = _frame(_ramp(150, +0.01))
    assert float(get_strategy("momentum").generate_signals(up).iloc[-1]) == 1.0
    down = _frame(_ramp(150, -0.01))
    assert float(get_strategy("momentum", allow_short=True)
                 .generate_signals(down).iloc[-1]) == -1.0


def test_macd_follows_the_signal_line():
    """MACD의 규칙은 '가격의 방향'이 아니라 **macd선 대 신호선**이다.

    ⚠️ 처음엔 "꾸준히 내리면 숏"이라고 썼다가 틀렸다. 지수적 하락
       (100·0.99^i)에서는 값이 0에 가까워질수록 두 EMA의 **차이 자체가
       줄어들어** macd선이 음수인 채로 0을 향해 올라간다. 신호선은 더
       뒤처져 있으므로 `macd > signal` — 규칙상 **롱이 맞다.**
       실측: macd -1.9165 vs signal -1.9972.

       코드가 아니라 내 기대가 틀렸다. 그래서 아래는 '가격이 이러면 이렇다'가
       아니라 **정의 그대로**를 검사한다 — 부등호를 뒤집으면 반드시 깨진다.
    """
    rng = np.random.default_rng(7)
    df = _frame(100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, 200))))
    close = df["close"]
    macd_line = (close.ewm(span=12, adjust=False).mean()
                 - close.ewm(span=26, adjust=False).mean())
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    want = pd.Series(0.0, index=df.index)
    want[macd_line > signal_line] = 1.0
    want[macd_line < signal_line] = -1.0

    got = get_strategy("macd", allow_short=True).generate_signals(df)
    assert (got == want).all(), (
        f"macd선-신호선 규칙과 다른 봉이 {int((got != want).sum())}개 있다")
    # 이 자료가 양쪽을 다 밟는지 확인 — 한쪽만 나오면 검사가 헛돈다
    # (첫 봉은 두 선이 모두 0이라 0.0이 섞인다. 그건 규칙대로다.)
    assert {1.0, -1.0} <= set(map(float, want.unique())), sorted(want.unique())

    # 선형 급락(절대 낙폭이 유지되는 하락)에서는 숏이 나온다
    crash = _frame([100.0] * 40 + [100 - 2.0 * i for i in range(60)])
    assert float(get_strategy("macd", allow_short=True)
                 .generate_signals(crash).iloc[-1]) == -1.0


def test_breakout_enters_on_a_new_high_and_leaves_on_the_exit_channel():
    """55봉 채널 위로 뚫으면 진입, 20봉 저점 아래로 빠지면 청산."""
    p = [100.0] * 60 + [130.0] + [131.0] * 5          # 신고가 돌파
    sig = get_strategy("breakout").generate_signals(_frame(p))
    assert float(sig.iloc[-1]) == 1.0, "신고가를 뚫었는데 진입하지 않는다"

    p2 = p + [131.0] * 20 + [80.0] * 3                # 20봉 저점 아래로 붕괴
    sig2 = get_strategy("breakout").generate_signals(_frame(p2))
    assert float(sig2.iloc[-1]) == 0.0, "청산 채널을 깼는데 계속 들고 있다"


def test_mean_reversion_buys_the_lower_band_and_leaves_at_the_middle():
    """평균 아래 2σ로 떨어지면 매수, 중심선 복귀 시 청산."""
    rng = np.random.default_rng(5)
    base = list(100 + rng.normal(0, 1.0, 60))
    drop = base + [88.0]                               # 하단 밴드 훨씬 아래
    assert float(get_strategy("mean_reversion")
                 .generate_signals(_frame(drop)).iloc[-1]) == 1.0
    back = drop + [100.0]                              # 중심선 복귀
    assert float(get_strategy("mean_reversion")
                 .generate_signals(_frame(back)).iloc[-1]) == 0.0

    # ⚠️ "하단에서 산다"만 검사하면 조건을 뒤집어도 통과한다(실제로 변이를
    #    두 번 놓쳤다). 뒤집힌 코드는 **밴드 안에 있는 동안 계속 롱**이 되는데,
    #    자극이 있는 자료에서는 어차피 마지막 봉이 1이라 구별이 안 된다.
    #    게다가 **마지막 봉만 보면 안 된다** — 뒤집힌 코드도 진입/청산이
    #    번갈아 일어나 마지막 봉이 우연히 0일 수 있다. 구간 전체를 봐야 한다.
    #
    #    그래서 '2σ를 한 번도 벗어나지 않는' 자료에서 **전 구간 무포지션**을
    #    요구한다. 완만한 하락 드리프트는 평균보다 늘 조금 아래지만 하단
    #    밴드까지는 안 간다 — 정상 코드는 0, 뒤집힌 코드는 계속 롱이다.
    drift = [100.0 - 0.1 * i for i in range(80)]
    sig = get_strategy("mean_reversion").generate_signals(_frame(drift))
    assert float(sig.abs().max()) == 0.0, (
        f"하단 밴드를 한 번도 안 벗어났는데 비중 {sig.abs().max()}를 잡는다 — "
        "'평균보다 조금 아래'를 과매도로 오인한다")


@pytest.mark.parametrize("name", ["rsi", "stochastic"])
def test_the_oscillators_buy_oversold_and_leave_at_the_middle(name):
    """과매도에서 진입하고 중심선(50)에서 대칭으로 청산한다."""
    p = [100.0] * 30 + _ramp(20, -0.03, 100.0)         # 꾸준한 급락 → 과매도
    sig = get_strategy(name).generate_signals(_frame(p))
    assert float(sig.iloc[-1]) == 1.0, f"{name}: 과매도인데 진입하지 않는다"

    p2 = p + _ramp(25, +0.04, p[-1])                   # 강한 반등 → 중심선 복귀
    sig2 = get_strategy(name).generate_signals(_frame(p2))
    assert float(sig2.iloc[-1]) == 0.0, f"{name}: 중심선을 넘었는데 청산하지 않는다"


def test_keltner_enters_above_the_upper_band():
    """조용하다가 밴드(EMA + 2·ATR) 위로 뚫으면 롱."""
    p = [100.0] * 40 + [140.0]
    assert float(get_strategy("keltner")
                 .generate_signals(_frame(p)).iloc[-1]) == 1.0
    p2 = [100.0] * 40 + [60.0]
    assert float(get_strategy("keltner", allow_short=True)
                 .generate_signals(_frame(p2)).iloc[-1]) == -1.0

    # ⚠️ 여기도 '돌파하면 산다'만으로는 방향이 안 고정된다(변이를 놓쳤다).
    #    부등호를 뒤집으면 **밴드 안에 있는 동안 계속 롱**이 되는데, 돌파
    #    자료만 보면 어차피 1이라 구별이 안 된다. 돌파가 **없는** 구간에서
    #    포지션이 0인지를 함께 봐야 한다.
    rng = np.random.default_rng(5)
    quiet = list(100 + rng.normal(0.0, 0.5, 80))       # 밴드를 안 벗어난다
    sig = get_strategy("keltner").generate_signals(_frame(quiet, span=0.002))
    assert float(sig.abs().max()) == 0.0, (
        f"밴드를 뚫은 적이 없는데 비중 {sig.abs().max()}를 잡는다")


# ── 대조군: 아무 자극도 없으면 아무 신호도 없어야 한다 ────────


@pytest.mark.parametrize("name", NAMES)
def test_a_perfectly_flat_market_produces_no_position(name):
    """완전히 평평한 시장에서 포지션을 잡으면 그건 신호가 아니라 잡음이다."""
    sig = get_strategy(name).generate_signals(_frame([100.0] * 120, span=0.0))
    assert float(sig.abs().max()) == 0.0, (
        f"{name}: 아무 일도 없는 시장에서 비중 {sig.abs().max()}를 잡는다")


# ── 목표 비중은 자본을 넘지 않는다 (감사 214) ──────────────────

def test_no_strategy_can_ask_for_more_than_the_whole_account():
    """`_finalize`의 [-1,1] 상한 — 모든 전략이 지나가는 마지막 문이다.

    +1.0은 '자본 전부'라는 뜻이다. 그 위를 허용하면 레버리지가 되고,
    리스크 계층은 그 값을 그대로 곱해 실제 주문 크기를 키운다. 전략이
    실수로 2.0을 내면 계좌의 두 배가 실린다 — 상한이 마지막 방어선이다.
    """
    import pandas as pd

    from quant.strategies.base import Strategy

    class _TooBig(Strategy):
        name = "toobig"
        allow_short = True

        def generate_signals(self, df):
            return self._finalize(
                pd.Series([5.0, -7.0, 0.5, -0.5], index=df.index), df.index)

    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    df = pd.DataFrame({"close": [1.0] * 4}, index=idx)
    out = _TooBig().generate_signals(df)
    assert list(out) == [1.0, -1.0, 0.5, -0.5], (
        f"자본을 넘는 목표 비중이 그대로 나갔다 — {list(out)}")
    assert out.max() <= 1.0 and out.min() >= -1.0
