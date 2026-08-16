"""긴 검증 — 과거를 길게 보되 **그 숫자가 왜 좋은지** 함께 말한다 (감사 256).

사장님 질문: "10년 전 데이터까지 모두 자동으로 보고 학습하는 형태인 거지?"

절반만 맞습니다. **학습창은 늘리지 않습니다** — 250봉 그대로입니다. 10년치로
학습시키면 이미 죽은 패턴(2015년의 시장)을 배웁니다. 늘리는 것은 **검증
구간**뿐입니다: 250봉으로 배우고 다음 구간에서 시험하는 것을 과거 전체에
걸쳐 반복합니다(워크포워드).

그리고 그렇게 얻은 숫자에는 **반드시 붙어야 하는 고지**가 둘 있습니다.

**① 생존 편향.** 10년을 돌리는 이 20종목은 오늘 살아남아 우리가 고른
종목입니다. 10년 전의 우리는 이 20개를 고를 수 없었습니다. 그때 골랐을
종목 중 상장폐지된 것들의 손실은 이 숫자 어디에도 없습니다 — 그래서 실제로
얻을 수 있었던 것보다 **좋게 나옵니다.**

**② 설정도 인샘플.** 챔피언 설정은 최근 데이터에서 뽑혔습니다. 과거 구간에
대해서는 '답을 보고 고른' 설정입니다(감사 240·255와 같은 주의).

이 고지가 빠지면 이 제품의 정체성(선택 편향 없는 공개 실험)이 무너집니다.
그래서 검사가 고지의 존재를 직접 지킵니다.

실측(2026-08-14 스냅샷, 오프라인):

    20종목 · 전체 125구간 중 플러스 78개(62%)
    코인은 구간이 **1개뿐** — 그날 코인 스냅샷이 300봉이라(거래소 이어받기
    수정 이전) 학습창 250을 빼면 50봉만 남는다

그 표본 격차가 보고서에 **그대로 드러난다** — 숨기지 않는 것이 목적이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.walkforward as WF  # noqa: E402
from quant.live.walkforward import (  # noqa: E402
    IN_SAMPLE_NOTE,
    MIN_SEGMENT_BARS,
    SURVIVORSHIP_NOTE,
    format_walkforward,
    long_history,
    segment_scores,
    walkforward_report,
)


def _returns(n: int, value: float = 0.001) -> pd.Series:
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series([value] * n, index=idx)


# ── 구간 나누기 ───────────────────────────────────────────────

def test_the_warmup_is_not_counted_as_a_flat_period():
    """⚠️ 학습창 구간의 0은 성과가 아니라 **아직 시작 안 함**이다.

    안 빼면 첫 구간이 '무성과'로 찍혀 설정이 부당하게 나빠 보인다.
    """
    r = pd.concat([_returns(250, 0.0), _returns(400, 0.001)])
    r.index = pd.date_range("2020-01-01", periods=650, freq="D")
    segs = segment_scores(r, warmup=250, market="us_stock", segments=4)
    assert len(segs) == 4
    assert all(s["total_return"] > 0 for s in segs), segs


def test_a_short_history_gets_no_segments():
    """구간이 표본 미달이면 성적을 만들지 않는다 — 모르면 안 적는다."""
    assert segment_scores(_returns(MIN_SEGMENT_BARS - 1), 0, "crypto") == []


def test_the_number_of_segments_shrinks_with_the_data():
    """코인 실측 장면 — 300봉에서 250을 빼면 구간이 하나뿐이다."""
    segs = segment_scores(_returns(300), warmup=250, market="crypto",
                          segments=8)
    assert len(segs) == 1, f"{len(segs)}구간 — 50봉을 8등분하면 안 된다"


def test_a_flat_series_gets_no_sharpe():
    """변동이 사실상 0이면 샤프를 만들지 않는다.

    ⚠️ `sd <= 0`으로는 못 잡는다 — 같은 값이 늘어선 계열의 표준편차는 부동소수
       상쇄로 1e-19쯤이 되고, 그걸로 나누면 **샤프 수천**이 나온다. 이 모듈의
       첫 판이 실제로 그랬고 이 검사가 잡았다.
    """
    segs = segment_scores(_returns(400, 0.001), warmup=0, market="us_stock",
                          segments=2)
    assert segs and all(s["sharpe"] is None for s in segs), segs


def test_a_varying_series_still_gets_a_sharpe():
    """대조군 — 판정이 지나쳐 진짜 계열까지 막으면 보고서가 빈칸이 된다."""
    idx = pd.date_range("2020-01-01", periods=200, freq="D")
    r = pd.Series([0.01 if i % 2 else -0.005 for i in range(200)], index=idx)
    segs = segment_scores(r, warmup=0, market="us_stock", segments=2)
    assert segs and all(s["sharpe"] is not None and s["sharpe"] > 0
                        for s in segs), segs


def test_the_sign_of_the_segment_follows_the_returns():
    up = segment_scores(_returns(200, 0.002), 0, "us_stock", 2)
    down = segment_scores(_returns(200, -0.002), 0, "us_stock", 2)
    assert all(s["total_return"] > 0 for s in up)
    assert all(s["total_return"] < 0 for s in down)


# ── 가짜 데이터를 10년 성적으로 둔갑시키지 않는가 ─────────────

def test_synthetic_data_is_refused(monkeypatch):
    """합성 시세로 만든 10년 성적은 그럴듯한 거짓말이다."""
    class _P:
        def get_ohlcv(self, *a, **k):
            df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0],
                               "close": [1.0], "volume": [1.0]},
                              index=pd.date_range("2020-01-01", periods=1))
            df.attrs["synthetic_fallback"] = True
            return df

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    assert long_history("crypto", "BTC/USDT", 2500) is None


def test_a_dead_feed_is_not_an_exception(monkeypatch):
    """한 종목 수신 실패가 보고서 전체를 죽이면 안 된다."""
    class _P:
        def get_ohlcv(self, *a, **k):
            raise RuntimeError("거래소 점검")

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    assert long_history("crypto", "BTC/USDT", 2500) is None


def test_real_data_passes_through(monkeypatch):
    """대조군 — 거부가 지나쳐 진짜 시세까지 막으면 보고서가 영영 빈다."""
    idx = pd.date_range("2020-01-01", periods=300, freq="D")
    good = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                         "close": 1.0, "volume": 1.0}, index=idx)

    class _P:
        def get_ohlcv(self, *a, **k):
            return good

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    got = long_history("us_stock", "SPY", 2500)
    assert got is not None and len(got) == 300


# ── 고지가 붙어 있는가 (③ 생존 편향) ─────────────────────────

def _offline():
    rep = walkforward_report("state", fetch=False, bars=800)
    if not rep:
        pytest.skip("스냅샷 없음")
    return rep


def test_the_report_always_carries_the_survivorship_warning():
    """이 표식이 빠지면 화면이 '실제로 벌 수 있었던 돈'으로 읽는다."""
    rep = _offline()
    assert rep["survivorship_biased"] is True
    assert rep["in_sample_setting"] is True
    assert SURVIVORSHIP_NOTE in rep["notes"] and IN_SAMPLE_NOTE in rep["notes"]


def test_the_warning_text_names_the_actual_problem():
    """'주의하세요' 같은 빈 경고는 경고가 아니다 — 무엇이 왜인지 적는다."""
    assert "살아남은 종목" in SURVIVORSHIP_NOTE
    assert "좋게 나옵니다" in SURVIVORSHIP_NOTE
    assert "최근 데이터에서 뽑혔" in IN_SAMPLE_NOTE


def test_the_human_line_shows_the_warning_too():
    text = format_walkforward(_offline())
    assert "긴 검증" in text
    assert "살아남은 종목" in text, "사람이 읽는 문장에서 고지가 사라졌다"


def test_the_report_says_which_data_it_used():
    """스냅샷으로 돌았는지 실데이터로 돌았는지 안 적으면 재현이 안 된다."""
    rep = _offline()
    assert rep["requested_bars"] == 800
    for r in rep["symbols"]:
        assert r["source"] in ("실데이터", "스냅샷")
        assert r["from"] <= r["to"] and r["bars"] > 0


def test_a_shorter_history_shows_up_as_fewer_segments():
    """표본 격차를 **숨기지 않는다**.

    실측(2026-08-14): 코인 스냅샷이 300봉이라(거래소 이어받기 수정 이전)
    학습창 250을 뺀 50봉으로 구간이 하나뿐이었다. 주식은 여덟이었다.
    봉이 짧으면 구간 수가 줄어드는 것이 보고서에서 바로 보여야 한다.
    """
    rep = _offline()
    pairs = sorted((r["bars"], r["n_segments"]) for r in rep["symbols"])
    assert pairs[0][1] <= pairs[-1][1], (
        f"짧은 과거가 더 많은 구간을 받았다: {pairs[0]} vs {pairs[-1]}")
    for r in rep["symbols"]:
        assert r["n_segments"] >= 1 and r["bars"] >= r["warmup"]


def test_an_empty_state_is_not_an_error():
    assert walkforward_report("/tmp/quant-없는곳-255", fetch=False) == {}
    assert "아직 없습니다" in format_walkforward({})


# ── 관찰이지 판정이 아니다 ────────────────────────────────────

def test_it_does_not_change_promotion():
    """생존 편향이 있는 값으로 승격을 바꾸면 그 편향이 매매에 들어간다."""
    retrain = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "walkforward" not in retrain


def test_the_training_window_is_not_stretched():
    """늘리는 것은 검증 구간뿐 — 학습창을 10년으로 늘리면 죽은 패턴을 배운다."""
    src = (ROOT / "quant" / "live" / "walkforward.py").read_text("utf-8")
    assert "train_window" in src, "학습창을 워밍업으로 존중하지 않는다"
    assert "warmup" in src
    assert WF.LONG_BARS >= 2000, "긴 검증인데 구간이 짧다"


def test_the_command_exists_and_is_offline_capable():
    """만들어 놓고 아무도 부르지 않는 기능은 없는 기능과 같다."""
    from quant.cli import build_parser

    args = build_parser().parse_args(["walkforward", "--offline", "--bars", "800"])
    assert args.offline is True and args.bars == 800
    assert args.func.__name__ == "_cmd_walkforward"


def test_the_weekly_workflow_actually_runs_it():
    wf = (ROOT / ".github" / "workflows" / "weekly-report.yml").read_text("utf-8")
    assert "quant walkforward" in wf, "주간 워크플로가 이 보고서를 부르지 않는다"
