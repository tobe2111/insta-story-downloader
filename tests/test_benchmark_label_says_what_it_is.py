"""'그냥 보유했다면'이 **무엇을 보유했는지** 밝히는가 (감사 109).

사이트는 전략 옆에 벤치마크를 나란히 그린다. 2026-08-11 값이 이랬다.

    전략        79,902원
    그냥 보유   79,256원   ← 시장이 -0.93% 빠졌다는 뜻

운영자가 물었다: **"그냥 보유했으면 80,000원 아니야?"**

라벨만 보면 그렇게 읽는 게 자연스럽다 — "아무것도 안 했다"로. 실제
정의는 **첫 기록일에 같은 돈으로 전 종목을 균등 매수해 그대로 보유**다.
현금으로 뒀다는 뜻이 아니라 **시장에 맡겨 뒀다면**이라는 뜻이라, 시장이
빠진 날은 이 값도 8만원 아래로 내려간다.

숫자는 맞았다. 그런데 **무엇의 숫자인지 모르면 오해가 생긴다** — 감사
107(두 계좌 혼동)과 같은 계열이고, FROZEN_IDEAS ⑳ 그대로다:
'만든 사람이 헷갈리면 읽는 사람은 반드시 헷갈린다.'

이 벤치마크는 이 실험의 **핵심 주장**을 지탱한다 — "전략이 그냥 보유를
못 이기면 전략의 의미가 없다". 그 비교선의 정의가 모호하면 주장 자체가
검증 불가능해진다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
PAGES = ["index.html", "paper.html"]


def _shown(name: str) -> str:
    """화면에 나가는 글만 — JS 주석은 뺀다."""
    s = (DOCS / name).read_text("utf-8")
    s = re.sub(r"/\*(?:.|\n)*?\*/", "", s)
    return re.sub(r"^\s*//.*$", "", s, flags=re.M)


@pytest.mark.parametrize("page", PAGES)
def test_the_benchmark_label_is_not_bare(page):
    """'그냥 보유했다면'만 적으면 '현금으로 뒀다면'으로 읽힌다."""
    text = _shown(page)
    for m in re.finditer(r"그냥 보유했다면", text):
        near = text[max(0, m.start() - 120):m.end()]
        assert ("균등" in near or "매수" in near), (
            f"{page}: '그냥 보유했다면'이 무엇을 보유했는지 밝히지 않는다\n"
            f"  …{re.sub(r'<[^>]+>', ' ', near)[-90:]}…")


def test_the_paper_page_explains_it_in_words():
    """범례만으로는 부족하다 — 한 번은 문장으로 설명해야 한다."""
    text = _shown("paper.html")
    assert "그냥 보유" in text
    seg = text[text.index("\"그냥 보유\""):][:600]
    for must in ("균등", "현금", "시장"):
        assert must in seg, (
            f"설명에 '{must}'가 없다 — 오해의 핵심(현금이 아니라 시장 노출)을 "
            f"짚지 못한다\n{re.sub(r'<[^>]+>', ' ', seg)[:200]}")


def test_the_benchmark_is_computed_from_the_ledger_index():
    """벤치마크는 장부의 균등지수(price)에서 나와야 한다.

    산문에 박거나 자산으로 다시 계산하면 입금이 벤치마크를 밀어 올린다.
    """
    src = (DOCS / "paper.html").read_text("utf-8")
    assert "hist[0].price" in src or "s.hist[0].price" in src, (
        "벤치마크를 첫 기록일의 균등지수로 정규화하지 않는다")


def test_the_recorded_index_actually_moves():
    """지수가 상수면 벤치마크가 늘 8만원이라 위 오해가 사실이 된다."""
    import json
    st = DOCS / "status.json"
    if not st.exists():
        return
    h = ((json.loads(st.read_text("utf-8")).get("paper") or {})
         .get("portfolio:ALL") or {}).get("history") or []
    prices = [r.get("price") for r in h if isinstance(r.get("price"), (int, float))]
    if len(prices) < 2:
        return
    assert len(set(prices)) > 1, (
        "균등지수가 한 번도 안 움직였다 — 벤치마크가 계산되지 않는 상태")
