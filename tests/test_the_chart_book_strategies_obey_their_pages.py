"""차트 자료에서 옮긴 전략 3종이 **자료의 규칙대로** 움직이는가 (2026-08-18).

사장님이 공유한 차트 공부 자료에서 수식으로 완전히 정의된 세 전략만
옮겼다 — 볼린저밴드(박스권·수축돌파), 파라볼릭 SAR, 일목균형표.
옮긴 규칙이 자료와 다르면 "당신 자료를 심사했습니다"가 거짓이 되므로,
검사도 자료의 문장을 기준으로 한다. 그리고 셋 모두 특혜 없이 도전자
링에 실제로 서는지 확인한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies import get_strategy                       # noqa: E402
from quant.strategies.bollinger import BollingerStrategy        # noqa: E402
from quant.strategies.ichimoku import IchimokuStrategy          # noqa: E402
from quant.strategies.psar import ParabolicSAR                  # noqa: E402


def _df(closes, spread=0.5):
    c = np.asarray([float(x) for x in closes])
    return pd.DataFrame({"open": c, "high": c + spread,
                         "low": c - spread, "close": c, "volume": 1.0},
                        index=pd.date_range("2025-01-01",
                                            periods=len(c), freq="D"))


# ── 볼린저 ① 박스권: "하단에서 매수하고 상단에서 매도" ─────────

def test_bollinger_reversion_buys_the_lower_band_and_sells_the_upper():
    rng = np.random.default_rng(3)
    base = 100 + rng.normal(0, 0.5, 60)          # 조용한 박스권
    dip = list(base) + [95.0]                     # 하단 이탈
    s = BollingerStrategy(mode="reversion").generate_signals(_df(dip))
    assert float(s.iloc[-1]) == 1.0, "하단을 깼는데 안 샀다"
    rip = list(base) + [95.0, 96.0, 108.0]        # 상단 돌파 — 청산
    s = BollingerStrategy(mode="reversion").generate_signals(_df(rip))
    assert float(s.iloc[-1]) == 0.0, "상단에 닿았는데 안 팔았다"


def test_bollinger_squeeze_buys_the_breakout_and_exits_midline():
    quiet = [100.0] * 60
    s = BollingerStrategy(mode="squeeze").generate_signals(_df(quiet))
    assert float(s.iloc[-1]) == 0.0, "돌파가 없는데 들어갔다"
    breakout = quiet + [104.0]                    # 수축 후 상단 돌파
    s = BollingerStrategy(mode="squeeze").generate_signals(_df(breakout))
    assert float(s.iloc[-1]) == 1.0, "수축 후 상단 돌파인데 안 샀다"
    fail = quiet + [104.0, 105.0, 99.0]           # 중앙선 하방 이탈 — 청산
    s = BollingerStrategy(mode="squeeze").generate_signals(_df(fail))
    assert float(s.iloc[-1]) == 0.0, "중앙선을 깼는데 들고 있다(자료의 매도 시그널)"


def test_bollinger_bands_exclude_the_current_bar():
    src = (ROOT / "quant" / "strategies" / "bollinger.py").read_text("utf-8")
    assert ".shift(1)" in src, "밴드가 자기 봉을 포함한다 — 미세 룩어헤드"


# ── 파라볼릭 SAR: 침범 순간 구간이 뒤집힌다 ────────────────────

def test_psar_rides_a_trend_and_flips_on_touch():
    up = list(np.linspace(100, 140, 60))          # 꾸준한 상승
    s = ParabolicSAR().generate_signals(_df(up))
    assert float(s.iloc[-1]) == 1.0, "상승 추세인데 매수 구간이 아니다"
    crash = up + [120.0]                          # SAR 침범 — 반전
    s = ParabolicSAR().generate_signals(_df(crash))
    assert float(s.iloc[-1]) == 0.0, "SAR을 깼는데 매수 구간에 남아 있다"


def test_psar_acceleration_is_capped():
    """가속변수는 0.2가 최대다(자료의 정의) — 상한이 없으면 SAR이 폭주한다."""
    src = (ROOT / "quant" / "strategies" / "psar.py").read_text("utf-8")
    assert "min(self.af_max, af + self.af_step)" in src
    s = ParabolicSAR(af_step=0.02, af_max=0.2)
    assert s.af_max == 0.2


# ── 일목균형표: 호전 + 구름 위 진입, 역전/구름 이탈 청산 ───────

def test_ichimoku_enters_above_the_cloud_and_exits_below():
    # 120봉 상승 → 전환선>기준선, 종가가 구름 위 (구름은 26일 전 계산값)
    up = list(np.linspace(100, 160, 120))
    s = IchimokuStrategy().generate_signals(_df(up))
    assert float(s.iloc[-1]) == 1.0, "호전 + 구름 위인데 진입하지 않았다"
    # 급락으로 전환선 역전 + 구름 아래 → 청산
    crash = up + list(np.linspace(158, 110, 15))
    s = IchimokuStrategy().generate_signals(_df(crash))
    assert float(s.iloc[-1]) == 0.0, "역전 + 구름 아래인데 들고 있다"


def test_ichimoku_cloud_is_from_the_past_not_the_future():
    """선행스팬은 26일 '앞에 기입'된다 — 오늘 비교하는 구름은 26일 전
    계산값이어야 하고, shift가 빠지면 미래 구름을 미리 보게 된다."""
    src = (ROOT / "quant" / "strategies" / "ichimoku.py").read_text("utf-8")
    assert ".shift(self.shift)" in src, "구름이 뒤로 밀리지 않았다(룩어헤드)"


# ── 심사대 — 셋 다 링에 서고, 특혜는 없다 ──────────────────────

def test_all_three_are_registered_and_buildable():
    for name, cls in (("bollinger", BollingerStrategy),
                      ("psar", ParabolicSAR), ("ichimoku", IchimokuStrategy)):
        assert isinstance(get_strategy(name), cls), f"{name} 미등록"


def test_the_chart_book_strategies_stand_in_the_ring():
    from quant.live.retrain import build_challengers
    ring = build_challengers({"strategy": "ml",
                              "params": {"model": "logreg"}}, seed="t")
    names = [c.get("strategy") for c in ring]
    for want in ("bollinger", "psar", "ichimoku"):
        assert want in names, (
            f"{want}가 링에 없다 — 만들어 두고 심사에 안 세우면 없는 전략이다")
    modes = sorted(c["params"].get("mode") for c in ring
                   if c.get("strategy") == "bollinger")
    assert modes == ["reversion", "squeeze"], (
        f"볼린저 두 활용법이 다 서지 않았다: {modes}")
