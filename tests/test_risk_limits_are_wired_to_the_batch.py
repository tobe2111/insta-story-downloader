"""위험 한도 두 개가 **배선 검사를 안 받았다** (감사 121·122).

감사 120(킬스위치)의 형제다. 같은 방식으로 찾았다 — 프로덕션 코드를 한
줄 망가뜨리고 **전체** 검사를 돌린다.

    ① `tgt_vol, vol_proven, vol_why = target_vol_now(state_dir)`
       →  `= 0.20, True, "게이트무시"`                 ❌ 1,580개 전부 통과

       엣지가 통계로 입증되기 전까지 목표 변동성을 연 12%로 잠그는
       게이트다. 이 잠금이 이 계좌의 **리스크 상한 그 자체**다.
       (2026-08-12 실측: 목표 0.12 · 사전추정 0.264% → 배수 45.5배.
        목표를 0.20으로 올리면 배수가 76배가 되고, 총노출은 무레버리지
        상한까지 밀려 올라간다.)

       왜 못 잡았나 — `test_edge_proven_gate.py`와 `test_portfolio_vol.py`가
       `target_vol_now`/`edge_proven`을 **순수 함수로** 부른다. 함수는
       옳다. 배치가 그 함수를 쓰는지는 아무도 안 봤다.

    ② `cap = 3.0 / n` (한 종목 과집중 상한)
       →  `cap = 1e9`                                  ❌ 전부 통과

       HRP는 저변동 종목에 자본을 몰아준다. 이 상한은 그 쏠림을 자른다.
       (2026-08-12 실측: 최대 배분 14.62% / 상한 15.00% — **아슬아슬하게
        안 걸린 상태**였다. 죽은 규칙이 아니라 매일 턱에 닿는 규칙이다.)

이 파일은 함수를 부르지 않는다. 진짜 배치를 돌리고 **장부에 남은 값**을
본다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.risk.portfolio_vol import VERIFY_TARGET_VOL  # noqa: E402

SYMS = [("synthetic", f"D{i}") for i in range(6)]


def _prep(tmp_path) -> str:
    from quant.live.retrain import save_champions
    d = str(tmp_path)
    save_champions({f"synthetic:D{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 5 + i,
                                                   "slow": 20 + 3 * i},
                                        "promotions": 0}
                    for i in range(6)}, d)
    return d


def _run(state_dir: str) -> dict:
    from quant.live.daily import run_daily_portfolio
    return run_daily_portfolio(SYMS, lookback=250, state_dir=state_dir,
                               require_real_data=False)


# ── ① 미검증 엣지 게이트가 배치에 걸리는가 ──────────────────────


def test_the_unproven_edge_gate_reaches_the_ledger(tmp_path):
    """엣지가 입증되기 전에는 장부의 목표 변동성이 검증치를 못 넘는다."""
    rec = _run(_prep(tmp_path))
    vt = rec["vol_target"]
    assert vt["proven"] is False, (
        "빈 장부인데 엣지가 입증됐다고 기록한다 — 게이트를 안 물어봤다")
    assert vt["target"] <= VERIFY_TARGET_VOL + 1e-9, (
        f"미입증 상태인데 목표 변동성이 {vt['target']}이다 "
        f"(상한 {VERIFY_TARGET_VOL})")
    assert vt["reason"], "왜 이 목표인지 장부에 안 남는다"


def test_the_gate_answer_actually_flows_into_the_batch(tmp_path, monkeypatch):
    """게이트가 다른 답을 주면 배치도 달라져야 한다.

    상수를 박아 넣어도 위 검사는 통과할 수 있다(0.12 ≤ 0.12). 그래서
    게이트의 답을 바꿔 보고 **장부가 따라오는지** 확인한다.
    """
    import quant.risk.portfolio_vol as PV
    monkeypatch.setattr(PV, "target_vol_now",
                        lambda state_dir="state": (0.031, False, "검사용 게이트"))
    vt = _run(_prep(tmp_path))["vol_target"]
    assert vt["target"] == 0.031, (
        f"게이트가 0.031을 줬는데 장부에는 {vt['target']}이 남았다 — "
        "배치가 게이트를 안 쓰고 자기 값을 쓴다")
    assert vt["reason"] == "검사용 게이트"


def test_a_lower_target_actually_buys_less(tmp_path, monkeypatch):
    """장부에만 적고 노출은 그대로인 것을 막는다 — 목표는 실제 크기를 정한다."""
    import quant.risk.portfolio_vol as PV

    def _run_with(target: float) -> float:
        monkeypatch.setattr(PV, "target_vol_now",
                            lambda state_dir="state": (target, False, "검사용"))
        return _run(_prep(tmp_path / f"t{target}"))["weight"]

    small, big = _run_with(0.004), _run_with(0.008)
    assert small > 0, "노출이 0이면 아래 비교가 헛것이 된다"
    assert abs(big - small * 2) < 1e-3, (
        f"목표를 2배로 올렸는데 총노출이 비례하지 않는다: {small} → {big}")


# ── ② 한 종목 과집중 상한이 실제로 자르는가 ────────────────────


def test_one_symbol_cannot_take_the_whole_budget(tmp_path, monkeypatch):
    """HRP가 한 종목에 90%를 줘도 배분은 3/n에서 잘려야 한다.

    쏠림은 HRP의 정상 동작이다(저변동 종목에 자본을 몬다). 그래서 이
    검사는 HRP를 고장 내는 것이 아니라 **HRP가 실제로 하는 일**을 넣고
    상한이 그것을 자르는지 본다.
    """
    import quant.live.daily as D
    n = len(SYMS)
    cap = 3.0 / n
    lopsided = {f"synthetic:D{i}": (0.9 if i == 0 else 0.1 / (n - 1))
                for i in range(n)}
    assert lopsided["synthetic:D0"] > cap, "전제가 깨졌다 — 상한이 안 걸린다"
    monkeypatch.setattr(D, "_hrp_slices", lambda rets, k: dict(lopsided))

    rec = _run(_prep(tmp_path))
    assert rec["alloc_method"] == "hrp", "패치가 안 먹었다 — 검사가 헛돈다"
    worst = max(rec["alloc"].values())
    assert worst <= cap + 1e-9, (
        f"한 종목이 배분 예산의 {worst:.1%}를 가져갔다 — 상한 {cap:.1%}가 "
        "구속하지 않는다")


def test_the_cap_does_not_quietly_inflate_the_budget(tmp_path, monkeypatch):
    """상한 초과분을 재분배하면 총예산이 커진다 — 잘라낸 만큼은 버린다."""
    import quant.live.daily as D
    n = len(SYMS)
    lopsided = {f"synthetic:D{i}": (0.9 if i == 0 else 0.1 / (n - 1))
                for i in range(n)}
    monkeypatch.setattr(D, "_hrp_slices", lambda rets, k: dict(lopsided))
    rec = _run(_prep(tmp_path))
    assert sum(rec["alloc"].values()) <= 1.0 + 1e-9, (
        f"배분 예산 합이 {sum(rec['alloc'].values()):.4f} — 1.0을 넘었다")
