"""CLI를 '실제로 돌려' 본다 — 코드를 읽어서는 안 보이는 결함을 위해.

2026-08-11 감사 68. 오늘 후반부에 나온 결함 몇 개는 소스를 아무리 읽어도
보이지 않았다. 명령을 진짜 장부에 대고 쳐야 보였다.

  · `quant journal`이 개발용 파일(results/state.json)을 기본으로 삼아,
    매일 매매가 도는데도 "거래 없음"만 말했다(감사 67).
  · 경보 문구가 말하는 문턱(30건)과 코드가 쓰는 문턱(10건)이 달랐다(66).

두 경우 모두 함수 단위 테스트는 전부 초록이었다. 함수는 옳았고, **연결된
전체가 엉뚱한 것을 가리켰다.** 그래서 이 파일은 명령을 끝에서 끝까지
돌리고, "돌긴 도는가"가 아니라 **"실제 재료를 보고 있는가"**를 확인한다.

⚠️ 네트워크·실계좌가 필요한 명령(briefing·live-check·social-post)은 여기서
   다루지 않는다. 그 경계를 넘는 순간 검사는 외부 상태에 의존해 불안정해진다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def _ledger(n: int = 8) -> dict:
    """통합 계좌 장부 흉내 — 매매가 있었던 계좌."""
    hist = []
    eq = 80_000.0
    for i in range(n):
        eq *= 1.0 + (0.004 if i % 3 else -0.006)
        hist.append({
            "date": f"2026-08-{i + 1:02d}",
            "price": 100.0 + i, "weight": 0.4 if i % 3 else 0.0,
            "equity": round(eq, 2), "principal": 80_000.0,
            "return_pct": round((eq / 80_000 - 1) * 100, 2),
            "turnover": {"filled": 1, "universe": 20, "ratio": 0.05},
        })
    return {"market": "portfolio", "symbol": "ALL", "start_cash": 80_000.0,
            "cash": 40_000.0, "history": hist, "deposits": [],
            "positions": {}, "last_bar": hist[-1]["date"]}


@pytest.fixture()
def account(tmp_path, monkeypatch):
    """실제 배치가 쓰는 것과 같은 배치의 state 디렉터리를 만든다."""
    paper = tmp_path / "state" / "paper"
    paper.mkdir(parents=True)
    (paper / "portfolio_ALL.json").write_text(
        json.dumps(_ledger(), ensure_ascii=False), encoding="utf-8")
    (paper / "crypto_BTC_USDT.json").write_text(
        json.dumps({**_ledger(), "market": "crypto", "symbol": "BTC/USDT"},
                   ensure_ascii=False), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(argv: list[str]) -> str:
    """CLI를 인자 그대로 실행하고 표준출력을 문자열로 돌려준다."""
    import contextlib
    import io

    from quant.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            main(argv)
        except SystemExit as exc:          # argparse의 정상 종료도 포함
            if exc.code not in (0, None):
                raise
    return buf.getvalue()


# ── ① 복기가 실제 장부를 본다 ─────────────────────────────────


def test_journal_finds_trades_in_the_real_account(account):
    """매매가 있는 장부에서 '거래 없음'이 나오면 안 된다.

    이 한 줄이 감사 67을 잡는다 — 기본 경로가 개발용 파일로 되돌아가면
    거래 수가 0이 되어 실패한다.
    """
    out = _run(["journal"])
    assert "portfolio_ALL.json" in out, f"엉뚱한 파일을 봤다:\n{out}"
    assert "아직 완결된 거래" not in out, (
        "매매가 있는 장부인데 '거래 없음'이라고 말한다 — 빈 파일을 보고 있다")
    assert "거래 수" in out and "기대손익" in out


def test_journal_falls_back_when_there_is_no_account_yet(tmp_path, monkeypatch):
    """통합 계좌 장부가 아직 없으면 예전 경로로 폴백하되 죽지 않는다."""
    monkeypatch.chdir(tmp_path)
    out = _run(["journal"])
    assert "state.json" in out          # 폴백 경로를 밝힌다
    assert "거래 복기" in out            # 크래시 없이 안내를 낸다


# ── ② 주간 보고서가 실제 기록을 요약한다 ─────────────────────


def test_weekly_summarizes_the_real_ledger(account):
    """월요일 아침 워크플로가 읽는 그 출력 — 기록이 있으면 📭가 아니어야."""
    out = _run(["weekly"])
    assert "📭" not in out, f"기록이 있는데 '기록 없음'이라 말한다:\n{out}"
    assert "portfolio:ALL" in out, "통합 계좌가 요약에 빠졌다"
    assert "모의" in out or "페이퍼" in out, "모의투자 고지가 빠졌다"


def test_weekly_says_it_plainly_when_there_is_nothing(tmp_path, monkeypatch):
    """기록이 없으면 📭를 낸다 — 워크플로가 그걸 보고 잡을 실패시킨다.

    조용히 빈 보고서를 보내면 '새벽 배치가 멈춘 주'가 평범한 주로 보인다.
    """
    (tmp_path / "state" / "paper").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    out = _run(["weekly"])
    assert "📭" in out


# ── ③ 워크플로가 부르는 명령이 실제로 존재한다 ────────────────


def test_every_command_the_workflows_call_actually_exists():
    """워크플로가 `python -m quant X`를 부르는데 X가 없으면 새벽에 죽는다.

    명령 이름 오타는 문법 검사로도, 단위 테스트로도 안 잡힌다 — 그 잡이
    실제로 도는 날 처음 드러난다.
    """
    import re

    from quant.cli import build_parser

    known = set()
    for act in build_parser()._subparsers._group_actions:      # type: ignore[attr-defined]
        known |= set(act.choices)
    assert known, "서브커맨드를 하나도 못 찾았다 — 탐지기가 고장났다"

    wf_dir = ROOT / ".github" / "workflows"
    called: set[str] = set()
    for f in wf_dir.glob("*.yml"):
        for m in re.finditer(r"python -m quant ([a-z][a-z-]*)",
                             f.read_text(encoding="utf-8")):
            called.add(m.group(1))
    assert called, "워크플로에서 quant 호출을 하나도 못 찾았다"
    missing = called - known
    assert not missing, f"워크플로가 없는 명령을 부른다: {sorted(missing)}"
