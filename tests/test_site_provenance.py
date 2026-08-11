"""사이트 수치 출처 계약 검사 — 화면의 숫자는 장부에서 나와야 한다.

배경(2026-08-11 감사): 사이트 산문에 '20종목', '8만원', '1억' 같은 숫자가
직접 박혀 있다. 지금은 설정과 일치하지만, AUTO_TARGETS에 종목을 추가하거나
시작 자금을 바꾸면 **사이트만 조용히 거짓말을 하게 된다** — 그리고 이 사이트의
유일한 자산은 정직성이다.

핵심 계약:
  ① 사이트에 박힌 숫자가 실제 설정과 일치한다(어긋나면 테스트가 실패)
  ② status.json의 파생값이 원본과 모순되지 않는다
  ③ 사이트가 표시하는 필드는 실제로 status.json에 존재한다
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def _read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def _produced_status_keys() -> set[str]:
    """status.json에 실제로 생기는 최상위 키.

    두 출처를 합친다. 소스 정규식만 보면 딕셔너리 리터럴로 만드는 키
    (live_url 등)를 놓치고, 실행 결과만 보면 그날 조건이 안 맞아 안 생긴
    키(generation·validation·run_health 등)를 '없는 키'로 오판한다.
    """
    import tempfile
    from quant.live.daily import write_docs_status

    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    keys = set(re.findall(r'status\["([a-z_]+)"\]', src))
    with tempfile.TemporaryDirectory() as td:
        st = write_docs_status(str(ROOT / "state"),
                               docs_path=f"{td}/status.json")
        keys |= {k for k in st if re.fullmatch(r"[a-z_]+", k)}
    return keys


# ── ① 산문에 박힌 숫자 = 실제 설정 ─────────────────────────────


# 현재 상태를 말하는 페이지들. trust.html은 제외한다 — 거기 적힌 '8종목'은
# 과거(8→20 확장) 기록이고, 과거를 현재 설정에 맞춰 고치는 것이야말로 이
# 사이트가 하지 않겠다고 약속한 일이다.
_LIVE_PAGES = ("index.html", "paper.html", "today.html",
               "sns_card.html", "weekly.html")


def test_symbol_count_in_prose_matches_config():
    from quant.markets import AUTO_TARGETS
    n = len(AUTO_TARGETS)
    for page in _LIVE_PAGES:
        html = _read(page)
        if "종목" not in html:
            continue
        found = {int(m) for m in re.findall(r"(\d+)종목", html)}
        # 설정과 다른 종목 수가 산문에 박혀 있으면 사이트가 거짓말을 한다
        assert found <= {n}, f"{page}: 산문 {found} vs 실제 {n}종목"


def test_history_pages_may_keep_past_numbers():
    """과거 기록은 현재 설정에 맞춰 고치지 않는다 — 그게 이 사이트의 약속이다."""
    html = _read("trust.html")
    assert "8종목에서 20종목으로" in html      # 변경을 지운 게 아니라 적어 뒀다


def test_start_cash_and_goal_in_prose_match_config():
    from quant.live.daily import GOAL_KRW, PORTFOLIO_START_CASH
    html = "".join(_read(p) for p in _LIVE_PAGES)
    if "8만원" in html:
        assert PORTFOLIO_START_CASH == 80_000, "산문은 8만원인데 설정이 다르다"
    if "1억" in html:
        assert GOAL_KRW == 100_000_000, "산문은 1억인데 설정이 다르다"


def test_judgment_days_not_hardcoded_in_site():
    """판정 기준일은 status.json의 target_days로만 표시해야 한다."""
    html = _read("index.html")
    assert "g.target_days" in html          # 장부 값을 쓴다
    # '90일'이 산문에 박혀 있다면 target_days와 일치해야 한다
    if "90일" in html:
        from quant.live.daily import _generation_info
        g = _generation_info(str(ROOT / "state"))
        assert not g or g["target_days"] == 90


# ── ② status.json 파생값의 무모순 ──────────────────────────────


def test_status_derived_values_are_consistent():
    path = DOCS / "status.json"
    if not path.exists():
        return
    st = json.loads(path.read_text(encoding="utf-8"))
    for key, p in (st.get("paper") or {}).items():
        hist = p.get("history") or []
        if not hist:
            continue
        # 요약의 equity는 마지막 기록의 equity와 같아야 한다
        assert p.get("equity") == hist[-1].get("equity"), key
        # 수익률은 원금 기준 계산과 (반올림 오차 안에서) 일치해야 한다
        if p.get("principal") and p.get("return_pct") is not None:
            calc = (p["equity"] / p["principal"] - 1) * 100
            assert abs(calc - p["return_pct"]) < 0.01, (
                f"{key}: 표시 {p['return_pct']} vs 계산 {calc:.4f}")


# ── ③ 사이트가 읽는 필드가 실제로 존재 ─────────────────────────


def test_site_reads_only_fields_that_exist():
    """사이트가 참조하는 status.json 최상위 키가 실제로 생성되는 키인가.

    index.html만 보던 것을 전 페이지로 넓혔다(2026-08-11) — 한 페이지만
    지키는 계약은 나머지 페이지에서 같은 결함이 자라게 둔다.
    """
    produced = _produced_status_keys()
    for page in sorted(DOCS.glob("*.html")):
        referenced = set(re.findall(r"\bst\.([a-z_]+)", page.read_text("utf-8")))
        unknown = referenced - produced
        # 이 테스트가 실제로 잡아낸 것: 사이트가 st.vol_target(최상위)을 읽었지만
        # vol_target은 일별 기록 안에만 있어 카드가 영원히 비어 있었다.
        assert not unknown, f"{page.name}: 없는 필드를 읽는다 {sorted(unknown)}"
