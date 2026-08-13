"""신선도는 '주장'이 아니라 '받은 사실'이어야 한다 (사장님 2026-08-13).

사장님 요청: "신선도를 최대한 실시간으로, 무료 선에서." + "홈페이지에 주가가
모두 실시간으로 반영되고, 투자한 내 자산 변동도 같이."

무료 선에서의 사다리:
    한국주식 — 한국투자증권 OpenAPI(무료·공식·실시간). 앱키가 있을 때만.
    미국주식 — Finnhub 무료 티어(분당 60회). 토큰이 있을 때만.
    코인     — 바이낸스 WebSocket(무계정·무제한). 브라우저 직결이라 워커 비용 0.
    환율     — 야후 KRW=X. 초 단위로 볼 이유가 없다.
    폴백     — 전부 야후(한국주식은 약 20분 지연).

핵심 계약 — **라벨을 코드에 박지 않는다.**
  감사 229가 정확히 그 반대였다: 화면은 '준실시간'이라 적혀 있었는데
  요청은 매번 거부당하고 있었다. 그래서 워커는 어느 소스로 받았는지를
  `source`·`delayed`로 함께 돌려주고, 화면은 그 값으로 라벨을 정한다.
  실시간 소스가 죽은 날 화면은 스스로 '지연'으로 바뀐다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
IDX = (ROOT / "docs" / "index.html").read_text("utf-8")
WORKER = (ROOT / "worker.js").read_text("utf-8")


# ── ① 워커: 소스 사다리 ───────────────────────────────────────


def test_korean_stocks_prefer_the_realtime_source():
    fn = WORKER[WORKER.find("async function oneQuote("):]
    fn = fn[:fn.find("async function quotes(")]
    assert "KR_SUFFIX.test(s)" in fn and "kisQuote" in fn, (
        "한국주식이 실시간 소스를 먼저 보지 않는다")
    assert "env.KIS_APP_KEY && env.KIS_APP_SECRET" in fn, (
        "앱키 없이 KIS를 부르려 한다 — 매번 실패한다")
    assert "yahooQuote" in fn, "실시간 소스가 죽었을 때 내려갈 곳이 없다"


def test_the_exchange_rate_never_goes_to_the_stock_provider():
    """KRW=X는 주식이 아니다 — Finnhub에 물으면 빈손으로 돌아온다."""
    fn = WORKER[WORKER.find("async function oneQuote("):]
    fn = fn[:fn.find("async function quotes(")]
    assert 's.indexOf("=") < 0' in fn, "환율 심볼을 주식 소스로 보낸다"


def test_every_quote_carries_where_it_came_from():
    """source·delayed가 없으면 화면은 라벨을 지어낼 수밖에 없다."""
    for fn_name in ("yahooQuote", "kisQuote", "finnhubQuote"):
        i = WORKER.find("function " + fn_name + "(")
        assert i > 0, fn_name
        body = WORKER[i:i + 1800]
        assert "source:" in body, f"{fn_name}가 출처를 안 남긴다"
        assert "delayed:" in body, f"{fn_name}가 지연 여부를 안 남긴다"


def test_only_yahoo_korean_quotes_are_marked_delayed():
    """야후 .KS는 약 20분 지연 — 그 사실이 응답에 실려야 한다."""
    body = WORKER[WORKER.find("async function yahooQuote("):]
    body = body[:body.find("async function kisToken(")]
    assert "delayed: KR_SUFFIX.test(s)" in body
    for fn_name in ("kisQuote", "finnhubQuote"):
        i = WORKER.find("function " + fn_name + "(")
        assert "delayed: false" in WORKER[i:i + 1800], (
            f"{fn_name}는 실시간인데 지연으로 표시된다")


def test_the_kis_token_is_cached_not_reissued_every_call():
    """매 요청 토큰을 발급하면 유량 제한에 막히고, 그 실패는 조용하다."""
    body = WORKER[WORKER.find("async function kisToken("):]
    body = body[:body.find("async function kisQuote(")]
    assert "cache.match(key)" in body and "cache.put(key" in body
    m = re.search(r"KIS_TOKEN_TTL\s*=\s*3600\s*\*\s*(\d+)", WORKER)
    assert m and int(m.group(1)) < 24, (
        "토큰 캐시가 발급 유효기간(24시간) 이상이다 — 만료된 토큰을 쓴다")


def test_no_credentials_are_committed():
    """앱키·시크릿은 Cloudflare 시크릿에만 있어야 한다."""
    for probe in ("KIS_APP_KEY", "KIS_APP_SECRET", "FINNHUB_TOKEN"):
        for hit in re.findall(probe + r'\s*[:=]\s*["\'][^"\']+["\']', WORKER):
            raise AssertionError(f"자격증명이 코드에 박혀 있다: {hit}")
        assert "env." + probe in WORKER, f"{probe}를 환경에서 읽지 않는다"


def test_the_cache_gets_shorter_when_a_realtime_source_is_on():
    """실시간 소스를 붙여 놓고 15초 캐시를 쓰면 실시간이 아니다."""
    body = WORKER[WORKER.find("async function quotes("):]
    assert "const ttl = live ? LIVE_TTL : CACHE_TTL;" in body
    live = int(re.search(r"LIVE_TTL\s*=\s*(\d+)", WORKER).group(1))
    base = int(re.search(r"CACHE_TTL\s*=\s*(\d+)", WORKER).group(1))
    assert 0 < live < base


# ── ② 화면: 코인 스트림 + 게이팅 ──────────────────────────────


def test_crypto_uses_a_stream_not_a_poll():
    assert "wss://stream.binance.com" in IDX
    assert "@miniTicker" in IDX


def test_a_dropped_stream_falls_back_instead_of_freezing():
    """끊긴 걸 모르면 화면은 마지막 값에서 굳은 채 라벨만 남는다(감사 229)."""
    fn = IDX[IDX.find("function openCryptoStream()"):]
    fn = fn[:fn.find("function pollStocks()")]
    assert "onclose" in fn and "onerror" in fn
    assert "pollCrypto()" in fn, "스트림이 끊겨도 폴링으로 내려가지 않는다"
    assert "openCryptoStream()" in fn.split("onclose", 1)[1], "재접속이 없다"


def test_polling_stops_when_nobody_is_looking():
    """안 보는 탭에 무료 한도를 쓰지 않는다."""
    assert "document.hidden" in IDX
    assert 'addEventListener("visibilitychange"' in IDX


def test_polling_slows_down_when_the_markets_are_closed():
    """장이 닫히면 값이 안 변한다 — 그 시간을 아껴 장중을 촘촘히 쓴다."""
    assert "function marketOpenish()" in IDX
    op = int(re.search(r"STOCK_MS_OPEN=(\d+)", IDX).group(1))
    cl = int(re.search(r"STOCK_MS_CLOSED=(\d+)", IDX).group(1))
    assert op < cl, "장중이 장 밖보다 느리다"
    assert op <= 15000, "장중 주기가 15초보다 느리다"


def test_the_free_tier_budget_still_fits():
    """Cloudflare 무료는 10만 요청/일 — 장중에만 부르면 몇 명까지 되는가.

    ⚠️ 이 검사는 '한도를 넘지 않는다'가 아니라 **'우리가 아는 숫자를
       적어 둔다'**가 목적이다. 주기를 몰래 올리면 여기서 걸린다.
    """
    op = int(re.search(r"STOCK_MS_OPEN=(\d+)", IDX).group(1)) / 1000
    hours_open = 13.0                      # 한국 6.7h + 미국 6.9h(대략)
    per_viewer = hours_open * 3600 / op
    viewers = 100_000 / per_viewer
    assert per_viewer <= 4000, f"뷰어당 하루 {per_viewer:.0f}회는 과하다"
    assert viewers >= 25, f"동시 시청자 {viewers:.0f}명이면 무료 한도가 빠듯하다"


# ── ③ 자산이 함께 움직인다 ────────────────────────────────────


def test_the_account_value_is_repainted_on_every_tick():
    """시세만 흐르고 자산이 안 움직이면 사장님 질문에 답한 게 아니다."""
    for fn_name in ("pollStocks", "pollCrypto", "openCryptoStream"):
        i = IDX.find("function " + fn_name + "()")
        assert i > 0, fn_name
        rest = IDX[i + 10:]
        end = rest.find("\n  function ")            # 다음 함수 선언까지
        body = rest[:end if end > 0 else 2500]
        assert "paintLive()" in body, f"{fn_name} 뒤에 자산을 다시 안 그린다"


def test_the_freshness_sentence_is_counted_not_hardcoded():
    """"코인은 실시간, 주식은 지연"을 문장에 박으면, KIS를 붙여 한국주식이
    실시간이 된 날에도 화면은 계속 지연이라고 말한다(감사 229의 교훈).
    """
    fn = IDX[IDX.find("function paintLive()"):]
    fn = fn[:fn.find("function drawTick()")]
    assert "lv.delayed" in fn, "지연 여부를 세지 않는다"
    assert "nLive" in fn and "nLate" in fn
    assert "실시간 '+nLive" in fn or "실시간 " in fn


def test_the_ticker_label_comes_from_the_response():
    tick = IDX[IDX.find("function drawTick()"):]
    tick = tick[:tick.find("function ")+0 if False else tick.find("drawTick();")]
    assert "lv.delayed" in tick, "시세띠 라벨이 받은 사실을 안 본다"


# ── ④ 소스가 아니라 **동작**으로 (node 하네스) ────────────────


def test_the_worker_ladder_behaves(tmp_path):
    """워커를 실제로 실행해 소스 선택·폴백·토큰 재사용을 확인한다.

    ⚠️ 위 검사들은 전부 소스 문자열을 본다. 이 저장소에서 여러 번 겪었듯
       그런 검사는 변이를 놓친다 — 실제로 이 하네스가 **토큰을 종목마다
       재발급하던 결함**을 잡아냈다(7종목이면 발급 7회, KIS 유량 제한).
       소스만 보던 검사는 "캐시를 쓴다"만 확인하고 통과했었다.
    """
    import shutil
    import subprocess

    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        import pytest
        pytest.skip("node 없음 — 워커 동작 검사 생략")
    r = subprocess.run([node, str(ROOT / "tests" / "worker_ladder_check.mjs")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)
