"""승격 관문 세 개가 **실제로 막는가** (감사 142).

`ChampionChallenger.evaluate`는 이 시스템에서 가장 무거운 결정을 한다 —
**어떤 전략이 돈을 굴릴 것인가.** 교체 조건은 한 줄이다.

    swap = bool(n >= self.min_obs          # ① 표본이 충분한가
                and mean > self.edge       # ② 평균 우위가 있는가
                and t_stat > self.t_threshold)   # ③ 통계적으로 유의한가

여기에 표본을 만드는 규칙 둘이 더 붙는다.

    diff = (rh - rc)[active]   # ④ 둘 다 관망한 봉은 표본에서 뺀다
    rc.iloc[-tail:]            # ⑤ 결승전은 지정 구간만 본다

변이 시험을 처음 걸어 보니 ③④⑤가 전부 무방비였다 — 지워도 검사가 통과했다.
기존 검사는 '같은 전략이면 교체 안 함', '더 나은 전략이면 교체함' 같은
**결과의 방향**만 봤고, 관문 하나하나가 **혼자서도 막는지**는 아무도 확인하지
않았다.

관문은 평소에 통과시키는 일을 하므로, 하나가 사라져도 대부분의 날에는
아무 차이가 없다. 그래서 **막아야 하는 상황을 만들어** 확인해야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import ChampionChallenger  # noqa: E402

N = 200
IDX = pd.date_range("2026-01-01", periods=N, freq="D")


def _rising() -> pd.DataFrame:
    price = np.linspace(100.0, 300.0, N)
    return pd.DataFrame({"open": price, "high": price, "low": price,
                         "close": price, "volume": 1.0}, index=IDX)


class _Flat:
    name = "flat"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index, name="target")


class _Long:
    """내내 롱 — 오르는 장에서 관망보다 확실히 낫다."""
    name = "long"
    allow_short = False

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index, name="target")


class _LateLong:
    """후반부에만 롱 — 앞쪽 봉은 둘 다 관망이라 표본에서 빠져야 한다."""
    name = "late_long"
    allow_short = False

    def generate_signals(self, df):
        s = pd.Series(0.0, index=df.index, name="target")
        s.iloc[N // 2:] = 1.0
        return s


def _cc(**kw):
    base = dict(min_obs=20, edge=0.0, t_threshold=1.0)
    base.update(kw)
    return ChampionChallenger(_Flat(), _Long(), **base)


# ── 전제 — 이 설정에서는 원래 교체된다 ────────────────────────


def test_the_challenger_normally_wins_here():
    """대조군이 없으면 아래 검사들이 '항상 False'를 확인하는 헛것이 된다."""
    res = _cc().evaluate(_rising())
    assert res["swap"] is True, res
    assert res["t_stat"] > 1.0 and res["mean_diff"] > 0


# ── ① 최소 표본 ───────────────────────────────────────────────


def test_a_thin_sample_cannot_promote():
    res = _cc(min_obs=10_000).evaluate(_rising())
    assert res["swap"] is False, (
        f"표본 {res['n']}건인데 최소 10,000건 조건을 통과했다")


# ── ② 평균 우위 ───────────────────────────────────────────────


def test_a_challenger_without_enough_edge_cannot_promote():
    res = _cc(edge=1.0).evaluate(_rising())     # 봉당 +100% 우위를 요구
    assert res["swap"] is False, res


# ── ③ 통계적 유의성 ───────────────────────────────────────────


def test_statistical_significance_is_required_on_its_own():
    """평균 우위가 있어도 t가 문턱을 못 넘으면 교체하지 않는다.

    이것이 다중검정 보정(select_t·confirm_t)이 실제로 작동하는 지점이다 —
    이 조건이 빠지면 '운 좋은 승자'가 그대로 챔피언이 된다.
    """
    res = _cc(t_threshold=1e9).evaluate(_rising())
    assert res["mean_diff"] > 0, "전제가 깨졌다 — 평균 우위가 없다"
    assert res["swap"] is False, (
        f"t={res['t_stat']:.2f}인데 문턱 1e9을 통과했다 — t-검정이 안 걸린다")


# ── ④ 관망 봉은 표본에서 뺀다 ─────────────────────────────────


def test_bars_where_both_sat_out_do_not_inflate_the_sample():
    """둘 다 관망한 봉의 수익 차이는 0이다 — 정보가 없는데 표본만 늘린다.

    0을 잔뜩 섞으면 평균이 0쪽으로 눌리고 표본은 커져, t-통계가 인위적으로
    바뀐다. 판단이 데이터가 아니라 워밍업 길이에 좌우된다.
    """
    cc = ChampionChallenger(_Flat(), _LateLong(), min_obs=5, edge=0.0,
                            t_threshold=1.0)
    res = cc.evaluate(_rising())
    assert res["n"] <= N // 2 + 2, (
        f"표본이 {res['n']}건 — 전반부 관망 구간까지 세고 있다(전체 {N}봉)")
    assert res["n"] >= N // 2 - 5, f"표본이 너무 적다: {res['n']}"


# ── ⑤ 결승전은 지정 구간만 본다 ───────────────────────────────


def test_the_final_round_only_looks_at_the_window_it_was_given():
    """tail=30이면 최근 30봉만 — 이게 풀리면 결승전이 선발 구간을 다시 본다.

    선발전에서 이미 본 구간을 결승에서 또 보면 '미공개 구간 재검증'이라는
    2단계 관문의 의미가 통째로 사라진다.
    """
    full = _cc().evaluate(_rising())
    tail = _cc().evaluate(_rising(), tail=30)
    assert tail["n"] <= 30, f"tail=30인데 표본이 {tail['n']}건이다"
    assert tail["n"] < full["n"], "구간을 잘랐는데 표본이 그대로다"


# ── 폴드 일관성 ───────────────────────────────────────────────


def test_fold_wins_are_counted_when_asked():
    res = _cc().evaluate(_rising(), folds=3)
    assert res["n_folds"] == 3
    assert res["fold_wins"] == 3, (
        f"내내 이기는 챌린저인데 폴드 승리가 {res['fold_wins']}/3이다")


def test_folds_are_not_reported_when_not_asked():
    """묻지 않았으면 만들어 내지 않는다 — 없는 근거가 생기면 안 된다."""
    assert "fold_wins" not in _cc().evaluate(_rising())
