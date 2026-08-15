"""레버리지는 **세 관문을 다 통과해야** 열린다 — 기본은 잠김.

⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님이 선물 투자를 물어서 ①②③④를
   순서대로 만들었고, 이게 그 자물쇠다).

    이 저장소가 이번 주 내내 고친 결함은 전부 같은 모양이었다 —
    **문서는 막는다고 적혀 있는데 코드는 안 막았다.** 검증 게이트가 경보만
    울리고 비중을 안 깎았고, 결승전이 한 번도 안 열렸고, 의회가 현금에
    의석을 줬다.

    레버리지는 그 결함이 나면 **계좌가 없어지는** 영역이다. 그래서 여기서는
    기본값이 잠김이고, 여는 것은 세 관문의 통과라는 사실뿐이다:

      ① 청산이 감시보다 먼저 오지 않는가
      ② 감시가 **실제로** 그만큼 자주 돌았는가 (설정이 아니라 실측)
      ③ 도중에 죽지 않는가 (파산확률)

    그리고 **모르면 잠긴다.** 셋 중 하나라도 답이 없으면 1배다.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.guard import (                              # noqa: E402
    MIN_BEATS_FOR_GAP,
    guard_once,
    load_heartbeat,
    observed_gap_minutes,
    record_heartbeat,
)
from quant.risk.leverage_gate import HARD_CAP, decide       # noqa: E402


def _beats(state_dir, n=30, every=15, hiccup_at=None, hiccup=180):
    t = dt.datetime(2026, 8, 15, 0, 0)
    for i in range(n):
        t += dt.timedelta(minutes=hiccup if i == hiccup_at else every)
        record_heartbeat(t.isoformat(), state_dir=str(state_dir))
    return t


def _returns(mu=0.0003, sd=0.015, n=800, seed=5):
    return np.random.default_rng(seed).normal(mu, sd, n)


# ── ① 기본은 잠김 ───────────────────────────────────────────────

def test_the_default_is_locked(tmp_path):
    """아무것도 안 하면 **1배**다 — 지금 이 시스템 그대로."""
    d = decide(state_dir=str(tmp_path))
    assert d.locked and d.allowed == 1.0


@pytest.mark.parametrize("missing", ["감시", "변동성", "수익률"])
def test_any_missing_measurement_keeps_it_locked(tmp_path, missing):
    """**모르면 잠긴다.** 미측정을 통과로 읽는 것이 이미 고친 실패다."""
    kw = dict(state_dir=str(tmp_path), requested=5.0,
              daily_vol=0.03, market="crypto", returns=_returns())
    if missing == "감시":
        pass                                    # 심장박동을 안 쌓는다
    else:
        _beats(tmp_path)
        kw["daily_vol"] = 0.0 if missing == "변동성" else kw["daily_vol"]
        kw["returns"] = None if missing == "수익률" else kw["returns"]
    d = decide(**kw)
    assert d.locked, f"{missing}을 모르는데 {d.allowed}배가 허용됐다"
    assert any(not c["ok"] for c in d.checks), "왜 잠겼는지를 안 말한다"


def test_it_says_which_gate_bound_the_limit(tmp_path):
    """한도를 정한 것이 무엇인지 말해야 한다 — 안 말하면 고칠 수가 없다."""
    _beats(tmp_path)
    d = decide(returns=_returns(), daily_vol=0.03, market="crypto",
               state_dir=str(tmp_path), requested=10.0)
    assert d.binding, "한도를 정한 관문을 안 밝힌다"
    assert len(d.checks) == 3, f"세 관문을 다 안 본다: {[c['name'] for c in d.checks]}"


# ── ② 설정이 아니라 실측을 쓴다 ─────────────────────────────────

def test_it_uses_the_observed_gap_not_the_intended_one(tmp_path):
    """**이 검사가 이 기능의 핵심이다.**

    15분마다 돌기로 해 놓고 한 번 3시간 벌어졌다면, 우리가 감당해야 할
    진실은 3시간이다. 설정값으로 한도를 계산하면 그 한도는 거짓이다.
    """
    _beats(tmp_path, hiccup_at=12, hiccup=180)
    assert observed_gap_minutes(str(tmp_path)) == pytest.approx(180.0)
    detail = next(c["detail"] for c in
                  decide(returns=_returns(), daily_vol=0.03, market="crypto",
                         state_dir=str(tmp_path)).checks
                  if c["name"] == "장중 감시 실적")
    assert "180" in detail, f"실측 간격을 안 쓴다: {detail}"


def test_a_guard_that_stopped_running_is_visible_now(tmp_path):
    """감시가 **지금 멈춰 있는** 것도 간격이다.

    마지막 심장박동까지만 보면, 어제부터 죽어 있는 감시가 '잘 돌고 있음'으로
    보인다 — 이 저장소가 데드맨 스위치를 만든 것과 같은 이유다.
    """
    last = _beats(tmp_path, n=20, every=15)
    healthy = observed_gap_minutes(str(tmp_path))
    later = (last + dt.timedelta(hours=6)).isoformat()
    stale = observed_gap_minutes(str(tmp_path), now_iso=later)
    assert stale > healthy and stale == pytest.approx(360.0, abs=1), (
        f"6시간 멈춰 있는데 간격이 {stale}분으로 보인다")


def test_too_few_beats_is_unknown_not_zero(tmp_path):
    """기록이 몇 개뿐이면 '간격 0분'이 아니라 **모름**이다."""
    _beats(tmp_path, n=MIN_BEATS_FOR_GAP - 1)
    assert observed_gap_minutes(str(tmp_path)) is None


def test_heartbeats_survive_a_broken_file(tmp_path):
    """기록 파일이 깨져도 감시가 죽으면 안 된다 — 감시가 죽는 게 제일 나쁘다."""
    (tmp_path / "guard_heartbeat.json").write_text("{망가짐", encoding="utf-8")
    st = record_heartbeat("2026-08-15T00:00:00", state_dir=str(tmp_path))
    assert st.beats == ["2026-08-15T00:00:00"]


# ── ③ 장중 킬스위치가 실제로 작동하는가 ─────────────────────────

def test_the_intraday_guard_actually_cuts_exposure(tmp_path):
    """낙폭이 깊으면 **그 자리에서** 노출을 줄인다 — 다음 새벽까지 안 기다린다."""
    v = guard_once(70.0, 100.0, 1.0, now_iso="2026-08-15T10:00:00",
                   state_dir=str(tmp_path))
    assert v.acted and v.scale == 0.0, v.reason
    assert load_heartbeat(str(tmp_path)).actions, "조치를 장부에 안 남긴다"


def test_the_guard_uses_the_same_killswitch_rule_at_every_level(tmp_path):
    """규칙을 여기 다시 적으면 새벽 배치와 장중 감시가 다른 선에서 물러난다.

    ⚠️ 이름만 확인하면 안 된다 — 변이 검사가 이걸 잡았다. `_kill_switch_scale`
       라는 **이름의 사본**을 만들어 두면 문자열 검사는 통과하고, 값은 깊은
       낙폭에서만 우연히 같다. 그래서 **모든 단계에서 값이 같은지**를 본다.
       히스테리시스(0→0.5→1.0 단계 복귀)까지 베끼기는 어렵다.
    """
    from quant.live.daily import _kill_switch_scale

    for prev in (1.0, 0.5, 0.0):
        for equity in (95.0, 90.0, 88.0, 85.0, 80.0, 75.0, 70.0, 50.0):
            v = guard_once(equity, 100.0, prev, now_iso="2026-08-15T10:00:00",
                           state_dir=str(tmp_path))
            # ⚠️ 기대값을 **감시가 실제로 잰 낙폭**으로 만든다. 명목값
            #    (-0.10)으로 만들면 100*(1-0.10)=90.00000000000001 같은 부동
            #    소수점 때문에 경계에서 갈라진다 — 코드 결함이 아니라 검사의
            #    결함이고, 그런 검사는 사람을 엉뚱한 곳으로 보낸다.
            want = _kill_switch_scale(prev, v.drawdown)
            assert v.scale == want, (
                f"낙폭 {v.drawdown:.1%}·직전 {prev:.0%}에서 장중 감시는 "
                f"{v.scale}, 새벽 배치는 {want} — 두 곳이 갈라졌다")


def test_a_quiet_run_is_still_recorded(tmp_path):
    """아무 일 없어도 **돌았다는 사실**은 남아야 한다 — 그게 간격의 재료다."""
    guard_once(99.0, 100.0, 1.0, now_iso="2026-08-15T10:00:00",
               state_dir=str(tmp_path))
    st = load_heartbeat(str(tmp_path))
    assert st.beats and not st.actions, "조용한 회차가 기록에서 빠졌다"


# ── ④ 관문이 실제로 깎는가 ──────────────────────────────────────

def test_the_gate_caps_an_aggressive_request(tmp_path):
    """10배를 요청해도 관문이 정한 값으로 깎인다 — 요청은 상한을 못 넘는다."""
    _beats(tmp_path)
    d = decide(returns=_returns(), daily_vol=0.03, market="crypto",
               state_dir=str(tmp_path), requested=10.0)
    assert d.allowed < 10.0 and d.binding != "요청값"


def test_a_modest_request_is_honoured(tmp_path):
    """관문은 **상한**이지 목표가 아니다 — 적게 쓰겠다면 그대로 둔다."""
    _beats(tmp_path)
    d = decide(returns=_returns(), daily_vol=0.01, market="kr_stock",
               state_dir=str(tmp_path), requested=1.05)
    assert d.allowed == pytest.approx(1.05) and d.binding == "요청값"


def test_a_ruinous_strategy_gets_nothing_even_with_perfect_guarding(tmp_path):
    """감시가 완벽해도 **죽는 전략에는 배수를 안 준다.**

    ①만 보고 열면 "1분마다 보니까 10배 괜찮다"가 되는데, 그 전략이 도중에
    죽으면 감시 주기는 아무 상관이 없다.
    """
    _beats(tmp_path, n=60, every=1)
    ruinous = np.where(np.random.default_rng(1).random(1000) < 0.51, 0.10, -0.10)
    d = decide(returns=ruinous, daily_vol=0.03, market="crypto",
               state_dir=str(tmp_path), requested=10.0)
    assert d.locked, f"파산하는 전략에 {d.allowed}배를 줬다"
    assert d.binding == "파산확률"


def test_the_hard_cap_binds_even_if_everything_looks_great(tmp_path):
    """모든 가정이 동시에 낙관적일 수 있다 — 계산을 믿되 무한히 믿지 않는다.

    ⚠️ 예전에는 `d.allowed <= HARD_CAP`으로 봤다. 자기가 검사하는 상수와
       비교하는 자기참조라 HARD_CAP을 1000으로 바꿔도 통과했고, 변이 검사가
       그걸 잡았다(2026-08-14 — 오늘 같은 함정을 두 번째로 잡았다).
       **독립된 숫자**로 못 박는다.
    """
    _beats(tmp_path, n=60, every=1)
    calm = _returns(mu=0.0005, sd=0.002)
    d = decide(returns=calm, daily_vol=0.002, market="kr_stock",
               state_dir=str(tmp_path), requested=100.0)
    assert d.allowed <= 5.0, f"모든 것이 좋아 보일 때 {d.allowed}배까지 열린다"
    assert 1.0 < HARD_CAP <= 5.0, (
        f"절대 상한 {HARD_CAP}배 자체가 상한 구실을 못 한다")


def test_nothing_in_the_codebase_uses_leverage_yet():
    """**문은 아직 안 열렸다.** 관문만 세운 상태여야 한다.

    총노출 상한(레버리지 금지)이 그대로인지 확인한다 — 이번 작업으로
    실제 운용이 바뀌면 안 된다.
    """
    from quant.risk.portfolio_vol import MAX_GROSS_EXPOSURE

    assert MAX_GROSS_EXPOSURE == 1.0, (
        "총노출 상한이 1.0이 아니다 — 관문만 세우기로 했는데 문이 열렸다")


# ── ⑤ 감시가 판단만 하고 장부를 안 고치면 다음 배치가 되돌린다 ──────

def test_the_cli_guard_writes_the_cut_into_the_ledger(tmp_path):
    """**판단만 하고 장부를 안 고치면 이 감시는 선언만 하는 장치다.**

    다음 새벽 배치가 옛 노출로 되돌리고, 장중에 줄인 것은 사라진다.
    `guard_once`만 검사하면 이 결함이 안 보인다 — 장부를 쓰는 것은 CLI다.
    """
    import json
    import types

    from quant.cli import _cmd_guard

    paper = tmp_path / "paper"
    paper.mkdir(parents=True)
    led = paper / "portfolio_ALL.json"
    led.write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "risk_scale": 1.0,
        "history": [{"date": "2026-08-01", "equity": 1_000_000.0},
                    {"date": "2026-08-15", "equity": 700_000.0}],
    }), encoding="utf-8")

    _cmd_guard(types.SimpleNamespace(state_dir=str(tmp_path),
                                     state_file="portfolio_ALL.json"))
    after = json.loads(led.read_text(encoding="utf-8"))
    assert after["risk_scale"] == 0.0, (
        f"낙폭 -30%인데 장부의 노출이 {after['risk_scale']} — 장중 감시가 "
        f"판단만 하고 장부를 안 고쳤다")


def test_the_cli_guard_leaves_a_quiet_ledger_alone(tmp_path):
    """아무 일 없을 때 장부를 건드리면 매 15분마다 커밋이 생긴다."""
    import json
    import types

    from quant.cli import _cmd_guard

    paper = tmp_path / "paper"
    paper.mkdir(parents=True)
    led = paper / "portfolio_ALL.json"
    body = json.dumps({"market": "portfolio", "symbol": "ALL",
                       "risk_scale": 1.0,
                       "history": [{"date": "2026-08-15", "equity": 1_000_000.0}]})
    led.write_text(body, encoding="utf-8")
    _cmd_guard(types.SimpleNamespace(state_dir=str(tmp_path),
                                     state_file="portfolio_ALL.json"))
    assert led.read_text(encoding="utf-8") == body, "조용한 회차가 장부를 고쳤다"
