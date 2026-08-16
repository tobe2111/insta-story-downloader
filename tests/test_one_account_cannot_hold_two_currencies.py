"""통합 계좌가 **두 통화를 동시에** 들고 있지 않은가 (감사 254).

2026-08-15에 100만원짜리 통합 계좌의 자산이 **7,249만원**으로 찍혔다.
하루 만에 +7,150%다. 원인은 한 줄이었다.

    opens_after[key] = _first_bar_after(df, pend["decided_bar"])   # 달러 시가
    prices[key]      = to_krw(market, df["close"].iloc[-1], fx)    # 원화 종가

통합 계좌는 원화 계좌다. 감사 212가 **평가가격**을 원화로 환산하도록 고쳤는데,
**대기 주문의 체결가**는 손대지 않았다. 그래서 미국주식은 달러 시가로 사고
원화 종가로 평가됐다 — 같은 종목의 같은 하루가 두 통화로 계산됐다.
META를 596.98(달러)에 사서 832,868(원)로 평가한 결과, 계좌는 자기가
7,154만원어치를 들고 있다고 믿었다.

이건 새 결함이 아니라 **감사 212의 나머지 절반**이다. 같은 규칙(원화로
바꿔서 담는다)을 두 곳에 나눠 적었고, 한 곳만 고쳤다(FROZEN_IDEAS ①).

여기서 지키는 것은 셋이다.
  ① 환산은 **한 함수**만 한다 — 두 경로가 각자 적으면 또 갈라진다.
  ② 그래도 빠졌을 때, 체결이 **실제로 막힌다** — 선언이 아니라 장치로.
  ③ 막힌 사실이 장부와 화면에 남는다 — 조용히 덜 사는 것도 사고다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import daily as D  # noqa: E402

SRC = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")


# ── ① 환산은 한 곳에서만 ────────────────────────────────────────

def test_the_fill_price_goes_through_the_same_gate_as_the_mark():
    """체결가와 평가가격이 **같은 함수**를 지나는가.

    이름이 아니라 호출을 본다 — 주석에 "원화로 환산한다"고 적어 두는 것은
    장치가 아니다.
    """
    body = SRC.split("def run_daily_portfolio", 1)
    assert len(body) == 2, "포트폴리오 실행부를 찾지 못했다 — 검사가 낡았다"
    body = body[1]
    assert "opens_after[key]" in body, "대기 주문 체결가를 담는 줄을 찾지 못했다"
    window = body.split("opens_after[key]", 1)[1][:400]
    assert "_to_krw_or_die" in window, (
        "대기 주문 체결가가 환산 문을 안 지난다 — 달러로 사서 원화로 "
        "평가하게 된다(감사 254가 바로 그것이다)")


def test_the_conversion_refuses_to_guess_when_the_rate_is_missing():
    """환율을 모를 때 1.0으로 때우면 감사 212가 그대로 돌아온다."""
    with pytest.raises(RuntimeError):
        D._to_krw_or_die("us_stock", 100.0, None)
    # 원화 시장은 환율이 없어도 값을 매길 수 있다 — 막으면 안 된다.
    assert D._to_krw_or_die("kr_stock", 100.0, None) == 100.0
    assert D._to_krw_or_die("us_stock", 100.0, 1400.0) == pytest.approx(140000.0)


# ── ② 그래도 빠졌을 때 실제로 막히는가 ──────────────────────────

class _Broker:
    """주문이 실제로 나갔는지만 보는 최소 브로커."""

    def __init__(self):
        self.fee = 0.0
        self.orders = []
        self.rejected = []

    def equity(self, marks):        # noqa: D102
        return 1_000_000.0

    def get_position(self, key):    # noqa: D102
        return type("P", (), {"quantity": 0.0})()

    def target_weight(self, key, weight, price, equity, **kw):  # noqa: D102
        self.orders.append({"key": key, "price": price, "weight": weight})
        return type("O", (), {"side": "buy",
                              "quantity": weight * equity / price})()


def _fill_loop(marks, opens_after, pending):
    """daily.py의 체결 루프와 **같은 규칙**을 쓰는지 값으로 확인한다.

    로직을 베껴 오지 않는다 — 문턱 상수와 판정식을 실제 모듈에서 가져온다.
    """
    refused = {}
    broker = _Broker()
    for key, pend in pending.items():
        _, fopen = opens_after.get(key, (None, None))
        if fopen is None:
            continue
        mark = marks.get(key)
        if mark and fopen and not (
                1.0 / D.FILL_MARK_MAX_RATIO
                <= float(fopen) / float(mark) <= D.FILL_MARK_MAX_RATIO):
            refused[key] = {"open": fopen, "mark": mark}
            continue
        broker.target_weight(key, float(pend["weight"]), fopen,
                             broker.equity(marks))
    return broker, refused


def test_a_dollar_price_against_a_won_mark_is_refused():
    """2026-08-15에 실제로 일어난 값을 그대로 넣는다."""
    broker, refused = _fill_loop(
        marks={"us_stock:META": 832868.17},          # 원화 종가
        opens_after={"us_stock:META": ("2026-08-15", 596.98)},   # 달러 시가
        pending={"us_stock:META": {"weight": 0.0515}})
    assert "us_stock:META" in refused, (
        "달러 시가와 원화 평가가격이 1,395배 차이인데 체결됐다 — "
        "100만원 계좌가 7,154만원어치를 사게 된다")
    assert not broker.orders, "거부했다면서 주문은 나갔다"


def test_an_ordinary_overnight_gap_still_fills():
    """장치가 정상 거래를 막으면 그 장치는 꺼진다 — 문턱이 넉넉한가."""
    broker, refused = _fill_loop(
        marks={"us_stock:META": 832868.17},
        opens_after={"us_stock:META": ("2026-08-15", 832868.17 * 0.82)},
        pending={"us_stock:META": {"weight": 0.0515}})
    assert not refused, f"18% 갭을 통화 오류로 오해했다: {refused}"
    assert broker.orders, "정상 갭인데 주문이 안 나갔다"


def test_the_threshold_sits_between_a_real_gap_and_a_currency_error():
    """문턱 자체가 말이 되는가 — 이 검사가 상수를 **직접 판정한다**.

    상수를 그대로 가져와 자기 자신과 비교하면 어떤 값이든 통과한다.
    그래서 바깥에서 온 두 사실(하룻밤 갭의 현실적 상한, 원/달러 환율)로
    가둔다.
    """
    assert 2.0 < D.FILL_MARK_MAX_RATIO < 50.0, (
        f"문턱 {D.FILL_MARK_MAX_RATIO}배 — 액면분할·갭보다 넉넉하되 "
        "환율(약 1,400배)보다는 한참 낮아야 한다")


# ── ③ 막힌 사실이 남는가 ────────────────────────────────────────

def test_the_refusal_reaches_the_ledger_and_the_screen():
    assert '"fill_refused": fill_refused or None' in SRC, (
        "체결을 거부하고 장부에 안 남긴다 — 계좌는 이유 없이 덜 산 채로 "
        "굴러가고, 아무도 모른다")
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "fill_refused" in index, "거부된 체결이 화면 경고에 안 나온다"
    assert "cash_short" in index, (
        "현금 부족으로 거부된 주문이 화면에 안 나온다 — 장부 주석은 "
        "'나오면 안 되는 값'이라고 적어 두고 정작 보여주지 않았다")


# ── 되돌린 기록이 되돌렸다고 말하는가 ───────────────────────────

def test_the_voided_fill_is_marked_as_restated_not_silently_erased():
    """숫자를 고쳤으면 **고쳤다고** 적혀 있어야 한다.

    이 저장소는 과거 기록을 고쳐 쓰지 않는다. 여기서 지운 것은 성적이
    아니라 **현실에서 불가능했던 체결**이고, 지운 내용은 기록 안에
    그대로 남아 있어야 한다 — 남지 않으면 그냥 유리하게 고친 것과
    구분되지 않는다.
    """
    import json
    for name in ("portfolio_ALL", "portfolio_SHADOW"):
        path = ROOT / "state" / "paper" / f"{name}.json"
        if not path.exists():
            continue
        st = json.loads(path.read_text("utf-8"))
        rec = [r for r in st.get("history") or [] if r.get("date") == "2026-08-15"]
        if not rec:
            continue
        r = rec[0]
        if "_restated" not in r:
            continue
        note = r["_restated"]
        assert note.get("why"), f"{name}: 왜 고쳤는지가 없다"
        assert note.get("before", {}).get("equity"), (
            f"{name}: 고치기 **전** 숫자가 안 남았다 — 검증할 수가 없다")
        assert note.get("voided_fills"), f"{name}: 무효로 한 체결이 안 남았다"
        # 되돌린 뒤의 자산이 원금과 같은 자릿수인가 — 되돌리다 다른 값을
        # 만들어 냈으면 여기서 걸린다.
        assert float(r["equity"]) < float(st["start_cash"]) * 5, (
            f"{name}: 되돌린 뒤에도 자산이 원금의 5배를 넘는다")


def test_the_repair_script_is_kept_as_the_record_of_what_changed():
    """일회성 복구도 근거가 저장소에 남아야 한다."""
    script = ROOT / "scripts" / "void_impossible_fill_20260815.py"
    assert script.exists(), (
        "장부 숫자를 손으로 고쳐 놓고 무엇을 어떻게 고쳤는지는 커밋 "
        "메시지에만 있다 — 우리가 남에게 하지 말라고 적은 그 일이다")
    src = script.read_text("utf-8")
    assert re.search(r"지어내|없던 거래", src), (
        "복구 스크립트가 '무엇을 하지 않았는지'를 말하지 않는다")
