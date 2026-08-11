"""오디션의 과최적화 방어선이 실제로 구속하는가 — 변이 시험으로 드러난 공백.

2026-08-11 감사 60. scripts/mutation_check.py 2차에서 세 장치가 '망가뜨려도
아무 검사가 실패하지 않는' 상태로 드러났다.

  ❌ `select_df = df.iloc[:-confirm_window]` → `select_df = df`
     선발전이 결승 구간을 미리 보게 만든다. 이건 오디션 전체에서 **가장
     중요한 장치**다 — 선발이 결승 데이터로 이뤄지면 결승은 검증이 아니라
     같은 데이터의 재확인이고, 2단계 관문이 1단계가 된다. 그 상태로도
     테스트가 전부 초록이었다.
  ❌ `select_t: float = 2.0` → `0.0`
     다중검정 보정 문턱을 없앤다. 후보 20여 명을 매일 세우면 그중 몇은
     운으로 이긴다. 문턱이 0이면 그 운을 전부 승격시킨다.
  ❌ 통합 계좌에서 합성 폴백 데이터로도 매매하게 만든다
     사이트가 "실데이터로만 판단한다"고 말하는 그 규칙이다.

셋 다 '있다는 것'은 소스로 확인됐지만 '구속한다는 것'은 아무도 안 봤다.
이 파일은 장치를 우회했을 때 결과가 실제로 달라지는지를 숫자로 확인한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.retrain import nightly_retrain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _frame(n=600, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)


class _Fixed:
    """지정한 비중 시계열을 그대로 내는 전략(결정적)."""

    name = "fixed"
    allow_short = True

    def __init__(self, series: pd.Series):
        self._s = series

    def generate_signals(self, df):
        return self._s.reindex(df.index).fillna(0.0)


# ── ① 선발전은 결승 구간을 볼 수 없다 ─────────────────────────


def test_selection_round_cannot_see_the_confirmation_window():
    """결승 구간에서만 잘하는 후보는 선발전을 통과하지 못해야 한다.

    후보를 이렇게 만든다: 결승 구간(마지막 confirm_window봉)에서는 완벽히
    맞히고, 그 앞 선발전 구간에서는 완벽히 틀린다. 선발전이 결승을 못
    본다면 이 후보는 1차에서 탈락한다. 만약 선발전이 전체 구간을 본다면
    결승 구간의 대박이 t-통계를 끌어올려 통과할 수 있다.
    """
    df = _frame()
    CONFIRM = 120
    ret = df["close"].pct_change().shift(-1).fillna(0.0)

    # 결승 구간만 정답(미래를 아는 후보), 그 전 구간은 오답
    peek = pd.Series(np.where(np.arange(len(df)) >= len(df) - CONFIRM,
                              np.sign(ret), -np.sign(ret)), index=df.index)
    flat = pd.Series(0.0, index=df.index)

    def build(spec):
        return _Fixed(peek if spec.get("params", {}).get("kind") == "peek"
                      else flat)

    out = nightly_retrain(
        df, {"strategy": "fixed", "params": {"kind": "flat"}},
        [{"strategy": "fixed", "params": {"kind": "peek"}}],
        build=build, confirm_window=CONFIRM, select_folds=0)

    assert not out["promoted"], (
        "결승 구간에서만 잘한 후보가 승격됐다 — 선발전이 결승을 미리 봤다")
    cand = out["candidates"][0]
    assert cand["t_stat"] <= 0, (
        f"선발전 t={cand['t_stat']:.2f} — 선발 구간에서는 지고 있어야 한다")


def test_selection_window_is_actually_shorter_than_the_data():
    """선발전 표본 수가 결승 구간만큼 짧아졌는지 직접 확인한다."""
    df = _frame(n=400)
    CONFIRM = 120
    seen = {}

    class _Recorder(_Fixed):
        def generate_signals(self, d):
            seen.setdefault("n", []).append(len(d))
            return super().generate_signals(d)

    flat = pd.Series(0.0, index=df.index)
    nightly_retrain(df, {"strategy": "fixed", "params": {}},
                    [{"strategy": "fixed", "params": {"x": 1}}],
                    build=lambda s: _Recorder(flat),
                    confirm_window=CONFIRM, select_folds=0)
    assert seen["n"], "전략이 한 번도 호출되지 않았다"
    assert min(seen["n"]) == len(df) - CONFIRM, (
        f"선발전이 {min(seen['n'])}봉을 봤다 — {len(df) - CONFIRM}봉이어야 한다")


# ── ② 다중검정 보정 문턱이 후보를 실제로 거른다 ───────────────


def test_selection_threshold_actually_rejects_weak_candidates():
    """문턱을 올리면 통과하던 후보가 떨어진다 — 문턱이 살아 있다는 증거.

    변이 시험에서 select_t를 2.0 → 0.0으로 내려도 아무 검사가 실패하지
    않았다. 후보 20여 명을 매일 세우면 그중 몇은 운으로 이기고, 문턱이
    없으면 그 운이 전부 챔피언이 된다.
    """
    df = _frame(seed=7)
    ret = df["close"].pct_change().shift(-1).fillna(0.0)
    rng = np.random.default_rng(3)
    # 아주 약한 우위(잡음에 살짝 묻힌 정답) — 문턱에 따라 갈리는 후보
    weak = pd.Series(np.sign(ret) * (rng.random(len(df)) < 0.53),
                     index=df.index)
    flat = pd.Series(0.0, index=df.index)

    def build(spec):
        return _Fixed(weak if spec.get("params", {}).get("kind") == "weak"
                      else flat)

    champ = {"strategy": "fixed", "params": {"kind": "flat"}}
    ch = [{"strategy": "fixed", "params": {"kind": "weak"}}]
    kw = dict(build=build, confirm_window=120, select_folds=0, confirm_t=0.0)

    lenient = nightly_retrain(df, champ, ch, select_t=0.0, **kw)
    strict = nightly_retrain(df, champ, ch, select_t=99.0, **kw)

    assert lenient["candidates"][0]["swap"], (
        "문턱 0에서도 통과하지 못했다 — 테스트 전제가 깨졌다")
    assert lenient["promoted"]
    assert not strict["candidates"][0]["swap"], (
        "문턱 99에서도 통과했다 — 문턱이 아무것도 거르지 않는다")
    assert not strict["promoted"], "선발전을 못 넘었는데 승격됐다"


def test_default_threshold_is_not_zero():
    """기본 문턱이 0으로 되돌려지면(보정 해제) 잡는다."""
    import inspect
    sig = inspect.signature(nightly_retrain)
    assert sig.parameters["select_t"].default >= 1.5, (
        "다중검정 보정 문턱이 사실상 해제됐다")
    assert sig.parameters["confirm_window"].default >= 60


# ── ③ 합성 폴백 데이터로는 매매하지 않는다 ────────────────────


def test_portfolio_refuses_synthetic_fallback_data(monkeypatch, tmp_path):
    """사이트가 "실데이터로만 판단한다"고 말하는 그 규칙의 끝단 확인.

    제공자가 조용히 합성 데이터로 폴백하면(네트워크 장애 시 개발 편의)
    그 위의 기록은 그럴듯한 거짓말이 된다. 통합 계좌 경로에서 실제로
    거부되는지 본다 — 변이 시험에서 이 가드를 꺼도 전부 통과했다.
    """
    from quant.live import daily as dl

    fake = _frame(seed=21)
    fake.attrs["synthetic_fallback"] = True

    class _P:
        def get_ohlcv(self, *a, **k):
            out = fake.copy()
            out.attrs["synthetic_fallback"] = True
            return out

    monkeypatch.setattr("quant.data.get_provider", lambda m: _P())
    monkeypatch.setattr(dl, "champion_strategy",
                        lambda *a, **k: _Fixed(pd.Series(0.5, index=fake.index)))
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    targets = [("synthetic", "AAA"), ("synthetic", "BBB")]

    # require_real_data=True(운영 기본값) → 전 종목이 폴백이므로 기록 없음
    with pytest.raises(RuntimeError, match="전 종목"):
        dl.run_daily_portfolio(targets, state_dir=str(tmp_path),
                               require_real_data=True)

    # 끄면(테스트·데모용) 돌아간다 — 가드가 실제로 그 플래그를 본다는 증거
    out = dl.run_daily_portfolio(targets, state_dir=str(tmp_path / "b"),
                                 require_real_data=False)
    assert not out.get("skipped")


def test_real_data_default_is_on():
    """운영 기본값이 꺼지면(가짜 데이터 허용) 잡는다."""
    import inspect

    from quant.live.daily import run_daily_paper, run_daily_portfolio
    for fn in (run_daily_portfolio, run_daily_paper):
        assert inspect.signature(fn).parameters[
            "require_real_data"].default is True, fn.__name__
