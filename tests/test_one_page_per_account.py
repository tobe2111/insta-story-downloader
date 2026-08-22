"""계좌가 넷이면 페이지도 넷이다 (감사 305).

사장님 지시(2026-08-22): *"100만원 투자 1페이지, 코인투자 1페이지, 선물투자
1페이지, 미국주식 1페이지 이렇게 나누자고. 지금은 막 섞여있어."*

맞는 지적이었다. 코인 트랙과 미국주식 트랙이 **한 페이지 안에** 있었다
(intraday.html). 그러면 읽는 사람은 화면의 숫자를 볼 때마다 "이건 어느
계좌 것인가"를 먼저 골라내야 한다. 두 계좌는 통화도 다르고(USDT / USD)
장 여는 시간도 다르고 시드도 따로인데, 그 사실이 화면 배치에는 안 드러나
있었다.

■ 여기서 지키는 것

  · 트랙마다 **자기 페이지**가 있다.
  · 각 페이지는 **자기 장부 파일만** 읽는다. 남의 장부를 읽기 시작하면
    한 페이지에 두 계좌가 다시 섞이고, 그때부터 어느 숫자가 어느 계좌
    것인지 코드를 열어야 알 수 있다.
  · 상단 바에서 넷이 **나란히** 보인다 — 어디로 가면 무엇이 있는지가
    한눈에 읽혀야 한다.
  · 페이지끼리 서로를 가리킨다 — 상단 바만으로는 "이 넷이 형제"라는
    관계가 안 읽힌다.

⚠️ 이 검사는 '섞이지 않았다'만 보지 않는다. **넷이 다 살아 있는지**도
   함께 본다(대조군). 그게 없으면 "페이지를 세 개 지운다"도 통과한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 트랙 → (페이지, 그 페이지가 읽어야 할 장부, 화면에 있어야 할 말)
TRACKS = {
    "100만 챌린지": ("index.html", "status.json", "100만"),
    "코인 단타": ("intraday.html", "intraday.json", "코인"),
    "미국주식 단타": ("us.html", "intraday_us.json", "미국"),
    "선물 양방향": ("futures.html", "futures.json", "선물"),
}

# 실험 트랙의 장부들. 실험 페이지가 **다른 실험**의 장부를 읽으면 한
# 페이지에 두 계좌가 섞인 것이다 — 사장님이 "막 섞여있어"라고 하신 상태.
_EXPERIMENT_LEDGERS = {"intraday.json", "intraday_us.json", "futures.json"}

# ⚠️ 본 계좌 장부(status.json)는 예외다. 실험 페이지가 이것을 읽는 것은
#    **비교**이지 섞임이 아니다 — "이 실험이 본 계좌보다 나은가"가 실험의
#    질문 자체이므로, 같은 기간 % 수익률을 나란히 놓는 칸이 있다.
#    다만 비교라고 **말하는 경우에만** 예외다. 말없이 본 계좌 숫자를
#    끌어다 쓰면 그건 다시 섞임이고, 읽는 사람은 그 숫자가 이 실험 것인 줄
#    안다. 그래서 아래 검사가 그 라벨을 함께 요구한다.
_BENCHMARK_LEDGER = "status.json"


def _text(page: str) -> str:
    return (DOCS / page).read_text("utf-8")


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_each_track_has_its_own_page(track):
    """대조군 — 넷이 다 있어야 한다.

    없으면 "페이지를 지워서 안 섞이게 했다"도 아래 검사를 통과한다.
    """
    page = TRACKS[track][0]
    assert (DOCS / page).exists(), f"{track} 페이지({page})가 없다"


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_a_page_reads_only_its_own_ledger(track):
    """**이 파일의 핵심.** 자기 장부만 읽는다.

    코인 페이지가 미국 장부를 읽던 것이 사장님이 "막 섞여있어"라고 하신
    바로 그 상태다. 화면 문구는 언제든 다시 늘어날 수 있으므로, 문구가
    아니라 **어느 파일을 부르는가**로 잰다.
    """
    page, own, _ = TRACKS[track]
    src = _text(page)

    def _fetched(name):
        return re.search(r'fetch\(\s*["\']' + re.escape(name), src)

    others = {f for f in _EXPERIMENT_LEDGERS if f != own and _fetched(f)}
    assert not others, (
        f"{track} 페이지({page})가 다른 실험의 장부를 읽는다: {sorted(others)} — "
        "한 페이지에 두 계좌가 섞이면 어느 숫자가 어느 계좌 것인지 "
        "읽는 사람이 매번 골라내야 한다")
    # 본 계좌를 끌어다 쓰면서 라벨이 있는지는 **화면에서** 본다
    # (test_the_benchmark_column_says_it_is_a_benchmark) — 소스에서 찾으면
    # 주석에 적힌 같은 글자에 걸려 통과한다.


def test_the_coin_page_no_longer_carries_the_us_track():
    """실제로 갈라졌는지 — 이번에 옮긴 그 자리를 못박는다."""
    src = _text("intraday.html")
    assert "intraday_us.json" not in src, (
        "코인 페이지가 아직 미국 장부를 읽는다")
    assert 'id="us-sum"' not in src, (
        "코인 페이지에 미국주식 칸이 남아 있다")


def test_the_us_page_actually_carries_it():
    """대조군 — 떼어 낸 것이 **다른 페이지에 붙어 있어야** 한다.

    없으면 "미국주식 트랙을 통째로 지웠다"도 위 검사를 통과한다. 이
    저장소는 화면을 정리한다며 기록을 지운 적이 없다.
    """
    src = _text("us.html")
    assert "intraday_us.json" in src, "미국 페이지가 미국 장부를 안 읽는다"
    assert 'id="us-sum"' in src, "미국 페이지에 미국주식 칸이 없다"


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_the_navbar_lists_every_track(track):
    """상단 바에서 넷이 나란히 보인다."""
    nav = (DOCS / "assets" / "nav.js").read_text("utf-8")
    page = TRACKS[track][0]
    assert f'"{page}"' in nav, f"상단 바에 {track}({page}) 링크가 없다"
    assert f'"{track}"' in nav, f"상단 바의 {track} 이름이 다르다"


def test_the_four_tracks_come_first_and_in_order():
    """넷이 **앞에, 같은 차례로** 있어야 한다.

    순서가 흔들리면 "어디에 무엇이 있나"를 매번 다시 찾게 된다.
    """
    nav = (DOCS / "assets" / "nav.js").read_text("utf-8")
    order = [m for m in re.findall(r'\["([a-z_]+\.html)",', nav)]
    want = ["index.html", "intraday.html", "us.html", "futures.html"]
    assert order[:4] == want, f"트랙 넷이 앞에 나란히 있지 않다: {order[:6]}"


def test_nothing_was_hidden_while_tidying():
    """대조군 — 정리하면서 기존 페이지를 상단 바에서 떨어뜨리지 않았다.

    화면을 정리한다며 기록 하나가 조용히 사라지면 그건 정리가 아니다.
    """
    nav = (DOCS / "assets" / "nav.js").read_text("utf-8")
    for page in ("paper.html", "today.html", "trust.html", "weekly.html"):
        assert f'"{page}"' in nav, (
            f"{page}가 상단 바에서 사라졌다 — 페이지는 그대로 있는데 "
            "가는 길만 없어지면 없는 것과 같다")


@pytest.mark.parametrize("page", ["intraday.html", "us.html", "futures.html"])
def test_the_sibling_pages_point_at_each_other(page):
    """상단 바만으로는 '이 넷이 형제'라는 관계가 안 읽힌다."""
    src = _text(page)
    siblings = {"intraday.html", "us.html", "futures.html"} - {page}
    missing = [s for s in siblings if f'href="{s}"' not in src]
    assert not missing, (
        f"{page}가 형제 페이지를 안 가리킨다: {missing}")


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_each_page_says_which_account_it_is(track):
    """제목만 봐도 어느 계좌인지 알아야 한다."""
    page, _, word = TRACKS[track]
    src = _text(page)
    head = src[:src.index("</head>")] if "</head>" in src else src[:3000]
    assert word in head, (
        f"{page}의 머리말에 '{word}'가 없다 — 제목만 봐도 어느 계좌인지 "
        "알 수 있어야 한다")


@pytest.mark.parametrize("page", ["intraday.html", "us.html", "futures.html"])
def test_every_experiment_page_says_it_is_not_real_money(page):
    """세 실험 트랙 모두 가상 자금이라고 **먼저** 말해야 한다."""
    src = _text(page)
    assert "실제 돈이 아니" in src, f"{page}가 가상 자금임을 말하지 않는다"
    assert "수익을 보장하지 않습니다" in src, (
        f"{page}에 수익 비보장 문구가 없다")


# ── 화면에서 확인해야 하는 것 ──────────────────────────────────

def _render_heads(page: str) -> str:
    """그 페이지를 진짜로 그려서 제목들만 돌려준다.

    ⚠️ 소스에서 문자열을 찾으면 **주석에 적힌 같은 글자**에 걸려 통과한다.
       실제로 그랬다(감사 305) — 비교 칸의 제목을 지우는 변이가 주석 덕에
       살아남았다. 화면이 무엇을 말하는지는 화면에 물어야 한다.
    """
    import functools
    import http.server
    import shutil
    import socketserver
    import sys
    import threading
    pytest.importorskip("playwright.sync_api",
                        reason="playwright 없음 — 화면 검사 생략")
    sys.path.insert(0, str(ROOT / "tests"))
    from _browser import block_external, chromium_or_skip
    from playwright.sync_api import sync_playwright
    import tempfile

    site = Path(tempfile.mkdtemp()) / "site"
    shutil.copytree(DOCS, site, dirs_exist_ok=True)

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chromium_or_skip())
            pg = b.new_page(viewport={"width": 1280, "height": 1000})
            block_external(pg)
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/{page}")
            pg.wait_for_timeout(1800)
            heads = "\n".join(pg.locator("h1, h2").all_inner_texts())
            b.close()
    finally:
        srv.shutdown()
    return heads


def test_the_benchmark_column_says_it_is_a_benchmark():
    """본 계좌 숫자를 끌어다 쓰는 칸은 **비교라고 말해야** 한다.

    실험 페이지가 본 계좌 장부를 읽는 것 자체는 옳다 — "이 실험이 본 계좌
    보다 나은가"가 실험의 질문이기 때문이다. 다만 라벨이 없으면 읽는
    사람은 그 숫자를 **이 실험 성적**으로 읽는다. 그러면 다시 섞임이다.
    """
    heads = _render_heads("intraday.html")
    assert "본 계좌와 나란히" in heads, (
        f"본 계좌 숫자를 쓰면서 비교라고 말하는 제목이 화면에 없다:\n{heads}")


def test_the_futures_page_says_what_it_trades():
    """'선물'이라는 말만으로는 무엇을 사고파는지 알 수 없다 (감사 306).

    사장님 질문(2026-08-22): *"선물은 미국 주식이나 ETF로 하는거야?
    아니면 코인?"*

    화면이 답하지 않아서 나온 질문이다. 이 트랙은 **코인 무기한 선물**로
    돌고, 코인 단타 트랙과 **같은 다섯 종목**을 쓴다 — 그래야 "방향을 하나
    더 쓰면 나아지는가"라는 질문에서 방향 말고는 다 같게 둘 수 있다.
    종목까지 다르면 성적 차이가 무엇 때문인지 영영 모른다.
    """
    src = _text("futures.html")
    assert "코인 무기한 선물" in src, (
        "선물 페이지가 무엇으로 도는지 말하지 않는다 — 주식인지 코인인지 "
        "읽는 사람이 알 수 없다")
    assert "미국주식이나\nETF가 아니라" in src or "ETF가 아니라" in src, (
        "무엇이 **아닌지**를 함께 말하지 않는다 — '선물'은 주식·지수·원자재 "
        "선물을 먼저 떠올리게 하는 말이다")
