"""개선 이력을 홈페이지에 자동 발행한다 (2026-08-23, 사장님 지시).

⚠️ 왜 만들었나. "매일 스스로를 고치는 시스템"이 이 제품의 정체성인데, 그
   증거(개선 이력)는 내부 문서에만 쌓이고 **공개 홈페이지에는 없었다.**
   읽는 사람 입장에서는 "고친다더라"는 주장만 있고 기록이 없는 셈이다.

   따로 일지를 쓰게 하면 언젠가 빠뜨린다 — 사람이 두 번 적는 기록은 반드시
   갈라진다(이 저장소가 반복해 잡아 온 병). 그래서 **이미 존재하는 단일
   진실**에서 뽑는다: 깃 커밋 이력. 개선이 머지되는 순간 기록은 이미 거기
   있고, 밤 배치가 그것을 사이트용 파일로 옮겨 적을 뿐이다.

정직 규칙:
  · 자동 배치가 남긴 커밋(장부 기록·감시 심장박동 — 전부 [skip 표식)은
    뺀다. 그건 개선이 아니라 운행 기록이다.
  · **얕은 복제(shallow clone)에서는 쓰지 않는다.** 이력의 일부만 보이는
    체크아웃에서 파일을 만들면 "이게 전부"로 읽힌다 — 부분 기록이 완전
    기록으로 둔갑하는 것이 이 저장소가 가장 경계하는 거짓말이다. 그날은
    기존 파일을 그대로 두고 경고만 남긴다.
  · 지난 항목을 고쳐 쓰지 않는다 — 커밋 이력이 원본이고 이 파일은 사본이다.
"""
from __future__ import annotations

import json
import os
import subprocess

from quant.utils.logging import get_logger

log = get_logger("reporting.changelog")

KEEP = 200                 # 사이트에 실을 최대 항목 수(전체 이력은 깃에 있다)
_BOT_MARK = "[skip"        # [skip actions]·[skip ci] — 자동 배치의 운행 기록


def _git(args: list[str]) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True,
                             timeout=30)
        if out.returncode != 0:
            return None
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def collect_entries(limit: int = KEEP) -> list[dict] | None:
    """깃 이력에서 사람의 개선 커밋만 뽑는다. 못 뽑으면 None(지어내지 않는다).

    얕은 복제면 None — 일부만 보이는 이력으로 파일을 만들면 그게 전부로
    읽힌다.
    """
    shallow = _git(["rev-parse", "--is-shallow-repository"])
    if shallow is None:
        return None
    if shallow.strip() == "true":
        log.warning("얕은 복제 — 개선 이력의 일부만 보여서 발행하지 않는다"
                    "(기존 파일 유지). 워크플로 checkout에 fetch-depth: 0")
        return None
    raw = _git(["log", "--no-merges", "--format=%ad|%s",
                "--date=format:%Y-%m-%d", f"-{limit * 3}"])
    if raw is None:
        return None
    entries = []
    for line in raw.splitlines():
        date, _, title = line.partition("|")
        if not title or _BOT_MARK in title:
            continue                    # 운행 기록은 개선이 아니다
        entries.append({"date": date, "title": title.strip()})
        if len(entries) >= limit:
            break
    return entries


def write_changelog(docs_dir: str = "docs") -> dict | None:
    """docs/changelog.json 발행. 못 뽑은 날은 기존 파일을 건드리지 않는다."""
    entries = collect_entries()
    if entries is None:
        return None
    if not entries:
        # 사람 커밋이 하나도 안 보이는 이력은 뽑기 실패와 같다 — 빈 파일로
        # 기존 기록을 덮으면 "개선이 없었다"로 읽힌다.
        log.warning("개선 커밋이 하나도 안 보인다 — 발행하지 않는다")
        return None
    from quant.utils.jsonio import atomic_write_json

    payload = {
        "note": "이 목록은 깃 커밋 이력에서 자동으로 뽑습니다 — 사람이 따로 "
                "적는 일지가 아니라, 개선이 저장소에 합쳐지는 순간 남는 "
                "기록의 사본입니다. 자동 배치의 운행 기록(장부 커밋)은 "
                "제외합니다.",
        "asof": entries[0]["date"],
        "count": len(entries),
        "entries": entries,
    }
    atomic_write_json(os.path.join(docs_dir, "changelog.json"), payload)
    return payload
