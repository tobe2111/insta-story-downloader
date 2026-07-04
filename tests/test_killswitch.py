"""일일 최대손실 킬스위치 테스트 (순수 stdlib).

검증 항목:
    - 기본값(None)이면 완전 비활성(하위 호환)
    - 한도 도달 시 발동(just_tripped) 후 그날 내내 할트
    - 다음 UTC 일자에 자동 재개 + 시작 자본 리셋
    - 상태 영속화: 재시작(새 인스턴스)해도 '오늘은 쉼' 유지
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "killswitch", str(Path(__file__).resolve().parent.parent
                      / "quant" / "live" / "killswitch.py"))
ks = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ks   # @dataclass 등 내부 조회가 sys.modules를 참조
_spec.loader.exec_module(ks)


def _t(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, tzinfo=timezone.utc)


def test_disabled_by_default():
    s = ks.DailyLossKillSwitch()                  # daily_max_loss=None
    assert s.update(10_000, _t(1)) is False
    assert s.update(1, _t(1, 12)) is False        # -99.99%여도 비활성이면 무시
    assert s.just_tripped is False


def test_trips_on_daily_loss_and_halts_rest_of_day():
    s = ks.DailyLossKillSwitch(daily_max_loss=0.03)
    assert s.update(10_000, _t(1, 0)) is False    # 하루 시작
    assert s.update(9_800, _t(1, 6)) is False     # -2%: 한도 내
    assert s.update(9_690, _t(1, 12)) is True     # -3.1%: 발동
    assert s.just_tripped is True                 # 발동 사이클에서만 True
    assert s.halted_until == "2026-07-02"
    assert s.update(9_900, _t(1, 18)) is True     # 회복해도 그날은 쉼
    assert s.just_tripped is False                # 재발동 아님(청산 중복 방지)


def test_resumes_next_utc_day_with_fresh_baseline():
    s = ks.DailyLossKillSwitch(daily_max_loss=0.03)
    s.update(10_000, _t(1, 0))
    assert s.update(9_600, _t(1, 12)) is True     # -4% 발동
    assert s.update(9_600, _t(2, 0)) is False     # 다음 UTC 일 → 재개
    assert s.halted_until is None
    # 기준 자본이 9,600으로 리셋 → 그 대비 -2%는 한도 내
    assert s.update(9_408, _t(2, 12)) is False
    # 그 대비 -3% 이상이면 다시 발동
    assert s.update(9_310, _t(2, 18)) is True


def test_day_boundary_resets_baseline_without_trip():
    s = ks.DailyLossKillSwitch(daily_max_loss=0.05)
    s.update(10_000, _t(1, 0))
    s.update(9_700, _t(1, 12))                    # -3%: 한도(5%) 내
    assert s.update(9_700, _t(2, 0)) is False     # 새 날: 9,700이 새 기준
    assert s.day_start_equity == 9_700


def test_state_persists_across_restart(tmp_path):
    p = str(tmp_path / "kill.json")
    s = ks.DailyLossKillSwitch(daily_max_loss=0.03, state_path=p)
    s.update(10_000, _t(1, 0))
    assert s.update(9_500, _t(1, 6)) is True      # 발동 → 디스크 기록

    raw = json.loads(Path(p).read_text(encoding="utf-8"))
    assert raw["halted_until"] == "2026-07-02"

    # 재시작 시뮬레이션: 새 인스턴스가 '오늘은 쉼'을 이어받는다
    s2 = ks.DailyLossKillSwitch(daily_max_loss=0.03, state_path=p)
    assert s2.update(9_500, _t(1, 12)) is True
    assert s2.just_tripped is False               # 이미 발동된 상태 → 청산 중복 없음
    assert s2.update(9_500, _t(2, 0)) is False    # 다음 날 자동 재개


def test_corrupt_state_file_starts_fresh(tmp_path):
    p = tmp_path / "kill.json"
    p.write_text("{ 손상된 json", encoding="utf-8")
    s = ks.DailyLossKillSwitch(daily_max_loss=0.03, state_path=str(p))
    assert s.update(10_000, _t(1, 0)) is False    # 예외 없이 새로 시작


def test_notifier_called_on_trip():
    sent = []

    class _N:
        def send(self, msg, level="info"):
            sent.append((msg, level))

    s = ks.DailyLossKillSwitch(daily_max_loss=0.03, notifier=_N())
    s.update(10_000, _t(1, 0))
    s.update(9_000, _t(1, 6))
    assert len(sent) == 1 and "킬스위치" in sent[0][0] and sent[0][1] == "error"
