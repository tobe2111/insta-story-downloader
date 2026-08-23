"""달력이 시키는 매매 — 가설 우선 3호(만기 주간)·4호(FOMC 사전 표류).

2026-08-23, 사장님 "얘기해준 거 다 하자" 지시의 후보 등록분. 둘 다 신호의
재료가 **달력**이고 가격을 아예 안 본다 — 수급 가설(만기 결제·롤오버·헤지
되감기 / 발표 전 위험 보상·포지션 정리)이 참인지 오디션이 판정한다.

같은 라운드에 검토한 **지수 편입·편출 수급은 반려**했다: 가설은 충분하나
(지수 펀드는 편입일에 가격 불문 사야 한다), 과거 편입·편출 종목과 시점의
**시점별 이력이 유료 데이터**라 검증 가능한 재료가 없다. 재료 없이 링에
세우면 다중검정 문턱만 올린다 — 반려 사유를 여기 남긴다.

지켜야 할 약속:
- 만기 주간 = [셋째 금요일−4, 셋째 금요일] — 순수 달력 계산, 항상 같은 달.
- FOMC 포지션은 발표일 D의 **D−1·D−2 봉**에 선다(체결 규약상 그 포지션이
  D−1일·D일 수익을 번다 — 문헌의 발표 전 구간).
- 가격이 판단을 못 바꾼다. 미래 봉이 과거 판단을 못 바꾼다.
- FOMC 달력(2020~2026) 밖의 해는 관망 + **경고**(조용한 관망은 고장이다).
- 롱 전용. 달력 날짜는 전부 그 시점 이전에 공표된 정례 일정이다.
"""
from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.fomc import FOMC_DECISION_DAYS, FOMC_LAST_YEAR  # noqa: E402
from quant.strategies.expiry_week import ExpiryWeek, third_friday  # noqa: E402
from quant.strategies.fomc_drift import FOMCDrift               # noqa: E402


def _df(dates, closes=None):
    idx = pd.DatetimeIndex(dates)
    c = np.asarray(closes if closes is not None
                   else [100.0] * len(idx), dtype=float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                         "volume": np.full(len(idx), 1e6)}, index=idx)


def _bdays(start, end):
    return pd.bdate_range(start, end)


# ── 만기 주간 ───────────────────────────────────────────────────

def test_third_friday_is_computed_correctly():
    assert third_friday(2026, 8) == 21     # 2026-08: 금 7·14·21
    assert third_friday(2024, 3) == 15     # 2024-03-01이 금요일
    assert third_friday(2020, 3) == 20     # 2020-03: 금 6·13·20


def test_expiry_week_holds_exactly_the_expiry_week():
    df = _df(_bdays("2026-08-03", "2026-08-31"))
    s = ExpiryWeek().generate_signals(df)
    held = {str(d.date()) for d in s.index[s > 0]}
    # 2026-08 만기 주 = 8/17(월)~8/21(금)
    assert held == {"2026-08-17", "2026-08-18", "2026-08-19",
                    "2026-08-20", "2026-08-21"}, held


def test_expiry_week_price_cannot_change_the_answer():
    dates = _bdays("2026-08-03", "2026-08-31")
    up = ExpiryWeek().generate_signals(
        _df(dates, closes=np.linspace(100, 200, len(dates))))
    dn = ExpiryWeek().generate_signals(
        _df(dates, closes=np.linspace(200, 100, len(dates))))
    assert list(up) == list(dn), "가격이 달력 판단을 바꿨다"


# ── FOMC 사전 표류 ──────────────────────────────────────────────

def test_fomc_position_stands_on_the_two_bars_before_the_decision():
    """2024-06-12(수) 발표 — 포지션은 6/10(월)·6/11(화), 발표일엔 없다."""
    df = _df(_bdays("2024-06-03", "2024-06-21"))
    s = FOMCDrift().generate_signals(df)
    held = {str(d.date()) for d in s.index[s > 0]}
    assert held == {"2024-06-10", "2024-06-11"}, held


def test_fomc_handles_a_thursday_decision():
    """2024-11-07(목, 대선 주간) — 포지션은 11/5(화)·11/6(수)."""
    df = _df(_bdays("2024-10-28", "2024-11-15"))
    s = FOMCDrift().generate_signals(df)
    held = {str(d.date()) for d in s.index[s > 0]}
    assert held == {"2024-11-05", "2024-11-06"}, held


def test_fomc_beyond_the_calendar_is_flat_and_loud(caplog):
    """달력 수명 밖의 해 — 관망은 하되 조용히 하지 않는다."""
    df = _df(_bdays("2027-06-01", "2027-06-30"))
    import logging
    with caplog.at_level(logging.WARNING):
        s = FOMCDrift().generate_signals(df)
    assert float(s.abs().max()) == 0.0
    assert any("달력 수명" in r.message for r in caplog.records), (
        "달력이 끝났는데 경고가 없다 — 조용한 관망은 고장이다")


def test_fomc_price_cannot_change_the_answer_and_no_future_leak():
    dates = _bdays("2024-06-03", "2024-06-21")
    up = FOMCDrift().generate_signals(
        _df(dates, closes=np.linspace(100, 200, len(dates))))
    dn = FOMCDrift().generate_signals(
        _df(dates, closes=np.linspace(200, 100, len(dates))))
    assert list(up) == list(dn), "가격이 달력 판단을 바꿨다"
    short = FOMCDrift().generate_signals(_df(dates[:8]))
    longer = FOMCDrift().generate_signals(_df(dates))
    assert list(short) == list(longer)[:8], "미래 봉이 과거 판단을 바꿨다"


def test_the_fomc_calendar_itself_is_sane():
    """오타가 곧 선견/왜곡이 되는 상수 — 형식·개수·요일을 못 박는다."""
    per_year: dict[int, int] = {}
    for d in FOMC_DECISION_DAYS:
        dt = _dt.date.fromisoformat(d)          # 형식이 틀리면 여기서 죽는다
        per_year[dt.year] = per_year.get(dt.year, 0) + 1
        assert dt.weekday() in (1, 2, 3), (
            f"{d}: FOMC 결정일이 화·수·목이 아니다 — 오타를 의심할 것")
    assert set(per_year) == set(range(2020, FOMC_LAST_YEAR + 1))
    assert all(v == 8 for v in per_year.values()), (
        f"연 8회 정례가 아니다: {per_year}")


# ── 공통 계약 ───────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [ExpiryWeek, FOMCDrift])
def test_never_short_and_hypothesis_written_where_the_rule_lives(cls):
    assert cls(allow_short=True).allow_short is False
    src = (ROOT / "quant" / "strategies"
           / f"{cls.name}.py").read_text("utf-8")
    for word in ("가설", "둔감"):
        assert word in src, f"{cls.name}: 소스에 '{word}'가 없다"
    claims = re.findall(r"(CAGR|승률|연평균|\d+\s*%\s*(수익|상승))", src)
    assert not claims, f"{cls.name}: 바깥 성적을 본문에 적었다: {claims}"


def test_both_are_wired_into_the_ring():
    from quant.live.retrain import build_challengers, champion_spec
    ring = build_challengers(champion_spec("crypto", "BTC/USDT"),
                             seed="x", evolve=True)
    names = {c.get("strategy") for c in ring}
    assert {"expiry_week", "fomc_drift"} <= names, names


def test_the_index_rebalance_rejection_is_recorded():
    """반려에도 기록이 남는다 — 이 파일 머리에 사유가 있다."""
    src = Path(__file__).read_text("utf-8")
    assert "지수 편입·편출" in src and "반려" in src and "유료" in src
