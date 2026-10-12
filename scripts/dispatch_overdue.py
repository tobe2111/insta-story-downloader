"""예약 시각이 지났는데 안 돈 잡을 **대신 띄운다** (2026-10-11 감사 351).

사장님: *"좀 영구적으로 문제없이 하자."*

■ 왜 있는가

GitHub 크론은 정시에 안 돈다. 실측(10/2~10/11, 예약 → 실제 시작):

    일일 기록      22:15 → 00:39~02:24 UTC (2.5~4시간 늦음)
    야간 재학습    21:15 → 23:55~02:34
    SNS 게시       23:45 → 01:59~03:20
    장중 감시      */5   → 하루 4~6번(나머지는 통째로 빠짐)

늦는 것 자체가 사고를 만들었다 — 일일 기록이 늦게 떠서 코인 봉이 늘 막
시작한 상태였고 주말 장부가 사라졌다(감사 350). 잡마다 시각 가정을 따로
고치면 다음 잡이 또 같은 데서 넘어진다. 그래서 **늦음을 한 곳에서 없앤다.**

■ 하는 일

워크플로 파일에서 크론을 **읽어**(손 명단 금지) 가장 최근 예약 시각을 구하고,
그 뒤로 시작된 실행이 하나도 없고 줄에 선 것도 없으면 `workflow_dispatch`로
띄운다. 장중 감시(사슬, 감사 348)가 12분마다 이 스크립트를 부르므로 늦음의
상한이 수 시간에서 **약 15분**이 된다. 일일 기록도 끝에 이 스크립트를 불러
감시 사슬이 죽었으면 되살린다(서로가 서로를 깨운다).

■ 안전

- 대상 잡은 전부 멱등이다 — 늦게 도착한 원래 크론 실행은 멱등 가드가
  건너뛴다(이미 하루 두 번 도는 예비 크론과 같은 처지다).
- 줄에 선 실행이 있으면 부르지 않는다(겹쳐 쌓지 않는다).
- 어떤 실패도 부른 잡을 죽이지 않는다 — 경고만 남기고 0으로 끝난다.
- 제외(`SKIP`)는 이유를 적은 것만: 감시 자신(사슬이 따로 돈다). 변이 전수는
  빼지 않고 유예를 길게 둔다(`GRACE_OVERRIDE_MIN`, 감사 354).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"

#: 대신 띄우지 않는 잡 — 이유가 있는 것만 적는다.
SKIP = {
    "guard.yml": "자기 사슬(감사 348)이 12분마다 다음 회차를 띄운다 — 아래 GUARD_MAX_GAP으로 따로 본다",
}
#: 예약 시각이 지나고 이만큼 기다린 뒤에도 안 떴으면 띄운다.
GRACE_MIN = 10
#: 잡마다 다른 유예(분). 변이 전수는 러너 넷 × 1~3시간이라 시각이 중요하지 않고
#: 겹치면 비싸다 — 처음엔 아예 뺐는데(감사 351), 10/12에 크론이 6시간 넘게 안
#: 떠 그날 전수가 통째로 빠졌다(감사 354). 빼는 대신 **늦게** 띄운다.
GRACE_OVERRIDE_MIN = {"mutation-sweep.yml": 240}
#: 감시 사슬이 이보다 오래 조용하면 되살린다(사슬 주기 12분의 2.5배).
GUARD_MAX_GAP_MIN = 30


def _field(spec: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/")
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-"))
        else:
            a = b = int(part)
        out |= set(range(a, b + 1, step))
    return out


def last_tick(expr: str, now: dt.datetime) -> dt.datetime | None:
    """`now` 이전(포함) 가장 최근 예약 시각(UTC). 8일 안에 없으면 None."""
    m, h, dom, mon, dow = expr.split()[:5]
    M, H = _field(m, 0, 59), _field(h, 0, 23)
    D, MO = _field(dom, 1, 31), _field(mon, 1, 12)
    W = {d % 7 for d in _field(dow, 0, 7)}
    t = now.replace(second=0, microsecond=0)
    for _ in range(8 * 24 * 60):
        cron_dow = (t.weekday() + 1) % 7          # 크론: 일=0
        if (t.minute in M and t.hour in H and t.month in MO
                and (dom == "*" or t.day in D) and (dow == "*" or cron_dow in W)):
            return t
        t -= dt.timedelta(minutes=1)
    return None


def scheduled_workflows() -> dict[str, list[str]]:
    """파일 → 크론 목록. 워크플로 파일에서 직접 읽는다."""
    import yaml
    out: dict[str, list[str]] = {}
    for p in sorted(WF.glob("*.yml")):
        doc = yaml.safe_load(p.read_text("utf-8")) or {}
        on = doc.get("on") or doc.get(True) or {}
        if not isinstance(on, dict):
            continue
        crons = [c["cron"] for c in (on.get("schedule") or []) if "cron" in c]
        if crons:
            out[p.name] = crons
    return out


def _api(method: str, path: str, body: dict | None = None):
    url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}"
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body else None)
    req.add_header("Authorization", f"Bearer {os.environ['GH_TOKEN']}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def _runs(wf: str) -> list[dict]:
    return (_api("GET", f"actions/workflows/{wf}/runs?per_page=20") or {}).get(
        "workflow_runs") or []


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}


def decide(wf: str, crons: list[str], runs: list[dict], now: dt.datetime) -> str | None:
    """띄울 이유(문장) 또는 None. 네트워크 없이 검사할 수 있게 갈라 둔다."""
    if any(r.get("status") in PENDING for r in runs):
        return None
    if wf == "guard.yml":
        last = max((_ts(r["created_at"]) for r in runs), default=None)
        if last is None or now - last > dt.timedelta(minutes=GUARD_MAX_GAP_MIN):
            return f"감시가 {GUARD_MAX_GAP_MIN}분 넘게 조용하다(마지막 {last})"
        return None
    grace = GRACE_OVERRIDE_MIN.get(wf, GRACE_MIN)
    ticks = [t for t in (last_tick(c, now - dt.timedelta(minutes=grace))
                         for c in crons) if t]
    if not ticks:
        return None
    tick = max(ticks)
    if any(_ts(r["created_at"]) >= tick - dt.timedelta(minutes=1) for r in runs):
        return None
    return f"예약 {tick:%m-%d %H:%M} UTC 이후 실행이 없다"


def main(argv: list[str]) -> int:
    if not os.environ.get("GH_TOKEN") or not os.environ.get("GITHUB_REPOSITORY"):
        print("::warning::GH_TOKEN/GITHUB_REPOSITORY 없음 — 밀린 잡을 못 본다")
        return 0
    only_guard = "--guard-only" in argv
    now = dt.datetime.now(dt.timezone.utc)
    targets = {"guard.yml": []} if only_guard else {
        wf: c for wf, c in scheduled_workflows().items() if wf not in SKIP}
    if "--with-guard" in argv:
        targets["guard.yml"] = []
    for wf, crons in targets.items():
        try:
            why = decide(wf, crons, _runs(wf), now)
            if not why:
                continue
            _api("POST", f"actions/workflows/{wf}/dispatches", {"ref": "main"})
            print(f"⏰ {wf} 대신 띄움 — {why}")
        except Exception as e:      # 어떤 실패도 부른 잡을 죽이지 않는다
            print(f"::warning::{wf} 밀림 확인 실패: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
