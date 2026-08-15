"""조종석이 화면에 쓰지 않은 조건으로 계산한다 (2026-08-14 감사 236).

같은 침묵이 두 군데 있었다. 둘 다 **형제 중 하나만 빠진** 모양이다.

① 민감도 스윕에 합성 데이터 경고가 없다
   실데이터를 못 받으면 이 저장소는 합성(가짜) 데이터로 폴백한다. 그
   사실을 화면에 띄우는 배너가 있고, 그 배너의 주석은 이렇게 적혀 있다 —
   "사용자가 가짜 데이터 백테스트를 진짜 성과로 믿게 된다. 이 제품에서
   가장 위험한 종류의 침묵이다."

   백테스트·포트폴리오·최적화·검증 넷은 전부 띄운다. **스윕만 없었다.**
   실측: 폴백 프레임을 넣으면 히트맵이 아무 경고 없이 그려졌다.

② 요청한 조건과 다른 조건으로 계산하고 말하지 않는다
   폼 입력은 조용히 범위 안으로 잘린다. 실측:

       요청: 봉 50 · IS창 10 · OOS창 5
       실제: 봉 200 · IS창 50 · OOS창 20
       화면: 아무 데도 없다 (검증 탭만 제목에 봉 수가 우연히 들어 있었다)

   자르는 것 자체는 옳다 — 50봉짜리 워크포워드는 숫자가 무의미하다.
   문제는 이 탭들이 **'이 파라미터를 신뢰해도 되는가'를 판정하는 과최적화
   검증 도구**라는 점이다. 판정의 전제가 화면에 없으면 판정을 검증할 수
   없다.

지키는 계약:
  · 데이터를 받아 결과를 그리는 탭은 **모두** 합성 폴백을 알린다
  · 화면은 **실제로 쓴 조건**을 적고, 요청과 다르면 그 사실도 적는다
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.web import app  # noqa: E402

SYNTH_MARK = "실데이터가 아닙니다"
BASE = {"market": "synthetic", "symbol": "DEMO", "strategy": "ma_cross"}


class _FakeProvider:
    """실데이터 수신에 실패해 합성으로 폴백한 상황을 흉내낸다."""

    def __init__(self, synthetic: bool):
        self.synthetic = synthetic

    def get_ohlcv(self, symbol, tf="1d", limit=800):
        n = int(limit)
        rng = np.random.default_rng(1)
        c = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n)))
        df = pd.DataFrame(
            {"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
             "volume": 1e9},
            index=pd.date_range("2023-01-01", periods=n, freq="D"))
        df.attrs["synthetic_fallback"] = self.synthetic
        return df


@pytest.fixture
def provider(monkeypatch):
    def _use(synthetic: bool):
        import quant.data as qd
        monkeypatch.setattr(qd, "get_provider",
                            lambda m: _FakeProvider(synthetic))
    return _use


def _text(html_str: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_str))


# 데이터를 받아 결과를 그리는 탭 전부. 새 탭이 생기면 여기 추가해야 한다.
TABS = {
    "백테스트": (app.run_backtest_html, {"limit": "400"}),
    "포트폴리오": (app.run_portfolio_html, {"symbols": "A,B", "limit": "400"}),
    "최적화": (app.run_optimize_html, {"limit": "800"}),
    "검증": (app.run_validate_html, {"limit": "800"}),
    "민감도 스윕": (app.run_sweep_html, {"limit": "800"}),
}


# ── ① 합성 데이터 경고 ────────────────────────────────────────

@pytest.mark.parametrize("name", list(TABS))
def test_every_tab_warns_about_synthetic_data(provider, name):
    """스윕만 빠져 있던 자리 — 다섯 형제가 같은 말을 해야 한다."""
    provider(True)
    fn, extra = TABS[name]
    out = fn({**BASE, **extra})
    assert SYNTH_MARK in out, f"{name}: 합성 데이터인데 경고가 없다"


@pytest.mark.parametrize("name", list(TABS))
def test_no_tab_cries_wolf_on_real_data(provider, name):
    """대조군 — 실데이터인데 경고가 뜨면 배너가 무의미해진다."""
    provider(False)
    fn, extra = TABS[name]
    out = fn({**BASE, **extra})
    assert SYNTH_MARK not in out, f"{name}: 실데이터인데 가짜라고 한다"


def test_the_tab_list_covers_every_data_fetching_page():
    """검사가 **아는 것만** 세면 완전성을 검사하지 못한다(이 저장소의 ㉞ 계열).

    소스에서 `get_provider(...).get_ohlcv(` 를 부르는 `run_*_html` 함수를
    찾아, 위 TABS가 그것들을 전부 덮는지 확인한다. 새 탭이 생기고 배너를
    빠뜨리면 여기서 걸린다.
    """
    import ast

    src = (Path(__file__).resolve().parent.parent
           / "quant" / "web" / "app.py").read_text("utf-8")
    tree = ast.parse(src)
    fetching = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name.startswith("run_")
                and node.name.endswith("_html")):
            continue
        body = ast.get_source_segment(src, node) or ""
        if "get_ohlcv(" in body:
            fetching.add(node.name)
    covered = {fn.__name__ for fn, _ in TABS.values()}
    assert fetching <= covered, (
        f"데이터를 받는 탭이 검사에 안 들어 있다: {sorted(fetching - covered)}")


# ── ② 실제로 쓴 조건 ──────────────────────────────────────────

CLAMPED = {
    "최적화": (app.run_optimize_html,
             {"limit": "50", "is_window": "10", "oos_window": "5"},
             ["봉 50→200", "IS창 10→50", "OOS창 5→20"]),
    "검증": (app.run_validate_html,
            {"limit": "50", "is_window": "10", "oos_window": "5"},
            ["봉 50→200", "IS창 10→50", "OOS창 5→20"]),
    "민감도 스윕": (app.run_sweep_html, {"limit": "50"}, ["봉 50→100"]),
}


@pytest.mark.parametrize("name", list(CLAMPED))
def test_a_clamped_input_is_disclosed(provider, name):
    """요청 50봉이 200봉이 됐으면 화면이 그렇게 말해야 한다."""
    provider(False)
    fn, params, expected = CLAMPED[name]
    t = _text(fn({**BASE, **params}))
    assert "실제 사용한 조건" in t, f"{name}: 조건 줄이 없다"
    for e in expected:
        assert e in t, f"{name}: '{e}' 가 화면에 없다 — {t[:200]}"


@pytest.mark.parametrize("name", list(CLAMPED))
def test_an_honoured_input_is_not_flagged_as_adjusted(provider, name):
    """대조군 — 안 자른 값까지 '조정했습니다'라고 하면 경고가 무뎌진다."""
    provider(False)
    fn, _, _ = CLAMPED[name]
    params = {"limit": "800", "is_window": "250", "oos_window": "125"}
    t = _text(fn({**BASE, **params}))
    assert "실제 사용한 조건" in t
    assert "조정했습니다" not in t, f"{name}: 안 잘랐는데 잘랐다고 한다"


# ── 자르는 함수 자체 ──────────────────────────────────────────

@pytest.mark.parametrize("raw,lo,hi,want_used,want_asked", [
    ("50", 200, 5000, 200, 50),        # 하한으로 올림
    ("9999", 200, 5000, 5000, 9999),   # 상한으로 내림
    ("800", 200, 5000, 800, 800),      # 그대로
    ("", 200, 5000, 800, 800),         # 빈 값 → 기본값
    ("abc", 200, 5000, 800, 800),      # 숫자가 아님 → 기본값
    ("  400 ", 200, 5000, 400, 400),   # 공백 허용
])
def test_bounded_param_reports_both_numbers(raw, lo, hi, want_used, want_asked):
    used, asked = app.bounded_param({"limit": raw}, "limit", 800, lo, hi)
    assert (used, asked) == (want_used, want_asked)


def test_bounded_param_without_an_upper_bound():
    """IS창·OOS창은 상한이 없다 — 데이터 길이 검사가 따로 잡는다."""
    assert app.bounded_param({"w": "99999"}, "w", 250, 50) == (99999, 99999)


def test_the_note_is_empty_when_there_is_nothing_to_say():
    assert app.conditions_note([]) == ""


def test_the_note_escapes_its_labels():
    """라벨이 화면에 그대로 들어가는 자리다 — 주입 경로를 막아 둔다."""
    out = app.conditions_note([("<script>x</script>", 1, 1)])
    assert "<script>" not in out and "&lt;script&gt;" in out
