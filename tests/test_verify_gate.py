"""재현성 경보가 **진짜 사건에만** 울리는가 (감사 103).

2026-08-11 밤, 'Nightly Validate'가 이렇게 실패했다:

    재현 불일치:   ✔ crypto:BTC/USDT: 재현 일치 — 같은 데이터·같은 코드에서
    같은 결정 · 주의: 실행 환경이 기록과 다름(기록 pd2.3.3 vs 현재 pd3.0.5)
    — 불일치 시 조작이 아니라 라이브러리 버전 차이일 수 있음
    ##[error]Process completed with exit code 1.

경보문과 판정이 정반대다. 원인은 워크플로 YAML 안의 이 한 줄:

    bad = [ln for ln in lines if "불일치" in ln or "재현 실패" in ln]

**경보가 자기 설명문에 걸렸다.** "불일치 시 조작이 아니라…"라는 안내
문구에 '불일치'가 들어 있어서, 통과(✔)한 줄이 사건으로 분류됐다.
pandas가 3.0으로 올라가 환경 지문이 달라진 순간부터는 매일 울린다.

이건 시끄러움의 문제가 아니다. 이 경보는 **"장부는 조작할 수 없다"**는
주장을 지키는 유일한 장치다. 매일 헛울리면 사장님이 무시하게 되고, 진짜
불일치가 난 날에도 똑같이 무시된다 — 경보를 끄는 가장 확실한 방법은
경보를 계속 울리는 것이다.

고친 방식은 오늘 두 번 쓴 것과 같다(⑤ 로직을 YAML에 두지 않는다):
판단을 스크립트로 빼고, **산문 대신 ✔/✘ 판정**을 읽는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from verify_gate import classify, decide          # noqa: E402

# 실제로 실패를 부른 그 줄(2026-08-11 19:58 UTC 로그 그대로).
REAL_PASS_LINE = (
    "  ✔ crypto:BTC/USDT: 재현 일치 — 같은 데이터·같은 코드에서 같은 결정 · "
    "주의: 실행 환경이 기록과 다름(기록 py3.12.13|np2.5.2|pd2.3.3|sk1.9.0|"
    "lock:3e29b4dc032e vs 현재 py3.12.13|np2.5.2|pd3.0.5|sk1.9.0|"
    "lock:3e29b4dc032e) — 불일치 시 조작이 아니라 라이브러리 버전 차이일 수 있음")

MISMATCH_LINE = ("  ✘ crypto:BTC/USDT: 결정 불일치: 기록 promoted=True "
                 "vs 재실행 False")
TAMPER_LINE = "  ✘ crypto:ETH/USDT: 데이터 해시 불일치 — 스냅샷 변조 의심"
OLD_RECORD_LINE = "  ✘ kr_stock:005930.KS: 스냅샷 없음(해시 기록 이전 날짜)"


def _run(text: str):
    sent, out = [], []
    code = decide(text, notify=sent.append, log=out.append)
    return code, "\n".join(out), sent


# ── 헛울림 ──────────────────────────────────────────────────────

def test_a_passing_line_with_an_environment_note_is_not_an_alarm():
    """이 검사가 없어서 매일 밤 헛울렸다."""
    code, out, sent = _run(f"🔍 재현성 검증\n{REAL_PASS_LINE}\n✅ 모든 결정이 재현\n")
    assert code == 0, (
        "통과(✔)한 줄을 사건으로 읽는다 — 경보문 자기 설명에 들어 있는 "
        f"'불일치'라는 낱말에 걸린 것이다\n{out}")
    assert not sent, f"헛경보를 보냈다: {sent}"


def test_the_environment_drift_is_still_reported():
    """헛울리지 않는 것과 **숨기는 것**은 다르다 — 알리되 실패시키지 않는다."""
    _code, out, _sent = _run(REAL_PASS_LINE)
    assert "실행 환경이 기록과 다름" in out or "환경이 기록과 다릅니다" in out, out


def test_old_records_do_not_trip_the_alarm():
    """'스냅샷 없음'은 옛 기록의 정상적 한계다."""
    code, out, sent = _run(f"{REAL_PASS_LINE}\n{OLD_RECORD_LINE}\n")
    assert code == 0, out
    assert not sent
    assert "대상 외" in out or "빠진 항목" in out, (
        f"검증하지 못한 항목을 조용히 넘긴다 — 몇 건인지 말해야 한다\n{out}")


# ── 진짜 사건 ───────────────────────────────────────────────────

def test_a_real_mismatch_fails_and_notifies():
    code, out, sent = _run(f"{REAL_PASS_LINE}\n{MISMATCH_LINE}\n")
    assert code != 0, f"결정이 달라졌는데 통과시켰다\n{out}"
    assert sent and "재현" in sent[0]


def test_a_tampered_snapshot_fails():
    code, _out, sent = _run(TAMPER_LINE)
    assert code != 0 and sent


def test_no_output_at_all_is_a_failure():
    """돌지 않은 검증을 통과로 읽으면 안 된다."""
    code, out, sent = _run("🔍 재현성 검증: 2026-08-11 · 전체 종목\n")
    assert code != 0, f"결과 줄이 하나도 없는데 통과했다\n{out}"
    assert not sent, "사건이 아니라 '감사가 안 돌았다'이므로 경보 대신 실패다"


def test_an_empty_file_is_a_failure():
    assert _run("")[0] != 0


# ── 분류기 자체 ─────────────────────────────────────────────────

def test_classify_separates_the_three_kinds():
    got = classify([REAL_PASS_LINE, OLD_RECORD_LINE, MISMATCH_LINE, "잡담"])
    assert len(got["passed"]) == 1
    assert len(got["benign"]) == 1
    assert len(got["bad"]) == 1


def test_the_word_mismatch_in_prose_never_decides_anything():
    """산문에 '불일치'가 몇 번 나오든 판정은 ✔/✘만 본다."""
    noisy = "  ✔ x:Y: 재현 일치 — 불일치 불일치 불일치 재현 실패 라는 낱말들"
    assert classify([noisy])["bad"] == []
    assert _run(noisy)[0] == 0


# ── 워크플로가 실제로 이 스크립트를 쓰는가 ─────────────────────

def test_the_workflow_calls_the_script_instead_of_inline_python():
    import yaml
    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "nightly-validate.yml").read_text("utf-8"))
    steps = wf["jobs"]["validate"]["steps"]
    gate = [s for s in steps if "경보" in str(s.get("name", ""))]
    assert gate, "재현 불일치 경보 단계를 찾지 못했다"
    run = str(gate[0].get("run") or "")
    assert "scripts/verify_gate.py" in run, (
        "판단이 아직 YAML 안에 있다 — 검사를 쓸 수 없어 오늘의 결함이 생겼다")
    assert "불일치" not in run.replace("verify_gate.py", ""), (
        "YAML에 아직 산문 매칭이 남아 있다")
