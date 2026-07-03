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


def test_no_command_prints_help(capsys=None):
    # command 없이 호출하면 도움말을 출력하고 조용히 반환(예외 없음)
    cli.main([])


def test_help_exits():
    try:
        cli.build_parser().parse_args(["--help"])
        assert False, "SystemExit 예상"
    except SystemExit:
        pass
