"""내 전략 고정(pin) — 전략은 사용자의 것, 브레이크는 우리의 것.

설치형 사용자는 자기 계좌에서 심사와 무관하게 자기 전략으로 매매할 수
있어야 한다(자기 돈에는 자기 전략을 쓸 권리가 있다). 단:

  ① 고정은 **확인 문구를 그대로 타이핑**해야만 된다 — 클릭 한 번의
     '확인'과 문장을 옮겨 적는 것은 다른 행동이다.
  ② 고정하면 신호는 그 전략이 내지만, **크기 결정(브레이크)은 그대로다**
     — 고정 모듈에 사이징 코드가 생기는 순간 브레이크를 우회할 길이 생긴다.
  ③ 고정 파일이 없으면 **아무것도 달라지지 않는다** — 우리 공개 실험
     계좌는 심사 결과만 따른다.
  ④ 고정된 전략은 **얼려진 사본**이다 — 자료 폴더를 나중에 고쳐도 고정은
     그대로(결정의 전제는 결정과 함께 보존한다).
  ⑤ 깨진 고정 파일은 '고정 없음'으로 조용히 넘기지 않는다 — 사용자는
     자기 전략이 돌고 있다고 믿는데 실제로는 다른 것이 돈다.
  ⑥ 고정 사실이 화면(status)에 남는다 — 아니면 그 성적이 시스템 심사의
     결과처럼 읽힌다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import pin as P  # noqa: E402

SPEC = {
    "name": "내전략",
    "version": 1,
    "entry": [{"left": "sma:5", "op": "cross_above", "right": "sma:20",
               "quote": "5일선이 20일선을 위로 돌파하면 산다"}],
    "exit": [{"left": "sma:5", "op": "cross_below", "right": "sma:20",
              "quote": "아래로 돌파하면 판다"}],
    "source": {"kind": "text", "ref": "테스트"},
}


def _install_spec(state_dir: Path) -> None:
    d = state_dir / "specs_user"
    d.mkdir(parents=True, exist_ok=True)
    (d / "내전략.json").write_text(json.dumps(SPEC, ensure_ascii=False),
                                   "utf-8")


# ── ① 확인 문구 없이는 고정되지 않는다 ─────────────────────────

def test_a_pin_requires_the_exact_ack_phrase(tmp_path):
    _install_spec(tmp_path)
    with pytest.raises(ValueError):
        P.save_pin("crypto", "BTC/USDT", "내전략", "네 알겠습니다",
                   state_dir=str(tmp_path))
    assert P.load_pins(str(tmp_path)) == {}, "틀린 문구로도 고정됐다"
    P.save_pin("crypto", "BTC/USDT", "내전략", P.ACK_PHRASE,
               state_dir=str(tmp_path))
    assert "crypto:BTC/USDT" in P.load_pins(str(tmp_path))


def test_the_cli_makes_the_user_type_it(tmp_path):
    """CLI가 문구를 미리 채워 주면 이 장치는 장식이 된다."""
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    seg = src[src.index("def _cmd_pin"):src.index("def _cmd_unpin")]
    assert "input(" in seg, "고정 확인이 타이핑 없이 지나간다"
    assert "scorecard" in seg, "성적표를 안 보여주고 고정을 받는다"
    assert "save_pin(" in seg and "typed" in seg, (
        "타이핑한 문구가 아니라 다른 값으로 고정한다")


# ── ② 신호만 바꾸고 크기에는 손대지 않는다 ────────────────────

def test_the_pin_module_contains_no_sizing_code():
    src = (ROOT / "quant" / "live" / "pin.py").read_text("utf-8")
    body = src.split('"""', 2)[-1]
    for banned in ("vol_scale", "_kill_switch", "exposure", "risk_scale",
                   "weight"):
        assert banned not in body, (
            f"고정 모듈에 크기 결정 코드({banned})가 있다 — 여기가 브레이크를 "
            "우회하는 뒷문이 된다")


def test_a_pinned_symbol_still_passes_through_the_same_sizing_path():
    """고정은 champion_spec/champion_strategy(신호의 출처)에서만 갈린다.

    daily.py의 크기 결정 경로가 고정 여부를 **모르게** 유지돼야, 브레이크가
    전략을 가리지 않고 걸린다는 문장이 구조로 보장된다.
    """
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    # 크기 결정 함수들 근처에서 pinned를 참조하면 안 된다
    for fn in ("_kill_switch_scale", "vol_scale", "validation_damp"):
        for i, ln in enumerate(src.splitlines()):
            if fn in ln and "pin" in ln.lower():
                raise AssertionError(
                    f"크기 결정({fn})이 고정 여부를 본다: {ln.strip()}")


# ── ③ 고정이 없으면 아무 일도 없다 ────────────────────────────

def test_no_pin_file_means_no_change(tmp_path):
    from quant.live.retrain import champion_spec
    spec = champion_spec("crypto", "BTC/USDT", state_dir=str(tmp_path))
    assert spec["strategy"] != "spec", "고정이 없는데 spec 전략이 나온다"


def test_our_public_account_has_no_pins():
    """사실 고정 — 공개 실험 계좌에 고정이 생기면 그날부터 성적의 의미가
    바뀐다. 만약 이 검사가 실패했다면 그 변화를 알고 한 것인지 물어야 한다."""
    assert P.load_pins(str(ROOT / "state")) == {}, (
        "공개 실험 계좌(state/)에 사용자 고정이 있다 — 이 계좌의 성적은 "
        "'심사를 통과한 전략만 쓴다'는 전제로 공개되고 있다")


# ── 고정이 실제로 신호의 출처를 바꾸는가 ───────────────────────

def test_a_pin_overrides_the_champion(tmp_path):
    _install_spec(tmp_path)
    P.save_pin("crypto", "BTC/USDT", "내전략", P.ACK_PHRASE,
               state_dir=str(tmp_path))
    from quant.live.retrain import champion_spec
    spec = champion_spec("crypto", "BTC/USDT", state_dir=str(tmp_path))
    assert spec["strategy"] == "spec"
    assert spec["params"]["spec"]["name"] == "내전략"


def test_a_pinned_strategy_actually_generates_signals(tmp_path):
    """문자열이 아니라 값으로 — 고정된 전략이 신호를 실제로 낸다."""
    _install_spec(tmp_path)
    P.save_pin("crypto", "BTC/USDT", "내전략", P.ACK_PHRASE,
               state_dir=str(tmp_path))
    from quant.live.retrain import champion_strategy
    strat = champion_strategy("crypto", "BTC/USDT", state_dir=str(tmp_path))
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    close = pd.Series(np.r_[np.linspace(100, 90, 30),
                            np.linspace(90, 120, 30)], index=idx)
    df = pd.DataFrame({"open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close, "volume": 1e6})
    sig = strat.generate_signals(df)
    assert float(sig.abs().sum()) > 0, "고정된 전략이 신호를 하나도 못 낸다"


def test_a_pin_beats_the_parliament_too(tmp_path):
    """의회(혼합 전략)가 있어도 고정이 이겨야 한다.

    핫리로드 경로(_refresh)는 의회를 champion_spec보다 먼저 보므로, 고정
    검사가 거기 없으면 **의회가 사용자 전략을 희석한다** — "내 전략으로
    매매"가 조용히 거짓말이 된다.
    """
    _install_spec(tmp_path)
    P.save_pin("crypto", "BTC/USDT", "내전략", P.ACK_PHRASE,
               state_dir=str(tmp_path))
    (tmp_path / "champions.json").write_text(json.dumps({
        "crypto:BTC/USDT": {
            "strategy": "ml", "params": {}, "promotions": 0,
            "parliament": [
                {"strategy": "ml", "params": {}, "weight": 0.5},
                {"strategy": "ma_cross",
                 "params": {"fast": 5, "slow": 20}, "weight": 0.5},
            ]}}, ensure_ascii=False), "utf-8")
    from quant.live.retrain import champion_strategy
    strat = champion_strategy("crypto", "BTC/USDT", state_dir=str(tmp_path))
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    close = pd.Series(np.r_[np.linspace(100, 90, 30),
                            np.linspace(90, 120, 30)], index=idx)
    df = pd.DataFrame({"open": close, "high": close * 1.01,
                       "low": close * 0.99, "close": close, "volume": 1e6})
    strat.generate_signals(df)
    impl = strat._impl
    assert type(impl).__name__ != "ParliamentStrategy", (
        "고정했는데 의회가 신호를 낸다 — 사용자 전략이 희석되고 있다")
    assert strat._spec and strat._spec.get("strategy") == "spec", strat._spec


def test_unpin_restores_the_system_champion(tmp_path):
    _install_spec(tmp_path)
    P.save_pin("crypto", "BTC/USDT", "내전략", P.ACK_PHRASE,
               state_dir=str(tmp_path))
    assert P.remove_pin("crypto", "BTC/USDT", state_dir=str(tmp_path))
    from quant.live.retrain import champion_spec
    assert champion_spec("crypto", "BTC/USDT",
                         state_dir=str(tmp_path))["strategy"] != "spec"
    assert not P.remove_pin("crypto", "BTC/USDT", state_dir=str(tmp_path))


# ── ④ 고정은 얼려진 사본이다 ──────────────────────────────────

def test_editing_the_spec_folder_does_not_change_a_pin(tmp_path):
    _install_spec(tmp_path)
    P.save_pin("crypto", "BTC/USDT", "내전략", P.ACK_PHRASE,
               state_dir=str(tmp_path))
    changed = dict(SPEC)
    changed["entry"] = [{"left": "sma:3", "op": "cross_above",
                         "right": "sma:60", "quote": "바뀐 규칙"}]
    (tmp_path / "specs_user" / "내전략.json").write_text(
        json.dumps(changed, ensure_ascii=False), "utf-8")
    spec = P.pinned_spec("crypto", "BTC/USDT", state_dir=str(tmp_path))
    assert spec["params"]["spec"]["entry"][0]["left"] == "sma:5", (
        "자료 폴더를 고치자 고정된 전략이 조용히 바뀌었다 — 결정의 전제는 "
        "결정과 함께 보존해야 한다")


# ── ⑤ 깨진 고정 파일은 침묵하지 않는다 ────────────────────────

def test_a_corrupt_pin_file_stops_instead_of_silently_unpinning(tmp_path):
    (tmp_path / "pins.json").write_text("{깨진 json", "utf-8")
    with pytest.raises(RuntimeError):
        P.load_pins(str(tmp_path))


# ── ⑥ 고정 사실이 화면에 남는다 ───────────────────────────────

def test_the_status_page_declares_pins():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["pins"]' in src, (
        "고정 사실이 화면에 안 나간다 — 사용자 지정 전략의 성적이 시스템 "
        "심사의 결과처럼 읽힌다")


def test_the_scorecard_admits_what_it_does_not_know(tmp_path):
    _install_spec(tmp_path)
    lines = "\n".join(P.scorecard("crypto", "BTC/USDT", "내전략",
                                  state_dir=str(tmp_path)))
    assert "기록 없음" in lines, "오디션 기록이 없는데 있는 척한다"
    assert "심사를 통과하지 않았습니다" in lines
    assert "브레이크" in lines or "킬스위치" in lines
