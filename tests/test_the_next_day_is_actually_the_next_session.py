"""'다음 날'이 실은 '다음 기록'이었다 (감사 247).

모델은 **내일** 오를 확률을 말합니다. 그 말을 채점하려면 **바로 다음
세션**의 방향과 짝지어야 합니다. 그런데 두 곳이 각자 이렇게 적고
있었습니다:

    for a, b in zip(history, history[1:]):

기록이 하루 빠지면 **이틀치 움직임이 하루 예측의 성적**으로 들어갑니다.
모델은 내일을 말했는데 채점은 모레까지 본 셈입니다.

실측(2026-08-15 장부, 전 종목 143쌍):

    한 세션짜리   137쌍
    두 세션짜리     6쌍   ← 코인 5 + 국내 1 (08-05→08-07, 08-06 결측)

4%지만 이 표본을 쓰는 두 곳이 모두 **사람이 보는 숫자**입니다:

    ① 해설의 신뢰도 곡선 — 화면에 나가는 "실제 상승 비율"
    ② 확률 경험 보정 — **표시되는 확률 자체를 바꾼다**(prob_up_cal)

고친 뒤 실제로 값이 움직입니다(전 종목 합산):

    50%±10%p 구간   상승 비율 57% → **61%**  (표본 47 → 44)
    60%±10%p 구간   상승 비율 48% → **53%**  (표본 65 → 59)

그리고 ②의 주석에는 *"짝짓기 규칙은 해설과 동일"*이라고 **적혀만** 있었고
실제로는 각자 복사본이었습니다 — ㉞ 같은 판정을 두 곳에서 쓰면 언젠가
갈라집니다. 이제 `next_session_pairs` 한 함수를 둘 다 씁니다.

세션은 시장마다 다릅니다(감사 243). 금요일→월요일은 사흘이지만 **한
세션**이라 정상이고, 코인의 하루 결측은 뺍니다. 그리고 뺐으면 **뺐다고
말합니다**(감사 168·240) — 숨기면 "그런 날이 없었다"와 구별되지 않습니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.calibration_guard import collect_pairs  # noqa: E402
from quant.live.explain import _band_accuracy, _band_pairs_flat  # noqa: E402
from quant.live.ledger_basics import next_session_pairs  # noqa: E402

HOLIDAYS = {"kr_stock": ["2026-08-17"], "us_stock": []}


def _h(rows):
    """[(날짜, 확률, 가격)] → 장부 history."""
    return [{"date": d, "prob_up": p, "price": pr} for d, p, pr in rows]


# ── 짝짓기: 무엇이 '다음 세션'인가 ────────────────────────────

def test_a_missing_coin_day_is_dropped():
    """실측 그 장면 — 08-06이 빠진 짝은 이틀치 움직임이다."""
    h = _h([("2026-08-05", 0.6, 100.0), ("2026-08-07", 0.6, 110.0)])
    pairs, dropped = next_session_pairs(h, "crypto", HOLIDAYS)
    assert pairs == [] and dropped == 1


def test_a_weekend_is_still_one_session_for_stocks():
    """대조군 — 금요일→월요일은 사흘이지만 한 번이다. 빼면 표본이 반 토막 난다."""
    h = _h([("2026-08-07", 0.6, 100.0), ("2026-08-10", 0.6, 110.0)])
    pairs, dropped = next_session_pairs(h, "kr_stock", HOLIDAYS)
    assert len(pairs) == 1 and dropped == 0


def test_a_holiday_does_not_break_the_pair():
    """08-17은 한국이 안 여는 날 — 08-14→08-18은 한 세션이다."""
    h = _h([("2026-08-14", 0.6, 100.0), ("2026-08-18", 0.6, 110.0)])
    pairs, dropped = next_session_pairs(h, "kr_stock", HOLIDAYS)
    assert len(pairs) == 1 and dropped == 0


def test_a_coin_weekend_is_a_real_session():
    """대조군 — 코인은 토·일에도 연다. 주식 규칙을 그대로 쓰면 안 된다."""
    h = _h([("2026-08-14", 0.6, 100.0), ("2026-08-15", 0.6, 110.0)])
    assert len(next_session_pairs(h, "crypto", HOLIDAYS)[0]) == 1


def test_an_unknown_market_is_not_filtered():
    """모르는 것과 아닌 것을 구분한다 — 모르면 막지 않는다."""
    h = _h([("2026-08-05", 0.6, 100.0), ("2026-08-07", 0.6, 110.0)])
    pairs, dropped = next_session_pairs(h, None, HOLIDAYS)
    assert len(pairs) == 1 and dropped == 0


def test_records_out_of_order_are_paired_by_date():
    """배열 순서를 믿지 않는다(감사 240과 같은 규칙)."""
    h = list(reversed(_h([("2026-08-14", 0.6, 100.0),
                          ("2026-08-15", 0.6, 110.0)])))
    pairs, _ = next_session_pairs(h, "crypto", HOLIDAYS)
    assert pairs[0][0]["date"] == "2026-08-14"


# ── 해설: 화면 문장이 무엇을 세는가 ───────────────────────────

def _band_rows(n, *, start="2026-08-01", market="crypto"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return _h([((d0 + dt.timedelta(days=i)).isoformat(), 0.6,
                100.0 + i) for i in range(n)])


def test_the_sentence_counts_times_not_days():
    """"최근 N일"은 틀렸다 — 금요일→월요일은 사흘이지만 한 번이다."""
    out = _band_accuracy(_band_rows(30), 0.6, market="crypto",
                         holidays=HOLIDAYS)
    assert "번의 실제 상승 비율" in out, out
    assert "일의 실제 상승 비율" not in out, out


def test_the_sentence_says_how_many_it_dropped():
    rows = _band_rows(30)
    del rows[10]                                  # 하루를 통째로 뺀다
    out = _band_accuracy(rows, 0.6, market="crypto", holidays=HOLIDAYS)
    assert "봉이 빠진 1번은 제외" in out, out


def test_a_clean_ledger_says_nothing_about_gaps():
    """대조군 — 뺀 게 없으면 그 말을 안 한다(없는 경고는 소음이다)."""
    out = _band_accuracy(_band_rows(30), 0.6, market="crypto",
                         holidays=HOLIDAYS)
    assert "봉이 빠진" not in out, out


def test_the_pooled_branch_reads_market_labelled_ledgers():
    """합산 표본은 `(시장, 장부)` 짝으로 온다 — 시장 없이는 세션을 모른다."""
    rows = _band_rows(30)
    del rows[10]
    out = _band_accuracy([], 0.6, pooled_history=[("crypto", rows)],
                         holidays=HOLIDAYS)
    assert "전 종목 합산" in out and "봉이 빠진 1번은 제외" in out, out


def test_an_old_style_pooled_list_still_works():
    """옛 형태(장부만의 목록)도 받는다 — 받되 거르지 않는다."""
    out = _band_accuracy([], 0.6, pooled_history=[_band_rows(30)])
    assert "전 종목 합산" in out, out


def test_band_pairs_flat_returns_the_dropped_count():
    rows = _band_rows(30)
    del rows[10]
    pairs, dropped = _band_pairs_flat(rows, 0.6, 0.10, "crypto", HOLIDAYS)
    assert dropped == 1 and len(pairs) == 27


# ── 보정 가드: 같은 함수를 쓰는가 ─────────────────────────────

def test_the_calibration_guard_drops_the_same_pairs():
    """주석에 '같은 규칙'이라 적는 것과 같은 함수를 쓰는 것은 다르다."""
    rows = _band_rows(30)
    del rows[10]
    with_market = collect_pairs([("crypto", rows)], HOLIDAYS)
    without = collect_pairs([rows])
    assert len(without) - len(with_market) == 1, (
        f"세션 규칙이 보정 가드에 안 걸렸다: {len(without)} vs {len(with_market)}")


def test_the_calibration_guard_still_works_on_old_lists():
    assert collect_pairs([_band_rows(5)]), "옛 형태를 통째로 버렸다"


# ── 진짜 장부에서 값이 실제로 달라지는가 ──────────────────────

def test_the_real_ledger_actually_changes():
    """같은 값이 나오면 이 작업은 무의미하다 — 실제로 갈리는지 본다."""
    import glob

    from quant.data.market_calendar import holiday_map

    files = sorted(glob.glob(str(ROOT / "state" / "paper" / "*.json")))
    pooled = []
    for f in files:
        if "portfolio" in Path(f).name:
            continue
        d = json.loads(Path(f).read_text("utf-8"))
        if d.get("history"):
            pooled.append((str(d.get("market") or ""), d["history"]))
    if not pooled:
        pytest.skip("장부 없음")
    hm = holiday_map("state")
    strict = collect_pairs(pooled, hm)
    loose = collect_pairs([h for _, h in pooled])
    if len(loose) == len(strict):
        pytest.skip("지금 장부에는 건너뛴 봉이 없다 — 전제 확인 필요")
    assert len(strict) < len(loose), (
        f"세션 규칙이 아무것도 안 뺐다: {len(strict)} vs {len(loose)}")


# ── 배선 ──────────────────────────────────────────────────────

def test_the_batch_ships_the_market_with_each_ledger():
    """시장이 없으면 하루 결측과 주말을 구별할 수 없다."""
    from quant.live.daily import _all_paper_histories

    got = _all_paper_histories("state")
    if not got:
        pytest.skip("장부 없음")
    assert all(isinstance(x, tuple) and len(x) == 2 for x in got), (
        "합산 장부 목록이 시장을 안 싣는다")
    assert any(m for m, _ in got), "시장 이름이 전부 비어 있다"


def test_the_explanation_call_passes_the_market():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    i = src.index("reason = explain_signal(")
    window = src[i:i + 700]
    assert "market=market" in window, "해설이 시장을 안 받는다 — 세션 판정 불가"
    assert "holidays=" in window, "해설이 휴장일 달력을 안 받는다"
