"""휴장일 달력 — 명절에 문 닫힌 걸 아는가 (2026-08-14).

고치기 전 `quant/live/market_hours.py`는 스스로 이렇게 적어 두고 있었다:

    "정직한 한계: 공휴일 달력이 없다. 요일(월~금)과 정규장 시간만 본다."

그래서 실제로 이런 일이 생겼다:

  · **사이트가 설·추석 내내 15초마다 시세를 조른다.** 무료 시세 한도를
    아무도 안 보는 휴장일에 태운다.
  · 화면이 '지연'인지 '휴장'인지 구분하지 못한다 — 값이 안 변하는 것이
    정상인지 고장인지 사람도 알 수 없다.
  · 배치의 `bar_age` 경고가 정상 연휴에 울린다. 가끔 울리는 경보는
    무시하게 되고, 그러면 진짜 신호도 함께 묻힌다.

출처를 증권사 API가 아니라 `exchange_calendars`로 고른 이유: 한국 공휴일은
음력(설·추석)이라 표에 박아 둘 수 없는데, API로 받으면 키가 없는 환경·
네트워크가 끊긴 환경에서 달력이 통째로 사라지고 **그 사실이 조용하다.**
라이브러리는 오프라인으로 같은 답을 주고, 아래처럼 값으로 확인할 수 있다.

지키는 계약:
  · 아는 휴일에는 '개장'이라고 하지 않는다
  · **모르는 것과 아닌 것을 구분한다** — 달력이 없으면 막지 않고, 그
    사실을 문장으로 밝힌다("공휴일 달력이 없어 …판정하지 못합니다")
  · 달력이 없어도 예전과 똑같이 돈다(배포판·최소 설치 환경)
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.market_calendar import (  # noqa: E402
    EXCHANGES,
    holiday_map,
    is_holiday,
)
from quant.live.market_hours import is_market_open, market_status  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))


@pytest.fixture(autouse=True)
def _fresh_memo():
    """달력 캐시(프로세스 안 메모)를 검사마다 비운다.

    ⚠️ 처음에는 이 fixture가 없었고, 검사들이 `state_dir="/nonexistent-…"`를
       넘겼다. 그런데 `holiday_map`은 캐시를 쓰려고 그 디렉터리를 **만든다** —
       파일시스템 루트에 진짜 폴더가 생겼고, 그 뒤로 검사는 그때 만든 캐시를
       읽었다. 그래서 달력 계산을 망가뜨리는 변이가 **검사를 통과했다**
       (변이 시험이 그 자리에서 잡아냈다). 남는 상태는 검사를 눈멀게 한다.
    """
    import quant.data.market_calendar as mc
    mc._MEMO.clear()
    yield
    mc._MEMO.clear()


def _at(y, m, d, h, mi=0):
    """그 순간(KST)을 UTC aware datetime으로."""
    return dt.datetime(y, m, d, h, mi, tzinfo=KST).astimezone(dt.timezone.utc)


# ── 달력이 실제로 맞는 날짜를 주는가 ──────────────────────────

@pytest.mark.parametrize("day", [
    "2026-01-01",   # 신정
    "2026-02-16", "2026-02-17", "2026-02-18",   # 설 (음력 — 표에 못 박는다)
    "2026-03-02",   # 삼일절 대체
    "2026-05-05",   # 어린이날
    "2026-05-25",   # 부처님오신날 대체(5/24가 일요일 → 월요일)
    "2026-09-24", "2026-09-25",   # 추석 (음력)
    "2026-10-09",   # 한글날
])
def test_the_korean_calendar_has_the_lunar_holidays(day, tmp_path):
    """설·부처님오신날은 음력이라 손으로 못 적는다 — 달력이 알아야 한다."""
    days = holiday_map(state_dir=str(tmp_path),
                       today=dt.date(2026, 1, 1), horizon_days=400)
    if not days.get("kr_stock"):
        pytest.skip("exchange_calendars 미설치 — 달력 없이도 도는 것이 계약이다")
    assert day in days["kr_stock"]


def test_the_calendar_does_not_call_weekends_holidays(tmp_path):
    """주말은 빼고 준다 — 요일 판정은 이미 market_hours가 한다.

    같은 판정을 두 곳에서 하면 언젠가 갈라진다(㉞).
    """
    days = holiday_map(state_dir=str(tmp_path),
                       today=dt.date(2026, 1, 1), horizon_days=400)
    if not days:
        pytest.skip("exchange_calendars 미설치")
    for market, ds in days.items():
        for d in ds:
            assert dt.date.fromisoformat(d).weekday() < 5, (
                f"{market} {d}: 주말을 휴장일 목록에 넣었다")


def test_both_markets_are_covered(tmp_path):
    days = holiday_map(state_dir=str(tmp_path),
                       today=dt.date(2026, 1, 1))
    if not days:
        pytest.skip("exchange_calendars 미설치")
    assert set(days) == set(EXCHANGES)


# ── 장 판정이 달력을 쓰는가 ───────────────────────────────────

HOL = {"kr_stock": ["2026-02-16", "2026-02-17", "2026-02-18"],
       "us_stock": ["2026-11-26"]}


def test_a_known_holiday_is_not_open():
    """설 연휴 월요일 10시 — 예전에는 '개장 중'이라고 했다."""
    assert is_market_open("kr_stock", _at(2026, 2, 16, 10), HOL) is False


def test_the_same_moment_is_open_without_a_calendar():
    """대조군 — 달력이 없으면 예전과 똑같이 동작한다(모르면 막지 않는다).

    이게 안 지켜지면 배포판·최소 설치 환경에서 장이 영영 안 열린다.
    """
    assert is_market_open("kr_stock", _at(2026, 2, 16, 10)) is True


def test_an_ordinary_day_still_opens():
    """대조군 — 막는 것만 검사하면 '전부 막는' 코드도 통과한다."""
    assert is_market_open("kr_stock", _at(2026, 2, 19, 10), HOL) is True


def test_one_market_holiday_does_not_close_the_other():
    """한국 설에 미국장은 연다 — 시장별로 따로 봐야 한다."""
    # 2026-02-17(화) 23:40 KST = 09:40 ET — 미국 정규장 안이다.
    # (2/16은 미국도 Presidents' Day 휴장이라 대조가 안 된다 — 17일을 쓴다.)
    assert is_market_open("us_stock", _at(2026, 2, 17, 23, 40), HOL) is True
    # 반대 방향: 추수감사절에 한국장은 연다
    assert is_market_open("kr_stock", _at(2026, 11, 26, 10), HOL) is True
    assert is_market_open("us_stock", _at(2026, 11, 26, 23, 40), HOL) is False


def test_crypto_is_never_closed_by_a_holiday():
    """코인은 24시간이다 — 달력이 코인을 막으면 그게 결함이다."""
    assert is_market_open("crypto", _at(2026, 2, 16, 10), HOL) is True


# ── 말하는 방식: 모르는 것과 아닌 것 ──────────────────────────

def test_the_status_line_names_the_holiday():
    s = market_status("kr_stock", _at(2026, 2, 16, 10), HOL)
    assert "폐장(공휴일)" in s
    assert "판정하지 못합니다" not in s, "아는데도 모른다고 말한다"


def test_the_status_line_admits_when_it_does_not_know():
    """달력이 없는 날 '공휴일 아님'이라고 단정하면 안 된다.

    그 문장을 읽은 사람이 실제 휴장일을 장애로 오해한다.
    """
    # 달력이 없으면 이 시각(설 연휴 월요일 10시)을 '개장 중'이라고 한다 —
    # 그게 예전 동작이고, 여기서 바꾸지 않는다(모르면 막지 않는다).
    assert "개장 중" in market_status("kr_stock", _at(2026, 2, 16, 10))
    # 폐장이라고 말할 때는 **왜 모르는지**를 밝혀야 한다.
    s = market_status("kr_stock", _at(2026, 2, 16, 17))
    assert "공휴일 달력이 없어" in s
    assert "폐장(공휴일)" not in s


def test_a_weekend_is_still_called_a_weekend():
    """대조군 — 주말을 공휴일이라 부르면 안 된다."""
    s = market_status("kr_stock", _at(2026, 2, 21, 10), HOL)   # 토요일
    assert "주말" in s


# ── is_holiday: 모름 = 막지 않음 ──────────────────────────────

@pytest.mark.parametrize("holidays", [None, {}, {"kr_stock": []}])
def test_no_calendar_means_unknown_not_open(holidays):
    assert is_holiday("kr_stock", dt.date(2026, 2, 16), holidays) is False


def test_a_string_date_works_too():
    """장부에서 읽은 ISO 문자열을 그대로 넣어도 같은 답이어야 한다."""
    assert is_holiday("kr_stock", "2026-02-16", HOL) is True
    assert is_holiday("kr_stock", "2026-02-16 09:00:00", HOL) is True


# ── 캐시: 그날 어떤 달력으로 판단했는지 파일로 남는가 ───────────

def test_the_calendar_is_cached_to_the_ledger(tmp_path):
    days = holiday_map(state_dir=str(tmp_path), today=dt.date(2026, 1, 1))
    if not days:
        pytest.skip("exchange_calendars 미설치")
    path = tmp_path / "holidays.json"
    assert path.exists(), "그날 쓴 달력이 파일로 안 남았다 — 재현할 수 없다"
    saved = json.loads(path.read_text("utf-8"))
    assert saved["source"] == "exchange_calendars"
    assert saved["markets"] == days
    assert saved["fetched"] == "2026-01-01"


def test_a_stale_cache_is_refreshed(tmp_path):
    (tmp_path / "holidays.json").write_text(json.dumps({
        "fetched": "2020-01-01", "until": "2020-12-31",
        "markets": {"kr_stock": ["2020-01-01"]}}), "utf-8")
    days = holiday_map(state_dir=str(tmp_path), today=dt.date(2026, 1, 1))
    if not days:
        pytest.skip("exchange_calendars 미설치")
    assert "2020-01-01" not in (days.get("kr_stock") or []), "낡은 달력을 그대로 썼다"


def test_a_fresh_cache_is_reused(tmp_path):
    """달력은 연 단위로만 바뀐다 — 매일 다시 만들 이유가 없다."""
    (tmp_path / "holidays.json").write_text(json.dumps({
        "fetched": "2026-01-01", "since": "2025-11-01", "until": "2027-01-01",
        "markets": {"kr_stock": ["2026-06-06"]}}), "utf-8")
    days = holiday_map(state_dir=str(tmp_path), today=dt.date(2026, 1, 5))
    assert days == {"kr_stock": ["2026-06-06"]}


def test_a_calendar_that_only_looks_forward_is_rebuilt(tmp_path):
    """지난 휴장일을 모르는 달력은 '신선'하지 않다(감사 243).

    "며칠째 새 봉이 없나"를 세려면 **어제가 휴장이었는지**를 알아야 한다.
    앞만 담긴 캐시를 그대로 쓰면 방금 지난 연휴가 통째로 '빠뜨린 세션'으로
    잡혀, 정상 휴장이 시세 장애로 보고된다.
    """
    (tmp_path / "holidays.json").write_text(json.dumps({
        "fetched": "2026-01-01", "until": "2027-01-01",
        "markets": {"kr_stock": ["2026-06-06"]}}), "utf-8")   # since 없음
    days = holiday_map(state_dir=str(tmp_path), today=dt.date(2026, 1, 5))
    assert days != {"kr_stock": ["2026-06-06"]}, "앞만 보는 달력을 그대로 썼다"
    assert "2026-01-01" in days["kr_stock"], "지난 신정을 모른다"


def test_an_old_calendar_beats_no_calendar(tmp_path, monkeypatch):
    """달력을 못 만들면 **옛 캐시라도 쓴다** — 없는 것보다 낫다."""
    (tmp_path / "holidays.json").write_text(json.dumps({
        "fetched": "2020-01-01", "until": "2020-12-31",
        "markets": {"kr_stock": ["2020-01-01"]}}), "utf-8")
    import quant.data.market_calendar as mc
    monkeypatch.setattr(mc, "_compute", lambda *a, **k: None)
    monkeypatch.setattr(mc, "_MEMO", {})
    assert mc.holiday_map(state_dir=str(tmp_path),
                          today=dt.date(2026, 1, 1)) == {"kr_stock": ["2020-01-01"]}


def test_no_calendar_and_no_cache_is_an_empty_dict(tmp_path, monkeypatch):
    import quant.data.market_calendar as mc
    monkeypatch.setattr(mc, "_compute", lambda *a, **k: None)
    monkeypatch.setattr(mc, "_MEMO", {})
    assert mc.holiday_map(state_dir=str(tmp_path), today=dt.date(2026, 1, 1)) == {}


# ── 브라우저에도 실려 나가는가 ────────────────────────────────

def test_the_site_gets_the_calendar_too():
    """사이트는 파이썬을 못 돌린다 — 배치가 실어 보내지 않으면 영영 모른다."""
    root = Path(__file__).resolve().parent.parent
    src = (root / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["holidays"]' in src, "status.json에 달력을 안 싣는다"
    page = (root / "docs" / "index.html").read_text("utf-8")
    assert "st.holidays" in page, "화면이 달력을 안 읽는다"
    assert "QuantLive.marketOpenish(Date.now(),holidays)" in page, (
        "장중 판정에 달력을 안 넘긴다 — 명절에도 15초마다 조른다")
