"""묵은 데이터로 판단한 날을 화면에서 밝히는가 (2026-08-14 감사 232 후속).

감사 232에서 이런 일이 있었다. 예비 배치가 실행 지연으로 23:58에 시작해
UTC 자정을 넘겼고, **0.03%만 만들어진 코인 봉**이 '2026-08-14'라는 새 하루를
열었다. 그 기록의 주식 판단은 전날 봉으로 내려진 것이다:

    08-13 기록  bar_partial 0.9619  bar_age {crypto 0, us 0, kr 0}   정상
    08-14 기록  bar_partial 0.0003  bar_age {crypto 0, us 1, kr 1}   ← 이것

**이 저장소는 과거를 고치지 않는다.** 불편한 날을 지우기 시작하면 좋은 날의
숫자도 믿을 수 없게 되기 때문이다. 그래서 기록은 그대로 두고 `docs/trust.html`
(재출발·기준 변경 기록)에 무슨 일이 있었는지 적는다 — 그것이 이 제품이
'정정'을 처리하는 방식이다.

이 검사가 지키는 것: **고쳤다는 사실이 화면에 남아 있는가.** 코드만 고치고
공개 문서에 안 적으면, 사이트를 보는 사람은 그날 숫자가 어떻게 나왔는지 알
방법이 없다. 그러면 '숨김없이 보여주는 공개 실험'이 아니다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TRUST = (ROOT / "docs" / "trust.html").read_text("utf-8")


def _visible(html: str) -> str:
    """사람 눈에 보이는 글자만. 주석·툴팁은 '적어 뒀다'로 치지 않는다.

    ⚠️ 이 저장소가 아홉 번 당한 함정이다 — 검사가 소스 문자열을 찾으면
       주석에 같은 말이 있는 것만으로 통과한다. 실제로 그래서, 화면에서
       문장을 지워도 검사가 초록인 적이 있었다.
    """
    h = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    h = re.sub(r'title="[^"]*"', " ", h)
    return re.sub(r"<[^>]+>", " ", h)


def test_the_stale_day_is_named_on_the_public_page():
    """어느 날 기록인지 — 날짜가 있어야 대조할 수 있다."""
    v = _visible(TRUST)
    assert "2026-08-14" in v, "묵은 판단이 있었던 날짜가 화면에 없다"


def test_the_page_says_what_actually_went_wrong():
    """'문제가 있었습니다'로는 부족하다 — 무엇이 어떻게 어긋났는지 적는다."""
    v = _visible(TRUST)
    for phrase in ("자정", "0.03%", "전날 봉"):
        assert phrase in v, f"'{phrase}'가 화면에 없다 — 설명이 비었다"


def test_the_page_points_at_the_evidence_field():
    """장부의 어느 필드를 보면 확인되는지 — 검증 가능해야 정정이다."""
    assert "bar_age_days" in _visible(TRUST), (
        "근거 필드를 안 적으면 독자가 스스로 확인할 수 없다")


def test_the_page_says_the_record_stays():
    """'고치지 않는다'가 이 제품의 정체성이다 — 그 말을 화면에서 한다."""
    v = _visible(TRUST)
    assert "지우거나 고치지 않습니다" in v


def test_the_page_says_what_was_fixed_going_forward():
    """정정은 사후 처리로 끝나면 안 된다 — 재발 방지도 함께 적는다."""
    v = _visible(TRUST)
    assert "90분" in v, "크론을 얼마나 떼어 놓았는지가 없다"
    assert "코드로도" in v, "시각만 고치고 끝난 것처럼 읽힌다"


def test_the_correction_matches_the_actual_ledger():
    """**화면의 주장이 장부와 맞는가** — 정정문이 또 하나의 창작이면 안 된다.

    이 저장소의 규칙: 숫자는 저장소에서 확인한 값만 쓴다.
    """
    path = ROOT / "state" / "paper" / "portfolio_ALL.json"
    if not path.exists():
        pytest.skip("장부 없음(새 설치)")
    hist = json.loads(path.read_text("utf-8")).get("history") or []
    rec = next((h for h in hist if h.get("date") == "2026-08-14"), None)
    if rec is None:
        pytest.skip("그날 기록이 아카이브로 옮겨졌다")
    age = rec.get("bar_age_days") or {}
    assert age.get("us_stock") == 1 and age.get("kr_stock") == 1, (
        f"화면은 주식이 하루 묵었다고 말하는데 장부는 {age}다")
    partial = max((rec.get("bar_partial") or {"x": 1.0}).values())
    assert partial < 0.01, (
        f"화면은 봉이 0.03%만 만들어졌다고 말하는데 장부는 {partial}다")


def test_a_normal_day_is_not_described_as_stale():
    """대조군 — 정상인 날은 bar_age가 전부 0이어야 그 주장이 성립한다."""
    path = ROOT / "state" / "paper" / "portfolio_ALL.json"
    if not path.exists():
        pytest.skip("장부 없음")
    hist = json.loads(path.read_text("utf-8")).get("history") or []
    rec = next((h for h in hist if h.get("date") == "2026-08-13"), None)
    if rec is None:
        pytest.skip("그날 기록이 아카이브로 옮겨졌다")
    assert set((rec.get("bar_age_days") or {}).values()) == {0}
