"""준실시간 시세가 실제로 도착하는가 (감사 229) + 참고값이 장부를 안 덮는가.

배경 ①:
  사이트는 맨 위 시세띠를 "준실시간"이라고 라벨하고, 워커(`/api/quotes`)를
  통해 야후 시세를 받아 온다. 그런데 페이지가 보낸 것은 **장부 키**
  (`us_stock:AAPL`)였고, 워커의 심볼 검사는

      SYM_RE = /^[A-Za-z0-9.^=-]{1,12}$/

  라 콜론도 밑줄도 받지 않는다. 20종목이 **전부** 걸러져 워커는 400을
  돌려줬고, `.catch(()=>{})`가 그 실패를 통째로 삼켰다. 주식 시세띠는
  **한 번도** 갱신된 적이 없이 영원히 '전일 확정'만 띄웠다.

  라벨이 정직했던 덕에 화면이 거짓말을 하지는 않았지만, 기능은 죽어
  있었고 아무도 몰랐다 — 이 저장소가 가장 경계하는 '조용한 고장'이다.
  서로 다른 두 파일(docs/index.html · worker.js)이 지켜야 할 약속이라
  검사가 둘을 묶는다(감사 219의 교훈: 같은 판정을 두 곳에서 하면 갈라진다).

배경 ②:
  같은 날 사장님 질문 — "잔고 평가금액도 시세띠랑 주기를 맞춰야 하지
  않나?" 맞추되 **덮어쓰지 않는다.** 확정값은 수익률·낙폭·TWR·킬스위치가
  함께 쓰는 숫자다. 참고값은 따로 적고, 환율을 못 받으면 해외 종목은
  아예 값을 매기지 않는다(1.0으로 때우지 않는다 — 감사 212와 같은 규칙).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
IDX = (ROOT / "docs" / "index.html").read_text("utf-8")
WORKER = (ROOT / "worker.js").read_text("utf-8")
# 준실시간 평가의 순수 계산은 2026-08-13부터 이 모듈에 있다 — 인라인
# 스크립트 안에서는 검사가 **실행**할 수 없기 때문이다. 값으로 확인하는
# 것은 tests/live_marks_check.mjs가 하고, 여기서는 계약의 자리만 본다.
LIVE = (ROOT / "docs" / "assets" / "live-marks.js").read_text("utf-8")


def _worker_symbol_rule():
    m = re.search(r"const SYM_RE\s*=\s*/(.+?)/;", WORKER)
    assert m, "worker.js의 심볼 검사 규칙을 찾지 못했다 — 검사가 낡았다"
    return re.compile(m.group(1).replace("\\^", "^"))


def _worker_max_symbols() -> int:
    m = re.search(r"const MAX_SYMBOLS\s*=\s*(\d+);", WORKER)
    assert m
    return int(m.group(1))


# ── ① 페이지가 보내는 것을 워커가 받아들이는가 ────────────────


def test_every_symbol_the_page_sends_passes_the_worker_filter():
    """이게 안 맞으면 워커는 400을 주고, 페이지는 조용히 포기한다."""
    from quant.markets import AUTO_TARGETS

    rule = _worker_symbol_rule()
    rejected = [sym for market, sym in AUTO_TARGETS
                if market != "crypto" and not rule.match(sym)]
    assert not rejected, (
        "워커가 거부하는 심볼을 페이지가 보낸다 — 시세가 영영 안 온다: "
        f"{rejected}")


def test_the_ledger_key_itself_would_have_been_rejected():
    """대조군 — 예전 방식(장부 키 그대로)은 실제로 전부 걸러진다.

    이 검사가 없으면 "원래 되던 것 아니냐"는 의심을 잠재울 수 없다.
    """
    from quant.markets import AUTO_TARGETS

    rule = _worker_symbol_rule()
    keys = [f"{m}:{s}" for m, s in AUTO_TARGETS if m != "crypto"]
    assert keys and not any(rule.match(k) for k in keys), (
        "장부 키가 통과한다 — 그렇다면 감사 229의 진단이 틀렸다")


def test_the_page_sends_tickers_and_maps_them_back():
    poll = IDX[IDX.find("function pollStocks()"):]
    poll = poll[:poll.find("pollCrypto();")]
    assert 'k.split(":")[1]' in poll, "장부 키에서 티커를 뽑지 않는다"
    assert "bySym[s]" in poll, "받은 시세를 장부 키로 되돌리지 않는다"
    assert "syms.concat" in poll, "요청에 티커 목록을 쓰지 않는다"
    assert not re.search(r"symbols=\"\+encodeURIComponent\(ks\b", poll), (
        "아직도 장부 키를 그대로 보낸다")


def test_the_request_fits_the_worker_symbol_budget():
    """운영 종목 + 환율이 워커 상한(MAX_SYMBOLS)을 넘으면 뒤쪽이 잘린다."""
    from quant.markets import AUTO_TARGETS

    n = len([1 for m, _ in AUTO_TARGETS if m != "crypto"]) + 1   # +1 = KRW=X
    assert n <= _worker_max_symbols(), (
        f"한 번에 {n}개를 보내는데 워커 상한은 {_worker_max_symbols()}개다 — "
        "초과분은 조용히 잘린다")


def test_the_exchange_rate_is_requested_too():
    """해외 종목을 원화로 평가하려면 실시간 환율이 함께 있어야 한다."""
    assert '"KRW=X"' in IDX
    assert _worker_symbol_rule().match("KRW=X"), (
        "워커가 환율 심볼을 거부한다")


# ── ② 참고값이 확정값을 덮지 않는다 ───────────────────────────


def test_live_marks_are_written_beside_the_book_value_not_over_it():
    assert 'class="cd lvv"' in IDX, "준실시간 참고값 자리가 없다"
    assert "function paintLive()" in IDX
    # 확정값(won(r.value))은 그대로 남아 있어야 한다
    assert "won(r.value)+" in IDX, "장부 확정 평가금액이 사라졌다"


def test_foreign_holdings_are_not_valued_without_a_rate():
    """환율을 못 받으면 값을 매기지 않는다 — 1.0으로 때우지 않는다.

    값으로 확인하는 것은 `tests/live_marks_check.mjs`다(달러 종목 null,
    원화 종목은 살아 있음). 여기서는 **화면이 그 계산에 위임하는지**만 본다 —
    페이지가 자기 식을 따로 쓰기 시작하면 두 곳이 갈라진다.
    """
    fn = IDX[IDX.find("function paintLive()"):]
    fn = fn[:fn.find("function drawTick()")]
    assert "QuantLive.markHoldings(all,live,liveFx)" in fn, (
        "화면이 준실시간 평가를 스스로 계산한다 — 계산은 한 곳에서만")
    assert "if (!fx) return null;" in LIVE, (
        "환율이 없을 때 해외 종목에 값을 매긴다")
    # 원화 시장은 환율 없이도 값을 매길 수 있어야 한다(대조군)
    assert "if (!USD_MKT.test(key)) return qty * lv.px;" in LIVE


def test_the_live_total_says_it_is_not_used_for_returns():
    note = IDX[IDX.find("const note=document.getElementById(\"live-note\")"):]
    note = note[:note.find("function drawTick()")]
    assert "수익률·낙폭·판단에는 쓰지 않습니다" in note
    # 신선도 문구(실시간/지연)는 모듈이 **세어서** 만든다
    assert "지연" in LIVE, "무료 시세의 지연을 밝히지 않는다"


def test_returns_and_drawdown_never_read_the_live_prices():
    """수익률·낙폭·TWR은 장부 기록만 쓴다 — 실시간 변수가 닿으면 안 된다.

    ⚠️ 닿는 순간 낙폭이 초 단위로 흔들리는데 킬스위치는 새벽에 한 번만
       돈다. 화면과 브레이크가 다른 숫자를 보는 것이 감사 224의 결함이었다.
    """
    # 오답 노트(일간 수익률 계산)와 메인 차트가 쓰는 구간
    for marker in ("/* --- 오답 노트 --- */", "/* --- 메인 차트 --- */"):
        i = IDX.find(marker)
        assert i > 0, marker
        block = IDX[i:i + 1600]
        for banned in ("live[", "liveFx", "liveValueOf"):
            assert banned not in block, (
                f"{marker} 구간이 준실시간 값을 읽는다: {banned}")


def test_a_partial_live_total_is_explained_not_silently_dropped():
    """일부 종목 시세를 못 받으면 합계를 내지 않되 **왜인지는 말한다**.

    부분 합계는 계좌를 실제보다 작게 보이게 하므로 내면 안 된다. 그렇다고
    그냥 지우면 화면이 아무 말 없이 조용해진다 — 오늘 고친 결함(감사 213·
    220·226)이 전부 그 모양이었다.
    """
    assert "missing.push" in LIVE, "어느 종목이 빠졌는지 모으지 않는다"
    fn = IDX[IDX.find("function paintLive()"):]
    fn = fn[:fn.find("function drawTick()")]
    assert "표시하지 않습니다" in fn and "받지 못했습니다" in fn, (
        "부분 수신일 때 이유를 말하지 않는다")
    assert "m.missing.length&&m.marked>0" in fn, (
        "한 건도 못 받은 경우와 일부만 못 받은 경우를 구분하지 않는다")
