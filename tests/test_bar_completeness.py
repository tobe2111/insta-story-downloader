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
    """주식 쪽 방어가 사라지면 같은 결함이 주식으로 번진다.

    ⚠️ **이 검사는 원래 문자열 세기였다**(감사 183에서 고침). 이렇게 있었다.

        assert src.count("_drop_unclosed") >= 2, "정의만 있고 호출되지 않는다"

    그런데 `stock.py`에는 그 호출을 **설명하는 주석**이 있고, 거기에도
    `_drop_unclosed`가 적혀 있다. 그래서 진짜 호출을 통째로 지워도 개수가
    2를 유지해 검사가 통과했다 — 변이 시험이 그대로 빠져나갔다.
    FROZEN_IDEAS ㊵의 자기참조 함정이 자기 자신에게 걸린 것이다.

    이제 **행동으로** 확인한다. 마감 전 '오늘' 봉이 붙은 프레임을 넣고
    그 봉이 실제로 잘려 나가는지 본다.
    """
    import pandas as pd

    from quant.data.stock import StockDataProvider

    p = StockDataProvider(market="us_stock")
    # 미국 정규장 마감은 16:00 ET — 12:00 ET는 장중이라 '오늘' 봉이 미완결
    now = pd.Timestamp("2026-08-12 12:00", tz="America/New_York")
    idx = pd.DatetimeIndex(["2026-08-10", "2026-08-11", "2026-08-12"])
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                       "close": [10.0, 11.0, 12.0], "volume": 1e6}, index=idx)

    got = p._drop_unclosed(df, now=now)
    assert list(got.index.strftime("%m-%d")) == ["08-10", "08-11"], (
        f"장중인데 오늘(08-12) 봉이 남았다: {list(got.index)}")

    # 대조군 — 마감 후에는 그날 봉을 인정해야 한다(늘 자르면 하루가 사라진다)
    after = p._drop_unclosed(df, now=pd.Timestamp("2026-08-12 17:00",
                                                  tz="America/New_York"))
    assert list(after.index.strftime("%m-%d")) == ["08-10", "08-11", "08-12"]


def test_the_stock_fetch_path_actually_calls_the_guard():
    """정의만 있고 **불리지 않으면** 방어가 아니다 — 수집 경로로 확인한다.

    위 검사는 함수가 옳은지만 본다. 감사 120의 교훈대로 부품 검사와 배선
    검사는 다른 것이라, 여기서는 `get_ohlcv`가 그 함수를 지나는지 본다.
    """
    import pandas as pd

    from quant.data.stock import StockDataProvider

    seen: list = []
    p = StockDataProvider(market="us_stock")
    idx = pd.DatetimeIndex(["2026-08-10", "2026-08-11"])
    frame = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                          "close": [10.0, 11.0], "volume": 1e6}, index=idx)

    p._via_yfinance = lambda *a, **k: frame.copy()       # 첫 소스가 바로 성공
    orig = p._drop_unclosed
    p._drop_unclosed = lambda df, now=None: seen.append(1) or orig(df, now)

    p.get_ohlcv("SPY", "1d", limit=10)
    assert seen, "get_ohlcv가 _drop_unclosed를 지나지 않는다 — 방어가 배선 안 됨"


def test_no_source_string_check_is_satisfied_by_comments_alone():
    """문자열 세기 검사가 **주석만으로** 충족되면 그건 검사가 아니다 (감사 183).

    이 파일의 `_drop_unclosed` 검사가 정확히 그랬다 — 진짜 호출을 지워도
    그 호출을 설명하는 주석에 같은 이름이 적혀 있어 개수가 유지됐다.
    변이 시험이 그대로 빠져나갔다(FROZEN_IDEAS ㊵ 자기참조 함정).

    여기서는 `tests/`의 모든 `.count("X") >= N` 중 식별자꼴 토큰을 모아,
    **주석을 걷어낸 코드만으로도** 그 개수가 나오는지 본다. 안 나오면
    그 검사는 주석에 기대고 있다는 뜻이다.
    """
    import re

    counts: dict[str, int] = {}
    for f in sorted(ROOT.glob("tests/*.py")):
        for m in re.finditer(r'\.count\((["\'])(.+?)\1\)\s*>=\s*(\d+)',
                             f.read_text(encoding="utf-8")):
            tok, need = m.group(2), int(m.group(3))
            if len(tok) >= 6 and re.search(r"[A-Za-z_]{4,}", tok):
                counts[tok] = max(counts.get(tok, 0), need)

    assert counts, "세는 검사를 하나도 못 찾았다 — 이 검사가 헛돈다"

    weak = []
    for tok, need in sorted(counts.items()):
        in_code = in_all = 0
        for s in sorted(ROOT.glob("quant/**/*.py")):
            for ln in s.read_text(encoding="utf-8").splitlines():
                n = ln.count(tok)
                in_all += n
                if not ln.lstrip().startswith("#"):
                    in_code += n
        if in_all >= need > in_code:
            weak.append(f"{tok!r}: 코드에 {in_code}회 · 주석까지 세면 {in_all}회 "
                        f"(검사는 {need}회 요구)")
    assert not weak, ("주석에 기대는 문자열 검사가 있다 — 진짜 호출이 사라져도 "
                      "통과한다:\n  " + "\n  ".join(weak))


# ── 재는 자를 바꾸면 답이 달라진다 (감사 204) ─────────────────────
#
# `_signal_frame`은 미완결 봉을 빼는 자리인데, `bar_status`를 부를 때
# **타임프레임을 안 넘겨 항상 일봉 자로 쟀다.** 같은 파일의 다른 두 자리
# (장부의 bar_partial, 기록용 bs)는 넘기고 있었는데 여기만 빠졌다(㉞).
#
# 실측(봇이 1시간봉으로 돌 때, 3시간 전에 **완성된** 봉):
#     1h 자 → 1.0 (완성)   /   1d 자 → 0.125 (진행 중)  ← 완성 봉이 버려진다


def test_the_ruler_matches_the_bar_it_measures():
    from quant.data.barclock import bar_elapsed_fraction

    now = _utc("2026-08-13 12:00:00")
    bar = "2026-08-13 09:00:00"          # 3시간 전에 닫힌 1시간봉
    assert bar_elapsed_fraction(bar, "1h", now) == 1.0, "완성된 봉인데"
    assert bar_elapsed_fraction(bar, "1d", now) < 1.0, "전제가 깨졌다"


def test_signal_frame_measures_with_the_timeframe_it_was_given():
    import pandas as pd

    from quant.live.daily import _signal_frame

    now = pd.Timestamp.now().normalize()
    idx = pd.date_range(end=now - pd.Timedelta(hours=3), periods=12, freq="h")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                       "close": 1.0, "volume": 1.0}, index=idx)
    # 3시간 전에 닫힌 1시간봉 → 뺄 것이 없다
    assert len(_signal_frame("crypto", df, "1h")) == len(df)
    # 대조군 — 같은 프레임을 일봉 자로 재면 마지막 봉을 진행 중으로 본다
    assert len(_signal_frame("crypto", df, "1d")) == len(df) - 1


def test_an_unjudgeable_bar_is_not_called_complete():
    """'모름'과 '완성됨'을 같은 답으로 내면 감사 71의 보호가 조용히 꺼진다."""
    from quant.data.barclock import bar_status

    st = bar_status("crypto", "2026-08-13 09:00:00", "2h",
                    _utc("2026-08-13 12:00:00"))
    assert st is not None, "모르는 타임프레임을 '완성됨'으로 답했다"
    assert st.get("undetermined") is True and st.get("elapsed") is None, st

    # 대조군 — 아는 타임프레임에서 진짜 완성된 봉은 None(=완성)이어야 한다
    assert bar_status("crypto", "2026-08-13 09:00:00", "1h",
                      _utc("2026-08-13 12:00:00")) is None


def test_a_future_bar_says_it_is_from_the_future():
    """미래 봉을 '0% 진행 중'이라고 적지 않는다 — 그럴듯한 숫자는 사실이 아니다."""
    from quant.data.barclock import bar_status

    st = bar_status("crypto", "2026-08-14 00:00:00", "1d",
                    _utc("2026-08-13 12:00:00"))
    assert st and st.get("future_bar") is True, st
    assert "미래" in st["note"]

    # 대조군 — 방금 시작한 (진짜) 봉은 미래 표식이 없어야 한다
    now_bar = bar_status("crypto", "2026-08-13 00:00:00", "1d",
                         _utc("2026-08-13 12:00:00"))
    assert now_bar and not now_bar.get("future_bar") and now_bar["elapsed"] == 0.5
