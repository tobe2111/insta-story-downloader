"""킬스위치가 **배선돼 있는가** (감사 120).

이 파일은 변이 시험이 찾아낸 구멍에서 나왔다. `quant/live/daily.py`의

    risk_scale = _kill_switch_scale(float(st.get("risk_scale", 1.0)), drawdown)

를 통째로

    risk_scale = 1.0

으로 바꾸면 — 즉 **낙폭 자동 브레이크를 완전히 제거하면** — 1,580개가
넘는 검사 전체가 초록으로 통과했다.

왜 그랬나. 킬스위치에 관한 검사는 세 종류가 있었는데 셋 다 장치를
비껴갔다.

    · test_killswitch_deposits.py  — `_kill_switch_scale(prev, dd)`를
      **순수 함수로** 부른다. 함수는 완벽하다. 아무도 안 쓰면 그만이다.
    · test_killswitch_effective.py — vol_scale과의 **순서**를 검사한다.
      브레이크가 밟히면 어떻게 되는지는 보지만, 밟히는지는 안 본다.
    · 나머지                        — 소스에 문자열이 있는지 본다.

셋을 합쳐도 "낙폭이 커졌을 때 노출이 실제로 줄어든다"는 문장을 아무도
확인하지 않았다. 부품 검사와 배선 검사는 다른 것이다 — FROZEN_IDEAS ⑭
'형제를 찾기 전까지 고친 게 아니다'의 다른 얼굴이고, 이 시스템에서
**가장 안전에 가까운 장치**에 그 구멍이 있었다.

그래서 이 검사는 함수를 부르지 않는다. 낙폭이 있는 장부를 만들어
**진짜 일일 배치를 돌리고**, 기록된 노출이 줄었는지 본다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARGETS = [("synthetic", "DEMO"), ("synthetic", "DEMO2")]


def _seed(tmp_path, *, equity_now: float, peak: float | None = None) -> str:
    """낙폭이 `equity_now / peak - 1`인 통합 계좌 장부를 만든다.

    낙폭은 자산이 아니라 **입금 제거 성장 지수** 위에서 재므로(감사
    2026-08-11), 입금이 없는 이 장부에서는 equity/start_cash가 곧 지수다.
    """
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({
        "synthetic:DEMO": {"strategy": "ma_cross",
                           "params": {"fast": 10, "slow": 30},
                           "promotions": 0},
        "synthetic:DEMO2": {"strategy": "ma_cross",
                            "params": {"fast": 5, "slow": 20},
                            "promotions": 0},
    }, d)
    hist = []
    if peak is not None:
        hist = [{"date": "2026-01-01", "equity": peak}]
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 80_000.0, "cash": equity_now,
        "positions": {}, "base_prices": {}, "last_bar": None,
        "history": hist,
    }), encoding="utf-8")
    return d


def _run(state_dir: str) -> dict:
    from quant.live.daily import run_daily_portfolio
    return run_daily_portfolio(TARGETS, lookback=200, state_dir=state_dir,
                               require_real_data=False)


# ── ① 평시 — 이 검사가 헛돌지 않는다는 증거 ─────────────────────


def test_a_healthy_account_actually_takes_exposure(tmp_path):
    """평시에 노출이 0이면 아래 검사들은 '0 == 0'을 확인하는 헛것이 된다."""
    rec = _run(_seed(tmp_path, equity_now=80_000.0))
    assert rec["risk_scale"] == 1.0
    assert rec["weight"] > 0, (
        "평시인데 총노출이 0이다 — 이 파일의 나머지 검사가 무의미해진다")


# ── ② 낙폭이 실제로 노출을 줄이는가 ────────────────────────────


def test_a_deep_drawdown_halves_the_exposure(tmp_path):
    """-15%~-25% 구간: 노출이 **정확히 절반**이어야 한다.

    '줄어든다'가 아니라 '절반'을 요구하는 이유 — 변동성 타깃 스케일러가
    감쇠를 되돌려 키우던 결함(감사 2026-08-11)이 있었다. 부등호로만
    검사하면 그 되돌림이 조금만 남아도 통과한다.
    """
    healthy = _run(_seed(tmp_path / "ok", equity_now=80_000.0))
    hurt = _run(_seed(tmp_path / "dd", equity_now=65_600.0, peak=80_000.0))

    assert hurt["drawdown_pct"] < -15.0
    assert hurt["risk_scale"] == 0.5, (
        f"낙폭 {hurt['drawdown_pct']}%인데 킬스위치가 안 걸렸다")
    assert abs(hurt["weight"] - healthy["weight"] * 0.5) < 1e-4, (
        f"브레이크를 밟았는데 노출이 안 줄었다: "
        f"평시 {healthy['weight']} → 낙폭 {hurt['weight']}")


def test_a_catastrophic_drawdown_flattens_the_book(tmp_path):
    """-25% 이하: 전량 관망. 노출도, 종목별 적용 노출도 남으면 안 된다."""
    rec = _run(_seed(tmp_path, equity_now=52_000.0, peak=80_000.0))
    assert rec["drawdown_pct"] < -25.0
    assert rec["risk_scale"] == 0.0
    assert rec["weight"] == 0.0
    assert rec["applied"] in (None, {}), (
        f"관망인데 종목별 노출이 남아 있다: {rec['applied']}")


def test_the_brake_reaches_the_orders_not_just_the_ledger(tmp_path):
    """장부에만 0을 적고 실제로는 사는 것을 막는다.

    감사 91·92 계열 — '기록한 숫자'와 '실제로 낸 주문'이 갈라지는 실수는
    이 저장소에서 반복해서 나왔다. 그러니 노출 0이면 **포지션도 없어야**
    한다.
    """
    d = _seed(tmp_path, equity_now=52_000.0, peak=80_000.0)
    _run(d)
    st = json.loads((Path(d) / "paper" / "portfolio_ALL.json")
                    .read_text("utf-8"))
    held = {k: v for k, v in (st.get("positions") or {}).items()
            if abs(float(v.get("quantity", 0.0))) > 0}
    assert not held, f"전량 관망인데 보유가 생겼다: {held}"
    assert not (st.get("pending") or {}), (
        f"전량 관망인데 다음 시가 예약 주문이 남았다: {st.get('pending')}")


# ── ③ 브레이크 상태가 다음 날로 이어지는가(히스테리시스) ────────


def test_the_brake_state_is_carried_into_the_next_day(tmp_path):
    """단계적 복귀는 **어제 상태**를 알아야 한다 — 장부에 남지 않으면
    매일 1.0에서 다시 시작해 '0 → 바로 1.0' 복귀가 된다."""
    d = _seed(tmp_path, equity_now=52_000.0, peak=80_000.0)
    _run(d)
    st = json.loads((Path(d) / "paper" / "portfolio_ALL.json")
                    .read_text("utf-8"))
    assert st.get("risk_scale") == 0.0, (
        "킬스위치 단계가 장부에 저장되지 않는다 — 히스테리시스가 죽는다")


# ── ③ 위험 예산을 '감쇠 전' 비중으로 재는가 (감사 183) ─────────


def _seed_wide(tmp_path, *, n: int, equity_now: float, peak: float | None = None):
    """종목이 많은 장부 — **변동성 스케일러가 실제로 도는** 유일한 설정.

    ⚠️ `ex_ante_vol`은 **비중이 0이 아닌 종목이 둘 이상**이어야 추정한다
       (공분산이라 하나로는 분산 효과를 못 잰다). 그런데 위 두 검사가 쓰는
       2종목 합성 장부에서는 마지막 봉에 롱이 걸리는 종목이 대개 하나뿐이라
       **추정불가 → 배수 1.0**이 된다. 즉 그 harness로는 스케일러가 아예
       안 돌아서, 스케일러에 관한 어떤 결함도 드러나지 않는다(감사 183에서
       실측). 8종목이면 추정이 되고 배수가 0.12~0.26 구간에 들어온다.
    """
    import json

    from quant.live.retrain import save_champions

    d = str(tmp_path)
    targets = [("synthetic", f"S{i}") for i in range(n)]
    save_champions({f"synthetic:S{i}": {"strategy": "momentum", "params": {},
                                        "promotions": 0} for i in range(n)}, d)
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "currency": "KRW",
        "start_cash": 80_000.0, "cash": equity_now,
        "positions": {}, "base_prices": {}, "last_bar": None,
        "history": ([{"date": "2026-01-01", "equity": peak}] if peak else []),
    }), encoding="utf-8")
    return targets, d


def _run_wide(tmp_path, **kw) -> dict:
    from quant.live.daily import run_daily_portfolio

    targets, d = _seed_wide(tmp_path, n=8, **kw)
    return run_daily_portfolio(targets, lookback=250, state_dir=d,
                               require_real_data=False)


def test_the_risk_budget_is_measured_before_the_brake_not_after(tmp_path,
                                                                monkeypatch):
    """변동성 배수를 **감쇠된 비중**으로 계산하면 브레이크가 통째로 사라진다.

    킬스위치가 비중을 절반으로 줄이면, 그 절반짜리 비중으로 사전 변동성을
    재는 순간 스케일러는 "위험이 절반"이라 판단해 배수를 두 배로 올린다.
    최종 노출이 감쇠 전과 **똑같아진다** — 감쇠는 했는데 아무 일도 안 한 것이다.
    (2026-08-11 감사에서 실제로 있었던 결함이다.)

    ⚠️ 위의 두 검사로는 이 결함을 못 잡는다(감사 183에서 실측). 이유가 둘:
       ① 2종목 장부에서는 비중이 0 아닌 종목이 하나뿐이라 **사전추정 자체가
          안 된다**(배수 1.0 고정) — 무엇을 넣어도 같은 답이다.
       ② 목표 변동성이 기본값이면 배수가 `MAX_VOL_SCALE` 천장에 붙는다.
          **한도에 눌려 있는 값으로는 순서를 검사할 수 없다.**
       그래서 종목을 8개로 넓히고 목표를 낮춰 배수를 중간 구간에 둔다.
    """
    import quant.risk.portfolio_vol as PV

    monkeypatch.setattr(PV, "target_vol_now",
                        lambda state_dir="state": (0.002, False, "테스트"))

    healthy = _run_wide(tmp_path / "ok", equity_now=80_000.0)
    hurt = _run_wide(tmp_path / "dd", equity_now=65_600.0, peak=80_000.0)

    # 전제 확인 — 하나라도 깨지면 이 검사는 '0 == 0'을 보는 헛것이 된다
    assert hurt["risk_scale"] == 0.5, hurt["risk_scale"]
    assert healthy["weight"] > 0, "대조군이 깨졌다 — 평시 노출이 0이다"
    assert healthy["vol_target"]["ex_ante"], (
        "사전추정이 안 됐다 — 스케일러가 안 도는 설정이라 순서를 못 잰다")
    assert 0.0 < healthy["vol_target"]["scale"] < 1.0, (
        f"배수가 한도에 눌려 있다({healthy['vol_target']['scale']}) — "
        "이 상태로는 순서를 검사할 수 없다")

    # 핵심 불변식 — **감쇠가 예산을 건드리면 안 된다.** 브레이크를 밟았다고
    # 위험 예산이 커지면 그건 브레이크가 아니다. 노출(weight)은 장부에
    # 소수 4자리로 반올림돼 있어 반올림 오차가 섞이므로, 반올림에 휘둘리지
    # 않는 배수 자체로 잰다.
    assert hurt["vol_target"]["scale"] == healthy["vol_target"]["scale"], (
        f"감쇠했더니 위험 예산이 달라졌다 — 감쇠된 비중으로 변동성을 재고 "
        f"있다: 평시 배수 {healthy['vol_target']['scale']} → "
        f"낙폭 배수 {hurt['vol_target']['scale']}")
    assert abs(hurt["vol_target"]["applied"]
               - healthy["vol_target"]["applied"] * 0.5) < 1e-4, (
        f"최종 적용 배수가 절반이 아니다: {healthy['vol_target']['applied']} "
        f"→ {hurt['vol_target']['applied']}")
    assert abs(hurt["weight"] - healthy["weight"] * 0.5) < 1e-4, (
        f"노출이 절반이 아니다: {healthy['weight']} → {hurt['weight']}")
