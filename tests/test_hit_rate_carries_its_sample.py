"""적중률이 **표본 수와 함께** 나가는가 (감사 111).

첫 화면의 종목 표는 매일 이렇게 나간다.

    KODEX 200 … 적중률 64%
    비트코인   … 적중률 35%

적중률은 `directional_accuracy`가 **포지션을 잡은 봉만** 세서 낸 값이다.
관망이 많은 종목은 표본이 아주 작다 — 며칠만 매수했다면 n이 한 자리다.
그런데 장부에 `hit_rate`만 남기고 **`n`은 남기지 않았고**, 화면도 비율만
보여줬다. n=3짜리 우연이 '실력 64%'처럼 읽힌다.

감사 94(SNS 카드가 신뢰구간 없이 소표본 비율을 방송)와 같은 계열이다.
이쪽이 더 나쁘다 — 첫 화면 **전 종목 행에 매일** 나간다.

고침: 장부에 `hit_n`을 함께 남기고, 화면은 표본이 얇으면(n<20) n을
병기하고 흐리게 보여준다. 숨기지 않되 확신처럼 보이지 않게 한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DAILY = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
INDEX = (ROOT / "docs" / "index.html").read_text("utf-8")


def test_the_ledger_records_the_sample_size():
    assert '"hit_n": acc.get("n")' in DAILY, (
        "적중률만 남기고 표본 수를 안 남긴다 — 나중에 되돌아봐도 그 비율이 "
        "몇 건짜리였는지 알 수 없다")


def test_the_accuracy_helper_actually_returns_n():
    """장부가 읽는 키가 실제로 있는가 — 없으면 매일 None이 쌓인다."""
    import numpy as np
    import pandas as pd

    from quant.robustness.accuracy import directional_accuracy
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    close = pd.Series(np.linspace(100, 130, 30), index=idx)
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1.0}, index=idx)
    out = directional_accuracy(df, pd.Series(1.0, index=idx), window=10)
    assert "n" in out, f"directional_accuracy가 n을 안 준다: {sorted(out)}"
    assert out["n"] > 0


def test_the_site_shows_the_sample_when_it_is_thin():
    seg = INDEX.split("const hn=", 1)
    assert len(seg) == 2, "첫 화면이 표본 수를 읽지 않는다"
    body = seg[1][:600]
    assert "hit_n" in INDEX
    assert re.search(r"hn\s*<\s*\d+", body), "얇은 표본 문턱이 없다"
    assert "n='+hn" in body, "표본 수를 화면에 적지 않는다"


def test_thin_samples_are_visually_muted():
    """숨기지는 않되 확신처럼 보이지 않게 — 흐리게."""
    assert re.search(r'hn!=null&&hn<\d+\?" sub"', INDEX), (
        "표본이 얇은 적중률이 진한 숫자로 나간다 — 우연이 실력처럼 읽힌다")


def test_a_missing_rate_is_a_dash_not_a_zero():
    """값이 없을 때 0%로 보이면 '한 번도 못 맞췄다'로 읽힌다."""
    body = INDEX.split("const hn=", 1)[1][:600]
    assert '"—"' in body


def test_the_threshold_is_stated_once_not_scattered():
    """문턱이 여러 값으로 흩어지면 표시와 색이 어긋난다."""
    body = INDEX.split("const hn=", 1)[1][:800]
    thresholds = set(re.findall(r"hn\s*<\s*(\d+)", body))
    assert len(thresholds) == 1, f"문턱이 여러 개다: {thresholds}"


# ── 라벨이 실제 계산과 같은가 (감사 112) ────────────────────────

def test_the_label_does_not_claim_a_window_the_value_does_not_have():
    """'적중률(60일)'이라 적었지만 장부에 남는 값은 **전체 기간**이다.

    directional_accuracy는 hit_rate(전체)와 rolling(최근 window)을 따로
    돌려주는데, 장부는 hit_rate만 남긴다. window=60은 rolling을 만드는
    데만 쓰인다. 열 이름이 '(60일)'이면 최근 60일치처럼 읽힌다 —
    숫자는 맞고 이름이 틀린, 오늘 반복해서 나온 계열이다.
    """
    paper = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "적중률(60일)" not in paper, (
        "장부에 남는 값은 전체 기간 적중률인데 열 이름이 '(60일)'이다")
    for page in ("paper.html", "index.html"):
        src = (ROOT / "docs" / page).read_text("utf-8")
        assert "적중률(전체)" in src, f"{page}: 적중률의 기간을 밝히지 않는다"


def test_the_ledger_stores_the_overall_rate_not_the_rolling_one():
    """전제 고정 — 장부가 rolling을 저장하기 시작하면 라벨도 바뀌어야 한다."""
    assert '"hit_rate": acc.get("hit_rate")' in DAILY
    assert '"rolling"' not in DAILY.split('"hit_rate"')[1][:200]
