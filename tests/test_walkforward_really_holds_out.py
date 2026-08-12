"""워크포워드가 **정말로 미래를 가려 두는가** (감사 144).

`walk_forward`는 이 시스템의 '신뢰할 만함' 판정을 떠받친다. 여기서 나온
OOS 샤프와 DSR이

    · 검증 리포트의 종합 판정
    · flag_watch의 과적합 경보
    · 엣지 입증 게이트(연 12% → 20% 잠금 해제)

로 이어진다. 그런데 변이를 처음 걸어 보니 **핵심 둘이 무방비**였다.

    is_slice = df.iloc[start : start + is_window]
    →  df.iloc[start : start + is_window + gap + oos_window]      ❌ 통과

    oos_ret = res.returns.iloc[-oos_window:]
    →  oos_ret = res.returns                                       ❌ 통과

첫 번째는 **워크포워드의 존재 이유 그 자체**다. IS에서 파라미터를 고르고
OOS에서 검증하는 것이 전부인데, IS가 OOS를 포함하면 그냥 전 구간
과최적화다. 그러고도 결과는 'OOS 성적'이라는 이름을 달고 나간다.

두 번째는 소스 주석이 이미 요구하고 있었다: "구간별 OOS 지표는 워밍업을
제외한 '꼬리'로만 계산해야 정직하다." 적어 두기만 하고 아무도 확인하지
않았다 — 오늘 반복해서 나온 계열이다.

이 파일은 최적화기가 **실제로 무엇을 받았는지**를 기록해서 확인한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.optimize.walkforward as WF  # noqa: E402
from quant.strategies.moving_average import MovingAverageCross  # noqa: E402

N = 420
IS_W, OOS_W, GAP, STEP = 200, 60, 5, 60
GRID = {"fast": [5, 10], "slow": [30, 60]}


def _df() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    idx = pd.date_range("2025-01-01", periods=N, freq="D")
    close = 100.0 * np.cumprod(1 + rng.normal(0.0005, 0.02, N))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1000.0}, index=idx)


def _run(spy=None):
    df = _df()
    return df, WF.walk_forward(df, MovingAverageCross, GRID, is_window=IS_W,
                               oos_window=OOS_W, step=STEP, embargo=GAP)


# ── ① 최적화기는 검증 구간을 보면 안 된다 ─────────────────────


def test_the_optimiser_never_sees_the_holdout(monkeypatch):
    """그리드 탐색에 넘어간 프레임이 OOS 시작 전에서 끝나는가.

    소스 모양이 아니라 **최적화기가 실제로 받은 데이터**를 기록해서 본다.
    """
    seen: list = []
    real = WF.grid_search

    def _spy(df_slice, *a, **kw):
        seen.append((df_slice.index[0], df_slice.index[-1], len(df_slice)))
        return real(df_slice, *a, **kw)

    monkeypatch.setattr(WF, "grid_search", _spy)
    df, res = _run()
    assert seen, "그리드 탐색이 한 번도 안 불렸다 — 검사가 헛돈다"

    idx = list(df.index)
    for (lo, hi, ln) in seen:
        assert ln == IS_W, f"최적화 구간 길이가 {ln} (기대 {IS_W})"
        start = idx.index(lo)
        oos_start = start + IS_W + GAP
        assert idx.index(hi) < oos_start, (
            f"최적화기가 검증 구간을 미리 봤다: 끝 {hi} ≥ OOS 시작 "
            f"{idx[oos_start]}")


def test_the_embargo_gap_is_actually_left_empty(monkeypatch):
    """학습 마지막 봉과 검증 첫 봉 사이에 gap봉이 비어 있는가."""
    seen: list = []
    real = WF.grid_search

    def _spy(df_slice, *a, **kw):
        seen.append(df_slice.index[-1])
        return real(df_slice, *a, **kw)

    monkeypatch.setattr(WF, "grid_search", _spy)
    df, res = _run()
    idx = list(df.index)
    for seg, is_end in zip(res["segments"], seen):
        gap_bars = idx.index(pd.Timestamp(seg["oos_start"])) - idx.index(is_end) - 1
        assert gap_bars == GAP, (
            f"엠바고가 {gap_bars}봉 — {GAP}봉이어야 한다 "
            "(학습 직후 봉이 바로 검증에 들어가면 정보가 샌다)")


# ── ② OOS 성과는 꼬리만 센다 ──────────────────────────────────


def test_only_the_holdout_tail_counts_as_oos_performance():
    """워밍업 구간이 성과에 섞이면 '검증 성적'이 아니게 된다.

    IS 이력을 워밍업으로 함께 백테스트하는 것은 콜드 스타트 편향을 막기
    위한 것이고(그 자체는 옳다), 성과로 세는 것은 마지막 oos_window봉뿐이어야
    한다. 섞이면 관망 봉이 성적을 희석하고 표본이 부풀어 DSR까지 흔들린다.
    """
    df, res = _run()
    n_seg = len(res["segments"])
    assert n_seg >= 2, f"구간이 {n_seg}개뿐 — 검사가 약해진다"
    # 이어 붙인 OOS 계열은 중복 제거 후 '구간 수 × oos_window' 언저리여야 한다.
    got = len(res["equity"]) - 1        # equity는 시작점 하나가 더 붙는다
    assert got <= n_seg * OOS_W, (
        f"OOS 표본이 {got}봉 — 최대 {n_seg * OOS_W}봉이어야 한다"
        "(워밍업 구간까지 성과로 세고 있다)")
    assert got >= n_seg * OOS_W * 0.5, f"OOS 표본이 너무 적다: {got}"


def test_segments_report_the_window_they_actually_measured():
    """구간별 기록의 oos_start가 실제 검증 시작 봉과 같은가."""
    df, res = _run()
    idx = list(df.index)
    for k, seg in enumerate(res["segments"]):
        expect = idx[k * STEP + IS_W + GAP]
        assert pd.Timestamp(seg["oos_start"]) == expect, (
            f"{k}번째 구간이 {seg['oos_start']}이라 적혔는데 실제는 {expect}")


# ── ③ 다중검정 보정이 살아 있는가 ─────────────────────────────


def test_more_trials_lower_the_deflated_sharpe():
    """시도를 많이 할수록 '운 좋은 승자' 문턱이 높아져야 한다.

    이 관계가 끊기면 매일 23명씩 이겨 온 챔피언을 그리드 4개짜리 기준으로
    평가하게 된다(감사 2026-08-11에서 실제로 그랬다).
    """
    df = _df()
    few = WF.walk_forward(df, MovingAverageCross, GRID, is_window=IS_W,
                          oos_window=OOS_W, step=STEP, embargo=GAP)
    many = WF.walk_forward(df, MovingAverageCross, GRID, is_window=IS_W,
                           oos_window=OOS_W, step=STEP, embargo=GAP,
                           extra_trials=5000)
    assert many["n_trials"] == 5000 and few["n_trials"] == 4
    assert many["dsr"] <= few["dsr"] + 1e-12, (
        f"시도 5,000회의 DSR({many['dsr']:.4f})이 4회({few['dsr']:.4f})보다 "
        "높다 — 다중검정 보정이 반대로 동작한다")
