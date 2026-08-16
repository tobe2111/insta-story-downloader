"""사이트가 그리는 벤치마크가 **오디션 링에도** 있는가.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2026-08-14 발견. 사이트는 "그냥 보유" 곡선을 벤치마크로 그려 보여준다.
그런데 **오디션 링에는 그 벤치마크가 없었다.** 매일 밤 20종목에서 후보
20여 명이 챔피언에게 도전하는데, 그 목록에 '아무것도 안 하기'가 빠져 있었다.

그래서 시스템은 구조적으로 "그냥 들고 있는 게 낫다"를 발견할 수 없었다.
화면에는 그 사실이 그려지고 있는데, 판단 루프는 그걸 후보로 세워 본 적이 없다.

실측(스냅샷 20종목, 수수료 미반영):
    ML 전략 샤프 중앙값 0.46  ·  단순 보유 0.81
    ML 방향 적중률 54.3%(3,512봉) — 문서가 말하는 52~55% 범위와 일치
예측은 정상인데 노출이 ~30%뿐이라 상승장에서 구조적으로 진다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies import get_strategy, list_strategies  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _df(n=200) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 140, n), index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)


def test_buy_hold_is_a_registered_strategy():
    assert "buy_hold" in list_strategies()


def test_buy_hold_actually_holds():
    sig = get_strategy("buy_hold").generate_signals(_df())
    assert (sig == 1.0).all(), "보유 전략이 보유하지 않는다"


def test_buy_hold_respects_a_warmup_so_the_contest_is_fair():
    """다른 전략은 지표 워밍업 동안 관망한다 — 보유만 0봉부터 실리면 불공정."""
    sig = get_strategy("buy_hold", warmup=50).generate_signals(_df())
    assert (sig.iloc[:50] == 0.0).all()
    assert (sig.iloc[50:] == 1.0).all()


def test_buy_hold_cannot_lever_up():
    """이 전략의 주제는 '들고 있기'다 — 1.0을 넘기면 다른 이야기가 된다."""
    sig = get_strategy("buy_hold", weight=5.0).generate_signals(_df())
    assert sig.max() <= 1.0 + 1e-12


def test_the_benchmark_is_actually_in_the_audition_ring():
    """이게 이 파일의 핵심 — 링에 없으면 영원히 발견되지 않는다."""
    from quant.live.retrain import DEFAULT_CHALLENGERS

    names = {c.get("strategy") for c in DEFAULT_CHALLENGERS}
    assert "buy_hold" in names, (
        "오디션 링에 벤치마크(보유)가 없다 — 사이트는 그 곡선을 그리면서 "
        "판단 루프는 한 번도 그것과 겨뤄 보지 않는다")


def test_the_benchmark_still_has_to_win_the_gate():
    """보유도 예외가 아니다 — 기본 챔피언이 되거나 관문을 건너뛰면 안 된다."""
    from quant.live.retrain import DEFAULT_CHAMPION

    assert DEFAULT_CHAMPION["strategy"] != "buy_hold", (
        "보유가 기본 챔피언이면 '검증을 통과할 때만 바꾼다'는 규칙 밖이다")


def test_buy_hold_can_actually_beat_the_champion_in_a_rising_market():
    """링에 세운 것이 실제로 겨룰 수 있는가 — 상승장에서 관망 챔피언을 이긴다."""
    from quant.live.champion_challenger import ChampionChallenger

    class _Flat:
        name = "flat"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(0.0, index=df.index)

    r = ChampionChallenger(_Flat(), get_strategy("buy_hold"),
                           min_obs=30, t_threshold=1.0).evaluate(_df(300))
    assert r["n"] > 0, "대결 표본이 0 — 보유가 링에서 평가되지 않는다"
    assert not r["identical"], "보유가 무효 후보로 분류됐다"
    assert r["mean_diff"] > 0 and r["t_stat"] > 0, r


def test_the_honest_limits_are_written_down():
    """'보유가 이기면 보유가 옳다'는 결론으로 새지 않게 한계를 적어 둔다."""
    src = (ROOT / "quant" / "strategies" / "buy_hold.py").read_text("utf-8")
    assert "생존 편향" in src
    assert "낙폭" in src
