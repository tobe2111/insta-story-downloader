"""분석 도구가 합성 데이터로 낸 결과를 진짜처럼 보고한다 (감사 250).

시세 수집이 실패하면 **합성(지어낸) 가격**으로 폴백합니다. 그 사실은
`df.attrs["synthetic_fallback"]`에 표식으로 남습니다 — 그런데 그 표식을
읽는 곳이 **설정 마법사 한 군데뿐**이었습니다. 분석 명령 다섯(백테스트·
민감도·검증·손익분기 비용·A/B 비교)은 전부 무시했습니다.

실측(2026-08-15, 네트워크가 막힌 환경에서 그대로 실행):

    $ quant costcheck --market crypto --symbol BTC/USDT
    [WARNING] BTC/USDT: 모든 거래소 실패. 합성 데이터로 폴백.   ← stderr, 스쳐 지나감

    === 손익분기 비용: ma_cross · BTC/USDT (500봉) ===
    수수료 0에서의 총수익률 :     44.22%
    비교적 비용에 견고한 편이다.                                 ← 본문은 진짜와 똑같다

    $ quant backtest --market crypto --symbol BTC/USDT
    총수익률 33.44% · 샤프지수 2.10 · 승률 57.21%

**지어낸 가격 위의 샤프 2.10입니다.** 결과 본문 어디에도 가짜라는 말이
없습니다.

같은 사실을 다른 곳은 크게 말합니다:

    사이트  "합성 데이터 폴백 N종목 — 이 종목의 그날 기록은 실제 시장이
             아닙니다"(가장 숨기면 안 되는 사실)
    매매    합성 폴백이면 아예 주문하지 않는다
             (tests/test_synthetic_fallback_never_trades.py)

**분석 도구만 조용했습니다.** 그리고 이건 사장님이 전략을 고를 때 보는
화면입니다 — 지어낸 데이터로 고른 전략이 실전에 올라갑니다.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.cli import _data_note  # noqa: E402


class _Frame:
    """attrs만 있는 최소 가짜 — 진짜 DataFrame이 필요 없는 검사다."""

    def __init__(self, **attrs):
        self.attrs = dict(attrs)


# ── 무엇 위에서 돌았는지 말하는가 ─────────────────────────────

def test_a_synthetic_fallback_is_shouted():
    """실측 그 장면 — 폴백인데 본문이 조용했다."""
    note = _data_note(_Frame(synthetic_fallback=True), "crypto")
    assert "합성" in note and "실제 시세를 받지 못해" in note, note


def test_it_tells_the_reader_not_to_use_it():
    """'합성입니다'만으로는 부족하다 — 무엇을 하면 안 되는지 말한다."""
    note = _data_note(_Frame(synthetic_fallback=True), "crypto")
    assert "시장에서 일어난 일이 아닙니다" in note
    assert "근거로 쓰지 마세요" in note


def test_a_deliberate_practice_run_says_so_too():
    """백테스트의 기본 시장이 synthetic이다 — 그 경우도 말한다."""
    note = _data_note(_Frame(), "synthetic")
    assert "연습용" in note and "실제 시장이 아닙니다" in note, note


def test_real_data_says_it_is_real():
    """대조군 — 진짜일 때 아무 말도 안 하면 침묵이 무엇을 뜻하는지 모른다."""
    note = _data_note(_Frame(source="yfinance"), "us_stock")
    assert "실제 시세" in note and "yfinance" in note, note
    assert "합성" not in note


def test_real_data_without_a_source_label_still_says_real():
    note = _data_note(_Frame(), "us_stock")
    assert "실제 시세" in note and "·" not in note, note


def test_the_fallback_wins_over_the_market_name():
    """`--market crypto`인데 폴백이면 '연습용'이 아니라 '합성'이다."""
    note = _data_note(_Frame(synthetic_fallback=True), "synthetic")
    assert "합성" in note and "연습용" not in note, note


@pytest.mark.parametrize("bad", [None, 0, "", False])
def test_a_falsy_marker_is_not_a_fallback(bad):
    """표식이 꺼져 있으면 폴백이 아니다 — 없는 경고를 만들지 않는다."""
    assert "합성" not in _data_note(_Frame(synthetic_fallback=bad), "crypto")


def test_a_frame_without_attrs_does_not_crash():
    """해설이 죽어서 분석이 통째로 멈추면 안 된다."""
    assert _data_note(object(), "crypto")


# ── 다섯 명령 **전부**에 배선됐는가 ───────────────────────────

ANALYSIS_COMMANDS = {
    "_cmd_backtest": "백테스트",
    "_cmd_sweep": "민감도 스윕",
    "_cmd_validate": "과최적화 검증",
    "_cmd_costcheck": "손익분기 비용",
    "_cmd_compare": "A/B 비교",
}


def _calls_data_note(func_name: str) -> bool:
    """소스를 파싱해 그 함수가 `_data_note`를 부르는지 본다.

    ⚠️ 문자열로 세지 않는다 — 다른 함수에 한 번만 있어도 통과해 버린다.
    """
    tree = ast.parse((ROOT / "quant" / "cli.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return any(isinstance(c, ast.Call)
                       and getattr(c.func, "id", "") == "_data_note"
                       for c in ast.walk(node))
    raise AssertionError(f"{func_name}를 못 찾았다 — 명령 이름이 바뀌었나")


@pytest.mark.parametrize("func,label", sorted(ANALYSIS_COMMANDS.items()))
def test_every_analysis_command_declares_its_data(func, label):
    """하나라도 빠지면 그 명령만 조용히 가짜를 진짜처럼 보고한다."""
    assert _calls_data_note(func), (
        f"{label}({func})이 어떤 데이터로 돌았는지 말하지 않는다")


def test_the_marker_is_the_one_the_provider_actually_sets():
    """읽는 이름과 쓰는 이름이 다르면 표식은 영영 안 걸린다(감사 229 계열)."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert '"synthetic_fallback"' in src
    hits = [p for p in (ROOT / "quant" / "data").rglob("*.py")
            if "synthetic_fallback" in p.read_text("utf-8")]
    assert hits, "제공자가 그 표식을 안 남긴다 — 이 감사의 전제가 깨졌다"


def test_the_trading_path_still_refuses_synthetic():
    """대조군 — 분석은 '말하고', 매매는 '거부한다'. 둘을 섞지 않는다."""
    assert (ROOT / "tests"
            / "test_synthetic_fallback_never_trades.py").exists(), (
        "매매 쪽 계약이 사라졌다 — 분석 경고만으로는 부족하다")
