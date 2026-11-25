"""전부 멈춘 계좌가 **다시 시작할 길**이 있다 (2026-11-18 사장님 "응 고쳐줘").

실측: 코인 단타 운용 계좌가 2026-11-15에 고점 대비 −25%로 전부 팔았다. 복귀
조건은 "낙폭 −15% 안쪽 회복"인데 현금만 들면 자산이 안 움직여 그 조건은 영원히
참이 될 수 없었다(자산 8,088.05 USDT 고정, 거래 0). 5분봉 트랙도 같았다.

지키는 것:
1. 낙폭 단계(−15% 절반 · −25% 멈춤)는 그대로다.
2. 멈춘 지 한 주가 지나면 **절반으로** 다시 산다 — 그 전에는 안 산다.
3. 다시 산 순간이 새 출발점이다 — 옛 고점으로 재서 곧바로 또 멈추지 않는다.
4. 새 출발점 위로 올라서기 전에는 절반을 넘지 않는다.
5. 절반으로 다시 −25%를 잃으면 또 멈춘다.
6. 다시 시작한 사실이 장부에 남는다.
7. 모든 계좌가 같은 한 함수를 쓴다(직접 `_kill_switch_scale`을 부르지 않는다).
"""
import re
from pathlib import Path

from quant.live.daily import KILL_SWITCH_COOLDOWN_DAYS, kill_switch_step

T0 = "2026-11-15T06:00:00+00:00"


def _day(n: float) -> str:
    import pandas as pd
    return (pd.Timestamp(T0) + pd.Timedelta(days=n)).isoformat()


def _stopped():
    st = {"risk_scale": 1.0}
    scale, _ = kill_switch_step(st, 7400.0, 10000.0, T0)   # −26%
    assert scale == 0.0
    return st


def test_the_drawdown_ladder_is_unchanged():
    st = {"risk_scale": 1.0}
    assert kill_switch_step(st, 9500.0, 10000.0, T0)[0] == 1.0
    assert kill_switch_step(st, 8400.0, 10000.0, T0)[0] == 0.5
    assert kill_switch_step(st, 7400.0, 10000.0, T0)[0] == 0.0


def test_it_waits_a_week_then_buys_back_at_half():
    st = _stopped()
    for d in (1, 3, KILL_SWITCH_COOLDOWN_DAYS - 0.1):
        assert kill_switch_step(st, 7400.0, 10000.0, _day(d))[0] == 0.0
    scale, dd = kill_switch_step(st, 7400.0, 10000.0, _day(KILL_SWITCH_COOLDOWN_DAYS))
    assert scale == 0.5 and dd == 0.0
    r = st["kill_switch"]["restarts"]
    assert len(r) == 1 and r[0]["drawdown_before"] < -0.25


def test_after_restart_the_old_peak_does_not_stop_it_again():
    st = _stopped()
    kill_switch_step(st, 7400.0, 10000.0, _day(KILL_SWITCH_COOLDOWN_DAYS))
    # 다음 회차 — 부르는 쪽은 여전히 옛 고점 10000을 넘긴다.
    scale, dd = kill_switch_step(st, 7350.0, 10000.0, _day(KILL_SWITCH_COOLDOWN_DAYS + 0.1))
    assert scale == 0.5, "옛 고점으로 재서 다시 산 회차에 곧바로 또 멈췄다"
    assert dd > -0.02


def test_half_until_it_climbs_above_the_new_start():
    st = _stopped()
    kill_switch_step(st, 7400.0, 10000.0, _day(KILL_SWITCH_COOLDOWN_DAYS))
    assert kill_switch_step(st, 7390.0, 10000.0, _day(8))[0] == 0.5
    assert kill_switch_step(st, 7500.0, 10000.0, _day(9))[0] == 1.0


def test_losing_another_quarter_at_half_stops_it_again():
    st = _stopped()
    kill_switch_step(st, 7400.0, 10000.0, _day(KILL_SWITCH_COOLDOWN_DAYS))
    assert kill_switch_step(st, 5500.0, 10000.0, _day(8))[0] == 0.0
    assert st["kill_switch"]["stopped_at"]


def test_every_account_uses_the_one_step_function():
    root = Path(__file__).resolve().parents[1] / "quant" / "live"
    for name in ("intraday_challenger.py", "intraday_us.py", "intraday_mode.py"):
        src = (root / name).read_text("utf-8")
        assert "kill_switch_step(" in src, name
        assert not re.search(r"_kill_switch_scale\(", src), (
            f"{name}이(가) 복귀 규칙 없는 킬스위치를 직접 부른다")
    daily = (root / "daily.py").read_text("utf-8")
    body = daily.split("def run_daily_portfolio", 1)[1]
    assert "kill_switch_step(" in body
