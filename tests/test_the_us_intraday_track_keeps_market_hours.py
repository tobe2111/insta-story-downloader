"""미국주식 장중 트랙 — 장이 닫히면 펜도 놓는다 (2026-08-19, 사장님 지시).

지켜야 할 약속:
- 미국 정규장 밖에서는 판단도 체결도 **기록도** 없다 — 닫힌 장의 가격으로
  '체결했다'고 적는 것은 실험이 아니라 소설이다.
- 같은 봉 멱등 — 새 정보가 없으면 회차를 쓰지 않는다(밤새 소음 금지).
- 통화는 USD 하나다. 원화 환산 코드가 이 모듈에 등장하는 순간
  감사 254(통화 혼합 사고)의 재발 지점이 생긴다.
- 체결·평가·킬스위치는 코인 트랙의 **같은 함수**를 빌려 쓴다 — 복사하면
  언젠가 두 트랙의 규칙이 갈라져 '미국장 대 코인장' 비교가 오염된다.
- 실데이터가 아니면(합성 폴백) 그 종목은 쉰다.
- 판정 기준은 첫 회차 전에 사전 등록됐다(prereg와 날짜가 일치).
- 배선: 5분 러너(cli)가 try로 감싸 부르고, guard.yml이 공개 JSON을 커밋한다.
- 화면(intraday.html)이 intraday_us.json에서만 읽는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.intraday_us as IU                      # noqa: E402

SRC = (ROOT / "quant" / "live" / "intraday_us.py").read_text("utf-8")

OPEN_NOW = "2026-08-19T15:00:00+00:00"    # 수요일 11:00 뉴욕 — 정규장
CLOSED_SAT = "2026-08-22T15:00:00+00:00"  # 토요일 — 휴장
CLOSED_NIGHT = "2026-08-19T02:00:00+00:00"  # 뉴욕 화 22:00 — 장 밖


class _AlwaysLong:
    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


def _bars(n=80, freq="1h", start="2026-08-10"):
    idx = pd.date_range(start, periods=n, freq=freq)
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px},
                        index=idx)


def _run(tmp_path, now, data=None):
    return IU.run_us_round(
        now, state_dir=str(tmp_path), docs_dir=str(tmp_path / "docs"),
        data=data if data is not None else {"AAPL": _bars()},
        strategy_factory=lambda sym: _AlwaysLong())


def test_no_round_outside_regular_hours(tmp_path):
    for closed in (CLOSED_SAT, CLOSED_NIGHT):
        v = _run(tmp_path, closed)
        assert v.get("skipped") == "미국장 휴장", v
    assert not (tmp_path / "intraday" / "us_challenger.json").exists(), (
        "장 밖인데 장부가 생겼다 — 닫힌 장의 체결은 소설이다")


def test_a_round_trades_inside_the_session(tmp_path):
    v = _run(tmp_path, OPEN_NOW)
    assert "equity" in v and v["trades"] >= 1, v   # 회차가 실제로 돌았다
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    assert st["currency"] == "USD"
    assert st["positions"].get("AAPL", 0) > 0
    pub = json.loads((tmp_path / "docs" / "intraday_us.json")
                     .read_text("utf-8"))
    assert pub["kind"] == IU.KIND and "가상" in pub["label"]


def test_same_bar_is_idempotent(tmp_path):
    _run(tmp_path, OPEN_NOW)
    v2 = _run(tmp_path, "2026-08-19T15:05:00+00:00")   # 5분 뒤, 새 봉 없음
    assert v2.get("skipped") == "같은 봉 재실행", v2
    st = json.loads(
        (tmp_path / "intraday" / "us_challenger.json").read_text("utf-8"))
    assert len(st["rounds"]) == 1, "같은 봉으로 두 회차를 썼다 — 소음이다"


def test_the_ladder_runs_its_own_ledger(tmp_path):
    data = {"AAPL": _bars(),
            "15m": {"AAPL": _bars(freq="15min", start="2026-08-18")},
            "5m": {}}
    _run(tmp_path, OPEN_NOW, data=data)
    t15 = json.loads(
        (tmp_path / "intraday" / "us_track_15m.json").read_text("utf-8"))
    assert t15["currency"] == "USD" and len(t15["rounds"]) == 1


def test_the_currency_seal_no_krw_in_this_module():
    for banned in ("usdkrw", "to_krw", "fx_usdkrw", "원화 환산을 한다"):
        assert banned not in SRC.replace("원화 환산을 하지 않는다", ""), (
            f"모듈에 '{banned}' — USD 봉인이 깨졌다(감사 254 재발 지점)")


def test_the_rules_are_borrowed_not_copied():
    assert "from quant.live.intraday_challenger import" in SRC
    assert "_execute_targets" in SRC, "체결 규칙을 빌려 쓰지 않는다"
    assert "_kill_switch_scale" in SRC, "킬스위치를 빌려 쓰지 않는다"
    assert "def _execute_targets" not in SRC, (
        "체결 규칙을 복사했다 — 두 트랙의 규칙이 갈라질 길을 만들었다")
    assert 'synthetic_fallback' in SRC and 'attrs.get("source")' in SRC, (
        "합성 시세 방어가 없다 — 가짜 체결의 문이 열렸다")


def test_the_goalposts_match_the_registry():
    from quant.live import prereg
    exp = prereg.PREREGISTERED["intraday_us"]
    assert exp["start"] == "2026-08-19" and exp["judge_on"] == "2026-11-17"
    assert IU.PREREGISTERED_JUDGEMENT["registered_on"] == exp["start"], (
        "트랙 내 사본과 사전 등록 원장의 등록일이 어긋난다")


def test_the_wiring_cannot_kill_the_coin_track():
    cli = (ROOT / "quant" / "cli.py").read_text("utf-8")
    i = cli.find("run_us_round")
    assert i > 0, "5분 러너가 미국 트랙을 부르지 않는다"
    assert "try:" in cli[max(0, i - 300):i], (
        "미국 트랙이 예외 방벽 없이 코인 트랙 뒤에 있다")
    guard = (ROOT / ".github" / "workflows" / "guard.yml").read_text("utf-8")
    assert "docs/intraday_us.json" in guard, "공개 JSON이 커밋되지 않는다"


def test_the_screen_reads_the_ledger_only():
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "intraday_us.json" in page and "us-sum" in page, (
        "미국 트랙 화면이 없다 — 공개되지 않는 실험은 실험이 아니다")
