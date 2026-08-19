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

import ast
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

# ── 필드 목록을 **소스에서** 읽는다 (감사 286) ──────────────────
#
# ⚠️ 2026-08-18 밤, 이 검사가 페이퍼 배치를 **사흘째 멈춰 세웠다.**
#
#       AssertionError: 장부에는 남기면서 어디에도 보여주지 않는 필드:
#           ['impossible_amounts', 'net_weight', 'short_refused']
#
#    셋 다 며칠 전 감사에서 **내가 장부에 새로 넣은 필드**다. 그런데 검사는
#    그날 밤 배치가 기록을 만들기 전까지 그 사실을 몰랐다 — 목록을
#    `docs/status.json`의 **마지막 기록**에서 읽었기 때문이다. 필드를 추가한
#    커밋의 CI는 초록이었고(그 시점 마지막 기록에는 아직 그 필드가 없다),
#    경고는 사흘 뒤 22:30 UTC에 **커밋 직전 관문**에서 처음 울렸다.
#    관문은 제 할 일을 했지만, 그 대가로 그날 장부가 통째로 안 남았다.
#
#    검사가 **자기가 감시할 대상을 감시받는 쪽이 만들어 줄 때까지 기다리면**
#    이렇게 된다. 필드는 기록이 아니라 코드가 정한다. 그러니 코드에서 읽는다.
#    그러면 필드를 넣은 그 PR에서 걸리고, 밤 배치는 멈추지 않는다.

DAILY = ROOT / "quant" / "live" / "daily.py"


def declared_record_fields() -> list[str]:
    """`run_daily_portfolio`가 장부에 쓰는 필드 이름 전부 (소스에서)."""
    tree = ast.parse(DAILY.read_text("utf-8"))
    fn = next((f for f in ast.walk(tree)
               if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
               and f.name == "run_daily_portfolio"), None)
    assert fn is not None, "run_daily_portfolio를 찾지 못했다 — 검사가 낡았다"
    out: list[str] = []
    for node in ast.walk(fn):
        # record = {...}
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(isinstance(t, ast.Name) and t.id == "record"
                   for t in node.targets):
                out += [k.value for k in node.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        # record["x"] = ... (나중에 덧붙이는 필드)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Name) and t.value.id == "record"
                        and isinstance(t.slice, ast.Constant)
                        and isinstance(t.slice.value, str)):
                    out.append(t.slice.value)
    assert len(out) > 30, f"필드를 {len(out)}개밖에 못 읽었다 — 검사가 낡았다"
    return sorted(set(out))


def _screen_blob() -> str:
    """화면을 만드는 코드 전부.

    ⚠️ `docs/assets/*.js`가 빠져 있었다(감사 286). 표시 판단이 페이지에서
       공용 모듈로 옮겨 가면서(체결 판정 `fills.js`, 금액 판정 `amounts.js`)
       **실제로 보여주고 있는 필드를 이 검사가 못 보게 됐다.** 검사가 보는
       범위가 화면을 만드는 범위보다 좁으면, 잘 보여주고 있는 것도 '안
       보여준다'고 우기게 된다 — 헛울리는 관문은 곧 무시당한다.
    """
    blob = "".join(p.read_text("utf-8") for p in sorted(DOCS.glob("*.html")))
    blob += "".join(p.read_text("utf-8")
                    for p in sorted((DOCS / "assets").glob("*.js")))
    blob += "".join(p.read_text("utf-8")
                    for p in sorted((ROOT / "quant" / "reporting").glob("*.py")))
    return blob


def _unshown(fields) -> list[str]:
    blob = _screen_blob()
    return [k for k in fields
            if k not in OFF_SCREEN_OK
            and not re.search(rf"\b{re.escape(k)}\b", blob)]


def test_every_field_the_code_writes_is_either_shown_or_justified():
    """기록이 생기기 **전에** 걸린다 — 필드를 넣은 그 PR에서.

    위의 형제 검사(`..._ledger_field_...`)는 이미 저장된 기록을 본다.
    그것만으로는 새 필드가 처음 기록되는 밤에야 걸리고, 그 밤은 배치가
    커밋을 못 하는 밤이 된다. 여기서는 코드가 쓰겠다고 선언한 필드를 본다.
    """
    unshown = _unshown(declared_record_fields())
    assert not unshown, (
        f"장부에 쓰겠다고 적어 놓고 어디에도 보여주지 않는 필드: {unshown}\n"
        "  → 화면에 넣거나, OFF_SCREEN_OK에 '왜 안 보여도 되는지'를 적을 것.\n"
        "  → 밤 배치가 아니라 **여기서** 걸리는 것이 이 검사의 목적이다.")


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
    "data_source": "종목별 시세 제공자 — 문제가 되는 경우(합성 폴백)는 "
                   "data_source_fallback으로 따로 경고한다",
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
    unshown = _unshown(list(hist[-1]))
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
    known = set(declared_record_fields())
    for rec in hist:
        known |= set(rec)
    stale = sorted(set(OFF_SCREEN_OK) - known)
    assert not stale, (
        f"장부에 더는 없는 필드의 면제가 남아 있다: {stale} — 목록을 정리할 것")




# ── 값을 정말 **기록에서** 읽는가 (감사 278) ────────────────────
#
# ⚠️ 2026-08-17 야간 변이 전수가 이 파일을 이렇게 뚫었다.
#
#       const lp=pfLast.lot_priority||null;   →   const lp=null;
#       const ba=pfLast.bar_age_days||null;   →   const ba=null;
#
#    둘 다 **경고가 통째로 사라지는** 변이인데 위의 검사들은 전부 통과했다.
#    이유가 아프다: 위 검사는 "그 낱말이 어딘가에 있는가"만 봤고,
#    `lot_priority`는 같은 파일 다른 줄과 `docs/assets/amounts.js`에,
#    `bar_age_days`는 `docs/trust.html` 본문에 그대로 남아 있었다.
#    **필드 이름이 파일에 있다는 것과 그 사실이 화면에 나온다는 것은 다른
#    일이다** — 이 파일이 감사 98에서 잡겠다고 한 바로 그 구별인데,
#    정작 검사 자신이 그 구별을 못 하고 있었다.
#
#    그래서 ① 값을 정말 기록에서 읽는지(구조)는 여기서 보고, ② 읽은 값이
#    정말 화면에 나오는지(행동)는 브라우저를 띄우는 짝
#    `tests/test_the_screen_says_who_took_the_budget.py`가 본다.
#
# ⚠️ 왜 굳이 파일을 나눴나 (감사 280). 이 파일은 `scripts/ledger_gate.py`가
#    **배치 커밋 직전에** 돌리는 세 파일 중 하나다. 배치 러너에는 브라우저가
#    없다. 여기에 브라우저 검사를 섞어 두면 관문이 브라우저에 의존하게 되고,
#    그러면 화면과 아무 상관 없는 이유로 **그날 장부가 아예 안 남는다.**
#    2026-08-17 밤에 실제로 그렇게 멈췄다. 관문은 가볍고 장부만 봐야 한다.

def test_the_flag_block_reads_those_fields_from_the_record():
    """①  경고를 만드는 자리가 **기록에서** 읽는가."""
    blk = INDEX.split("const flags=[]", 1)[1].split("side-flags", 1)[0]
    for field, why in (
            ("lot_priority", "예산을 끌어 쓴 사실"),
            ("bar_age_days", "묵은 봉으로 판단한 시장"),
            ("stale_marks", "묵은 가격으로 평가한 종목")):
        assert f"pfLast.{field}" in blk, (
            f"{why}을 기록에서 읽지 않는다 — 그 경고는 영영 안 뜬다. "
            "(낱말이 파일 어딘가에 남아 있는 것과 화면에 나오는 것은 다르다)")


def test_the_cash_card_reads_the_net_exposure_from_the_record():
    """②  '돈이 지금 어디 있나' 카드가 순노출을 **기록에서** 읽는가.

    합계(weight)만 말하면 파는 쪽이 켜진 날 화면은 실제로 시장에 걸린 것과
    다른 크기의 위험을 보여준다. 행동(정말 화면에 나오는가)은 브라우저 짝
    `tests/test_the_screen_says_who_took_the_budget.py`가 본다.
    """
    # 같은 문구가 HTML 뼈대(카드 자리)에도 있다 — 그리는 코드는 마지막 것이다.
    blk = INDEX.rsplit("돈이 지금 어디 있는가", 1)[1].split("side-cash", 1)[0]
    assert "pfLast.net_weight" in blk, (
        "순노출을 기록에서 읽지 않는다 — 롱·숏이 섞인 날 화면은 합계만 "
        "말하고, 읽는 사람은 실제와 다른 크기의 위험을 본다")
