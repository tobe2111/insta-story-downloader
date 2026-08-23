"""트랙 페이지 실시간 평가 — "마지막 회차 기준"만 떠 있던 문제 (2026-08-23).

사장님: "홈페이지에 계속 마지막 회차 기준이라고 떠있는데 실시간으로 자산이
얼마인지 계속 볼 수 있게 가능해? 모든 투자페이지들 말이야." / "각 종목들
가격은 계속 변동이 있을텐데 그 종목들과 자산 모두 실시간이 가능하냐는거지."

홈(100만)은 이미 준실시간 참고 평가가 있었고, 트랙 페이지 셋(코인 단타·
미국 단타·코인 선물)은 회차 확정값만 보여주고 있었다. assets/track-live.js
한 곳이 셋을 모두 흘린다.

지켜야 할 약속:
- 실시간 값은 **참고**다 — 확정 기록(수익률·판정·곡선)을 덮지 않는다.
- 전부 값이 있을 때만 합계 — 일부만 더한 합계는 계좌를 실제보다 작게
  보이게 한다. 못 받은 종목은 이름을 말한다.
- 숏은 가격이 오르면 잃는다(부호 수량).
- '지금'이라는 말은 실시간 줄에만 쓴다(감사 299 — 확정값을 '지금'이라
  부르면 같은 화면의 두 숫자가 다 '지금'이 된다).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
TRACKS = ["intraday.html", "us.html", "futures.html"]


def test_the_calculation_actually_computes():
    """돈이 걸린 식은 값으로 확인한다 — node 하네스 실행(감사 229의 교훈)."""
    import shutil
    import subprocess

    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        import pytest
        pytest.skip("node 없음 — 평가 계산 실행 검사 생략")
    r = subprocess.run([node, str(ROOT / "tests" / "track_live_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_every_track_page_wires_the_live_layer():
    for name in TRACKS:
        src = (DOCS / name).read_text("utf-8")
        assert 'src="assets/track-live.js"' in src, (
            f"{name}: 실시간 모듈을 싣지 않는다")
        assert 'id="tl-line"' in src, f"{name}: 실시간 줄이 들어갈 자리가 없다"
        assert "TrackLive.start(" in src, f"{name}: 실시간 흐름을 시작하지 않는다"
        i = src.find("assets/track-live.js")
        j = src.find("TrackLive.start(")
        assert 0 < i < j, f"{name}: 모듈을 쓰는 곳보다 뒤에서 싣는다"


def test_the_confirmed_number_is_no_longer_called_now():
    """확정값의 라벨에서 '지금'을 뗐는가 — '지금'은 실시간 줄의 말이다."""
    for name in ("intraday.html", "us.html"):
        src = (DOCS / name).read_text("utf-8")
        assert "지금 (마지막 회차 기준)" not in src, (
            f"{name}: 확정값이 여전히 '지금'을 자칭한다")
        assert "마지막 회차 확정" in src, f"{name}: 확정 라벨이 사라졌다"


def test_the_module_keeps_its_honesty_promises():
    src = (DOCS / "assets" / "track-live.js").read_text("utf-8")
    # ① 참고임을 말하고, 판정에 안 쓴다고 말한다
    assert "실시간 참고" in src and "확정 기록만" in src
    # ② 부분 수신이면 합계를 지어내지 않는다
    assert "합계는 표시하지 않습니다" in src
    assert "complete ? Number(equity) + delta : null" in src, (
        "부분 수신에서도 합계를 내는 코드로 바뀌었다")
    # ③ 숏 부호
    assert 'h.direction === "short" ? -q : q' in src
    # ④ 시세 소스 — 코인은 거래소 직결, 주식은 워커 프록시
    assert "api.binance.com" in src and "/api/quotes" in src


def test_the_live_layer_never_rewrites_the_ledger_numbers():
    """모듈이 큰 확정 숫자(.big)를 만지지 않는다 — tl-line·표 주석만 산다."""
    src = (DOCS / "assets" / "track-live.js").read_text("utf-8")
    assert ".big" not in src and "innerText" not in src.replace(
        "lineEl.innerHTML", ""), "모듈이 확정 표시 영역을 건드린다"
    assert "tl-live" in src, "표 주석은 별도 요소로 덧붙여야 한다(덮지 않는다)"
