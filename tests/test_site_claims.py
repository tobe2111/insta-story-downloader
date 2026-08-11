"""사이트가 단언한 것이 코드에서 실제로 지켜지는가.

배경(2026-08-11 감사): trust.html은 "이 기록은 조작할 수 없습니다"라는
제목으로 시스템 동작을 여러 개 단언한다. 그 문장들이 코드와 어긋나면
사이트의 유일한 자산인 정직성이 무너진다. 실제로 두 건이 어긋나 있었다.

  · "낙폭 단계별 자동 킬스위치가 적용됩니다" → 스케일러가 되돌려 키워
    실제로는 아무 효과가 없었다(같은 감사에서 수정)
  · "누적 검증 횟수로 문턱을 높입니다" → 코드는 롤링 1년 + 상한 1.35.
    코드가 아니라 설명이 틀렸던 것이라 설명을 고쳤다.

핵심 계약: 사이트가 말하는 장치는 코드에 실재하고, 수치는 코드와 같다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TRUST = (ROOT / "docs" / "trust.html").read_text("utf-8")


def test_claimed_verify_command_exists():
    assert "python -m quant verify" in TRUST
    from quant.live.retrain import verify_retrain
    assert callable(verify_retrain)


def test_claimed_killswitch_actually_reduces_exposure():
    """사이트가 말하는 '자동 킬스위치'가 실제로 노출을 줄이는가."""
    assert "킬스위치" in TRUST
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    # 감쇠 전 비중으로 예산을 잡고, 감쇠는 그 뒤에 곱한다
    assert "vol_scale(base_w, rets_map, tgt_vol)" in src
    assert "vol_scale(pre_w" not in src


def test_claimed_next_open_fill_is_real():
    assert "다음 거래 세션의 시가" in TRUST
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "IMMEDIATE_FILL_MARKETS" in src


def test_claimed_no_synthetic_records():
    assert "합성 데이터로 기록을 채우는 경로 자체가" in TRUST
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'df.attrs.get("synthetic_fallback")' in src
    assert "전 종목 데이터 실패 — 기록하지 않음" in src


def test_multiple_testing_numbers_match_the_code():
    """사이트에 적힌 문턱 수식·상한이 코드 상수와 같아야 한다."""
    from quant.live.retrain import CONFIRM_T_CAP, TRIALS_WINDOW_DAYS
    assert f"{CONFIRM_T_CAP}" in TRUST
    assert "최근 1년" in TRUST and TRIALS_WINDOW_DAYS == 365
    # 누적 총계로 문턱을 올린다는 옛 설명이 되살아나면 안 된다
    assert "누적 검증 횟수를 저장하고, 횟수가" not in TRUST


def test_shadow_control_and_parliament_exist():
    assert "섀도 대조군" in TRUST and "의회 운용" in TRUST
    src = (ROOT / "quant" / "cli.py").read_text("utf-8")
    assert "portfolio_SHADOW.json" in src
    from quant.live.parliament import ParliamentStrategy
    assert ParliamentStrategy is not None


def test_structure_epoch_describes_todays_changes():
    """구조 세대 설명이 실제 구조를 기술하는가(장부의 자기 기술)."""
    from quant.live.daily import STRUCTURE_WHY
    assert "안전장치 복구" in STRUCTURE_WHY


def test_parliament_explanation_discloses_the_mixture():
    """의원이 둘 이상이면 '리더 논리'가 곧 오늘의 비중이 아니다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "의석 1위 의원의" in src and "가중 평균한 값" in src


def test_parliament_summary_is_silent_for_single_member():
    from quant.live.parliament import parliament_summary
    assert parliament_summary({"parliament": [{"strategy": "ml",
                                               "weight": 1.0}]}) is None
    two = parliament_summary({"parliament": [
        {"strategy": "ml", "weight": 0.6},
        {"strategy": "ma_cross", "weight": 0.4}]})
    assert two and "60%" in two and "40%" in two


# ── 코인 미완결 봉 공개 (감사 63) ─────────────────────────────


def test_site_discloses_the_partial_crypto_bar():
    """코인이 미완결 봉으로 판단한다는 사실이 사이트에 적혀 있는가.

    trust.html은 "미완결 봉 제거는 이미 고쳐진 상태"라고 적고 있었다.
    주식 문맥에서는 맞지만, 코인은 여전히 진행 중인 봉으로 판단한다
    (실측 15/15). 읽는 사람은 '전부 고쳐졌다'로 읽는다. 사이트가 코드보다
    더 말하는 것을 막는 것이 이 파일의 목적이다.
    """
    t = (ROOT / "docs" / "trust.html").read_text(encoding="utf-8")
    assert "만들어지는 중인 봉" in t, "코인 미완결 봉 사실이 공개돼 있지 않다"
    assert "bar_partial" in t          # 장부 필드명까지 밝힌다
    assert "15개 중 15개" in t          # 추정이 아니라 실측 숫자
    assert "일봉 종가가 아닙니다" in t   # 공개 차트와 어긋나는 이유


def test_partial_bar_field_exists_in_code():
    """사이트가 약속한 bar_partial이 실제로 기록되는가(주장-코드 대조)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert '"bar_partial"' in src
    assert (ROOT / "quant" / "data" / "barclock.py").exists()
