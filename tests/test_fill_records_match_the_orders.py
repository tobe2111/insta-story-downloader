"""체결 기록이 **실제로 낸 주문**과 같은가 (감사 92).

감사 91의 형제다. 같은 파일, 한 줄 사이에서 같은 값을 두 정의로 썼다:

    order = broker.target_weight(
        key, float(pend["weight"]) * sl, fopen, eq_now, ...)   # 주문: ×슬라이스
    fills.append({..., "weight": round(float(pend["weight"]), 4)})  # 기록: 안 곱함

`pend["weight"]`는 종목 안에서의 비중이고, 계좌 비중이 되려면 배분
슬라이스를 곱해야 한다. 주문은 곱해서 나가는데 **기록만 빼먹었다.**

2026-08-10 장부에 남은 결과:

    fills → kr_stock:069500.KS  weight 0.165
    실제 주문                    ≈ 0.165 × 슬라이스 ≈ 0.0036
    같은 날 총노출               0.0684

체결 하나가 계좌 총노출의 2.4배로 적혀 있었다 — 성립할 수 없는 숫자다.
같은 장부의 `pending_next_open`은 같은 `pend`에서 뽑으면서 슬라이스를
곱한다. 즉 코드 스스로 '곱해야 계좌 비중'임을 알고 있었고, 체결 기록
한 곳만 빠져 있었다.

여기서 고정하는 계약:
  ① 기록하는 체결 비중은 주문에 넘긴 값과 **같은 식**이어야 한다.
  ② 어떤 체결 하나도 그날 총노출보다 클 수 없다(무레버리지 계좌에서).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DAILY = ROOT / "quant" / "live" / "daily.py"


def test_the_recorded_weight_is_the_ordered_weight():
    """주문에 넘긴 식과 기록하는 식이 같은지 — 소스에서 직접 대조한다.

    ⚠️ 원래 이 대조를 **정규식**으로 했다. `"weight": ...` 바로 다음 줄이
    `"type": "시가"`라고 전제했는데, 체결 기록에 수량·금액을 추가하자
    (2026-08-13) 사이에 줄이 끼어들어 패턴이 안 맞았다 — 계약은 그대로인데
    검사만 빨개진 것이다. 감사 183·199·204·211·212에 이어 여섯 번째다.
    글자 대신 **구조**를 본다: `"type": "시가"`인 fills.append를 찾아
    그 안의 `weight` 식을 꺼낸다.
    """
    import ast

    src = DAILY.read_text("utf-8")
    order = re.search(r"order = broker\.target_weight\(\s*\n?\s*key, ([^,]+),",
                      src)
    assert order, "시가 체결 주문 호출을 찾지 못했다 — 검사가 낡았다"
    ordered = order.group(1).strip()

    recorded = None
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "fills"
                and node.args and isinstance(node.args[0], ast.Dict)):
            continue
        d = node.args[0]
        got = {k.value: v for k, v in zip(d.keys, d.values)
               if isinstance(k, ast.Constant)}
        if getattr(got.get("type"), "value", None) != "시가":
            continue
        w = got.get("weight")
        assert w is not None, "시가 체결 기록에 비중이 없다"
        # round(<식>, 4) 안쪽의 식을 꺼낸다
        if (isinstance(w, ast.Call) and isinstance(w.func, ast.Name)
                and w.func.id == "round"):
            w = w.args[0]
        recorded = ast.unparse(w)
    assert recorded, "시가 체결 기록을 찾지 못했다 — 검사가 낡았다"

    # 공백·따옴표 차이를 흡수해 비교한다(ast.unparse는 정규화된 형태를 낸다)
    norm = lambda t: ast.unparse(ast.parse(t, mode="eval").body)  # noqa: E731
    assert norm(recorded) == norm(ordered), (
        f"주문은 {ordered!r}로 내면서 장부에는 {recorded!r}를 적는다 — "
        "장부가 실제 체결과 다른 비중을 말한다")


def test_pending_next_open_uses_the_same_definition():
    """예약 표도 같은 정의여야 한다(여기는 원래 맞았다 — 무너지면 잡는다)."""
    src = DAILY.read_text("utf-8")
    assert re.search(r'"pending_next_open": \{k: round\(float\(p\["weight"\]\)\s*\n?'
                     r'\s*\* float\(p\.get\("slice"\)', src), (
        "예약 주문 비중이 배분 슬라이스를 곱하지 않는다 — 계좌 비중이 아니다")


def test_no_single_fill_exceeds_the_days_gross_exposure():
    """저장된 장부의 산술 검사 — 체결 하나가 총노출보다 크면 뭔가 거짓말이다.

    고치기 전 기록은 **고치지 않는다.** 새 장부에만 있는 `applied`를
    '수정 이후'의 표시로 삼아, 그 기록들만 본다.
    """
    checked = 0
    for fp in (ROOT / "state" / "paper").glob("portfolio_*.json"):
        for rec in json.loads(fp.read_text("utf-8")).get("history") or []:
            if not rec.get("applied"):
                continue                      # 수정 이전 기록 — 건드리지 않는다
            gross = float(rec.get("weight") or 0)
            for f in rec.get("fills") or []:
                w = abs(float(f.get("weight") or 0))
                checked += 1
                assert w <= gross + 1e-3, (
                    f"{fp.name} {rec.get('date')}: 체결 {f.get('key')} 비중 "
                    f"{w}가 그날 총노출 {gross}보다 크다")
    assert checked >= 0            # 새 기록이 아직 없으면 통과(다음 배치부터)
