"""첫 화면 적중률이 인샘플이다 (2026-08-14 감사 240).

종목표의 "적중률(전체)"은 장부가 아니라 **과거 400봉에 오늘의 챔피언 전략을
적용해** 잰 값이다. 그런데 그 400봉은 **그 챔피언을 뽑은 오디션(800봉)과
100% 겹친다**:

    적중률 표본 400봉 중
      오디션이 본 구간          400봉 (100%)
       ├ 선발전(챔피언 고른 곳)  280봉  (70%)
       └ 결승전(홀드아웃)        120봉  (30%)
      오디션이 못 본 구간          0봉

챔피언은 그 데이터에서 이겼기 때문에 뽑혔다. 같은 데이터로 성적을 매기면
**선택 편향이 그대로 숫자에 들어간다.** 그런데 화면에는 "적중률(전체)"이라고만
적혀 있어, 읽는 사람은 이 실험의 실전 성적으로 읽는다.

이 제품은 "선택 편향 없는 공개 실험"을 내걸고 있다. 그 화면에 편향된 숫자를
아무 표시 없이 매일 띄우면 그 주장 자체가 무너진다. 감사 94(카드가 신뢰구간
없이 비율을 방송)의 연장선이고 훨씬 크다.

고친 방법은 숫자를 지우는 것이 **아니다** — 두 숫자는 다른 것을 재고 둘 다
쓸모가 있다. 나란히 놓고 무엇인지 밝힌다:

    위: 과거 400봉 — "이 전략이 그 구간에서 방향을 맞혔나"(인샘플)
    아래: 장부     — "우리가 실제로 맞혔나"(아무도 안 고른 구간, 표본 작음)

실측 차이(2026-08-14): SK하이닉스 60.5% → 실전 33%(n=3) · S&P500 ETF
50.0% → 실전 25%(n=4). 표본이 이렇게 작을 때는 어느 쪽도 실력의 증거가
아니고, 그 사실도 화면이 말해야 한다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.ledger_basics import live_hit_rate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IDX = (ROOT / "docs" / "index.html").read_text("utf-8")


def _rec(w, price):
    return {"date": "2026-01-01", "weight": w, "price": price}


def _hist(pairs):
    return [{"date": f"2026-01-{i:02d}", "weight": w, "price": p}
            for i, (w, p) in enumerate(pairs, start=1)]


# ── 장부 적중률의 셈법 ────────────────────────────────────────

def test_a_long_that_went_up_is_a_hit():
    h = _hist([(0.5, 100), (0.5, 110)])
    assert live_hit_rate(h) == {"hit_rate": 1.0, "n": 1, "n_flat": 0}


def test_a_long_that_went_down_is_a_miss():
    assert live_hit_rate(_hist([(0.5, 100), (0.5, 90)]))["hit_rate"] == 0.0


def test_a_short_that_went_down_is_a_hit():
    assert live_hit_rate(_hist([(-0.5, 100), (0.0, 90)]))["hit_rate"] == 1.0


def test_a_flat_day_is_not_scored_but_is_counted():
    """방향이 없던 봉을 오답으로 세면 안 된다(감사 168과 같은 규칙)."""
    got = live_hit_rate(_hist([(0.5, 100), (0.5, 100), (0.5, 110)]))
    assert got["n"] == 1 and got["n_flat"] == 1
    assert got["hit_rate"] == 1.0


def test_a_day_with_no_position_is_not_scored():
    """방향을 안 걸었으면 채점할 것이 없다."""
    assert live_hit_rate(_hist([(0.0, 100), (0.0, 90)]))["n"] == 0


def test_no_sample_is_none_not_zero():
    """0.0으로 위장하면 '한 번도 못 맞혔다'로 읽힌다."""
    assert live_hit_rate([])["hit_rate"] is None
    assert live_hit_rate(_hist([(0.0, 100)]))["hit_rate"] is None


def test_records_out_of_order_are_still_paired_by_date():
    """장부 배열이 뒤집혀 있어도 시간순으로 짝짓는다(chrono)."""
    h = list(reversed(_hist([(0.5, 100), (0.5, 110)])))
    assert live_hit_rate(h)["hit_rate"] == 1.0


@pytest.mark.parametrize("bad", [None, "x", 0, -5])
def test_a_broken_price_is_skipped_not_scored(bad):
    h = [_rec(0.5, 100), {"date": "2026-01-02", "weight": 0.5, "price": bad}]
    assert live_hit_rate(h)["n"] == 0


# ── 두 숫자가 실제로 다른가 (진짜 장부로) ─────────────────────

def test_the_two_numbers_actually_differ_on_the_real_ledger():
    """같은 값이면 이 작업이 무의미하다 — 실제로 갈리는지 본다."""
    path = ROOT / "docs" / "status.json"
    if not path.exists():
        pytest.skip("status.json 없음")
    st = json.loads(path.read_text("utf-8"))
    diffs = []
    for key, v in (st.get("paper") or {}).items():
        if key.startswith("portfolio"):
            continue
        h = v.get("history") or []
        if not h:
            continue
        ins = h[-1].get("hit_rate")
        live = live_hit_rate(h)["hit_rate"]
        if ins is not None and live is not None and abs(ins - live) > 0.05:
            diffs.append(key)
    assert diffs, "인샘플과 실전 적중률이 어디서도 안 갈린다 — 전제 확인 필요"


# ── 화면이 무엇인지 밝히는가 ──────────────────────────────────

def test_the_column_no_longer_claims_to_be_the_whole_record():
    assert "적중률(전체)</th>" not in IDX, (
        "열 제목이 아직 '적중률(전체)' — 무엇을 잰 값인지 말하지 않는다")


def test_the_tooltip_says_it_is_in_sample():
    m = re.search(r'<th title="([^"]*)"[^>]*>적중률<br>', IDX)
    assert m, "적중률 열의 설명이 없다"
    tip = m.group(1)
    for phrase in ("400봉", "100% 겹치고", "인샘플"):
        assert phrase in tip, f"설명에 '{phrase}'가 없다 — {tip[:120]}"


def test_the_column_shows_both_numbers():
    assert "과거 400봉 · 실전" in IDX
    assert "last.live_hit" in IDX, "화면이 실전 적중률을 안 읽는다"
    assert "last.live_hit_n" in IDX, "표본 수를 안 보여준다"
    # ⚠️ 값을 **계산만** 하고 칸에 안 넣으면 화면에는 안 나온다 — 변이
    #    시험이 그 자리를 찔러 잡았다(계산과 표시는 다른 일이다).
    i = IDX.index("'<td class=\"num'+(hn!=null&&hn<20?\" sub\":\"\")+'\">'+hr+")
    assert "lhr" in IDX[i:i + 200], "적중률 칸이 실전 값을 그리지 않는다"


def test_the_ledger_records_the_live_hit_rate():
    """함수가 맞아도 **장부에 안 실리면** 화면은 영영 '—'다(감사 229)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"live_hit": _lh.get("hit_rate")' in src
    assert '_lh = live_hit_rate(st.get("history") or [])' in src


def test_it_is_measured_before_todays_record_is_added():
    """오늘의 결정은 내일 가격이 나와야 채점된다 — 미래를 당겨 쓰지 않는다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    i = src.index('_lh = live_hit_rate(')
    j = src.index('"live_hit": _lh.get("hit_rate")')
    assert i < j, "기록을 붙인 뒤에 잰다면 오늘 것이 섞인다"


# ── 공개했는가 ────────────────────────────────────────────────

def test_the_trust_page_explains_the_in_sample_problem():
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    v = re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", " ", trust, flags=re.S))
    # 태그·줄바꿈이 문장 가운데를 가른다 — 공백을 하나로 눌러 비교한다
    # (소스 문자열을 그대로 찾는 검사가 서식 때문에 빨개지는 것을 막는다).
    v = re.sub(r"\s+", " ", v)
    for phrase in ("인샘플", "100% 겹칩니다", "선택 편향 없는 공개 실험"):
        assert phrase in v, f"신뢰 페이지에 '{phrase}'가 없다"
    assert "어느 쪽도 실력의 증거가 아닙니다" in v, (
        "표본이 작다는 사실을 안 밝히면 실전 숫자가 또 다른 오해가 된다")
