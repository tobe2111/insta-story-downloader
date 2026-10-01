"""13F 수집기가 SEC 공정접근을 지키고, 막힌 날을 '아무도 안 샀다'로 바꾸지 않는가 (감사 331).

실측(2026-10-01 야간 배치 로그): `HTTP Error 429: Too Many Requests`가 수백 줄.
조회기가 쉼 없이 두드려 SEC가 막았고, 막힌 뒤에도 제출을 1999년까지 거슬러
하나씩 두드렸다. 이력은 0점, 홈페이지의 13F 칸은 출시 후 한 번도 안 채워졌다.
그리고 장중 러너는 13F 캐시를 커밋하지 않아 15분마다 처음부터 두드렸다.

여기서 지키는 것:
  ① 요청 사이 간격 — SEC 한도(초당 10회) 아래.
  ② 429·503은 물러났다가(Retry-After를 따라) 다시 시도, 404는 되풀이 안 함.
  ③ 제출자 하나가 막히면 몇 번 만에 접는다 — 1999년까지 안 간다.
  ④ 막힌 밤은 쌓아 둔 이력을 지우지 않는다. 깨끗한 조회는 언제나 이긴다.
  ⑤ 밤 조회가 오늘 스냅샷을 써서, 장중 회차는 EDGAR로 안 나간다.
  ⑥ 그 캐시가 장중 러너의 커밋에 실린다(따로 — 없는 날 커밋 전체를 안 깨게).
"""
from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

import quant.data.thirteenf as TF

ROOT = Path(__file__).resolve().parent.parent

INFO = ('<?xml version="1.0"?><informationTable><infoTable>'
        '<nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip>'
        '<value>1</value></infoTable></informationTable>')


class _Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, retry_after=None):
    hdrs = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("u", code, "x", hdrs, None)


# ── ① 간격 ───────────────────────────────────────────────────────
def test_back_to_back_requests_are_spaced_below_the_sec_limit(monkeypatch):
    clk = _Clock()
    monkeypatch.setattr(TF, "_last_call", [0.0])
    calls = []

    def opener(req, timeout=0):
        calls.append(clk.t)
        return _Resp(b"{}")

    for _ in range(5):
        TF._urllib_fetch("https://x", sleep=clk.sleep, clock=clk.now, opener=opener)
    gaps = [b - a for a, b in zip(calls, calls[1:])]
    assert all(g >= TF.MIN_INTERVAL_S - 1e-9 for g in gaps), gaps
    assert TF.MIN_INTERVAL_S >= 0.1          # 초당 10회를 넘지 않는다


# ── ② 재시도 ─────────────────────────────────────────────────────
def test_a_429_backs_off_as_told_and_then_succeeds(monkeypatch):
    clk = _Clock()
    monkeypatch.setattr(TF, "_last_call", [0.0])
    seq = [_http_error(429, retry_after=3), _Resp(b"ok")]

    def opener(req, timeout=0):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    out = TF._urllib_fetch("https://x", sleep=clk.sleep, clock=clk.now, opener=opener)
    assert out == "ok"
    assert 3.0 in clk.slept                  # SEC가 말한 만큼 쉬었다


def test_a_404_is_not_retried(monkeypatch):
    clk = _Clock()
    monkeypatch.setattr(TF, "_last_call", [0.0])
    n = [0]

    def opener(req, timeout=0):
        n[0] += 1
        raise _http_error(404)

    with pytest.raises(urllib.error.HTTPError):
        TF._urllib_fetch("https://x", sleep=clk.sleep, clock=clk.now, opener=opener)
    assert n[0] == 1


def test_a_persistent_429_gives_up_after_the_attempt_budget(monkeypatch):
    clk = _Clock()
    monkeypatch.setattr(TF, "_last_call", [0.0])
    n = [0]

    def opener(req, timeout=0):
        n[0] += 1
        raise _http_error(429)

    with pytest.raises(urllib.error.HTTPError):
        TF._urllib_fetch("https://x", sleep=clk.sleep, clock=clk.now, opener=opener)
    assert n[0] == TF.MAX_ATTEMPTS
    assert max(clk.slept) <= TF.RETRY_CAP_S


# ── ③ 막힌 제출자는 접는다 ───────────────────────────────────────
def _submissions(n):
    return json.dumps({"filings": {"recent": {
        "form": ["13F-HR"] * n,
        "accessionNumber": [f"0000000000-{i:02d}-000001" for i in range(n)],
        "filingDate": [f"20{25 - i // 4:02d}-0{1 + i % 4}-15" for i in range(n)],
        "reportDate": ["2024-12-31"] * n}}})


def test_a_blocked_filer_is_not_walked_back_to_1999():
    folder_hits = [0]

    def fetch(url, timeout=12.0):
        if "submissions" in url:
            return _submissions(60)              # 제출이 60개 쌓인 제출자
        folder_hits[0] += 1
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    out = TF.filings_history("0001067983", fetch=fetch, max_filings=12)
    assert out == []
    assert folder_hits[0] == TF.MAX_CONSECUTIVE_FAILURES, folder_hits[0]


def test_attempts_are_capped_even_when_some_succeed():
    hits = [0]

    def fetch(url, timeout=12.0):
        if "submissions" in url:
            return _submissions(60)
        hits[0] += 1
        if url.endswith("index.json"):
            # 두 번에 한 번만 성공 — 연속 실패 차단기는 안 걸린다
            if hits[0] % 4 == 1:
                raise RuntimeError("flaky")
            return json.dumps({"directory": {"item": [{"name": "it.xml"}]}})
        return INFO

    out = TF.filings_history("0001067983", fetch=fetch, max_filings=3)
    assert len(out) <= 3
    assert hits[0] <= 2 * (3 + 2)           # 폴더+정보표 두 번씩, 시도 상한 안


# ── ④ 막힌 밤은 이력을 지우지 않는다 ─────────────────────────────
def _good_fetch(url, timeout=12.0):
    if "submissions" in url:
        return json.dumps({"filings": {"recent": {
            "form": ["13F-HR", "13F-HR"],
            "accessionNumber": ["0001-26-000002", "0001-26-000001"],
            "filingDate": ["2026-08-14", "2026-05-15"],
            "reportDate": ["2026-06-30", "2026-03-31"]}}})
    if "index.json" in url:
        return json.dumps({"directory": {"item": [{"name": "it.xml"}]}})
    return INFO


def _blocked_fetch(url, timeout=12.0):
    raise RuntimeError("HTTP Error 429: Too Many Requests")


FILERS = {"0001067983": "Berkshire"}


def test_a_blocked_night_keeps_the_history_it_already_had(tmp_path):
    good = TF.refresh_history(str(tmp_path), fetch=_good_fetch, filers=FILERS,
                              today="2026-09-30")
    assert len(good) == 2
    again = TF.refresh_history(str(tmp_path), fetch=_blocked_fetch, filers=FILERS,
                               today="2026-10-01")
    assert again == good                     # 지우지 않았다
    rep = TF.load_fetch_report(str(tmp_path))
    assert rep["fetch"]["ok"] is False
    assert rep["fetch"]["kept_previous"] is True
    assert rep["fetch"]["errors"] >= 1
    assert "429" in rep["fetch"]["last_error"]
    assert rep["points"] == 2


def test_a_blocked_first_night_says_so_instead_of_reporting_nobody(tmp_path):
    TF.refresh_history(str(tmp_path), fetch=_blocked_fetch, filers=FILERS,
                       today="2026-10-01")
    rep = TF.load_fetch_report(str(tmp_path))
    assert rep["points"] == 0
    assert rep["fetch"]["ok"] is False and rep["fetch"]["errors"] >= 1


def test_a_clean_pull_always_replaces(tmp_path):
    TF.refresh_history(str(tmp_path), fetch=_good_fetch, filers=FILERS,
                       today="2026-09-30")

    def clean_empty(url, timeout=12.0):        # 오류 없이 제출이 하나도 없다
        return json.dumps({"filings": {"recent": {"form": []}}})

    out = TF.refresh_history(str(tmp_path), fetch=clean_empty, filers=FILERS,
                             today="2026-10-01")
    assert out == []
    assert TF.load_fetch_report(str(tmp_path))["fetch"]["ok"] is True


def test_the_filer_summary_says_who_holds_what_and_when(tmp_path):
    TF.refresh_history(str(tmp_path), fetch=_good_fetch, filers=FILERS,
                       today="2026-09-30")
    f = TF.load_fetch_report(str(tmp_path))["filers"][0]
    assert f["filed"] == "2026-08-14" and f["report"] == "2026-06-30"
    assert f["holds"] == ["AAPL"] and f["filings"] == 2


# ── ⑤ 장중 회차는 밤 스냅샷을 쓴다 ───────────────────────────────
def test_the_nightly_pull_writes_todays_snapshot_so_rounds_stay_offline(tmp_path):
    TF.refresh_history(str(tmp_path), fetch=_good_fetch, filers=FILERS,
                       today="2026-10-01")

    def boom(*a, **k):
        raise AssertionError("장중 회차가 EDGAR를 두드렸다")

    snap = TF.refresh(str(tmp_path), now="2026-10-01T14:00:00+00:00", fetch=boom,
                      filers=FILERS)
    assert snap["cluster"]["AAPL"]["count"] == 1
    assert snap["cluster"]["AAPL"]["as_of"] == "2026-06-30"


def test_the_snapshot_never_uses_a_filing_from_the_future(tmp_path):
    """스냅샷 날짜보다 늦게 제출된 보유는 그날의 스냅샷에 못 들어간다."""
    TF.refresh_history(str(tmp_path), fetch=_good_fetch, filers=FILERS,
                       today="2026-06-01")         # 8/14 제출은 아직 세상에 없다
    snap = json.loads((tmp_path / TF.CACHE_FILE).read_text("utf-8"))
    assert snap["cluster"]["AAPL"]["as_of"] == "2026-03-31"


# ── ⑥ 배선 ───────────────────────────────────────────────────────
def test_the_intraday_runner_commits_the_13f_cache_on_its_own_line():
    y = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "git add state/thirteenf.json 2>/dev/null || true" in y
    main_add = [ln for ln in y.splitlines() if "git add state/guard_heartbeat.json" in ln]
    assert main_add and "thirteenf" not in main_add[0], \
        "없는 날 이 줄 전체가 실패해 심장박동까지 안 담긴다"


def test_the_nightly_tune_passes_the_contact_user_agent():
    y = (ROOT / ".github" / "workflows" / "nightly-retrain.yml").read_text("utf-8")
    assert "EDGAR_UA: ${{ vars.EDGAR_UA }}" in y


def test_the_request_names_a_contact_even_when_the_repo_variable_is_empty(monkeypatch):
    """저장소 변수가 비면 워크플로는 빈 문자열을 넘긴다 — 그때도 연락처가 실린다."""
    clk = _Clock()
    monkeypatch.setattr(TF, "_last_call", [0.0])
    monkeypatch.setenv("EDGAR_UA", "")
    seen = {}

    def opener(req, timeout=0):
        seen["ua"] = req.get_header("User-agent")
        return _Resp(b"{}")

    TF._urllib_fetch("https://x", sleep=clk.sleep, clock=clk.now, opener=opener)
    assert "@" in seen["ua"] and seen["ua"] == TF._DEFAULT_UA
    monkeypatch.setenv("EDGAR_UA", "Other Co ops@example.com")
    TF._urllib_fetch("https://x", sleep=clk.sleep, clock=clk.now, opener=opener)
    assert seen["ua"] == "Other Co ops@example.com"
