"""방송도 영어로 나가는가 (2026-08-26 감사 325).

사장님 지시: *"서비스 영어로도 만들어줘 홈페이지나 프로그램이나."* 사이트가
영어로 열리는데 방송만 한국어면, 영어로 들어온 사람이 이 계정을 팔로우할
이유가 없다.

■ 이 검사가 지키는 것

  ① **숫자가 같은가** — 이게 가장 중요하다. 두 글은 같은 날의 같은 장부를
     말한다. 금액·수익률이 한 자라도 다르면 그건 번역이 아니라 **두 개의
     서로 다른 방송**이고, 어느 쪽이 진짜인지 아무도 모른다.
  ② **같은 관문을 지나는가** — 계좌로 설명되지 않는 숫자는 한국어에서
     멈추고 영어에서 새어 나가면 안 된다(감사 288의 문이 하나 더 생긴 셈).
  ③ **고지가 살아남는가** — 모의투자·수익 보장 없음·킬스위치·사람의 개입.
     길이 제한에 걸려도 고지는 남는다(감사 97).
  ④ **같은 종목을 말하는가** — 상위 종목을 언어마다 따로 고르면 같은 날
     두 글이 다른 종목을 방송한다(FROZEN_IDEAS ①).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from quant.reporting.social import (
    ImpossibleNumbers,
    THREADS_TEXT_LIMIT,
    build_captions,
    build_captions_en,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def status():
    with open(ROOT / "docs" / "status.json", encoding="utf-8") as f:
        return json.load(f)


def _ledger_figures(x: dict) -> list:
    """**장부에서 나온 값**만 뽑아 글자 모양 그대로 만든다.

    ⚠️ 두 글의 숫자를 통째로 비교하면 안 된다. 이름과 산문에는 언어마다
       다른 숫자가 정당하게 들어간다 — "100만 챌린지" vs "1M Won Challenge",
       "목표는 1억이 아니라" vs "not 100 million". 그건 장부가 아니다.
       지켜야 하는 것은 **돈과 성적**이 두 글에서 같은 글자로 나가는 것이다.
    """
    out = [x["date"], f"D+{x['day_no']}"]
    if x["equity"] is not None:
        out.append(f"{x['equity']:,.0f}")
    for key in ("return_pct", "day_pct", "twr_pct"):
        if x.get(key) is not None:
            out.append(f"{x[key]:+.2f}%")
    vh = x.get("vs_hold")
    if vh:
        out += [f"{vh['hold']:,.0f}", f"{abs(vh['diff']):,.0f}",
                f"{vh['diff_pct']:+.2f}%"]
    if x.get("invested") is not None:
        out.append(f"{x['invested'] * 100:.0f}%")
    if x.get("gross") is not None:
        out.append(f"{x['gross'] * 100:.0f}%")
    if isinstance(x.get("n_held"), int):
        out.append(str(x["n_held"]))
    return out


def test_the_english_caption_is_written_at_all(status):
    en = build_captions_en(status)
    assert en["instagram"].strip(), "영어 인스타 캡션이 비었다"
    assert en["threads"].strip(), "영어 스레드 캡션이 비었다"
    assert en["date"] == build_captions(status)["date"], (
        "두 글이 서로 다른 날을 말한다")


def test_the_money_is_identical_in_both_languages(status):
    """**가장 중요한 검사** — 숫자가 다르면 그건 두 개의 방송이다."""
    from quant.reporting.social import _today_numbers
    want = _ledger_figures(_today_numbers(status))
    assert len(want) >= 6, f"비교할 장부 값이 너무 적다 — 검사가 헛돈다: {want}"
    ko = build_captions(status)["instagram"]
    en = build_captions_en(status)["instagram"]
    for token in want:
        assert token in ko, f"한국어 캡션에 장부 값 {token!r}이 없다"
        assert token in en, (
            f"영어 캡션에 장부 값 {token!r}이 없다 — 두 글이 같은 장부를 "
            "말하고 있지 않다")


def test_the_short_version_agrees_too(status):
    """짧은 판에도 **자산·누적·하루치**는 같은 글자로 남아야 한다."""
    from quant.reporting.social import _today_numbers
    x = _today_numbers(status)
    ko = build_captions(status)["threads"]
    en = build_captions_en(status)["threads"]
    want = [x["date"], f"{x['equity']:,.0f}", f"{x['return_pct']:+.2f}%"]
    for token in want:
        assert token in ko and token in en, (
            f"짧은 판에서 {token!r}이 어긋난다.\n  ko: {ko}\n  en: {en}")


def test_the_comparison_would_actually_catch_a_drift(status):
    """대조군 — 비교가 아무것도 안 잡으면 위 검사는 장식이다."""
    from quant.reporting.social import _today_numbers
    x = _today_numbers(status)
    want = _ledger_figures(x)
    assert f"{x['equity']:,.0f}" in want, "자산이 비교 대상에 없다"
    assert f"{x['equity'] + 1:,.0f}" not in build_captions_en(status)[
        "instagram"], "한 자 다른 금액이 캡션에 있다(비교가 무의미하다)"


def test_the_english_is_not_a_translation_of_the_korean(status):
    """영어에 한국어가 남아 있으면 옮기다 만 것이다.

    종목은 코드 그대로(ETH/USDT · AAPL) 적는다 — 한국어 이름을 영어로
    지어내면 그건 번역이 아니라 창작이다.
    """
    en = build_captions_en(status)
    for key in ("instagram", "threads"):
        left = re.findall(r"[가-힣]+", en[key])
        assert not left, f"영어 {key} 캡션에 한국어가 남았다: {sorted(set(left))}"


def test_both_languages_pick_the_same_symbols(status):
    """상위 종목을 언어마다 따로 고르면 같은 날 다른 종목을 방송한다."""
    from quant.reporting.social import _today_numbers, _top_names_en
    x = _today_numbers(status)
    ko, en = x["top_names"], _top_names_en(x)
    assert len(ko) == len(en), f"고른 종목 수가 다르다: {ko} vs {en}"
    # 숏·대기 표시도 같은 자리에 있어야 한다.
    assert [("(숏)" in n) for n in ko] == [("(short)" in n) for n in en], (
        f"숏 표시가 어긋난다: {ko} vs {en}")
    assert [("(대기)" in n) for n in ko] == [("(queued)" in n) for n in en], (
        f"대기 표시가 어긋난다: {ko} vs {en}")


def test_the_english_carries_the_honest_notice(status):
    """모의투자·수익 보장 없음·적중률 상한 — 번역해도 남아야 한다."""
    ig = build_captions_en(status)["instagram"]
    for must in ["paper trading", "No return is guaranteed",
                 "52–55%", "not post only the good days"]:
        assert must in ig, f"영어 캡션에서 '{must}'가 사라졌다"


def test_the_short_english_keeps_the_notice_even_when_squeezed(status):
    """길이 제한에 걸려도 **고지는 지킨다**(감사 97과 같은 규칙)."""
    th = build_captions_en(status)["threads"]
    assert len(th) <= THREADS_TEXT_LIMIT, (
        f"영어 스레드 캡션이 {len(th)}자로 한도({THREADS_TEXT_LIMIT})를 넘는다")
    assert "no return guaranteed" in th.lower(), "짧은 판에 고지가 없다"


def _a_wordy_day(status: dict) -> dict:
    """**쓸 말이 많은 날**을 만든다 — 500자를 넘겨 짧은 판이 줄어드는 날.

    ⚠️ 환경에 기대면 안 된다. 오늘 장부는 짧아서 줄이는 가지가 아예 안
       돌고, 그러면 "길이가 넘쳐도 고지는 지킨다"는 검사가 헛돈다 —
       감사 97이 잡은 결함이 정확히 그 가지에 있었다.
    """
    st = copy.deepcopy(status)
    last = st["paper"]["portfolio:ALL"]["history"][-1]
    last["applied"] = {f"us_stock:LONGNAME{i}XXXXXXXXXXXX": 0.2 - 0.01 * i
                       for i in range(3)}
    last["risk_scale"] = 0.5
    last["paused"] = True
    last["exposure_scale"] = 0.7
    return st


def test_the_kill_switch_survives_the_short_version(status):
    """킬스위치는 하이라이트가 아니라 **고지**다 — 잘리면 안 된다."""
    st = _a_wordy_day(status)
    long = build_captions_en(st)          # 줄이기 전 길이를 먼저 확인한다
    th = long["threads"]
    assert len(th) <= THREADS_TEXT_LIMIT
    assert "Top allocations" not in th, (
        "짧은 판이 줄어들지 않았다 — 이 검사가 줄이는 가지를 안 보고 있다")
    assert "Kill switch" in th, f"짧은 판에서 킬스위치 고지가 잘렸다:\n{th}"


def test_a_human_touch_survives_the_short_version(status):
    """사람이 손댄 날은 영어 방송도 그 사실을 말해야 한다."""
    th = build_captions_en(_a_wordy_day(status))["threads"]
    assert "human intervened" in th, f"사람의 개입이 잘렸다:\n{th}"
    assert "exposure multiplier" in th, f"노출 배수가 잘렸다:\n{th}"


def test_a_short_is_called_a_short_in_english(status):
    """팔아 둔 종목을 그냥 이름만 적으면 **산 것처럼 읽힌다**(감사 264).

    ⚠️ 오늘 장부에 숏이 없을 수도 있다 — 없으면 이 검사는 아무것도 안
       지킨다. 그래서 조건을 **만들어서** 본다.
    """
    from quant.reporting.social import _today_numbers, _top_names_en
    st = copy.deepcopy(status)
    st["paper"]["portfolio:ALL"]["history"][-1]["applied"] = {
        "crypto:BTC/USDT": -0.2, "us_stock:AAPL": 0.1}
    x = _today_numbers(st)
    ko, en = x["top_names"], _top_names_en(x)
    assert any("(숏)" in n for n in ko), f"한국어에 숏 표시가 없다: {ko}"
    assert any("(short)" in n for n in en), (
        f"영어 캡션이 숏을 숏이라 적지 않는다: {en}")
    assert [("(숏)" in n) for n in ko] == [("(short)" in n) for n in en], (
        f"숏 표시가 다른 종목에 붙었다: {ko} vs {en}")


def test_the_english_stops_on_an_impossible_day(status):
    """계좌로 설명되지 않는 숫자는 **영어에서도** 멈춘다.

    한국어에만 문이 있으면, 같은 사고가 영어로 세상에 나간다 — 감사 288이
    "사이트는 고쳤는데 캡션만 남아 있었다"고 적은 그 모양 그대로다.
    """
    st = copy.deepcopy(status)
    st["paper"]["portfolio:ALL"]["history"][-1]["day_pct"] = 7149.96
    with pytest.raises(ImpossibleNumbers):
        build_captions_en(st)
    with pytest.raises(ImpossibleNumbers):
        build_captions(st)          # 대조군 — 두 문이 같이 닫혀야 한다


def test_a_normal_day_is_not_blocked(status):
    """대조군 — 평범한 날까지 막으면 위 관문은 방송을 통째로 끈다."""
    assert build_captions_en(status)["instagram"]


def test_the_english_points_at_the_english_site(status):
    """영어로 읽은 사람이 링크를 눌렀는데 한국어가 나오면 거기서 끝이다."""
    for key in ("instagram", "threads"):
        assert "lang=en" in build_captions_en(status)[key], (
            f"영어 {key} 캡션의 링크가 한국어 화면으로 간다")


def test_the_file_is_written_next_to_the_korean_one(tmp_path, status):
    """어드민이 복사해 올릴 파일이 실제로 만들어지는가."""
    from quant.reporting import social
    docs = tmp_path / "docs"
    (docs / "social").mkdir(parents=True)
    with open(docs / "status.json", "w", encoding="utf-8") as f:
        json.dump(status, f)
    meta = social.write_content(str(docs))
    out = Path(meta["dir"])
    for name in ("caption_instagram.txt", "caption_threads.txt",
                 "caption_instagram_en.txt", "caption_threads_en.txt"):
        assert (out / name).exists(), f"{name}이 안 만들어졌다"
    latest = json.loads((docs / "social" / "latest.json").read_text("utf-8"))
    assert latest["captions"]["instagram_en"], "포인터에 영어판이 없다"


def test_an_old_folder_without_english_still_works(tmp_path, status):
    """대조군 — 영어판이 없던 옛 폴더에서 포인터가 죽으면 안 된다.

    없는 것을 지어내지도, 그것 때문에 멈추지도 않는다.
    """
    from quant.reporting import social
    docs = tmp_path / "docs"
    (docs / "social").mkdir(parents=True)
    with open(docs / "status.json", "w", encoding="utf-8") as f:
        json.dump(status, f)
    meta = social.write_content(str(docs))
    out = Path(meta["dir"])
    for name in ("caption_instagram_en.txt", "caption_threads_en.txt"):
        (out / name).unlink()
    latest = social.refresh_latest(str(docs))
    assert latest["captions"]["instagram"], "한국어판까지 사라졌다"
    assert "instagram_en" not in latest["captions"], (
        "없는 영어판을 있다고 적었다")


def test_the_admin_screen_offers_the_english_caption():
    """만들어 두고 아무도 못 쓰면 없는 것과 같다 (감사 289 계열).

    사람이 실제로 복사해 올리는 자리는 대시보드다. 파일만 생기고 화면에
    안 뜨면 그 영어 캡션은 태어나서 한 번도 쓰이지 않는다.
    """
    admin = (ROOT / "docs" / "admin.html").read_text("utf-8")
    assert "d.captions.instagram_en" in admin, (
        "대시보드가 영어 인스타 캡션을 읽지 않는다")
    assert "d.captions.threads_en" in admin, (
        "대시보드가 영어 스레드 캡션을 읽지 않는다")
    # 없는 날에는 빈 칸을 내밀지 않는다 — 빈 글이 그대로 올라간다.
    assert "if(d.captions.instagram_en)" in admin, (
        "영어판이 없는 옛 날짜에도 빈 칸을 보여준다")
