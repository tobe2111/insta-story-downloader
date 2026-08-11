"""포트폴리오 목표 변동성 + 판정 게이트 계약 검사.

핵심 계약:
  ① 사전 변동성은 공분산으로 — 분산이 실제로 줄인 리스크가 반영돼야
     그만큼 되돌려 키울 수 있다
  ② 스케일의 진짜 한도는 배수가 아니라 총노출(레버리지 금지선)
  ③ 엣지 미입증이면 게이트가 검증 목표로 잠근다 — 소유자의 명시적
     우회(risk_override_ack)만 그 잠금을 연다
  ④ 잔돈 주문은 차단하되 청산은 언제나 허용
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quant.risk.portfolio_vol as pv  # noqa: E402
from quant.risk.portfolio_vol import (  # noqa: E402
    MAX_GROSS_EXPOSURE,
    VERIFY_TARGET_VOL,
    ex_ante_vol,
    target_vol_now,
    vol_scale,
)


def _rets(seed: float, n: int = 60):
    """결정적 의사난수 수익률 — 재현 가능해야 테스트가 장부가 된다."""
    out, x = [], seed
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        out.append((x / 2147483648 - 0.5) * 0.04)
    return out


def test_ex_ante_vol_reflects_diversification():
    """같은 총노출이라도 여러 종목에 나누면 사전 변동성이 낮아진다."""
    solo = {"a": 0.4}
    split = {f"s{i}": 0.1 for i in range(4)}
    rmap = {"a": _rets(1)}
    rmap.update({f"s{i}": _rets(i + 7) for i in range(4)})
    v_split = ex_ante_vol(split, rmap)
    assert v_split is not None
    # 단일 종목은 종목이 2개 미만이라 None — 분산 케이스만 값이 나온다
    assert ex_ante_vol(solo, rmap) is None
    assert v_split > 0


def test_scale_raises_underrisked_portfolio():
    """목표보다 사전 변동성이 낮으면 배수가 1보다 커진다(되돌려 키운다)."""
    w = {f"s{i}": 0.01 for i in range(5)}
    rmap = {f"s{i}": _rets(i + 3) for i in range(5)}
    ex = ex_ante_vol(w, rmap)
    scale, ex2 = vol_scale(w, rmap, target=ex * 3)
    assert ex2 == pytest.approx(ex)
    assert scale > 1.0


def test_low_vol_estimate_does_not_cap_below_target():
    """사전 변동성이 아주 낮아도 배수 상한이 먼저 걸리면 안 된다.

    실측에서 배수 25배가 노출 상한보다 먼저 걸려 총노출이 34%에서 멈추는
    것을 확인했다 — 한도는 배수가 아니라 노출이어야 한다.
    """
    w = {f"s{i}": 0.02 for i in range(5)}       # 총노출 0.10
    rmap = {f"s{i}": [x * 0.001 for x in _rets(i + 5)] for i in range(5)}
    scale, ex = vol_scale(w, rmap, target=0.12)
    assert ex is not None and ex < 0.01         # 아주 낮은 사전 변동성
    gross_after = sum(abs(v) for v in w.values()) * scale
    assert gross_after == pytest.approx(MAX_GROSS_EXPOSURE, rel=1e-6)


def test_gross_exposure_is_the_real_cap():
    """배수가 아니라 총노출이 한도 — 레버리지 금지선을 넘지 않는다."""
    w = {f"s{i}": 0.05 for i in range(4)}          # 총노출 0.2
    rmap = {f"s{i}": _rets(i + 11) for i in range(4)}
    scale, _ = vol_scale(w, rmap, target=99.0)     # 터무니없이 큰 목표
    gross_after = sum(abs(v) for v in w.values()) * scale
    assert gross_after <= MAX_GROSS_EXPOSURE + 1e-9
    # 상한이 3배 같은 임의 배수가 아니라 노출로 결정됐는지
    assert scale == pytest.approx(MAX_GROSS_EXPOSURE / 0.2, rel=1e-6)


def test_unproven_edge_locks_target(tmp_path, monkeypatch):
    monkeypatch.setattr("quant.risk.portfolio_vol.edge_proven",
                        lambda sd="state": (False, "표본 부족"))
    monkeypatch.setattr("quant.utils.settings.load_settings",
                        lambda: {"portfolio_target_vol": 0.30})
    tgt, proven, _why = target_vol_now(str(tmp_path))
    assert proven is False
    assert tgt == VERIFY_TARGET_VOL          # 설정값 0.30이 잠금에 막힌다


def test_owner_override_opens_the_lock(tmp_path, monkeypatch):
    """소유자의 명시적 확인이 있으면 잠금이 열린다 — 다만 사유에 표시된다."""
    monkeypatch.setattr("quant.risk.portfolio_vol.edge_proven",
                        lambda sd="state": (False, "표본 부족"))
    monkeypatch.setattr("quant.utils.settings.load_settings",
                        lambda: {"portfolio_target_vol": 0.05,
                                 "risk_override_ack": True})
    tgt, proven, why = target_vol_now(str(tmp_path))
    assert proven is False and tgt == pytest.approx(0.05)
    assert "우회" in why


def test_dust_order_blocked_but_liquidation_allowed():
    from quant.live.daily import MIN_ORDER_KRW, _is_dust_order

    class _P:
        def __init__(self, q): self.quantity = q

    class _B:
        def __init__(self, q=0.0): self._q = q
        def get_position(self, key): return _P(self._q)

    eq = 80_000.0
    # 신규 40원어치 매수 → 잔돈이라 차단
    assert _is_dust_order(_B(), "kr_stock:A", 40 / eq, 1000.0, eq)
    # 충분히 큰 주문은 통과
    assert not _is_dust_order(_B(), "kr_stock:A", 5000 / eq, 1000.0, eq)
    # 이미 보유 중인데 목표 0 → 청산은 잔돈이어도 허용
    assert not _is_dust_order(_B(q=0.04), "kr_stock:A", 0.0, 1000.0, eq)
    assert MIN_ORDER_KRW > 0


# ── 실제 관측값 회귀 — 6.8% 마비가 100%로 교정되는가 ───────────
#
# 2026-08-10 실측: 통합 계좌 총노출 6.8%, 실현 변동성 연 0.6%. 8만원 중
# 5천원만 굴린 셈이고, 그 기록은 "실제로 굴리면 어떻게 되는가"에 답하지
# 못한다. 아래는 그날의 배분과 현실적인 변동성 구조로 교정 사슬 전체가
# 의도대로 도는지 고정한다 — 상수 하나만 잘못 바꿔도 여기서 깨진다.


def _market_like_returns(keys, n=90, seed=11):
    """공통 시장 요인 + 시장별 개별 변동성(코인 60%·미국 22%·한국 25%)."""
    import math
    import random
    rng = random.Random(seed)
    sd = {"crypto": 0.60, "us_stock": 0.22, "kr_stock": 0.25}
    mkt = [rng.gauss(0, 0.008) for _ in range(n)]
    return {k: [0.6 * mkt[i]
                + rng.gauss(0, sd.get(k.split(":")[0], 0.25) / math.sqrt(252))
                for i in range(n)] for k in keys}


def test_observed_paralysis_is_corrected_to_full_exposure():
    keys = [f"crypto:C{i}" for i in range(5)] \
        + [f"us_stock:U{i}" for i in range(9)] \
        + [f"kr_stock:K{i}" for i in range(6)]
    pre_w = {k: 0.068 / len(keys) for k in keys}      # 실측 총노출 6.8%
    rets = _market_like_returns(keys)

    ex = pv.ex_ante_vol(pre_w, rets)
    assert ex is not None and ex < 0.02, "6.8% 노출인데 변동성이 2%를 넘을 리 없다"

    scale, _ = pv.vol_scale(pre_w, rets, pv.VERIFY_TARGET_VOL)
    gross = sum(abs(w) for w in pre_w.values()) * scale
    assert abs(gross - pv.MAX_GROSS_EXPOSURE) < 1e-9, "교정 후 전액 투자여야 한다"

    # 한도는 배수가 아니라 노출이어야 한다 — 배수 상한이 먼저 걸리면
    # 목표에 영원히 못 닿는다(초기 구현에서 실제로 겪은 결함).
    assert pv.VERIFY_TARGET_VOL / ex < pv.MAX_VOL_SCALE


def test_ex_ante_vol_needs_enough_common_history():
    """표본이 얇으면 추정하지 않는다 — 모르면 건드리지 않는다."""
    keys = ["a:1", "a:2"]
    short = {k: [0.01, -0.01, 0.005] for k in keys}
    assert pv.ex_ante_vol({k: 0.5 for k in keys}, short) is None
    # 그때 배수는 1.0(무개입)이라 노출이 갑자기 커지지 않는다
    scale, ex = pv.vol_scale({k: 0.5 for k in keys}, short, 0.12)
    assert scale == 1.0 and ex is None
