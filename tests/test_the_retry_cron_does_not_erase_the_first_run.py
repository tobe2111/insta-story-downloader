"""예비 크론이 본 크론의 성적을 지운다 (감사 244).

새벽 배치는 하루에 **두 번** 돕니다 — 본 크론, 그리고 놓친 종목을 건지는
예비 크론. 그런데 배치 건강 기록(`run_health.json`)은 그냥 덮어썼습니다.
예비 크론은 이미 기록된 종목을 정상적으로 전부 건너뛰므로, 그 기록은
언제나 **"성공 0 · 건너뜀 20"**입니다.

실측(2026-08-14, 커밋 순서대로 — `git log -- state/run_health.json`):

    paper    ok=20 skip=0    ← 본 크론이 20종목을 다 돌았다
    paper    ok=0  skip=20   ← 예비 크론이 덮어썼다. **이게 화면에 남는다**
    retrain  ok=16 skip=4 → ok=4 skip=16   (2026-08-13, 같은 일)

그래서 **잘 돈 날과 배치가 아예 안 뜬 날이 같은 기록**으로 남습니다.
부분 마비를 잡으려고 만든 장부(감사 226)가 정작 자기 자신을 지우고
있었습니다 — 20종목 중 19개가 실패한 날을 잡으라고 만든 숫자인데, 그
숫자가 매일 0이면 아무것도 잡을 수 없습니다.

고친 방법: 같은 날짜면 **종목 단위로 합칩니다.** 오늘 한 번이라도 성공한
종목은 성공, 끝까지 실패한 종목만 실패, 한 번도 안 돈 종목만 건너뜀입니다.
건너뜀은 여전히 통과가 아닙니다(감사 226) — 다만 **다른 실행이 이미 해낸
일**을 건너뜀으로 되돌리지 않습니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import _write_run_health  # noqa: E402

KEYS = [f"m:{i:02d}" for i in range(20)]


def _health(tmp_path, kind="paper"):
    return json.loads(
        (tmp_path / "run_health.json").read_text("utf-8"))[kind]


# ── 실측 그 장면 ──────────────────────────────────────────────

def test_a_full_run_survives_the_retry_cron(tmp_path):
    """본 크론이 20종목을 다 돌았다 — 예비 크론이 그 사실을 지우면 안 된다."""
    _write_run_health(str(tmp_path), "paper", ok=KEYS, failed={})
    _write_run_health(str(tmp_path), "paper", ok=[], failed={}, skipped=KEYS)
    r = _health(tmp_path)
    assert r["ok"] == 20, f"성공이 지워졌다: {r}"
    assert r["skipped"] == 0, f"이미 해낸 일이 건너뜀으로 되돌아왔다: {r}"


def test_the_record_says_how_many_times_it_ran(tmp_path):
    """두 번 돈 날과 한 번 돈 날은 다른 날이다 — 그것도 기록이다."""
    _write_run_health(str(tmp_path), "paper", ok=KEYS, failed={})
    assert _health(tmp_path)["runs"] == 1
    _write_run_health(str(tmp_path), "paper", ok=[], failed={}, skipped=KEYS)
    assert _health(tmp_path)["runs"] == 2


def test_the_retry_cron_gets_credit_for_what_it_rescued(tmp_path):
    """예비 크론의 존재 이유 — 본 크론이 놓친 것을 건진다."""
    _write_run_health(str(tmp_path), "paper", ok=KEYS[:1],
                      failed={k: "네트워크" for k in KEYS[1:]})
    _write_run_health(str(tmp_path), "paper", ok=KEYS[1:16],
                      failed={k: "여전히 실패" for k in KEYS[16:]},
                      skipped=KEYS[:1])
    r = _health(tmp_path)
    assert (r["ok"], r["failed"], r["skipped"]) == (16, 4, 0), r
    assert r["failed_keys"] == KEYS[16:], r["failed_keys"]


def test_a_failure_that_never_recovered_stays_a_failure(tmp_path):
    """대조군 — 합치기가 실패를 삼키면 경보가 통째로 꺼진다."""
    _write_run_health(str(tmp_path), "paper", ok=[], failed={"m:00": "터짐"})
    _write_run_health(str(tmp_path), "paper", ok=[], failed={}, skipped=["m:01"])
    r = _health(tmp_path)
    assert r["failed"] == 1 and r["failed_keys"] == ["m:00"], r
    assert r["errors"].get("m:00") == "터짐", "오류 문구를 잃었다 — 원인을 못 본다"


def test_a_symbol_that_never_ran_is_still_a_skip(tmp_path):
    """건너뜀은 여전히 통과가 아니다(감사 226)."""
    _write_run_health(str(tmp_path), "paper", ok=["m:00"], failed={},
                      skipped=["m:01"])
    _write_run_health(str(tmp_path), "paper", ok=[], failed={},
                      skipped=["m:00", "m:01"])
    r = _health(tmp_path)
    assert r["ok"] == 1 and r["skipped"] == 1, r
    assert r["skipped_keys"] == ["m:01"], r["skipped_keys"]


# ── 어제 것을 오늘로 끌고 오지 않는가 ─────────────────────────

def test_yesterdays_success_does_not_count_today(tmp_path):
    """날짜가 다르면 새 기록이다 — 안 그러면 성적이 영원히 초록으로 남는다."""
    (tmp_path / "run_health.json").write_text(json.dumps(
        {"paper": {"date": "2020-01-01", "ok": 20, "runs": 3,
                   "ok_keys": KEYS}}), "utf-8")
    _write_run_health(str(tmp_path), "paper", ok=[], failed={}, skipped=KEYS)
    r = _health(tmp_path)
    assert r["ok"] == 0 and r["skipped"] == 20, f"어제 성적을 오늘로 끌고 왔다: {r}"
    assert r["runs"] == 1


def test_the_other_batch_is_untouched(tmp_path):
    """대조군 — 페이퍼 기록이 재학습 기록을 건드리면 안 된다."""
    _write_run_health(str(tmp_path), "retrain", ok=KEYS, failed={})
    _write_run_health(str(tmp_path), "paper", ok=[], failed={}, skipped=KEYS)
    assert _health(tmp_path, "retrain")["ok"] == 20


# ── 옛 기록과의 하위 호환 ─────────────────────────────────────

def test_an_old_entry_without_ok_keys_is_not_a_crash(tmp_path):
    """`ok_keys`가 없던 시절 기록 위에 그대로 써도 죽지 않아야 한다."""
    (tmp_path / "run_health.json").write_text(json.dumps(
        {"paper": {"date": "2020-01-01", "ok": 20, "failed": 0}}), "utf-8")
    import datetime as _dt
    today = _dt.date.today().isoformat()
    (tmp_path / "run_health.json").write_text(json.dumps(
        {"paper": {"date": today, "ok": 20, "failed": 0}}), "utf-8")
    _write_run_health(str(tmp_path), "paper", ok=["m:00"], failed={})
    r = _health(tmp_path)
    # 세어 둔 20은 종목 이름이 없어 되살릴 수 없다 — 지어내지 않는다.
    assert r["ok"] == 1 and r["runs"] == 2, r


def test_a_broken_health_file_does_not_stop_the_batch(tmp_path):
    (tmp_path / "run_health.json").write_text("{망가짐", "utf-8")
    _write_run_health(str(tmp_path), "paper", ok=["m:00"], failed={})
    assert _health(tmp_path)["ok"] == 1
