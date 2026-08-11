import pytest



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


# ── 가드가 실제로 발동하는가 (감사 62) ────────────────────────
#
# 변이 시험에서 발동 조건(`abs((d - asof).days) <= pad_days`)을 죽여
# **항상 비발동**으로 만들어도 아무 검사가 실패하지 않았다. 실적 발표일
# 전후는 변동성이 가장 큰 구간이고, 공분산은 발표 일정을 모르므로 하필
# 그날 목표보다 더 실린다 — 그걸 막으라고 만든 장치다.


def test_guard_fires_inside_the_window_and_not_outside(tmp_path, monkeypatch):
    import datetime as _dt

    from quant.data import earnings as eg

    day = _dt.date(2026, 8, 20)
    monkeypatch.setattr(eg, "nearest_earnings_date",
                        lambda sym, asof, sd, fetch=None: day)

    # 발표 당일·±1일은 발동(비중 절반), 그 밖은 비발동(1.0)
    for delta, want in ((0, eg.GUARD_FACTOR), (-1, eg.GUARD_FACTOR),
                        (1, eg.GUARD_FACTOR), (-3, 1.0), (5, 1.0)):
        f, d = eg.earnings_guard_factor(
            "AAPL", day + _dt.timedelta(days=delta),
            state_dir=str(tmp_path), pad_days=1)
        if want < 1.0:
            assert f == want and d == day.isoformat(), delta
        else:
            assert f == 1.0 and d is None, delta


def test_guard_factor_actually_halves():
    """GUARD_FACTOR가 1.0으로 되돌려지면(사실상 해제) 잡는다."""
    from quant.data.earnings import GUARD_FACTOR
    assert 0.0 < GUARD_FACTOR < 1.0, "실적 가드가 아무것도 줄이지 않는다"


def test_guard_is_wired_after_the_scaler():
    """감쇠 계수로 따로 두고 스케일 뒤에 곱하는 배선이 유지되는가.

    비중에 바로 곱하면 뒤의 변동성 스케일러가 되돌려 키워 가드가 사라진다
    (2026-08-11 감사에서 고친 결함).
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parent.parent
    src = (root / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "guard_damp[key] = ef" in src
    assert "eff = w * eff_scale * vscale * guard_damp.get(key, 1.0)" in src


def test_per_symbol_path_actually_halves_the_recorded_weight(monkeypatch,
                                                             tmp_path):
    """종목별 페이퍼 경로에서 가드가 실제로 비중을 깎는가 (감사 63).

    커버리지로 보니 이 블록(daily.py의 `weight = float(weight * ef)`)이
    어떤 테스트에서도 실행된 적이 없었다. 통합 계좌 쪽은 오늘 아침
    '스케일러가 되돌려 키운다'는 결함을 고치며 계약 검사를 붙였는데,
    종목별 경로는 구조가 달라(사이징이 이미 끝난 뒤에 곱한다) 그 검사에
    걸리지 않았고 자기 검사도 없었다.
    """
    import datetime as dt
    import json

    import numpy as np
    import pandas as pd

    from quant.data import earnings as eg
    from quant.live import daily as dl

    rng = np.random.default_rng(6)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 300)))
    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    bars = pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)
    last_day = dt.date.fromisoformat(str(bars.index[-1])[:10])

    class _P:
        def get_ohlcv(self, *a, **k):
            return bars.copy()

    class _S:
        name = "fixed"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(0.9, index=df.index)

    def _run(state_dir, guard_on):
        monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
        monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _S())
        monkeypatch.setattr(dl, "champion_spec",
                            lambda *a, **k: {"strategy": "fixed", "params": {}})
        monkeypatch.setattr(
            eg, "nearest_earnings_date",
            lambda sym, asof, sd, fetch=None: last_day if guard_on else None)
        dl.run_daily_paper("us_stock", "SPY", state_dir=str(state_dir),
                           require_real_data=False)
        st = json.loads((state_dir / "paper" / "us_stock_SPY.json")
                        .read_text(encoding="utf-8"))
        return st["history"][-1]

    off = _run(tmp_path / "off", guard_on=False)
    on = _run(tmp_path / "on", guard_on=True)

    assert off["earnings_guard"] is None
    assert on["earnings_guard"], "발표일인데 가드 흔적이 없다"
    assert on["earnings_guard"]["factor"] == eg.GUARD_FACTOR
    assert on["weight"] == pytest.approx(off["weight"] * eg.GUARD_FACTOR,
                                         abs=1e-4), (
        f"가드가 비중을 안 깎았다: {off['weight']} → {on['weight']}")
