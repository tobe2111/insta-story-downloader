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
    # ⚠️ 감사 155에서 event_dates가 **공표 + 추정**을 함께 담게 됐다.
    #    개수를 못 박으려면 공표만 보는 published_event_dates를 쓴다.
    #    (예전엔 event_dates가 공표만 담았고, 그래서 2027년 뒤로는 집합이
    #     통째로 비어 FOMC 가드가 조용히 영구 정지했다.)
    from quant.events import published_event_dates
    assert len(published_event_dates(0)) == 81   # 2018~2027 정례 79 + 2020 긴급 2
    assert len(event_dates(0)) > 81, "추정 일정이 안 들어갔다 — 가드가 언젠가 꺼진다"


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

    # ⚠️ 마지막 봉이 **오늘**이어야 한다(감사 284). 고정 과거 날짜를 쓰면
    #    "묵은 시세로는 챔피언을 다시 뽑지 않는다" 관문에 걸린다 — 이 검사가
    #    보려는 것은 링에 오르는 후보이지 시세 신선도가 아니다.
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=400,
                        freq="D")
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


# ── 실전 반영 CLI (quant live) ────────────────────────────────────

def test_live_cli_paper_mode_runs_one_cycle(tmp_path, capsys):
    """기본(페이퍼) 모드 1사이클 — 실제 자금 없이 챔피언/전략 루프가 돈다."""
    from quant.cli import main

    state = tmp_path / "state.json"
    main(["live", "--market", "synthetic", "--symbol", "TEST",
          "--strategy", "ma_cross", "--iters", "1", "--interval", "1",
          "--state", str(state), "--dashboard", str(tmp_path / "d.html")])
    out = capsys.readouterr().out
    assert "페이퍼 모드" in out
    assert state.exists()
    st = json.loads(state.read_text(encoding="utf-8"))
    assert st["mode"] == "paper" and st["history"]


def test_live_cli_real_requires_typed_confirmation(monkeypatch, capsys):
    """--real은 '실전' 타이핑 없이는 절대 시작되지 않는다 (EOF 포함)."""
    from quant.cli import main

    monkeypatch.setattr("builtins.input", lambda *a: "yes")   # 오답
    main(["live", "--market", "crypto", "--symbol", "BTC/USDT", "--real",
          "--iters", "1"])
    assert "취소" in capsys.readouterr().out

    def eof(*a):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)                # 비대화형
    main(["live", "--market", "crypto", "--symbol", "BTC/USDT", "--real",
          "--iters", "1"])
    assert "취소" in capsys.readouterr().out


def test_live_cli_real_unsupported_market_exits():
    import pytest

    from quant.cli import main

    with pytest.raises(SystemExit, match="실거래를 지원하지"):
        main(["live", "--market", "synthetic", "--symbol", "T", "--real"])


# ── 종목별 관련 뉴스 + 방송 장면·사이트 개선 ─────────────────────────

def test_collect_briefing_symbol_news(tmp_path, monkeypatch):
    """종목 검색 피드의 항목에 sym 키가 붙는다 (방송 카드 매칭용)."""
    import urllib.parse

    import quant.live.briefing as bf
    import quant.utils.http as _http

    btc_q = urllib.parse.quote("비트코인")

    def fake_get_text(url, headers=None, timeout=30):
        if btc_q in url:
            return ("<rss><channel><item><title>비트코인 신고가 - 코인뉴스</title>"
                    "<link>https://e.com/b</link></item></channel></rss>")
        raise RuntimeError("차단")

    monkeypatch.setattr(_http, "get_text", fake_get_text)
    out = bf.collect_briefing(str(tmp_path))
    syms = [it for it in out["items"] if it.get("sym")]
    assert syms and syms[0]["sym"] == "crypto:BTC/USDT"
    assert syms[0]["title"] == "비트코인 신고가"


def test_broadcast_attaches_symbol_news(tmp_path):
    """계좌 키와 일치하는 종목 뉴스가 방송 계좌 데이터에 붙는다."""
    import json as _json

    from quant.web.app import broadcast_json

    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "crypto_BTC_USDT.json").write_text(_json.dumps({
        "market": "crypto", "symbol": "BTC/USDT", "cash": 0, "quantity": 0,
        "history": [{"date": "2026-08-05", "equity": 10000.0,
                     "return_pct": 0.0, "price": 100.0}]}), encoding="utf-8")
    (tmp_path / "briefing.json").write_text(_json.dumps({
        "date": "2026-08-05", "note": "참고",
        "items": [{"cat": "종목", "title": "비트코인 뉴스", "source": "S",
                   "link": "", "time": "", "sym": "crypto:BTC/USDT"}]}),
        encoding="utf-8")
    d = _json.loads(broadcast_json(state_dir=str(tmp_path), with_live=False))
    acc = [a for a in d["accounts"] if a["key"] == "crypto:BTC/USDT"][0]
    assert acc["news"]["title"] == "비트코인 뉴스"


def test_broadcast_scene_cycle_present():
    """방송 화면: 장면 전환(종목 확대·게이지 오버레이) 요소가 존재한다."""
    from quant.web.app import render_broadcast

    doc = render_broadcast()
    assert 'id="scene"' in doc and "sceneLoop" in doc
    assert "body.focus .candle" in doc


def test_docs_have_table_and_weekly_and_hero():
    root = Path(__file__).resolve().parent.parent / "docs"
    paper = (root / "paper.html").read_text(encoding="utf-8")
    # 2026-08-12 감사 107에서 제목을 '종목별 참고 계좌'로 바꿨다 —
    # 통합 계좌(8만원)와 종목 계좌(각 1만원)를 구별하기 위해서다.
    # 여기서는 '종목별 표가 있다'만 보고, 이름 규칙은
    # tests/test_two_ledgers_are_not_confused.py가 검사한다.
    assert "종목별" in paper                          # 증권사 시세표
    assert 'href="weekly.html"' in paper
    weekly = (root / "weekly.html").read_text(encoding="utf-8")
    assert "주간 아카이브" in weekly and "status.json" in weekly
    assert "종목별 주간 수익률" in weekly
    index = (root / "index.html").read_text(encoding="utf-8")
    assert "100만 챌린지 · 통합 실기록" in index     # 히어로 실계좌 카드


def test_live_cli_multi_symbols_paper(tmp_path):
    """--symbols 다중 종목 페이퍼 1사이클 — MultiTrader 경로."""
    import json as _json

    from quant.cli import main

    state = tmp_path / "m.json"
    main(["live", "--market", "synthetic", "--symbols", "AAA,BBB",
          "--strategy", "ma_cross", "--iters", "1", "--interval", "1",
          "--state", str(state), "--dashboard", str(tmp_path / "d.html")])
    st = _json.loads(state.read_text(encoding="utf-8"))
    assert st["mode"] == "paper" and st["history"]
    assert "positions" in st


def test_symbol_info_names_and_reasons():
    """모든 자동 운용 종목에 한글 이름·선정 이유가 있다 (사이트·방송 표시용)."""
    from quant.markets import AUTO_TARGETS, SYMBOL_INFO

    for market, symbol in AUTO_TARGETS:
        info = SYMBOL_INFO.get(f"{market}:{symbol}")
        assert info and info["name"] and info["why"], f"{market}:{symbol}"
    assert SYMBOL_INFO["kr_stock:005930.KS"]["name"] == "삼성전자"
    assert SYMBOL_INFO["kr_stock:069500.KS"]["name"] == "KODEX 200"


def test_names_in_status_and_broadcast(tmp_path):
    import json as _json

    from quant.live.daily import write_docs_status
    from quant.web.app import broadcast_json

    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "kr_stock_005930.KS.json").write_text(_json.dumps({
        "market": "kr_stock", "symbol": "005930.KS", "cash": 0, "quantity": 0,
        "history": [{"date": "2026-08-05", "equity": 10000.0,
                     "return_pct": 0.0, "price": 240000.0}]}), encoding="utf-8")
    st = write_docs_status(str(tmp_path), docs_path=str(tmp_path / "s.json"))
    assert st["symbols"]["kr_stock:005930.KS"]["name"] == "삼성전자"
    d = _json.loads(broadcast_json(state_dir=str(tmp_path), with_live=False))
    acc = [a for a in d["accounts"] if a["key"] == "kr_stock:005930.KS"][0]
    assert acc["name"] == "삼성전자"


def test_paper_page_has_names_and_reasons_section():
    root = Path(__file__).resolve().parent.parent / "docs"
    paper = (root / "paper.html").read_text(encoding="utf-8")
    assert "왜 이 종목들인가" in paper
    assert "st.symbols" in paper


# ── 운영 안정성 + 콘텐츠 지원 ────────────────────────────────────

def test_workflows_have_failure_alerts():
    """자동 운용 워크플로 4종에 실패 경보(if: failure) 스텝이 있다."""
    root = Path(__file__).resolve().parent.parent / ".github" / "workflows"
    for name in ("nightly-retrain.yml", "daily-paper.yml",
                 "nightly-validate.yml", "deposit.yml"):
        t = (root / name).read_text(encoding="utf-8")
        assert "실패 경보" in t and "if: failure()" in t, name


def test_today_page_markers():
    """오늘의 판단 페이지: 촬영/카드 모드·핵심 요소가 존재한다."""
    root = Path(__file__).resolve().parent.parent / "docs"
    t = (root / "today.html").read_text(encoding="utf-8")
    assert "오늘의 판단" in t and "?card=1" in t
    assert "status.json" in t and "오늘의 자세" in t
    assert "수익을 보장하지 않습니다" in t
    paper = (root / "paper.html").read_text(encoding="utf-8")
    assert 'href="today.html"' in paper


def test_card_generation_step_and_og():
    root = Path(__file__).resolve().parent.parent
    dp = (root / ".github" / "workflows" / "daily-paper.yml").read_text(encoding="utf-8")
    assert "공유 카드 이미지 생성" in dp and "card.png" in dp
    idx = (root / "docs" / "index.html").read_text(encoding="utf-8")
    assert "card.png" in idx                       # og:image가 매일 갱신 카드로
