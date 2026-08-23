"""다양성 가중 그림자 — '섞는 비중' 축만 흔드는 두 가상 계좌 (2026-08-23).

의회 비중(softmax)은 의원 간 상관을 보지 않는다. 상관까지 본 비중(alt_weight)
과의 거리(weight_gap)는 매일 재 왔고(실측 0.196), 이제 그 격차가 실제 돈
곡선에서 얼마인지 두 트랙으로 잰다. 사전 등록 문턱(0.2) **미달 상태에서
사장님 지시로 조기 착수**했다 — 그 사실은 모듈과 공개 노트에 함께 적힌다.

지켜야 할 약속:
- 의회 1석이거나 alt_weight가 하나라도 없으면 그 계좌는 잴 수 없다(None).
  None을 0으로 적지 않는다.
- 두 트랙은 **같은 신호·같은 종목·같은 규약**이고 섞는 비중만 다르다.
- 전일 목표를 오늘 수익에 적용한다(1봉 지연) — 오늘 목표로 오늘을 벌면
  선견이다.
- 잴 것이 없는 날은 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.diversity_shadow import (          # noqa: E402
    START_CASH,
    diversity_public,
    mix_pair,
    run_diversity_shadow,
)


def _mid_month_df(n=80):
    """월 중순만 걷는 일봉 — turn_of_month 신호가 전부 0이 되는 달력."""
    days = []
    d = pd.Timestamp("2025-01-08")
    while len(days) < n:
        if 8 <= d.day <= 20 and d.weekday() < 5:
            days.append(d)
        d += pd.Timedelta(days=1)
    c = np.full(len(days), 100.0)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c,
                         "volume": np.full(len(days), 1e6)},
                        index=pd.DatetimeIndex(days))


def _write_champions(tmp_path, members):
    (tmp_path / "champions.json").write_text(json.dumps({
        "us_stock:AAPL": {"strategy": members[0]["strategy"],
                          "params": members[0]["params"],
                          "parliament": members}}), "utf-8")


def test_the_pair_mixes_the_same_signals_with_two_weightings(tmp_path):
    """buy_hold(항상 1) + turn_of_month(중순엔 0) 의회 — 혼합은 비중이 결정."""
    _write_champions(tmp_path, [
        {"strategy": "buy_hold", "params": {}, "weight": 0.3,
         "alt_weight": 0.8},
        {"strategy": "turn_of_month", "params": {}, "weight": 0.7,
         "alt_weight": 0.2},
    ])
    pair = mix_pair("us_stock", "AAPL", _mid_month_df(), str(tmp_path))
    assert pair is not None
    pos_a, pos_d = pair
    assert abs(pos_a - 0.3) < 1e-9, "실제 비중 혼합이 틀렸다"
    assert abs(pos_d - 0.8) < 1e-9, "다양성 비중 혼합이 틀렸다"


def test_a_single_seat_or_missing_alt_weight_is_not_measurable(tmp_path):
    # 1석 — alt_weight가 있어도 '혼합 비교'가 성립하지 않는다
    _write_champions(tmp_path, [
        {"strategy": "buy_hold", "params": {}, "weight": 1.0,
         "alt_weight": 1.0}])
    assert mix_pair("us_stock", "AAPL", _mid_month_df(),
                    str(tmp_path)) is None
    # 2석인데 alt_weight 하나가 없다 — 균등으로 채우면 '모름'이 '판단'이 된다
    _write_champions(tmp_path, [
        {"strategy": "buy_hold", "params": {}, "weight": 0.5,
         "alt_weight": 0.5},
        {"strategy": "turn_of_month", "params": {}, "weight": 0.5}])
    assert mix_pair("us_stock", "AAPL", _mid_month_df(),
                    str(tmp_path)) is None


def test_an_empty_day_writes_nothing(tmp_path):
    assert run_diversity_shadow(bar="2026-08-23", pairs={}, marks={},
                                state_dir=str(tmp_path)) is None
    assert run_diversity_shadow(bar="2026-08-23",
                                pairs={"k": (0.5, 0.5)}, marks={},
                                state_dir=str(tmp_path)) is None
    assert not (tmp_path / "diversity_shadow").exists(), (
        "잴 것이 없는 날 파일을 만들었다 — 빈 회차가 가짜 평평함을 만든다")


def test_yesterdays_target_earns_todays_return_and_tracks_diverge(tmp_path):
    """1봉 지연 + 트랙 격리 — 같은 가격 변화에 두 트랙이 비중만큼 다르게 번다."""
    pairs = {"us_stock:AAPL": (0.2, 0.8)}
    d1 = run_diversity_shadow(bar="d1", pairs=pairs,
                              marks={"us_stock:AAPL": 100.0},
                              state_dir=str(tmp_path))
    # 첫날 — 전일 목표가 없으니 수익 0, 회전 수수료만
    assert d1["actual"]["equity"] < START_CASH
    d2 = run_diversity_shadow(bar="d2", pairs=pairs,
                              marks={"us_stock:AAPL": 110.0},
                              state_dir=str(tmp_path))
    ra = d2["actual"]["equity"] / d1["actual"]["equity"] - 1
    rd = d2["diversity"]["equity"] / d1["diversity"]["equity"] - 1
    assert ra > 0 and rd > 0, "전일 목표가 오늘 수익을 못 벌었다(1봉 지연 위반?)"
    assert rd > ra + 0.02, (
        "두 트랙이 비중 차이만큼 갈라지지 않았다 — 격리 실패(같은 비중을 쓴다?)")


def test_rerunning_the_same_bar_is_idempotent(tmp_path):
    pairs = {"k": (0.5, 0.5)}
    marks = {"k": 100.0}
    a = run_diversity_shadow(bar="d1", pairs=pairs, marks=marks,
                             state_dir=str(tmp_path))
    b = run_diversity_shadow(bar="d1", pairs=pairs, marks=marks,
                             state_dir=str(tmp_path))
    assert a == b
    st = json.loads((tmp_path / "diversity_shadow" / "actual.json")
                    .read_text("utf-8"))
    assert len(st["history"]) == 1


def test_a_symbol_without_a_mark_leaves_both_tracks(tmp_path):
    """시세 없는 종목은 두 트랙 모두에서 빠진다 — 한쪽만 빼면 비교가 죽는다."""
    out = run_diversity_shadow(
        bar="d1", pairs={"a": (0.5, 0.5), "b": (1.0, 1.0)},
        marks={"a": 100.0}, state_dir=str(tmp_path))
    assert out["actual"]["symbols"] == 1
    assert out["diversity"]["symbols"] == 1


def test_the_early_start_is_confessed_not_hidden():
    """문턱(0.2) 미달(0.196) 조기 착수 사실이 모듈과 공개 노트에 있다."""
    src = (ROOT / "quant" / "live" / "diversity_shadow.py").read_text("utf-8")
    assert "0.196" in src and "0.2" in src
    assert "조기" in src, "조기 착수라는 사실이 소스에 없다"


def test_it_is_wired_into_the_daily_batch():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "mix_pair(market, symbol, df_sig, state_dir)" in src, (
        "재료 수집이 배선되지 않았다 — 계좌는 있는데 영원히 빈다")
    assert "run_diversity_shadow(bar=bar, pairs=div_pairs" in src, (
        "계좌 전진이 배선되지 않았다")
    assert 'status["diversity_shadow"]' in src, (
        "공개 배선이 없다 — 재고도 아무도 못 보면 잰 것이 아니다")


def test_the_public_note_and_rows(tmp_path):
    assert diversity_public(str(tmp_path)) is None
    run_diversity_shadow(bar="d1", pairs={"k": (0.5, 0.5)},
                         marks={"k": 100.0}, state_dir=str(tmp_path))
    pub = diversity_public(str(tmp_path))
    assert set(pub["tracks"]) == {"actual", "diversity"}
    assert "0.196" in pub["note"], "공개 노트가 조기 착수 사실을 숨겼다"
