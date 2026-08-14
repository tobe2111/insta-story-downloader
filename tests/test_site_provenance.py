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

import pytest

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


def _prose(html: str) -> str:
    """읽는 사람에게 **보이는 글자**만 남긴다 — 주석·스크립트는 뺀다.

    ⚠️ 왜 필요한가 (2026-08-14). 아래 검사는 원본 HTML을 통째로 훑었다.
       그래서 "예전에 8만원이 박혀 있었다"고 적어 둔 **개발자 주석**까지
       산문으로 셌다. 시작금을 100만원으로 고치자 이 검사가 "산문은
       8만원인데 설정이 다르다"며 실패했는데 — 화면에는 8만원이 한 글자도
       없었다. 결함을 기록해 둔 주석이 결함으로 잡힌 것이다.

       그리고 반대 방향이 더 나쁘다. 상수가 8만원이던 동안 이 검사는
       **주석 덕분에** 초록이었다. 화면 산문이 무엇을 말하든 상관없이.
    """
    out = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<script\b.*?</script>", " ", out, flags=re.S | re.I)


def test_start_cash_and_goal_in_prose_match_config():
    from quant.live.daily import GOAL_KRW, PORTFOLIO_START_CASH
    html = "".join(_prose(_read(p)) for p in _LIVE_PAGES)
    if "8만원" in html:
        assert PORTFOLIO_START_CASH == 80_000, "산문은 8만원인데 설정이 다르다"
    if "1억" in html:
        assert GOAL_KRW == 100_000_000, "산문은 1억인데 설정이 다르다"
    # 지금 설정이 말하는 시작금은 **화면에 그렇게 적혀 있어야** 한다.
    # (없어도 된다 — 금액은 장부에서 읽는 게 원칙이다. 있다면 맞아야 한다.)
    won = f"{PORTFOLIO_START_CASH / 10_000:,.0f}만원"
    others = {f"{v:,.0f}만원" for v in (8, 10, 50, 100, 500, 1000)} - {won}
    stale = sorted(w for w in others if f"{w}으로 시작" in html
                   or f"{w}으로 시작" in html.replace(" ", ""))
    assert not stale, f"산문이 설정과 다른 시작금을 말한다: {stale} (설정 {won})"


def test_the_prose_is_checked_against_the_live_ledger_not_only_the_constant():
    """산문의 금액은 **살아 있는 계좌**와도 맞아야 한다 (2026-08-13).

    ⚠️ 위 검사에는 구멍이 있었다. 산문을 코드 상수(`PORTFOLIO_START_CASH`)
    와만 대조하는데, 그 상수는 **새 계좌를 만들 때의 기본값**이지 지금
    계좌의 원금이 아니다. 매칭 입금으로 원금이 8만원 → 100만원이 되고
    계좌가 원화로 다시 열린 뒤에도 상수는 80,000 그대로였고, 그래서
    **첫 화면이 "8만원으로 시작한 자동매매"라고 계속 말하는데 검사는 전부
    초록**이었다.

    지키는 규칙: 표시용 금액은 산문에 박지 말고 장부(status.json)에서
    읽는다. 박아야 한다면 지금 계좌와 같아야 한다.
    """
    sj = ROOT / "docs" / "status.json"
    if not sj.exists():
        pytest.skip("status.json이 없다 — 배치 전")
    paper = json.loads(sj.read_text("utf-8")).get("paper") or {}
    pf = next((v for k, v in paper.items() if k.startswith("portfolio:")), None)
    if not pf or pf.get("principal") is None:
        pytest.skip("통합 계좌 기록이 아직 없다")

    principal = float(pf["principal"])
    man = principal / 10_000
    for page in _LIVE_PAGES:
        text = _read(page)
        # 주석은 사실을 설명하는 자리라 뺀다(HTML 주석 · JS 블록 주석)
        shown = re.sub(r"<!--(?:.|\n)*?-->", "", text)
        shown = re.sub(r"/\*(?:.|\n)*?\*/", "", shown)
        # `//` 줄 주석도 산문이 아니다. URL(https://)과 섞이지 않게 **줄
        # 첫머리**가 //인 줄만 뺀다.
        shown = "\n".join(ln for ln in shown.splitlines()
                          if not ln.lstrip().startswith("//"))
        for m in re.finditer(r"(\d[\d,]*)만원", shown):
            ctx = shown[max(0, m.start() - 90):m.end() + 60]
            if "시작" not in ctx and "가상 자금" not in ctx and "원금" not in ctx:
                continue
            val = float(m.group(1).replace(",", ""))
            if val == 1.0:                    # 종목별 참고 계좌(1만원)는 별개
                continue
            assert val == man, (
                f"{page}: 원금을 '{m.group(1)}만원'이라 말하는데 지금 계좌는 "
                f"{man:,.0f}만원이다 — 금액을 산문에 박지 말고 장부에서 읽을 것\n"
                f"  …{ctx[:140]}…")


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


# ── ④ 사이트가 직접 계산하지 말고 장부를 읽는가 ────────────────
#
# 2026-08-11 감사: index·paper·today·weekly 네 페이지가 브라우저에서
# `(오늘자산/어제자산 - 1)`로 하루치를 다시 계산하고 있었다. 입금을 빼지
# 않으므로 매칭입금이 들어온 날은 그 입금이 '수익'으로 표시된다 — 파이썬
# 쪽에서 같은 결함을 고쳤는데(day_return_pct) 화면은 옛 방식이었다.
# 같은 숫자를 두 곳에서 따로 계산하면 반드시 갈라진다.

_DAY_PAGES = ("index.html", "paper.html", "today.html", "weekly.html")


def test_pages_prefer_ledger_day_pct():
    for page in _DAY_PAGES:
        html = _read(page)
        assert "day_pct" in html, f"{page}: 장부의 하루치를 읽지 않는다"


def test_pages_only_recompute_as_fallback():
    """자체 계산은 옛 기록용 폴백으로만 남아야 한다(삼항의 뒷항)."""
    for page in _DAY_PAGES:
        html = _read(page)
        for m in re.finditer(r"\(\s*\w+\.equity\s*/\s*prev\.equity\s*-\s*1\s*\)",
                             html):
            head = html[max(0, m.start() - 220):m.start()]
            assert "day_pct" in head, (
                f"{page}: 장부 값 없이 자산 비율로 하루치를 계산한다")


def test_day_pct_is_actually_produced():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'record["day_pct"]' in src
