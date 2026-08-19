"""**가드가 안 걸린 날과, 가드가 아무것도 모르는 날은 다르다** (감사 289).

실적 발표 전후는 하루 만에 가격이 크게 뛰는 날이라, 그날 비중을 줄이는
장치(실적 가드)가 있다. 그런데 2026-08-19까지 그 가드는 **한 번도 발동한
적이 없었다.**

    state/earnings.json  6종목 · 발표일이 들어 있는 종목 **0개**
    장부 earnings_guard  2026-08-13·14·15·19 전부 null

원인은 라이브러리 하나였다. 발표일은 시세 제공처가 HTML 표로 주고, 그
파싱에 `lxml`이 필요한데 설치 목록에 없었다. 배치 로그에는 매일 이렇게
찍히고 있었다.

    실적 캘린더 조회 실패 MSFT: Missing optional dependency 'lxml'.

아픈 것은 **화면이 조용했다는 점**이다. 가드가 안 걸린 날과 똑같이 보였다.
이 저장소의 규칙 그대로다 — 모르는 것과 아닌 것은 다르다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.earnings import calendar_health  # noqa: E402


# ── ① 파싱에 필요한 것이 설치 목록에 있는가 ──────────────────────

def test_the_parser_the_calendar_needs_is_actually_installed():
    """선택 의존성이 아니다 — 없으면 가드가 통째로 죽는다."""
    req = (ROOT / "requirements.txt").read_text("utf-8")
    lines = [ln.strip() for ln in req.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert any(re.match(r"^lxml\b", ln) for ln in lines), (
        "lxml이 설치 목록에 없다 — 실적 발표일 표를 못 읽고, 가드는 매일 "
        "조용히 꺼진다(주석 처리된 줄은 설치되지 않는다)")


# ── ② 아는 것과 모르는 것을 숫자로 구별하는가 ────────────────────

def _cache(tmp_path, data: dict) -> str:
    (tmp_path / "earnings.json").write_text(json.dumps(data), "utf-8")
    return str(tmp_path)


def test_a_calendar_that_knows_nothing_is_visible(tmp_path):
    d = _cache(tmp_path, {"AAPL": {"dates": [], "fetched": "2026-08-07"},
                          "MSFT": {"dates": [], "fetched": ""}})
    h = calendar_health(["AAPL", "MSFT"], d)
    assert h["symbols"] == 2 and h["known"] == 0, h


def test_a_calendar_that_knows_something_says_so(tmp_path):
    d = _cache(tmp_path, {"AAPL": {"dates": ["2026-08-20"],
                                   "fetched": "2026-08-19"},
                          "MSFT": {"dates": [], "fetched": "2026-08-19"}})
    h = calendar_health(["AAPL", "MSFT"], d)
    assert h["known"] == 1, h


def test_the_reason_it_is_empty_is_kept(tmp_path):
    """'못 받았다'와 '없다'가 파일에서 같은 모양이면 영영 구별 못 한다."""
    d = _cache(tmp_path, {"MSFT": {"dates": [], "fetched": "",
                                   "error": "ImportError: lxml"}})
    h = calendar_health(["MSFT"], d)
    assert h.get("errors", {}).get("MSFT", "").endswith("lxml"), h


def test_asking_about_nothing_leaves_no_noise(tmp_path):
    """대조군 — 물어본 종목이 없으면 장부에 아무것도 남기지 않는다."""
    assert calendar_health([], _cache(tmp_path, {})) == {}


def test_a_missing_cache_does_not_explode(tmp_path):
    h = calendar_health(["AAPL"], str(tmp_path / "없는폴더"))
    assert h["known"] == 0 and h["checked"] == 0, h


# ── ③ 조회가 실패하면 그 이유가 캐시에 남는가 ────────────────────

def test_a_failed_fetch_records_why(tmp_path, monkeypatch):
    import datetime as dt

    from quant.data import earnings as E

    def _boom(symbol):
        raise ImportError("Missing optional dependency 'lxml'.")

    E._known_dates("MSFT", dt.date(2026, 8, 19), str(tmp_path), _boom)
    saved = json.loads((tmp_path / "earnings.json").read_text("utf-8"))
    assert "lxml" in (saved["MSFT"].get("error") or ""), saved
    # 실패를 '오늘 받아왔다'로 도장 찍지 않는다(감사 191) — 내일 다시 시도한다.
    assert not saved["MSFT"].get("fetched"), saved


def test_a_good_fetch_clears_the_reason(tmp_path):
    """대조군 — 성공한 뒤에도 옛 오류가 남아 있으면 영영 빨간불이다."""
    import datetime as dt

    from quant.data import earnings as E

    E._known_dates("MSFT", dt.date(2026, 8, 19), str(tmp_path),
                   lambda s: (_ for _ in ()).throw(ImportError("lxml")))
    E._known_dates("MSFT", dt.date(2026, 8, 20), str(tmp_path),
                   lambda s: ["2026-08-25"])
    saved = json.loads((tmp_path / "earnings.json").read_text("utf-8"))
    assert not saved["MSFT"]["error"], saved
    assert saved["MSFT"]["dates"] == ["2026-08-25"], saved


# ── ④ 그 사실이 화면에 나오는가 ──────────────────────────────────

def test_the_screen_says_the_guard_is_blind():
    src = (ROOT / "docs" / "index.html").read_text("utf-8")
    blk = src.split("const flags=[]", 1)[1].split("side-flags", 1)[0]
    assert "pfLast.earnings_calendar" in blk, (
        "가드가 아무것도 모르는 상태를 화면이 기록에서 읽지 않는다 — "
        "그러면 조용한 날과 구별되지 않는다")
    # ⚠️ **낱말이 있는 것과 그리는 것은 다르다.** 조건을 꺼도 경고문과
    #    변수 이름은 그대로 남아, 낱말만 세는 검사는 조용히 통과한다.
    #    그리는 것을 결정하는 **조건 자체**를 못 박는다(감사 278·288의 함정).
    assert "if(ec&&ec.symbols&&!ec.known)" in blk, (
        "가드가 눈먼 상태를 보고 갈라지지 않는다 — 경고가 영영 안 뜬다")
    assert "지키지 못합니다" in blk, (
        "경고가 무슨 일인지 말하지 않는다")


def test_the_ledger_actually_writes_that_field():
    """화면이 읽을 값을 장부가 쓰지 않으면 경고는 영영 안 뜬다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"earnings_calendar"' in src, "장부가 그 값을 남기지 않는다"


def test_the_real_cache_today_is_the_reason_this_test_exists():
    """지금 저장소의 캐시가 실제로 '아무것도 모른다'였다는 기록.

    고쳐져서 발표일이 들어오면 이 검사는 스스로 비켜선다 — 그때는
    위의 검사들이 계속 지킨다.
    """
    path = ROOT / "state" / "earnings.json"
    if not path.exists():
        pytest.skip("캐시 없음")
    cache = json.loads(path.read_text("utf-8"))
    known = [k for k, v in cache.items() if (v or {}).get("dates")]
    if known:
        pytest.skip(f"이제 발표일을 안다({len(known)}종목) — 고쳐졌다")
    assert cache, "캐시가 비어 있다 — 확인할 것이 없다"
