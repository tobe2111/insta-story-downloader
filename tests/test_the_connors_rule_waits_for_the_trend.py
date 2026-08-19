"""코너스 RSI(2) — 세 줄 규칙이 세 줄 그대로 도는가 (2026-08-19 수집 라운드).

지켜야 할 약속:
- 추세 아래(200일선 밑)에서는 아무리 과매도여도 사지 않는다 — 이 규칙의
  절반은 '언제 안 사는가'다. 그 관문이 빠지면 다른 전략이 된다.
- 청산은 **가격이 단기선 위로 복귀**할 때다(RSI 중심선이 아니다) — 기존
  RSI 반전과 이 규칙을 가르는 유일한 지점이라, 여기가 무너지면 중복이 된다.
- 워밍업(이평 미정) 구간은 관망 — '모름'을 '조건 충족'으로 읽지 않는다.
- 링에 등록돼 있고 화면 이름표가 있다(등록되지 않은 전략은 돌지 않는다).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.connors import ConnorsRSI2          # noqa: E402
from quant.strategies.rsi import RSIReversion             # noqa: E402


def _frame(px: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(px), freq="D")
    s = pd.Series(px, index=idx, dtype=float)
    return pd.DataFrame({"open": s, "high": s * 1.001,
                         "low": s * 0.999, "close": s, "volume": 1.0})


def _uptrend_then_dip(n_up=260, dip=6):
    """길게 오른 뒤 짧게 급락 — 추세 위의 눌림(이 규칙이 노리는 장면)."""
    up = [100.0 + i * 0.5 for i in range(n_up)]
    return up + [up[-1] * (1 - 0.02 * (i + 1)) for i in range(dip)]


def test_it_buys_the_dip_inside_an_uptrend():
    sig = ConnorsRSI2().generate_signals(_frame(_uptrend_then_dip()))
    assert sig.iloc[-1] == 1.0, (
        f"추세 위 급락인데 사지 않는다: 마지막 신호 {sig.iloc[-1]}")


def test_it_refuses_the_same_dip_below_the_trend():
    """같은 급락이라도 200일선 아래면 안 산다 — 대조군."""
    down = [200.0 - i * 0.5 for i in range(260)]
    px = down + [down[-1] * (1 - 0.02 * (i + 1)) for i in range(6)]
    sig = ConnorsRSI2().generate_signals(_frame(px))
    assert sig.max() == 0.0, (
        "하락 추세에서 눌림을 샀다 — 이 규칙의 절반(안 사는 조건)이 없다")


def test_the_exit_is_the_price_not_the_oscillator():
    """청산 기준이 가격의 단기선 복귀인가 — 기존 RSI 반전과 갈리는 지점."""
    px = _uptrend_then_dip()
    px += [px[-1] * (1 + 0.03 * (i + 1)) for i in range(4)]   # 급반등
    sig = ConnorsRSI2(exit_ma=5).generate_signals(_frame(px))
    assert sig.iloc[-1] == 0.0, "단기선 위로 복귀했는데 계속 들고 있다"
    # 반등이 단기선을 못 넘는 동안에는 계속 보유해야 한다(중심선 청산이 아님).
    px2 = _uptrend_then_dip()
    px2 += [px2[-1] * (1 + 0.0005 * (i + 1)) for i in range(3)]
    sig2 = ConnorsRSI2(exit_ma=5).generate_signals(_frame(px2))
    assert sig2.iloc[-1] == 1.0, (
        "단기선 아래인데 나갔다 — 청산 기준이 가격이 아니다")


def test_it_is_not_the_same_signal_as_plain_rsi_reversion():
    """중복이면 등록할 이유가 없다 — 신호가 실제로 갈리는지 값으로 본다."""
    px = _uptrend_then_dip()
    px += [px[-1] * (1 + 0.03 * (i + 1)) for i in range(4)]
    df = _frame(px)
    a = ConnorsRSI2().generate_signals(df).to_numpy()
    b = RSIReversion(period=2, oversold=10).generate_signals(df).to_numpy()
    assert not np.array_equal(a, b), (
        "기존 RSI 반전과 신호가 완전히 같다 — 중복 후보다")


def test_warmup_is_flat_not_a_guess():
    sig = ConnorsRSI2().generate_signals(_frame([100.0 + i for i in range(40)]))
    assert sig.abs().sum() == 0.0, (
        "200일선이 정해지기도 전에 의견을 냈다 — '모름'을 조건 충족으로 읽었다")


def test_it_is_registered_where_it_must_be():
    from quant.live.retrain import build_strategy
    assert type(build_strategy(
        {"strategy": "connors_rsi2", "params": {}})).__name__ == "ConnorsRSI2"
    ring = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"strategy": "connors_rsi2"' in ring, "오디션 링에 없다 — 돌지 않는다"
    app = (ROOT / "quant" / "web" / "app.py").read_text("utf-8")
    assert "connors_rsi2" in app, "조종석에 이름표가 없다"
