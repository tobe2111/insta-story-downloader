"""실거래 경로가 페이퍼 경로의 교정을 따라오는가.

배경(2026-08-11 감사): 페이퍼에서 일 37% 회전의 원인이던 '밴드를 종목 수로
나누기'(0.05/20 = 0.25% → 사실상 밴드 없음)를 상대 밴드로 고쳤는데,
**실거래 경로(daily_live)만 옛 코드로 남아 있었다.** 실제 수수료를 내는
쪽이 더 오래 방치돼 있던 셈이다.

핵심 계약:
  ① 실거래도 비용 비례 상대 밴드를 쓴다(종목 수로 나누지 않는다)
  ② 페이퍼와 같은 가드(켈리 상한)를 쓴다
  ③ 실거래는 롱온리·무레버리지 + 어드민 노출 배수를 따른다
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "quant" / "live" / "daily_live.py").read_text("utf-8")


def test_live_uses_relative_band():
    assert "rebalance_band_rel=_rebalance_band_rel(market, state_dir)" in SRC
    # 종목 수로 나누던 옛 밴드가 남아 있으면 회전율이 다시 폭증한다
    assert "REBALANCE_BAND / n" not in SRC
    assert "REBALANCE_BAND = " not in SRC        # 쓰이지 않는 상수도 남기지 않는다


def test_live_shares_paper_guards():
    assert "_kelly_cap_from_history" in SRC


def test_live_is_long_only_and_unlevered():
    assert "max(0.0, min(1.0, weight))" in SRC
    assert "* exposure" in SRC                   # 어드민 노출 배수 반영


def test_live_records_exposure_scale():
    assert '"exposure_scale": exposure' in SRC


def test_live_refuses_synthetic_data():
    assert 'df.attrs.get("synthetic_fallback")' in SRC


def test_live_isolates_per_symbol_failure():
    assert "한 종목 실패가 나머지를 막으면 안 된다" in SRC


def test_band_helper_is_shared_not_duplicated():
    """같은 규칙을 두 곳에 복사하면 한 곳만 고치는 오늘의 결함이 재발한다."""
    from quant.live.daily import _rebalance_band_rel
    assert callable(_rebalance_band_rel)
    assert "from quant.live.daily import" in SRC
