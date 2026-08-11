"""룩어헤드 검사를 '실제로 링에 오르는 후보 전부'로 넓힌다.

2026-08-11 감사 57. tests/test_leakage.py의 자동 순회는 `list_strategies()`를
돈다 — ma_cross·momentum·…·ml 9개다. 그런데 야간 오디션이 실제로 세우는
링은 그것이 아니다. build_challengers()가 만드는 링에는

  · ML 변형 15종(보정·트리플배리어·메타라벨·시간감쇠·가지치기·풀링 …)
  · 챔피언 돌연변이(시드 결정적)
  · 래퍼 3종 — regime_wrap / event_wrap / stop_wrap

이 들어 있고, 이 중 무엇이든 그날의 챔피언이 되어 **실제로 돈을 굴린다.**
그런데 순회 검사는 기본 파라미터의 ml 하나만 보고 지나갔다. event_wrap과
stop_wrap은 오늘 손으로 읽어 인과적임을 확인했지만, 검사가 없다는 것은
다음에 누가 고칠 때 아무도 못 잡는다는 뜻이다.

룩어헤드는 이 시스템에서 가장 비싼 결함이다 — 조용하고, 백테스트를
아름답게 만들고, 실전에서만 틀린다. 그러니 검사 범위는 '등록된 전략'이
아니라 '챔피언이 될 수 있는 것 전부'여야 한다. 이 파일은 링 구성 함수를
그대로 불러 순회하므로, 앞으로 후보를 추가하면 자동으로 함께 검사된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.synthetic import SyntheticDataProvider  # noqa: E402
from quant.live.retrain import (  # noqa: E402
    DEFAULT_CHAMPION,
    build_challengers,
    build_strategy,
)

_DF = SyntheticDataProvider(seed=23).get_ohlcv("RING", "1d", limit=420)
_CUT = 320


def _spec_label(spec: dict) -> str:
    s = spec.get("strategy", "?")
    p = spec.get("params", {})
    inner = p.get("inner")
    if isinstance(inner, dict):
        return f"{s}({_spec_label(inner)})"
    keys = [f"{k}={v}" for k, v in sorted(p.items()) if k != "inner"]
    return f"{s}[{','.join(keys[:4])}]"


def _resolve(spec: dict, champion: dict) -> dict:
    """링의 원시 스펙을 run_retrain과 **똑같은 규칙**으로 실제 스펙으로 바꾼다.

    링에는 `{"model": "gb", ...}`처럼 strategy 키가 없는 '병합형'이 섞여 있다.
    이것은 '챔피언과 같은 전략의 파라미터 변형'이라는 뜻이며, retrain.py가
    챔피언 params 위에 얹어 해석한다. 검사도 같은 규칙을 써야 실제로 링에
    오르는 것을 검사하는 것이 된다.
    """
    if "strategy" in spec:
        return {"strategy": spec["strategy"],
                "params": dict(spec.get("params", {}))}
    return {"strategy": champion["strategy"],
            "params": {**champion.get("params", {}), **spec}}


def _assert_causal(spec: dict, *, include_boundary: bool = True) -> None:
    """미래를 잘라내도 겹치는 과거 신호가 한 봉도 달라지면 안 된다.

    ⚠️ 경계 봉(_CUT-1)을 **포함해서** 비교한다. 제외하면 shift(-1) 한 봉짜리
       룩어헤드가 통째로 안 보인다 — 가장 흔한 형태가 정확히 그 한 봉이다.
    """
    end = _CUT if include_boundary else _CUT - 1
    full = build_strategy(spec).generate_signals(_DF)
    trunc = build_strategy(spec).generate_signals(_DF.iloc[:_CUT])
    a = full.iloc[:end].to_numpy(dtype=float)
    b = trunc.iloc[:end].to_numpy(dtype=float)
    assert len(a) == len(b) == end
    bad = int(np.sum(~np.isclose(a, b, atol=1e-9, equal_nan=True)))
    assert bad == 0, (
        f"'{_spec_label(spec)}' 미래 참조 의심: 미래를 자르니 과거 신호 "
        f"{bad}봉이 바뀐다")


def test_every_challenger_in_the_ring_is_causal():
    """그날 링에 오르는 후보 전부 — 래퍼·ML 변형·돌연변이 포함."""
    ring = build_challengers(DEFAULT_CHAMPION, seed="2026-08-11:crypto")
    assert len(ring) >= 20, f"링이 너무 작다({len(ring)}) — 구성이 바뀌었나?"
    n_ml, n_wrap = 0, 0
    for raw in ring:
        spec = _resolve(raw, DEFAULT_CHAMPION)
        _assert_causal(spec)
        if spec["strategy"] == "ml":
            n_ml += 1
        elif spec["strategy"].endswith("_wrap"):
            n_wrap += 1
    # 병합형(ML 변형)과 래퍼가 실제로 검사됐는지 — 해석이 조용히 깨져
    # '전부 통과'가 '아무것도 안 봄'이 되는 것을 막는다
    assert n_ml >= 14, f"ML 변형이 검사되지 않았다({n_ml}개)"
    assert n_wrap >= 3, f"래퍼가 검사되지 않았다({n_wrap}개)"


def test_wrappers_are_causal_even_when_stacked():
    """래퍼가 래퍼를 감싸도(진화가 실제로 만드는 모양) 인과적이어야 한다."""
    base = {"strategy": "ma_cross", "params": {"fast": 20, "slow": 60}}
    stacked = {"strategy": "stop_wrap",
               "params": {"inner": {"strategy": "event_wrap",
                                    "params": {"inner": {
                                        "strategy": "regime_wrap",
                                        "params": {"inner": base,
                                                   "trend_window": 100}},
                                        "pad_days": 1}},
                          "trail": 0.08}}
    _assert_causal(stacked)


def test_trailing_stop_guard_is_path_dependent_but_deterministic():
    """스톱은 경로 의존이라 벡터화 유혹이 크다 — 같은 입력이면 같은 출력."""
    spec = {"strategy": "stop_wrap",
            "params": {"inner": {"strategy": "ma_cross",
                                 "params": {"fast": 10, "slow": 30}},
                       "trail": 0.05}}
    a = build_strategy(spec).generate_signals(_DF).to_numpy()
    b = build_strategy(spec).generate_signals(_DF).to_numpy()
    assert np.array_equal(a, b, equal_nan=True)
    _assert_causal(spec)


def _peeker_signals(df):
    """다음 봉이 오르면 미리 사는 전략 — 가장 흔한 형태의 룩어헤드(1봉)."""
    import pandas as pd
    nxt = df["close"].shift(-1)
    return pd.Series(np.where(nxt > df["close"], 1.0, 0.0), index=df.index)


def _bad_bars(end: int) -> int:
    a = _peeker_signals(_DF).iloc[:end].to_numpy(dtype=float)
    b = _peeker_signals(_DF.iloc[:_CUT]).iloc[:end].to_numpy(dtype=float)
    return int(np.sum(~np.isclose(a, b, atol=1e-9)))


def test_detector_catches_a_planted_one_bar_leak():
    """탐지기가 살아 있는지 — 일부러 미래를 보는 전략은 반드시 잡혀야 한다.

    오늘 여러 번 '내가 쓴 검사가 통과했는데 결함은 있었다'를 겪었다.
    통과를 안심으로 읽지 않으려면 탐지기 자체를 시험해야 한다.
    """
    assert _bad_bars(_CUT) > 0, "탐지기가 심어 둔 룩어헤드를 놓쳤다"


def test_excluding_the_boundary_bar_hides_a_one_bar_leak():
    """경계 봉을 빼면 shift(-1) 룩어헤드가 **통째로 안 보인다**(감사 57).

    1봉 룩어헤드는 절단된 계열의 마지막 봉 하나만 바꾼다. 비교 구간에서
    그 봉을 빼면 차이가 0이 되어 검사가 초록으로 통과한다. 그리고 1봉이
    가장 흔한 룩어헤드 형태다 — 하필 가장 흔한 것에 눈을 감는 탐지기다.

    이 검사는 그 사실을 못 박아, 누가 다시 경계를 빼면 실패하게 한다.
    """
    assert _bad_bars(_CUT - 1) == 0, "전제가 깨졌다 — 이 테스트를 다시 보라"
    assert _bad_bars(_CUT) > 0


def test_primary_leakage_detector_includes_the_boundary_bar():
    """프로젝트의 1차 룩어헤드 방어선(test_leakage.py)에도 같은 규칙을 요구한다."""
    src = (Path(__file__).resolve().parent / "test_leakage.py").read_text(
        encoding="utf-8")
    body = src.split("def _assert_no_lookahead")[1].split("\ndef ")[0]
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))   # 주석은 설명이다
    assert "_CUT - 1" not in code, (
        "경계 봉을 제외하고 비교하면 1봉 룩어헤드를 놓친다")
    assert "iloc[:_CUT]" in code
