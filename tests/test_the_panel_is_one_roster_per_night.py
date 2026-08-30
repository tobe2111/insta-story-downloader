"""패널 명단은 **밤마다 하나**다 (2026-08-29 장부 실측).

■ 무엇이 잘못돼 있었나

패널 관문은 "한 설정을 여러 종목에 돌려 날짜별 횡단 평균을 관측 하나로
본다". 그러려면 그날 밤 **모든 종목이 같은 명단**을 돌아야 한다. 그런데
명단을 뽑는 날짜가 종목마다 달랐다 — 각 종목의 **마지막 봉 날짜**였다.

코인은 주말에도 봉이 생기고 주식은 안 생긴다. 그래서 봉 날짜가 갈리는
밤에는 한 통에 **서로 다른 명단 둘**이 담겼다.

    2026-08-29 장부 실측 (12종목이 돈 밤):
        cross_rank ×3  … 종목  5   ← 08-29 명단
        ml         ×3  … 종목  7   ← 08-27 명단
        동시검정: 설정 6개 · 날짜 79일

    같은 밤 다른 실행(쪼개지지 않은 경우):
        설정 3개 · 종목 12 · 날짜 120일

■ 왜 이것이 조용한 손실인가

세 가지를 한꺼번에 잃는다.

  ① **횡단 폭이 반으로 준다.** 패널의 이득은 종목을 가로질러 잡음이
     상쇄되는 데서 나온다. 12종목이 5와 7로 갈리면 그 상쇄가 반만 된다.
  ② **다중검정 부담이 두 배가 된다.** 부트스트랩은 담긴 설정 수를 센다.
     3개를 재려고 낸 비용으로 6개어치 벌을 받는다.
  ③ **자가 다시 짧아진다.** 표를 세로로 맞출 때 날짜를 교집합하므로,
     참여 종목이 다른 설정들이 섞이면 날짜까지 깎인다(120 → 79, -34%).
     패널을 만든 이유가 바로 "재는 자가 짧다"였는데 그 자를 도로 잘랐다.

그리고 어디에도 빨간불이 안 떴다 — 숫자는 멀쩡한 모양으로 장부에 남고,
성적이 안 나오면 시장 탓으로 읽힌다.
"""
from __future__ import annotations

import inspect
import json

import pytest

from quant.live import retrain as R


def test_the_night_hands_every_symbol_the_same_roster_date():
    """밤 배치가 **한 날짜**를 정해 모든 종목에 넘긴다(배선 확인).

    함수가 명단 날짜를 받을 수 있는 것과 밤 배치가 하나로 정해 넘기는 것은
    다른 일이다 — 안 넘기면 각 종목이 다시 자기 봉 날짜로 뽑는다.
    """
    src = inspect.getsource(R.run_retrain_all)
    assert "roster_asof" in src, "밤 배치가 명단 날짜를 정하지 않는다"
    call = src[src.index("run_retrain(market, symbol"):]
    call = call[:call.index(")\n")]
    assert "panel_asof=roster_asof" in call, (
        "종목마다 자기 봉 날짜로 명단을 뽑는다 — 봉 날짜가 갈리는 밤에 "
        "패널이 둘로 쪼개진다")
    # 정한 날짜는 루프 **밖**에서 한 번만 정해져야 한다(안이면 다시 갈린다).
    assert (src.index("roster_asof =")
            < src.index("for idx, (market, symbol)")), (
        "명단 날짜를 종목 루프 안에서 정한다 — 하나로 정한 뜻이 없다")


def test_run_retrain_uses_the_given_date_not_the_last_bar():
    """넘겨받은 날짜가 있으면 **그것으로** 명단을 뽑는다."""
    call = inspect.getsource(R.run_retrain)
    call = call[call.index("panel_specs=shared_panel_specs("):]
    call = call[:call.index("\n\n")]
    assert "panel_asof or asof" in call, (
        "넘겨받은 밤의 날짜를 안 쓴다 — 배선만 있고 효력이 없다")
    assert "panel_asof" in inspect.signature(R.run_retrain).parameters


def test_two_different_dates_really_do_give_different_rosters():
    """⚠️ 전제 확인 — 날짜가 다르면 **명단이 실제로 다르다**.

    같았다면 위 검사들은 있지도 않은 위험을 지키는 장식이다. 회전이
    멈추거나 명단이 하나로 줄면 여기서 빨간불이 뜬다.
    """
    a = [R.spec_key(s) for s in R.shared_panel_specs("2026-08-27")]
    b = [R.spec_key(s) for s in R.shared_panel_specs("2026-08-29")]
    assert set(a).isdisjoint(b), (
        f"이틀치 명단이 겹친다: {a} vs {b} — 쪼개짐이 눈에 안 띄게 된다")
    assert len(a) == R.PANEL_ROSTER_PER_NIGHT


class _FakeCollector:
    """설정 N개어치 판정을 그대로 돌려주는 최소 수집기."""

    def __init__(self, n_specs: int):
        self._n = n_specs

    def verdicts(self, t_threshold=None):
        return [{"spec_key": json.dumps({"i": i}), "n_symbols": 5,
                 "n_dates": 120, "mean_diff": 0.0, "t_stat": 0.1,
                 "pass": False, "symbol_wins": 2, "symbol_win_rate": 0.4,
                 "gain": {"variance_gain": 1.0}} for i in range(self._n)]

    def panel_frame(self, *a, **k):
        import pandas as pd
        return pd.DataFrame()


def test_a_split_night_is_flagged_in_the_ledger_itself(tmp_path):
    """명단보다 설정이 많으면 장부가 **스스로 고장이라고 적는다**.

    이 결함이 오래 안 보였던 이유는 쪼개진 밤의 숫자가 '성적이 나쁜 밤'과
    똑같이 생겼기 때문이다. 장부가 말하지 않으면 시장 탓으로 읽힌다.
    """
    rec = R.record_panel("2026-08-29", _FakeCollector(R.PANEL_ROSTER_PER_NIGHT * 2),
                         str(tmp_path), n_symbols_seen=12,
                         roster_asof="2026-08-29")
    assert "roster_split" in rec, (
        "명단 3개짜리 밤에 설정 6개가 담겼는데 장부가 아무 말도 안 한다")
    assert str(R.PANEL_ROSTER_PER_NIGHT) in rec["roster_split"]


def test_a_normal_night_is_not_flagged(tmp_path):
    """대조군 — 정상인 밤에는 **아무 표시도 안 한다**.

    ⚠️ 이게 없으면 "언제나 고장"도 위 검사를 통과한다. 늘 켜져 있는
       경고등은 꺼진 것과 같다(감사 99).
    """
    rec = R.record_panel("2026-08-29", _FakeCollector(R.PANEL_ROSTER_PER_NIGHT),
                         str(tmp_path), n_symbols_seen=12,
                         roster_asof="2026-08-29")
    assert "roster_split" not in rec


def test_the_ledger_remembers_which_roster_it_measured(tmp_path):
    """장부에 **명단 날짜**가 남는다 — 회전은 날짜만 보므로 이 한 칸이면
    그날의 명단 전체가 되살아난다. 안 남기면 "왜 저 설정을 쟀나"에 답할
    수 없다.
    """
    rec = R.record_panel("2026-08-29", _FakeCollector(1), str(tmp_path),
                         n_symbols_seen=12, roster_asof="2026-08-27")
    assert rec["roster_asof"] == "2026-08-27"
    line = json.loads((tmp_path / R.PANEL_FILE).read_text("utf-8").strip())
    assert line["roster_asof"] == "2026-08-27", "파일에는 안 적혔다"
    # 옛 호출부(날짜를 안 넘기는 곳)도 조용히 죽지 않는다 — 자료 날짜로 채운다.
    old = R.record_panel("2026-08-29", _FakeCollector(1), str(tmp_path))
    assert old["roster_asof"] == "2026-08-29"


@pytest.mark.parametrize("asof", ["2026-08-27", "2026-08-28", "2026-08-29"])
def test_one_roster_covers_every_symbol_in_a_mixed_market_night(asof):
    """⚠️ 이 결함의 재현 — 시장이 섞인 밤에도 명단이 **하나**여야 한다.

    코인은 주말에 봉이 있고 주식은 없다. 종목의 마지막 봉으로 뽑으면 같은
    밤에 명단이 갈린다. 밤의 날짜 하나로 뽑으면 갈릴 수가 없다.
    """
    per_symbol = {  # 실제로 이렇게 갈렸다(2026-08-29 장부)
        "crypto:BTC/USDT": "2026-08-29",
        "us_stock:AAPL": "2026-08-27",
        "kr_stock:005930": "2026-08-27"}
    fixed = {k: [R.spec_key(s) for s in R.shared_panel_specs(asof)]
             for k in per_symbol}
    assert len({tuple(v) for v in fixed.values()}) == 1, (
        "밤의 날짜로 뽑았는데도 종목마다 명단이 다르다")
    split = {k: [R.spec_key(s) for s in R.shared_panel_specs(d)]
             for k, d in per_symbol.items()}
    assert len({tuple(v) for v in split.values()}) > 1, (
        "종목 봉 날짜로 뽑아도 명단이 안 갈린다 — 이 결함이 났던 자리가 "
        "사라졌다면 위 검사들이 지키는 것이 없다")

def test_the_batch_really_hands_a_real_date_down(monkeypatch, tmp_path):
    """배선을 **돌려서** 확인한다 — 소스에 글자가 있는 것으로는 부족하다.

    ``roster_asof``를 빈 문자열로 만들어 놓아도 소스 검사는 다 통과한다
    (변수도 있고 넘기기도 한다). 그런데 빈 문자열은 호출부에서
    ``panel_asof or asof``에 걸려 **조용히 종목별 봉 날짜로 되돌아간다** —
    고친 것이 그대로 원위치되는데 아무 데도 빨간불이 안 뜬다.

    그래서 실제로 배치를 돌려, 종목들이 **같은 날짜**를, 그것도 **빈 값이
    아닌 날짜**를 받는지 본다.
    """
    got: list = []

    def fake_run_retrain(market, symbol, **kw):
        got.append(kw.get("panel_asof"))
        return {"skipped": False, "asof": "2026-08-27", "panel_diffs": {}}

    monkeypatch.setattr(R, "run_retrain", fake_run_retrain)
    R.run_retrain_all(targets=[("crypto", "BTC/USDT"), ("us_stock", "AAPL"),
                               ("kr_stock", "005930")],
                      state_dir=str(tmp_path))
    assert len(got) == 3
    assert len(set(got)) == 1, f"종목마다 다른 명단 날짜를 받았다: {got}"
    assert got[0], "명단 날짜가 비어 있다 — 호출부에서 종목 봉 날짜로 되돌아간다"
    # 그 날짜로 뽑은 명단이 실제로 명단 크기만큼 나온다(빈 값이면 전체가 온다).
    assert len(R.shared_panel_specs(got[0])) == R.PANEL_ROSTER_PER_NIGHT
    line = json.loads((tmp_path / R.PANEL_FILE).read_text("utf-8").strip())
    assert line["roster_asof"] == got[0], (
        "장부에 적힌 명단 날짜가 실제로 쓴 것과 다르다")


# ── 밤의 두 회차가 UTC 자정에 갈리던 것 (2026-08-30 장부 실측) ──────────

def test_the_two_runs_of_one_night_share_a_roster_date():
    """⚠️ 이 결함의 재현 — **밤 배치는 하루에 두 번 돈다.**

    본 실행 21:15 UTC · 예비 22:45 UTC. 러너가 밀리면 두 번째가 **UTC
    자정을 넘어간다.** 그러면 같은 밤의 두 회차가 다른 날짜를 갖고, 명단이
    날짜로 회전하므로 **다른 명단을 돌게 된다.**

    실측(패널 장부가 쌓인 3밤, 커밋 시각):

        08-28 05:53 · 06:52          UTC 같은 날 ✓
        08-29 03:40 · 04:22          UTC 같은 날 ✓
        08-29 23:57 · 08-30 01:15    UTC **다른 날** ✗

    UTC로 묶으면 1/3, 한국 날짜로 묶으면 3/3이다.
    """
    import datetime as _dt

    U = _dt.timezone.utc
    nights = [("2026-08-28 05:53", "2026-08-28 06:52"),
              ("2026-08-29 03:40", "2026-08-29 04:22"),
              ("2026-08-29 23:57", "2026-08-30 01:15")]   # 자정을 넘은 밤
    for a, b in nights:
        ka, kb = (R.night_key(_dt.datetime.fromisoformat(t).replace(tzinfo=U))
                  for t in (a, b))
        assert ka == kb, (
            f"한 밤의 두 회차가 다른 열쇠를 받는다: {a}→{ka} vs {b}→{kb} — "
            "명단이 갈리면 작업 #56이 그 밤의 두 줄을 합칠 수 없다")
        assert (R.shared_panel_specs(ka) == R.shared_panel_specs(kb)), (
            "열쇠는 같은데 명단이 다르다 — 회전이 날짜만 보지 않는다")


def test_utc_really_would_have_split_that_night():
    """대조군 — **UTC로는 실제로 갈렸다**는 것을 못 박는다.

    ⚠️ 이게 없으면 위 검사는 "아무 열쇠나 항상 같다"로도 통과한다. 그리고
       더 중요하게, 갈리지 않는 상황을 지키는 검사는 안전장치가 아니라
       장식이다 — 전제가 사라지면 빨간불이 뜨게 한다.
    """
    import datetime as _dt

    U = _dt.timezone.utc
    a = _dt.datetime(2026, 8, 29, 23, 57, tzinfo=U)
    b = _dt.datetime(2026, 8, 30, 1, 15, tzinfo=U)
    assert a.date() != b.date(), "UTC로도 안 갈린다 — 이 결함이 났던 자리가 없다"
    assert R.night_key(a) == R.night_key(b) == "2026-08-30"
    assert (R.shared_panel_specs(a.date().isoformat())
            != R.shared_panel_specs(b.date().isoformat())), (
        "UTC 날짜 둘이 같은 명단을 준다 — 그러면 고칠 것이 없었다는 뜻이다")


def test_the_night_key_is_the_korean_calendar_day():
    """열쇠는 **한국 달력일**이다 — 경계가 배치 창 밖에 있어야 한다.

    한국 자정은 15:00 UTC다. 배치 창(06:15~12:00 KST)에서 가장 멀리 떨어진
    자리라 어느 회차도 경계에 걸리지 않는다.
    """
    import datetime as _dt

    from quant.live.market_hours import KST

    U = _dt.timezone.utc
    # 한국 자정 직전/직후에서 열쇠가 바뀐다(경계가 15:00 UTC).
    assert R.night_key(_dt.datetime(2026, 8, 29, 14, 59, tzinfo=U)) == "2026-08-29"
    assert R.night_key(_dt.datetime(2026, 8, 29, 15, 1, tzinfo=U)) == "2026-08-30"
    # 예정된 두 회차(21:15 · 22:45 UTC)는 같은 열쇠를 받는다.
    for hh, mm in ((21, 15), (22, 45)):
        assert R.night_key(
            _dt.datetime(2026, 8, 29, hh, mm, tzinfo=U)) == "2026-08-30"
    # ⚠️ 시간대는 한 곳에서만 온다 — 같은 규칙이 두 곳에 있으면 갈라진다.
    src = inspect.getsource(R.night_key)
    assert "market_hours import KST" in src, (
        "시간대를 여기서 다시 정의한다 — 언젠가 저쪽과 갈라진다")
    assert KST.utcoffset(None) == _dt.timedelta(hours=9)


def test_a_naive_time_does_not_silently_shift_the_night():
    """시간대가 없는 시각을 줘도 **조용히 어긋나지 않는다**(UTC로 읽는다)."""
    import datetime as _dt

    naive = _dt.datetime(2026, 8, 29, 23, 57)
    aware = naive.replace(tzinfo=_dt.timezone.utc)
    assert R.night_key(naive) == R.night_key(aware) == "2026-08-30"


def test_the_batch_uses_the_night_key_not_the_utc_day():
    """밤 배치가 **실제로** 그 열쇠를 쓴다(배선 확인)."""
    src = inspect.getsource(R.run_retrain_all)
    line = next(l for l in src.splitlines() if "roster_asof =" in l)
    assert "night_key()" in line, (
        f"밤 배치가 UTC 달력일로 명단을 정한다: {line.strip()} — "
        "두 회차가 자정을 사이에 두면 다른 명단을 돈다")
    assert "_today_iso()" not in line
