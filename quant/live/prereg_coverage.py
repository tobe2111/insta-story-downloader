"""사전 등록 실험의 **판정 재료가 앞에서 잘리지 않는가**를 매일 잰다 (2026-11-10 감사 376).

감사 374·375가 같은 병을 이틀에 두 번 보여 줬다 — 장부는 회차 **개수**로 잘리고 판정
창은 **날짜**로 적혀 있어서, 회차 주기가 바뀌자(감사 348) 판정 재료가 조용히 사흘·
17일 치로 줄었다. 빨간불은 없었다: "표본이 아직 얇다"는 정상 상태처럼 보이기 때문이다.

자리를 하나씩 찾아 고치는 것으로는 다음 자리를 못 막는다. 그래서 **성질**을 잰다:

  · 진행 중인 등록 실험마다, 짝지은 재료의 **첫 날짜**를 센다.
  · 지금까지 본 가장 이른 첫 날짜를 `state/prereg_coverage.json`에 기억한다.
  · 첫 날짜가 기억보다 **뒤로 가면** 재료가 앞에서 잘린 것이다 → `lost`.
    (정상이라면 판정일까지 재료는 쌓이기만 한다 — 앞이 사라질 일이 없다.)
  · 첫 날짜가 등록 시작일보다 `LATE_GRACE_DAYS` 넘게 늦으면 `late_start`로 적는다
    (그 실험의 재료가 늦게 시작했다 — 등록 창 앞부분은 판정에 없다).

⚠️ 이 모듈은 아무것도 고치지 않는다. 판정·매매를 한 칸도 안 바꾸고, **못 보던 사실을
   보이게** 한다(경보 `prereg_material_lost:` · 화면 trust).
⚠️ 기억은 가장 이른 날짜만 지킨다 — 한 번 잘린 것을 다음 날 '정상'으로 삼으면 경보가
   하루만 울리고 끝나는데, 그건 경보 열쇠가 막는다(이름 목록 · 한 번 알림).
"""
from __future__ import annotations

import datetime as dt
import json
import os

FILE = "prereg_coverage.json"
LATE_GRACE_DAYS = 7


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def coverage(state_dir: str = "state", today: str | None = None, *,
             save: bool = True) -> dict:
    from quant.live import sequential as S
    from quant.live.final_judgement import CLOSED_EXPERIMENTS
    from quant.live.final_judgement import FILE as JUDGED
    from quant.live.prereg import PREREGISTERED

    today = today or dt.date.today().isoformat()
    path = os.path.join(state_dir, FILE)
    mem = _load(path).get("first_ever") or {}
    judged = _load(os.path.join(state_dir, JUDGED))
    out: dict = {"pairs": {}, "lost": [], "late_start": [], "unread": [],
                 "rule": {"late_grace_days": LATE_GRACE_DAYS}}
    for key, exp in PREREGISTERED.items():
        if key in CLOSED_EXPERIMENTS or key in judged or today > str(exp.get("judge_on")):
            continue
        cover: dict = {}
        try:
            if key == "trend_core_live":
                # 짝이 아니라 본 계좌 한 줄기 — 같은 셈(첫 날짜)을 그 장부에 건다.
                rows = [r for r in (S._load(os.path.join(state_dir, "paper", "portfolio_ALL.json"))
                                    .get("history") or [])
                        if str(r.get("date"))[:10] >= str(exp.get("start"))[:10]
                        and r.get("equity") is not None]
                days = sorted(S._days(rows))
                cover["trend_core_live:main"] = {"first": days[0] if days else None,
                                                 "last": days[-1] if days else None,
                                                 "n": len(days)}
            else:
                S._pairs_for(key, state_dir, cover=cover)
        except Exception:  # noqa: BLE001 — 못 읽은 것은 못 읽었다고 적는다
            out["unread"].append(key)
            continue
        start = str(exp.get("start") or "")[:10]
        for name, c in cover.items():
            first, prev = c.get("first"), mem.get(name)
            lost = bool(first and prev and first > prev)
            if first:
                mem[name] = min(prev, first) if prev else first
            ever = mem.get(name)
            late = False
            if ever and start:
                try:
                    late = (dt.date.fromisoformat(ever)
                            - dt.date.fromisoformat(start)).days > LATE_GRACE_DAYS
                except ValueError:
                    late = False
            out["pairs"][name] = {"experiment": key, "start": start, "first": first,
                                  "first_ever": ever, "last": c.get("last"),
                                  "n": c.get("n"), "lost": lost, "late_start": late}
            if lost:
                out["lost"].append(name)
            if late:
                out["late_start"].append(name)
    if save:
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"first_ever": dict(sorted(mem.items())), "updated": today},
                      f, ensure_ascii=False, indent=1)
    return out
