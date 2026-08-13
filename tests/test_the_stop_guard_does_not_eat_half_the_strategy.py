"""트레일링 스톱이 **전략의 절반을 먹어치우지 않는가** (감사 214).

`TrailingStopGuard`는 다른 전략을 감싸 되돌림이 크면 신호를 끊는 래퍼다.
그런데 `allow_short`를 base에서 물려받지 않았다. `Strategy.allow_short`의
클래스 기본값이 False라, 숏을 내는 전략을 감싸는 순간 `_finalize`가
**숏을 전부 0으로 잘라 버렸다.** 실측:

    감싸기 전 : 롱 93봉 · 숏 88봉
    감싼 뒤   : 롱 93봉 · 숏  0봉

형제 셋(adx·event_guard·liquidity)은 전부 `self.allow_short =
base.allow_short`를 하고 있었고 **여기만 빠져 있었다.** 한 줄이다.

왜 나쁜가: 이 래퍼는 오디션 챌린저로 참전한다. 전략의 절반을 잃은 채로
평가되므로, 채택·탈락이 **스톱의 효과가 아니라 사라진 숏 때문에** 갈린다.
"스톱이 도움이 되는가"를 재려고 만든 실험이 다른 질문에 답하고 있었다.

그리고 숏은 스톱 자체도 못 받고 있었다 — 되돌림 판정이 `w[t] > 0`
안에만 있어서, 숏은 클립되기 전에도 이 분기에 오지 못했다. '가드'라는
이름으로 한쪽만 지키고 있었던 셈이다. 지금은 대칭이다: 롱은 고점 대비
하락, 숏은 **저점 대비 반등**이 손실이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies.base import Strategy  # noqa: E402
from quant.strategies.moving_average import MovingAverageCross  # noqa: E402
from quant.strategies.stop_guard import TrailingStopGuard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class _Fixed(Strategy):
    """항상 같은 신호를 내는 전략 — 스톱만 따로 떼어 본다."""

    name = "fixed"

    def __init__(self, value: float, allow_short: bool = False):
        self.value = value
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(self.value, index=df.index)


def _df(closes) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    c = pd.Series([float(v) for v in closes], index=idx)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1e6}, index=idx)


# ── 감싸도 숏이 살아남는가 ────────────────────────────────────

def test_wrapping_does_not_delete_the_short_side():
    """실측을 그대로 재현한다 — 감싸기 전후로 숏 봉 수가 같아야 한다."""
    idx = pd.date_range("2026-01-01", periods=200, freq="D")
    c = pd.Series(np.r_[np.linspace(100, 60, 100), np.linspace(60, 100, 100)],
                  index=idx)
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                       "close": c, "volume": 1e6}, index=idx)
    base = MovingAverageCross(fast=5, slow=20, allow_short=True)
    plain = base.generate_signals(df)
    guarded = TrailingStopGuard(base, trail=0.10).generate_signals(df)

    assert int((plain < 0).sum()) > 0, "이 데이터에 숏 구간이 없다 — 검사가 헛돈다"
    assert int((guarded < 0).sum()) > 0, (
        f"감싸는 순간 숏이 전부 사라졌다 — {int((plain < 0).sum())}봉 → 0봉")


def test_the_wrapper_inherits_the_short_permission():
    for allow in (True, False):
        base = MovingAverageCross(fast=5, slow=20, allow_short=allow)
        assert TrailingStopGuard(base).allow_short is allow


def test_a_long_only_base_still_produces_no_shorts():
    """대조군 — 숏을 물려받느라 롱 온리 전략이 숏을 내면 안 된다."""
    base = MovingAverageCross(fast=5, slow=20, allow_short=False)
    df = _df(list(np.linspace(100, 60, 120)))
    assert int((TrailingStopGuard(base).generate_signals(df) < 0).sum()) == 0


# ── 스톱이 실제로 발동하는가 (양방향) ─────────────────────────

def test_the_long_stop_fires_on_a_drawdown_from_the_peak():
    # 100 → 120(고점) → 100 : 고점 대비 -16.7% > 10%
    out = TrailingStopGuard(_Fixed(1.0), trail=0.10).generate_signals(
        _df([100, 110, 120, 115, 100, 100]))
    assert list(out) == [1.0, 1.0, 1.0, 1.0, 0.0, 0.0], list(out)


def test_the_short_stop_fires_on_a_rebound_from_the_trough():
    """숏은 **저점 대비 반등**이 손실이다 — 예전에는 아예 안 잡혔다."""
    # 100 → 80(저점) → 95 : 저점 대비 +18.75% > 10%
    out = TrailingStopGuard(_Fixed(-1.0, allow_short=True),
                            trail=0.10).generate_signals(
        _df([100, 90, 80, 84, 95, 95]))
    assert list(out) == [-1.0, -1.0, -1.0, -1.0, 0.0, 0.0], list(out)


def test_a_quiet_market_is_not_stopped_out():
    """대조군 — 되돌림이 없는데 끊으면 가드가 아니라 고장이다."""
    out = TrailingStopGuard(_Fixed(1.0), trail=0.10).generate_signals(
        _df([100, 101, 102, 103, 104]))
    assert list(out) == [1.0] * 5

    sh = TrailingStopGuard(_Fixed(-1.0, allow_short=True),
                           trail=0.10).generate_signals(
        _df([100, 99, 98, 97, 96]))
    assert list(sh) == [-1.0] * 5


# ── 스톱 뒤 재진입 금지 ──────────────────────────────────────

def test_after_a_stop_the_same_signal_cannot_re_enter():
    """스톱 직후 같은 신호로 바로 되사면 스톱이 무의미해진다."""
    out = TrailingStopGuard(_Fixed(1.0), trail=0.10).generate_signals(
        _df([100, 120, 100, 118, 119, 120]))
    assert out.iloc[2] == 0.0
    assert list(out.iloc[3:]) == [0.0, 0.0, 0.0], (
        f"스톱 뒤에 다시 들어갔다 — {list(out)}")


def test_a_flat_signal_resets_the_stop():
    """inner가 신호를 접었다 다시 내면 새 판이다 — 영구 금지가 아니다."""
    base_vals = [1.0, 1.0, 1.0, 0.0, 1.0, 1.0]

    class _Seq(Strategy):
        name = "seq"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(base_vals, index=df.index)

    out = TrailingStopGuard(_Seq(), trail=0.10).generate_signals(
        _df([100, 120, 100, 100, 100, 101]))
    assert out.iloc[2] == 0.0                      # 스톱
    assert out.iloc[4] == 1.0 and out.iloc[5] == 1.0, (
        f"신호가 끊겼다 재개됐는데도 계속 막는다 — {list(out)}")


# ── 방향 전환은 상태를 새로 잡는가 ───────────────────────────

def test_flipping_direction_starts_a_fresh_stop():
    """롱에서 눌린 고점이 숏 구간까지 따라오면 엉뚱한 자리에서 끊긴다."""
    vals = [1.0, 1.0, -1.0, -1.0]

    class _Flip(Strategy):
        name = "flip"
        allow_short = True

        def generate_signals(self, df):
            return pd.Series(vals, index=df.index)

    out = TrailingStopGuard(_Flip(), trail=0.10).generate_signals(
        _df([100, 130, 100, 101]))
    # 숏으로 바뀐 뒤에는 롱 시절 고점(130)과 무관하게 새로 잰다
    assert out.iloc[2] == -1.0 and out.iloc[3] == -1.0, list(out)


# ── 형제 찾기 ───────────────────────────────────────────────

def test_every_wrapper_inherits_the_short_permission():
    """래퍼가 base의 숏 허용을 물려받지 않으면 전략의 절반이 사라진다.

    이 한 줄을 빠뜨린 곳이 실제로 있었다(stop_guard). 새 래퍼가 생길 때
    같은 것을 또 빠뜨리면 여기서 걸린다.
    """
    import ast

    offenders = []
    for path in sorted((ROOT / "quant" / "strategies").glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            init = next((n for n in cls.body if isinstance(n, ast.FunctionDef)
                         and n.name == "__init__"), None)
            if init is None:
                continue
            args = {a.arg for a in init.args.args}
            # base를 받아 감싸는 래퍼만 대상 (자체 전략은 인자로 직접 받는다)
            if "base" not in args:
                continue
            body = ast.unparse(init)
            if "allow_short" not in body:
                offenders.append(f"{path.name}:{cls.name}")
    assert not offenders, (
        "base를 감싸면서 allow_short를 물려받지 않는 래퍼가 있다 — 감싸는 "
        "순간 숏이 전부 잘린다:\n  " + "\n  ".join(offenders))
