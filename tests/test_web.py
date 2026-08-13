"""웹 UI 테스트.

폼 렌더링은 표준 라이브러리만으로 동작(pandas 불필요), 백테스트 실행 경로는
pandas가 필요하다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.web.app import (
    MARKETS,
    STRATEGIES,
    read_state,
    render_form,
    render_monitor,
    render_optimize_form,
    render_portfolio_form,
    render_screener_form,
    render_sweep_form,
    render_validate_form,
    run_backtest_html,
    run_optimize_html,
    run_portfolio_html,
    run_screener_html,
    run_sweep_html,
    run_validate_html,
    state_json,
)


def test_render_form_has_controls():
    doc = render_form()
    assert "<form" in doc and 'action="/backtest"' in doc
    assert "<nav" in doc and 'href="/sweep"' in doc   # 조종석 네비게이션
    for s in STRATEGIES:
        assert s in doc
    for m in MARKETS:
        assert m in doc


def test_render_sweep_form():
    doc = render_sweep_form()
    assert "<form" in doc and 'action="/sweep/run"' in doc
    assert "히트맵" in doc and "<nav" in doc


def test_render_optimize_form():
    doc = render_optimize_form()
    assert "<form" in doc and 'action="/optimize/run"' in doc
    assert "워크포워드" in doc and 'href="/optimize"' in doc


def test_run_optimize_html_synthetic():
    doc = run_optimize_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "500",
                             "is_window": "200", "oos_window": "100"})
    assert "워크포워드 결과" in doc and "OOS" in doc and "<nav" in doc


def test_run_optimize_html_unsupported_strategy():
    doc = run_optimize_html({"strategy": "ensemble"})  # 그리드 없는 전략
    assert "최적화 미지원" in doc  # 폼으로 안내


def test_render_validate_form():
    """검증 폼 렌더링 (pandas 불필요 — quant.cli는 argparse만 쓰는 경량 모듈)."""
    doc = render_validate_form()
    assert "<form" in doc and 'action="/validate/run"' in doc
    assert "<nav" in doc and 'href="/validate"' in doc     # 네비게이션에 검증 탭
    # CLI validate와 같은 기본 그리드 지원 전략만 선택지로 노출
    from quant.cli import _VALIDATE_GRIDS
    for s in _VALIDATE_GRIDS:
        assert s in doc
    for field in ("market", "symbol", "timeframe", "limit",
                  "is_window", "oos_window"):
        assert f'name="{field}"' in doc
    assert "보장되지 않습니다" in doc            # 정직성 푸터


def test_run_validate_html_synthetic():
    """검증 3종 실행 경로 (pandas 필요 — CI). 합성 시장 + 기본 그리드."""
    doc = run_validate_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "500",
                             "is_window": "250", "oos_window": "125"})
    assert "검증 결과" in doc and "<nav" in doc
    assert "워크포워드" in doc and "PBO" in doc and "CPCV" in doc
    assert "<pre" in doc                        # 한국어 리포트 문자열을 <pre>로
    assert "보장되지 않습니다" in doc            # 정직성 푸터


def test_run_validate_html_unsupported_strategy():
    doc = run_validate_html({"strategy": "ensemble"})   # 기본 그리드 없는 전략
    assert "검증 미지원" in doc                  # 폼으로 안내


def test_render_portfolio_form():
    doc = render_portfolio_form()
    assert "<form" in doc and 'action="/portfolio/run"' in doc
    assert "포트폴리오" in doc and 'href="/portfolio"' in doc


def test_run_portfolio_html_synthetic():
    doc = run_portfolio_html({"market": "synthetic", "symbols": "A, B, C",
                              "strategy": "momentum", "limit": "200"})
    assert "성과 지표" in doc and "샤프지수" in doc and "<nav" in doc


def test_run_portfolio_html_empty_symbols():
    doc = run_portfolio_html({"market": "synthetic", "symbols": "  "})
    assert "종목을 하나 이상" in doc  # 빈 입력 → 폼으로 안내


def test_render_screener_form():
    doc = render_screener_form()
    assert "<form" in doc and 'action="/screener/run"' in doc
    assert "종목 선별" in doc and "<nav" in doc and 'href="/screener"' in doc


def test_run_screener_no_symbols():
    doc = run_screener_html({"symbols": "  "})
    assert "후보 종목을 하나 이상" in doc


def test_run_screener_no_api_key():
    """FMP 키가 없으면(=재무데이터 없음) 안내 메시지로 폼을 보여준다."""
    import os
    os.environ.pop("FMP_API_KEY", None)
    doc = run_screener_html({"symbols": "AAPL, MSFT", "top_n": "1"})
    assert "FMP_API_KEY" in doc


def test_render_monitor_no_state(tmp_path):
    doc = render_monitor([str(tmp_path / "nope.json")])
    assert "실행 중인" in doc and "<nav" in doc


def test_render_monitor_with_state(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "symbol": "X", "strategy": "s", "mode": "paper",
        "history": [{"time": "t", "equity": 10000 + i, "weight": 0.5, "price": 0}
                    for i in range(4)],
        "positions": [{"symbol": "X", "quantity": 0.1, "avg_price": 100}],
        "orders": [],
    }), encoding="utf-8")
    doc = render_monitor([str(p)])
    assert "라이브 모니터" in doc and "<nav" in doc and "총자산" in doc
    # 실시간 갱신: JS 폴러 + 요소 id, 페이지 meta-refresh 제거
    assert 'id="eqline"' in doc and "fetch(" in doc and "setInterval" in doc
    assert 'http-equiv="refresh"' not in doc
    # 전체 실시간: 포지션·주문 테이블도 JS로 갱신되도록 id 부여
    assert 'id="pos-body"' in doc and 'id="ord-body"' in doc
    assert 'id="kpi-dd"' in doc and 'id="kpi-trades"' in doc
    assert 'id="kpi-acc"' in doc and "방향 정확도" in doc   # 예측 정확도 타일


def test_state_json_reads_file(tmp_path):
    import json
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"symbol": "BTC/USDT", "history": []}), encoding="utf-8")
    assert read_state([str(p)])["symbol"] == "BTC/USDT"
    assert json.loads(state_json([str(p)]))["symbol"] == "BTC/USDT"
    # 파일 없으면 빈 객체
    assert state_json([str(tmp_path / "none.json")]) == "{}"


def test_run_sweep_html_synthetic():
    doc = run_sweep_html({"market": "synthetic", "symbol": "X", "limit": "300"})
    assert "<table" in doc and "hsl(" in doc      # 히트맵 렌더
    assert 'href="/"' in doc                       # 네비게이션


def test_render_form_message():
    assert "테스트경고" in render_form("테스트경고")


def test_run_backtest_html_synthetic():
    doc = run_backtest_html({"market": "synthetic", "symbol": "X",
                             "strategy": "ma_cross", "limit": "200"})
    assert "성과 지표" in doc and "샤프지수" in doc
    assert "<nav" in doc  # 조종석 네비게이션
    # "이게 운인가?" 신뢰도 분석(PSR + 몬테카를로)이 포함되어야 한다
    assert "이게 운인가" in doc and "PSR" in doc


def test_run_backtest_html_ensemble():
    doc = run_backtest_html({"market": "synthetic", "strategy": "ensemble",
                             "limit": "150"})
    assert "<svg" in doc


def test_run_backtest_html_bad_limit_defaults():
    # limit이 숫자가 아니어도 기본값으로 처리되어 크래시하지 않아야 한다
    doc = run_backtest_html({"market": "synthetic", "strategy": "rsi",
                             "limit": "abc"})
    assert "성과 지표" in doc


def test_run_backtest_html_escapes_symbol_xss():
    """웹 파라미터(symbol)가 리포트 제목에 이스케이프되어 반사형 XSS가 막힌다."""
    doc = run_backtest_html({"market": "synthetic", "strategy": "ma_cross",
                             "symbol": "<script>alert(1)</script>", "limit": "120"})
    assert "<script>alert(1)</script>" not in doc     # 원본 스크립트 태그 없음
    assert "&lt;script&gt;" in doc                     # 이스케이프됨


def test_parse_symbols_caps_and_dedupes():
    """종목 수가 상한(_MAX_SYMBOLS)으로 제한되고 중복이 제거된다(자원 고갈 방지)."""
    from quant.web.app import _parse_symbols, _MAX_SYMBOLS
    many = ",".join(f"S{i}" for i in range(10_000))
    out = _parse_symbols(many)
    assert len(out) == _MAX_SYMBOLS               # 수만 개 → 상한으로 잘림
    # 중복 제거 + upper 옵션
    assert _parse_symbols("aapl, aapl , msft", upper=True) == ["AAPL", "MSFT"]
    assert _parse_symbols("  ") == []


def test_web_token_gate():
    """QUANT_WEB_TOKEN이 설정되면 토큰 없는 요청을 401로 막는다(노출 시 인증)."""
    import os
    from urllib.parse import urlparse
    from quant.web import server

    h = server.QuantHandler.__new__(server.QuantHandler)   # __init__ 우회

    class _Hdr(dict):
        def get(self, k, d=""):
            return dict.get(self, k, d)
    h.headers = _Hdr()

    os.environ.pop("QUANT_WEB_TOKEN", None)
    assert h._authorized(urlparse("/backtest?x=1"))        # 토큰 미설정 → 허용

    os.environ["QUANT_WEB_TOKEN"] = "sekret"
    try:
        assert not h._authorized(urlparse("/backtest"))              # 토큰 없음 → 거부
        assert h._authorized(urlparse("/backtest?token=sekret"))     # 일치 → 허용
        assert not h._authorized(urlparse("/backtest?token=nope"))   # 불일치 → 거부
        assert h._authorized(urlparse("/health"))                    # health는 항상 허용
    finally:
        os.environ.pop("QUANT_WEB_TOKEN", None)


def test_fallback_banner_flags_synthetic_data():
    """실데이터 폴백이면 결과 화면에 '가짜 데이터' 경고가 떠야 한다(정직성)."""
    from types import SimpleNamespace

    from quant.web.app import _fallback_banner

    fake = SimpleNamespace(attrs={"synthetic_fallback": True})
    real = SimpleNamespace(attrs={})
    assert "실데이터가 아닙니다" in _fallback_banner(fake)
    assert _fallback_banner(real) == ""
    assert "실데이터가 아닙니다" in _fallback_banner(real, fake)  # 하나라도 폴백이면 경고


def test_page_has_loading_overlay_and_korean_labels():
    """폼 페이지에 로딩 오버레이·한글 전략 라벨이 포함된다."""
    from quant.web.app import render_form

    doc = render_form()
    assert 'id="busy"' in doc and "계산 중" in doc      # 로딩 오버레이
    assert "이동평균 교차" in doc and "머신러닝" in doc  # 한글 라벨
    assert 'value="ma_cross"' in doc                    # 값은 코드명 유지


def test_broadcast_page_and_api(tmp_path):
    """방송 모드: 전용 화면에 LIVE·고지 문구, API에 계좌·확정/실시간 구분."""
    import json as _json

    from quant.web.app import broadcast_json, render_broadcast

    doc = render_broadcast()
    assert "LIVE" in doc and "/api/broadcast" in doc
    assert "모의투자" in doc and "보장" in doc          # 방송 고지 상시 노출
    assert "<nav" not in doc                            # 송출용 — 내비게이션 없음

    # 상태 파일 → API JSON (실시간 시세 없이도 확정 기록으로 동작해야 한다)
    d = tmp_path / "paper"; d.mkdir()
    (d / "crypto_BTC.json").write_text(_json.dumps({
        "market": "crypto", "symbol": "BTC/USDT", "start_cash": 10000,
        "cash": 5000, "quantity": 0.1, "avg_price": 50000,
        "history": [{"date": "2026-08-03", "equity": 10200, "return_pct": 2.0,
                     "price": 52000, "weight": 0.5, "hit_rate": 0.52},
                    {"date": "2026-08-04", "equity": 10100, "return_pct": 1.0,
                     "price": 51000, "weight": 0.5, "hit_rate": 0.52}]}),
        encoding="utf-8")
    out = _json.loads(broadcast_json(str(tmp_path), with_live=False))
    assert out["disclaimer"] and "모의" in out["disclaimer"]
    a = out["accounts"][0]
    assert a["key"] == "crypto:BTC/USDT" and a["equity"] == 10100
    assert a["mdd_pct"] < 0                             # 10200→10100 낙폭 반영
    assert "live_equity" not in a                       # 시세 없으면 확정만(정직)
    assert "cash" not in a and "positions" not in a     # 내부 필드 비노출


def test_broadcast_api_includes_reason_and_news(tmp_path):
    """방송 API: 새벽 판단 근거(reason)와 어젯밤 재학습 소식(news)을 담는다."""
    import json as _json

    from quant.web.app import broadcast_json

    d = tmp_path / "paper"; d.mkdir()
    (d / "crypto_BTC.json").write_text(_json.dumps({
        "market": "crypto", "symbol": "BTC/USDT", "cash": 0, "quantity": 0,
        "history": [{"date": "2026-08-04", "equity": 10100, "return_pct": 1.0,
                     "price": 51000, "weight": 0.5,
                     "reason": "매수 +50% — 이동평균 교차: 상승 추세"}]}),
        encoding="utf-8")
    (tmp_path / "retrain_history.jsonl").write_text(
        _json.dumps({"asof": "2026-08-04", "market": "crypto",
                     "symbol": "BTC/USDT", "promoted": True,
                     "champion_strategy": "ml"}) + "\n", encoding="utf-8")
    out = _json.loads(broadcast_json(str(tmp_path), with_live=False))
    assert out["accounts"][0]["reason"].startswith("매수 +50%")
    assert "챔피언 교체" in out["news"] and "BTC/USDT" in out["news"]
    assert out["swaps"][0]["key"] == "crypto:BTC/USDT"


def test_candles_api_shape_and_synthetic_refusal(tmp_path, monkeypatch):
    """캔들 API: 실시세만 내보내고(합성 폴백 거부), 보유 정보를 오버레이용으로 담는다."""
    import json as _json

    import pandas as pd

    import quant.data as qd
    from quant.web.app import _CANDLE_CACHE, candles_json

    _CANDLE_CACHE.clear()
    idx = pd.date_range("2026-08-04 09:00", periods=30, freq="min")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.5, "volume": 1.0}, index=idx)

    class _Stub:
        def __init__(self, synthetic):
            self.synthetic = synthetic

        def get_ohlcv(self, *a, **k):
            d = df.copy()
            if self.synthetic:
                d.attrs["synthetic_fallback"] = True
            return d

    d = tmp_path / "paper"; d.mkdir()
    (d / "crypto_BTC_USDT.json").write_text(_json.dumps({
        "market": "crypto", "symbol": "BTC/USDT", "cash": 1000,
        "quantity": 0.5, "avg_price": 99.5,
        "history": [{"date": "2026-08-04", "weight": 0.64, "equity": 10100,
                     "return_pct": 1.0, "price": 100.5}]}), encoding="utf-8")

    monkeypatch.setattr(qd, "get_provider", lambda m, **k: _Stub(False))
    out = _json.loads(candles_json("crypto:BTC/USDT", state_dir=str(tmp_path)))
    assert len(out["candles"]) == 30 and out["last"] == 100.5
    assert out["candles"][0][0] == "09:00"          # 시:분 라벨
    assert out["position"]["side"] == "매수 보유"
    # ⚠️ 여기는 원래 0.64(=기록의 `weight`)를 기대했다. 그 값은 **오늘 내린
    #    결정**이고, 화면이 "매수 보유 · 비중 X%"로 붙이던 숫자다. 주식은
    #    다음 세션 시가 체결이라 지금 들고 있는 것은 어제 결정의 결과다 —
    #    실측에서 "매수 보유 · 비중 0%"(실제 1.77주 보유)가 나왔다(감사 223).
    #    이제 보유를 보여주고, 오늘의 결정은 `plan`으로 따로 준다.
    assert out["position"]["weight"] == round(0.5 * 100.5 / 10100, 4)
    assert out["position"]["plan"] == 0.64

    _CANDLE_CACHE.clear()
    monkeypatch.setattr(qd, "get_provider", lambda m, **k: _Stub(True))
    out = _json.loads(candles_json("crypto:ETH/USDT", state_dir=str(tmp_path)))
    assert out["candles"] == []                     # 가짜 캔들은 방송에 안 나간다


def test_indicator_chips_champion_aware(tmp_path, monkeypatch):
    """판단 지표 칩: 챔피언 파라미터로 계산되고, 합성 폴백이면 비어 있다."""
    import numpy as np
    import pandas as pd

    import quant.data as qd
    from quant.live.retrain import save_champions
    from quant.web.app import _CHIP_CACHE, indicator_chips

    _CHIP_CACHE.clear()
    n = 260
    close = 100 * np.cumprod(1 + np.full(n, 0.002))     # 뚜렷한 상승 추세
    idx = pd.date_range("2025-06-01", periods=n, freq="D")
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1.0}, index=idx)

    class _Stub:
        def get_ohlcv(self, *a, **k):
            return df.copy()

    monkeypatch.setattr(qd, "get_provider", lambda m, **k: _Stub())
    save_champions({"crypto:BTC/USDT": {
        "strategy": "ma_cross", "params": {"fast": 10, "slow": 30},
        "promotions": 0}}, str(tmp_path))

    chips = indicator_chips("crypto", "BTC/USDT", str(tmp_path))
    labels = [c["label"] for c in chips]
    assert "10일선 > 30일선" in labels                    # 챔피언 파라미터 사용
    assert "RSI(14)" in labels and "200일선(레짐)" in labels
    assert all(c["state"] in ("pos", "neg", "mid") for c in chips)

    # 합성 폴백 → 빈 목록(방송에 가짜 지표 금지)
    _CHIP_CACHE.clear()

    class _Fb(_Stub):
        def get_ohlcv(self, *a, **k):
            d = df.copy(); d.attrs["synthetic_fallback"] = True; return d

    monkeypatch.setattr(qd, "get_provider", lambda m, **k: _Fb())
    assert indicator_chips("crypto", "ETH/USDT", str(tmp_path)) == []


def test_broadcast_has_watermark_event_comment():
    """방송 화면: QR 워터마크·이벤트 배너·장중 상황 코멘트 슬롯이 존재한다."""
    from quant.web.app import render_broadcast

    doc = render_broadcast()
    assert "quant.jiwon-1a2.workers.dev" in doc          # 사이트 유입 다리
    assert 'id="event"' in doc and "popEvent" in doc     # 사건 배너
    assert 'id="c-comment"' in doc and "판단 아님" in doc  # 상황≠판단 명시
    assert "M0 0" in doc or "<path d=" in doc            # QR 인라인


def test_docs_status_live_url_env(tmp_path, monkeypatch):
    """QUANT_LIVE_URL 변수를 설정하면 사이트 라이브 버튼용 필드가 채워진다."""
    import json as _json

    from quant.live.daily import write_docs_status

    monkeypatch.setenv("QUANT_LIVE_URL", "https://youtube.com/@example/live")
    out = tmp_path / "docs" / "status.json"
    st = write_docs_status(str(tmp_path), docs_path=str(out))
    assert st["live_url"] == "https://youtube.com/@example/live"
    monkeypatch.delenv("QUANT_LIVE_URL")
    st = write_docs_status(str(tmp_path), docs_path=str(out))
    assert st["live_url"] is None


# ── 조종석 입금 화면 (만원 → 1억 매칭) ──────────────────────────────

def test_render_deposit_form_without_token_shows_setup(monkeypatch):
    """토큰이 없으면 설정 안내를 보여준다 — 사용자가 길을 잃지 않게."""
    from quant.web.app import render_deposit_form

    monkeypatch.delenv("QUANT_GH_TOKEN", raising=False)
    doc = render_deposit_form()
    assert 'action="/deposit/run"' in doc
    assert "QUANT_GH_TOKEN" in doc and "Fine-grained" in doc
    assert "후원금 자체를 운용하지 않습니다" in doc      # 법적 고지 유지


def test_render_deposit_form_with_token_hides_setup(monkeypatch):
    from quant.web.app import render_deposit_form

    monkeypatch.setenv("QUANT_GH_TOKEN", "github_pat_x")
    doc = render_deposit_form()
    assert "Fine-grained" not in doc
    assert 'name="amount"' in doc and 'name="memo"' in doc


def test_run_deposit_html_validates_amount(monkeypatch):
    from quant.web import app as _app

    monkeypatch.setenv("QUANT_GH_TOKEN", "github_pat_x")
    called = []
    monkeypatch.setattr(_app, "dispatch_deposit", lambda a, m="": called.append(a))
    assert "숫자가 아닙니다" in _app.run_deposit_html({"amount": "abc"})
    assert "이하여야" in _app.run_deposit_html({"amount": "99999999"})
    assert "이하여야" in _app.run_deposit_html({"amount": "0"})
    assert called == []                                  # 검증 실패 시 디스패치 없음


def test_run_deposit_html_dispatches_and_registers_pending(monkeypatch):
    """접수 성공 → 디스패치 1회 + 방송 배너용 pending 등록(숫자 조작은 없음)."""
    import json as _json

    from quant.web import app as _app

    monkeypatch.setenv("QUANT_GH_TOKEN", "github_pat_x")
    calls = []
    monkeypatch.setattr(_app, "dispatch_deposit",
                        lambda a, m="": calls.append((a, m)))
    _app._PENDING_DEPOSITS.clear()
    doc = _app.run_deposit_html({"amount": "10000", "memo": "슈퍼챗 홍길동"})
    assert calls == [(10000, "슈퍼챗 홍길동")]
    assert "접수 완료" in doc and "10,000" in doc
    d = _json.loads(_app.broadcast_json(state_dir="없는_디렉터리", with_live=False))
    assert d["pending"] and d["pending"][0]["amount"] == 10000
    assert d["pending"][0]["memo"] == "슈퍼챗 홍길동"
    _app._PENDING_DEPOSITS.clear()


def test_pending_deposits_expire(monkeypatch):
    """TTL(15분)이 지난 접수는 배너 후보에서 사라진다."""
    import time as _time

    from quant.web import app as _app

    _app._PENDING_DEPOSITS.clear()
    _app._PENDING_DEPOSITS.append(
        {"ts": _time.time() - 16 * 60, "time": "00:00:00",
         "amount": 5000, "memo": ""})
    assert _app._pending_deposits() == []
    assert _app._PENDING_DEPOSITS == []                  # 목록 자체도 정리
    _app._PENDING_DEPOSITS.clear()


def test_dispatch_deposit_calls_github_api(monkeypatch):
    """workflow_dispatch 엔드포인트·헤더·본문 형식 검증 (네트워크 없음)."""
    import quant.utils.http as _http
    from quant.web.app import dispatch_deposit

    monkeypatch.setenv("QUANT_GH_TOKEN", "github_pat_secret")
    monkeypatch.setenv("QUANT_GH_REPO", "owner/repo")
    calls = []
    monkeypatch.setattr(_http, "post_text",
                        lambda url, headers=None, body=None:
                        calls.append((url, headers, body)) or "")
    dispatch_deposit(10000, "메모")
    url, headers, body = calls[0]
    assert url == ("https://api.github.com/repos/owner/repo"
                   "/actions/workflows/deposit.yml/dispatches")
    assert headers["Authorization"] == "Bearer github_pat_secret"
    assert body == {"ref": "main", "inputs": {"amount": "10000", "memo": "메모"}}


def test_dispatch_deposit_requires_token(monkeypatch):
    import pytest

    from quant.web.app import dispatch_deposit

    monkeypatch.delenv("QUANT_GH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="QUANT_GH_TOKEN"):
        dispatch_deposit(10000)


def test_deposit_nav_present():
    """조종석 내비게이션에 '입금' 항목이 있다."""
    from quant.web.app import render_form

    assert 'href="/deposit"' in render_form()


# ── 증권사 스타일 테마 + 실시간 시세 바 ──────────────────────────────

def test_cockpit_has_ticker_bar_and_korean_colors():
    """모든 조종석 페이지에 얇은 시세 바 + 상승 빨강/하락 파랑 토큰이 있다."""
    doc = render_form()
    assert 'id="tickbar"' in doc and "/api/broadcast" in doc
    assert "--up:#f04452" in doc and "--down:#3182f6" in doc


def test_broadcast_korean_market_colors():
    """방송 화면: 상승=빨강(--ok), 하락=파랑(--bad), LIVE 배지는 별도 빨강(--rec)."""
    from quant.web.app import render_broadcast

    doc = render_broadcast()
    assert "--ok:#f04452" in doc and "--bad:#3182f6" in doc
    assert "--rec:#e5484d" in doc and "var(--rec)" in doc
    assert "rotateNews" in doc and "브리핑(참고용" in doc   # 브리핑 회전 배너


def test_docs_pages_ticker_and_colors():
    """사이트(index/paper): 시세 바 요소 + 증권사 색 + 실시간/확정 구분 표기."""
    root = Path(__file__).resolve().parent.parent / "docs"
    for name in ("index.html", "paper.html"):
        doc = (root / name).read_text(encoding="utf-8")
        assert 'id="tickbar"' in doc, name
        assert "#f04452" in doc and "#3182f6" in doc, name
        assert "전일 확정" in doc and "실시간" in doc, name
    paper = (root / "paper.html").read_text(encoding="utf-8")
    assert "시장 브리핑" in paper and "판단에 사용되지 않는" in paper


# ── 전문 차트 엔진 (TradingView Lightweight Charts) ────────────────

def test_lightweight_charts_bundled_and_wired():
    """라이브러리 번들 + 사이트/방송 연동 + SVG 폴백 유지."""
    root = Path(__file__).resolve().parent.parent
    lib = root / "docs" / "assets" / "lightweight-charts.js"
    assert lib.exists() and lib.stat().st_size > 100_000
    assert "Apache License" in lib.read_text(encoding="utf-8")[:400]  # 고지 유지
    paper = (root / "docs" / "paper.html").read_text(encoding="utf-8")
    assert "assets/lightweight-charts.js" in paper
    assert "addAreaSeries" in paper and "function spark(" in paper   # 폴백 보존
    from quant.web.app import render_broadcast
    doc = render_broadcast()
    assert "lightweight-charts" in doc                              # CDN 로드
    assert "addCandlestickSeries" in doc and "candleChart" in doc   # 폴백 보존
    assert "MA20" in doc                                            # 분석 보조선


def test_candles_json_has_epoch(tmp_path, monkeypatch):
    """캔들 6번째 필드 epoch(초) — 차트 엔진용. 라벨 5필드는 하위호환 유지."""
    import json as _json

    import pandas as pd

    import quant.data as qd
    from quant.web import app as _app

    idx = pd.date_range("2026-08-05 09:00", periods=30, freq="1min")
    df = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                       "volume": 1.0}, index=idx)

    class _P:
        def get_ohlcv(self, *a, **k):
            return df

    monkeypatch.setattr(qd, "get_provider", lambda m, **k: _P())
    _app._CANDLE_CACHE.clear()
    d = _json.loads(_app.candles_json("crypto:TEST/USDT", state_dir=str(tmp_path)))
    row = d["candles"][0]
    assert len(row) == 6
    assert row[5] == int(idx[0].timestamp())
