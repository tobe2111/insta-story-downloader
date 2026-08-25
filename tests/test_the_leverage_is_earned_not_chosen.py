"""배율은 사람이 고르는 게 아니라 기록이 벌어야 얻는다 (감사 314).

사장님 지시(2026-08-25): *"그 조정은 그냥 수익률과 성공률이 높게만 나오면
되는거야. 실시간으로 조정은 이 프로그램 자체에서 머신러닝에서 할 일이고."*

맞는 지적이었다. 배율 상한을 3으로 할지 2로 할지 사람이 매번 정하는 것은
근거 없는 손질이고, 그 손질이 쌓이면 "그때그때 좋아 보이는 값"을 고른
장부가 된다.

■ 그런데 "수익률이 높게 나온 배율"을 고르면 안 된다 — 이 구별이 전부다

지난 기록에서 가장 많이 번 배율을 고르는 것은 학습이 아니라 **과최적화**다.
같은 잡음을 두 번 믿고, 하필 그 잡음에 배율까지 얹는다. 2026-08-24 실측:
이 시스템의 실전 적중률은 45.8%(95% 구간 36.7~55.2%)로 우연과 구별되지
않는다. 그 상태에서 '수익률 최대'를 좇으면 동전 던지기에 3배를 태운다.

■ 여기서 지키는 것

  · **기본은 1배.** 증명 전에는 안 올린다.
  · **위험 대비로 잰다.** 같은 수익이라도 요동이 크면 안 준다.
  · **우연을 배제한 뒤에만** 올린다 — 평균 회차 수익률의 95% 하한이 0을
    넘어야 한다. 점추정이 양수라는 이유로 올리면 우리가 그토록 걸러낸
    '운 좋은 승자'가 우리 자신이 된다(본 계좌의 edge_proven과 같은 잣대).
  · **내릴 때는 즉시, 올릴 때는 천천히.** 반대로 만들면 한 번의 폭락으로
    끝난다.
  · 화면이 **지금 허락된 값**과 **사람이 정한 절대 천장**을 구별해 말한다.
    둘을 같은 이름으로 부르면 3배라 적힌 화면이 실제로는 1배로 돈다.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.leverage import (  # noqa: E402
    DRAWDOWN_STOP, MIN_ROUNDS, MIN_STD, adaptive_max_leverage, drawdown,
    evidence, round_returns,
)

CAP = 3.0


def _curve(vals):
    return [{"equity": float(v)} for v in vals]


def _walk(n, mu, sd, seed=1, start=100.0):
    rng = random.Random(seed)
    v = start
    out = []
    for _ in range(n):
        v *= 1.0 + rng.gauss(mu, sd)
        out.append(v)
    return _curve(out)


def _steady(n, step, start=100.0):
    """요동 없이 일정하게 오르는 곡선 — 요동 0을 만드는 데 쓴다."""
    return _curve([start * (1.0 + step) ** i for i in range(n)])


# ══ ① 증명 전에는 1배 ═════════════════════════════════════════════

def test_a_thin_record_earns_no_leverage():
    got = adaptive_max_leverage(_walk(20, 0.01, 0.002), hard_cap=CAP)
    assert got["max_leverage"] == 1.0
    assert str(MIN_ROUNDS) in got["why"], got["why"]


def test_a_coin_flip_record_earns_no_leverage():
    """평균이 0 근처면 표본이 많아도 안 준다 — 우연과 구별되지 않는다."""
    got = adaptive_max_leverage(_walk(400, 0.0, 0.01, seed=5), hard_cap=CAP)
    assert got["max_leverage"] == 1.0
    assert got["proven"] is False


def test_a_losing_record_earns_no_leverage():
    got = adaptive_max_leverage(_walk(400, -0.002, 0.005, seed=7),
                                hard_cap=CAP)
    assert got["max_leverage"] == 1.0


def test_a_proven_record_does_earn_leverage():
    """대조군 — 진짜로 증명되면 **올라가야** 한다.

    이게 없으면 "무조건 1배를 돌려준다"는 고장도 위 검사들을 전부 통과한다.
    """
    got = adaptive_max_leverage(_walk(400, 0.004, 0.01, seed=3), hard_cap=CAP)
    assert got["proven"] is True, got["why"]
    assert got["max_leverage"] > 1.0
    assert got["max_leverage"] <= CAP


def test_it_never_exceeds_the_human_ceiling():
    """사람이 정한 절대 천장은 못 넘는다 — 아무리 성적이 좋아도."""
    got = adaptive_max_leverage(_walk(500, 0.05, 0.005, seed=9), hard_cap=CAP)
    assert got["max_leverage"] <= CAP + 1e-9


# ══ ② 위험 대비로 잰다 ════════════════════════════════════════════

def test_more_wobble_earns_less_leverage():
    """같은 평균 수익이라도 요동이 크면 배율이 적어야 한다."""
    calm = adaptive_max_leverage(_walk(400, 0.004, 0.006, seed=3),
                                 hard_cap=CAP)["max_leverage"]
    wild = adaptive_max_leverage(_walk(400, 0.004, 0.030, seed=3),
                                 hard_cap=CAP)["max_leverage"]
    assert calm > wild, (calm, wild)


def test_an_unmeasurable_wobble_earns_nothing():
    """요동이 0이면 위험 대비를 잴 수 없다 — 잴 수 없으면 안 올린다.

    ⚠️ 여기서 무한대가 되면 '완벽한 전략'이 상한을 통째로 가져간다.
    """
    got = adaptive_max_leverage(_steady(400, 0.003), hard_cap=CAP)
    assert got["max_leverage"] == 1.0, (
        "완벽히 일정한 곡선이 상한을 통째로 가져갔다 — 요동 문턱이 "
        "부동소수 잡음 크기였다(감사 209와 같은 실수)")
    assert "잴 수 없다" in got["why"]


# ══ ③ 내릴 때는 즉시 ══════════════════════════════════════════════

def test_a_deep_drawdown_drops_to_one_immediately():
    """증명된 기록이라도 낙폭이 깊어지면 **그 자리에서** 1배다."""
    good = _walk(400, 0.004, 0.01, seed=3)
    assert adaptive_max_leverage(good, hard_cap=CAP)["proven"] is True
    peak = good[-1]["equity"]
    hurt = good + _curve([peak * (1.0 - DRAWDOWN_STOP - 0.02)])
    got = adaptive_max_leverage(hurt, hard_cap=CAP)
    assert got["max_leverage"] == 1.0, got
    assert "낙폭" in got["why"]


def test_a_shallow_dip_does_not_panic():
    """대조군 — 얕은 되돌림에는 안 내린다. 아니면 늘 1배가 된다."""
    good = _walk(400, 0.004, 0.01, seed=3)
    peak = good[-1]["equity"]
    dip = good + _curve([peak * (1.0 - DRAWDOWN_STOP / 3.0)])
    assert adaptive_max_leverage(dip, hard_cap=CAP)["max_leverage"] > 1.0


# ══ ④ 못 읽는 입력에 크게 걸지 않는다 ═════════════════════════════

@pytest.mark.parametrize("curve", [None, [], [{"equity": None}],
                                   [{"equity": "많이"}], [{}, {}]])
def test_an_unreadable_curve_earns_nothing(curve):
    assert adaptive_max_leverage(curve, hard_cap=CAP)["max_leverage"] == 1.0


@pytest.mark.parametrize("cap", [None, 0, 1.0, -3, "셋"])
def test_an_unusable_ceiling_means_no_leverage(cap):
    assert adaptive_max_leverage(_walk(400, 0.004, 0.01), hard_cap=cap
                                 )["max_leverage"] == 1.0


def test_it_reads_both_curve_shapes():
    """곡선 점이 dict든 [시각, 자산]이든 같게 읽는다."""
    a = round_returns([{"equity": 100}, {"equity": 110}])
    b = round_returns([["t1", 100], ["t2", 110]])
    assert a == b == [pytest.approx(0.1)]


def test_drawdown_is_measured_from_the_peak():
    assert drawdown(_curve([100, 120, 90])) == pytest.approx(0.25)
    assert drawdown(_curve([100, 110, 120])) == pytest.approx(0.0)


# ══ ⑤ 트랙이 실제로 그 상한을 쓴다 (배선) ═════════════════════════

def test_the_ledger_publishes_todays_ceiling():
    """⚠️ 계산이 맞아도 리포트에 안 실리면 화면은 아무것도 못 그린다."""
    from quant.live import futures_challenger as F
    st = {"cash": 10_000.0, "start_cash": 10_000.0, "positions": {},
          "cost_paid": 0.0, "last_prices": {}, "rounds": [],
          "curve": _walk(20, 0.001, 0.002)}
    r = F.public_report(st)
    cap = r.get("leverage_cap")
    assert cap and cap["max_leverage"] == 1.0, cap
    assert r["max_gross_exposure"] == F.MAX_GROSS_EXPOSURE, (
        "사람이 정한 절대 천장이 사라졌다 — 둘은 다른 값이다")


def test_the_ledger_recomputes_rather_than_reading_an_old_round():
    """지난 회차에 그 칸이 없어도 **지금 값**이 나와야 한다.

    옛 기록에서 읽으면, 이 장치가 켜지기 전 회차만 있는 트랙은 영영
    '모름'으로 남는다(과거는 고치지 않으므로).
    """
    from quant.live import futures_challenger as F
    st = {"cash": 10_000.0, "start_cash": 10_000.0, "positions": {},
          "cost_paid": 0.0, "last_prices": {},
          "rounds": [{"at": "2026-08-01T00:00:00+09:00", "equity": 10_000.0}],
          "curve": _walk(400, 0.004, 0.01, seed=3)}
    cap = F.public_report(st)["leverage_cap"]
    assert cap["proven"] is True and cap["max_leverage"] > 1.0, cap


def test_the_rule_change_is_disclosed():
    """실험 도중 규칙을 바꿨으므로 공개 기록에 남는다 — 조용한 골대 이동 금지."""
    from quant.live import futures_challenger as F
    whats = " ".join(c.get("what", "") for c in F.RULE_CHANGES)
    assert "기록이" in whats and "2026-08-25" in [c["on"] for c in F.RULE_CHANGES]


def test_a_broken_measurement_does_not_raise_the_ceiling(monkeypatch):
    """재다가 터져도 **1배**로 떨어진다 — 모를 때 크게 거는 것이 최악이다."""
    from quant.live import futures_challenger as F
    monkeypatch.setattr(
        "quant.live.leverage.adaptive_max_leverage",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("망가짐")))
    st = {"cash": 10_000.0, "start_cash": 10_000.0, "positions": {},
          "cost_paid": 0.0, "last_prices": {}, "rounds": [],
          "curve": _walk(400, 0.004, 0.01, seed=3)}
    assert F.public_report(st)["leverage_cap"]["max_leverage"] == 1.0


def test_the_wobble_floor_is_sized_for_a_real_market():
    """요동 문턱이 **부동소수 잡음 크기가 아니어야** 한다.

    감사 209가 정확히 이 실수였다: 원리는 맞게 적어 놓고 문턱을 1e-9로
    잡아, 사실상 멈춘 시세가 그대로 통과해 목표 비중이 100%가 됐다.
    """
    assert MIN_STD > 1e-12, "문턱이 부동소수 잡음 크기다 — 아무것도 못 막는다"
    assert MIN_STD < 1e-4, "문턱이 너무 커서 진짜 조용한 구간까지 막는다"


def test_a_real_market_wobble_is_not_mistaken_for_noise():
    """대조군 — 실제 트랙의 요동(0.44%)은 '잴 수 없음'으로 걸리면 안 된다."""
    ev = evidence(_walk(400, 0.004, 0.0044, seed=3))
    assert "잴 수 없다" not in ev["why"], ev


# ══ ⑥ 두 성질을 **직접** 겨냥한다 ═════════════════════════════════
#
# ⚠️ 위의 '무작위 기록' 검사들은 이 둘을 재는 것처럼 보이지만 실제로는
#    못 잡는다(변이 시험이 확인). 무작위 곡선은 여러 성질이 한꺼번에
#    움직여서, 하나를 망가뜨려도 다른 것이 결과를 지켜 준다.
#    그래서 여기서는 **결정적인 곡선**으로 그 성질만 잰다.


def _alternating(n, mean, wobble, start=100.0):
    """평균은 정확히 `mean`, 요동은 정확히 `wobble`인 곡선.

    번갈아 오르내리므로 낙폭이 한 걸음치를 넘지 않는다 — 낙폭 관문이
    먼저 걸려서 재려던 것을 못 재는 일이 없다.
    """
    v = start
    out = []
    for i in range(n):
        v *= 1.0 + mean + (wobble if i % 2 == 0 else -wobble)
        out.append(v)
    return _curve(out)


def test_a_weak_positive_mean_is_not_proof():
    """평균이 양수여도 **신뢰구간이 0을 품으면** 증명이 아니다.

    이게 없으면 "평균만 보고 올린다"는 고장이 그대로 통과한다 — 그건
    우리가 그토록 걸러낸 '운 좋은 승자'가 우리 자신이 되는 것이다.
    """
    # 평균 +0.03%, 요동 0.47% → 200회차에서 95% 하한이 0 아래다.
    ev = evidence(_alternating(200, 0.0003, 0.0047))
    assert ev["mean"] > 0, "전제가 틀렸다 — 평균이 양수여야 하는 검사다"
    assert ev["lo"] < 0, f"전제가 틀렸다 — 하한이 0 아래여야 한다 ({ev['lo']})"
    assert ev["proven"] is False, (
        "평균이 양수라는 이유로 증명 처리했다 — 신뢰구간을 안 본다")
    assert adaptive_max_leverage(_alternating(200, 0.0003, 0.0047),
                                 hard_cap=CAP)["max_leverage"] == 1.0


def test_the_ratio_is_return_divided_by_wobble():
    """위험 대비란 **수익을 요동으로 나눈 것**이다.

    수익만 보고 정하면 같은 수익이라도 요동이 두 배인 기록에 같은 배율을
    주게 된다 — 그건 위험을 안 본 것이다.
    """
    ev = evidence(_alternating(300, 0.002, 0.01))
    assert ev["ratio"] == pytest.approx(ev["mean"] / ev["std"], rel=1e-6), (
        f"위험 대비가 수익/요동이 아니다 (ratio={ev['ratio']}, "
        f"mean={ev['mean']}, std={ev['std']})")


def test_the_same_return_with_double_the_wobble_earns_half_the_reach():
    """같은 수익·두 배 요동이면 위험 대비도 절반이어야 한다(대조군 짝)."""
    calm = evidence(_alternating(300, 0.002, 0.01))["ratio"]
    wild = evidence(_alternating(300, 0.002, 0.02))["ratio"]
    assert wild == pytest.approx(calm / 2.0, rel=0.05), (calm, wild)


# ══ ⑦ 회차가 실제로 그 상한을 지킨다 (배선) ═══════════════════════
#
# ⚠️ 상한을 옳게 계산해도 **체결이 그 값을 안 쓰면** 아무 일도 안 일어난다.
#    그래서 회차를 진짜로 한 번 돌려 총 노출을 잰다.


def _round_with_curve(monkeypatch, tmp_path, curve, signal=1.0):
    """시세와 전략만 갈아 끼우고 **나머지 길은 실제 코드**를 지나가게 한다."""
    import pandas as pd

    import quant.live.futures_challenger as F

    closes = [100.0] * 40
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    df = pd.DataFrame({"open": closes, "high": closes, "low": closes,
                       "close": closes, "volume": [1.0] * len(closes)},
                      index=idx)

    class _Strat:
        def generate_signals(self, frame):
            return pd.Series([signal] * len(frame), index=frame.index)

    monkeypatch.setattr(F, "_fetch_real", lambda sym, timeframe=None: df)
    monkeypatch.setattr(F, "build_two_sided",
                        lambda sym, state_dir: (_Strat(), True))
    monkeypatch.setattr(F, "MIN_BARS", 5)

    st = F.load_state(str(tmp_path))
    st["curve"] = list(curve)
    F.save_state(st, str(tmp_path))
    return F.run_futures_round("2026-06-01T00:00:00+09:00",
                               state_dir=str(tmp_path),
                               universe=["BTC/USDT"], per_side=0.0)


def test_an_unproven_track_never_exceeds_one_times(monkeypatch, tmp_path):
    """증명 안 된 트랙은 총 노출이 자산을 못 넘는다.

    넘으면 체결이 '기록이 정한 상한'을 무시하고 옛 고정값(3배)을 쓴 것이다.
    """
    rec = _round_with_curve(monkeypatch, tmp_path, _walk(30, 0.001, 0.002))
    eq, gross = float(rec["equity"]), float(rec["gross_exposure"])
    assert gross <= eq * 1.01, (
        f"증명 안 됐는데 총 노출 {gross:.0f}이 자산 {eq:.0f}을 넘었다 — "
        "배율 상한이 체결에 안 걸렸다")
    assert rec["leverage_cap"]["max_leverage"] == 1.0


def test_a_proven_track_is_allowed_to_exceed_one_times(monkeypatch, tmp_path):
    """대조군 — 증명된 트랙은 넘을 수 있어야 한다.

    이게 없으면 "무조건 1배로 묶는다"는 고장도 위 검사를 통과한다.
    """
    rec = _round_with_curve(monkeypatch, tmp_path,
                            _walk(400, 0.004, 0.01, seed=3))
    assert rec["leverage_cap"]["proven"] is True, rec["leverage_cap"]
    eq, gross = float(rec["equity"]), float(rec["gross_exposure"])
    assert gross > eq * 1.01, (
        f"증명됐는데 총 노출 {gross:.0f}이 자산 {eq:.0f}을 안 넘었다 — "
        "번 배율이 체결에 안 닿았다")
