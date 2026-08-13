"""배치가 **자기가 매매하는 시장의 마감 뒤에** 도는가 (감사 221).

배치 시각은 UTC 고정(GitHub Actions cron)인데 미국장 마감은 서머타임을 탄다:

    여름(EDT) 16:00 ET = 20:00 UTC  → 05:00 KST
    겨울(EST) 16:00 ET = 21:00 UTC  → 06:00 KST

예전 배치는 20:30 UTC(05:30 KST)였다. 여름에는 마감 30분 뒤라 괜찮지만
**겨울에는 미국장이 아직 열려 있다.** 그러면 오늘 봉이 미완성이라 버려지고
미국 신호만 **한 세션 전** 봉으로 내려간다 — 11월~3월 다섯 달 동안.

한국·코인은 최신인데 미국만 뒤처지니 종목 간 비교도 어긋난다. 고장이
아니라 일정 문제라 검사로 잡을 수밖에 없다.

지키는 계약(연중, 서머타임과 무관):
  · 배치는 **미국장 마감(겨울 21:00 UTC) 뒤**에 돈다
  · 배치는 **한국장 개장(00:00 UTC = 09:00 KST) 전**에 끝난다
  · 재학습 → 배치 → SNS 순서가 유지되고, 각자 타임아웃만큼 여유가 있다
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# 시장 경계 (UTC). 서머타임 때문에 미국 마감은 계절에 따라 20:00~21:00.
US_CLOSE_WINTER_MIN = 21 * 60          # EST 16:00 ET
KR_OPEN_MIN = 0                        # 09:00 KST = 00:00 UTC
DATA_SETTLE_MIN = 10                   # 종가 확정까지 최소 여유


def _crons(name: str) -> list[int]:
    """그 워크플로의 크론들을 'UTC 자정부터의 분'으로."""
    wf = yaml.safe_load((WF / name).read_text("utf-8"))
    sched = (wf.get(True) or wf.get("on") or {}).get("schedule") or []
    out = []
    for s in sched:
        m, h = s["cron"].split()[:2]
        out.append(int(h) * 60 + int(m))
    return sorted(out)


def _timeout(name: str) -> int:
    wf = yaml.safe_load((WF / name).read_text("utf-8"))
    return max(int(j.get("timeout-minutes") or 0) for j in wf["jobs"].values())


# ── 미국장 마감 뒤인가 ────────────────────────────────────────

def test_the_batch_starts_after_the_us_close_even_in_winter():
    """겨울(EST)에도 미국장이 닫힌 **뒤**에 시작해야 한다."""
    first = _crons("daily-paper.yml")[0]
    assert first >= US_CLOSE_WINTER_MIN + DATA_SETTLE_MIN, (
        f"배치가 {first // 60:02d}:{first % 60:02d} UTC에 시작한다 — 겨울에는 "
        f"미국장이 {US_CLOSE_WINTER_MIN // 60:02d}:00 UTC에 닫으므로 그때 "
        "오늘 봉이 미완성이고, 미국 신호만 한 세션 뒤처진다")


def test_the_retrain_also_sees_the_closed_us_bar():
    """재학습이 배치보다 먼저 도는데, 그쪽만 미완성 봉을 보면 조건이 갈린다.

    '오디션과 실전이 같은 조건을 본다'는 이 저장소의 오래된 계약이다.
    """
    first = _crons("nightly-retrain.yml")[0]
    assert first >= US_CLOSE_WINTER_MIN, (
        f"재학습이 {first // 60:02d}:{first % 60:02d} UTC — 겨울 미국장 마감 "
        "전이라 배치와 다른 봉으로 학습한다")


# ── 한국장 개장 전인가 ────────────────────────────────────────

def test_the_batch_finishes_before_the_korean_open():
    """한국 주문은 그날 개장 시가에 체결된다 — 그 전에 결정이 끝나야 한다."""
    last = _crons("daily-paper.yml")[-1]
    done = last + _timeout("daily-paper.yml")
    kr_open = KR_OPEN_MIN + 24 * 60          # 다음 UTC 날짜의 00:00
    assert done <= kr_open, (
        f"마지막 배치가 {done // 60:02d}:{done % 60:02d} UTC에 끝난다 — "
        "한국장 개장(00:00 UTC) 뒤라 그날 시가를 놓친다")


# ── 순서와 여유 ───────────────────────────────────────────────

def test_the_pipeline_keeps_its_order_with_room_to_run():
    """재학습 → 배치 → SNS. 앞 잡의 타임아웃만큼은 비워 둬야 한다."""
    retrain, paper, social = (_crons("nightly-retrain.yml")[0],
                              _crons("daily-paper.yml")[0],
                              _crons("social-post.yml")[0])
    assert retrain < paper < social, (
        f"순서가 어긋났다 — 재학습 {retrain} · 배치 {paper} · SNS {social}")
    assert paper - retrain >= _timeout("nightly-retrain.yml"), (
        "재학습이 끝나기 전에 배치가 시작할 수 있다 — 그날 승격된 챔피언을 "
        "놓친다")
    assert social - _crons("daily-paper.yml")[-1] >= _timeout("daily-paper.yml"), (
        "배치(예비 포함)가 끝나기 전에 SNS가 나갈 수 있다 — 어제 숫자가 "
        "오늘 것으로 방송된다")


def test_no_cron_crosses_midnight_utc():
    """자정을 넘기면 '어느 UTC 날짜의 실행인가'가 갈려 감시 창이 꼬인다.

    데드맨 감시는 크론 시각에서 배치 날짜를 역산한다(같은 날 새벽이면
    직전 배치는 하루 전). 파이프라인이 자정을 넘나들면 그 역산이 무너진다.
    """
    for name in ("nightly-validate.yml", "nightly-retrain.yml",
                 "daily-paper.yml", "social-post.yml"):
        for m in _crons(name):
            assert 19 * 60 <= m < 24 * 60, (
                f"{name}: 크론 {m // 60:02d}:{m % 60:02d} UTC가 저녁 구간을 "
                "벗어난다 — 데드맨 창 계산의 전제가 깨진다")


# ── 셸에 박힌 크론 문자열이 따라오는가 ────────────────────────

def test_the_shell_condition_matches_the_actual_backup_cron():
    """같은 크론 문자열이 schedule 블록과 셸 조건 **두 곳**에 있다.

    한쪽만 고치면 조건이 영영 안 맞아 주간 요약이 두 번 나간다 — 시각을
    옮길 때 실제로 밟은 자리다.
    """
    import re

    text = (WF / "daily-paper.yml").read_text("utf-8")
    wf = yaml.safe_load(text)
    crons = [s["cron"] for s in (wf.get(True) or wf.get("on"))["schedule"]]
    used = re.findall(r'github\.event\.schedule[^=]*=\s*"([^"]+)"', text)
    assert used, "셸 조건에서 크론 문자열을 찾지 못했다 — 검사가 낡았다"
    for u in used:
        assert u in crons, (
            f"셸이 '{u}' 크론을 기다리는데 실제 크론은 {crons}다 — 조건이 "
            "영영 안 맞아 주간 요약이 중복 발송된다")


@pytest.mark.parametrize("name", ["nightly-validate.yml", "nightly-retrain.yml",
                                  "daily-paper.yml", "social-post.yml"])
def test_every_scheduled_job_has_a_timeout(name):
    """타임아웃 없는 잡은 몇 시간을 태우고도 로그를 안 남긴다(감사 77)."""
    assert _timeout(name) > 0, f"{name}: timeout-minutes가 없다"
