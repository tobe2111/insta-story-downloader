"""보합 봉이 '틀린 예측'으로 채점됐다 (감사 168).

`directional_accuracy`는 사이트 첫 화면과 대시보드에 매일 나가는 **적중률**을
만든다. "다음 봉 방향을 맞혔는가"를 재는 지표다.

    active  = (sig.abs() > 1e-9) & ret_next.notna()
    correct = active & (np.sign(sig) == np.sign(ret_next))

`np.sign(0.0)`은 0이다. 그래서 다음 봉이 **정확히 보합**이면 롱이든 숏이든
`sign(sig) != 0` — 무조건 '틀림'이 된다. 그런데 그 봉은 애초에 방향이
없었으므로 **채점 자체가 불가능한 봉**이다.

실측(롱 고정, 상승 6 · 하락 2 · 보합 2):

    보고된 적중률   60.0%   ← 보합 2봉이 오답으로 분모·분자에 들어갔다
    방향이 있던 봉  75.0%   (6/8)

15%p 차이다. 방향이 자기 자신에게 **불리한** 쪽이라 '정직해 보이는' 오류인데,
그래도 틀린 숫자다. 그리고 더 나쁜 게 있다 — **보합 봉 비율은 종목마다 다르다.**
거래정지·상하한가·저유동 국내주식은 보합이 흔하고 코인은 거의 없다. 그래서
같은 실력이어도 종목에 따라 적중률이 다르게 나오고, 종목 간 비교가 조용히
왜곡된다.

고침: 방향이 없던 봉은 분모에서 뺀다. 다만 **숨기지는 않는다** — 몇 봉을
뺐는지 `n_flat`으로 함께 돌려주고 장부에도 남긴다. 안 보이면 "보합이
없었다"와 구별되지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.robustness.accuracy import directional_accuracy  # noqa: E402


def _frame(moves: list[int], step: float = 0.01) -> pd.DataFrame:
    """moves = 봉별 방향(+1/-1/0). 정답을 손으로 아는 계열을 만든다."""
    close = [100.0]
    for m in moves:
        close.append(close[-1] * (1.0 + step * m))
    idx = pd.date_range("2025-01-01", periods=len(close), freq="D")
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": [1e6] * len(close)},
                        index=idx)


def _long(df: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0, index=df.index)


# 상승 6 · 하락 2 · 보합 2 → 방향이 있던 8봉 중 6봉 적중 = 75%
MIXED = [+1, +1, +1, +1, +1, +1, -1, -1, 0, 0]


# ── 보합 봉이 오답이 되지 않는가 ──────────────────────────────


def test_a_flat_bar_is_not_scored_as_a_miss():
    df = _frame(MIXED)
    r = directional_accuracy(df, _long(df))
    assert r["n"] == 8, (
        f"채점 표본이 {r['n']}봉 — 방향이 있던 봉은 8봉뿐이다")
    assert r["hit_rate"] == pytest.approx(0.75), (
        f"적중률 {r['hit_rate']:.1%} — 보합 2봉이 오답으로 들어갔다(정답 75%)")


def test_the_excluded_flat_bars_are_disclosed():
    """분모에서 빼되 숨기면 안 된다 — '보합이 없었다'와 구별돼야 한다."""
    r = directional_accuracy(_frame(MIXED), _long(_frame(MIXED)))
    assert r["n_flat"] == 2, r


def test_a_series_with_no_flat_bars_reports_zero():
    """대조군 — 평시에 0이어야 이 칸이 의미가 있다."""
    df = _frame([+1, +1, -1, +1, -1])
    r = directional_accuracy(df, _long(df))
    assert r["n_flat"] == 0 and r["n"] == 5, r


def test_an_all_flat_series_is_unscoreable_not_zero_percent():
    """한 번도 안 움직인 종목의 적중률은 0%가 아니라 '판정 불가'다.

    0%로 내보내면 "모델이 매번 틀렸다"로 읽힌다 — 사실은 맞출 방향이 없었다.
    """
    df = _frame([0, 0, 0, 0])
    r = directional_accuracy(df, _long(df))
    assert r["n"] == 0 and np.isnan(r["hit_rate"]), r
    assert r["n_flat"] == 4, r


# ── 원래 동작이 그대로인가 (대조군) ───────────────────────────


def test_a_perfect_forecast_is_still_a_hundred_percent():
    df = _frame([+1, -1, +1, -1])
    sig = pd.Series([1.0, -1.0, 1.0, -1.0, 0.0], index=df.index)
    r = directional_accuracy(df, sig)
    assert r["hit_rate"] == pytest.approx(1.0) and r["n"] == 4, r


def test_a_perfectly_wrong_forecast_is_still_zero():
    """대조군 — 진짜 오답까지 지워 버리면 지표가 늘 좋아 보인다."""
    df = _frame([+1, -1, +1, -1])
    sig = pd.Series([-1.0, 1.0, -1.0, 1.0, 0.0], index=df.index)
    r = directional_accuracy(df, sig)
    assert r["hit_rate"] == pytest.approx(0.0) and r["n"] == 4, r


def test_flat_positions_are_still_excluded():
    """관망(비중 0)은 원래부터 채점 대상이 아니다."""
    df = _frame([+1, +1, +1, +1])
    sig = pd.Series([1.0, 0.0, 0.0, 1.0, 0.0], index=df.index)
    assert directional_accuracy(df, sig)["n"] == 2


def test_the_last_bar_has_no_future_and_is_excluded():
    """대조군 — 없는 미래를 채점하면 그게 룩어헤드다."""
    df = _frame([+1, +1, +1])
    assert directional_accuracy(df, _long(df))["n"] == 3   # 4봉 중 마지막 제외


def test_the_rolling_window_uses_the_same_rule():
    """이동 적중률의 분모도 같은 기준이어야 한다 — 한쪽만 고치면 두 숫자가 갈린다.

    ⚠️ 창을 전 구간보다 짧게 잡으면 창 경계 때문에 값이 달라진다(봉 하나가
       빠지면 5/7 = 71.4%). 규칙이 같은지 보려면 **창이 전 구간을 덮어야**
       한다. 처음에 window=10으로 잡았다가 이 경계에 걸렸다.
    """
    df = _frame(MIXED)
    r = directional_accuracy(df, _long(df), window=len(df))
    last = float(r["rolling"].dropna().iloc[-1])
    assert last == pytest.approx(0.75), (
        f"이동 적중률 {last:.1%} — 전체 적중률과 규칙이 다르다")


# ── 장부에 남는가 (배선) ──────────────────────────────────────


def test_the_ledger_records_how_many_bars_were_excluded():
    """부품이 아니라 배선 — 뺀 봉 수가 기록까지 가야 사람이 볼 수 있다."""
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"hit_flat": acc.get("n_flat")' in daily, (
        "새벽 배치 장부에 보합 제외 봉 수가 안 남는다")
    learner = (ROOT / "quant" / "live" / "autolearn.py").read_text("utf-8")
    assert '"n_flat": acc.get("n_flat")' in learner, (
        "학습 루프 기록에 보합 제외 봉 수가 안 남는다")


def test_the_metric_states_which_fill_convention_it_uses():
    """전제 고정 — 이 지표는 종가 대비 종가다.

    이 시스템은 실제로는 **다음 봉 시가**에 체결한다. 즉 적중률은 "모델이
    방향을 맞혔는가"이지 "우리가 그 방향을 먹었는가"가 아니다. 둘을 같은
    것으로 읽으면 적중률이 좋은데 손익이 안 따라오는 날을 설명할 수 없다.
    이 사실이 독스트링에서 사라지면 그 오해가 되살아난다.
    """
    src = (ROOT / "quant" / "robustness" / "accuracy.py").read_text("utf-8")
    assert "종가 대비 종가" in src and "다음 봉 시가" in src
