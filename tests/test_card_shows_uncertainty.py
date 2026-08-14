"""가장 널리 퍼지는 화면이 **불확실성을 같이 말하는가** (감사 94).

`paper.html`은 보정 표에 윌슨 95% 신뢰구간을 함께 찍고, 주석에 이유까지
적어 뒀다:

    // 윌슨 95% 신뢰구간 — 소표본의 비율이 확신처럼 읽히지 않게 폭을 함께 보인다
    신뢰구간(95%)이 좁아질 때까지는 비율보다 구간을 믿으세요.

그런데 **SNS 카드에는 그게 없었다.** 같은 집계를 같은 데이터로 하면서
점추정만 찍었다. 2026-08-11 실제 값:

    카드: "55~60%라 말한 날 8일 · 실제 상승 12%"
    사이트: 같은 칸에 95% 구간 2~47%

n=8짜리 비율이 확정된 사실처럼 나갔다. 좋아 보이는 쪽도 똑같다 —
"70% 이상 → 실제 상승 64%"(실제 구간 39~84%)는 증거처럼 읽힌다.

이 프로젝트는 엣지 판정에서 **윌슨 하한**을 쓰고, 하한이 50%를 못 넘으면
거절한다. 같은 잣대가 방송에도 적용돼야 한다 — 오히려 사이트보다 카드가
더 멀리 가므로 더 엄격해야 한다.

여기서 고정하는 계약: **보정 비율을 보이는 곳은 구간도 같이 보인다.**
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
CARD = (DOCS / "sns_card.html").read_text("utf-8")
PAPER = (DOCS / "paper.html").read_text("utf-8")


def test_the_card_computes_a_confidence_interval():
    assert "wilson" in CARD, (
        "카드가 보정 비율을 점추정으로만 찍는다 — 표본 8일짜리 숫자가 "
        "확정된 사실처럼 방송된다")


def test_the_card_uses_the_same_formula_as_the_site():
    """두 화면이 다른 식을 쓰면 같은 날 다른 구간을 말하게 된다.

    ⚠️ 이 검사는 원래 **두 파일에 같은 사본이 들어 있는가**를 봤다. 의도는
       옳았지만 방법이 사본을 요구하고 있었다 — 그리고 실제로 사본은
       파이썬까지 셋으로 늘어나 있었다(2026-08-14).

       이제 식은 docs/assets/hitrate.js 한 곳에만 있고 둘 다 그것을 싣는다.
       '같은 식인가'를 비교로 확인할 필요가 없어졌다 — **같은 파일**이다.
       그래서 여기서는 사본이 되살아나지 않는지를 지킨다.
    """
    for name, src in (("sns_card.html", CARD), ("paper.html", PAPER)):
        assert 'src="assets/hitrate.js"' in src, f"{name}가 공용 식을 안 싣는다"
        assert not re.search(r"z\s*\*\s*z\s*/\s*\(\s*2\s*\*\s*n\s*\)", src), (
            f"{name}가 윌슨 식 사본을 다시 갖고 있다")
        assert "QuantHitRate.wilsonCI" in src, f"{name}가 공용 식을 안 부른다"


def test_the_card_band_matches_the_shared_rule_by_value():
    """문자열이 아니라 **값**으로 확인한다.

    카드는 비율(p)로 부르고 공용 함수는 적중 수(k)로 받는다 — 그 변환을
    카드가 잘못하면 파일은 하나인데 답이 갈린다.
    """
    import json
    import shutil
    import subprocess

    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        import pytest
        pytest.skip("node 없음 — 카드 구간 값 검사 생략")
    m = re.search(r"var wilson\s*=\s*(function\(p,n\)\{.+?\});", CARD, re.S)
    assert m, "카드의 구간 함수를 찾지 못했다 — 검사가 낡았다"
    cases = [[3, 8], [12, 25], [0, 5], [49, 81]]
    js = f"""
      import {{ readFileSync }} from "node:fs";
      new Function(readFileSync("docs/assets/hitrate.js", "utf8"))();
      const wilson = {m.group(1)};
      console.log(JSON.stringify({json.dumps(cases)}.map(([k, n]) =>
        [wilson(k / n, n), globalThis.QuantHitRate.wilsonCI(k, n)])));
    """
    r = subprocess.run([node, "--input-type=module", "-e", js],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
    for (k, n), (card, shared) in zip(cases, json.loads(r.stdout)):
        assert abs(card[0] - shared[0]) < 1e-12, f"k={k} n={n} 하한이 갈린다"
        assert abs(card[1] - shared[1]) < 1e-12, f"k={k} n={n} 상한이 갈린다"


def test_every_calibration_ratio_on_the_card_carries_its_band():
    """비율을 찍는 줄에는 구간도 같이 있어야 한다."""
    # 보정 카드(n===6) 블록만 본다.
    blk = CARD.split("}else if(n===6){", 1)
    assert len(blk) == 2, "보정 카드 블록을 찾지 못했다 — 검사가 낡았다"
    body = blk[1].split("}else if(n===", 1)[0]
    assert "a.up/a.n" in body, "보정 비율 계산을 찾지 못했다 — 검사가 낡았다"
    assert "wilson(" in body, (
        "보정 비율은 찍으면서 신뢰구간은 계산하지 않는다")
    # ⚠️ "95%"가 본문에 있다는 것만으로는 부족하다 — 안내문에도 그 글자가
    #    있어서, 렌더링만 지워도 통과한다(변이 시험이 이 구멍을 잡았다).
    #    **계산한 구간이 실제로 그려지는지**를 본다.
    row = body.split("var rows6=", 1)[1].split("html=page(", 1)[0]
    for part in ("ci[0]", "ci[1]"):
        assert part in row, (
            f"신뢰구간을 계산해 놓고 화면에 그리지 않는다({part} 미사용) — "
            "카드는 여전히 점추정만 방송한다")
    assert "95%" in row, "구간이 무엇인지(95%) 그 줄에서 밝히지 않는다"


def test_the_card_says_when_the_sample_is_still_thin():
    """표본이 얇으면 얇다고 먼저 말한다(사이트와 같은 문턱 30일)."""
    body = CARD.split("}else if(n===6){", 1)[1].split("}else if(n===", 1)[0]
    assert re.search(r"calTotal\s*<\s*30", body), (
        "표본 30일 미만에도 '수집 중'이라 말하지 않는다 — 사이트는 말한다")


def test_the_site_still_shows_its_band():
    """반대 방향 퇴행도 막는다 — 사이트에서 구간이 사라지면 여기서 걸린다."""
    assert "신뢰구간" in PAPER and "wilson" in PAPER
