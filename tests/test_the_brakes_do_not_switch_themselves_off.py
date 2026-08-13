"""브레이크가 스스로 꺼지지 않는가 (감사 198).

이 저장소에서 매매를 강제로 멈추는 장치는 둘이다.

    DailyLossKillSwitch  하루 -x% → 그날 하루 중단
    CircuitBreaker       고점 대비 -x% → 수동 reset까지 중단

둘 다 "기준선을 기억해 두고 지금 자산과 비교한다"는 같은 모양이라,
**같은 방식으로 조용히 꺼졌다.** 실측(2026-08-13, 고치기 전):

    킬스위치   : 그날 첫 관측이 NaN → -50%도 -99%도 발동 안 함
    서킷브레이커: 첫 관측이 NaN → peak=nan, 세션 끝까지 회복 못 함
    서킷브레이커: 첫 관측이 inf → 다음 관측이 곧바로 '-100% 낙폭' 오발동
    둘 다      : 한도를 0.03 대신 3으로 적으면 아무 말 없이 꺼짐

안전장치는 없는 것보다 **'있다고 믿는데 없는 것'**이 나쁘다 — 그 믿음
위에서 더 크게 베팅하게 되기 때문이다. 그래서 이 파일의 검사는 전부
"꺼지지 않는다"를 본다.

⚠️ 이 파일의 모든 '안 꺼진다' 검사에는 **대조군**이 붙어 있다. NaN을 넣은
   뒤 발동하는 것만 보면, 애초에 아무 조건에서나 발동하는 망가진 장치도
   통과한다. 그래서 같은 자리에서 **정상값이면 어떻게 되는지**를 함께 본다.
"""
from __future__ import annotations

import datetime as dt
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.circuit_breaker import BreakerConfig, CircuitBreaker  # noqa: E402
from quant.live.killswitch import DailyLossKillSwitch  # noqa: E402

NOW = dt.datetime(2026, 8, 13, 1, 0, tzinfo=dt.timezone.utc)
NAN = float("nan")
INF = float("inf")


@contextmanager
def _quant_logs():
    """`quant` 로거는 propagate=False라 pytest의 caplog가 아무것도 못 본다.

    감사 195에서 실제로 헛돌 뻔한 자리다 — 경고가 아예 없어도 caplog로만
    확인하면 통과한다. 로거에 수집 핸들러를 직접 붙인다.
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


def _breaker(**kw):
    kw.setdefault("max_daily_loss", None)
    kw.setdefault("max_drawdown", 0.20)
    return CircuitBreaker(BreakerConfig(**kw))


# ── ① 숫자가 아닌 자산값이 기준선을 오염시키지 않는다 ────────────────


def test_a_nan_reading_does_not_disable_the_circuit_breaker():
    """NaN 한 번이 세션 전체의 브레이크를 먹지 않는가.

    고치기 전: peak_equity가 nan이 되고 `max(nan, x)`는 nan을 그대로 둔다
    (x > nan이 False이므로). 그 뒤로는 낙폭이 얼마든 비교가 전부 거짓이라
    **세션이 끝날 때까지** 발동하지 않았다.
    """
    b = _breaker()
    assert b.update(NAN, "d1") is False          # 판정 보류 — 발동도 아니다
    assert b.peak_equity is None, "NaN이 기준선이 되어 버렸다"
    b.update(10_000, "d1")
    assert b.peak_equity == 10_000
    assert b.update(7_500, "d1") is True, "NaN 이후 낙폭 -25%인데 브레이크가 안 걸린다"

    # 대조군 — NaN이 중간에 끼어도 이미 잡힌 고점이 밀리지 않는다
    c = _breaker()
    c.update(10_000, "d1")
    c.update(NAN, "d1")
    assert c.peak_equity == 10_000, "NaN이 고점을 지웠다"
    assert c.update(7_500, "d1") is True


def test_a_nan_reading_does_not_disable_the_killswitch_for_the_day():
    """그날 첫 관측이 NaN이면 하루 종일 꺼져 있었다.

    고치기 전 실측: day_start_equity=nan → `nan > 0`이 거짓이라 손실 판정을
    통째로 건너뛰고, 날짜가 안 바뀌니 기준선도 다시 안 잡힌다. -99%까지
    떨어져도 발동하지 않았다.
    """
    k = DailyLossKillSwitch(daily_max_loss=0.03)
    assert k.update(NAN, NOW) is False
    assert k.day_start_equity is None, "NaN이 그날 기준 자본이 되어 버렸다"
    k.update(10_000, NOW)
    assert k.day_start_equity == 10_000
    assert k.update(9_000, NOW) is True, "NaN 이후 -10%인데 킬스위치가 안 걸린다"

    # 대조군 — NaN 없이 같은 순서면 당연히 걸린다(장치 자체가 살아 있음)
    ok = DailyLossKillSwitch(daily_max_loss=0.03)
    ok.update(10_000, NOW)
    assert ok.update(9_000, NOW) is True


def test_an_infinite_reading_does_not_fake_a_total_loss():
    """inf는 반대 방향으로 틀렸다 — 즉시 '-100% 낙폭' 오발동.

    peak=inf가 되면 다음 관측이 무엇이든 `x/inf - 1 = -1.0`이라 전 종목이
    청산된다. '모름'이 '전액 손실'로 둔갑하는 것이다.
    """
    b = _breaker()
    b.update(INF, "d1")
    assert b.update(10_000, "d1") is False, "inf 때문에 브레이크가 오발동했다"
    assert not b.tripped

    # 대조군 — 진짜 -100%(자산 0)는 반드시 발동해야 한다. 위 검사가
    # "그냥 발동을 안 하는 장치"를 통과시키지 않도록 반대편을 못 박는다.
    real = _breaker()
    real.update(10_000, "d1")
    assert real.update(0.0, "d1") is True
    assert "낙폭" in real.reason


def test_a_reading_that_is_not_a_number_at_all_is_refused():
    """None·문자열도 같은 취급 — float()가 안 되면 판정하지 않는다."""
    for bad in (None, "", "십만원", object()):
        b = _breaker()
        assert b.update(bad, "d1") is False
        assert b.peak_equity is None, f"{bad!r}가 기준선이 되었다"


def test_a_tripped_breaker_stays_tripped_through_a_bad_reading():
    """이미 걸린 브레이크가 NaN 한 번에 풀리면 안 된다.

    판정 보류는 '아직 안 걸렸다'가 아니라 '지금 상태 그대로'여야 한다.
    """
    b = _breaker()
    b.update(10_000, "d1")
    assert b.update(7_000, "d1") is True
    assert b.update(NAN, "d1") is True, "NaN이 걸린 브레이크를 풀어 버렸다"


def test_the_silence_is_broken_when_a_reading_is_unusable():
    """조용히 넘어가지 않는가 — 이 결함의 본체는 '모르게 꺼지는 것'이다."""
    with _quant_logs() as logs:
        _breaker().update(NAN, "d1")
        DailyLossKillSwitch(daily_max_loss=0.03).update(NAN, NOW)
    joined = "\n".join(logs)
    assert "서킷브레이커" in joined and "일일 손실 킬스위치" in joined
    assert joined.count("숫자가 아닙니다") >= 2, joined

    # 대조군 — 멀쩡한 값에는 이 경고가 나오면 안 된다(늑대 소년 방지)
    with _quant_logs() as quiet:
        _breaker().update(10_000, "d1")
        DailyLossKillSwitch(daily_max_loss=0.03).update(10_000, NOW)
    assert not [m for m in quiet if "숫자가 아닙니다" in m]


# ── ② 한도 오기입이 장치를 조용히 끄지 못한다 ────────────────────────


@pytest.mark.parametrize("bad", [3, 20, 100, 1.5])
def test_a_percent_written_as_a_whole_number_is_refused(bad):
    """0.03을 3으로 적으면 '-300% 도달 시 발동' = 영영 발동 안 함.

    시작 로그에는 `-{limit:.0%}`로 "-300%"라고 찍히므로, 사장님은 브레이크가
    걸려 있다고 믿게 된다. 설정 오타는 **실행 전에** 드러나야 한다.
    """
    with pytest.raises(ValueError, match="0.03"):
        BreakerConfig(max_drawdown=bad)
    with pytest.raises(ValueError, match="0.03"):
        DailyLossKillSwitch(daily_max_loss=bad)


@pytest.mark.parametrize("bad", [0, 0.0, -0.2, -1])
def test_a_zero_or_negative_limit_is_refused(bad):
    """반대쪽 오타 — 0이나 음수면 항상 발동해서 매매가 아예 안 된다."""
    with pytest.raises(ValueError):
        BreakerConfig(max_daily_loss=bad)
    with pytest.raises(ValueError):
        DailyLossKillSwitch(daily_max_loss=bad)


@pytest.mark.parametrize("bad", [NAN, INF, "삼퍼센트", object()])
def test_a_limit_that_is_not_a_number_is_refused(bad):
    with pytest.raises(ValueError):
        BreakerConfig(max_drawdown=bad)


def test_the_ordinary_settings_still_work():
    """대조군 — 실제로 쓰는 값들은 그대로 통과해야 한다.

    이게 없으면 위 검사들은 "무엇이든 거절하는 장치"도 통과시킨다.
    cli.py의 기본값(0.03 · 0.15)과 '미사용'(None)을 못 박는다.
    """
    cfg = BreakerConfig(max_daily_loss=0.03, max_drawdown=0.15)
    assert (cfg.max_daily_loss, cfg.max_drawdown) == (0.03, 0.15)
    assert BreakerConfig(max_daily_loss=None).max_daily_loss is None
    assert BreakerConfig(max_drawdown=1.0).max_drawdown == 1.0     # -100%는 유효
    assert DailyLossKillSwitch(daily_max_loss=None).daily_max_loss is None
    assert DailyLossKillSwitch(daily_max_loss=0.03).daily_max_loss == 0.03


# ── ③ 두 장치가 같은 판정을 쓴다 ─────────────────────────────────────


def test_both_brakes_ask_the_same_judge():
    """판정이 갈라지지 않는가(㉞ · 감사 192).

    감사 182에서 브로커 둘만 고쳤다가 형제 넷을 빠뜨렸다. 여기서도 한쪽만
    고치면 "킬스위치는 NaN을 막는데 서킷브레이커는 안 막는" 상태가 되고,
    그건 둘 다 안 막는 것보다 알아채기 어렵다. 같은 나쁜 입력에 두 장치가
    **같은 반응**을 하는지 행동으로 확인한다.
    """
    for bad_limit in (3, -0.2, NAN):
        errs = []
        for make in (lambda v: BreakerConfig(max_daily_loss=v),
                     lambda v: DailyLossKillSwitch(daily_max_loss=v)):
            try:
                make(bad_limit)
                errs.append(None)
            except ValueError:
                errs.append("거절")
        assert errs == ["거절", "거절"], f"{bad_limit!r}에 두 장치 반응이 다르다: {errs}"

    b, k = _breaker(), DailyLossKillSwitch(daily_max_loss=0.03)
    assert (b.update(NAN, "d1"), k.update(NAN, NOW)) == (False, False)
    assert b.peak_equity is None and k.day_start_equity is None
