"""DART 배선 — 한국 실적 발표일 수집, 키 조건부 (2026-08-23, 사장님 지시).

PEAD는 발표일을 아는 시장에서만 움직인다. 야후 캘린더가 비는 한국은 DART
(전자공시)로 채우되, **인증키(DART_API_KEY)가 환경변수에 있을 때만** 움직인다.

지켜야 할 약속:
- 키가 없으면 조용히 아무것도 하지 않는다(매일 경고는 소음 — 진짜 고장을
  가린다). 키가 들어오면 코드 변경 없이 다음 배치부터 수집이 시작된다.
- 키 값은 저장소·캐시·로그·오류 메시지 어디에도 적히지 않는다.
- 코드표(30일)·발표일(7일) 캐시 — 실패를 '오늘 받아온 것'으로 도장 찍지
  않는다(옛 캐시 유지, 내일 재시도).
- 발표일 대용치는 정기공시 접수일이다 — 대용치라는 사실을 숨기지 않는다.
- ETF처럼 코드표에 없는 종목은 빈 목록(발표 없음이 사실)이다.

전부 목킹으로 검증한다 — CI에는 키도 네트워크도 없다.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.earnings as earn                        # noqa: E402
from quant.data.earnings import (                          # noqa: E402
    _corp_codes,
    _fetch_dates_dart,
    attach_earnings_days,
    dart_fetcher,
    dart_key,
    earnings_guard_factor,
)

KEY = "TESTKEY_0123456789abcdef0123456789abcdef"
TODAY = _dt.date(2026, 8, 23)


def _corp_zip(entries) -> bytes:
    rows = "".join(
        f"<list><corp_code>{cc}</corp_code><corp_name>{n}</corp_name>"
        f"<stock_code>{sc}</stock_code></list>" for cc, n, sc in entries)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><result>{rows}</result>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


def test_no_key_means_no_key(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    assert dart_key() is None
    monkeypatch.setenv("DART_API_KEY", "   ")
    assert dart_key() is None
    monkeypatch.setenv("DART_API_KEY", KEY)
    assert dart_key() == KEY


def test_corp_codes_parse_cache_and_do_not_refetch(tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", KEY)
    calls = []

    def fake_get_bytes(url, timeout=30):
        calls.append(url)
        return _corp_zip([("00126380", "삼성전자", "005930"),
                          ("00164742", "비상장사", ""),      # 상장 안 됨 — 제외
                          ("00164779", "SK하이닉스", "000660")])
    import quant.utils.http as http
    monkeypatch.setattr(http, "get_bytes", fake_get_bytes)

    codes = _corp_codes(str(tmp_path), TODAY)
    assert codes == {"005930": "00126380", "000660": "00164779"}
    assert len(calls) == 1
    # 신선한 캐시 — 다시 부르지 않는다
    codes2 = _corp_codes(str(tmp_path), TODAY)
    assert codes2 == codes and len(calls) == 1


def test_corp_code_failure_keeps_the_old_cache_and_retries(tmp_path,
                                                           monkeypatch):
    monkeypatch.setenv("DART_API_KEY", KEY)
    old = {"fetched": "2026-01-01", "codes": {"005930": "00126380"}}
    (tmp_path / "dart_corp_codes.json").write_text(json.dumps(old), "utf-8")

    def boom(url, timeout=30):
        raise RuntimeError("접속 실패")
    import quant.utils.http as http
    monkeypatch.setattr(http, "get_bytes", boom)

    codes = _corp_codes(str(tmp_path), TODAY)
    assert codes == {"005930": "00126380"}, "실패했는데 옛 캐시를 버렸다"
    saved = json.loads((tmp_path / "dart_corp_codes.json").read_text("utf-8"))
    assert saved["fetched"] == "2026-01-01", (
        "실패를 '오늘 받아온 것'으로 도장 찍었다 — 30일간 재시도가 죽는다")


def _prime_corp_cache(tmp_path):
    (tmp_path / "dart_corp_codes.json").write_text(json.dumps(
        {"fetched": TODAY.isoformat(),
         "codes": {"005930": "00126380"}}), "utf-8")


def test_dart_dates_are_iso_paginated_and_deduped(tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", KEY)
    _prime_corp_cache(tmp_path)
    pages = {
        1: {"status": "000", "total_page": 2,
            "list": [{"rcept_dt": "20240814"}, {"rcept_dt": "20240514"}]},
        2: {"status": "000", "total_page": 2,
            "list": [{"rcept_dt": "20240814"},        # 중복
                     {"rcept_dt": "20231114"},
                     {"rcept_dt": "bogus"}]},          # 형식 불량 — 버린다
    }
    seen = []

    def fake_get_json(url, timeout=30):
        page = int(url.split("page_no=")[1].split("&")[0])
        seen.append(page)
        return pages[page]
    import quant.utils.http as http
    monkeypatch.setattr(http, "get_json", fake_get_json)

    dates = _fetch_dates_dart("005930.KS", str(tmp_path))
    assert dates == ["2023-11-14", "2024-05-14", "2024-08-14"]
    assert seen == [1, 2], "total_page에서 멈추지 않았다"


def test_an_etf_missing_from_the_code_table_has_no_announcements(tmp_path,
                                                                 monkeypatch):
    monkeypatch.setenv("DART_API_KEY", KEY)
    _prime_corp_cache(tmp_path)
    assert _fetch_dates_dart("069500.KS", str(tmp_path)) == []


def test_status_013_is_empty_and_other_errors_never_leak_the_key(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", KEY)
    _prime_corp_cache(tmp_path)
    import quant.utils.http as http
    monkeypatch.setattr(http, "get_json",
                        lambda url, timeout=30: {"status": "013"})
    assert _fetch_dates_dart("005930.KS", str(tmp_path)) == []

    monkeypatch.setattr(http, "get_json", lambda url, timeout=30: {
        "status": "010", "message": f"등록되지 않은 키 {KEY} 입니다"})
    with pytest.raises(RuntimeError) as ei:
        _fetch_dates_dart("005930.KS", str(tmp_path))
    assert KEY not in str(ei.value), "오류 메시지에 키가 실렸다"


def test_the_key_never_lands_in_cache_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", KEY)
    import quant.utils.http as http
    monkeypatch.setattr(http, "get_bytes", lambda url, timeout=30: _corp_zip(
        [("00126380", "삼성전자", "005930")]))
    monkeypatch.setattr(http, "get_json", lambda url, timeout=30: {
        "status": "000", "total_page": 1,
        "list": [{"rcept_dt": "20240814"}]})
    _corp_codes(str(tmp_path), TODAY)
    earnings_guard_factor("005930.KS", TODAY, str(tmp_path),
                          fetch=dart_fetcher(str(tmp_path)))
    for p in tmp_path.iterdir():
        assert KEY not in p.read_text("utf-8"), f"{p.name}에 키가 적혔다"


def test_the_redactor_hides_the_dart_key():
    from quant.utils.http import redact_secrets
    out = redact_secrets(f"https://opendart.fss.or.kr/api/list.json"
                         f"?crtfc_key={KEY}&corp_code=1")
    assert KEY not in out and "crtfc_key=***" in out


def test_the_whole_path_feeds_pead(tmp_path, monkeypatch):
    """가드 호출 → 캐시 → earn_day 부착까지 — PEAD의 한국 재료가 실제로 흐른다."""
    monkeypatch.setenv("DART_API_KEY", KEY)
    _prime_corp_cache(tmp_path)
    import quant.utils.http as http
    monkeypatch.setattr(http, "get_json", lambda url, timeout=30: {
        "status": "000", "total_page": 1,
        "list": [{"rcept_dt": "20260812"}]})
    earnings_guard_factor("005930.KS", TODAY, str(tmp_path),
                          fetch=dart_fetcher(str(tmp_path)))
    idx = pd.bdate_range("2026-08-03", "2026-08-21")
    c = np.full(len(idx), 100.0)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                       "volume": c}, index=idx)
    out = attach_earnings_days(df, "005930.KS", str(tmp_path))
    assert "earn_day" in out.columns
    assert str(out.index[out["earn_day"] > 0][0].date()) == "2026-08-12"


def test_the_daily_batch_asks_korea_only_with_a_key():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "if dart_key() is not None:" in src, (
        "키 가드가 없다 — 키 없는 날마다 실패 경고가 쌓인다")
    assert "fetch=dart_fetcher(state_dir)" in src, (
        "한국 가드가 DART 조회로 배선되지 않았다")
    # 두 파이프라인 모두 한국에도 earn_day를 붙인다
    for f in ("quant/live/daily.py", "quant/live/retrain.py"):
        s = (ROOT / f).read_text("utf-8")
        assert 'market in ("us_stock", "kr_stock")' in s, (
            f"{f}: 한국에 earn_day를 안 붙인다 — 캐시가 차도 PEAD가 관망한다")


def test_the_workflow_hands_the_key_to_the_batch():
    """새벽 배치 워크플로가 시크릿을 실제로 넘긴다 (2026-08-24).

    코드가 키 조건부로 완벽해도 워크플로가 env로 안 넘기면 키는 영원히
    '미설정'이다 — 실제로 그렇게 배선이 빠진 채 배송됐고, 사장님이 키를
    등록한 날 확인 과정에서 잡았다. 이 자리가 다시 비면 여기서 죽는다.
    """
    src = (ROOT / ".github" / "workflows" / "daily-paper.yml").read_text("utf-8")
    assert "DART_API_KEY: ${{ secrets.DART_API_KEY }}" in src, (
        "daily-paper.yml이 DART_API_KEY를 배치에 넘기지 않는다 — "
        "키를 등록해도 한국 발표일 수집이 영원히 시작되지 않는다")


def test_the_proxy_definition_is_confessed():
    src = (ROOT / "quant" / "data" / "earnings.py").read_text("utf-8")
    assert "대용치" in src and "정기공시" in src, (
        "발표일 정의(정기공시 접수일 = 대용치)를 숨겼다")
