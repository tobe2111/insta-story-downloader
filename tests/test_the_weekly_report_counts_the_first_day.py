"""주간 리포트가 계좌의 첫날을 안 센다 — 부호가 반대로 나간다 (감사 241).

주간 수익의 기준점은 "창 직전 마지막 기록"인데, **직전 기록이 없으면**
`window[0]["equity"]` — 즉 **첫 기록 자기 자신**을 기준으로 삼고 있었다.
그러면 첫날 수익이 항상 0이 되고, 계좌가 문을 연 첫 주의 성적에서 첫날의
움직임이 통째로 빠진다.

실측(원화 계좌 첫 주, 원금 1,000,000원 · 기록 999,635.06 → 999,847.15):

    리포트   주간 **+0.02%** · 최악일 2026-08-13 **+0.00%**
    사실     주간 **-0.0153%** · 최악일 2026-08-13 **-0.0365%**

**부호가 반대다.** 그리고 이 리포트는 월요일 아침 텔레그램으로 나간다.

감사 239(낙폭이 원금을 고점으로 안 친다)와 **같은 병**이다 — 기준선에서
원금이 빠지면 첫날 손실이 사라진다. 같은 실수가 두 자리에 있었다.

함께 발견: 화살표가 화면의 숫자와 어긋났다. 파이썬의 음의 0(-0.0)은
`>= 0`이 참이면서 `+.2f`로는 "-0.00"으로 찍힌다 — 실제로 그렇게 나갔다:

    🔺 us_stock:QQQ: 주간 -0.00%

화면이 스스로 모순되면 나머지 숫자도 함께 의심받는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import (  # noqa: E402
    _week_base_principal,
    format_weekly,
    weekly_summary,
)

ROOT = Path(__file__).resolve().parent.parent


def _account(tmp_path, *, start_cash, equities, dates=None, deposits=None,
             market="portfolio", symbol="ALL", name="portfolio_ALL.json"):
    dates = dates or [f"2026-08-{13 + i:02d}" for i in range(len(equities))]
    st = {"market": market, "symbol": symbol, "start_cash": start_cash,
          "cash": 0.0, "positions": {}, "last_bar": dates[-1],
          "deposits": deposits or [],
          "history": [{"date": d, "equity": float(e), "price": 100.0}
                      for d, e in zip(dates, equities)]}
    paper = tmp_path / "paper"
    paper.mkdir(exist_ok=True)
    (paper / name).write_text(json.dumps(st), "utf-8")
    return st


def _week(tmp_path):
    return weekly_summary(str(tmp_path))["markets"]["portfolio:ALL"]


# ── 첫 주가 원금 대비인가 ─────────────────────────────────────

def test_the_first_week_is_measured_against_the_principal(tmp_path):
    """실측 그 장면 — +0.02%가 아니라 -0.02%가 나와야 한다."""
    _account(tmp_path, start_cash=1_000_000.0,
             equities=[999_635.06, 999_847.15])
    m = _week(tmp_path)
    # 요약은 소수점 2자리로 반올림해 저장한다 — 같은 자리에서 비교한다
    assert m["week_return_pct"] == pytest.approx(
        round((999_847.15 / 1_000_000.0 - 1) * 100, 2), abs=1e-9)
    assert m["week_return_pct"] < 0, "손실인데 이익으로 보고한다"


def test_the_first_day_can_be_the_worst_day(tmp_path):
    """첫날 손실이 '최악일'에서 사라지던 자리."""
    _account(tmp_path, start_cash=1_000_000.0,
             equities=[999_635.06, 999_847.15])
    worst = _week(tmp_path)["worst_day"]
    assert worst["date"] == "2026-08-13"
    assert worst["pct"] == pytest.approx(-0.04, abs=1e-9)


def test_a_first_day_gain_is_counted_too(tmp_path):
    """대조군 — 방향과 무관하게 첫날이 세어져야 한다."""
    _account(tmp_path, start_cash=1_000_000.0, equities=[1_050_000.0])
    assert _week(tmp_path)["week_return_pct"] == pytest.approx(5.0)


# ── 창 앞에 기록이 있으면 그대로 ───────────────────────────────

def test_a_week_with_a_prior_record_uses_that_record(tmp_path):
    """대조군 — 직전 기록이 있으면 원금이 아니라 그 기록이 기준이다.

    안 그러면 2주차부터 누적 수익이 매주 다시 세어진다.
    """
    dates = [f"2026-08-{d:02d}" for d in (1, 8, 9)]
    _account(tmp_path, start_cash=1_000_000.0,
             equities=[900_000.0, 990_000.0, 1_000_000.0], dates=dates)
    m = _week(tmp_path)
    # 창(08-08~) 직전 기록은 08-01의 900,000
    assert m["week_return_pct"] == pytest.approx(
        round((1_000_000.0 / 900_000.0 - 1) * 100, 2), abs=1e-9)


# ── 입금을 두 번 세지 않는가 ──────────────────────────────────

def test_a_deposit_before_any_record_is_counted_exactly_once(tmp_path):
    """기록이 하나도 없던 시절의 입금 — 정확히 한 번만 세어야 한다.

    그 돈은 필연적으로 **첫 기록의 자산**에 들어가 있다. 그래서 기준선은
    시작금 그대로 두고, 빼는 일은 `flows`에게 맡긴다. 둘 다 하면 두 번
    세어 입금이 통째로 손실로 보인다(실측 -92%).
    """
    st = _account(tmp_path, start_cash=80_000.0, equities=[1_000_000.0],
                  dates=["2026-08-13"],
                  deposits=[{"date": "2026-08-01", "amount": 920_000.0,
                             "settled_bar": "2026-08-01"}])
    # 기준은 시작금 그 자체다 — 입금은 flows가 첫 기록에서 뺀다.
    # 둘 다 하면 두 번 세어 입금이 통째로 손실로 보인다(실측 -92%).
    assert _week_base_principal(st, "2026-08-13") == pytest.approx(80_000.0)
    assert _week(tmp_path)["week_return_pct"] == pytest.approx(0.0)


def test_a_deposit_that_landed_before_the_week_is_not_subtracted_again(tmp_path):
    """창보다 **오래된** 입금이 창 첫날로 끌려오면 안 된다.

    귀속을 창만 보고 잡으면, 창 이전에 이미 자산에 들어간 돈이 "창 첫
    기록에서 들어온 것"으로 취급돼 그 주 수익에서 빠진다 — 이미 기준선에
    포함된 돈을 또 빼는 것이라 **한 주가 통째로 -50%로 보인다.**
    """
    dates = ["2026-08-01", "2026-08-02", "2026-08-08", "2026-08-09"]
    _account(tmp_path, start_cash=900_000.0,
             equities=[900_000.0, 1_820_000.0, 1_830_000.0, 1_840_000.0],
             dates=dates,
             deposits=[{"date": "2026-08-02", "amount": 920_000.0,
                        "settled_bar": "2026-08-02"}])
    m = _week(tmp_path)          # 창은 08-03~08-09 → 기준은 08-02의 1,820,000
    assert m["week_return_pct"] == pytest.approx(
        round((1_840_000.0 / 1_820_000.0 - 1) * 100, 2), abs=1e-9), (
        f"창 이전 입금을 또 뺐다: {m['week_return_pct']}")


def test_a_deposit_settled_inside_the_week_is_not_double_counted(tmp_path):
    """창 안의 입금은 flows가 이미 뺀다 — 여기서 더하면 두 번이다.

    입금이 기준에도 들어가고 수익에서도 빠지면, **입금이 손실로 보인다**
    (감사 211의 거울상).
    """
    st = _account(tmp_path, start_cash=80_000.0, equities=[1_000_000.0],
                  dates=["2026-08-13"],
                  deposits=[{"date": "2026-08-13", "amount": 920_000.0,
                             "settled_bar": "2026-08-13"}])
    assert _week_base_principal(st, "2026-08-13") == pytest.approx(80_000.0)
    m = _week(tmp_path)
    assert m["week_return_pct"] == pytest.approx(0.0, abs=1e-6), (
        f"입금이 수익/손실로 둔갑했다: {m['week_return_pct']}")


# ── 옛 장부와의 하위 호환 ─────────────────────────────────────

def test_a_ledger_without_start_cash_falls_back(tmp_path):
    """시작금 필드가 없던 시절 기록 — 지금까지와 같은 값이 나와야 한다."""
    st = {"market": "portfolio", "symbol": "ALL",
          "history": [{"date": "2026-08-13", "equity": 50.0, "price": 1.0}]}
    assert _week_base_principal(st, "2026-08-13") == 50.0


@pytest.mark.parametrize("bad", [None, 0, -1, "x"])
def test_a_broken_start_cash_falls_back(bad):
    st = {"start_cash": bad,
          "history": [{"date": "2026-08-13", "equity": 77.0}]}
    assert _week_base_principal(st, "2026-08-13") == 77.0


# ── 화살표가 화면의 숫자와 같은 것을 보는가 ────────────────────

def _line(pct):
    s = {"period": ("2026-08-08", "2026-08-14"), "swaps": [],
         "markets": {"x:Y": {"week_return_pct": pct, "equity": 100.0,
                             "total_return_pct": 0.0}}}
    return [ln for ln in format_weekly(s).splitlines() if ln.startswith(
        ("🔺", "🔻", "➖"))][0]


def test_a_negative_zero_is_not_an_up_arrow():
    """"🔺 QQQ: 주간 -0.00%" 가 실제로 나갔다."""
    line = _line(-0.0)
    assert not line.startswith("🔺"), line


@pytest.mark.parametrize("pct,mark", [
    (1.5, "🔺"), (-1.5, "🔻"), (0.0, "➖"), (-0.0, "➖"),
    (0.001, "➖"),     # 화면에 +0.00%로 찍히는 값 — 화살표도 중립
    (-0.001, "➖"),
    (0.006, "🔺"),     # +0.01%로 찍힌다
    (-0.006, "🔻"),
])
def test_the_arrow_matches_the_printed_number(pct, mark):
    line = _line(pct)
    assert line.startswith(mark), line


def test_the_arrow_and_the_number_never_contradict():
    """반올림 경계 전체를 훑어 화살표와 부호가 어긋나는 값이 없는지 본다."""
    for i in range(-300, 301):
        pct = i / 100.0
        line = _line(pct)
        shown = line.split("주간 ")[1].split("%")[0]
        if line.startswith("🔺"):
            assert not shown.startswith("-"), (pct, line)
        elif line.startswith("🔻"):
            assert shown.startswith("-"), (pct, line)
        else:
            assert shown in ("+0.00", "-0.00"), (pct, line)


# ── 진짜 장부에서도 방향이 맞는가 ─────────────────────────────

def test_the_real_ledger_reports_the_right_sign():
    """지금 계좌는 원금 아래에 있다 — 주간 리포트가 그렇게 말해야 한다."""
    path = ROOT / "state" / "paper" / "portfolio_ALL.json"
    if not path.exists():
        pytest.skip("장부 없음")
    d = json.loads(path.read_text("utf-8"))
    hist = d.get("history") or []
    if len(hist) > 7:
        pytest.skip("첫 주가 아니다 — 이 검사의 전제가 끝났다")
    m = weekly_summary("state")["markets"].get("portfolio:ALL")
    if not m:
        pytest.skip("요약에 통합 계좌가 없다")
    true_pct = (hist[-1]["equity"] / float(d["start_cash"]) - 1) * 100
    assert (m["week_return_pct"] > 0) == (true_pct > 0), (
        f"주간 {m['week_return_pct']:+.4f}% vs 원금 대비 {true_pct:+.4f}%")
