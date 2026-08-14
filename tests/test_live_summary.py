"""일일 요약 알림 테스트 — 순수 stdlib(합성 dict만 사용, pandas 불필요)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "live_summary",
    str(Path(__file__).resolve().parent.parent / "quant" / "live" / "summary.py"))
summ = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(summ)


def _state(day: str = "2026-07-04") -> dict:
    return {
        "symbol": "BTC/USDT",
        "strategy": "sma_cross",
        "mode": "paper",
        "history": [
            {"time": "2026-07-03 23:00:00", "equity": 9_999.0},  # 어제 것(오늘 카운트 제외)
            {"time": f"{day} 01:00:00", "equity": 10_000.0,
             "hit_rate": 0.51, "n": 100,
             "recent_hit_rate": 0.53, "recent_n": 100},
            {"time": f"{day} 02:00:00", "equity": 10_123.45,
             "hit_rate": 0.52, "n": 100,
             "recent_hit_rate": 0.54, "recent_n": 100},
        ],
        "position": {"symbol": "BTC/USDT", "quantity": 0.1, "avg_price": 60_000.0},
        "last_error": None,
    }


def test_build_summary_contains_key_facts():
    text = summ.build_daily_summary(_state(), today="2026-07-04")
    assert "일일 요약" in text and "2026-07-04" in text
    assert "사이클 2회" in text                    # 오늘(07-04) 기록만 카운트
    # 마지막 기록의 recent_hit_rate. ⚠️ 비율만 나가지 않는다 — 구간이 50%를
    # 품으면 "판정 불가"가 붙는다(2026-08-14). n=100짜리 54%가 바로 그렇다.
    assert "54% (판정 불가 44~63% · n=100)" in text, text
    assert "BTC/USDT 0.100000" in text              # 포지션
    assert "마지막 에러 없음" in text
    # 수익 보장류 문구가 없어야 한다(법적 금지)
    assert "보장" not in text


def test_build_summary_robust_to_missing_keys():
    # 빈 dict / None / 이상한 history 항목이 있어도 예외 없이 문자열이 나온다.
    for state in ({}, None, {"history": "이상함"}, {"history": [None, 3, {}]},
                  {"position": "이상함"}, {"positions": [None, {"quantity": "x"}]}):
        text = summ.build_daily_summary(state, today="2026-07-04")
        assert isinstance(text, str) and "일일 요약" in text
        assert "N/A" in text                        # 적중률·자산은 N/A로 대체


def test_build_summary_reports_last_error_and_multi_positions():
    state = {
        "history": [{"time": "2026-07-04 01:00:00", "equity": 5_000.0}],
        "positions": [
            {"symbol": "BTC/USDT", "quantity": 0.2},
            {"symbol": "ETH/USDT", "quantity": 0.0},   # 0 수량은 표시 제외
        ],
        "last_error": "타임아웃",
    }
    text = summ.build_daily_summary(state, today="2026-07-04")
    assert "마지막 에러 타임아웃" in text
    assert "BTC/USDT 0.200000" in text and "ETH/USDT" not in text


def test_maybe_daily_summary_rollover_logic():
    # 최초(None): 날짜만 기록, 전송 없음 — 재시작마다 중복 전송 방지
    d, text = summ.maybe_daily_summary(_state(), None, today="2026-07-04")
    assert d == "2026-07-04" and text is None
    # 같은 날: 전송 없음
    d, text = summ.maybe_daily_summary(_state(), "2026-07-04", today="2026-07-04")
    assert text is None
    # 날짜 롤오버: 전송
    d, text = summ.maybe_daily_summary(_state("2026-07-05"), "2026-07-04",
                                       today="2026-07-05")
    assert d == "2026-07-05" and text and "일일 요약" in text


def test_load_last_summary_date_missing_and_corrupt(tmp_path):
    assert summ.load_last_summary_date(None) is None
    assert summ.load_last_summary_date(str(tmp_path / "없는파일.json")) is None
    bad = tmp_path / "corrupt.json"
    bad.write_text('{"last_summary_date": "2026-07-0', encoding="utf-8")  # 잘림
    assert summ.load_last_summary_date(str(bad)) is None                  # 폴백
    ok = tmp_path / "state.json"
    ok.write_text(json.dumps({"last_summary_date": "2026-07-03"}), encoding="utf-8")
    assert summ.load_last_summary_date(str(ok)) == "2026-07-03"


class _FakeTrader:
    """notify_daily_summary가 기대하는 최소 인터페이스(합성)."""

    def __init__(self, notifier, state_path=None):
        self.notifier = notifier
        self.state_path = state_path
        self._last_summary_date = None
        self.persisted = 0

    def snapshot(self):
        return _state()

    def _persist(self):
        self.persisted += 1


class _Recorder:
    def __init__(self):
        self.sent = []

    def send(self, msg, level="info"):
        self.sent.append(msg)


def test_notify_daily_summary_no_notifier_is_noop():
    t = _FakeTrader(notifier=None)
    summ.notify_daily_summary(t)                    # 예외 없이 아무 일도 없음
    assert t._last_summary_date is None and t.persisted == 0


def test_notify_daily_summary_sends_once_per_rollover():
    n = _Recorder()
    t = _FakeTrader(notifier=n, state_path="state.json")
    summ.notify_daily_summary(t)                    # 최초: 날짜만 기록
    assert not n.sent and t._last_summary_date
    t._last_summary_date = "2000-01-01"             # 롤오버 시뮬레이션
    summ.notify_daily_summary(t)
    assert len(n.sent) == 1 and "일일 요약" in n.sent[0]
    assert t.persisted == 1                          # 전송 후 즉시 저장
    summ.notify_daily_summary(t)                    # 같은 날 재호출: 중복 없음
    assert len(n.sent) == 1


def test_notify_daily_summary_swallows_errors():
    class _Boom:
        def send(self, msg, level="info"):
            raise RuntimeError("알림 채널 다운")

    t = _FakeTrader(notifier=_Boom(), state_path="state.json")
    t._last_summary_date = "2000-01-01"
    summ.notify_daily_summary(t)                    # 예외가 밖으로 새지 않는다
