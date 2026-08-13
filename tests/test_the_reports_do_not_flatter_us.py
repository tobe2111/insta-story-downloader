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


# ── 망가진 전략 하나가 나머지를 지우지 않는가 (감사 202) ──────────
#
# `attribution.py`는 **운영 경로에 배선되어 있지 않다**(export와 검사에서만
# 쓰인다). 그래서 live 결함이 아니라 공개 API의 구멍으로 적는다 — 감사 196에서
# "실제 경로를 지나는지부터 확인할 것"을 배운 대로 확인하고 그대로 적는다.
#
# 실측(고치기 전): 전략 하나의 샤프가 NaN이면
#   · `max(nan, 0.0)`이 nan → 합계 nan → `total > 0`이 거짓
#   · **전 전략의 기여도 힌트가 사라진다**
#   · 리포트에는 "샤프 nan · 총수익 nan%"가 사람에게 그대로 나간다
#   · NaN이 섞인 정렬은 순서가 뒤죽박죽이 된다


def _rows(sharpes: dict) -> dict:
    import math as _m
    out = {n: {"sharpe": s, "total_return": s, "contribution_hint": None}
           for n, s in sharpes.items()}
    pos = {n: (max(float(r["sharpe"]), 0.0)
               if _m.isfinite(float(r["sharpe"])) else 0.0)
           for n, r in out.items()}
    tot = sum(pos.values())
    if tot > 0:
        for n in out:
            out[n]["contribution_hint"] = pos[n] / tot
    return out


def test_the_real_attribution_gives_hints_to_the_strategies_that_earned_them():
    """**실제 `strategy_attribution`을 돌려** 힌트가 붙는지 본다.

    ⚠️ 이 검사를 처음엔 손으로 만든 dict로 썼다가 변이가 빠져나갔다 —
       계산 코드를 안 지나기 때문이다. 이 파일이 위쪽에서 스스로 경고해 둔
       바로 그 함정이고, 감사 179에서 배운 것이다.

    ⚠️ 그리고 확인한 것: **NaN 샤프는 실제 경로로 도달 불가다.** 관망·NaN
       신호·한 봉짜리 신호를 실제 `Backtester`에 태워도 샤프는 0.0이나
       유한값이다(엔진이 위쪽에서 막는다). 그래서 `strategy_attribution`의
       `isfinite` 필터에는 변이 항목을 붙이지 않았다 — 잡을 수 없는 항목은
       안전장치가 아니라 소음이다(감사 183과 같은 자리).
    """
    import numpy as np
    import pandas as pd

    from quant.reporting.attribution import strategy_attribution

    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    rng = np.random.default_rng(4)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 120)))
    df = pd.DataFrame({"open": c * .99, "high": c * 1.02, "low": c * .98,
                       "close": c, "volume": 1e6}, index=idx)

    class _Long:
        name = "매수보유"

        def generate_signals(self, d):
            return pd.Series(1.0, index=d.index)

    class _Flat:
        name = "관망"

        def generate_signals(self, d):
            return pd.Series(0.0, index=d.index)

    out = strategy_attribution(df, {"매수보유": _Long(), "관망": _Flat()})
    assert out["매수보유"]["sharpe"] > 0, out
    assert out["매수보유"]["contribution_hint"] == 1.0, out
    assert out["관망"]["contribution_hint"] == 0.0, out

    # 대조군 — 모두가 0 이하면 힌트를 만들 근거가 없으니 전부 None이어야 한다.
    # (없으면 위 단언은 "무조건 힌트를 지어내는" 구현도 통과시킨다.)
    only_flat = strategy_attribution(df, {"관망": _Flat()})
    assert only_flat["관망"]["contribution_hint"] is None, only_flat


def test_the_report_keeps_hints_for_the_strategies_that_have_them():
    """리포트 쪽 — 값이 없는 줄 하나가 나머지 줄의 힌트를 지우면 안 된다."""
    from quant.reporting.attribution import attribution_report
    text = attribution_report(_rows({"좋은전략": 1.5, "망가진전략": float("nan"),
                                     "보통전략": 0.4}))
    assert text.count("기여 힌트") == 3, f"힌트가 사라졌다:\n{text}"

    none_text = attribution_report(_rows({"A": -0.5, "B": -1.0}))
    assert "기여 힌트" not in none_text, none_text


def test_a_number_we_could_not_measure_says_so():
    """화면에 'nan'을 내보내지 않는다 — 0인지 실패인지 읽는 사람이 모른다."""
    from quant.reporting.attribution import attribution_report
    text = attribution_report(_rows({"좋은전략": 1.5, "망가진전략": float("nan")}))
    assert "nan" not in text.lower(), text
    assert "측정 불가" in text, text
    assert "1.50" in text, "멀쩡한 숫자까지 뭉갰다"


def test_the_ranking_is_stable_when_a_value_is_missing():
    """측정 불가는 맨 뒤로, 같은 값이면 이름 순 — 순서가 흔들리면 대조가 안 된다."""
    from quant.reporting.attribution import attribution_report
    nan = float("nan")
    body = [ln for ln in attribution_report(
        _rows({"C": 0.4, "A": nan, "B": 1.5})).splitlines()
        if ln.startswith("  ")]
    assert body[0].startswith("  B") and body[1].startswith("  C"), body
    assert body[2].startswith("  A"), f"측정 불가가 맨 뒤가 아니다: {body}"


def test_an_empty_weight_frame_is_not_a_crash():
    """빈 프레임에서 리포트가 죽으면 그날 요약 전체가 사라진다."""
    import pandas as pd

    from quant.reporting.attribution import ensemble_weight_report

    class _E:
        last_weights_ = pd.DataFrame()

    assert "가중치 정보가 없습니다" in ensemble_weight_report(_E())
