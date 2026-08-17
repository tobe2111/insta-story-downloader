"""브로커 조회가 실패했을 때, 실패가 '보유 0'으로 둔갑하지 않는가.

2026-08-11 감사 53. `except Exception: cur_qty = 0.0` 형태의 폴백을 전수로
훑다가 나온 계열이다. 조회 실패를 0으로 치는 것은 편해 보이지만, 0은
'없음'이라는 **측정값**이라 안전장치들이 그 값을 믿고 정반대로 움직인다.

  ① 잔돈 주문 차단: 목표가 0(청산)인데 보유를 0으로 오인하면 차액도 0이라
     '잔돈'으로 분류돼 **청산 주문이 통째로 생략된다.** 함수 docstring이
     "빠져나오는 길을 막으면 덫이 된다"고 적어 둔 바로 그 일이 조회 실패
     한 번에 일어난다.
  ② 재조정 쿨다운: 보유를 0으로 오인하면 목표 대비 이탈이 100%로 계산돼
     '큰 이탈은 즉시 대응' 예외에 걸린다. 브로커가 불안정한 날일수록 더
     많이 매매하게 되는, 회전율 통제의 정확한 반대다.
  ③ 의회 다양성 강제: 상관을 못 재면 0(무상관)으로 쳐서 후보가 통과한다.
     같은 베팅에 두 자리를 주지 않겠다는 가드가, 실패할 때 열린다.

셋 다 공통점은 '모름'을 '안전한 값'으로 반올림했다는 것이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import _is_dust_order  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class _BrokenBroker:
    """포지션 조회가 항상 실패하는 브로커(네트워크 장애·인증 만료 등)."""

    def get_position(self, key):
        raise RuntimeError("조회 실패")


class _Holding:
    def __init__(self, qty):
        self.quantity = qty


class _OkBroker:
    def __init__(self, qty):
        self._qty = qty

    def get_position(self, key):
        return _Holding(self._qty)


# ── ① 청산 봉쇄 ───────────────────────────────────────────────


def test_broker_failure_never_blocks_a_liquidation():
    """목표 0(청산)인데 조회가 실패해도 주문을 막지 않는다."""
    assert _is_dust_order(_BrokenBroker(), "kr_stock:005930",
                          0.0, 70_000.0, 80_000.0) is False


def test_broker_failure_does_not_classify_anything_as_dust():
    """모를 때는 잔돈이 아니라고 본다 — 어떤 목표든 주문을 막지 않는다."""
    for target in (0.0, 0.001, 0.5, -0.3):
        assert _is_dust_order(_BrokenBroker(), "k", target,
                              70_000.0, 80_000.0) is False, target


def test_dust_logic_still_works_when_broker_answers():
    """정상 조회 시의 판정은 그대로 — 폴백만 바꿨지 규칙은 안 바꿨다."""
    # 목표 0.5×80,000 = 40,000원, 보유 없음 → 잔돈 아님
    assert _is_dust_order(_OkBroker(0.0), "k", 0.5, 70_000.0, 80_000.0) is False
    # 목표가 보유와 거의 같으면(차액 0) 잔돈
    assert _is_dust_order(_OkBroker(1.0), "k", 70_000.0 / 80_000.0,
                          70_000.0, 80_000.0) is True
    # 보유 중인데 목표 0 = 청산 → 언제나 허용
    assert _is_dust_order(_OkBroker(1.0), "k", 0.0, 70_000.0, 80_000.0) is False


# ── ② 쿨다운이 조회 실패로 무력화되지 않는다 ──────────────────


def test_cooldown_path_skips_symbol_on_position_read_failure():
    src = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    block = src.split("# 재조정 쿨다운")[1].split("_in_cooldown(")[0]
    assert "skipped_why[key]" in block, "조회 실패가 기록 없이 넘어간다"
    assert "보유 조회 실패" in block
    assert "continue" in block
    # 예전의 '조회 실패는 없음으로' 주석·동작이 남아 있으면 안 된다
    assert "조회 실패는 '없음'으로" not in src


# ── ③ 의회 다양성 가드는 실패 시 닫힌다 ───────────────────────


def test_parliament_correlation_failure_assumes_duplicate():
    """상관을 못 재면 '무상관(통과)'이 아니라 '중복(탈락)'으로 본다.

    ⚠️ 2026-08-14 이전 이 검사는 `except` 분기에 `c = 1.0`이라는 **글자가
    있는지**만 봤다. 그래서 초록이었지만 정작 흔한 경로는 열려 있었다 —
    pandas의 corr는 한쪽 분산이 0이면 예외를 던지지 않고 조용히 **NaN**을
    돌려주고, 판정이 `c == c and c > CORR_CAP`이라 NaN은 `c == c`에서
    False가 되어 '중복 아님'으로 통과했다. 주석이 막겠다고 적어 둔 바로 그
    방향이었다.

    ⚠️⚠️ 2026-08-17(감사 276): **그 판정식마저 무력해졌다.** pandas 3.0부터
    한쪽이 상수인 계열의 상관이 NaN이 아니라 0에 가까운 부동소수(6.4e-18)로
    나온다. 즉 '못 잰 것'이 이제 **'완벽하게 무상관'**으로 읽히고, 그건
    다양성 판정에서 가장 좋은 점수다 — 가드가 막으려던 방향으로 정확히,
    그리고 이번에는 NaN 검사를 통과하면서 열렸다.

    두 번 같은 자리에서 당했다. 그래서 이제 **글자도 판정식도 아니라 값으로**
    본다 — 상수 계열을 실제로 넣어 보고 '중복'이 나오는지 확인한다.
    라이브러리가 무엇을 돌려주든 우리 답은 같아야 한다.
    """
    import numpy as np
    import pandas as pd

    from quant.live.parliament import safe_corr

    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    live = pd.Series(np.random.default_rng(7).normal(0, 0.01, len(idx)), index=idx)
    flat = pd.Series(0.001, index=idx)          # 분산 0 — 상관이 정의되지 않는다

    # 라이브러리가 NaN을 안 준다는 사실 자체를 못 박아 둔다. 이 줄이 깨지면
    # pandas가 또 바뀐 것이고, 그때 이 검사는 여전히 옳은 답을 요구한다.
    raw = float(flat.corr(live))
    assert raw == raw, ("pandas가 다시 NaN을 돌려준다 — 그래도 아래 계약은 "
                        "그대로여야 한다")

    assert safe_corr(flat, live) != safe_corr(flat, live), (
        "상수 계열의 상관을 '무상관'으로 본다 — 계산 실패가 곧 통과가 된다")
    assert safe_corr(live, flat) != safe_corr(live, flat), "순서만 바꿔도 같아야 한다"
    # 대조군 — 멀쩡한 두 계열은 실제 값을 돌려줘야 한다. 다 NaN으로 막으면
    # 다양성 판정이 통째로 꺼지고, 그것도 같은 종류의 고장이다.
    other = pd.Series(np.random.default_rng(8).normal(0, 0.01, len(idx)), index=idx)
    c = safe_corr(live, other)
    assert c == c and -1.0 <= c <= 1.0, c

    src = (ROOT / "quant" / "live" / "parliament.py").read_text(encoding="utf-8")
    assert "safe_corr(rets[i], rets[j])" in src, (
        "승격 쪽 상관 게이트가 판정을 한 곳에서 안 쓴다")
    assert "safe_corr(r, rets[j])" in src, (
        "다양성 쪽 상관 게이트가 판정을 한 곳에서 안 쓴다")
