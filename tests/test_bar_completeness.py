"""결정에 쓴 봉이 다 만들어진 봉이었는가 — 그리고 아니면 그렇게 적는가.

2026-08-11 감사 56. 주식 제공자에는 `_drop_unclosed`가 있어 장 마감 전의
'오늘' 봉을 버린다. 코인 제공자에는 없다. 코인은 24시간 돌아가므로 UTC
일봉의 '오늘' 봉은 **항상** 진행 중이고, 새벽 배치는 그 봉을 마지막 봉으로
받아 그대로 판단에 쓴다.

저장된 스냅샷으로 실측한 결과(2026-08-07~09):

    코인 : 결정에 쓴 봉 15개 중 **15개**가 확정 봉과 달랐다
           종가 차이 평균 66.8bp(최대 150.8bp)
           고저 레인지 평균 36.2% 축소(최대 88.6%)
    주식 : 28개 중 0개 — _drop_unclosed가 제대로 막고 있다

레인지가 36% 짧게 잡히면 ATR·GK변동성이 낮게 읽히고, 변동성 타깃 사이징의
분모가 작아져 목표보다 큰 비중이 실린다. 모델도 24시간 봉으로 학습해 놓고
19시간 봉으로 예측하게 된다. 그리고 장부의 price가 그날 일봉 종가가 아니라,
공개 차트와 대조하려는 사람에게는 매일 어긋나 보인다.

이 검사는 '어느 봉으로 판단할지'를 강제하지 않는다(그건 매매 동작을 바꾸는
별개 결정이다). 대신 **그 사실이 장부에 남는지**를 강제한다 — 숨긴 채로
"누구든 검증할 수 있다"고 말하지 않기 위해서다.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.barclock import bar_elapsed_fraction, bar_status  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


# ── 완성도 계산 ───────────────────────────────────────────────


def test_elapsed_fraction_of_a_daily_bar():
    bar = "2026-08-10 00:00:00"
    # 새벽 배치는 19:00 UTC에 돈다 → 그날 봉은 79% 만들어진 상태
    assert bar_elapsed_fraction(bar, "1d", _utc("2026-08-10 19:00:00")) == 0.79166 or \
        abs(bar_elapsed_fraction(bar, "1d", _utc("2026-08-10 19:00:00"))
            - 19 / 24) < 1e-9
    assert bar_elapsed_fraction(bar, "1d", _utc("2026-08-11 00:00:00")) == 1.0
    assert bar_elapsed_fraction(bar, "1d", _utc("2026-08-12 05:00:00")) == 1.0
    # 아직 시작도 안 한 봉(제공자가 미리 내놓는 유령 봉)
    assert bar_elapsed_fraction(bar, "1d", _utc("2026-08-09 12:00:00")) == 0.0


def test_unknown_timeframe_or_bad_input_is_none_not_zero():
    """모르면 '완성됨(1.0)'도 '미완성(0)'도 아닌 None이다."""
    assert bar_elapsed_fraction("2026-08-10", "3d") is None
    assert bar_elapsed_fraction("나쁜 값", "1d") is None
    assert bar_elapsed_fraction(None, "1d") is None


def test_timezone_aware_bars_are_normalized_to_utc():
    a = bar_elapsed_fraction("2026-08-10T00:00:00+00:00", "1d",
                             _utc("2026-08-10 12:00:00"))
    b = bar_elapsed_fraction("2026-08-10 00:00:00", "1d",
                             _utc("2026-08-10 12:00:00"))
    assert a == b == 0.5


# ── 장부에 남기는 기록 ────────────────────────────────────────


def test_partial_crypto_bar_is_recorded():
    st = bar_status("crypto", "2026-08-10 00:00:00", "1d",
                    _utc("2026-08-10 19:00:00"))
    assert st is not None
    assert abs(st["elapsed"] - 19 / 24) < 1e-3
    assert "확정값이 아니" in st["note"]


def test_complete_bar_records_nothing():
    """정상(완성된 봉)일 때는 None — 값이 있다는 것 자체가 고백이다."""
    assert bar_status("crypto", "2026-08-10 00:00:00", "1d",
                      _utc("2026-08-11 03:00:00")) is None


def test_stock_markets_are_not_flagged():
    """주식은 _drop_unclosed가 막으므로 이 장치의 대상이 아니다."""
    for m in ("us_stock", "kr_stock", "synthetic"):
        assert bar_status(m, "2026-08-10 00:00:00", "1d",
                          _utc("2026-08-10 19:00:00")) is None


# ── 두 장부 경로 모두에 배선됐는가 ────────────────────────────


def test_both_ledger_paths_record_partial_bars():
    src = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert "from quant.data.barclock import bar_status" in src
    # 종목별 페이퍼 기록
    assert '"bar_partial": bar_status(market, df.index[-1], timeframe)' in src
    # 통합 계좌 기록
    assert '"bar_partial": partial_bars or None' in src
    assert "partial_bars[key] = bs[\"elapsed\"]" in src


def test_stock_provider_still_drops_unclosed_bars():
    """주식 쪽 방어가 사라지면 같은 결함이 주식으로 번진다."""
    src = (ROOT / "quant" / "data" / "stock.py").read_text(encoding="utf-8")
    assert "def _drop_unclosed" in src
    assert "_drop_unclosed(" in src.split("def _drop_unclosed")[0] or \
        src.count("_drop_unclosed") >= 2, "정의만 있고 호출되지 않는다"
