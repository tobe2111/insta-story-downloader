"""리스크 서킷브레이커 테스트 (순수 stdlib)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "cb", str(Path(__file__).resolve().parent.parent
             / "quant" / "live" / "circuit_breaker.py"))
cb = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cb   # @dataclass 내부 조회가 sys.modules를 참조하므로 등록
_spec.loader.exec_module(cb)


def test_no_trip_within_limits():
    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=0.05, max_drawdown=0.2))
    assert b.update(10_000, "2026-01-01") is False
    assert b.update(9_800, "2026-01-01") is False   # -2%, 한도 내
    assert not b.tripped


def test_daily_loss_trips():
    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=0.05, max_drawdown=None))
    b.update(10_000, "2026-01-01")
    assert b.update(9_400, "2026-01-01") is True    # -6% > 한도 5%
    assert b.tripped and "일일 손실" in b.reason


def test_drawdown_trips():
    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=None, max_drawdown=0.20))
    b.update(10_000, "2026-01-01")
    b.update(12_000, "2026-01-02")   # 고점 갱신
    assert b.update(9_500, "2026-01-03") is True    # 고점 대비 -20.8%
    assert "최대 낙폭" in b.reason


def test_daily_resets_on_new_day():
    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=0.05, max_drawdown=None))
    b.update(10_000, "2026-01-01")
    b.update(9_700, "2026-01-01")            # -3%, 미발동
    assert not b.tripped
    # 다음 날 기준 리셋 → 같은 절대수준이어도 당일 손실 0
    assert b.update(9_700, "2026-01-02") is False
    assert not b.tripped


def test_notifier_called_on_trip():
    sent = []

    class N:
        def send(self, msg, level="info"):
            sent.append((msg, level))

    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=0.05), notifier=N())
    b.update(10_000, "2026-01-01")
    b.update(9_000, "2026-01-01")
    assert sent and sent[0][1] == "error" and "서킷브레이커" in sent[0][0]


def test_reset():
    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=0.05))
    b.update(10_000, "2026-01-01")
    b.update(9_000, "2026-01-01")
    assert b.tripped
    b.reset()
    assert not b.tripped and b.reason == ""


def test_reset_rebaselines_and_allows_resume():
    """reset 후 재개 시, 여전히 참인 손실 조건으로 '즉시 재발동'하지 않아야 한다.

    구버전은 플래그만 지워 다음 update가 같은 -10%를 재평가해 바로 재발동했다.
    reset가 기준값(고점·일일 시작 자본)까지 비워 현재 자산으로 새 창을 잡아야 한다.
    """
    b = cb.CircuitBreaker(cb.BreakerConfig(max_daily_loss=0.05, max_drawdown=0.2))
    b.update(10_000, "2026-01-01")
    assert b.update(9_000, "2026-01-01") is True     # -10% → 발동
    b.reset()
    # 같은 날·같은 자산으로 재개 → 새 기준(9000)으로 리셋되어 재발동 안 함
    assert b.update(9_000, "2026-01-01") is False
    assert not b.tripped
