"""알파 11차 계약 검사 — 부분 켈리 상한 + 트레일링 스톱 오디션 챌린저.

핵심 계약:
  ① 켈리 상한: 표본 30일 미만 비개입(1.0) · 음의 엣지는 floor(0.25)로
     제한 · 좋은 통계는 비개입(1.0 캡) — 손계산과 일치
  ② 페이퍼·포트폴리오 두 경로에 배선 + 기록 필드(kelly_cap)
  ③ TrailingStopGuard: 고점 대비 -trail 되돌림에서 신호 차단, inner가
     접기 전 재진입 금지, 신호 종료 후 상태 리셋(결정적)
  ④ stop_wrap이 링에 참전하고 build_strategy가 만들 수 있다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import _kelly_cap_from_history  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402
from quant.strategies.stop_guard import TrailingStopGuard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _hist(days: int, win_ret: float, loss_ret: float, win_every: int = 2) -> list:
    """보유일 수익이 (승·패 교대) 패턴인 가짜 장부."""
    out, eq = [], 1000.0
    for i in range(days + 1):
        out.append({"weight": 0.5, "equity": eq})
        eq *= (1 + win_ret) if i % win_every == 0 else (1 + loss_ret)
    return out


# ── ① 켈리 상한 손계산 ─────────────────────────────────────────


def test_kelly_cap_small_sample_no_intervention():
    assert _kelly_cap_from_history(_hist(10, 0.01, -0.01)) == 1.0
    assert _kelly_cap_from_history([]) == 1.0


def test_kelly_cap_negative_edge_floors():
    # 승률 50%, 이익 +1% vs 손실 -2% → 켈리 음수 → floor 0.25
    cap = _kelly_cap_from_history(_hist(60, 0.01, -0.02))
    assert cap == 0.25


def test_kelly_cap_strong_edge_no_cap():
    # 승률 50%, 이익 +3% vs 손실 -1% → 켈리 f*=(0.5·3−0.5)/3=1/3 →
    # ½켈리 0.167… < floor 0.25 → 0.25? 아니다: max(floor, min(1, 0.167))=0.25
    cap = _kelly_cap_from_history(_hist(60, 0.03, -0.01))
    assert abs(cap - 0.25) < 1e-9
    # 이익 +5% vs 손실 -0.5% → f*=(0.5·10−0.5)/10=0.45 → ½켈리 0.225 → floor
    # 극단 우위: 승 3/4 비율(3승 1패)로 만들면 캡이 커진다
    hist = _hist(80, 0.02, -0.01, win_every=1)     # 전부 승 → wins만 → 비개입
    assert _kelly_cap_from_history(hist) == 1.0


# ── ② 배선 ─────────────────────────────────────────────────────


def test_kelly_wired_and_recorded():
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert dl.count("_kelly_cap_from_history(") >= 3   # 정의 + 두 경로
    assert '"kelly_cap"' in dl


# ── ③ 트레일링 스톱 ────────────────────────────────────────────


class _Const(Strategy):
    name = "const"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _px(vals):
    idx = pd.date_range("2026-01-01", periods=len(vals), freq="D")
    v = np.asarray(vals, dtype=float)
    return pd.DataFrame({"open": v, "high": v, "low": v, "close": v,
                         "volume": 1.0}, index=idx)


def test_trailing_stop_cuts_and_blocks_reentry():
    # 100→120(고점)→107(−10.8% 되돌림: 스톱)→이후 계속 보유 신호지만 차단
    df = _px([100, 110, 120, 115, 107, 112, 118])
    sig = TrailingStopGuard(_Const(), trail=0.10).generate_signals(df)
    assert sig.iloc[0] == 1.0 and sig.iloc[3] == 1.0   # 되돌림 -4.2%는 유지
    assert sig.iloc[4] == 0.0                          # 스톱 발동
    assert (sig.iloc[5:] == 0.0).all()                 # 재진입 금지


def test_trailing_stop_resets_after_inner_exits():
    class OnOff(Strategy):
        name = "onoff"
        allow_short = False

        def generate_signals(self, df):
            w = [1, 1, 1, 0, 1, 1]                     # 중간에 스스로 접는다
            return pd.Series(w, index=df.index, dtype=float)

    df = _px([100, 120, 105, 104, 100, 101])           # 105에서 스톱(-12.5%)
    sig = TrailingStopGuard(OnOff(), trail=0.10).generate_signals(df)
    assert sig.iloc[2] == 0.0                          # 스톱
    assert sig.iloc[3] == 0.0                          # inner도 접음 → 리셋
    assert sig.iloc[4] == 1.0                          # 새 신호는 다시 허용


# ── ④ 링 참전 + 빌드 ───────────────────────────────────────────


def test_stop_wrap_in_ring_and_buildable():
    from quant.live.retrain import build_challengers, build_strategy
    ring = build_challengers(
        {"strategy": "ma_cross", "params": {"fast": 10, "slow": 30}},
        seed="2026-08-09:t", evolve=True)
    stops = [c for c in ring if c.get("strategy") == "stop_wrap"]
    assert len(stops) == 1 and stops[0]["params"]["trail"] == 0.10
    strat = build_strategy(stops[0])
    assert isinstance(strat, TrailingStopGuard)
    # 이미 stop_wrap 챔피언이면 '벗긴 원본'이 도전한다(되돌아갈 길)
    ring2 = build_challengers(stops[0], seed="2026-08-09:t", evolve=True)
    assert any(c == {"strategy": "ma_cross",
                     "params": {"fast": 10, "slow": 30}} for c in ring2)
