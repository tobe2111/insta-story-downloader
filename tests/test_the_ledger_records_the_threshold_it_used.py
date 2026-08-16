"""장부가 **아무도 넘은 적 없는 문턱**을 적고 있었다 (감사 258).

야간 오디션은 선발전(선별)과 결승전(판정) 두 단계입니다. 다중검정 보정은
후보 수에 비례해 문턱을 올리는데, 그 값이 결승 문턱보다 엄격하면 결승전이
정의상 아무것도 거를 수 없습니다 — 그래서 코드는 선발 문턱을 결승 문턱까지
**내려서** 돌립니다. 그 조정 자체는 옳습니다.

틀린 것은 **기록**이었습니다. 조정은 오디션 함수 안에서만 일어났고,
장부와 콘솔은 **조정 전 값**을 적었습니다:

    기록·화면   선발 t≥2.52     ← 175/175건 전부. 아무도 넘은 적 없는 숫자
    실제 적용   선발 t≥1.03

실측(2026-08-16, 스냅샷으로 진짜 오디션 실행):

    us_stock:SPY   선발전 t=2.39로 통과 → 승격    ← 2.52를 못 넘었는데 통과
    us_stock:QQQ   선발전 t=1.63으로 통과 → 승격

"왜 챔피언이 안 바뀌나"를 2.52로 판단하면 답이 통째로 어긋납니다. 그리고
같은 계산을 두 곳에서 하면 언젠가 갈라지므로, **판정하는 곳을 하나로**
두고 오디션·장부·화면이 그 함수를 함께 읽게 했습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.retrain import effective_select_t  # noqa: E402


# ── 조정 규칙 자체 ────────────────────────────────────────────

def test_a_screen_stricter_than_the_final_is_lowered():
    """선별기가 자기가 먹여 살리는 검정보다 엄격하면 그 검정은 죽는다."""
    assert effective_select_t(2.52, 1.03) == pytest.approx(1.03)


def test_a_screen_looser_than_the_final_is_left_alone():
    """대조군 — 늘 내리면 조정이 아니라 그냥 무시다."""
    assert effective_select_t(0.8, 1.03) == pytest.approx(0.8)


def test_equal_thresholds_are_untouched():
    assert effective_select_t(1.03, 1.03) == pytest.approx(1.03)


def test_the_old_gate_is_still_reproducible():
    """옛 결정(gate_version 1)은 옛 규칙으로 재현돼야 한다 — 과거를 안 고친다."""
    assert effective_select_t(2.52, 1.03, clamp_screen=False) == pytest.approx(2.52)


# ── 장부·화면이 실제로 쓴 값을 적는가 ─────────────────────────

def test_the_ledger_writes_the_used_threshold():
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"select_t_used": round(effective_select_t(' in src, (
        "장부가 실제 적용 문턱을 안 적는다")


def test_the_console_prints_the_used_threshold():
    """매일 화면에 찍히는 숫자가 틀리면 매일 잘못 판단한다."""
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "select_t_used = effective_select_t(" in src
    assert "t≥{select_t_used:.2f}" in src, "콘솔이 아직 조정 전 값을 찍는다"


def test_only_one_place_decides():
    """같은 판정을 두 곳에서 하면 언젠가 갈라진다.

    조정 규칙(`select_t > confirm_t`)이 함수 밖에도 있으면 그 순간부터
    장부와 오디션이 다른 문턱을 말할 수 있다.
    """
    import re

    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    body = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    body = re.sub(r'"""(?:.|\n)*?"""', "", body)
    hits = re.findall(r"select_t\s*>\s*confirm_t", body)
    assert len(hits) == 1, f"조정 판정이 {len(hits)}곳에 있다 — 하나여야 한다"


def test_the_audition_uses_what_the_function_says(tmp_path):
    """함수가 말하는 값과 오디션이 실제로 쓴 값이 같은가 — 끝까지 돌려 본다."""
    import pandas as pd

    from quant.live.retrain import nightly_retrain
    from quant.strategies.base import Strategy

    class _Fixed(Strategy):
        name = "fixed"

        def __init__(self, level):
            self.level = level

        def generate_signals(self, df):
            s = pd.Series(self.level, index=df.index)
            return self._finalize(s, df.index)

    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    close = pd.Series([100 + i * 0.05 + (i % 7) * 0.3 for i in range(400)],
                      index=idx, dtype=float)
    df = pd.DataFrame({"open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close,
                       "volume": 1000.0}, index=idx)

    # 선발 문턱을 터무니없이 높게 요청한다. 조정이 살아 있으면 결승 문턱까지
    # 내려가 후보가 선발전을 통과할 수 있다.
    d = nightly_retrain(df, {"strategy": "fixed", "params": {"level": 0.5}},
                        [{"level": 1.0}],
                        build=lambda s: _Fixed(s["params"]["level"]),
                        confirm_window=120, select_t=99.0, confirm_t=0.0)
    assert effective_select_t(99.0, 0.0) == 0.0
    # 조정이 없었다면 t=99를 넘을 후보가 없어 '이긴 후보 없음'으로 끝난다.
    assert "이긴 후보 없음" not in d["reason"], (
        f"조정이 안 걸렸다 — 선발전이 99.0으로 돌았다: {d['reason']}")
