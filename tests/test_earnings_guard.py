

# ── 발표 '이후' 창 — 문서가 약속한 보호의 나머지 절반 ─────────
#
# 2026-08-11 감사: 가드는 "발표 ±N일"이라고 문서·사이트에 적혀 있는데,
# 미래 날짜만 찾다 보니 실제로는 **발표 전만** 작동했다. 발표 다음 날은
# 갭과 변동성이 가장 큰 구간인데 가드가 이미 꺼져 있었다.


def _cached(tmp_path, symbol, dates):
    import json
    (tmp_path / "earnings.json").write_text(
        json.dumps({symbol: {"dates": dates, "fetched": "2026-08-11"}}),
        encoding="utf-8")


def test_guard_fires_the_day_after_earnings(tmp_path):
    import datetime as dt

    from quant.data.earnings import GUARD_FACTOR, earnings_guard_factor
    _cached(tmp_path, "AAPL", ["2026-08-10"])
    f, when = earnings_guard_factor(
        "AAPL", dt.date(2026, 8, 11), str(tmp_path), fetch=lambda s: [])
    assert f == GUARD_FACTOR and when == "2026-08-10"


def test_guard_fires_the_day_before_earnings(tmp_path):
    import datetime as dt

    from quant.data.earnings import GUARD_FACTOR, earnings_guard_factor
    _cached(tmp_path, "AAPL", ["2026-08-12"])
    f, _ = earnings_guard_factor(
        "AAPL", dt.date(2026, 8, 11), str(tmp_path), fetch=lambda s: [])
    assert f == GUARD_FACTOR


def test_guard_is_off_outside_the_window(tmp_path):
    import datetime as dt

    from quant.data.earnings import earnings_guard_factor
    _cached(tmp_path, "AAPL", ["2026-08-01", "2026-09-01"])
    f, when = earnings_guard_factor(
        "AAPL", dt.date(2026, 8, 11), str(tmp_path), fetch=lambda s: [])
    assert f == 1.0 and when is None


def test_next_earnings_date_still_looks_forward_only(tmp_path):
    """예고용(다음 발표일) 조회는 과거를 돌려주면 안 된다 — 용도가 다르다."""
    import datetime as dt

    from quant.data.earnings import next_earnings_date
    _cached(tmp_path, "AAPL", ["2026-08-01", "2026-09-01"])
    d = next_earnings_date("AAPL", dt.date(2026, 8, 11), str(tmp_path),
                           fetch=lambda s: [])
    assert d == dt.date(2026, 9, 1)
