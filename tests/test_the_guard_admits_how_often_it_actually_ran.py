"""장중 감시가 **예약대로 안 돌면 그 사실을 말하는가** (감사 267).

2026-08-15에 장중 감시를 붙이면서 스스로 이렇게 적었다.

    "이 파일의 핵심은 감시가 아니라 '얼마나 자주 봤는지를 기록하는 것'이다.
     15분마다 돌게 설정해 놓고 '15분마다 봅니다'라고 적는 것은 쉽다."

그리고 다음 날 그 기록을 처음 읽어 봤다.

    08-15 17:20 → 08-16 02:37   **558분**
    08-16 02:37 → 08-16 03:31    54분

예약은 15분이다. 공용 러너는 촘촘한 cron을 크게 밀거나 건너뛴다.
**"15분마다 봅니다"는 설정을 옮겨 적은 것이지 사실이 아니었다.**

레버리지 한도는 이미 실측 간격을 쓰므로 안전 쪽으로 계산된다 — 그
설계는 제대로 작동했다. 문제는 **아무도 그 기록을 읽지 않았다**는
것이다. 심장박동은 매 회차 남았고, 공개 페이지는 계속 15분이라고
말하고 있었다. 기록하는 것과 읽는 것은 다른 일이다(감사 265와 같은 계열).

여기서 지키는 것:
  ① 예약 주기가 코드와 워크플로 **두 곳에서 갈라지지 않는다**.
  ② 실제 간격이 예약보다 크게 벌어지면 **사람에게 닿는다**.
  ③ 판정은 실측이 충분할 때만 한다 — 세 번 뛴 기록으로 단정하지 않는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import guard as G  # noqa: E402
from quant.live.flag_watch import _current_flags  # noqa: E402


# ── ① 예약 주기가 두 곳에서 갈라지지 않는가 ─────────────────────

def test_the_code_and_the_schedule_agree_on_the_interval():
    """배포판에는 .github/가 안 실리므로 코드가 값을 갖는다.

    그 순간 같은 사실이 두 곳에 적히므로, 갈라지지 않는지 여기서 본다
    (FROZEN_IDEAS ①). 갈라지면 경보 문턱이 실제 예약과 무관해진다.
    """
    wf = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    m = re.search(r'cron:\s*"\*/(\d+) \* \* \* \*"', wf)
    assert m, "guard.yml의 cron을 읽지 못했다 — 검사가 낡았다"
    assert int(m.group(1)) == G.GUARD_INTERVAL_MINUTES, (
        f"워크플로는 {m.group(1)}분, 코드는 {G.GUARD_INTERVAL_MINUTES}분 — "
        "같은 사실이 두 곳에서 갈라졌다")


def test_the_late_threshold_would_have_caught_the_real_lag():
    """문턱이 실제로 일어난 일을 잡는가 — 상수를 자기 자신과 비교하지 않는다.

    바깥에서 온 사실 둘로 가둔다: 실측 최악 간격 558분은 반드시 걸려야
    하고, 크론이 한두 번 밀린 정도(약 30분)로는 울리면 안 된다.
    """
    limit = G.GUARD_INTERVAL_MINUTES * G.GUARD_LATE_FACTOR
    assert 558 > limit, f"실측 558분이 문턱 {limit}분을 안 넘는다"
    assert 30 < limit, (
        f"문턱 {limit}분이 너무 낮다 — 크론이 한 번 밀릴 때마다 울리면 "
        "아무도 안 본다")


# ── ② 사람에게 닿는가 ───────────────────────────────────────────

def _flags_with_beats(tmp_path, beats: list[str]) -> dict:
    """심장박동을 써 두고 **운영과 같은 경로**로 판정까지 간다.

    `_current_flags`에 직접 값을 만들어 넣지 않는다 — 그러면 재료를 모으는
    쪽(status를 만드는 daily.py)이 빠져서, 배선이 끊겨도 통과한다.
    """
    import json
    (tmp_path / "guard_heartbeat.json").write_text(
        json.dumps({"beats": beats, "actions": []}), encoding="utf-8")
    return _current_flags(_status_from(tmp_path))


def _status_from(state_dir) -> dict:
    """daily.py가 status에 감시 실측을 싣는 그 경로를 그대로 부른다."""
    from quant.live.daily import write_docs_status
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as d:
        st = write_docs_status(state_dir=str(state_dir),
                               docs_path=os.path.join(d, "status.json"))
    return st


def _every(n: int, minutes: int) -> list[str]:
    import datetime as dt
    t0 = dt.datetime(2026, 8, 16, 0, 0, tzinfo=dt.timezone.utc)
    return [(t0 + dt.timedelta(minutes=i * minutes)).isoformat()
            for i in range(n)]


def test_a_nine_hour_gap_reaches_a_human(tmp_path):
    """실제로 일어난 모양 그대로 넣는다 — 촘촘한 기록 + 한 번의 큰 구멍."""
    import datetime as dt
    beats = _every(G.MIN_BEATS_FOR_GAP, 15)
    last = dt.datetime.fromisoformat(beats[-1])
    beats.append((last + dt.timedelta(minutes=558)).isoformat())

    flags = _flags_with_beats(tmp_path, beats)
    hit = [v for k, v in flags.items() if k.startswith("guard_late")]
    assert hit, f"9시간 넘게 감시가 멈췄는데 아무 말이 없다: {sorted(flags)}"
    assert "558" in hit[0], "실제 간격이 몇 분이었는지 숫자가 안 나온다"
    assert "15" in hit[0], "예약 주기와 비교해 주지 않는다"


def test_a_guard_running_on_schedule_stays_quiet(tmp_path):
    """예약대로 도는 날에는 조용해야 한다 — 매일 울리면 꺼진 경보와 같다."""
    flags = _flags_with_beats(tmp_path, _every(G.MIN_BEATS_FOR_GAP + 5, 15))
    assert not [k for k in flags if k.startswith("guard_late")], (
        "15분 간격으로 잘 돌고 있는데 경보가 울린다")


def test_a_mildly_late_run_stays_quiet(tmp_path):
    """크론이 조금 밀린 정도로 울리면 사람이 무시하기 시작한다."""
    flags = _flags_with_beats(tmp_path, _every(G.MIN_BEATS_FOR_GAP + 5, 25))
    assert not [k for k in flags if k.startswith("guard_late")], (
        "25분 간격(예약 15분)에 경보가 울린다 — 너무 예민하다")


# ── ③ 표본이 얇으면 판정하지 않는가 ─────────────────────────────

def test_three_beats_are_not_enough_to_declare_anything(tmp_path):
    """이 저장소가 적중률에서 배운 것과 같은 규칙이다 — 표본이 판정한다.

    실제로 2026-08-16 아침의 기록이 이랬다(3회). 여기서 "558분!"이라고
    단정하면, 이제 막 켠 감시를 고장으로 신고하게 된다.
    """
    beats = ["2026-08-15T17:20:15+00:00",
             "2026-08-16T02:37:50+00:00",
             "2026-08-16T03:31:35+00:00"]
    assert len(beats) < G.MIN_BEATS_FOR_GAP        # 전제 고정
    flags = _flags_with_beats(tmp_path, beats)
    assert not [k for k in flags if k.startswith("guard_late")], (
        "심장박동 3회로 감시 주기를 단정한다")


def test_the_whole_chain_runs_from_heartbeat_to_a_sent_message(tmp_path,
                                                               monkeypatch):
    """심장박동 → 실측 → status → 판정 → **실제 발송**까지 한 번에 본다.

    ⚠️ 변이 시험이 여기서 구멍을 잡았다 — 위 검사들이 안쪽 함수만 불러서,
    재료를 status에 싣는 단계가 빠져도 전부 통과했다. 그 단계는 배치에서
    우연히 맞아떨어지고 있었을 뿐이다. **우연히 맞는 배선은 언젠가 우연히
    틀린다.**
    """
    import datetime as dt
    import json

    from quant.live import flag_watch as FW

    beats = _every(G.MIN_BEATS_FOR_GAP, 15)
    last = dt.datetime.fromisoformat(beats[-1])
    beats.append((last + dt.timedelta(minutes=558)).isoformat())
    (tmp_path / "guard_heartbeat.json").write_text(
        json.dumps({"beats": beats, "actions": []}), encoding="utf-8")

    sent: list[str] = []

    class _N:
        def send(self, msg, level="info"):
            sent.append(msg)
            return True

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _N())

    # ⚠️ 새 알림을 쏘는 것은 `write_docs_status` **자신**이다(daily.py가 그
    #    안에서 check_and_notify_flags를 부른다). 그래서 여기서 한 번 더
    #    부르면 이미 켜진 플래그로 분류돼 조용하다 — 그게 정상이다. 사슬을
    #    보려면 **운영이 실제로 부르는 그 한 번**을 지켜봐야 한다.
    status = _status_from(tmp_path)
    assert (status.get("guard") or {}).get("observed_gap_min"), (
        "status를 만드는 쪽이 감시 실측을 안 싣는다 — 판정할 재료가 없다")
    assert any("558" in m for m in sent), (
        f"심장박동에 9시간 구멍이 있는데 아무것도 발송되지 않았다: {sent}")

    # 같은 경보가 다음 날 또 울리지 않는지도 여기서 본다 — 매일 울리는
    # 경보는 꺼진 경보와 같다(이 모듈의 존재 이유).
    before = len(sent)
    FW.check_and_notify_flags(status, state_dir=str(tmp_path))
    assert len(sent) == before, "이미 켜져 있던 경보가 다시 발송된다"


def test_the_judge_does_not_read_files_behind_its_own_back():
    """판정 함수는 **받은 것만** 봐야 한다.

    ⚠️ 2026-08-16에 여기서 심장박동 파일을 직접 읽게 만들었다가 CI가
    무너졌다. 감시 기록이 쌓이자, 감시와 아무 상관 없는 검사들
    (`test_the_frozen_feed_does_not_look_like_a_weekend` 등)이 "경보 없음"을
    확인하지 못했다 — 그 함수가 **저장소의 지금 상태에 묶였기** 때문이다.
    값으로 확인할 수 없게 된 판정기는 판정기가 아니다.
    """
    import inspect

    from quant.live import flag_watch as FW
    src = inspect.getsource(FW._current_flags)
    for banned in ("open(", "load_heartbeat", "observed_gap_minutes",
                   "os.path.join"):
        assert banned not in src, (
            f"판정 함수가 바깥 상태를 직접 읽는다({banned!r}) — 재료 수집은 "
            "status를 만드는 쪽이 한다")
    assert "state_dir" not in inspect.signature(FW._current_flags).parameters, (
        "판정 함수가 파일 경로를 받는다 — 다시 파일을 읽게 될 문이다")


def test_a_missing_heartbeat_file_does_not_break_the_other_flags(tmp_path):
    """감시 기록이 없다고 다른 경고까지 죽으면 안 된다."""
    flags = _current_flags(
        {"paper": {"portfolio:ALL": {"history": [
            {"date": "2026-08-16",
             "cash_short": [{"key": "us_stock:AMZN", "need": 1, "cash": 0}]}]}}})
    assert [k for k in flags if k.startswith("cash_short")], (
        "감시 기록이 없다는 이유로 다른 경고가 사라진다")


# ── 공개 문구가 실측과 어긋나지 않는가 ──────────────────────────

def test_the_public_page_does_not_state_the_interval_as_a_bare_fact():
    """"15분마다 봅니다"를 단정으로 적으면 그건 설정을 옮겨 적은 것이다.

    지난 기록(날짜 붙은 항목)은 고치지 않는다 — 이 저장소는 과거를 다시
    쓰지 않는다. 대신 **정정 항목이 있는가**를 본다.
    """
    trust = (ROOT / "docs" / "trust.html").read_text("utf-8")
    assert "558" in trust, (
        "실측 간격이 예약과 크게 다르다는 사실이 공개 페이지에 없다 — "
        "'15분마다 봅니다'만 남아 있으면 그건 사실이 아닌 문장이다")
