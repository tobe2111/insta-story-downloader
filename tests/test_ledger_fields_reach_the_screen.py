"""장부에만 있고 **화면에는 없는 필드**를 찾는다 (감사 98).

FROZEN_IDEAS ⑮에서 스스로 정한 방법이다: "기록했다"와 "보여줬다"는 다른
일이고, 감사할 때 장부에만 있는 필드를 목록으로 뽑아 보라고 적었다.
그대로 돌렸더니 하나가 나왔다.

    "alloc_method": alloc_method,   # hrp | erc | equal — 폴백 흔적

배분 코드는 **폴백 사다리**다:

    hrp = _hrp_slices(...)
    erc = None if hrp else _erc_slices(...)
    slices = hrp or erc or {k: 1.0 / n}        ← 조용히 아래 칸으로

상관 추정에 쓸 데이터가 모자란 날은 HRP가 실패하고 ERC로, 그것도 안 되면
자본 균등으로 내려간다. 장부는 그 흔적을 남기는데(주석에 "폴백 흔적"이라고
직접 적혀 있다) **사이트는 언제나 "HRP·계층적 리스크 패리티"라고 산문으로
말하고 있었다.** 폴백이 일어난 날에만 거짓말을 하는, 가장 잡기 어려운
종류다 — 평소에는 맞기 때문에 아무도 의심하지 않는다.

이 저장소는 같은 실수를 이미 두 번 했다(종목 수·시작금, 목표 변동성
기본값). 그때마다 "산문에 박지 말고 장부에서 읽어라"로 고쳤다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
PAPER = (DOCS / "paper.html").read_text("utf-8")
INDEX = (DOCS / "index.html").read_text("utf-8")


# ── 본체 ────────────────────────────────────────────────────────

def test_the_site_reads_the_allocation_method_from_the_ledger():
    assert "alloc_method" in PAPER, (
        "사이트가 배분 방식을 장부에서 읽지 않는다 — 폴백이 일어난 날에도 "
        "'HRP'라고 말하게 된다")


def test_the_site_does_not_hardcode_hrp_as_the_method():
    """'HRP'가 조건 없이 박혀 있으면 폴백한 날 거짓말이 된다."""
    m = re.search(r'\?rest\.length\+"종목 위험 분산\(([^"]*)"', PAPER)
    assert m, "포트폴리오 설명 문구를 찾지 못했다 — 검사가 낡았다"
    assert "HRP" not in m.group(1), (
        f"배분 방식이 산문에 박혀 있다: {m.group(1)!r}")


def test_each_rung_of_the_fallback_ladder_has_a_label():
    """세 칸(hrp·erc·equal) 모두 이름이 있어야 한다 — 없으면 빈칸이 나간다."""
    for rung in ("hrp", "erc", "equal"):
        assert re.search(rf"\b{rung}\s*:", PAPER), (
            f"폴백 사다리의 '{rung}' 칸에 표시할 이름이 없다")
    assert "폴백" in PAPER, (
        "폴백으로 내려간 상태를 폴백이라 부르지 않는다 — 읽는 사람은 "
        "평소와 같은 화면으로 본다")


def test_a_fallback_raises_a_flag_on_the_front_page():
    """조용한 저하는 경고여야 한다 — 아무도 안 보면 없는 것과 같다."""
    flags = INDEX.split("const flags=[]", 1)[1].split("side-flags", 1)[0]
    assert "alloc_method" in flags, (
        "배분 폴백이 '지금 켜진 경고'에 나타나지 않는다")
    for rung in ('"equal"', '"erc"'):
        assert rung in flags, f"{rung} 폴백에 대한 경고가 없다"


# ── 방법 자체를 고정한다 ────────────────────────────────────────

# 화면에 안 나와도 되는 필드 — 왜 괜찮은지 이유를 함께 적는다.
# (이유를 못 적겠으면 그건 결함이다.)
OFF_SCREEN_OK = {
    "code_sha": "재현용 지문 — 저장소 커밋으로 검증하는 값이라 화면 표시가 목적이 아니다",
    "env": "실행 환경 지문 — 위와 같다",
    "accounting": "회계 방식 버전 — 방식 변경은 trust.html 문단으로 알린다",
    "principal": "원금 — 화면은 자산·손익으로 같은 사실을 보여준다",
    "pnl": "손익 — 위와 같다",
    "hit_rate": "통합 계좌에서는 항상 null(종목 계좌에서만 의미)",
    "xsec_tilt": "종목별 확신도 배수 — 결과인 alloc·applied로 이미 보인다",
    "earnings_guard": "실적 가드 발동 종목 — 발동한 날만 값이 생기고, 그때는 아래 검사가 요구한다",
    "drawdown_pct": "낙폭 — 킬스위치 문구와 자산 곡선으로 같은 사실이 보인다",
    "random_pctile": "무작위 대비 백분위 — index의 별도 카드에서 읽는다",
    "kelly_caps": "종목별 켈리 상한 — 걸렸을 때의 효과가 applied·weight에 이미 반영돼 보인다",
}


def test_every_ledger_field_is_either_shown_or_justified():
    """새 필드를 장부에 넣으면 **보이거나, 왜 안 보여도 되는지 적히거나**.

    이 검사가 하는 일은 판단이 아니라 **강제된 검토**다. 필드를 추가하고
    화면에 안 넣으면 여기서 걸리고, 이유를 한 줄 적어야 통과한다.
    그 한 줄을 못 쓰겠으면 그건 감추고 있는 것이다.
    """
    status = DOCS / "status.json"
    if not status.exists():
        return
    st = json.loads(status.read_text("utf-8"))
    hist = ((st.get("paper") or {}).get("portfolio:ALL") or {}).get("history") or []
    if not hist:
        return
    blob = "".join(p.read_text("utf-8") for p in DOCS.glob("*.html"))
    blob += "".join(p.read_text("utf-8")
                    for p in (ROOT / "quant" / "reporting").glob("*.py"))

    unshown = []
    for k in hist[-1]:
        if k in OFF_SCREEN_OK:
            continue
        if not re.search(rf"\b{re.escape(k)}\b", blob):
            unshown.append(k)
    assert not unshown, (
        f"장부에는 남기면서 어디에도 보여주지 않는 필드: {unshown}\n"
        "  → 화면에 넣거나, OFF_SCREEN_OK에 '왜 안 보여도 되는지'를 적을 것.\n"
        "  → 이유를 한 줄로 못 쓰겠으면 그건 감추고 있는 것이다.")


def test_the_justification_list_does_not_rot():
    """이유 목록이 실제 필드와 어긋나면(오타·삭제) 검사가 헐거워진다."""
    status = DOCS / "status.json"
    if not status.exists():
        return
    st = json.loads(status.read_text("utf-8"))
    hist = ((st.get("paper") or {}).get("portfolio:ALL") or {}).get("history") or []
    if not hist:
        return
    known = set()
    for rec in hist:
        known |= set(rec)
    stale = sorted(set(OFF_SCREEN_OK) - known)
    assert not stale, (
        f"장부에 더는 없는 필드의 면제가 남아 있다: {stale} — 목록을 정리할 것")
