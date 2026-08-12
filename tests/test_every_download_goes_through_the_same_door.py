"""세 곳이 공용 HTTP 문을 지나지 않고 있었다 (감사 178).

`quant/utils/http.py`는 바깥에서 오는 것을 받는 **공용 문**이다. 거기에
방어가 세 겹 걸려 있다.

    · 응답 크기 상한 32MB — 악의적·오작동 서버의 초대형 응답으로 인한 메모리 고갈 방지
    · 교차 호스트·스킴 강등 리다이렉트에서 인증 헤더 제거(감사 170)
    · 오류 메시지에서 비밀 가리기(감사 170)

그런데 **바깥 데이터를 가장 많이 받는 세 경로**가 그 문을 안 지났다.

    quant/data/sentiment.py   공포탐욕지수     urlopen + resp.read()
    quant/data/stock.py       야후 chart API   urlopen + json.load(resp)
    quant/data/stock.py       stooq CSV        urlopen + resp.read()

셋 다 **본문을 상한 없이** 통째로 읽는다. 방어를 만들어 놓고 정작 매일 밤
도는 수집 경로가 그 앞을 비껴간 것이다(감사 135와 같은 계열 — 만들었는데
배선 안 됨).

실측(가짜 57MB 응답):

    예전:  그대로 메모리에 올린다
    지금:  "응답이 너무 큽니다(>33554432B)" → 빈 결과로 안전하게 폴백

시세 수집이 OOM으로 죽으면 그날 기록이 통째로 빈다. 돈을 잃는 결함은
아니지만, 이 저장소가 **이미 막기로 결정한 위험**을 세 곳이 지나치고 있었다.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.utils.http as H  # noqa: E402


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _serve(monkeypatch, body: bytes):
    monkeypatch.setattr(
        H, "_opener",
        type("_O", (), {"open": lambda s, r, timeout=None: _Resp(body)})())


def _huge() -> bytes:
    """상한(32MB)을 넘는 응답. 문법은 멀쩡한 JSON이라 파싱은 시도된다."""
    return (b'{"data":[' + b'{"timestamp":"1","value":"1"},' * 2_000_000
            + b'{"timestamp":"1","value":"1"}]}')


# ── 공용 문을 지나는가 (배선) ─────────────────────────────────


@pytest.mark.parametrize("mod", ["quant/data/sentiment.py", "quant/data/stock.py"])
def test_no_module_opens_its_own_connection(mod):
    """직접 urlopen을 부르면 상한·리다이렉트 방어를 통째로 건너뛴다."""
    src = (ROOT / mod).read_text("utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "urlopen(" not in code, f"{mod}이 공용 헬퍼를 지나지 않는다"


# ── 초대형 응답이 막히는가 ────────────────────────────────────


def test_a_huge_response_is_refused_by_the_helper(monkeypatch):
    _serve(monkeypatch, _huge())
    with pytest.raises(RuntimeError, match="너무 큽니다"):
        H.get_json("https://api.test/x")


def test_the_sentiment_feed_falls_back_instead_of_eating_memory(monkeypatch):
    from quant.data.sentiment import fear_greed_history

    _serve(monkeypatch, _huge())
    s = fear_greed_history()
    assert s.empty, "초대형 응답을 그대로 읽어들인다"


def test_the_stooq_source_is_capped_too(monkeypatch):
    from quant.data.stock import StockDataProvider

    _serve(monkeypatch, b"x" * (H._MAX_RESPONSE_BYTES + 10))
    with pytest.raises(RuntimeError, match="너무 큽니다"):
        StockDataProvider()._via_stooq("SPY", "1d", None, None, 100)


def test_the_yahoo_http_source_is_capped_too(monkeypatch):
    from quant.data.stock import StockDataProvider

    _serve(monkeypatch, _huge())
    with pytest.raises(RuntimeError, match="너무 큽니다"):
        StockDataProvider()._via_yahoo_http("SPY", "1d", None, None, 100)


# ── 대조군: 정상 응답은 그대로 읽혀야 한다 ────────────────────


def test_a_normal_sentiment_response_still_parses(monkeypatch):
    from quant.data.sentiment import fear_greed_frame, fear_greed_history

    payload = {"data": [{"timestamp": "1704067200", "value": "55"},
                        {"timestamp": "1704153600", "value": "70"}]}
    _serve(monkeypatch, json.dumps(payload).encode())
    s = fear_greed_history()
    assert len(s) == 2 and list(s.values) == [55.0, 70.0]

    _serve(monkeypatch, json.dumps(payload).encode())
    frame = fear_greed_frame()
    assert list(frame.columns) == ["fear_greed"]
    assert frame["fear_greed"].max() <= 1.0, "0~1로 정규화돼야 한다"


def test_a_network_failure_is_still_graceful(monkeypatch):
    """대조군 — 외부 피처 실패가 백테스트를 죽이면 안 된다."""
    import urllib.error

    from quant.data.sentiment import fear_greed_history

    def _boom(self, req, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(H, "_opener", type("_O", (), {"open": _boom})())
    assert fear_greed_history().empty


# ── 파서 자체의 계약 ──────────────────────────────────────────


def test_the_parser_sorts_and_dedupes():
    from quant.data.sentiment import _parse_fng

    payload = {"data": [
        {"timestamp": "1704153600", "value": "70"},   # 01-02
        {"timestamp": "1704067200", "value": "55"},   # 01-01
        {"timestamp": "1704153600", "value": "80"},   # 01-02 중복(나중 값 채택)
    ]}
    s = _parse_fng(payload)
    assert list(s.index.strftime("%m-%d")) == ["01-01", "01-02"]
    assert list(s.values) == [55.0, 80.0], "중복은 마지막 값을 남겨야 한다"


def test_the_parser_skips_broken_rows():
    from quant.data.sentiment import _parse_fng

    s = _parse_fng({"data": [{"timestamp": "x", "value": "1"},
                             {"value": "2"},
                             {"timestamp": "1704067200", "value": "55"}]})
    assert list(s.values) == [55.0], "망가진 행 하나가 전체를 버리면 안 된다"


def test_an_empty_payload_is_an_empty_series():
    from quant.data.sentiment import _parse_fng

    assert _parse_fng({}).empty and _parse_fng({"data": []}).empty


# ── 합성 데이터의 재현성 ──────────────────────────────────────


def test_synthetic_data_is_reproducible_per_symbol():
    """합성 폴백은 시드로 고정돼야 한다 — 안 그러면 재현 검증이 무너진다."""
    from quant.data.synthetic import SyntheticDataProvider

    a = SyntheticDataProvider(seed=42).get_ohlcv("BTC/USDT", "1d", limit=50)
    b = SyntheticDataProvider(seed=42).get_ohlcv("BTC/USDT", "1d", limit=50)
    assert a["close"].equals(b["close"]), "같은 시드인데 값이 다르다"

    c = SyntheticDataProvider(seed=42).get_ohlcv("ETH/USDT", "1d", limit=50)
    assert not a["close"].equals(c["close"]), (
        "종목이 달라도 같은 계열이 나온다 — 분산 효과가 가짜가 된다")

    d = SyntheticDataProvider(seed=7).get_ohlcv("BTC/USDT", "1d", limit=50)
    assert not a["close"].equals(d["close"]), "시드가 달라도 같은 계열이 나온다"


def test_synthetic_data_is_a_valid_ohlcv_frame():
    """대조군 — 폴백 데이터도 무결성 검사를 통과하는 모양이어야 한다."""
    from quant.data.quality import is_severe, scan_ohlcv
    from quant.data.synthetic import SyntheticDataProvider

    df = SyntheticDataProvider(seed=3).get_ohlcv("X", "1d", limit=120)
    assert len(df) == 120
    assert not is_severe(scan_ohlcv(df)), scan_ohlcv(df)
