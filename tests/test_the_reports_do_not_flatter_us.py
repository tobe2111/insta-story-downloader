"""사람이 읽는 네 산출물의 계약을 못 박는다 (감사 179).

훑은 파일 — `reporting/dashboard.py` · `reporting/fill_gap.py` ·
`reporting/attribution.py` · `reporting/html_report.py`.
**결함은 못 찾았다.** 확인한 것을 적어 둔다.

이 넷의 공통 위험은 하나다 — **우리에게 유리한 쪽으로 조용히 기우는 것.**

  · 대시보드: 잘려 나간 과거의 낙폭을 잊으면 **위험 지표가 시간이 지나면
    저절로 좋아진다.** `history_summary`를 접어 넣는지 확인했다.
  · 체결 격차: 불리 갭의 **부호**가 뒤집히면 "백테스트가 낙관적"이라는
    자기 고발이 "보수적"이라는 자랑으로 바뀐다. 매수·매도 양방향으로 확인했다.
  · 기여도: 모든 전략의 샤프가 0 이하일 때 **억지 힌트를 만들지 않는지**.
  · HTML 리포트: 낙폭·거래 통계가 실제 값과 같은지.

이 파일들에는 변이 항목이 없었다 — 부호를 뒤집어도 스위트가 초록이었다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting.attribution import attribution_report  # noqa: E402
from quant.reporting.dashboard import build_dashboard_html  # noqa: E402
from quant.reporting.fill_gap import _iter_fill_gaps  # noqa: E402


# ── 대시보드: 잘려 나간 과거를 잊지 않는가 ────────────────────


BASE = {"symbol": "X", "strategy": "s", "mode": "paper",
        "history": [{"equity": e, "weight": 1.0} for e in (100.0, 105.0, 108.0)]}
SUMMARY = {"start": 100.0, "peak": 200.0, "max_drawdown": -0.60, "dropped": 500}


def _percents(html: str) -> list[str]:
    return re.findall(r"-?\d+\.\d+%", html)


def test_the_dashboard_remembers_the_drawdown_it_trimmed_away():
    """위험 지표가 시간이 지나면 저절로 좋아지면 그건 지표가 아니라 위안이다."""
    without = build_dashboard_html(BASE)
    with_ = build_dashboard_html({**BASE, "history_summary": SUMMARY})
    assert "-60.00%" in with_, (
        f"잘린 구간의 -60% 낙폭이 사라졌다: {_percents(with_)}")
    assert "-60.00%" not in without, "대조군이 깨졌다 — 요약 없이도 -60%가 나온다"


def test_the_dashboard_still_shows_the_current_return():
    """대조군 — 요약을 접어 넣느라 지금 손익을 잃으면 안 된다."""
    assert "8.00%" in build_dashboard_html(BASE)


def test_an_empty_history_does_not_crash_the_dashboard():
    html = build_dashboard_html({"symbol": "X", "strategy": "s", "history": []})
    assert isinstance(html, str) and len(html) > 0


# ── 체결 격차: 불리한 쪽이 양수인가 ───────────────────────────


def _hist(dec_price: float, fill_price: float, w_before: float, w_after: float):
    return [
        {"date": "2024-01-01", "price": dec_price, "weight": w_before},
        {"date": "2024-01-02", "price": dec_price, "weight": w_after},
        {"date": "2024-01-03", "price": fill_price, "weight": w_after,
         "fill": {"decided_bar": "2024-01-02", "price": fill_price,
                  "weight": w_after}},
    ]


def test_buying_higher_than_decided_is_adverse():
    """매수인데 체결가가 더 높으면 불리하다 — 양수여야 한다."""
    got = _iter_fill_gaps(_hist(100.0, 101.0, 0.0, 1.0))
    assert len(got) == 1
    _, abs_bp, adverse_bp = got[0]
    assert abs_bp == pytest.approx(100.0)
    assert adverse_bp == pytest.approx(100.0), (
        "부호가 뒤집히면 '백테스트가 낙관적'이 '보수적'으로 둔갑한다")


def test_selling_lower_than_decided_is_adverse_too():
    """매도인데 체결가가 더 낮아도 불리하다 — 방향이 대칭이어야 한다."""
    _, _, adverse_bp = _iter_fill_gaps(_hist(100.0, 99.0, 1.0, 0.0))[0]
    assert adverse_bp == pytest.approx(100.0)


def test_a_favourable_fill_is_negative():
    """대조군 — 유리하게 체결된 날은 음수여야 한다(늘 양수면 검사가 헛돈다)."""
    _, _, adverse_bp = _iter_fill_gaps(_hist(100.0, 99.0, 0.0, 1.0))[0]
    assert adverse_bp == pytest.approx(-100.0)


def test_a_bar_with_no_weight_change_is_not_a_sample():
    """주문이 안 나간 날은 체결 격차를 잴 수 없다 — 표본에서 빠져야 한다."""
    assert _iter_fill_gaps(_hist(100.0, 105.0, 1.0, 1.0)) == []


def test_records_are_read_in_date_order_not_array_order():
    """장부가 날짜순으로 저장되지 않은 적이 실제로 있었다(감사 51).

    ⚠️ 아무렇게나 섞으면 안 잡힌다. '직전 기록'은 `hist[j-1]`로 찾으므로,
       **배열에서 앞에 놓인 행의 비중이 진짜 전날과 달라야** 답이 갈린다.
       처음엔 그냥 섞었더니 우연히 같은 답이 나와 변이를 놓쳤다.

       아래는 배열 앞자리에 '비중 1'인 행을 두었다. 정렬하지 않으면
       prev_w=1 → 비중 변화 없음 → **표본이 통째로 사라진다.**
    """
    rows = _hist(100.0, 101.0, 0.0, 1.0)            # [01-01(0), 01-02(1), 01-03(fill)]
    unsorted = [rows[2], rows[1], rows[0]]          # 01-03, 01-02, 01-01
    got = _iter_fill_gaps(unsorted)
    assert len(got) == 1, (
        "날짜순으로 안 읽으면 '직전'이 미래가 되어 표본이 사라진다")
    assert got[0][2] == pytest.approx(100.0), got


def test_a_bad_price_is_skipped_not_counted_as_zero():
    rows = _hist(0.0, 101.0, 0.0, 1.0)               # 결정가 0 — 비율을 못 낸다
    assert _iter_fill_gaps(rows) == []


# ── 기여도: 근거 없으면 숫자를 만들지 않는가 ──────────────────


def test_the_report_shows_the_hint_when_there_is_one():
    text = attribution_report({
        "a": {"sharpe": 1.0, "total_return": 0.2, "contribution_hint": 0.75},
        "b": {"sharpe": 0.33, "total_return": 0.1, "contribution_hint": 0.25}})
    assert "75%" in text and "25%" in text
    assert "근사" in text, "한계를 안 밝히면 힌트가 결론처럼 읽힌다"


def test_no_positive_sharpe_means_no_invented_hint():
    """전부 손실인데 '이 전략이 75% 기여'라고 말하면 그건 지어낸 숫자다.

    ⚠️ 손으로 만든 dict를 `attribution_report`에 넣는 것만으로는 부족하다 —
       힌트를 **계산하는** 코드가 한 줄도 안 돈다(변이를 놓쳤다).
       실제로 `strategy_attribution`을 돌려야 그 자리가 실행된다.
    """
    from quant.data.synthetic import SyntheticDataProvider
    from quant.reporting.attribution import strategy_attribution
    from quant.strategies import get_strategy

    # 꾸준히 내리는 시장 — 롱 온리 전략들의 샤프가 0 이하가 된다
    df = SyntheticDataProvider(seed=11).get_ohlcv("T", "1d", limit=200)
    df = df.copy()
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].iloc[0] * (0.99 ** np.arange(len(df)))

    got = strategy_attribution(df, {"ma": get_strategy("ma_cross"),
                                    "mom": get_strategy("momentum")})
    assert all(r["sharpe"] <= 0 for r in got.values()), (
        f"전제가 깨졌다 — 하락장인데 샤프가 양수다: {got}")
    assert all(r["contribution_hint"] is None for r in got.values()), (
        f"근거가 없는데 기여도 숫자를 만들었다: {got}")


def test_the_report_always_carries_its_disclaimer():
    """대조군 — 어떤 경우에도 '미래 수익 보장 아님'이 붙어야 한다."""
    for hint in (0.5, None):
        text = attribution_report({"a": {"sharpe": 1.0, "total_return": 0.1,
                                         "contribution_hint": hint}})
        assert "보장하지 않습니다" in text, hint


# ── HTML 리포트: 숫자가 실제 값과 같은가 ──────────────────────


def test_the_html_report_prints_the_real_numbers():
    from quant.backtest.engine import Backtester
    from quant.data.synthetic import SyntheticDataProvider
    from quant.reporting.html_report import build_report_html
    from quant.strategies import get_strategy

    df = SyntheticDataProvider(seed=5).get_ohlcv("T", "1d", limit=200)
    res = Backtester(get_strategy("ma_cross")).run(df)
    html = build_report_html(res, title="T")

    assert f"{res.metrics.max_drawdown:.2%}" in html, "낙폭이 리포트와 다르다"
    assert f"{res.metrics.total_return:.2%}" in html, "총수익이 리포트와 다르다"
    assert "보장" in html, "면책 문구가 없다"


def test_the_html_report_survives_a_flat_market():
    """대조군 — 거래가 하나도 없어도 리포트가 나와야 한다."""
    import pandas as pd

    from quant.backtest.engine import Backtester
    from quant.reporting.html_report import build_report_html
    from quant.strategies import get_strategy

    idx = pd.date_range("2024-01-01", periods=120, freq="D")
    c = pd.Series(100.0, index=idx)
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                       "volume": 1e6}, index=idx)
    res = Backtester(get_strategy("ma_cross")).run(df)
    assert isinstance(build_report_html(res, title="flat"), str)
