"""사이트가 말하는 숫자가 **실제 설정을 따라가는가** (감사 89).

`quant/reporting/social.py`에 이런 주석이 있다:

    종목 수와 시작금은 산문에 박지 않는다 — 설정이 바뀌면 SNS만 조용히
    거짓말을 하게 된다(사이트에 같은 결함이 있어 이미 계약 검사로 막았다).

SNS 캡션은 실제로 그렇게 돼 있다. 그런데 **사이트는 아니었다.** "20종목"이
index·paper·sns_card·admin 네 곳에 문자열로 박혀 있고, 유니버스를 바꾸면
사이트만 옛 숫자를 말한다.

기존 계약 검사는 이랬다:

    assert len(AUTO_TARGETS) == 20        # 코드를 고정
    assert "20종목" in trust               # HTML을 고정 (별개로!)

둘이 **연결돼 있지 않다.** 유니버스를 25종목으로 바꾸면 첫 줄만 고치게 되고,
사이트는 "20종목"이라 말한 채 통과한다. 게다가 검사가 보는 `trust.html`의
"20종목"은 **날짜가 붙은 과거 기록**("2026-08-05, 8종목에서 20종목으로
확장했습니다")이라, 바뀌면 안 되는 문장을 고정하고 바뀌어야 하는 문장은
놓치고 있었다 — 정확히 거꾸로였다.

여기서는 숫자를 **코드에서 읽어** 대조한다. 이 파일 어디에도 20이라는
literal이 없어야 검사가 제 구실을 한다.

⚠️ 날짜가 붙은 문장은 면제한다. `trust.html`의 이력은 '그때 그랬다'는
   기록이고, 이 프로젝트는 **과거를 고치지 않는다.**
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import PORTFOLIO_START_CASH      # noqa: E402
from quant.markets import AUTO_TARGETS                 # noqa: E402

DOCS = ROOT / "docs"

# 지금 굴리는 구조를 **현재형으로** 주장하는 페이지들.
LIVE_CLAIM_PAGES = ["index.html", "paper.html", "sns_card.html", "admin.html"]

# 날짜가 붙은 문장은 과거 기록이다 — 고치지 않는다.
DATED = re.compile(r"20\d\d-\d\d-\d\d")


def _sentences_with(text: str, pattern: re.Pattern):
    """패턴이 나온 자리 주변 문장을 (숫자, 문맥)으로 돌려준다."""
    out = []
    for m in pattern.finditer(text):
        s, e = max(0, m.start() - 160), min(len(text), m.end() + 60)
        ctx = re.sub(r"<[^>]+>", " ", text[s:e])
        out.append((m.group(1), re.sub(r"\s+", " ", ctx).strip()))
    return out


SYMS = re.compile(r"(\d{1,3})\s*종목")
WON = re.compile(r"(\d{1,3}(?:,\d{3})*)\s*원")


# ── 종목 수 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("page", LIVE_CLAIM_PAGES)
def test_symbol_count_claims_match_the_universe(page):
    """'N종목'이라 말하면 그 N이 실제 유니버스 크기여야 한다."""
    n = len(AUTO_TARGETS)
    text = (DOCS / page).read_text(encoding="utf-8")
    for got, ctx in _sentences_with(text, SYMS):
        if DATED.search(ctx):
            continue                       # 날짜 붙은 과거 기록은 면제
        assert int(got) == n, (
            f"{page}: 사이트는 '{got}종목'이라 말하는데 실제 유니버스는 "
            f"{n}종목이다 — 설정이 바뀌면 사이트만 조용히 거짓말을 한다\n"
            f"  …{ctx[:120]}…")


def test_the_universe_is_not_empty():
    """유니버스가 비면 위 검사가 조용히 전부 통과한다."""
    assert len(AUTO_TARGETS) >= 2


def test_historical_records_are_exempt():
    """날짜 붙은 이력은 유니버스가 바뀌어도 그대로여야 한다.

    '2026-08-05, 8종목에서 20종목으로 확장했습니다'는 그때의 사실이다.
    이 검사가 이력까지 강제하면 과거를 고치게 만든다.
    """
    trust = (DOCS / "trust.html").read_text(encoding="utf-8")
    dated = [ctx for _n, ctx in _sentences_with(trust, SYMS)
             if DATED.search(ctx)]
    assert dated, "trust.html의 날짜 붙은 종목 수 기록을 찾지 못했다"


# ── 시작금 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("page", LIVE_CLAIM_PAGES)
def test_start_cash_claims_match_the_code(page):
    """'80,000원' 같은 시작금 주장도 코드를 따라가야 한다."""
    text = (DOCS / page).read_text(encoding="utf-8")
    start = int(PORTFOLIO_START_CASH)
    man = start // 10_000              # 만원 단위 표기도 허용
    for got, ctx in _sentences_with(text, WON):
        if DATED.search(ctx):
            continue
        if "시작" not in ctx and "가상 자금" not in ctx:
            continue                           # 시작금 문맥만 본다
        val = int(got.replace(",", ""))
        assert val in (start, man), (
            f"{page}: 시작금을 '{got}원'이라 말하는데 코드는 {start:,}원이다\n"
            f"  …{ctx[:120]}…")


def test_the_sns_caption_does_not_hardcode_either():
    """캡션 쪽 규칙이 무너지지 않았는지도 같이 본다(그쪽이 원본이다)."""
    src = (ROOT / "quant" / "reporting" / "social.py").read_text("utf-8")
    assert "AUTO_TARGETS" in src and "PORTFOLIO_START_CASH" in src, (
        "캡션이 종목 수·시작금을 코드에서 읽지 않고 산문에 박기 시작했다")


def test_this_test_reads_the_numbers_from_code():
    """이 파일이 숫자를 박아 두면 검사가 제 구실을 못 한다.

    코드가 25종목이 돼도 이 파일이 20을 알고 있으면 아무것도 못 잡는다.
    """
    me = Path(__file__).read_text(encoding="utf-8")
    # 설명문(docstring)과 주석은 뺀다 — 거기 적힌 숫자는 판단에 쓰이지 않고,
    # 오히려 '그때 왜 이렇게 했나'를 남기는 기록이다. 검사가 봐야 하는 것은
    # **실행되는 코드**뿐이다.
    body = re.sub(r'"""(?:.|\n)*?"""', "", me)
    body = re.sub(r"#.*", "", body)
    # 이 함수 자신도 뺀다 — 아래 패턴 문자열이 자기 자신에 걸린다.
    body = body.split("def test_this_test_reads_the_numbers_from_code")[0]
    n, won = len(AUTO_TARGETS), int(PORTFOLIO_START_CASH)
    banned = [f"{n}종목", f"{won:,}", f"{won // 10_000}만원"]
    for bad in banned:
        assert bad not in body, (
            f"검사 안에 현재 설정값을 박았다({bad!r}) — 코드에서 읽어야 "
            "설정이 바뀔 때 이 검사가 제 구실을 한다")


# ── 목표 변동성 기본값 (감사 90) ────────────────────────────────
#
# 어드민 패널은 사장님이 통합 계좌의 위험 크기를 정하는 화면이다. 거기에
# "비워두면 코드 기본값 (엣지 미입증 12% / 입증 후 20%)을 따릅니다"라고
# 적혀 있는데, 그 숫자가 산문에 박혀 있었다. 코드 기본값이 바뀌면 패널이
# 사장님께 거짓말을 한다 — 그걸 읽고 위험을 정하는 화면에서.
#
# index.html은 같은 값을 장부(vt.target)에서 읽어 렌더링한다. 두 화면이
# 같은 사실을 다른 방식으로 말하고 있었고, 한쪽만 뒤처질 수 있었다.

def _pct_claims(text: str, keyword: str):
    """키워드 근처에 적힌 퍼센트 값들."""
    out = []
    for m in re.finditer(re.escape(keyword), text):
        seg = re.sub(r"<[^>]+>", " ", text[m.start():m.start() + 220])
        out += [float(x) for x in re.findall(r"(\d{1,2}(?:\.\d)?)\s*%", seg)]
    return out


def test_admin_states_the_real_default_target_vols():
    """어드민이 말하는 '코드 기본값'이 진짜 코드 기본값이어야 한다."""
    from quant.risk.portfolio_vol import PROVEN_TARGET_VOL, VERIFY_TARGET_VOL
    text = (DOCS / "admin.html").read_text(encoding="utf-8")
    claims = _pct_claims(text, "코드 기본값")
    assert claims, "어드민에서 '코드 기본값' 안내를 찾지 못했다"
    want = {round(VERIFY_TARGET_VOL * 100, 1), round(PROVEN_TARGET_VOL * 100, 1)}
    got = {round(c, 1) for c in claims}
    assert want <= got, (
        f"어드민이 코드 기본값을 {sorted(got)}%라 말하는데 실제는 "
        f"{sorted(want)}%다 — 사장님이 그 문장을 읽고 위험 크기를 정한다")


def test_the_live_flag_reads_the_target_from_the_ledger():
    """index의 리스크 잠금 문구는 장부 값을 렌더링해야 한다(산문 금지)."""
    text = (DOCS / "index.html").read_text(encoding="utf-8")
    assert "vt.target" in text, (
        "index가 목표 변동성을 장부에서 읽지 않고 산문에 박기 시작했다")


# ── 카드도 코드에서 읽는가 (감사 113) ──────────────────────────
#
# 감사 89에서 **캡션**은 종목 수·시작금을 코드에서 읽게 고쳤다. 그런데
# **SNS 카드는 그대로 산문**이었다 — 또 형제를 안 찾았다(FROZEN_IDEAS ⑭).
# 게다가 'N종목 분산'은 후보 수지 실제 보유가 아니라, 절반이 관망인 날에도
# 그만큼 퍼져 있는 것처럼 읽혔다(감사 91과 같은 계열).

CARD = (DOCS / "sns_card.html").read_text(encoding="utf-8")


def _card_body() -> str:
    """JS 주석은 뺀다 — 화면에 나가는 글만 본다."""
    return re.sub(r"^\s*//.*$", "", CARD, flags=re.M)


def test_the_card_reads_the_start_cash_from_the_ledger():
    body = _card_body()
    assert "startTxt" in body and "port.start_cash" in body, (
        "카드가 시작금을 장부에서 읽지 않는다")
    assert "시작 8만원" not in body, "시작금이 산문에 박혀 있다"


def test_the_card_separates_holdings_from_the_universe():
    body = _card_body()
    assert "'종목 보유 / 후보 '" in body, (
        "카드가 '실제 보유'와 '후보'를 구별하지 않는다 — 절반이 관망인 날도 "
        "전 종목에 퍼져 있는 것처럼 읽힌다")
    assert "종목 분산" not in body, "'N종목 분산'이 남아 있다"


def test_the_card_counts_holdings_from_the_ledger():
    body = _card_body()
    assert "var held=" in body and "nCash" in body, (
        "보유 종목 수를 장부에서 세지 않는다")


# ── 어드민 참고 수치도 장부에서 (감사 118) ─────────────────────
#
# 목표 변동성 입력란 아래에 이런 문장이 **고정 문자열**로 박혀 있었다:
#   "참고: 20종목 무레버리지 전액투자의 예상 변동성이 약 8.8%입니다."
# 사장님이 그 숫자를 읽고 위험 크기를 정하는 화면인데, 값이 맞는지
# 아무도 확인하지 않는다. 감사 90에서 '코드 기본값 12/20%'는 코드에서
# 읽게 고쳤는데 이 줄만 남겨 뒀다 — 형제 미탐색 일곱 번째.

ADMIN = (DOCS / "admin.html").read_text(encoding="utf-8")


def test_admin_does_not_hardcode_a_reference_volatility():
    body = re.sub(r"/\*(?:.|\n)*?\*/", "", ADMIN)
    assert "8.8%" not in body, "참고 변동성이 산문에 박혀 있다"
    assert "무레버리지 전액투자의 예상 변동성이 약" not in body


def test_admin_reads_the_reference_from_the_ledger():
    assert 'id="volref"' in ADMIN, "참고 수치를 담을 자리가 없다"
    assert "vt.ex_ante" in ADMIN and "vt.scale" in ADMIN, (
        "어드민이 참고 수치를 장부에서 읽지 않는다")


def test_admin_does_not_invent_a_derived_number():
    """검증할 수 없는 파생값을 만들지 않는다.

    처음엔 '전액투자 환산 = ex_ante ÷ 총노출'을 보이려 했다가 잡았다 —
    ex_ante는 스케일 **전** 비중 기준이고 weight는 스케일 **후** 총노출
    이라 나누면 아무 뜻이 없다. 장부에 있는 값만 그대로 적는다.
    """
    body = re.sub(r"/\*(?:.|\n)*?\*/", "", ADMIN)
    assert "vt.ex_ante/last.weight" not in body.replace(" ", ""), (
        "스케일 전후가 다른 두 값을 나눠 파생 수치를 만든다")
    assert "전액투자 환산" not in body
