"""브리핑 피드가 죽어도 조용하다 (2026-08-14 감사 237).

`collect_briefing`은 피드 하나가 실패하면 로그에 한 줄 찍고 `continue` 했다.
장부(`state/briefing.json`)에는 `date`·`items`·`note`만 남았고 **어떤 소스가
죽었는지는 아무 데도 없었다.** 그래서 이런 일이 조용히 지나간다:

  · 일반 피드 3개가 전부 죽고 종목 뉴스만 살아도 40건이 모여 화면은
    멀쩡해 보인다
  · 반대로 구글 뉴스가 종목 검색만 막으면(같은 호스트에 요청이 20번 더
    간다) **종목 뉴스가 통째로 사라지는데** 화면은 일반 뉴스를 그대로
    보여주고 끝난다

이 저장소가 이미 두 번 세운 규칙을 이 파일에서만 안 지키고 있었다 —
"건너뜀은 통과가 아니다"(감사 226), "판단 근거를 장부에 남긴다"(감사 235).

⚠️ 브리핑은 **표시 전용**이라 매매 판단에는 쓰이지 않는다. 그래도 화면에
   나가는 것이고, 이 제품의 계약은 "보이는 것이 사실이어야 한다"이다.
   조용히 반쪽만 보여주는 것은 그 계약 위반이다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import briefing as br  # noqa: E402

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>테스트 기사 {n}</title><link>https://example.test/{n}</link>
<pubDate>Thu, 14 Aug 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""


# 일반 피드와 종목 뉴스는 **URL 모양이 같다**(둘 다 구글 뉴스 검색). 그래서
# 호출 순서로 가른다 — 앞의 len(FEEDS)건이 일반 피드, 그 뒤가 종목 뉴스다.
ALL, FEEDS_ONLY, SYMBOLS_ONLY = "all", "feeds", "symbols"


def _run(monkeypatch, tmp_path, which=None):
    """which: None(전부 성공) · ALL · FEEDS_ONLY · SYMBOLS_ONLY 를 실패시킨다."""
    calls = {"n": 0}
    n_feeds = len(br.FEEDS)

    def fake_get_text(url, headers=None, timeout=15):
        calls["n"] += 1
        is_feed = calls["n"] <= n_feeds
        if which == ALL or (which == FEEDS_ONLY and is_feed) \
                or (which == SYMBOLS_ONLY and not is_feed):
            raise OSError("연결 거부(모의)")
        return RSS.format(n=calls["n"])

    monkeypatch.setattr("quant.utils.http.get_text", fake_get_text)
    out = br.collect_briefing(state_dir=str(tmp_path), date="2026-08-14")
    saved = json.loads((tmp_path / br.BRIEFING_FILE).read_text("utf-8"))
    return out, saved


# ── 전부 살아 있을 때 (대조군) ────────────────────────────────

def test_a_healthy_run_records_every_source(monkeypatch, tmp_path):
    """대조군이 없으면 '항상 실패라고 적는' 코드도 통과한다."""
    _, saved = _run(monkeypatch, tmp_path)
    h = saved["sources"]
    assert len(h["feeds_ok"]) == len(br.FEEDS)
    assert h["feeds_failed"] == {}
    assert len(h["symbols_ok"]) == len(br.SYMBOL_QUERIES)
    assert h["symbols_failed"] == {}


# ── 일부만 죽었을 때 ──────────────────────────────────────────

def test_a_dead_general_feed_is_named(monkeypatch, tmp_path):
    """일반 피드가 죽었는데 종목 뉴스가 살아 있으면 화면은 멀쩡해 보인다."""
    _, saved = _run(monkeypatch, tmp_path, FEEDS_ONLY)
    h = saved["sources"]
    assert h["feeds_ok"] == []
    assert set(h["feeds_failed"]) == {c for c, _ in br.FEEDS}
    assert h["symbols_ok"], "종목 뉴스는 살아 있어야 대조가 된다"
    assert saved["items"], "기사는 모였다 — 그래서 조용히 지나갔던 것이다"


def test_the_symbol_news_vanishing_is_recorded(monkeypatch, tmp_path):
    """종목 뉴스만 통째로 사라지는 경우 — 가장 눈에 안 띄는 고장이다."""
    _, saved = _run(monkeypatch, tmp_path, SYMBOLS_ONLY)
    h = saved["sources"]
    assert h["symbols_ok"] == []
    assert len(h["symbols_failed"]) == len(br.SYMBOL_QUERIES)
    assert h["feeds_ok"], "일반 피드는 살아 있어야 대조가 된다"


def test_the_reason_is_recorded_not_just_the_fact(monkeypatch, tmp_path):
    """'데이터 장애'인지 '차단'인지 구분 못 하면 대응도 못 한다."""
    _, saved = _run(monkeypatch, tmp_path, ALL)
    reasons = list(saved["sources"]["feeds_failed"].values())
    assert reasons and all("OSError" in r for r in reasons)


def test_everything_dead_is_still_a_saved_record(monkeypatch, tmp_path):
    """전멸해도 기록은 남는다 — 조용히 사라지는 것이 가장 나쁘다."""
    out, saved = _run(monkeypatch, tmp_path, ALL)
    assert out["items"] == []
    assert saved["sources"]["feeds_ok"] == []
    assert saved["sources"]["symbols_ok"] == []
    assert len(saved["sources"]["feeds_failed"]) == len(br.FEEDS)


# ── 사람이 읽는 출력 ──────────────────────────────────────────

def test_the_console_line_counts_both_kinds(monkeypatch, tmp_path, capsys):
    """배치 로그만 보고도 반쪽인지 알 수 있어야 한다."""
    _run(monkeypatch, tmp_path, SYMBOLS_ONLY)
    out = capsys.readouterr().out
    assert f"피드 {len(br.FEEDS)}/{len(br.FEEDS)}" in out
    assert f"종목 0/{len(br.SYMBOL_QUERIES)}" in out
    assert "뉴스를 못 받은 종목" in out


def test_a_clean_run_does_not_cry_wolf(monkeypatch, tmp_path, capsys):
    """대조군 — 멀쩡한 날에 경고가 뜨면 경고가 무뎌진다."""
    _run(monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert "⚠️" not in out


def test_the_old_fields_are_untouched(monkeypatch, tmp_path):
    """화면이 읽는 기존 필드를 건드리지 않았는가(하위 호환)."""
    _, saved = _run(monkeypatch, tmp_path)
    assert saved["date"] == "2026-08-14"
    assert saved["note"] == br.NOTE
    assert isinstance(saved["items"], list)


def test_load_briefing_still_reads_it(monkeypatch, tmp_path):
    _run(monkeypatch, tmp_path)
    got = br.load_briefing(state_dir=str(tmp_path))
    assert got is not None and "sources" in got
