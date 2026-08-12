"""우리를 검사하는 도구가 틀리면 아무도 안 잡는다 (감사 180).

훑은 파일 — `backtest/cost_sensitivity.py` · `data/crosscheck.py` ·
`robustness/regime.py` · `reporting/html_report.py`.

**결함 하나를 찾았다 — 손익분기 대조가 슬리피지를 통째로 빼먹었다.**

`break_even_cost`는 수수료를 올릴 때 슬리피지도 `slippage_ratio`(기본 0.5)
배로 **함께** 올린다. 그러니 거기서 나온 숫자는 '수수료'가 아니라 **총비용
fee×1.5의 대리 변수**다. 그런데 리포트는 이렇게 대조했다.

    if preset["fee"] > be:          # 수수료 : 수수료

실제 시장은 수수료와 슬리피지의 비율이 제각각이다.

    시장            수수료    슬리피지   총비용   (fee만 볼 때 놓치는 몫)
    crypto         0.1000%   0.0500%   0.1500%   1/3
    kr_stock       0.0900%   0.0500%   0.1400%   1/3
    crypto_upbit   0.0500%   0.0500%   0.1000%   1/2
    us_stock       0.0100%   0.0500%   0.0600%   **5/6**

미국주식은 무수수료 브로커가 일반화돼 비용의 거의 전부가 슬리피지다.
실측(손익분기 편도 0.03% = 총비용 0.045%짜리 전략):

    예전:  "실전에선 마이너스가 되는 시장: crypto, crypto_upbit, kr_stock"
           → **us_stock 누락.** 총비용 0.06% > 손익분기 0.045%인데 빠졌다.
    지금:  us_stock도 목록에 든다.

미국주식은 이 저장소가 **실제로 굴리는 시장**이다. 비용을 못 이기는 전략을
"주요 시장 프리셋보다는 손익분기가 높다"고 안심시켜 왔다 — 이 도구의 존재
이유가 바로 그 안심을 깨는 것인데.

나머지 셋에서는 결함을 못 찾았다. 확인한 것을 적어 둔다.

  · 교차검증: 겹침이 없으면 ok=False("검증 못 함"은 "통과"가 아니다),
    0 나눗셈은 inf로 드러난다.
  · 레짐 분류: expanding 분위수라 절단 검사를 통과한다(룩어헤드 없음).
    미지 구간은 0.5(중립)로 인코딩된다.
  · HTML 리포트: 표에 찍힌 숫자가 metrics의 실제 값과 같다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.cost_sensitivity import (  # noqa: E402
    break_even_cost,
    cost_sensitivity_report,
    cost_sweep,
)
from quant.backtest.costs import MARKET_COST_PRESETS  # noqa: E402
from quant.data.crosscheck import compare_sources  # noqa: E402
from quant.robustness.regime import (  # noqa: E402
    classify_regime,
    regime_feature,
    regime_summary,
)


def _falling(n: int = 260) -> pd.DataFrame:
    """꾸준히 내리는 시장 — 롱 온리 전략은 수수료 0에서도 손실이다."""
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    c = pd.Series(100.0 * (0.99 ** np.arange(n)), index=idx)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999,
                         "close": c, "volume": 1e6}, index=idx)


# ── 손익분기: 슬리피지를 빼먹지 않는가 ────────────────────────


def _be(fee: float, ratio: float = 0.5) -> dict:
    return {"break_even_fee": fee, "slippage_ratio": ratio,
            "break_even_total_cost": fee * (1.0 + ratio),
            "base_return_at_zero_fee": 0.12, "turnover_per_bar": 0.4,
            "unprofitable_at_zero": False, "capped": False}


def test_a_market_whose_cost_is_mostly_slippage_is_not_let_off():
    """미국주식은 비용의 5/6이 슬리피지다 — 수수료만 보면 통째로 빠진다."""
    us = MARKET_COST_PRESETS["us_stock"]
    total = us["fee"] + us["slippage"]
    # 손익분기 총비용 0.045% < 미국주식 총비용 0.06% → 적자여야 한다.
    assert total > 0.00045, "전제가 깨졌다 — 프리셋이 바뀌었으면 이 검사도 고칠 것"
    assert us["fee"] < 0.00045, "전제가 깨졌다 — 수수료만 보면 안 걸리는 상황이어야 한다"

    text = cost_sensitivity_report([], _be(0.0003))
    assert "us_stock" in text, (
        f"비용을 못 이기는 시장을 놓쳤다 — 미국주식 총비용 {total:.4%}: {text}")


def test_the_markets_it_can_beat_are_still_left_out():
    """대조군 — 늘 전부 나열하면 목록이 아무 말도 안 하는 것과 같다."""
    text = cost_sensitivity_report([], _be(0.01))     # 총비용 1.5% — 다 이긴다
    for name in MARKET_COST_PRESETS:
        assert name not in text, f"{name}이 적자로 잘못 분류됐다: {text}"
    assert "손익분기가 높다" in text


def test_a_market_just_under_the_line_is_left_out_but_just_over_is_in():
    """경계 양쪽 — 한 방향으로만 확인하면 '전부 적자'로 뒤집혀도 통과한다."""
    up = MARKET_COST_PRESETS["crypto_upbit"]
    total = up["fee"] + up["slippage"]                # 0.1000%
    below = cost_sensitivity_report([], _be(total / 1.5 * 1.01))   # 손익분기가 더 큼
    above = cost_sensitivity_report([], _be(total / 1.5 * 0.99))   # 손익분기가 더 작음
    assert "crypto_upbit" not in below, below
    assert "crypto_upbit" in above, above


def test_the_total_cost_is_the_fee_times_one_plus_the_ratio():
    """탐색이 쓴 슬리피지 배수를 리포트가 알아야 한다 — 안 그러면 또 빠진다."""
    df = _falling()
    df = df.iloc[::-1].copy()                         # 뒤집어 상승장으로
    df.index = pd.date_range("2023-01-01", periods=len(df), freq="D")
    from quant.strategies import get_strategy

    got = break_even_cost(df, lambda: get_strategy("ma_cross"), hi=0.05)
    assert got["slippage_ratio"] == pytest.approx(0.5)
    assert got["break_even_total_cost"] == pytest.approx(
        got["break_even_fee"] * 1.5), got


def test_an_old_result_without_the_new_keys_still_reads_right():
    """예전 형식(총비용 키 없음)이 들어와도 슬리피지를 반영해야 한다."""
    old = _be(0.0003)
    del old["slippage_ratio"], old["break_even_total_cost"]
    assert "us_stock" in cost_sensitivity_report([], old)


def test_a_strategy_with_no_edge_is_called_out_not_given_a_break_even():
    """수수료 0에서도 손실이면 '손익분기'랄 게 없다 — 0을 돌려줘야 한다."""
    from quant.strategies import get_strategy

    got = break_even_cost(_falling(), lambda: get_strategy("ma_cross"))
    assert got["unprofitable_at_zero"] is True, got
    assert got["break_even_fee"] == 0.0, (
        "엣지가 없는데 손익분기 수수료를 붙이면 '이 정도까지는 된다'로 읽힌다")
    text = cost_sensitivity_report([], got)
    assert "엣지가 없는 것" in text


def test_the_sweep_reports_one_row_per_fee_in_order():
    from quant.strategies import get_strategy

    df = _falling().iloc[::-1].copy()
    df.index = pd.date_range("2023-01-01", periods=len(df), freq="D")
    fees = [0.0, 0.001, 0.005]
    rows = cost_sweep(df, lambda: get_strategy("ma_cross"), fees)
    assert [r["fee"] for r in rows] == fees
    assert rows[0]["total_return"] >= rows[-1]["total_return"], (
        "수수료를 올렸는데 수익이 늘었다 — 비용이 안 걸린다")


# ── 교차검증: '검증 못 함'을 '통과'로 만들지 않는가 ────────────


def _frame(vals, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="D")
    return pd.DataFrame({"close": list(map(float, vals))}, index=idx)


def test_two_sources_that_never_overlap_are_not_a_pass():
    got = compare_sources(_frame([1, 2, 3]), _frame([1, 2, 3], "2030-01-01"))
    assert got["n_common"] == 0
    assert got["ok"] is False, "겹치는 봉이 하나도 없는데 '일치'라고 하면 안 된다"


def test_matching_sources_pass_and_a_single_bad_bar_fails():
    """대조군 — 늘 False면 이 검사는 아무것도 안 지킨다."""
    same = compare_sources(_frame([100, 101, 102]), _frame([100, 101, 102]))
    assert same["ok"] is True and same["n_common"] == 3

    off = compare_sources(_frame([100, 101, 102]), _frame([100, 110, 102]))
    assert off["ok"] is False and off["n_exceed"] == 1
    assert off["max_rel_diff"] == pytest.approx(9 / 101)


def test_a_zero_price_shows_up_as_infinite_not_as_agreement():
    got = compare_sources(_frame([0, 100]), _frame([1, 100]))
    assert not np.isfinite(got["max_rel_diff"]), got
    assert got["ok"] is False


def test_a_missing_column_is_not_a_pass():
    a = _frame([1, 2, 3])
    assert compare_sources(a, a.rename(columns={"close": "adj_close"}))["ok"] is False
    assert compare_sources(a, a.iloc[0:0])["ok"] is False
    assert compare_sources(None, a)["ok"] is False


# ── 레짐 분류: 미래를 보지 않는가 ─────────────────────────────


def _walk(n: int = 600, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), index=idx)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1e6}, index=idx)


@pytest.mark.parametrize("k", [300, 450, 599])
def test_the_regime_of_a_past_bar_does_not_change_when_the_future_arrives(k):
    """절단 검사 — 오늘 라벨이 내일 데이터로 바뀌면 그건 예측이 아니라 커닝이다."""
    df = _walk()
    full = classify_regime(df).iloc[:k]
    trunc = classify_regime(df.iloc[:k])
    assert (full.values == trunc.values).all(), (
        f"{k}봉까지 잘라 계산한 라벨이 전체로 계산한 것과 다르다 — 룩어헤드")


def test_both_volatility_labels_actually_appear():
    """대조군 — 전부 'unknown'이면 위 절단 검사가 헛돈다."""
    reg = classify_regime(_walk())
    assert set(reg["vol"]) >= {"high", "low"}, reg["vol"].value_counts().to_dict()
    assert set(reg["trend"]) >= {"bull", "bear"}, reg["trend"].value_counts().to_dict()


def test_an_unknown_regime_is_encoded_as_neutral_not_as_bullish():
    """미지를 1.0으로 채우면 이력이 짧은 초반이 통째로 '강세장'이 된다."""
    f = regime_feature(_walk())
    assert f.iloc[0]["trend_up"] == pytest.approx(0.5)
    assert f.iloc[0]["vol_high"] == pytest.approx(0.5)
    assert set(np.unique(f.values)) <= {0.0, 0.5, 1.0}, np.unique(f.values)


def test_the_regime_shares_add_up_to_one():
    got = regime_summary(_walk())
    assert sum(got.values()) == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in got.values()), got


# ── HTML 리포트: 표의 숫자가 실제 값인가 ──────────────────────


def test_every_metric_row_carries_the_real_number():
    from quant.backtest.engine import Backtester
    from quant.data.synthetic import SyntheticDataProvider
    from quant.reporting.html_report import build_report_html
    from quant.strategies import get_strategy

    df = SyntheticDataProvider(seed=9).get_ohlcv("T", "1d", limit=250)
    res = Backtester(get_strategy("ma_cross")).run(df)
    html_out = build_report_html(res, title="T")
    m = res.metrics
    for label, want in [("총수익률", f"{m.total_return:.2%}"),
                        ("CAGR", f"{m.cagr:.2%}"),
                        ("샤프지수", f"{m.sharpe:.2f}"),
                        ("최대낙폭", f"{m.max_drawdown:.2%}"),
                        ("시장노출", f"{m.exposure:.2%}")]:
        assert f"<tr><td>{label}</td><td>{want}</td></tr>" in html_out, (
            f"{label} 칸이 실제 값 {want}와 다르다")


def test_the_title_cannot_smuggle_a_script_in():
    from quant.backtest.engine import Backtester
    from quant.data.synthetic import SyntheticDataProvider
    from quant.reporting.html_report import build_report_html
    from quant.strategies import get_strategy

    df = SyntheticDataProvider(seed=9).get_ohlcv("T", "1d", limit=120)
    res = Backtester(get_strategy("ma_cross")).run(df)
    out = build_report_html(res, title="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
