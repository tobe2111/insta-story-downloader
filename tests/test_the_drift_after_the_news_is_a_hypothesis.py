"""실적 발표 후 표류(PEAD) — 가설 우선 후보 2호 (2026-08-23 수집 라운드).

가설: 좋은 실적에 시장이 덜 반응하고(정보의 점진적 확산), 기관이 물량을
며칠에 걸쳐 나눠 집행해(분할 집행 = 가격에 둔감한 매수) 가격이 발표 방향으로
몇 주 더 움직인다. 발라·브라운 1968 이래 문서화된 현상이지만, **우리 종목·
우리 기간에서 통하는지는 오디션만 답한다.**

재료 실측(2026-08-23): state/earnings.json 캐시에 미국 종목당 발표일 25건,
2020~2026 — 백테스트 창 전체를 덮는다. 파이프라인이 캐시에서 컬럼을 붙이므로
백테스트에 네트워크가 없다.

지켜야 할 약속:
- 발표일 당일 반응이 문턱을 넘으면 다음 hold_days 봉 보유, 아니면 관망.
- 발표일 컬럼이 없는 시장(한국·코인)은 **전부 관망** — "발표가 없었다"와
  "몰랐다"를 같게 취급하지 않는다(0으로 지어내지 않음).
- 롱 전용(숏 표류는 공매도 제약으로 실전 재현이 안 된다).
- 미래 봉이 과거 판단을 못 바꾼다.
- 부착 함수는 캐시만 읽는다 — 네트워크 없음.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.data.earnings import attach_earnings_days        # noqa: E402
from quant.strategies.pead import PEADStrategy              # noqa: E402


def _df(closes, earn_at=None):
    c = np.asarray([float(x) for x in closes])
    idx = pd.date_range("2026-01-05", periods=len(c), freq="B")
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": np.full(len(c), 1e6)}, index=idx)
    if earn_at is not None:
        col = np.zeros(len(c))
        for i in earn_at:
            col[i] = 1.0
        df["earn_day"] = col
    return df


def test_a_big_positive_reaction_starts_the_drift_hold():
    closes = [100] * 3 + [104] + [104] * 30          # 3번 봉에서 +4% 발표 반응
    s = PEADStrategy(min_jump=0.02, hold_days=5).generate_signals(
        _df(closes, earn_at=[3]))
    assert float(s.iloc[2]) == 0.0, "발표 전인데 들고 있다"
    assert float(s.iloc[3]) == 1.0, "발표일 마감에 진입하지 않았다"
    assert float(s.iloc[7]) == 1.0, "보유 창 안인데 내렸다"
    assert float(s.iloc[8]) == 0.0, "hold_days가 지났는데 들고 있다"


def test_a_small_or_negative_reaction_is_ignored():
    small = _df([100] * 3 + [101] + [101] * 10, earn_at=[3])    # +1% < 문턱
    drop = _df([100] * 3 + [95] + [95] * 10, earn_at=[3])       # −5% (롱 전용)
    for df, why in ((small, "문턱 미달"), (drop, "음수 반응")):
        s = PEADStrategy(min_jump=0.02, hold_days=5).generate_signals(df)
        assert float(s.abs().max()) == 0.0, f"{why}인데 샀다"


def test_a_jump_without_an_announcement_is_not_news():
    """발표일 아닌 날의 +4%는 그냥 변동이다 — 가설의 재료가 아니다."""
    s = PEADStrategy(min_jump=0.02, hold_days=5).generate_signals(
        _df([100] * 3 + [104] + [104] * 10, earn_at=[]))
    assert float(s.abs().max()) == 0.0


def test_a_market_without_the_calendar_stays_flat():
    """컬럼이 없으면 전부 관망 — '몰랐다'를 '발표 없음'으로 지어내지 않는다."""
    s = PEADStrategy().generate_signals(_df([100] * 3 + [110] + [110] * 10))
    assert float(s.abs().max()) == 0.0


def test_tomorrow_cannot_change_today():
    closes = [100] * 3 + [104] + [104] * 30
    short = PEADStrategy(hold_days=5).generate_signals(
        _df(closes[:10], earn_at=[3]))
    longer = PEADStrategy(hold_days=5).generate_signals(
        _df(closes, earn_at=[3]))
    assert list(short) == list(longer)[:10], "미래 봉이 과거 판단을 바꿨다"


def test_it_never_goes_short_and_refuses_nonsense():
    assert PEADStrategy(allow_short=True).allow_short is False
    for mj, hd in ((0.0, 20), (0.6, 20), (0.02, 0), (0.02, 999)):
        with pytest.raises(ValueError):
            PEADStrategy(min_jump=mj, hold_days=hd)


def test_the_attachment_reads_the_cache_and_never_invents(tmp_path):
    (tmp_path / "earnings.json").write_text(json.dumps(
        {"AAPL": {"dates": ["2026-01-07"], "fetched": "2026-08-23"}}), "utf-8")
    df = _df([100] * 5)
    out = attach_earnings_days(df, "AAPL", str(tmp_path))
    assert float(out["earn_day"].sum()) == 1.0
    assert str(out.index[out["earn_day"] > 0][0].date()) == "2026-01-07"
    # 캐시에 없는 종목 — 컬럼 자체를 안 붙인다(0으로 지어내지 않음)
    out2 = attach_earnings_days(df, "TSLA", str(tmp_path))
    assert "earn_day" not in out2.columns
    # 캐시 파일이 깨져도 조용히 생략(부착 실패가 매매를 못 막는다)
    (tmp_path / "earnings.json").write_text("{{{", "utf-8")
    out3 = attach_earnings_days(df, "AAPL", str(tmp_path))
    assert "earn_day" not in out3.columns


def test_the_attachment_never_touches_the_network():
    import inspect

    src = inspect.getsource(attach_earnings_days)
    for banned in ("yfinance", "_fetch", "requests", "urlopen"):
        assert banned not in src, (
            f"부착 함수가 {banned}를 부른다 — 오디션 백테스트는 오프라인이어야 "
            "하고, 발표일은 바뀌지 않는 과거 사실이라 캐시로 충분하다")


def test_the_hypothesis_is_written_where_the_rule_lives():
    src = (ROOT / "quant" / "strategies" / "pead.py").read_text("utf-8")
    for word in ("가설", "나눠 집행", "생존 편향", "대용치"):
        assert word in src, f"소스에 '{word}'가 없다"
    import re
    claims = re.findall(r"(CAGR|승률|연평균|\d+\s*%\s*(수익|상승))", src)
    assert not claims, f"바깥 성적을 본문에 적었다: {claims}"


def test_the_column_does_not_leak_into_the_ml_feature_matrix():
    """earn_day가 x_ 접두가 아닌 것은 실수가 아니라 계약이다.

    ml._features()는 x_ 컬럼을 전부 ML 입력으로 자동 포함한다. 발표일
    표식은 PEAD 전용 재료이지 ML 거시 피처가 아니다 — x_를 붙이는 순간
    기존 ML 챔피언 전원의 피처 집합이 가설도 등록도 없이 바뀐다.
    """
    from quant.strategies.ml import _features

    df = _df([100.0 + i for i in range(40)], earn_at=[5])
    feats = _features(df)
    assert "earn_day" not in feats.columns, (
        "발표일 표식이 ML 피처 행렬에 올라탔다 — 등록 안 된 시행이다")
    assert not any(str(c).startswith("x_earn") for c in feats.columns)


def test_it_is_wired_into_both_pipelines_and_the_ring():
    for f in ("quant/live/retrain.py", "quant/live/daily.py"):
        src = (ROOT / f).read_text("utf-8")
        assert "attach_earnings_days(df, symbol, state_dir)" in src, (
            f"{f}: 발표일 컬럼을 안 붙인다 — 전략은 있는데 재료가 없다")
    from quant.live.retrain import build_challengers, champion_spec
    ring = build_challengers(champion_spec("crypto", "BTC/USDT"),
                             seed="x", evolve=True)
    assert any(c.get("strategy") == "pead" for c in ring), "링에 안 서 있다"
