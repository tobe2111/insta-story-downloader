"""배분 사다리 — "얼마씩 나눌까"도 측정으로 (2026-08-19).

종목 선정(오디션)·매매 주기(주기 사다리)는 진화하는데 배분(HRP)만 고정
규칙이었다. 같은 신호·같은 데이터에 배분 방법만 바꾼 가상 계좌 4개를
나란히 굴려 그 비대칭을 끝낸다.

지켜야 할 약속:
- 같은 봉을 두 번 굴려도 계좌가 두 번 움직이지 않는다(멱등).
- 시세가 없는 날은 아무것도 쓰지 않는다(가짜 평평함 금지).
- 균등 배분은 정말 1/n이다(이름과 동작의 일치).
- hrp·erc는 본 계좌가 쓰는 바로 그 함수를 부른다(같은 규칙 한 곳).
- 전일 목표가 오늘 수익을 만든다(1봉 지연) — 오늘 신호로 오늘 수익을
  먹으면 룩어헤드다.
- 본 계좌 배치에 배선돼 있고, 실험 실패가 본 계좌를 못 죽인다.
- 화면에는 '상대 비교 전용'과 다중검정 주의가 장부에서 읽혀 나간다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.live.alloc_ladder as AL                     # noqa: E402


def _rets_map(seed=0, n=120):
    rng = np.random.RandomState(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return {f"m:S{i}": pd.Series(rng.normal(0, 0.01 * (i + 1), n), index=idx)
            for i in range(3)}


_W = {"m:S0": 1.0, "m:S1": 1.0, "m:S2": 1.0}


def _run(tmp_path, bar, marks, weights=_W):
    return AL.run_alloc_ladder(bar=bar, weights=weights,
                               rets_map=_rets_map(), marks=marks,
                               n_total=3, state_dir=str(tmp_path))


def test_same_bar_is_idempotent(tmp_path):
    marks = {"m:S0": 100.0, "m:S1": 200.0, "m:S2": 300.0}
    _run(tmp_path, "2026-08-19", marks)
    st1 = json.loads((tmp_path / "alloc_ladder" / "equal.json").read_text("utf-8"))
    _run(tmp_path, "2026-08-19", marks)
    st2 = json.loads((tmp_path / "alloc_ladder" / "equal.json").read_text("utf-8"))
    assert st1 == st2 and len(st2["history"]) == 1, "같은 봉에 두 번 움직였다"


def test_no_marks_writes_nothing(tmp_path):
    assert _run(tmp_path, "2026-08-19", {}) is None
    assert not (tmp_path / "alloc_ladder").exists() or \
        not list((tmp_path / "alloc_ladder").glob("*.json")), (
        "시세 없는 날 기록을 만들었다 — 곡선이 가짜 평평함을 얻는다")


def test_equal_really_means_one_over_n(tmp_path):
    marks = {"m:S0": 100.0, "m:S1": 200.0, "m:S2": 300.0}
    _run(tmp_path, "2026-08-19", marks)
    st = json.loads((tmp_path / "alloc_ladder" / "equal.json").read_text("utf-8"))
    for k, v in st["prev_weights"].items():
        assert abs(v - 1.0 / 3) < 1e-5, f"균등이 균등이 아니다: {k}={v}"


def test_yesterdays_target_earns_todays_return(tmp_path):
    """1봉 지연 — 오늘 정한 비중이 오늘 수익을 먹으면 룩어헤드다."""
    d1 = {"m:S0": 100.0, "m:S1": 100.0, "m:S2": 100.0}
    d2 = {"m:S0": 110.0, "m:S1": 110.0, "m:S2": 110.0}   # +10%
    _run(tmp_path, "2026-08-19", d1)
    st1 = json.loads((tmp_path / "alloc_ladder" / "equal.json").read_text("utf-8"))
    _run(tmp_path, "2026-08-20", d2)
    st2 = json.loads((tmp_path / "alloc_ladder" / "equal.json").read_text("utf-8"))
    # 첫날은 보유가 없었으니(전일 목표 없음) 수수료만 나가고, 둘째 날
    # +10%를 총노출만큼 먹는다.
    gross = st1["history"][0]["gross"]
    got = st2["history"][1]["equity"] / st1["history"][0]["equity"] - 1
    want = 0.10 * gross
    assert abs(got - want) < 0.01, (
        f"둘째 날 수익 {got:.4f} ≠ 전일 노출 {gross:.2f}×10% ({want:.4f})")


def test_hrp_and_erc_come_from_the_one_true_place():
    src = (ROOT / "quant" / "live" / "alloc_ladder.py").read_text("utf-8")
    assert "from quant.live.daily import _hrp_slices" in src
    assert "from quant.live.daily import _erc_slices" in src, (
        "hrp·erc를 복사해 왔다 — 본 계좌와 반드시 어긋난다(같은 규칙 한 곳)")


def test_the_daily_batch_is_wired_and_cannot_be_killed_by_it():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "run_alloc_ladder(bar=bar" in src, "일일 배치에 배선이 없다"
    i = src.find("run_alloc_ladder(bar=bar")
    guard = src[max(0, i - 400):i]
    assert "try:" in guard, (
        "실험이 예외 방벽 없이 본 계좌 경로에 들어 있다 — 실험 실패가 "
        "본 계좌 배치를 죽인다")


def test_the_screen_reads_the_warning_from_the_ledger(tmp_path):
    marks = {"m:S0": 100.0, "m:S1": 200.0, "m:S2": 300.0}
    _run(tmp_path, "2026-08-19", marks)
    pub = AL.ladder_public(str(tmp_path))
    assert set(pub["tracks"]) == set(AL.ALLOC_METHODS)
    assert "상대 비교 전용" in pub["note"] and "우연히" in pub["note"], (
        "규약·다중검정 주의가 요약에 없다")
    paper = (ROOT / "docs" / "paper.html").read_text("utf-8")
    assert "alloc_ladder" in paper and "st.alloc_ladder.note" in paper, (
        "화면이 주의 문구를 장부에서 읽지 않는다 — 산문에 다시 쓰면 "
        "어긋난 날 거짓말이 된다")
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["alloc_ladder"]' in daily, "status.json에 실리지 않는다"
