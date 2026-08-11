"""실거래 준비 진단이 실제로 **관문 노릇을 하는가** (감사 87).

`.github/workflows/kr-live.yml` 은 이렇게 배치돼 있다:

    - name: 준비 진단 (키·토큰·잔고 — 주문 없음)     ← 관문
      run: python -m quant live-check --broker ... --real
    - name: 실거래 집행 (기본 모의투자)               ← 실제 주문
      run: python -m quant live-daily --real ...

GitHub Actions는 단계가 실패하면 잡을 멈춘다. 즉 이 배치의 의도는 명백하다 —
**준비가 안 됐으면 매매하지 마라.**

그런데 `_cmd_live_check`는 `ok_all`을 계산해 화면에 찍고 **그냥 버렸다.**
종료코드는 언제나 0이라 관문이 아무도 막지 않는다. 키가 없거나 인증이
만료됐거나 잔고 조회가 실패해도 화면에 ❌만 뜨고 **다음 단계가 실주문을
낸다.**

오늘 반복해서 나온 계열이다: 장치가 있고, 이름도 '진단'이고, 관문 자리에
놓여 있는데, **막지 않는다.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant import cli                      # noqa: E402


class _Args:
    real = False
    broker = "kis"


@pytest.fixture
def run_check(monkeypatch):
    """check_readiness 결과를 갈아끼우고 live-check를 돌린다."""

    def _go(rows, real=False):
        import quant.live.daily_live as dl
        monkeypatch.setattr(dl, "check_readiness", lambda **_k: rows)
        out: list[str] = []
        monkeypatch.setattr("builtins.print",
                            lambda *x, **k: out.append(" ".join(str(i) for i in x)))
        a = _Args()
        a.real = real
        code = 0
        try:
            cli._cmd_live_check(a)
        except SystemExit as exc:
            # 문자열 코드는 파이썬이 stderr로 찍고 1로 끝낸다 — 사용자가
            # 보는 글이므로 화면 출력과 같이 센다.
            if isinstance(exc.code, int):
                code = exc.code
            else:
                code = 1
                out.append(str(exc.code or ""))
        return code, "\n".join(out)

    return _go


ALL_OK = [("키", True, "정상"), ("인증·잔고", True, "정상")]
SOME_BAD = [("키", False, "누락: KIS_APP_KEY"), ("인증·잔고", False, "재시도")]


# ── 본체 ────────────────────────────────────────────────────────

def test_missing_prerequisites_fail_the_command(run_check):
    """미비하면 **0이 아닌 종료코드**여야 한다 — 그래야 워크플로가 멈춘다."""
    code, out = run_check(SOME_BAD)
    assert "미비" in out, "화면에 미비 안내조차 없다"
    assert code != 0, (
        "화면은 '미비 항목이 있습니다'라고 말하면서 종료코드는 0(성공)이다 — "
        "kr-live 워크플로의 다음 단계가 그대로 실주문을 낸다")


def test_ready_state_succeeds(run_check):
    """반대로 준비된 상태까지 막으면 실거래가 아예 못 돈다."""
    code, out = run_check(ALL_OK)
    assert code == 0, out
    assert "준비 완료" in out


def test_one_bad_item_is_enough_to_block(run_check):
    """하나라도 미비하면 막는다 — 부분 통과는 통과가 아니다."""
    code, _ = run_check([("키", True, "정상"), ("인증·잔고", False, "실패")])
    assert code != 0


def test_an_empty_diagnosis_is_not_a_pass(run_check):
    """점검 항목이 하나도 없으면 '전부 통과'가 아니라 '점검 못 함'이다.

    진단기가 조용히 빈 목록을 돌려주면(예: 브로커 이름 오타) 지금 구조에서는
    ok_all이 True로 남아 초록이 된다 — 아무것도 확인하지 않고 통과한다.
    """
    code, out = run_check([])
    assert code != 0, (
        "점검 항목이 0건인데 '준비 완료'로 통과했다 — 아무것도 확인하지 "
        f"않고 실거래를 허용한다 ({out!r})")


def test_the_real_flag_is_reflected_in_the_banner(run_check):
    _code, out = run_check(ALL_OK, real=True)
    assert "실전 도메인" in out
    _code, out = run_check(ALL_OK, real=False)
    assert "모의투자 도메인" in out


# ── 워크플로 배치가 관문 구실을 하는가 ─────────────────────────

def test_the_workflow_runs_the_check_before_trading():
    """진단이 집행보다 **앞에** 있어야 관문이다."""
    import yaml
    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "kr-live.yml").read_text("utf-8"))
    steps = wf["jobs"]["live"]["steps"]
    names = [s.get("name") or s.get("uses") or "" for s in steps]
    runs = [str(s.get("run") or "") for s in steps]

    i_check = next(i for i, r in enumerate(runs) if "live-check" in r)
    i_trade = next(i for i, r in enumerate(runs) if "live-daily" in r)
    assert i_check < i_trade, (
        f"진단({names[i_check]})이 집행({names[i_trade]}) 뒤에 있다 — 관문이 아니다")


def test_the_gate_step_is_not_neutralized():
    """`|| true` 나 continue-on-error 로 관문을 무력화하지 않았는가."""
    import yaml
    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "kr-live.yml").read_text("utf-8"))
    for s in wf["jobs"]["live"]["steps"]:
        run = str(s.get("run") or "")
        if "live-check" in run:
            assert "|| true" not in run and "|| :" not in run, (
                "진단 실패를 삼키고 있다 — 관문이 장식이 된다")
            assert not s.get("continue-on-error"), (
                "continue-on-error 때문에 진단이 실패해도 집행이 진행된다")
