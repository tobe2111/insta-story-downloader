"""끄려고 적은 글자가 켜는 결과를 냈다 (감사 195).

`config/settings.json`은 사장님이 어드민에서 바꾸고 **깃에 커밋되는** 파일이다.
즉 UI 말고 **사람이 직접 고치는 일이 실제로 있다.** 그런데 불린 값을 이렇게
읽었다.

    out["risk_override_ack"] = bool(raw.get("risk_override_ack", False))

파이썬에서 **비어 있지 않은 문자열은 전부 참**이다. 실측:

    risk_override_ack = "false"  →  True   ← 켜졌다
    risk_override_ack = "no"     →  True
    risk_override_ack = "0"      →  True
    social_post       = "false"  →  True   (계속 게시한다)

`risk_override_ack`는 **"실수로 켜지지 않게" 일부러 따로 둔 키**다. 엣지가
미입증인 상태에서 목표 변동성 상한을 푸는 스위치인데, **끄려고 적은 글자가
켜는 결과**를 냈다. 이 파일이 스스로 적어 둔 안전 원칙과 정반대다.

이제 글자를 글자대로 읽는다. 모르는 값은 **추측하지 않고** 기본값으로 두되
경고를 남긴다 — 이 파일의 규칙 그대로(죽지는 않되 숨기지도 않는다).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.utils.settings import (  # noqa: E402
    DEFAULTS, MAX_TARGET_VOL, MIN_TARGET_VOL, load_settings, owner_gate,
)

BOOLS = ["trading_paused", "social_post", "risk_override_ack"]


@pytest.fixture()
def logs():
    """`quant` 로거는 `propagate=False`라 pytest의 caplog가 못 본다.

    루트에 붙는 caplog 핸들러까지 기록이 올라오지 않으므로, 이 로거에 직접
    수집 핸들러를 붙인다. (이걸 모르고 caplog만 믿으면 '경고를 안 남긴다'는
    결함을 **검사가 못 잡는다** — 감사 195에서 실제로 헛돌 뻔했다.)
    """
    got: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            got.append(record.getMessage())

    logger = logging.getLogger("quant")
    handler = _Collect()
    logger.addHandler(handler)
    try:
        yield got
    finally:
        logger.removeHandler(handler)


@pytest.fixture()
def settings(tmp_path):
    def _write(raw: dict):
        fp = tmp_path / "settings.json"
        fp.write_text(json.dumps(raw), encoding="utf-8")
        return load_settings(str(fp))
    return _write


# ── 끄려고 적은 글자가 끄는가 ─────────────────────────────────


@pytest.mark.parametrize("key", BOOLS)
@pytest.mark.parametrize("off", ["false", "False", "FALSE", "no", "0", "off", ""])
def test_a_written_off_actually_turns_it_off(settings, key, off):
    assert settings({key: off})[key] is False, (
        f"{key}={off!r}로 껐는데 켜졌다")


@pytest.mark.parametrize("key", BOOLS)
@pytest.mark.parametrize("on", ["true", "True", "yes", "1", "on"])
def test_a_written_on_actually_turns_it_on(settings, key, on):
    """대조군 — 전부 False로 읽으면 스위치가 통째로 죽는다."""
    assert settings({key: on})[key] is True, f"{key}={on!r}로 켰는데 꺼졌다"


@pytest.mark.parametrize("key", BOOLS)
def test_real_booleans_still_work(settings, key):
    assert settings({key: True})[key] is True
    assert settings({key: False})[key] is False


@pytest.mark.parametrize("key", BOOLS)
def test_an_unrecognised_value_falls_back_to_the_default_and_warns(
        settings, key, logs):
    """모르는 값을 추측하면 그게 바로 이 결함이다 — 기본값 + 경고."""
    got = settings({key: "아마도"})
    assert got[key] is DEFAULTS[key], f"{key}: 모르는 값을 추측했다"
    assert any(key in m for m in logs), f"{key}: 모르는 값을 조용히 넘어갔다"


def test_the_override_flag_is_the_one_that_must_never_turn_on_by_accident(
        settings):
    """엣지 미입증 상태에서 위험 상한을 푸는 스위치다."""
    for off in ("false", "no", "0", "off", ""):
        assert settings({"risk_override_ack": off})["risk_override_ack"] is False
    assert settings({})["risk_override_ack"] is False
    assert settings({"risk_override_ack": True})["risk_override_ack"] is True


# ── 숫자 손잡이의 계약 ────────────────────────────────────────


def test_exposure_scale_is_clamped_to_no_leverage(settings):
    assert settings({"exposure_scale": 10})["exposure_scale"] == 1.0
    assert settings({"exposure_scale": -5})["exposure_scale"] == 0.0
    assert settings({"exposure_scale": 0.5})["exposure_scale"] == 0.5


def test_an_unreadable_exposure_scale_warns_instead_of_silently_full(
        settings, logs):
    got = settings({"exposure_scale": "절반"})
    assert got["exposure_scale"] == 1.0
    assert any("exposure_scale" in m for m in logs), (
        "노출 축소가 무시됐는데 아무 말이 없다")


def test_target_vol_is_clamped_and_a_typo_falls_back_to_none(settings):
    assert settings({"portfolio_target_vol": 5.0})["portfolio_target_vol"] == \
        MAX_TARGET_VOL
    assert settings({"portfolio_target_vol": 0.0001})["portfolio_target_vol"] == \
        MIN_TARGET_VOL
    assert settings({"portfolio_target_vol": "높게"})["portfolio_target_vol"] is None
    assert settings({"portfolio_target_vol": ""})["portfolio_target_vol"] is None
    assert settings({})["portfolio_target_vol"] is None


# ── 폴백이 조용하지 않은가 ────────────────────────────────────


def test_a_corrupt_file_falls_back_loudly(tmp_path, logs):
    fp = tmp_path / "settings.json"
    fp.write_text("{망가진", encoding="utf-8")
    assert load_settings(str(fp)) == DEFAULTS
    assert any("무시되고" in m for m in logs), (
        "일시정지·노출 축소가 사라졌는데 조용히 넘어갔다")


def test_a_missing_file_is_normal_and_quiet(tmp_path, logs):
    assert load_settings(str(tmp_path / "없음.json")) == DEFAULTS
    assert logs == [], f"설정 파일이 없는 건 정상 상태다: {logs}"


def test_the_owner_gate_reads_the_same_two_switches(tmp_path):
    fp = tmp_path / "settings.json"
    fp.write_text(json.dumps({"trading_paused": "yes", "exposure_scale": 0.25}),
                  encoding="utf-8")
    assert owner_gate(str(fp)) == (True, 0.25)
    fp.write_text(json.dumps({"trading_paused": "no"}), encoding="utf-8")
    assert owner_gate(str(fp)) == (False, 1.0)
