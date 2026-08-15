"""얼어붙은 시세가 주말과 구별되지 않는다 (감사 243).

멱등 가드는 "새 봉이 없으면 조용히 건너뛴다"라서, 시세 공급이 끊겨도 주말과
똑같이 침묵합니다. 그래서 감사 226이 **정체 경보**를 만들었습니다 — 며칠째
새 봉을 못 받아 건너뛰는 종목을 세어 화면에 띄우는 규칙입니다.

그 경보가 **재학습 배치에만 배선돼 있었습니다.** 돈을 굴리는 쪽인 페이퍼
배치는 배치 건강 기록에 `stale`을 아예 넘기지 않아, 사이트의 정체 경보가
그쪽에서는 영영 울리지 않는 구조였습니다.

    quant/live/retrain.py   _write_run_health(..., stale=stale_targets(...))  ✅
    quant/live/daily.py     _write_run_health(..., skipped=skipped)           ❌

실측(2026-08-14 배치): `run_health.paper` = **성공 0 · 실패 0 · 건너뜀 20**.
20종목 전부가 아무 일도 안 한 날인데 사이트에 뜬 경보는 0건이었습니다.
감사 139(거래소 규격을 아무도 안 물었다)와 같은 계열 — 만들어 놓고 배선하지
않은 장치입니다.

그리고 **달력 일수로 세면 안 됩니다.** 시장마다 여는 날이 다릅니다:

    2026-08-15(토) · 마지막 봉 08-13 기준
        코인   놓친 세션 2 (08-14 · 08-15 — 코인은 매일 연다)
        주식   놓친 세션 1 (08-14 — 토요일은 애초에 안 연다)

    2026-08-18(화) 기준
        코인   5세션 → 경보     미국주식 3세션 → 경보
        한국주식 2세션 → 조용   (08-17은 광복절 대체휴일 — 안 여는 날이다)

같은 이틀이 시장마다 다른 뜻입니다. 하나의 달력 일수로 세면 코인 시세가
얼어붙은 사고와 주말이 섞이고, **주말과 구별되지 않는 경보는 꺼진 경보**
입니다(감사 99).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.market_calendar import missed_sessions  # noqa: E402
from quant.live.daily import paper_stale_targets  # noqa: E402
from quant.live.flag_watch import _current_flags  # noqa: E402

# 2026-08-17은 광복절(08-15 토) 대체휴일 — 저장소의 달력이 그렇게 말한다.
HOLIDAYS = {"kr_stock": ["2026-08-17"], "us_stock": []}


# ── 시장마다 '열렸어야 한 날'이 다르다 ────────────────────────

def test_the_weekend_counts_for_coins_but_not_for_stocks():
    """실측 그 장면 — 같은 이틀이 시장마다 다른 뜻이다."""
    assert missed_sessions("crypto", "2026-08-13", "2026-08-15") == 2
    assert missed_sessions("kr_stock", "2026-08-13", "2026-08-15") == 1
    assert missed_sessions("us_stock", "2026-08-13", "2026-08-15") == 1


def test_a_holiday_is_not_a_missed_session():
    """08-17은 한국이 안 여는 날이다 — 못 받은 게 아니라 없는 것이다."""
    kr = missed_sessions("kr_stock", "2026-08-13", "2026-08-18", HOLIDAYS)
    us = missed_sessions("us_stock", "2026-08-13", "2026-08-18", HOLIDAYS)
    assert kr == 2, f"한국 휴장일을 거래일로 셌다: {kr}"
    assert us == 3, f"미국은 08-17에 열었다: {us}"


def test_without_a_calendar_it_still_counts_weekdays():
    """대조군 — 달력이 없어도 요일까지는 안다(달력은 '더 아는 것')."""
    assert missed_sessions("kr_stock", "2026-08-13", "2026-08-18", None) == 3


def test_the_same_day_is_zero():
    assert missed_sessions("crypto", "2026-08-15", "2026-08-15") == 0


@pytest.mark.parametrize("bad", ["", "언젠가", None, "2026-13-45"])
def test_an_unreadable_date_is_unknown_not_zero(bad):
    """0('정상')과 None('모른다')을 섞으면 고장이 정상으로 보인다."""
    assert missed_sessions("crypto", bad, "2026-08-15") is None


# ── 페이퍼 장부를 읽어 정체를 세는가 ──────────────────────────

def _ledger(tmp_path, key, last_date):
    market, _, symbol = key.partition(":")
    safe = f"{market}_{symbol}".replace("/", "_")
    d = tmp_path / "paper"
    d.mkdir(exist_ok=True)
    (d / f"{safe}.json").write_text(json.dumps(
        {"market": market, "symbol": symbol, "last_bar": last_date,
         "history": [{"date": last_date, "equity": 100.0, "price": 1.0}]}),
        "utf-8")


def test_a_frozen_coin_feed_is_flagged(tmp_path):
    _ledger(tmp_path, "crypto:BTC/USDT", "2026-08-13")
    got = paper_stale_targets(["crypto:BTC/USDT"], str(tmp_path),
                              today="2026-08-18", holidays=HOLIDAYS)
    assert got == {"crypto:BTC/USDT": 5}


def test_one_session_behind_is_not_an_alarm(tmp_path):
    """대조군 — 매일 울리는 경보는 꺼진 경보와 같다(감사 99).

    배치가 그 시장의 마감보다 이르면 한 세션 뒤처지는 것이 정상이다.
    """
    _ledger(tmp_path, "us_stock:SPY", "2026-08-13")
    assert paper_stale_targets(["us_stock:SPY"], str(tmp_path),
                               today="2026-08-14", holidays=HOLIDAYS) == {}


def test_the_korean_holiday_keeps_it_quiet(tmp_path):
    """실측 그 장면 — 같은 날 미국은 울리고 한국은 조용해야 한다."""
    _ledger(tmp_path, "kr_stock:005930.KS", "2026-08-13")
    _ledger(tmp_path, "us_stock:SPY", "2026-08-13")
    got = paper_stale_targets(["kr_stock:005930.KS", "us_stock:SPY"],
                              str(tmp_path), today="2026-08-18",
                              holidays=HOLIDAYS)
    assert got == {"us_stock:SPY": 3}, f"휴장일을 장애로 셌다: {got}"


def test_it_loads_the_calendar_by_itself(tmp_path):
    """부르는 쪽이 달력을 안 줘도 **스스로 읽어야** 한다.

    ⚠️ 처음 판은 `holidays`를 받기만 하고 기본값이 None이었다 — 운영 배치는
       그 인자를 안 넘기므로 공휴일이 전부 거래일로 세어졌다. 실측: 광복절
       대체휴일(2026-08-17)이 낀 구간에서 국내주식이 2세션이 아니라 3세션
       밀린 것으로 잡혀 **정상 휴장이 시세 장애로 보고됐다.**
    """
    import datetime as dt

    import quant.data.market_calendar as mc
    mc._MEMO.clear()
    today = dt.date.today()
    (tmp_path / "holidays.json").write_text(json.dumps({
        "fetched": today.isoformat(),
        "since": (today - dt.timedelta(days=365)).isoformat(),
        "until": (today + dt.timedelta(days=365)).isoformat(),
        "markets": HOLIDAYS}), "utf-8")
    _ledger(tmp_path, "kr_stock:005930.KS", "2026-08-13")
    _ledger(tmp_path, "us_stock:SPY", "2026-08-13")
    got = paper_stale_targets(["kr_stock:005930.KS", "us_stock:SPY"],
                              str(tmp_path), today="2026-08-18")
    assert got == {"us_stock:SPY": 3}, f"달력을 안 읽었다: {got}"


def test_a_ledger_we_cannot_read_is_not_invented(tmp_path):
    """장부가 없으면 '정체 0'이 아니라 **판정하지 않는다**."""
    assert paper_stale_targets(["crypto:BTC/USDT"], str(tmp_path),
                               today="2026-08-18") == {}


def test_nothing_skipped_means_nothing_to_count(tmp_path):
    assert paper_stale_targets([], str(tmp_path)) == {}


# ── 배선돼 있는가 (이 감사의 본체) ────────────────────────────

def _call_kwargs(func_name: str, callee: str, path: Path) -> list[set]:
    """소스를 파싱해 그 함수 안의 호출 인자 이름을 모은다.

    ⚠️ 문자열로 찾지 않는다 — 줄바꿈·변수 이름이 바뀌면 검사가 헛돈다
       (이 저장소가 반복해서 겪은 계열). 구조를 봐야 하면 파싱한다.
    """
    tree = ast.parse(path.read_text("utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for call in ast.walk(node):
                if (isinstance(call, ast.Call)
                        and getattr(call.func, "id", "") == callee):
                    out.append({k.arg for k in call.keywords})
    return out


def test_the_paper_batch_actually_reports_staleness(tmp_path, monkeypatch):
    """규칙이 있어도 **배선이 없으면** 경보는 영영 안 울린다(감사 139 계열).

    ⚠️ 처음 쓴 판은 소스를 파싱해 `stale=` 인자가 있는지만 봤다. 변이 시험이
       그 자리를 찔러 잡았다 — `stale=None`으로 바꿔도 인자는 그대로 있어서
       검사가 초록이었다. **모양이 아니라 결과를 본다**: 배치를 실제로 돌려
       장부에 정체가 적혔는지 확인한다.
    """
    import quant.live.daily as D

    _ledger(tmp_path, "crypto:BTC/USDT", "2026-08-13")
    monkeypatch.setattr(D, "run_daily_paper",
                        lambda market, symbol, **kw: {"skipped": True})
    monkeypatch.setattr(D, "paper_stale_targets",
                        lambda skipped, sd, **kw: {k: 5 for k in skipped})
    D.run_daily_paper_all([("crypto", "BTC/USDT")], state_dir=str(tmp_path))
    health = json.loads((tmp_path / "run_health.json").read_text("utf-8"))
    assert health["paper"].get("stale"), (
        f"페이퍼 배치가 정체를 안 남겼다 — 사이트 경보가 못 울린다: "
        f"{health['paper']}")
    assert health["paper"].get("stale_unit") == "거래일", health["paper"]


def test_the_paper_batch_is_wired_to_the_real_counter():
    """대조군 — 정체를 **계산해서** 넘기는지(상수를 넣으면 안 넘긴 것이다)."""
    tree = ast.parse((ROOT / "quant" / "live" / "daily.py").read_text("utf-8"))
    vals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_daily_paper_all":
            for call in ast.walk(node):
                if (isinstance(call, ast.Call)
                        and getattr(call.func, "id", "") == "_write_run_health"):
                    vals += [k.value for k in call.keywords if k.arg == "stale"]
    assert vals, "페이퍼 배치가 정체를 아예 안 넘긴다"
    assert all(isinstance(v, ast.Call) for v in vals), (
        "정체 자리에 상수가 들어 있다 — 넘기지 않는 것과 같다")


def test_the_retrain_batch_still_reports_staleness():
    """대조군 — 원래 배선돼 있던 쪽을 끊지 않았는지."""
    calls = _call_kwargs("run_retrain_all", "_write_run_health",
                         ROOT / "quant" / "live" / "retrain.py")
    assert calls and all("stale" in kw for kw in calls), calls


# ── 화면이 단위를 지어내지 않는가 ─────────────────────────────

def _flag(kind, entry):
    return _current_flags({"run_health": {kind: entry}})


def test_the_paper_alarm_says_trading_days():
    f = _flag("paper", {"date": "2026-08-18", "ok": 0, "failed": 0,
                        "skipped": 1, "stale": {"crypto:BTC/USDT": 5},
                        "max_stale_days": 5, "stale_unit": "거래일"})
    msg = "\n".join(f.values())
    assert "5거래일" in msg, f"단위를 지어냈다: {msg}"


def test_the_retrain_alarm_still_says_calendar_days():
    """대조군 — 재학습은 달력 일수로 잰다. 두 단위를 한 말로 섞으면 안 된다."""
    f = _flag("retrain", {"date": "2026-08-18", "ok": 0, "failed": 0,
                          "skipped": 1, "stale": {"crypto:BTC/USDT": 7},
                          "max_stale_days": 7})
    msg = "\n".join(f.values())
    assert "7일" in msg and "거래일" not in msg, msg


def test_a_healthy_run_raises_no_alarm():
    assert not _flag("paper", {"date": "2026-08-18", "ok": 20, "failed": 0,
                               "skipped": 0})
