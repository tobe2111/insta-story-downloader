"""설계한 주기와 실제 주기가 갈라지지 않게 (감사 348).

① 장중 감시: 크론은 "*/5"인데 GitHub가 실제로 띄운 것은 하루 4~6번이었다
   (10/3~10/11 실측, 간격 3~7시간). 잡은 매번 초록이라 빨간불이 없었다.
   이제 회차가 끝나면 약 13분 뒤 다음 회차를 스스로 띄운다(workflow_dispatch).
② 변이 전수: 항목이 1,495건이 되자 한 벌이 3시간 한도를 넘겨 취소됐다(10/10).
   이제 조각 넷을 나란히 돈다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"


def test_the_guard_chains_its_next_round():
    doc = yaml.safe_load((WF / "guard.yml").read_text("utf-8"))
    assert doc["permissions"].get("actions") == "write"
    steps = doc["jobs"]["guard"]["steps"]
    last = steps[-1]
    assert "사슬" in last["name"] and "always()" in last["if"]
    assert "refs/heads/main" in last["if"], "다른 가지가 사슬을 만들면 안 된다"
    assert "/dispatches" in last["run"]
    assert "select(" in last["run"], "이미 줄에 있는 회차를 세지 않으면 사슬이 불어난다"
    # 다음 회차까지 기다리는 시간이 잡 상한 안에 들어야 한다.
    assert "720" in last["run"] and doc["jobs"]["guard"]["timeout-minutes"] >= 13
    assert any("*/" in (c.get("cron") or "") for c in (doc.get("on") or doc.get(True))["schedule"]), (
        "크론 예비가 사라지면 사슬이 끊긴 날 아무도 되살리지 않는다")


def test_the_sweep_runs_in_four_shards():
    doc = yaml.safe_load((WF / "mutation-sweep.yml").read_text("utf-8"))
    job = doc["jobs"]["sweep"]
    assert job["strategy"]["matrix"]["shard"] == [0, 1, 2, 3]
    assert job["strategy"]["fail-fast"] is False
    run = [s for s in job["steps"] if "변이 전수" in (s.get("name") or "")][0]
    assert run["env"]["MUTATION_SHARD"].endswith("/4")


def test_shards_cover_every_item_exactly_once(tmp_path):
    src = (ROOT / "scripts" / "mutation_check.py").read_text("utf-8")
    assert "_idx % _SH_N != _SH_I" in src
    # 조각 번호로 나눈 몫의 합이 전체와 같다(빠지거나 겹치지 않는다).
    n = 1495
    seen = [i for k in range(4) for i in range(n) if i % 4 == k]
    assert sorted(seen) == list(range(n))
