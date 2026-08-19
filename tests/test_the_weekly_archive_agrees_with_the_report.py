"""공개 주간 아카이브가 주간 리포트와 다른 값을 말한다 (감사 246).

감사 241에서 텔레그램 주간 리포트의 부호를 고쳤습니다. 그런데 **같은 병을
가진 형제**가 공개 페이지에 그대로 남아 있었습니다 — `docs/weekly.html`은
자기 자바스크립트 복사본으로 주간 수익률을 세고 있었고, 그 복사본은 아예
다른 값을 쓰고 있었습니다:

    const ret = cur.day_pct != null ? cur.day_pct : ...

`day_pct`는 **그 주 마지막 날 하루치**입니다. 열 제목은 "주간 수익률"인데
매주 마지막 하루를 주간 성적으로 내보내고 있었습니다.

실측(2026-08-10 주, 브라우저로 띄워 읽은 값):

    아카이브 페이지  **+0.02%**   ← 08-14 하루치
    사실(원금 대비)  **-0.02%**   ← 1,000,000 → 999,847.15

**부호가 반대입니다.** 그리고 종목 표는 첫 주를 통째로 비워 두고 있었습니다
(직전 주 기록이 없으면 `–`) — 20종목 중 13종목이 빈칸이었습니다.

㉞ 같은 판정을 두 곳에서 쓰면 언젠가 갈라집니다. 그래서 셈을 한 곳으로
모았습니다: 배치가 `_window_return` 하나로 계산해 `status.json`에 실어
보내고, **페이지는 읽기만 합니다.** 집계가 없으면 지어내지 않고 "아직
주간 집계가 없습니다"라고 적습니다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import (  # noqa: E402
    _monday_of,
    weekly_archive,
    weekly_summary,
)

WEEKLY = (ROOT / "docs" / "weekly.html").read_text("utf-8")
# 주석은 코드가 아니다 — 옛 결함을 **설명하는** 주석까지 금지하면 그 설명을
# 지우게 되고, 왜 이렇게 됐는지가 사라진다(이 저장소는 그 설명을 남긴다).
CODE = re.sub(r"/\*.*?\*/", " ", re.sub(r"<!--.*?-->", " ", WEEKLY, flags=re.S),
              flags=re.S)


def _ledger(tmp_path, name, *, market, symbol, start_cash, rows, deposits=None):
    d = tmp_path / "paper"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps({
        "market": market, "symbol": symbol, "start_cash": start_cash,
        "cash": 0.0, "positions": {}, "deposits": deposits or [],
        "last_bar": rows[-1][0],
        "history": [{"date": dt, "equity": float(eq), "price": 100.0,
                     "day_pct": pctv}
                    for dt, eq, pctv in rows]}), "utf-8")


# ── 주 경계 ──────────────────────────────────────────────────

@pytest.mark.parametrize("day,monday", [
    ("2026-08-10", "2026-08-10"),   # 월요일 그 자신
    ("2026-08-14", "2026-08-10"),   # 금요일
    ("2026-08-16", "2026-08-10"),   # 일요일 — 다음 주로 넘기지 않는다
    ("2026-08-17", "2026-08-17"),
])
def test_the_week_starts_on_monday(day, monday):
    assert _monday_of(day) == monday


# ── 아카이브가 하루치를 주간이라 부르지 않는가 ────────────────

def test_the_first_week_is_measured_against_the_principal(tmp_path):
    """실측 그 장면 — +0.02%가 아니라 -0.02%여야 한다.

    `day_pct`를 일부러 +0.02로 넣어 둔다. 그걸 집어 들면 검사가 빨개진다.
    """
    _ledger(tmp_path, "portfolio_ALL.json", market="portfolio", symbol="ALL",
            start_cash=1_000_000.0,
            rows=[("2026-08-13", 999_635.06, -0.04),
                  ("2026-08-14", 999_847.15, 0.02)])
    got = weekly_archive(str(tmp_path))["portfolio:ALL"]["2026-08-10"]
    assert got["return_pct"] == pytest.approx(-0.02), (
        f"마지막 하루치를 주간 수익률로 내보냈다: {got}")
    assert got["equity"] == pytest.approx(999_847.15)


def test_a_later_week_counts_from_the_previous_week(tmp_path):
    """대조군 — 둘째 주부터는 직전 주 마지막 자산이 기준이다."""
    _ledger(tmp_path, "crypto_BTC_USDT.json", market="crypto",
            symbol="BTC/USDT", start_cash=10_000.0,
            rows=[("2026-08-07", 10_000.0, 0.0),
                  ("2026-08-14", 11_000.0, 5.0)])
    rows = weekly_archive(str(tmp_path))["crypto:BTC/USDT"]
    assert rows["2026-08-10"]["return_pct"] == pytest.approx(10.0), rows


def test_the_first_week_of_a_symbol_is_not_blank(tmp_path):
    """첫 주를 '–'로 비우면 20종목 중 13종목이 빈칸이 된다(실측)."""
    _ledger(tmp_path, "us_stock_SPY.json", market="us_stock", symbol="SPY",
            start_cash=10_000.0, rows=[("2026-08-14", 10_100.0, 1.0)])
    rows = weekly_archive(str(tmp_path))["us_stock:SPY"]
    assert rows["2026-08-10"]["return_pct"] == pytest.approx(1.0)


def test_a_deposit_is_not_a_weekly_gain(tmp_path):
    """입금이 주간 수익으로 둔갑하면 안 된다(감사 211·241과 같은 규칙)."""
    _ledger(tmp_path, "portfolio_ALL.json", market="portfolio", symbol="ALL",
            start_cash=80_000.0,
            rows=[("2026-08-13", 1_000_000.0, 0.0)],
            deposits=[{"date": "2026-08-13", "amount": 920_000.0,
                       "settled_bar": "2026-08-13"}])
    row = weekly_archive(str(tmp_path))["portfolio:ALL"]["2026-08-10"]
    assert row["return_pct"] == pytest.approx(0.0, abs=1e-6), (
        f"입금이 수익으로 보인다: {row}")
    assert row["deposit"] == pytest.approx(920_000.0), "입금 사실을 안 밝힌다"


# ── 두 곳이 같은 말을 하는가 ──────────────────────────────────

def test_the_archive_and_the_telegram_report_agree(tmp_path):
    """같은 주를 두 화면이 다르게 말하면 둘 다 못 믿는다."""
    _ledger(tmp_path, "portfolio_ALL.json", market="portfolio", symbol="ALL",
            start_cash=1_000_000.0,
            rows=[("2026-08-13", 999_635.06, -0.04),
                  ("2026-08-14", 999_847.15, 0.02)])
    arch = weekly_archive(str(tmp_path))["portfolio:ALL"]["2026-08-10"]
    rep = weekly_summary(str(tmp_path))["markets"]["portfolio:ALL"]
    assert arch["return_pct"] == pytest.approx(rep["week_return_pct"])


def test_the_real_ledger_agrees_too():
    """진짜 장부에서도 두 값이 같아야 한다(합성 데이터만으로는 부족하다)."""
    if not (ROOT / "state" / "paper" / "portfolio_ALL.json").exists():
        pytest.skip("장부 없음")
    arch = weekly_archive("state").get("portfolio:ALL") or {}
    rep = weekly_summary("state")["markets"].get("portfolio:ALL")
    if not arch or not rep:
        pytest.skip("집계할 기록이 없다")
    last = sorted(arch)[-1]
    # ⚠️ 두 화면은 창이 다르다 — 아카이브는 **달력 주**(월요일~), 리포트는
    #    **최근 7일**(마지막 기록일 기준). 계좌의 모든 기록이 한 주 안에
    #    있던 첫 주에는 우연히 같은 날들을 봤지만, 8-19 배치가 새 주의
    #    기록을 만들자 두 창이 갈라졌다(아카이브 8-17주=+0.35 vs 리포트
    #    7일=+0.07 — 둘 다 맞는 숫자다). 같은 날들을 볼 때만 같아야 한다.
    import datetime as dt
    import json as _json
    from quant.live.daily import _monday_of
    with open(ROOT / "state" / "paper" / "portfolio_ALL.json",
              encoding="utf-8") as f:
        dates = [r["date"] for r in _json.load(f).get("history") or []]
    week_days = {d for d in dates if _monday_of(d) == last}
    anchor = max(dt.date.fromisoformat(d) for d in dates)
    start = anchor - dt.timedelta(days=6)
    rep_days = {d for d in dates if dt.date.fromisoformat(d) >= start}
    if week_days != rep_days:
        pytest.skip("달력 주와 최근 7일이 다른 날들을 보는 주 — "
                    "두 값이 다른 것이 정상이다")
    assert arch[last]["return_pct"] == pytest.approx(rep["week_return_pct"]), (
        f"아카이브 {arch[last]['return_pct']} vs 리포트 "
        f"{rep['week_return_pct']}")


# ── 페이지가 계산을 그만뒀는가 ────────────────────────────────

def test_the_page_no_longer_computes_its_own_weekly_return():
    assert "day_pct" not in CODE, (
        "페이지가 아직 하루치(day_pct)를 주간 수익률로 쓴다")
    assert "st.weekly" in CODE, "페이지가 배치가 낸 집계를 안 읽는다"


def test_the_page_does_not_keep_its_own_week_boundary():
    """주 경계도 한 곳에서 정한다 — 두 규칙이면 또 갈라진다."""
    assert "mondayOf" not in CODE, (
        "페이지가 자기 주 경계 규칙을 갖고 있다")


def test_the_page_says_so_instead_of_inventing(tmp_path):
    """집계가 없으면 지어내지 않는다."""
    assert "아직 주간 집계가 없습니다" in WEEKLY
    assert "지어낸 값을 대신 보여주지 않습니다" in WEEKLY


def test_the_footnote_matches_what_the_code_does():
    """설명이 계산과 다르면 그 설명이 다음 결함이다."""
    note = WEEKLY.split('class="note"', 1)[1][:600]
    for phrase in ("직전 주가 없으면 원금", "입금은 수익이 아니"):
        assert phrase in re.sub(r"<[^>]+>", "", note), (
            f"각주가 '{phrase}'를 말하지 않는다")


def test_the_batch_ships_the_archive():
    """화면이 읽어도 배치가 안 실으면 영영 빈칸이다(감사 229)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["weekly"] = wk' in src, "배치가 주간 집계를 안 실어 보낸다"


def test_the_correction_is_disclosed():
    """공개 페이지에 나갔던 숫자다 — 조용히 고치지 않는다."""
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    v = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                                   re.sub(r"<!--.*?-->", " ", trust, flags=re.S)))
    for phrase in ("주간 아카이브", "+0.02%", "-0.02%", "페이지는 읽기만"):
        assert phrase in v, f"신뢰 페이지에 '{phrase}'가 없다"
    assert "과거 기록은 고치지 않습니다" in v
