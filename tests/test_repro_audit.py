"""재현성 감사 계약 검사 — 돌지 않는 검증은 장식이다.

배경(2026-08-11 감사): `quant verify`는 처음부터 있었지만 **어떤 워크플로도
실행하지 않았다.** 사이트는 "판단·장부·코드가 공개돼 누구든 검증할 수 있다"고
말하는데, 그 검증은 한 번도 자동으로 돌아본 적이 없었다. 돌지 않는 검증은
깨져도 아무도 모르고, 깨진 줄 모르는 검증은 검증이 아니다.

핵심 계약:
  ① 야간 워크플로가 실제로 verify를 실행한다
  ② 결과가 없으면 '통과'가 아니라 실패로 읽는다(조용한 죽음 금지)
  ③ 표본 감사는 자른 사실을 결과에 남긴다(조용한 축소 금지)
  ④ 표본 선택은 날짜 시드로 결정적이다(같은 날 재실행 → 같은 표본)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.retrain import verify_retrain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WF = (ROOT / ".github" / "workflows" / "nightly-validate.yml").read_text("utf-8")
# 판단 로직은 2026-08-11 감사 103에서 YAML 밖으로 옮겼다 — YAML 안에 있으면
# 검사를 쓸 수 없고, 실제로 그래서 '통과 줄의 설명문'에 걸려 매일 헛울리는
# 결함이 살아 있었다. 여기서는 배선만 보고, **동작**은 test_verify_gate.py가
# 실제로 돌려서 확인한다.
GATE = (ROOT / "scripts" / "verify_gate.py").read_text("utf-8")


# ── ①② 워크플로 배선 ─────────────────────────────────────────


def test_nightly_workflow_actually_runs_verify():
    assert "quant verify" in WF
    assert "--sample" in WF


def test_empty_verify_output_is_treated_as_failure():
    """감사가 조용히 죽으면 '통과'로 읽히면 안 된다."""
    assert "재현 감사 출력 없음" in GATE
    assert "verify_gate.py" in WF          # 워크플로가 그 판단을 실제로 부른다
    assert "timeout-minutes" in WF


def test_mismatch_triggers_an_alert():
    assert "재현성 감사 불일치" in GATE
    assert "get_notifier()" in GATE


# ── ③④ 표본 감사 ─────────────────────────────────────────────


def _ledger(tmp_path, n=10, asof="2026-08-10"):
    lines = [json.dumps({"asof": asof, "market": "synthetic",
                         "symbol": f"S{i}", "promoted": False,
                         "mutation_seed": f"{asof}:s{i}"})
             for i in range(n)]
    (tmp_path / "retrain_history.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def test_sampling_discloses_what_was_skipped(tmp_path):
    _ledger(tmp_path, n=10)
    out = verify_retrain("2026-08-10", state_dir=str(tmp_path), sample=3)
    notes = [r["detail"] for r in out if r["key"] == "-"]
    assert any("표본 감사" in d and "미검사 7종목" in d for d in notes)
    # 3종목만 실제로 검사한다(나머지는 '스냅샷 없음'으로도 나오지 않는다)
    assert len([r for r in out if r["key"] != "-"]) == 3


def test_sampling_is_deterministic_per_date(tmp_path):
    _ledger(tmp_path, n=10)
    a = [r["key"] for r in verify_retrain("2026-08-10",
                                          state_dir=str(tmp_path), sample=3)]
    b = [r["key"] for r in verify_retrain("2026-08-10",
                                          state_dir=str(tmp_path), sample=3)]
    assert a == b                       # 같은 날 재실행 → 같은 표본(멱등)


def test_sampling_rotates_across_dates(tmp_path):
    picks = set()
    for day in ("2026-08-08", "2026-08-09", "2026-08-10"):
        _ledger(tmp_path, n=10, asof=day)
        picks |= {r["key"] for r in verify_retrain(
            day, state_dir=str(tmp_path), sample=3) if r["key"] != "-"}
    # 날짜마다 다른 표본이라 며칠이면 커버리지가 넓어진다
    assert len(picks) > 3


def test_no_sampling_checks_everything(tmp_path):
    _ledger(tmp_path, n=4)
    out = verify_retrain("2026-08-10", state_dir=str(tmp_path))
    assert len(out) == 4
    assert not any(r["key"] == "-" for r in out)


def test_cli_exposes_sample_flag():
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert '"--sample"' in src
    assert "sample=int(getattr(args" in src


# ── ⑤ '만들어 놓고 아무도 부르지 않는 기능' 봉쇄 ───────────────
#
# 2026-08-11 감사에서 같은 병을 세 번 만났다: verify(재현 검증), weekly(주간
# 건강 보고서) — 둘 다 명령도 있고 알림 배선도 끝났는데 **어떤 워크플로도
# 실행하지 않았다.** 사장님이 직접 명령을 치지 않으면 영원히 오지 않는다.
# 자동화가 전제인 명령은 자동화에 연결돼 있어야 한다.

WORKFLOWS = (ROOT / ".github" / "workflows")
_ALL_WF = "\n".join(p.read_text("utf-8") for p in WORKFLOWS.glob("*.yml"))


def _scheduled_workflow_texts() -> list[str]:
    return [p.read_text("utf-8") for p in WORKFLOWS.glob("*.yml")
            if "schedule:" in p.read_text("utf-8")]


def test_automation_commands_are_actually_scheduled():
    """자동화가 전제인 명령은 크론이 있는 워크플로에서 실행돼야 한다."""
    scheduled = "\n".join(_scheduled_workflow_texts())
    for cmd in ("quant verify", "quant weekly", "quant live-daily --all",
                "quant retrain", "quant social-post"):
        head = " ".join(cmd.split()[:2])
        assert head in scheduled, f"크론에 연결되지 않은 명령: {head}"


def test_weekly_report_has_its_own_schedule():
    wf = (WORKFLOWS / "weekly-report.yml").read_text("utf-8")
    assert "schedule:" in wf and "cron:" in wf
    assert "quant weekly" in wf
    # 기록이 없는 주는 '조용한 정상'이 아니라 사건이다
    assert "📭" in wf
