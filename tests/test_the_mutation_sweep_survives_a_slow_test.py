"""변이 시험이 느린 검사 하나에 통째로 죽지 않는다 (2026-10-11 감사 349).

조각 넷 중 셋이 느린 검사 파일의 기준선에서 `subprocess.TimeoutExpired`로
요약 없이 죽었다 — 그 조각의 수백 건이 결과 없이 사라졌다. 시간 초과는
예외가 아니라 종료코드로 센다.

⚠️ 이 스크립트는 import하면 변이 시험이 돈다 — 소스를 읽어 본다.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "mutation_check.py"


def _func(name):
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(name)


def test_every_subprocess_with_a_timeout_catches_it():
    fn = _func("_run_verbose")
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
             and ast.unparse(c.func) == "subprocess.run"
             and any(k.arg == "timeout" for k in c.keywords)]
    assert calls, "시간 한도 없는 실행은 러너 한도까지 매달린다"
    handlers = [h for t in ast.walk(fn) if isinstance(t, ast.Try)
                for h in t.handlers if h.type is not None
                and "TimeoutExpired" in ast.unparse(h.type)]
    assert handlers, "TimeoutExpired를 잡지 않으면 조각 전체가 요약 없이 죽는다"
    for c in calls:
        assert any(c in list(ast.walk(t)) for t in ast.walk(fn)
                   if isinstance(t, ast.Try) and t.handlers
                   and any("TimeoutExpired" in ast.unparse(h.type or ast.Name("x"))
                           for h in t.handlers)), "시간 초과를 잡는 try 밖의 실행이 있다"


def test_a_baseline_timeout_is_named_not_merged_into_failure():
    src = SRC.read_text(encoding="utf-8")
    assert "RC_TIMEOUT" in src and "원본 코드에서 시간 초과" in src
