"""시장 브리핑(표시 전용) + 이벤트 위험 필터 테스트."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── 브리핑 (stdlib만 — pandas 불필요) ─────────────────────────────

_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>코스피 2% 급등 마감 - 연합뉴스</title>
  <link>https://example.com/1</link><pubDate>Tue, 05 Aug 2026</pubDate></item>
<item><title>연준 금리 동결 시사 - 한국경제</title>
  <link>https://example.com/2</link><pubDate>Tue, 05 Aug 2026</pubDate></item>
<item><title></title><link>x</link></item>
<item><title>세 번째 헤드라인 - 매경</title><link>https://example.com/3</link></item>
<item><title>네 번째 - A</title><link>h</link></item>
<item><title>다섯 번째(top_n 초과) - B</title><link>h</link></item>
</channel></rss>"""


def test_parse_rss_extracts_and_caps():
    from quant.live.briefing import parse_rss

    items = parse_rss(_RSS, "증시", top_n=4)
    assert len(items) == 4                       # 빈 제목 건너뜀 + top_n 상한
    assert items[0]["title"] == "코스피 2% 급등 마감"
    assert items[0]["source"] == "연합뉴스"      # "제목 - 언론사" 분리
    assert items[0]["cat"] == "증시"
    assert items[0]["link"] == "https://example.com/1"


def test_parse_rss_bad_xml_returns_empty():
    from quant.live.briefing import parse_rss

    assert parse_rss("이건 XML이 아님 <<<", "증시") == []


def test_collect_briefing_isolates_feed_failures(tmp_path, monkeypatch):
    """피드 하나가 죽어도 나머지는 수집되고, 판단 미사용 문구가 저장된다."""
    import quant.live.briefing as bf

    def fake_get_text(url, headers=None, timeout=30):
        if "%EC%A6%9D%EC%8B%9C" in url:          # 증시 피드만 성공
            return _RSS
        raise RuntimeError("네트워크 오류")

    import quant.utils.http as _http
    monkeypatch.setattr(_http, "get_text", fake_get_text)
    out = bf.collect_briefing(str(tmp_path))
    assert len(out["items"]) == 4
    assert "판단에 사용되지" in out["note"]
    saved = json.loads((tmp_path / "briefing.json").read_text(encoding="utf-8"))
    assert saved["items"] == out["items"]
    # load_briefing 왕복
    assert bf.load_briefing(str(tmp_path))["items"] == out["items"]


def test_load_briefing_missing_returns_none(tmp_path):
    from quant.live.briefing import load_briefing

    assert load_briefing(str(tmp_path)) is None


def test_briefing_in_docs_status(tmp_path, monkeypatch):
    """브리핑이 있으면 docs/status.json에 실린다 (사이트 표시용)."""
    from quant.live.daily import write_docs_status

    (tmp_path / "briefing.json").write_text(json.dumps(
        {"date": "2026-08-05", "items": [{"cat": "증시", "title": "t",
                                          "source": "s", "link": "", "time": ""}],
         "note": "판단에 사용되지 않는 참고 정보입니다."}), encoding="utf-8")
    out = tmp_path / "docs" / "status.json"
    st = write_docs_status(str(tmp_path), docs_path=str(out))
    assert st["briefing"]["items"][0]["title"] == "t"


def test_briefing_in_broadcast_json(tmp_path):
    from quant.web.app import broadcast_json

    (tmp_path / "briefing.json").write_text(json.dumps(
        {"date": "2026-08-05", "items": [{"cat": "코인", "title": "헤드라인",
                                          "source": "", "link": "", "time": ""}],
         "note": "참고"}), encoding="utf-8")
    d = json.loads(broadcast_json(state_dir=str(tmp_path), with_live=False))
    assert d["briefing"]["items"][0]["title"] == "헤드라인"


# ── 이벤트 달력 + EventGuard ──────────────────────────────────────

def test_event_dates_pad_and_membership():
    from quant.events import event_dates, is_event_day

    assert is_event_day(date(2026, 3, 18))       # FOMC 발표일
    assert is_event_day(date(2026, 3, 17))      # ±1일 패딩
    assert is_event_day(date(2026, 3, 19))
    assert not is_event_day(date(2026, 3, 25))
    assert is_event_day(date(2026, 3, 18), pad_days=0)
    assert not is_event_day(date(2026, 3, 17), pad_days=0)
    assert len(event_dates(0)) == 81             # 2018~2027 정례 79 + 2020 긴급 2


def test_event_guard_gates_event_window():
    import numpy as np
    import pandas as pd

    from quant.strategies import EventGuard
    from quant.strategies.base import Strategy

    class Always(Strategy):
        name = "always"

        def generate_signals(self, df):
            return pd.Series(1.0, index=df.index)

    idx = pd.date_range("2026-03-10", "2026-03-31", freq="D")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                       "close": np.linspace(100, 120, len(idx)),
                       "volume": 1.0}, index=idx)
    sig = EventGuard(Always(), pad_days=1, factor=0.0).generate_signals(df)
    assert sig.loc["2026-03-17"] == 0.0
    assert sig.loc["2026-03-18"] == 0.0
    assert sig.loc["2026-03-19"] == 0.0
    assert sig.loc["2026-03-25"] == 1.0
    # factor=0.5 → 이벤트 창 비중 절반
    half = EventGuard(Always(), pad_days=1, factor=0.5).generate_signals(df)
    assert half.loc["2026-03-18"] == 0.5


def test_event_guard_non_datetime_index_passthrough():
    """정수 인덱스(합성 테스트 데이터)에서는 게이팅하지 않고 그대로 통과."""
    import pandas as pd

    from quant.strategies import EventGuard
    from quant.strategies.base import Strategy

    class Always(Strategy):
        name = "always"

        def generate_signals(self, df):
            return pd.Series(1.0, index=df.index)

    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                       "close": 1.0, "volume": 1.0}, index=range(10))
    sig = EventGuard(Always()).generate_signals(df)
    assert (sig == 1.0).all()


def test_build_strategy_event_wrap():
    from quant.live.retrain import build_strategy
    from quant.strategies import EventGuard, MovingAverageCross

    s = build_strategy({"strategy": "event_wrap",
                        "params": {"inner": {"strategy": "ma_cross",
                                             "params": {"fast": 5, "slow": 20}},
                                   "pad_days": 1, "factor": 0.0}})
    assert isinstance(s, EventGuard)
    assert isinstance(s.base, MovingAverageCross)


def test_retrain_injects_event_wrap_challenger(tmp_path, monkeypatch):
    """진화 모드에서 event_wrap 챌린저가 링에 오르는지 확인 (승격 강제는 아님)."""
    import numpy as np
    import pandas as pd

    import quant.live.retrain as rt

    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx))), index=idx)
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1.0})
    df.attrs["source"] = "test"

    class _Prov:
        def get_ohlcv(self, *a, **k):
            return df

    monkeypatch.setattr("quant.data.get_provider", lambda m: _Prov())

    captured = {}
    real = rt.nightly_retrain

    def spy(d, champ, challengers, **kw):
        captured["challengers"] = challengers
        return {"promoted": False, "reason": "테스트", "candidates": []}

    monkeypatch.setattr(rt, "nightly_retrain", spy)
    rt.run_retrain("crypto", "BTC/USDT", state_dir=str(tmp_path))
    kinds = [c.get("strategy") for c in captured["challengers"]]
    assert "event_wrap" in kinds
    assert "regime_wrap" in kinds
    monkeypatch.setattr(rt, "nightly_retrain", real)
