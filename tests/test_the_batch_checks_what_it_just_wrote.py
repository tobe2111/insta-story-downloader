"""배치가 **자기가 방금 쓴 기록**을 검사하는가 (감사 265).

2026-08-15 새벽 배치가 100만원 계좌의 자산을 7,249만원(+7,150%)으로 적었다.
그 값이 틀렸다는 것은 **이미 저장소 안의 검사가 알고 있었다** —
`test_no_implausible_equity_jumps`가 하루 ±50% 초과 변동을 잡는다.
그런데 그 검사는 그 기록을 **한 번도 못 봤다.**

배치 커밋은 전부 `[skip actions]`를 단다. 이유는 정당하다(장중 감시는
15분마다 도니 하루 96번 전체 검사를 돌릴 수 없고, `[skip ci]`는
Cloudflare 배포까지 멈춘다 — 2026-08-10 사고). 하지만 그 결과
**배치가 만든 기록에는 아무 검사도 걸리지 않는 구멍**이 생겼고, 그
구멍으로 7,150%가 반나절을 살아남았다. 다음 PR이 열릴 때까지 아무도
몰랐고, 알게 된 것도 우연이었다.

이 저장소가 반복해서 잡아 온 계열 그대로다 — **장치는 있는데 그 장치가
보는 자리에 물건이 없었다.**

여기서 지키는 것:
  ① 장부를 쓰는 배치는 커밋 **전에** 장부 검사를 돌린다.
  ② 실패하면 **커밋하지 않는다**(오염된 기록 = 내일의 출발 상태).
  ③ 관문은 검사 규칙을 **자기가 다시 적지 않는다**(FROZEN_IDEAS ①).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WF = ROOT / ".github" / "workflows"

# 계좌 상태(state/paper·현금·포지션)를 쓰는 배치들. 이들이 남긴 기록은
# 다음 날의 출발점이 되므로, 틀린 채로 커밋되면 오염이 이어진다.
LEDGER_BATCHES = ("daily-paper.yml", "nightly-retrain.yml",
                  "deposit.yml", "kr-live.yml")


def _text(name: str) -> str:
    p = WF / name
    assert p.exists(), f"{name}이 없다 — 검사가 낡았다"
    return p.read_text("utf-8")


@pytest.mark.parametrize("name", LEDGER_BATCHES)
def test_a_ledger_batch_runs_the_gate_before_committing(name):
    """관문이 커밋 **앞에** 있어야 한다 — 뒤에 있으면 이미 늦었다."""
    src = _text(name)
    assert "scripts/ledger_gate.py" in src, (
        f"{name}: 방금 쓴 기록을 아무도 안 보고 커밋한다 — "
        "2026-08-15의 +7,150%가 이 구멍으로 나갔다")
    gate = src.index("scripts/ledger_gate.py")
    commit = src.index('git commit -m "', gate - 4000 if gate > 4000 else 0)
    # 관문 뒤에 오는 첫 커밋이 그 배치의 기록 커밋이어야 한다.
    assert src.index("scripts/ledger_gate.py") < src.index(
        'git commit -m "', gate), (
        f"{name}: 관문이 커밋보다 뒤에 있다 — 오염된 기록이 이미 나갔다")
    assert commit is not None


@pytest.mark.parametrize("name", LEDGER_BATCHES)
def test_a_failing_gate_stops_the_commit(name):
    """관문이 실패해도 커밋이 나가면 관문이 아니다.

    워크플로 스텝은 기본적으로 실패하면 뒤를 멈춘다. 그래서 지킬 것은
    **관문에 실패를 삼키는 장식이 붙지 않았는가**다 — `|| true`,
    `continue-on-error`가 붙는 순간 이 장치는 선언만 남는다.
    """
    src = _text(name)
    line = next(ln for ln in src.splitlines()
                if "scripts/ledger_gate.py" in ln)
    assert "||" not in line, f"{name}: 관문 실패를 삼킨다 — {line.strip()!r}"
    # 관문이 들어 있는 스텝에 continue-on-error가 붙었는지 본다.
    step = src[:src.index("scripts/ledger_gate.py")].rsplit("- name:", 1)[-1]
    assert "continue-on-error" not in step, (
        f"{name}: 관문 스텝에 continue-on-error가 붙어 실패가 무시된다")


def test_the_gate_does_not_restate_the_rules_itself():
    """관문은 **목록**만 갖는다 — 무엇이 말이 되는 장부인지는 tests/가 정한다."""
    src = (ROOT / "scripts" / "ledger_gate.py").read_text("utf-8")
    for banned in ("0.5", "equity /", "drawdown"):
        assert banned not in src.split('"""', 2)[-1], (
            f"관문이 판정 기준({banned!r})을 자기가 적고 있다 — 두 곳에 적으면 "
            "언젠가 갈라진다")


def test_the_gate_actually_fails_on_a_broken_ledger(tmp_path):
    """관문이 **진짜로 빨간불을 주는가** — 초록만 확인하면 아무것도 모른다."""
    from scripts import ledger_gate  # noqa: PLC0415
    assert ledger_gate.run() == 0, "지금 장부에서 관문이 실패한다"

    # 존재하지 않는 검사를 목록에 넣으면 관문은 통과가 아니라 실패여야 한다 —
    # 검사 파일이 사라졌는데 초록이 나오는 것이 가장 나쁜 상태다.
    #
    # ⚠️ `!= 0`으로 보면 안 된다(변이 시험이 잡아냈다). 없는 파일을 그대로
    #    pytest에 넘겨도 pytest가 사용법 오류로 0이 아닌 값을 준다 — 즉
    #    **관문이 아무것도 안 해도 이 검사는 통과한다.** 관문이 스스로
    #    알아챘다는 것을 보려면 그 전용 신호(2)를 봐야 한다.
    orig = ledger_gate.LEDGER_CHECKS
    try:
        ledger_gate.LEDGER_CHECKS = ("tests/test_this_does_not_exist.py",)
        assert ledger_gate.run() == 2, (
            "검사 파일이 사라진 것을 관문이 스스로 못 알아챈다 — "
            "pytest에 떠넘기면 '실패 이유'가 사라진다")
    finally:
        ledger_gate.LEDGER_CHECKS = orig


def test_the_gate_says_whether_the_ledger_is_wrong_or_the_checker_broke(
        monkeypatch):
    """둘 다 커밋을 막지만, **사람에게는 다른 사건**이다.

    새벽 5시 30분에 배치가 멈췄을 때 찾아야 할 것이 장부인지 도구인지
    관문이 말해 주지 않으면, 없는 버그를 몇 시간 찾게 된다.
    """
    import subprocess as _sp

    from scripts import ledger_gate  # noqa: PLC0415

    def _fake(rc):
        def _run(*a, **k):
            return _sp.CompletedProcess(a[0] if a else [], rc, "", "")
        return _run

    seen = {}
    for rc, expect in ((1, "장부가 말이 안 된다"), (4, "미실행"), (5, "미실행")):
        monkeypatch.setattr(ledger_gate.subprocess, "run", _fake(rc))
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = ledger_gate.run()
        seen[rc] = buf.getvalue()
        assert out == 1, f"종료코드 {rc}인데 관문이 커밋을 허용한다"
        assert expect in seen[rc], (
            f"종료코드 {rc}의 설명이 '{expect}'를 말하지 않는다:\n{seen[rc]}")
    assert seen[1] != seen[4], (
        "장부 오류와 도구 고장이 **같은 문구**로 나간다 — 사람이 엉뚱한 곳을 "
        "뒤지게 된다")


def test_a_checker_that_collected_nothing_is_not_a_pass():
    """검사가 0개 수집돼도 통과가 되면, 이름만 바뀌어도 관문이 사라진다.

    pytest는 수집 0건에 5를 준다 — 0이 아니므로 막히지만, 그건 우연이
    아니라 의도여야 한다. 그래서 5가 '못 돌았다' 쪽에 명시적으로 있는지 본다.
    """
    from scripts import ledger_gate  # noqa: PLC0415
    assert 5 in ledger_gate._PYTEST_CANT_RUN, (
        "검사가 하나도 수집되지 않은 상태가 '못 돌았다'로 분류돼 있지 않다")
    assert 0 not in ledger_gate._PYTEST_CANT_RUN


def test_the_gate_is_cheap_enough_that_cost_is_not_an_excuse():
    """비싸면 언젠가 꺼진다 — 실제로 얼마나 걸리는지 잰다."""
    import time
    t0 = time.monotonic()
    rc = subprocess.run([sys.executable, "scripts/ledger_gate.py"],
                        cwd=ROOT, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    assert rc.returncode == 0, rc.stdout[-2000:]
    assert elapsed < 60, (
        f"장부 관문이 {elapsed:.0f}초 걸린다 — 이 정도면 '배치가 느려진다'는 "
        "이유로 언젠가 꺼진다. 검사 범위를 좁혀야 한다")


# ── 나오면 안 되는 값이 사람에게 닿는가 ─────────────────────────

def _flags(record: dict) -> dict:
    from quant.live.flag_watch import _current_flags
    return _current_flags({"paper": {"portfolio:ALL": {"history": [record]}}})


def test_a_cash_short_reaches_a_human_not_just_a_web_page():
    """cash_short는 2026-08-15 사고의 **가장 이른 신호**였다.

    새벽 5시 30분에 장부에 남았고, 반나절 뒤 사람이 우연히 볼 때까지
    조용했다. 화면에 띄우는 것으로는 부족하다 — 화면은 열어야 보인다.
    """
    flags = _flags({"date": "2026-08-15", "cash_short": [
        {"key": "us_stock:AMZN", "need": 6365504.94, "cash": 677061.47}]})
    hit = [v for k, v in flags.items() if k.startswith("cash_short")]
    assert hit, f"현금 부족 거부가 알림으로 안 나간다: {sorted(flags)}"
    assert "AMZN" in hit[0], "어느 종목이 거부됐는지 안 알려준다"


def test_a_refused_fill_reaches_a_human():
    flags = _flags({"date": "2026-08-16", "fill_refused": {
        "us_stock:META": {"open": 596.98, "mark": 832868.17,
                          "why": "통화 환산 누락 의심"}}})
    hit = [v for k, v in flags.items() if k.startswith("fill_refused")]
    assert hit, f"거부된 체결이 알림으로 안 나간다: {sorted(flags)}"
    assert "META" in hit[0]


def test_a_clean_day_stays_quiet():
    """매일 울리는 경보는 꺼진 경보와 같다."""
    flags = _flags({"date": "2026-08-16", "cash_short": None,
                    "fill_refused": None, "equity": 1_000_000.0})
    noisy = [k for k in flags
             if k.startswith(("cash_short", "fill_refused"))]
    assert not noisy, f"아무 일도 없는 날에 경보가 울린다: {noisy}"
