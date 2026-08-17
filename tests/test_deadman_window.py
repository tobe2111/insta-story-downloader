"""dead man's switch가 **하루짜리 누락을 실제로 잡는가** (감사 104).

감시 잡은 "지난 N시간 안에 배치 커밋이 있는가"로 장부 연속성을 본다.
그런데 **감시 시각과 창 길이가 배치 시각과 어긋나면, 어제 커밋이 창 안에
들어와 오늘의 실패를 덮는다.** 실제로 그랬다:

    SNS 커밋   22:45 UTC 실행 → 약 23:19 UTC 커밋
    감시 실행  23:30 UTC 예약 → 실측 23:56~00:01 UTC (크론 지연)
    26시간 창 시작 ≈ 21:56 UTC(전날)  →  어제 SNS 커밋이 **1.3시간 여유로
                                        창 안**

2026-08-11 밤 SNS 게시가 numpy 오류로 죽어 그날 커밋이 아예 없었는데,
감시는 **어제 커밋을 보고 초록**이 될 상황이었다. 감시가 감시를 못 한다 —
오늘 하루 종일 고친 "말과 행동이 다르다" 계열의 가장 나쁜 형태다.

여기서는 산문이 아니라 **시각 산술**로 검사한다. 워크플로에 적힌 크론과 창
길이를 읽어, 각 배치에 대해

    ① 오늘 커밋은 창 **안**   (배치가 늦어져도 견딜 여유가 있는가)
    ② 어제 커밋은 창 **밖**   (하루짜리 누락을 구별할 수 있는가)

를 동시에 만족하는지 본다. 둘 중 하나만 보면 안 된다 — ①만 보면 오늘 결함,
②만 보면 배치가 조금만 늦어도 헛울린다.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WF_DIR = ROOT / ".github" / "workflows"
DEADMAN = WF_DIR / "deadman.yml"

# GitHub 크론은 예약보다 늦게 뜬다. 실측(2026-08-08~11) 26·29·31분.
# 넉넉히 60분까지 밀려도 판정이 뒤집히면 안 된다.
MAX_CRON_DELAY_MIN = 60

# 감시가 존재를 요구하는 배치 — (커밋 제목 조각, 워크플로, 커밋까지 걸린 실측 분)
# 커밋 지연은 '잡 시작 → 커밋 푸시'까지의 실측 최대치다.
BATCHES = [
    ("야간 재학습 기록", "nightly-retrain.yml", 140),
    ("매일 자동 페이퍼 기록", "daily-paper.yml", 170),
    ("SNS 게시 콘텐츠", "social-post.yml", 45),
]


def _crons(path: Path) -> list[tuple[int, int]]:
    wf = yaml.safe_load(path.read_text("utf-8"))
    sched = (wf.get(True) or wf.get("on") or {}).get("schedule") or []
    out = []
    for s in sched:
        m, h = s["cron"].split()[:2]
        out.append((int(h), int(m)))
    return out


def _window_hours() -> int:
    src = DEADMAN.read_text("utf-8")
    m = re.search(r'--since="(\d+) hours ago"', src)
    assert m, "감시 창 길이를 찾지 못했다 — 검사가 낡았다"
    return int(m.group(1))


def _deadman_run_utc(delay_min: int) -> dt.datetime:
    crons = _crons(DEADMAN)
    assert len(crons) == 1, f"감시 크론이 여러 개다: {crons}"
    h, m = crons[0]
    base = dt.datetime(2026, 8, 12, h, m, tzinfo=dt.timezone.utc)
    return base + dt.timedelta(minutes=delay_min)


def _latest_commit_utc(wf: str, extra_min: int, day: dt.date) -> dt.datetime:
    """그 배치가 **가장 늦게** 커밋을 남기는 시각(마지막 크론 + 실측 지연)."""
    h, m = max(_crons(WF_DIR / wf))
    t = dt.datetime.combine(day, dt.time(h, m), tzinfo=dt.timezone.utc)
    return t + dt.timedelta(minutes=extra_min)


def _earliest_commit_utc(wf: str, extra_min: int, day: dt.date) -> dt.datetime:
    h, m = min(_crons(WF_DIR / wf))
    t = dt.datetime.combine(day, dt.time(h, m), tzinfo=dt.timezone.utc)
    return t + dt.timedelta(minutes=extra_min)


# 감시가 도는 날. 배치는 그 '전날 저녁(UTC)'에 돈다 — 감시가 01:30 UTC면
# 같은 UTC 날짜의 새벽이므로, 배치 날짜는 감시 날짜의 **하루 전**이다.
RUN_DAY = dt.date(2026, 8, 12)


def _batch_day(run: dt.datetime) -> dt.date:
    """감시 실행 시각 기준 '방금 끝났어야 할' 배치가 도는 UTC 날짜."""
    # 배치 크론은 전부 19:00~22:45 UTC다. 감시가 그보다 이르면(=다음 날 새벽)
    # 직전 배치는 하루 전이다.
    return run.date() - dt.timedelta(days=1) if run.hour < 19 else run.date()


@pytest.mark.parametrize("delay", [0, 30, MAX_CRON_DELAY_MIN])
@pytest.mark.parametrize("name,wf,lag", BATCHES)
def test_todays_commit_is_inside_the_window(name, wf, lag, delay):
    """① 오늘 커밋은 창 안 — 아니면 정상인 날에도 헛울린다."""
    run = _deadman_run_utc(delay)
    start = run - dt.timedelta(hours=_window_hours())
    newest = _latest_commit_utc(wf, lag, _batch_day(run))
    assert start <= newest <= run, (
        f"{name}: 오늘 커밋 {newest:%m-%d %H:%M}이 창 "
        f"[{start:%m-%d %H:%M} ~ {run:%m-%d %H:%M}] 밖이다 — 헛경보가 난다")


@pytest.mark.parametrize("yday_delay", [0, 30, MAX_CRON_DELAY_MIN])
@pytest.mark.parametrize("delay", [0, 30, MAX_CRON_DELAY_MIN])
@pytest.mark.parametrize("name,wf,lag", BATCHES)
def test_yesterdays_commit_is_outside_the_window(name, wf, lag, delay,
                                                 yday_delay):
    """② 어제 커밋은 창 밖 — 아니면 하루짜리 누락을 못 잡는다.

    이 검사가 없어서 SNS 항목이 **구조적으로** 하루 누락을 못 잡았다:
    어제 커밋 23:19가 26시간 창(시작 21:56) 안에 1.3시간 여유로 들어왔다.

    ⚠️ 그런데 이 검사도 반쪽이었다(2026-08-17 감사 278). **오늘의 감시는
       늦을 수 있다고 보면서 어제의 배치는 늘 정시라고 가정했다.** 늦는 것은
       크론의 성질이지 날짜의 성질이 아니다 — 어제 배치가 밀린 날은 어제
       커밋이 창 안으로 다시 걸어 들어온다. 야간 변이 전수가 창을 26시간으로
       되돌려도 검사가 초록이었던 이유가 이것이다. 두 쪽 모두 밀린다고 본다.
    """
    run = _deadman_run_utc(delay)
    start = run - dt.timedelta(hours=_window_hours())
    yday = _latest_commit_utc(wf, lag + yday_delay,
                              _batch_day(run) - dt.timedelta(days=1))
    assert yday < start, (
        f"{name}: 어제 커밋 {yday:%m-%d %H:%M}(크론 {yday_delay}분 지연)이 "
        f"아직 창 안이다(창 시작 {start:%m-%d %H:%M}, 여유 "
        f"{(yday - start).total_seconds() / 3600:+.2f}시간) — "
        "오늘 그 배치가 죽어도 어제 것으로 통과한다")


def test_the_window_has_real_margin_on_both_sides():
    """여유를 숫자로 못 박는다 — 아슬아슬하면 언젠가 뒤집힌다.

    두 쪽의 **최악**을 각각 본다. 오늘 쪽은 감시가 가장 늦게 뜰 때가 최악이고
    (창이 뒤로 밀려 오늘 커밋을 놓칠 뻔한다), 어제 쪽은 감시가 정시인데 어제
    배치만 밀렸을 때가 최악이다(어제 커밋이 창 안으로 들어온다).
    """
    for name, wf, lag in BATCHES:
        late = _deadman_run_utc(MAX_CRON_DELAY_MIN)
        inside = ((_latest_commit_utc(wf, lag, _batch_day(late))
                   - (late - dt.timedelta(hours=_window_hours())))
                  .total_seconds() / 3600)
        punctual = _deadman_run_utc(0)
        start = punctual - dt.timedelta(hours=_window_hours())
        yday = _latest_commit_utc(wf, lag + MAX_CRON_DELAY_MIN,
                                  _batch_day(punctual) - dt.timedelta(days=1))
        outside = (start - yday).total_seconds() / 3600
        assert inside >= 1.0, f"{name}: 오늘 커밋 여유 {inside:.2f}시간뿐"
        assert outside >= 1.0, (
            f"{name}: 어제 커밋과 창 시작 간격이 {outside:.2f}시간뿐 — "
            "크론이 조금만 더 밀려도 하루 누락을 못 잡는다")


def test_the_deadman_runs_after_every_batch_it_checks():
    """감시가 마지막 배치보다 **뒤에** 있어야 관문이다."""
    run = _deadman_run_utc(0)
    for name, wf, lag in BATCHES:
        done = _latest_commit_utc(wf, lag, _batch_day(run))
        assert done < run, (
            f"{name}이 감시({run:%H:%M})보다 늦게 끝난다({done:%H:%M}) — "
            "아직 안 끝난 일을 '없다'고 말하게 된다")


def test_all_batch_commits_use_the_github_only_skip_marker():
    """`[skip ci]`는 Cloudflare 배포까지 건너뛴다(2026-08-10 실제 사고).

    커밋은 됐는데 사이트가 조용히 낡는다 — 그래서 배치 커밋은
    `[skip actions]`(GitHub만 스킵)를 쓴다. 한 곳만 되돌아가도 그 배치의
    날에는 사이트가 멈춘다.
    """
    bad = []
    for p in sorted(WF_DIR.glob("*.yml")):
        for i, ln in enumerate(p.read_text("utf-8").splitlines(), 1):
            if "git commit" in ln and "[skip ci]" in ln:
                bad.append(f"{p.name}:{i}")
    assert not bad, (
        f"배치 커밋이 [skip ci]를 쓴다 — Cloudflare가 배포를 건너뛴다: {bad}")


def test_every_batch_commit_carries_a_skip_marker_at_all():
    """표식이 아예 없으면 배치 커밋이 CI를 통째로 다시 돌린다."""
    missing = []
    for p in sorted(WF_DIR.glob("*.yml")):
        for i, ln in enumerate(p.read_text("utf-8").splitlines(), 1):
            if "git commit -m" in ln and "skip" not in ln:
                missing.append(f"{p.name}:{i}")
    assert not missing, f"스킵 표식 없는 배치 커밋: {missing}"
