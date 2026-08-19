"""정지 버튼은 **전부** 멈춰야 한다 (감사 292).

조종석의 '긴급 정지'는 사장님이 직접 누르는 유일한 브레이크다. 나머지
브레이크(킬스위치·서킷브레이커)는 전부 자동이라, 자동이 못 보는 것 —
뉴스로만 알 수 있는 사고, "데이터가 이상한데" 하는 직감 — 앞에서는 이
버튼 하나뿐이다.

그런데 그 버튼은 **페이퍼 쪽 두 명령에만** 걸려 있었다. 실제 돈이 나가는
쪽(국내주식 실거래 집행, 실시간 루프, 외부 신호 웹훅)과 자동 학습 루프는
버튼이 눌린 채로도 그대로 주문을 냈다. 즉 사장님이 "다 멈춤"을 누르고
폰을 덮은 동안, 멈춘 것은 가짜 돈 쪽이고 진짜 돈 쪽은 계속 돌았다.

여기서 지키는 것은 두 가지다.
  ① **목록** — 주문을 낼 수 있는 명령이 하나라도 관문 밖에 있으면 실패.
     새 명령이 생겨도 자동으로 걸린다.
  ② **행동** — 버튼이 켜져 있으면 각 명령이 실제로 아무것도 안 한다.
     그리고 **버튼이 꺼져 있으면 멈추지 않는다**(대조군) — 이게 없으면
     "전부 멈춘다"는 검사는 "전부 고장났다"로도 통과한다.
"""
from __future__ import annotations

import argparse
import ast
import pathlib

import pytest

CLI = pathlib.Path(__file__).resolve().parents[1] / "quant" / "cli.py"

# 주문을 내거나 장부를 움직이는 실행기 — 이 이름이 본문에 있으면
# "이 명령은 매매를 한다"로 본다.
_ORDER_MARKERS = (
    "run_daily_paper", "run_daily_portfolio", "run_daily_live",
    "run_intraday_round", "run_us_round", "AutoLearner",
    "WebhookExecutor", "PaperBroker", "get_broker",
)

# 주문을 내지 않는다고 사람이 확인한 명령만 여기 적는다.
# (live-check은 "주문 없이 키·인증·잔고만 확인"하는 진단이다.)
_REVIEWED_NO_ORDER = {"_cmd_live_check"}


def _command_bodies() -> dict[str, str]:
    src = CLI.read_text("utf-8")
    lines = src.splitlines()
    out = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("_cmd_"):
            out[node.name] = "\n".join(lines[node.lineno - 1:node.end_lineno])
    return out


def _ordering_commands() -> list[str]:
    return sorted(
        name for name, body in _command_bodies().items()
        if name not in _REVIEWED_NO_ORDER
        and any(m in body for m in _ORDER_MARKERS)
    )


def test_the_scan_actually_finds_the_trading_commands():
    """빈 목록은 '전부 통과'가 아니라 '아무것도 안 봤다'이다."""
    found = _ordering_commands()
    assert len(found) >= 6, f"매매 명령을 못 찾았다 — 목록 스캔이 죽었다: {found}"
    for must in ("_cmd_live_daily", "_cmd_paper_daily", "_cmd_intraday_round"):
        assert must in found, f"{must}이(가) 매매 명령으로 안 잡혔다"


@pytest.mark.parametrize("name", _ordering_commands())
def test_every_command_that_can_place_an_order_passes_the_stop_button(name):
    body = _command_bodies()[name]
    assert "_halted(args)" in body, (
        f"{name}은(는) 주문을 낼 수 있는데 수동 킬스위치 관문을 안 지난다.\n"
        "주문/장부를 건드리기 전에 `if _halted(args): return`을 넣거나, "
        "정말 주문을 안 내는 명령이면 _REVIEWED_NO_ORDER에 근거와 함께 적어라."
    )


def _minimal_args(tmp_path):
    """관문 말고는 아무것도 못 하는 인자 — 통과하면 반드시 터진다."""
    return argparse.Namespace(state_dir=str(tmp_path), docs=False)


@pytest.mark.parametrize("name", _ordering_commands())
def test_the_stop_button_actually_stops_each_one(name, tmp_path, capsys,
                                                 monkeypatch):
    monkeypatch.setenv("QUANT_WEBHOOK_SECRET", "x" * 40)
    from quant.cli import __dict__ as cli_ns
    from quant.live import manual_halt

    manual_halt.set_halt(str(tmp_path), True, who="사장님", reason="다 멈춰")
    assert cli_ns[name](_minimal_args(tmp_path)) is None
    out = capsys.readouterr().out
    assert "🛑" in out and "매매를 건너뜁니다" in out, (
        f"{name}: 멈추기는 했는데 왜 멈췄는지 말하지 않는다 — "
        "조용한 공백은 고장과 구별이 안 된다"
    )


@pytest.mark.parametrize("name", _ordering_commands())
def test_when_the_button_is_off_nothing_is_stopped(name, tmp_path,
                                                   monkeypatch):
    """대조군 — 버튼이 꺼져 있으면 각 명령은 제 일을 하러 간다.

    인자가 모자라 곧바로 터지는 것이 정상이다. 그 예외가 곧 "관문을
    지나 실제 작업으로 들어갔다"는 증거다. 여기서 조용히 끝나면 위
    검사는 '멈춘다'가 아니라 '원래 아무것도 안 한다'를 본 것이 된다.
    """
    monkeypatch.setenv("QUANT_WEBHOOK_SECRET", "x" * 40)
    from quant.cli import __dict__ as cli_ns
    from quant.live import manual_halt

    manual_halt.set_halt(str(tmp_path), False, who="사장님", reason="재개")
    with pytest.raises(Exception):
        cli_ns[name](_minimal_args(tmp_path))
