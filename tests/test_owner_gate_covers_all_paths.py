"""주문을 내는 **모든** 경로가 사장님의 전역 스위치를 지나는가 (감사 83).

`trading_paused`는 설정 문서에 "신규 매매 중단"이라 적힌 소유자 스위치다.
그런데 이 규칙이 실행 경로마다 따로 적혀 있었고, 결과는 이랬다:

    daily.py        ✅ 읽음
    daily_live.py   ✅ 읽음
    webhook.py      ❌ (감사 82에서 고침)
    engine.py       ❌  ← quant live --real
    multi.py        ❌  ← quant live --real (다종목)
    autolearn.py    ❌

즉 사장님이 대시보드에서 '일시정지'를 눌러 두어도 `quant live --real`은
계속 주문을 냈다. **스위치를 누른 사람은 멈췄다고 믿는다.**

같은 규칙을 여러 곳에 적으면 반드시 한 곳이 뒤처진다(오늘 1번 교훈).
그래서 판정은 `quant.utils.settings.owner_gate()` 한 곳에만 두고, 여기서
**주문 경로를 열거해** 전부 그 문을 지나는지 확인한다. 새 경로가 생기면
이 검사가 먼저 빨개진다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.utils.settings import DEFAULTS, owner_gate      # noqa: E402

QUANT = ROOT / "quant"

# 이 문을 지나지 않아도 되는 파일과 그 이유. 면제는 **이유와 함께만** 준다.
EXEMPT = {
    # 브로커 구현 자신 — 주문을 '결정'하지 않고 '실행'만 한다.
    "quant/broker/paper.py": "브로커 구현(결정하지 않음)",
    "quant/broker/retry.py": "브로커 래퍼(결정하지 않음)",
    "quant/broker/us_live.py": "브로커 구현(결정하지 않음)",
    "quant/broker/kr_live.py": "브로커 구현(결정하지 않음)",
    "quant/broker/crypto_live.py": "브로커 구현(결정하지 않음)",
    "quant/broker/base.py": "인터페이스",
}

# 문을 지나는 것으로 인정하는 표식(단일 구현을 쓰거나 설정을 직접 읽거나).
GATE_MARKERS = ("owner_gate", "trading_paused")


def _order_placing_files() -> dict[str, str]:
    """`broker.target_weight(...)`을 부르는 파일 → 그 파일 내용."""
    out = {}
    for p in sorted(QUANT.rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding="utf-8")
        # 정의가 아니라 **호출**만 센다
        calls = re.findall(r"(?<!def )\w+\.target_weight\s*\(", text)
        if calls:
            out[rel] = text
    return out


ORDER_FILES = _order_placing_files()


def test_the_sweep_actually_finds_the_order_paths():
    """열거가 비면 아래 검사들이 조용히 전부 통과한다."""
    assert len(ORDER_FILES) >= 5, sorted(ORDER_FILES)
    for must in ("quant/live/daily.py", "quant/live/multi.py",
                 "quant/live/engine.py", "quant/live/webhook.py"):
        assert must in ORDER_FILES, f"{must} 가 주문 경로 목록에서 빠졌다"


@pytest.mark.parametrize("rel", sorted(ORDER_FILES))
def test_every_order_path_consults_the_owner_switch(rel):
    """새 주문 경로가 생기면 여기서 먼저 막힌다.

    면제하려면 EXEMPT에 **이유와 함께** 적어야 한다 — 조용히 빠져나갈 수
    없게 하는 것이 목적이다.
    """
    if rel in EXEMPT:
        pytest.skip(f"면제: {EXEMPT[rel]}")
    text = ORDER_FILES[rel]
    assert any(m in text for m in GATE_MARKERS), (
        f"{rel} 이 주문을 내면서 사장님의 전역 스위치를 읽지 않는다 — "
        "'일시정지'를 눌러도 이 경로는 계속 주문한다")


def test_exemptions_still_exist():
    """면제 목록에 사라진 파일이 남아 있으면 착각을 만든다."""
    stale = [f for f in EXEMPT if not (ROOT / f).exists()]
    assert not stale, f"없는 파일을 면제하고 있다: {stale}"


# ── 단일 구현이 실제로 옳은가 ───────────────────────────────────

def test_gate_reads_the_switches(tmp_path):
    import json
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"trading_paused": True, "exposure_scale": 0.3}),
                 encoding="utf-8")
    paused, scale = owner_gate(str(p))
    assert paused is True and scale == pytest.approx(0.3)


def test_gate_clamps_a_nonsense_scale(tmp_path):
    import json
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"exposure_scale": 7.5}), encoding="utf-8")
    _paused, scale = owner_gate(str(p))
    assert scale == 1.0, "노출 배수가 1을 넘어 레버리지가 된다"

    p.write_text(json.dumps({"exposure_scale": -2.0}), encoding="utf-8")
    _paused, scale = owner_gate(str(p))
    assert scale == 0.0, "음수 배수가 방향을 뒤집는다"


def test_missing_settings_do_not_stop_trading(tmp_path):
    """설정 파일이 없는 것이 정상 상태다 — 그걸로 매매를 막으면 안 된다."""
    paused, scale = owner_gate(str(tmp_path / "does_not_exist.json"))
    assert paused is False and scale == 1.0


def test_broken_settings_do_not_stop_trading(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{{{ 깨진 파일", encoding="utf-8")
    paused, scale = owner_gate(str(p))
    assert paused is False and scale == 1.0


def test_the_switches_are_declared_in_defaults():
    """DEFAULTS에 없는 키는 코드가 아무리 읽어도 항상 None이다(과거 결함)."""
    assert "trading_paused" in DEFAULTS and "exposure_scale" in DEFAULTS
