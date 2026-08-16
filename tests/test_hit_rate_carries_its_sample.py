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


def test_the_site_asks_the_shared_rule_instead_of_its_own_threshold():
    """⚠️ 이 감사(111)의 **기준은 나중에 틀린 것으로 드러났다** (2026-08-14).

    여기서 정한 규칙은 'n<20이면 흐리게 + n 병기'였다. 방향은 맞았지만
    기준이 표본 크기였다. 사장님이 "솔라나 64% n=11"을 지적해 20종목을
    전부 재 봤더니 **19개**의 95% 신뢰구간이 50%를 품고 있었고, 그중에는
    n=81짜리 60%(구간 50~70%)도 있었다 — 이 문턱을 통과해 아무 단서 없이
    "60%"라는 단정으로 나가고 있었다. **n이 아니라 구간이 판정한다.**

    그래서 문턱은 사라졌고 판정은 docs/assets/hitrate.js 한 곳으로 갔다.
    이 검사는 '문턱이 다시 생기지 않는가'를 지킨다.
    """
    assert "QuantHitRate.format" in INDEX, "첫 화면이 공용 판정을 안 쓴다"
    assert not re.search(r"hn\s*<\s*\d+", INDEX), (
        "표본 크기 문턱이 되살아났다 — n=81짜리 60%가 그 문턱을 통과한다")


def test_inconclusive_rates_are_visually_muted():
    """숨기지는 않되 확신처럼 보이지 않게 — 판정 불가면 흐리게.

    흐리게 할지도 화면이 정하지 않는다. 판정과 표시를 다른 곳에서 정하면
    "흐린데 문구는 단정"인 상태가 생긴다.
    """
    assert re.search(r'hf\.dim\?" sub"', INDEX), (
        "판정 불가인 적중률이 진한 숫자로 나간다 — 우연이 실력처럼 읽힌다")


def test_a_missing_rate_is_a_dash_not_a_zero():
    """값이 없을 때 0%로 보이면 '한 번도 못 맞췄다'로 읽힌다."""
    from quant.robustness.accuracy import hit_rate_text
    assert hit_rate_text({}) == "N/A"
    js = (ROOT / "docs" / "assets" / "hitrate.js").read_text("utf-8")
    assert '"\u2014"' in js or '"—"' in js, "화면 쪽에 '—' 표기가 없다"


def test_the_verdict_is_decided_in_one_place_only():
    """판정이 여러 곳에 흩어지면 페이지마다 다른 확신으로 나간다.

    옛 검사는 '문턱이 한 값인가'를 봤다. 이제 문턱 자체가 없고, 지켜야 할
    것은 **판정하는 곳이 하나인가**다(FROZEN_IDEAS ①).
    """
    # 이름이 아니라 **식의 몸통**을 본다 — QuantHitRate.wilsonCI를 부르는 것도
    # 이름에는 'wilson'이 들어간다. 걸러야 할 것은 사본이지 호출이 아니다.
    #
    # ⚠️ 이 검사를 넣자마자 사본 **둘**이 걸렸다(2026-08-14): paper.html의
    #    보정 곡선과 sns_card.html의 카드가 각자 같은 식을 적고 있었고,
    #    sns_card 쪽 주석은 스스로 "paper.html이 쓰는 것과 같은 식"이라고
    #    적어 두기까지 했다. 셋이 갈라지면 같은 표본이 화면·카드·알림에서
    #    다른 폭으로 나간다.
    body = re.compile(r"z\s*\*\s*z\s*/\s*\(\s*2\s*\*\s*n\s*\)")
    for page in sorted((ROOT / "docs").glob("*.html")):
        src = page.read_text("utf-8")
        assert not body.search(src), f"{page.name}가 신뢰구간 식을 직접 적는다"
    for page in ("index.html", "paper.html"):
        src = (ROOT / "docs" / page).read_text("utf-8")
        assert "QuantHitRate" in src, f"{page}가 공용 판정을 안 쓴다"
    # 파이썬 쪽도 같다 — explain.py가 갖고 있던 사본은 n=0에서 터졌다.
    hits = [p for p in (ROOT / "quant").rglob("*.py")
            if p.name != "accuracy.py" and re.search(r"z\s*\*\s*z\s*/\s*\(\s*2\s*\*\s*n\s*\)",
                                                     p.read_text("utf-8"))]
    assert not hits, f"파이썬에 신뢰구간 사본이 있다: {[p.name for p in hits]}"


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
    # ⚠️ 라벨은 2026-08-14(감사 240)에 다시 바뀌었다. '적중률(전체)'은
    #    **무엇을 잰 값인지** 말하지 않아 인샘플 숫자를 실전 성적으로 읽게
    #    했다. 지금 라벨은 '과거 400봉 · 인샘플/실전'이다 — 기간만이 아니라
    #    출처까지 밝힌다. 여기서 지킬 것은 특정 글자가 아니라 **기간과 출처를
    #    밝히는가**이므로 그쪽을 본다.
    for page in ("paper.html", "index.html"):
        src = (ROOT / "docs" / page).read_text("utf-8")
        assert "과거 400봉" in src, f"{page}: 적중률이 무엇을 잰 값인지 안 밝힌다"
        assert "인샘플" in src, f"{page}: 인샘플이라는 사실을 안 밝힌다"


def test_the_ledger_stores_the_overall_rate_not_the_rolling_one():
    """전제 고정 — 장부가 rolling을 저장하기 시작하면 라벨도 바뀌어야 한다."""
    assert '"hit_rate": acc.get("hit_rate")' in DAILY
    assert '"rolling"' not in DAILY.split('"hit_rate"')[1][:200]
