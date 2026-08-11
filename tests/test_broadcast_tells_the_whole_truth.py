"""방송이 **불리한 사실까지 말하는가** (감사 95·96·97).

세 가지가 한 계열이다 — 장부에는 있는데 방송에는 없거나, 있다가 조용히
사라진다.

**95. 카드가 '누적'을 '오늘'이라 불렀다.**
2026-08-10에 캡션의 같은 결함을 고치고 trust.html에 공개했는데,
**카드는 그대로였다.** `return_pct`(원금 대비 누적)를 큰 글씨로
"오늘 -0.06%"라 찍고 훅까지 그 값으로 골랐다. 누적이 +40%가 되면 매일
"오늘 +40%"가 나가고, 크게 잃은 날에도 "좋은 날" 훅이 붙는다.
고친 결함의 **형제를 안 찾은 것**이 이 프로젝트에서 반복되는 실패다.

**96. 사람의 개입이 방송에 없었다.**
장부는 이렇게 적어 뒀다:

    # 어드민 개입의 흔적 — 일시정지·노출 배수는 숨기지 않고 기록한다
    "paused": paused, "exposure_scale": ...

기록은 했는데 **사이트에도 카드에도 캡션에도 표시되지 않았다.** 이 시스템
에서 사람이 결과를 손으로 바꿀 수 있는 유일한 통로가 그 둘이다. 손댄 날의
성적은 전략만의 결과가 아니고, 회의적인 독자가 가장 먼저 묻는 것도 그거다.

**97. 길이 제한이 경고부터 잘랐다.**
스레드 캡션은 500자를 넘으면 짧은 판으로 바꾸는데, 킬스위치 문구가
'배분 상위' 줄에 붙어 있어 **하이라이트와 함께 잘려 나갔다.** 코드 주석은
"링크·고지는 지키고 하이라이트를 줄인다"라고 적혀 있었는데 실제로는
반대였다. 쓸 말이 많은 날일수록 경고가 사라진다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.reporting.social import (        # noqa: E402
    THREADS_TEXT_LIMIT,
    build_captions,
)

CARD = (ROOT / "docs" / "sns_card.html").read_text("utf-8")
INDEX = (ROOT / "docs" / "index.html").read_text("utf-8")


def _status(**over):
    rec = {"date": "2026-08-10", "equity": 79_950.0, "return_pct": -0.06,
           "day_pct": -0.05, "twr_pct": -0.06, "weight": 0.07,
           "risk_scale": 1.0, "paused": False, "exposure_scale": 1.0,
           "alloc": {"us_stock:AAPL": 0.15},
           "applied": {"us_stock:AAPL": 0.012},
           "champion": {"symbols": 20}}
    rec.update(over)
    return {"updated": "2026-08-10T21:00:00Z",
            "paper": {"portfolio:ALL": {"history": [rec]},
                      "us_stock:AAPL": {"history": [
                          {"date": "2026-08-10", "weight": 0.12}]}},
            "symbols": {"us_stock:AAPL": {"name": "애플"}},
            "retrain_recent": []}


# ── 95. 누적을 '오늘'이라 부르지 않는다 ─────────────────────────

def test_the_card_reads_the_day_figure_not_the_cumulative_one():
    """카드가 `day_pct`를 쓰는가 — `return_pct`를 '오늘'이라 부르면 안 된다."""
    assert "last.day_pct" in CARD, (
        "카드가 하루치를 장부에서 읽지 않는다 — 누적을 '오늘'이라 부르게 된다")


def test_the_card_labels_the_cumulative_number_as_cumulative():
    body = CARD.split("}else if(n===2){", 1)[1].split("}else if(n===", 1)[0]
    assert "누적 '+esc(retTxt)" in body, (
        "카드의 큰 숫자가 누적인데 '누적'이라 적지 않는다")
    assert "오늘 '+esc(dayTxt)" in body, "하루치를 따로 보이지 않는다"
    assert "오늘 '+esc(retTxt)" not in body, (
        "카드가 여전히 누적을 '오늘'이라 찍는다 — 2026-08-10에 공개 정정한 "
        "바로 그 결함이다")


def test_the_card_hook_is_chosen_by_the_day_figure():
    """훅도 하루치로 고른다 — 누적으로 고르면 잃은 날에도 '좋은 날'이 뜬다."""
    hook = CARD.split("var hook;", 1)[1].split("var head=", 1)[0]
    assert re.search(r"hd\s*<=\s*-1", hook) and "hd==null" in hook, (
        f"훅이 하루치가 아닌 값으로 갈린다:\n{hook[:300]}")
    assert not re.search(r"\bret\s*<=\s*-1", hook), (
        "훅이 아직 누적(ret)으로 갈린다")
    # ⚠️ 분기가 `hd`를 본다는 것만으로는 부족하다 — `hd`에 누적을 담으면
    #    그대로 통과한다(변이 시험이 이 구멍을 잡았다). **무엇을 담는지**를
    #    본다.
    assert re.search(r"var hd\s*=\s*dayp\s*;", CARD), (
        "훅의 기준값(hd)에 하루치가 아닌 값을 담고 있다 — 이름만 바뀌고 "
        "누적으로 훅을 고르던 결함이 그대로다")


# ── 96. 사람의 개입을 숨기지 않는다 ────────────────────────────

def test_a_paused_day_says_so_in_the_caption():
    caps = build_captions(_status(paused=True), site_url="https://e.com")
    for text in (caps["instagram"], caps["threads"]):
        assert "사람의 개입" in text and "일시정지" in text, (
            "운영자가 신규 주문을 멈춘 날인데 방송이 아무 말도 하지 않는다 — "
            f"'전부 자동'이라는 주장이 거짓이 된다\n{text}")


def test_a_hand_set_exposure_says_so_in_the_caption():
    caps = build_captions(_status(exposure_scale=0.5), site_url="https://e.com")
    for text in (caps["instagram"], caps["threads"]):
        assert "사람의 개입" in text and "50%" in text, text


def test_an_untouched_day_says_nothing_extra():
    """손대지 않은 날까지 경고를 붙이면 문구가 의미를 잃는다."""
    caps = build_captions(_status(), site_url="https://e.com")
    for text in (caps["instagram"], caps["threads"]):
        assert "사람의 개입" not in text


def test_the_card_and_the_site_show_the_intervention_too():
    assert "last.paused" in CARD and "last.exposure_scale" in CARD, (
        "카드가 사람의 개입을 읽지 않는다")
    assert "pfLast.paused" in INDEX and "pfLast.exposure_scale" in INDEX, (
        "사이트의 '지금 켜진 경고'에 사람의 개입이 없다")


# ── 97. 길이 제한이 경고를 자르지 않는다 ───────────────────────

def test_the_short_thread_keeps_the_warnings():
    """500자 넘겨 짧은 판으로 바뀌어도 킬스위치·개입 고지는 남는다."""
    long_names = {f"kr_stock:{i:06d}.KS": {"name": "아주아주긴종목이름" * 3}
                  for i in range(3)}
    st = _status(risk_scale=0.5, paused=True, exposure_scale=0.5,
                 applied={k: 0.1 for k in long_names})
    st["symbols"].update(long_names)
    for k in long_names:
        st["paper"][k] = {"history": [{"date": "2026-08-10", "weight": 0.2}]}
    # 훅·재학습 문구까지 길어지도록 재학습 기록도 채운다
    st["retrain_recent"] = [{"asof": "2026-08-10", "promoted": True}] * 9

    th = build_captions(st, site_url="https://example.com")["threads"]
    assert len(th) <= THREADS_TEXT_LIMIT, f"{len(th)}자"
    assert "킬스위치" in th, (
        "길이 때문에 짧은 판으로 바뀌자 킬스위치 고지가 사라졌다 — "
        f"쓸 말이 많은 날일수록 경고가 없어진다\n{th}")
    assert "사람의 개입" in th, f"개입 고지가 사라졌다\n{th}"
    assert "모의투자" in th and "example.com" in th


def test_the_short_thread_still_drops_the_highlights():
    """무엇을 줄이는지도 고정한다 — 고지 대신 하이라이트를 줄여야 한다."""
    src = (ROOT / "quant" / "reporting" / "social.py").read_text("utf-8")
    short = src.split("if len(th) > THREADS_TEXT_LIMIT:", 1)[1].split(
        "return {", 1)[0]
    # 주석은 뺀다 — 왜 이렇게 했는지의 기록이지 실행되는 코드가 아니다
    # (여기 '배분 상위'가 설명으로 등장해 검사가 헛돌았다).
    short = re.sub(r"#.*", "", short)
    assert "{kill}" in short and "{owner}" in short, (
        "짧은 판에 고지가 들어 있지 않다")
    assert "배분 상위" not in short, (
        "짧은 판이 하이라이트를 그대로 두고 있다 — 줄일 것은 이쪽이다")
