"""주기 사다리 — 최적 주기를 사람이 고르지 않고 나란히 재서 곡선이 고르게.

2026-08-18 사장님 지시("최대한 이상적으로"). 지켜야 할 약속:
- 15분·5분 트랙은 본 트랙(1시간)과 **같은 체결 규칙**(_execute_targets)을
  쓴다 — 갈라지면 주기 비교가 체결 규칙 비교로 오염된다.
- 각 트랙은 자기 주기의 닫힌 봉으로만 판단한다.
- 같은 봉으로 두 번 판단하지 않는다(멱등) — 크론이 봉보다 자주 돌 때
  같은 봉을 반복 매매하면 비용만 쌓인다.
- 사다리 실패가 본 실험을 막지 않고, 본 트랙의 판정(90일)을 오염시키지
  않는다 — 공개 리포트가 다중검정 주의를 함께 싣는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.intraday_challenger as IC              # noqa: E402


class _Up:
    """언제나 매수 1.0 — 체결 경로만 보는 검사용."""

    def generate_signals(self, df):
        return pd.Series(np.ones(len(df)), index=df.index)


def _df(n, freq, px=100.0, start="2026-08-17 00:00"):
    idx = pd.date_range(start, periods=n, freq=freq)
    c = np.full(n, px)
    return pd.DataFrame({"open": c, "close": c, "high": c + 1, "low": c - 1,
                         "volume": np.full(n, 1e6)}, index=idx)


def _data(n5=450, n15=150):
    return {"15m": {s: _df(n15, "15min") for s in IC.UNIVERSE},
            "5m": {s: _df(n5, "5min") for s in IC.UNIVERSE}}


def test_each_track_trades_on_its_own_closed_bars(tmp_path):
    out = IC.run_ladder("2026-08-18T12:00:00", state_dir=str(tmp_path),
                        data=_data(), strategy_factory=lambda s: _Up())
    by = {t["timeframe"]: t for t in out}
    assert by["15m"]["trades"] > 0 and by["5m"]["trades"] > 0
    st5 = json.loads((tmp_path / "intraday" / "track_5m.json").read_text("utf-8"))
    st15 = json.loads((tmp_path / "intraday" / "track_15m.json").read_text("utf-8"))
    # 각 트랙이 자기 주기의 마지막 닫힌 봉으로 판단했는가
    last5 = st5["rounds"][-1]["bar_times"][IC.UNIVERSE[0]]
    last15 = st15["rounds"][-1]["bar_times"][IC.UNIVERSE[0]]
    assert last5.endswith("55:00") and last15.endswith("45:00"), (last5, last15)


def test_the_same_bar_is_never_traded_twice(tmp_path):
    data = _data()
    IC.run_ladder("2026-08-18T12:00:00", state_dir=str(tmp_path),
                  data=data, strategy_factory=lambda s: _Up())
    out2 = IC.run_ladder("2026-08-18T12:02:00", state_dir=str(tmp_path),
                         data=data, strategy_factory=lambda s: _Up())
    assert all(t.get("skipped") for t in out2), (
        f"같은 봉인데 또 판단했다 — 비용만 쌓인다: {out2}")


def test_the_ladder_shares_the_execution_rule():
    """사다리가 본 트랙과 같은 체결 함수를 쓴다 — 같은 규칙은 한 곳에."""
    src = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")
    body = src.split("def run_ladder", 1)[1].split("\ndef ", 1)[0]
    assert "_execute_targets(" in body, "사다리가 자기만의 체결 규칙을 만들었다"
    assert "_kill_switch_scale" in body, "사다리 트랙에 브레이크가 없다"


def test_a_ladder_crash_cannot_stop_the_main_round():
    src = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")
    assert "주기 사다리 실패(본 실험 무관)" in src, (
        "사다리 예외가 본 실험으로 새어 나간다")


def test_the_public_report_lists_the_ladder_with_the_warning(tmp_path):
    IC.run_ladder("2026-08-18T12:00:00", state_dir=str(tmp_path),
                  data=_data(), strategy_factory=lambda s: _Up())
    st = {"rounds": [{"time": "2026-08-18T12:00:00", "equity": 10_000.0,
                      "trades": []}],
          "start_cash": 10_000.0, "positions": {}, "cost_paid": 0.0}
    out = IC.write_public_report(st, docs_dir=str(tmp_path),
                                 state_dir=str(tmp_path))
    tfs = {t["timeframe"] for t in out["ladder"]}
    assert tfs == {"15m", "5m"}, out["ladder"]
    for t in out["ladder"]:
        assert t["cost_paid"] > 0 and t["trades_total"] > 0
    assert "우연히" in out["ladder_note"], "다중검정 주의가 빠졌다"
    page = (ROOT / "docs" / "intraday.html").read_text("utf-8")
    assert "주기 사다리" in page and "d.ladder" in page


def test_the_judgement_still_belongs_to_the_main_track():
    """사다리는 참고 진단 — 판정 기준은 본 실험(1시간)의 것만 유효하다."""
    src = (ROOT / "quant" / "live" / "intraday_challenger.py").read_text("utf-8")
    assert "판정은 본 실험(1시간)의" in src, (
        "사다리가 판정 자격을 주장하지 않는다는 문구가 없다")
