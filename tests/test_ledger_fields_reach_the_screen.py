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

import functools
import http.server
import json
import re
import shutil
import socketserver
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _browser import block_external, chrome_exe  # noqa: E402

CHROME = chrome_exe()

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




# ── 문자열이 아니라 **화면**으로 확인한다 (감사 278) ────────────
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
#    그래서 ① 값을 정말 기록에서 읽는지(구조)와 ② 읽은 값이 정말 화면에
#    나오는지(행동)를 둘 다 본다. ①만 있으면 배선이 끊겨도 모르고,
#    ②만 있으면 브라우저가 없는 곳에서 조용히 건너뛴다.

# 실측 계좌 크기(2026-08-15) — 이 금액을 넘는 값은 화면이 일부러 감춘다.
_EQ = 997197.56

# 경고가 떠야 하는 하루 / 조용해야 하는 하루. 대조군이 없으면 "매일 뜨는
# 경고"가 되어도 모른다 — 매일 뜨는 경고는 꺼진 경고와 같다.
_LOUD = {"lot_priority": {"crypto:BTC/USDT": {"spent": 200000.0,
                                              "budget": 120000.0,
                                              "gave_way": ["kr_stock:069500"]}},
         "bar_age_days": {"us_stock": 3, "kr_stock": 0}}
_QUIET = {"lot_priority": None, "bar_age_days": {"us_stock": 0, "kr_stock": 1}}


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


def _serve(root: Path) -> tuple[str, socketserver.TCPServer]:
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _make_site(base: Path, name: str, patch: dict) -> Path:
    root = base / name
    shutil.copytree(DOCS, root, dirs_exist_ok=True)
    st = json.loads((DOCS / "status.json").read_text("utf-8"))
    pf = st["paper"]["portfolio:ALL"]
    pf["equity"], pf["principal"], pf["start_cash"] = _EQ, 1_000_000.0, 1_000_000.0
    rec = pf["history"][-1]
    rec["equity"] = _EQ
    # ⚠️ 계좌 안에 들어오는 금액만 쓴다 — 넘으면 화면이 '못 믿을 값'으로
    #    따로 처리하고(감사 273) 이 경고 자체가 안 뜬다.
    for k, v in patch.items():
        if v is None:
            rec.pop(k, None)
        else:
            rec[k] = v
    (root / "status.json").write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    return root


@pytest.fixture(scope="module")
def _flags(tmp_path_factory):
    """두 하루(시끄러운 날·조용한 날)의 사이드바 경고 전문.

    ⚠️ playwright 동기 API는 한 프로세스에 **하나의 드라이버 루프**만
       허용한다. 검사마다 sync_playwright()를 열면 두 번째가 "이미 도는
       루프" 오류로 죽는다 — 한 번 열고 두 페이지를 본다.
    """
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    if not Path(CHROME).exists():
        pytest.skip("chromium 없음 — 화면 검사 생략")
    from playwright.sync_api import sync_playwright

    base = tmp_path_factory.mktemp("fields")
    urls, servers, out = {}, [], {}
    for name, patch in (("loud", _LOUD), ("quiet", _QUIET)):
        url, srv = _serve(_make_site(base, name, patch))
        urls[name], _ = url, servers.append(srv)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)
            try:
                for name, url in urls.items():
                    pg = b.new_page(viewport={"width": 1440, "height": 900})
                    block_external(pg)
                    errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    pg.goto(f"{url}/index.html")
                    pg.wait_for_timeout(2400)
                    pg.click("#morebtn")     # 자세히 보기 — 상태 경고까지 편다
                    pg.wait_for_timeout(200)
                    out[name] = pg.locator("#side-flags").inner_text()
                    assert not errs, f"{name}: 스크립트가 던졌다 — {errs}"
                    pg.close()
            finally:
                b.close()
        yield out
    finally:
        for srv in servers:
            srv.shutdown()


def test_the_screen_says_who_took_the_budget(_flags):
    """'못 샀다'만 말하고 '그 돈은 누가 가져갔나'를 감추면 절반만 밝힌 것이다."""
    txt = _flags["loud"]
    assert "예산을 끌어 쓴 종목" in txt, f"예산을 끌어 쓴 사실이 화면에 없다:\n{txt}"
    assert "BTC/USDT" in txt or "비트코인" in txt, f"어느 종목인지가 없다:\n{txt}"
    assert "자리를 내줬습니다" in txt, f"대신 밀려난 종목을 말하지 않는다:\n{txt}"


def test_the_screen_says_it_judged_on_a_stale_bar(_flags):
    """묵은 봉으로 낸 판단은 다른 시장과 같은 날로 비교할 수 없다."""
    txt = _flags["loud"]
    assert "묵은 봉으로 판단" in txt, f"묵은 봉으로 판단한 시장이 화면에 없다:\n{txt}"
    assert "us_stock 3일 전 봉" in txt, f"어느 시장이 며칠 묵었는지가 없다:\n{txt}"


def test_a_fresh_and_full_day_says_neither(_flags):
    """대조군 — 정상인 날에 이 경고가 뜨면 매일 울리는 배경음이 된다."""
    txt = _flags["quiet"]
    assert "예산을 끌어 쓴 종목" not in txt, f"끌어 쓴 적 없는데 경고가 뜬다:\n{txt}"
    assert "묵은 봉으로 판단" not in txt, f"최신 봉인데 묵었다고 한다:\n{txt}"
