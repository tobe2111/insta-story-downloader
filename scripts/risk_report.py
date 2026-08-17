#!/usr/bin/env python3
"""위험 리포트 — 위기 재생 + 스트레스 시나리오를 돌려 docs/risk.json에 쓴다.

산출물이 **실측 장부(status.json)와 다른 파일**에 사는 것이 설계다:
여기 있는 숫자는 전부 시뮬레이션이고, 실전 성적처럼 읽히면 안 된다.
파일 안의 kind="simulation"이 그 표식이며, 읽는 쪽(사이트)은 이 표식과
함께 표시할 의무가 있다.

야간 검증 배치가 매일 돌린다 — 스트레스는 '지금 노출' 기준이라 하루만
지나도 낡는다. 실패해도 배치를 막지 않는다(위험 분석이 없는 날은 있어도,
그것 때문에 검증 전체가 멈추는 날은 없어야 한다).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def build(state_dir: str = "state") -> dict:
    from quant.risk.replay import load_snapshot_closes, replay_risk_layer
    from quant.risk.stress import stress_from_state

    replay = replay_risk_layer(
        load_snapshot_closes(str(ROOT / state_dir / "snapshots")))
    stress = stress_from_state(str(ROOT / state_dir))
    return {
        "kind": "simulation",
        "generated": dt.date.today().isoformat(),
        "replay": replay,
        "stress": stress,
    }


def main() -> int:
    report = build()
    out = ROOT / "docs" / "risk.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    rep, st = report.get("replay"), report.get("stress")
    if rep:
        print(f"✅ 위기 재생 {rep['period']['from']}~{rep['period']['to']} "
              f"({rep['n_symbols']}종목): MDD 무브레이크 {rep['raw']['mdd']:.0%}"
              f" → 브레이크 {rep['braked']['mdd']:.0%} · "
              f"킬스위치 발동 {len(rep['kill_switch_episodes'])}회")
    else:
        print("⚠️ 위기 재생 불가 — 스냅샷 부족")
    if st:
        print(f"✅ 스트레스 {len(st['scenarios'])}개 시나리오: 최악 "
              f"{st['worst']['scenario']} {st['worst']['drawdown_pct']}%")
    else:
        print("⚠️ 스트레스 불가 — 통합 계좌 장부 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
