"""매매를 안 바꾸는 카드라도 공개 기록이다 (감사 181).

훑은 파일 — `live/macro_brief.py` · `live/briefing.py` · `__main__.py`.

**결함 하나를 찾았다 — 거시 카드가 미래 날짜를 공개 기록에 남겼다.**

`fred_series`는 기본적으로 발표 시차만큼 인덱스를 **앞으로 민다**. 판단(ML
피처)에서 "그 시점에 실제로 알 수 있던 값"만 쓰게 하려는 룩어헤드 방지책이고,
거기서는 옳다. 그런데 `macro_summary`는 그 **시프트된 인덱스의 마지막 날짜**를
그대로 "이 값의 날짜"로 `status.json`에 실었다.

    PUBLICATION_LAG_DAYS = {"T10Y2Y": 1, "BAMLH0A0HYM2": 1,
                            "DTWEXBGS": 1, "T10YIE": 1}   ← 넷 다 1일

즉 **관측일 + 1일**이 찍힌다. FRED가 당일치를 내놓는 날이면 사이트가
**내일 날짜**를 남긴다. 실측(FRED 최신 관측일 2026-08-12):

    예전:  date = "2026-08-13"    ← 미래
    지금:  date = "2026-08-12"

돈이 걸린 결함은 아니다 — 이 카드는 매매를 바꾸지 않고, 지금 화면은 날짜를
그리지도 않는다. 그래도 `status.json`은 이 실험의 **공개 감사 기록**이고,
거기 미래 날짜가 박혀 있으면 "언제 것인지"를 검증하려는 사람이 처음부터
어긋난 자료를 본다.

값(`value`·`chg5_pct`)은 시프트와 무관하게 동일하다 — 바뀌는 것은 날짜
라벨뿐이고, 판단 경로(`fred_frame`·ML 피처)는 그대로 시차 보정을 쓴다.

나머지 둘은 결함 못 찾음. 확인한 것을 적어 둔다.

  · 뉴스 브리핑: 피드 하나가 죽어도 나머지가 살고, 망가진 XML은 빈 목록,
    카테고리 간 중복 제거, 길이 상한.
  · `python -m quant`: 진입점이 실제로 CLI를 부른다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.macro as M  # noqa: E402
from quant.live.briefing import (  # noqa: E402
    NOTE,
    collect_briefing,
    load_briefing,
    parse_rss,
)
from quant.live.macro_brief import _interpret, macro_summary  # noqa: E402

LATEST = pd.Timestamp("2026-08-12")


@pytest.fixture()
def fred(monkeypatch):
    """FRED가 '오늘치'를 내놓는 날을 흉내낸다 — 시차를 밀면 내일이 된다."""
    monkeypatch.setenv("FRED_API_KEY", "dummy")

    def _payload(url, headers=None, timeout=30):
        return {"observations": [
            {"date": str((LATEST - pd.Timedelta(days=i)).date()),
             "value": f"{1.5 + i * 0.01:.4f}"}
            for i in range(20)][::-1]}

    monkeypatch.setattr(M, "get_json", _payload)
    return _payload


# ── 거시 카드: 날짜가 관측일인가 ──────────────────────────────


def test_the_macro_card_never_stamps_a_date_the_data_does_not_have(fred):
    """발표 시차는 판단용 보정이지 '이 값의 날짜'가 아니다."""
    got = macro_summary()
    assert got is not None
    want = str(LATEST.date())
    for item in got["items"]:
        assert item["date"] == want, (
            f"{item['key']}: 관측일 {want}인데 {item['date']}로 찍혔다 — "
            "발표 시차만큼 밀린 날짜를 그대로 실었다")


def test_no_macro_date_is_in_the_future(fred):
    got = macro_summary()
    for item in got["items"]:
        assert pd.Timestamp(item["date"]) <= LATEST, (
            f"공개 기록에 미래 날짜가 들어갔다: {item}")


def test_the_values_are_unchanged_by_the_date_fix(fred):
    """대조군 — 날짜만 고쳐야 한다. 값이 흔들리면 카드가 딴것이 된다."""
    got = macro_summary()
    by_key = {i["key"]: i for i in got["items"]}
    assert by_key["t10y2y"]["value"] == pytest.approx(1.5)
    # 5일 전 값은 1.55 → (1.5/1.55 - 1)*100 = -3.23%
    assert by_key["usd_idx"]["chg5_pct"] == pytest.approx(-3.23)
    assert set(by_key) == {"t10y2y", "hy_spread", "usd_idx", "t10yie"}


def test_the_judgement_path_still_shifts_for_publication_lag(fred):
    """대조군 — 표시용을 고치느라 판단용 룩어헤드 방지를 풀면 큰일이다."""
    shifted = M.fred_series("T10Y2Y")
    raw = M.fred_series("T10Y2Y", lag_days=0)
    assert shifted.index[-1] == raw.index[-1] + pd.Timedelta(days=1), (
        "판단 경로의 발표 시차 보정이 사라졌다 — 룩어헤드가 열린다")


def test_no_key_means_no_card(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert macro_summary() is None


def test_a_broken_feed_is_a_missing_card_not_a_crash(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "dummy")
    monkeypatch.setattr(M, "get_json", lambda *a, **k: {"observations": []})
    assert macro_summary() is None, "빈 응답인데 빈 카드를 만들면 안 된다"

    def _boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(M, "get_json", _boom)
    assert macro_summary() is None


@pytest.mark.parametrize("vals,want", [
    ({"t10y2y": {"value": -0.3}}, "역전"),
    ({"t10y2y": {"value": 0.3}}, "정상"),
    ({"hy_spread": {"value": 6.0}}, "경색"),
    ({"hy_spread": {"value": 3.0}}, "안정"),
    ({"hy_spread": {"value": 4.0}}, "보통"),
    ({"usd_idx": {"chg5_pct": 1.0}}, "달러 강세"),
    ({"usd_idx": {"chg5_pct": -1.0}}, "달러 약세"),
    ({"usd_idx": {"chg5_pct": 0.0}}, "달러 보합"),
])
def test_the_interpretation_matches_the_number(vals, want):
    """양쪽 다 확인 — 한쪽만 보면 부호를 뒤집어도 통과한다."""
    assert want in _interpret(vals)


def test_a_missing_series_produces_no_sentence_about_it():
    assert _interpret({}) == ""
    assert "달러" not in _interpret({"t10y2y": {"value": 1.0}})


# ── 뉴스 브리핑: 하나가 죽어도 나머지가 사는가 ────────────────


def _rss(*titles: str) -> str:
    body = "".join(
        f"<item><title>{t}</title><link>https://x/{i}</link>"
        f"<pubDate>Tue, 12 Aug 2026 00:00:00 GMT</pubDate></item>"
        for i, t in enumerate(titles))
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>"


def test_the_publisher_is_split_off_the_headline():
    got = parse_rss(_rss("금리 동결 - 한국경제"), "증시")
    assert got[0]["title"] == "금리 동결"
    assert got[0]["source"] == "한국경제"
    assert got[0]["cat"] == "증시"


def test_broken_xml_is_an_empty_list_not_an_exception():
    assert parse_rss("<rss><unclosed>", "증시") == []
    assert parse_rss("", "증시") == []


def test_only_the_top_n_are_kept():
    got = parse_rss(_rss("a", "b", "c", "d", "e", "f"), "증시", top_n=3)
    assert [g["title"] for g in got] == ["a", "b", "c"]


def test_an_empty_headline_is_skipped_without_losing_the_rest():
    got = parse_rss(_rss("", "살아있는 기사"), "증시")
    assert [g["title"] for g in got] == ["살아있는 기사"]


def test_long_fields_are_clipped():
    got = parse_rss(_rss("가" * 500), "증시")
    assert len(got[0]["title"]) == 120


def test_one_dead_feed_does_not_take_the_whole_briefing_down(tmp_path,
                                                             monkeypatch):
    import quant.utils.http as H

    calls = {"n": 0}

    def _get_text(url, headers=None, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("첫 피드 죽음")
        return _rss(f"기사{calls['n']}")

    monkeypatch.setattr(H, "get_text", _get_text)
    got = collect_briefing(str(tmp_path))
    assert got["items"], "피드 하나가 죽었다고 브리핑 전체가 비었다"
    assert got["note"] == NOTE
    assert load_briefing(str(tmp_path))["items"] == got["items"]


def test_every_feed_dead_is_an_empty_briefing_not_a_crash(tmp_path,
                                                          monkeypatch):
    import quant.utils.http as H

    def _boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(H, "get_text", _boom)
    got = collect_briefing(str(tmp_path), date="2026-08-12")
    assert got["date"] == "2026-08-12"
    assert got["items"] == []
    assert got["note"] == NOTE
    # ⚠️ 2026-08-14 감사 237부터 **어떤 소스가 죽었는지도 함께 남긴다.**
    #    예전 이 검사는 dict 전체를 통짜로 비교해서, 기록을 늘리는 것과
    #    동작이 바뀌는 것을 구분하지 못했다. 지키려는 계약은 "전멸해도
    #    예외를 던지지 않고 빈 브리핑을 남긴다"이므로 그것만 본다.
    assert got["sources"]["feeds_ok"] == []
    assert got["sources"]["feeds_failed"], "죽은 피드가 기록되지 않았다"


def test_the_same_headline_is_not_listed_twice(tmp_path, monkeypatch):
    import quant.utils.http as H

    monkeypatch.setattr(H, "get_text",
                        lambda *a, **k: _rss("같은 기사 - 언론사"))
    got = collect_briefing(str(tmp_path))
    titles = [i["title"] for i in got["items"]]
    assert titles == ["같은 기사"], titles
    assert got["items"][0].get("sym"), (
        "종목 검색에서도 나온 기사면 종목 표식이 붙어야 한다")


def test_a_missing_briefing_file_is_none_not_a_crash(tmp_path):
    assert load_briefing(str(tmp_path)) is None
    (tmp_path / "briefing.json").write_text("{not json", encoding="utf-8")
    assert load_briefing(str(tmp_path)) is None


# ── 진입점: python -m quant 가 실제로 도는가 ──────────────────


def test_the_module_entry_point_actually_runs_the_cli():
    """`python -m quant`가 도는지는 소스만 봐선 모른다 — 실제로 돌려 본다."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    got = subprocess.run([sys.executable, "-m", "quant", "--help"],
                         capture_output=True, text=True, cwd=str(ROOT),
                         env=env, timeout=120)
    assert got.returncode == 0, got.stderr[-2000:]
    assert "backtest" in got.stdout, got.stdout[:2000]
