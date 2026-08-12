"""아직 안 판 포지션이 '완결 거래'로 세어졌다 (감사 176).

`extract_trades`는 자본곡선과 포지션에서 라운드트립 거래를 뽑는다. 그런데
자료가 끝나는 시점에 **아직 들고 있던** 포지션도 한 건의 거래로 세고, 그
평가손익을 승률·기대손익·이익팩터에 넣었다.

    exit_eq = eq[end + 1] if end + 1 < n else eq[end]   # 데이터 끝이면 미실현

주석은 "미실현"이라고 알고 있었는데, **결과에는 그 사실이 안 적혔다.**
쓰는 쪽은 그냥 거래 한 건으로 읽는다.

방향이 나쁘다. 상승장에서는 들고 있는 포지션이 대개 이익 중이라 승률과
기대손익이 **위로** 부풀고, 하락장에서는 반대로 눌린다 — 즉 "지금 잘 되고
있으면 과거 성적도 좋아 보인다". 성과 지표가 **현재 포지션의 평가손익에
따라 흔들리면** 그건 성과 지표가 아니다.

실측(손실로 청산한 거래 1건 + 이익 중인 미청산 1건):

    예전:  거래 2건 · 승률 50%
    지금:  거래 1건 · 승률  0% · 미청산 1건 (따로 표시)

거래 수가 적을 때 특히 아프다. 이 저장소는 "거래 30건 미만은 잡음"이라고
경고하는데, 그 적은 표본에 미실현 한 건이 섞이면 비중이 크다.

──────────────────────────────────────────────────────────────
어디까지 영향을 주는가 — 정직하게

이 통계를 쓰는 곳은 백테스트 HTML 리포트와 CLI 거래 복기 두 곳이다.
**실거래 사이징에는 안 쓰인다** — 새벽 배치의 켈리 상한(`_kelly_cap_from_history`)은
라운드트립이 아니라 보유일의 일간 수익으로 따로 계산한다. 확인했다.
`fractional_kelly_cap`(이 통계를 받는 함수)은 export만 되고 운영 경로에서
불리지 않는다.

즉 돈이 걸린 결함은 아니고 **보고의 정확성** 문제다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.trades import extract_trades, trade_stats  # noqa: E402

IDX = pd.date_range("2024-01-01", periods=6, freq="D")


def _run(equity: list[float], positions: list[float]):
    n = len(equity)
    eq = pd.Series(equity, index=IDX[:n], dtype=float)
    pos = pd.Series(positions, index=IDX[:n], dtype=float)
    trades = extract_trades(eq, pos)
    return trades, trade_stats(trades)


# ── 미청산 포지션은 통계에 안 들어간다 ────────────────────────


def test_a_position_still_held_is_marked_open():
    trades, _ = _run([100.0, 100.0, 110.0, 121.0], [0.0, 1.0, 1.0, 1.0])
    assert len(trades) == 1
    assert trades[0].is_open is True, "끝까지 들고 있었는데 완결로 표시된다"


def test_an_open_position_is_excluded_from_the_statistics():
    """이것이 감사 176 — 평가손익이 승률에 섞이던 자리."""
    _, stats = _run([100.0, 100.0, 110.0, 121.0], [0.0, 1.0, 1.0, 1.0])
    assert stats["num_trades"] == 0, (
        "아직 안 판 포지션이 완결 거래로 세어진다")
    assert stats["num_open"] == 1, "뺀 사실이 안 보인다"


def test_a_winning_open_position_does_not_lift_the_win_rate():
    """손실로 청산한 1건 + 이익 중인 미청산 1건 → 승률은 0%다."""
    _, stats = _run([100.0, 100.0, 90.0, 90.0, 90.0, 120.0],
                    [0.0, 1.0, 0.0, 0.0, 1.0, 1.0])
    assert stats["num_trades"] == 1 and stats["num_open"] == 1, stats
    assert stats["win_rate"] == 0.0, (
        f"승률 {stats['win_rate']:.0%} — 평가이익이 실현승률을 끌어올린다")
    assert stats["expectancy"] < 0, stats


def test_a_losing_open_position_does_not_drag_the_win_rate_down():
    """반대 방향 대조군 — 평가손실도 마찬가지로 빠져야 한다."""
    _, stats = _run([100.0, 100.0, 120.0, 120.0, 120.0, 80.0],
                    [0.0, 1.0, 0.0, 0.0, 1.0, 1.0])
    assert stats["num_trades"] == 1 and stats["num_open"] == 1, stats
    assert stats["win_rate"] == 1.0, (
        f"승률 {stats['win_rate']:.0%} — 평가손실이 실현승률을 끌어내린다")


def test_the_counts_always_add_up():
    """뺀 것과 남은 것의 합이 전체여야 '숨기지 않았다'가 성립한다."""
    trades, stats = _run([100.0, 100.0, 90.0, 90.0, 90.0, 120.0],
                         [0.0, 1.0, 0.0, 0.0, 1.0, 1.0])
    assert stats["num_trades"] + stats["num_open"] == len(trades)


# ── 대조군: 정상 청산은 예전 그대로여야 한다 ──────────────────


def test_a_closed_trade_is_unchanged():
    """엔진 규약(청산 손익은 다음 봉에 실현)이 그대로인지 확인한다."""
    trades, stats = _run([100.0, 100.0, 110.0, 121.0, 121.0],
                         [0.0, 1.0, 1.0, 0.0, 0.0])
    assert len(trades) == 1 and trades[0].is_open is False
    assert trades[0].return_pct == pytest.approx(0.21), trades[0]
    assert stats["num_trades"] == 1 and stats["num_open"] == 0
    assert stats["win_rate"] == 1.0


def test_two_closed_trades_still_count_as_two():
    trades, stats = _run([100.0, 100.0, 110.0, 110.0, 110.0, 121.0],
                         [0.0, 1.0, 0.0, 0.0, 1.0, 0.0])
    assert stats["num_trades"] == 2 and stats["num_open"] == 0
    assert all(not t.is_open for t in trades)


def test_no_trades_at_all_is_still_zero():
    _, stats = _run([100.0, 100.0, 100.0], [0.0, 0.0, 0.0])
    assert stats["num_trades"] == 0 and stats["num_open"] == 0


def test_an_empty_list_keeps_the_old_shape():
    """대조군 — 빈 입력의 반환 모양이 바뀌면 쓰는 쪽이 KeyError를 만난다."""
    s = trade_stats([])
    for k in ("num_trades", "win_rate", "avg_win", "avg_loss", "expectancy",
              "profit_factor", "avg_bars_held", "num_open"):
        assert k in s, k


# ── 사람이 읽는 줄에 드러나는가 ───────────────────────────────


def test_the_review_report_says_what_it_excluded():
    from quant.live.journal import build_review, review_report

    hist = [{"equity": 100.0, "weight": 0.0},
            {"equity": 100.0, "weight": 1.0},
            {"equity": 90.0, "weight": 0.0},
            {"equity": 90.0, "weight": 1.0},
            {"equity": 120.0, "weight": 1.0}]
    text = review_report(build_review(hist))
    assert "아직 안 판" in text, text


def test_the_report_is_quiet_when_nothing_is_open():
    """대조군 — 평시에 붙으면 매번 붙어서 아무도 안 읽는다."""
    from quant.live.journal import build_review, review_report

    hist = [{"equity": 100.0, "weight": 0.0},
            {"equity": 100.0, "weight": 1.0},
            {"equity": 120.0, "weight": 0.0},
            {"equity": 120.0, "weight": 0.0}]
    assert "아직 안 판" not in review_report(build_review(hist))
