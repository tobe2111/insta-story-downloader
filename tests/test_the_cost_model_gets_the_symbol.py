"""비용 모델을 부를 때는 **종목을 끝까지 넘긴다** (2026-09-08).

■ 무엇이 있었나

2026-09-03에 한국 ETF의 증권거래세를 빼면서 이렇게 적었다 —

    "체결·밴드·오디션·공개 자료가 **전부 종목을 넘겨받는다.** 표만 고치고
     배선을 안 하면 장부는 그대로 틀린다."

그날 배선을 **반만** 했다. 실측(2026-09-08): `measured_cost_model` 호출
자리 중 종목을 넘기던 곳은 **오디션 하나뿐**이었고, 검증 3종(DSR·PBO·
CPCV)과 그림자 넷(배분 사다리·2세대·무제약·다양성)은 전부 시장만 넘겼다.

`is_etf`는 종목을 모르면 주식으로 본다(비싼 쪽 = 보수적). 그래서 운용
한국 12종목 중 **ETF 6종목이 6.5bp 대신 14.0bp — 2.15배**를 물었다.

⚠️ 방향이 '보수적'이라 아무 빨간불도 안 떴다. **보수적인 것과 옳은 것은
   다르다.**

■ 어떻게 재는가 — 사유를 **검사 가능한 주장**으로 적게 한다

종목이 정말 필요 없는 자리도 있다(시장 단위 요약, ETF 프리셋이 없는 시장).
그런 자리는 사유를 남기되, **말로 쓰지 않고 표에 대고 확인할 수 있게** 쓴다:

    # cost-model: 종목 무관(crypto)     ← `crypto_etf` 프리셋이 없어야 참
    # cost-model: 시장 단위 요약        ← 시장별 표를 만드는 자리에서만

앞의 것은 누가 `us_stock_etf` 프리셋을 새로 만드는 순간 **거짓이 되고, 그날
CI가 먼저 말한다.** 사유를 산문으로 두면 그렇게 못 한다.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.backtest.costs import MARKET_COST_PRESETS  # noqa: E402

FUNC = "measured_cost_model"
MARKET_FREE = "# cost-model: 종목 무관("
SUMMARY = "# cost-model: 시장 단위 요약"
#: 시장 단위 요약이 허용되는 유일한 자리 — 시장별 공개 비용표를 만든다.
SUMMARY_ONLY_IN = "cost_basis_bp"


def _calls():
    """`measured_cost_model` 호출 자리 — 소스에서 센다(손 명단 금지)."""
    for path in sorted((ROOT / "quant").rglob("*.py")):
        src = path.read_text("utf-8")
        if FUNC not in src:
            continue
        lines = src.splitlines()
        tree = ast.parse(src)
        # 어느 함수 안인가 — 사유의 허용 범위를 판정하는 데 쓴다.
        owner = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    owner[id(child)] = node.name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name != FUNC:
                continue
            has_symbol = any(k.arg == "symbol" for k in node.keywords) or len(node.args) >= 4
            # 사유는 호출 줄이나 그 위 다섯 줄 안에 있어야 한다.
            lo = max(0, node.lineno - 6)
            near = "\n".join(lines[lo:node.lineno])
            yield {"file": str(path.relative_to(ROOT)), "line": node.lineno,
                   "func": owner.get(id(node), "<module>"),
                   "symbol": has_symbol, "near": near}


def test_the_counter_actually_finds_the_calls():
    """세는 장치가 0을 세면 아래 검사가 조용히 통과한다 — 그 길을 막는다."""
    calls = list(_calls())
    assert len(calls) >= 12, f"호출 자리를 {len(calls)}개밖에 못 읽었다"


def test_every_cost_lookup_passes_the_symbol_or_says_why():
    """종목을 안 넘기는 자리는 **검사 가능한 사유**를 달아야 한다."""
    bad = []
    for c in _calls():
        if c["symbol"]:
            continue
        if MARKET_FREE in c["near"] or SUMMARY in c["near"]:
            continue
        bad.append(f"{c['file']}:{c['line']} ({c['func']})")
    assert not bad, (
        "비용 모델에 종목을 안 넘기면서 사유도 없는 자리 — 한국 ETF가 "
        f"주식 요율(2.15배)을 문다: {bad}")


def test_the_market_free_reason_is_still_true():
    """'종목 무관'이라고 적은 시장에 ETF 프리셋이 생기면 그 사유는 거짓이다."""
    wrong = []
    for c in _calls():
        if MARKET_FREE not in c["near"]:
            continue
        for chunk in c["near"].split(MARKET_FREE)[1:]:
            market = chunk.split(")")[0].strip()
            if f"{market}_etf" in MARKET_COST_PRESETS:
                wrong.append(f"{c['file']}:{c['line']} — {market}")
    assert not wrong, (
        "'종목 무관'이라고 적어 둔 시장에 ETF 프리셋이 생겼다 — 그 자리는 "
        f"이제 종목을 넘겨야 한다: {wrong}")


def test_the_market_summary_reason_is_only_for_the_summary():
    """'시장 단위 요약' 사유를 아무 데나 쓰면 위 검사가 무력해진다."""
    wrong = [f"{c['file']}:{c['line']} ({c['func']})"
             for c in _calls()
             if SUMMARY in c["near"] and c["func"] != SUMMARY_ONLY_IN]
    assert not wrong, f"시장 단위 요약이 아닌 자리에 그 사유가 붙었다: {wrong}"
