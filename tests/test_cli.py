"""통합 CLI 테스트 (argparse 구조 — pandas 불필요)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "quant_cli", str(Path(__file__).resolve().parent.parent / "quant" / "cli.py"))
cli = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cli
_spec.loader.exec_module(cli)


def test_parser_has_subcommands():
    parser = cli.build_parser()
    ns = parser.parse_args(["backtest", "--strategy", "rsi", "--limit", "100"])
    assert ns.command == "backtest"
    assert ns.strategy == "rsi" and ns.limit == 100
    assert callable(ns.func)


def test_web_defaults():
    ns = cli.build_parser().parse_args(["web"])
    assert ns.command == "web" and ns.host == "127.0.0.1" and ns.port == 8000
    assert ns.open is False


def test_web_open_flag():
    ns = cli.build_parser().parse_args(["web", "--open", "--port", "9000"])
    assert ns.open is True and ns.port == 9000


def test_no_command_prints_help(capsys=None):
    # command 없이 호출하면 도움말을 출력하고 조용히 반환(예외 없음)
    cli.main([])


def test_help_exits():
    try:
        cli.build_parser().parse_args(["--help"])
        assert False, "SystemExit 예상"
    except SystemExit:
        pass


def test_backtest_turnover_flags_parse():
    """회전율 절감 옵션(데드밴드·쿨다운·트로틀)이 파싱된다."""
    ns = cli.build_parser().parse_args(
        ["backtest", "--rebalance-band", "0.03", "--stop-cooldown", "5",
         "--dd-throttle", "--dd-band", "0.01"])
    assert ns.rebalance_band == 0.03 and ns.stop_cooldown == 5
    assert ns.dd_throttle is True and ns.dd_band == 0.01


def test_backtest_turnover_flags_default_off():
    """옵션 미지정 시 전부 0/False — 기존 동작 그대로."""
    ns = cli.build_parser().parse_args(["backtest"])
    assert ns.rebalance_band == 0.0 and ns.stop_cooldown == 0
    assert ns.dd_throttle is False and ns.dd_band == 0.0


def test_validate_subcommand_parses():
    ns = cli.build_parser().parse_args(
        ["validate", "--strategy", "ma_cross", "--limit", "600",
         "--grid", '{"fast":[5],"slow":[40]}'])
    assert ns.command == "validate" and callable(ns.func)
    assert ns.grid == '{"fast":[5],"slow":[40]}'
    assert ns.is_window == 250 and ns.oos_window == 125


def test_validate_default_grids_match_strategy_params():
    """기본 그리드의 파라미터 이름이 실제 전략 생성자와 일치한다."""
    import inspect

    from quant.strategies import get_strategy

    for name, grid in cli._VALIDATE_GRIDS.items():
        params = inspect.signature(type(get_strategy(name)).__init__).parameters
        for key in grid:
            assert key in params, f"{name} 그리드의 '{key}'가 생성자에 없음"


def test_validate_runs_end_to_end(capsys):
    """validate가 3단계(워크포워드+DSR·PBO·CPCV)를 실제로 실행하고 요약을 찍는다."""
    cli.main(["validate", "--limit", "600",
              "--grid", '{"fast":[5,10],"slow":[40,60]}'])
    out = capsys.readouterr().out
    assert "워크포워드" in out and "DSR" in out
    assert "PBO" in out and "CPCV" in out
    assert "보장되지 않습니다" in out
