"""패널 관문이 **관문을 느슨하게 만들지 않는가** (2026-08-27 사장님 ①안).

■ 왜 이 검사가 이 저장소에서 특별히 중요한가

관문을 넓히는 변경은 **거의 항상 통과율을 올린다.** 그래서 "더 많이
승격됐다"는 결과만 보면 성공처럼 보이는데, 실제로는 과최적화 기계를
만들어 놓고 축하하는 것일 수 있다. 이 제품의 정체성(선택 편향 없는 공개
실험)은 바로 그 지점에서 무너진다.

그래서 이 파일은 "패널이 더 많이 통과시키는가"를 **검사하지 않는다.**
대신 **느슨해지면 안 되는 자리들이 그대로인가**를 검사한다:

  ① 종목마다 부호가 갈리는 설정은 **점수를 못 받는다**(오히려 상쇄된다).
     한 종목에서만 좋아 보이는 것은 대개 잡음이고, 그걸 걸러 내는 것이
     이 관문의 존재 이유다.
  ② 종목 수로 날짜 수를 대신할 수 없다 — 관측 단위는 **날짜**다.
  ③ 판정하지 않은 것(skipped)은 **통과가 아니다**(감사 226).
  ④ 이득의 크기를 **장부에 남긴다** — "패널로 바꿨다"는 선언은 이득의
     증거가 아니다. 분산이 실제로 줄었는지 숫자로 확인할 수 있어야 한다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.live.panel_gate import (MIN_PANEL_DATES, MIN_PANEL_SYMBOLS,
                                   PanelCollector, panel_diff, panel_verdict,
                                   power_gain)

ROOT = Path(__file__).resolve().parent.parent
DATES = pd.date_range("2026-01-01", periods=120, freq="D")


def _series(values) -> pd.Series:
    return pd.Series(values, index=DATES[:len(values)], dtype=float)


def _consistent(n_sym=10, edge=0.002, noise=0.01, seed=0):
    """모든 종목이 **같은 방향**으로 조금씩 이기는 설정."""
    rng = np.random.default_rng(seed)
    return {f"s{i}": _series(edge + rng.normal(0, noise, len(DATES)))
            for i in range(n_sym)}


def _mixed(n_sym=10, edge=0.002, noise=0.01, seed=0):
    """절반은 이기고 절반은 지는 설정 — 종목별로는 그럴듯해 보인다."""
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n_sym):
        sign = 1.0 if i % 2 == 0 else -1.0
        out[f"s{i}"] = _series(sign * edge + rng.normal(0, noise, len(DATES)))
    return out


def test_a_setting_that_helps_everywhere_gets_credit():
    """방향이 일관된 설정은 패널에서 **강해진다** — 그게 이득의 정체다."""
    v = panel_verdict(_consistent(), t_threshold=2.0)
    assert not v["skipped"], v
    assert v["t_stat"] > 2.0, f"일관된 설정인데 패널 t가 낮다: {v}"
    assert v["symbol_win_rate"] == 1.0


def test_a_setting_that_only_helps_some_symbols_does_not():
    """⚠️ 이 검사가 이 파일의 핵심이다.

    종목마다 부호가 갈리는 설정은 횡단 평균에서 **상쇄된다.** 종목 하나만
    떼어 보면 t가 그럴듯하게 나오는데도 패널은 점수를 주지 않는다 —
    "이 종목에서 운이 좋았나"와 "이 설정이 진짜인가"는 다른 질문이다.

    이 성질이 깨지면 패널 관문은 **표본만 부풀린 느슨한 관문**이 된다.
    """
    mixed = _mixed()
    v = panel_verdict(mixed, t_threshold=2.0)
    assert not v["skipped"], v
    assert abs(v["t_stat"]) < 2.0, (
        f"부호가 갈리는 설정이 패널을 통과했다: {v} — 패널이 잡음을 "
        "증폭하고 있다")
    # 대조군: 종목 하나만 보면 그럴듯하다(그래서 지금 관문이 속을 수 있다)
    one = mixed["s0"]
    t_one = float(one.mean() / (one.std(ddof=1) / np.sqrt(len(one))))
    assert t_one > 1.0, "표본 구성이 잘못됐다 — 단일 종목도 안 그럴듯하다"


def test_symbols_cannot_substitute_for_dates():
    """관측 단위는 **날짜**다 — 종목을 아무리 늘려도 날짜가 짧으면 판정 안 한다.

    이걸 안 지키면 "40종목 × 63봉 = 2,500 표본"이라는 거짓 셈이 그대로
    관문에 들어온다. 같은 날 종목들은 함께 움직이므로 독립 표본이 아니다.
    """
    short = {f"s{i}": _series(np.full(MIN_PANEL_DATES - 1, 0.01))
             for i in range(50)}          # 종목은 50개, 날짜는 모자람
    v = panel_verdict(short, t_threshold=2.0)
    assert v["skipped"], f"날짜가 모자란데 판정했다: {v}"
    assert "날짜" in v["reason"]


def test_one_symbol_is_not_a_panel():
    """종목 하나짜리 평균을 '패널'이라 부르면 기록이 거짓말을 한다."""
    v = panel_verdict({"s0": _series(np.full(120, 0.01))}, t_threshold=2.0)
    assert v["skipped"], v
    assert "종목" in v["reason"]


def test_skipping_is_not_passing():
    """대조군 — 판정하지 않은 것을 '통과'로 읽으면 안 된다 (감사 226).

    이 검사가 없으면 "표본이 모자라 건너뜀"이 조용히 승격으로 이어질 수 있다.
    """
    for bad in ({"s0": _series(np.full(120, 0.01))},                 # 종목 부족
                {f"s{i}": _series(np.full(5, 0.01)) for i in range(9)}):  # 날짜 부족
        v = panel_verdict(bad, t_threshold=2.0)
        assert v["skipped"] is True
        assert "pass" not in v, (
            f"건너뛴 판정에 pass 필드가 있다 — 통과로 읽힐 수 있다: {v}")


def test_a_thin_day_does_not_speak_for_the_whole_panel():
    """참여 종목이 적은 날은 버린다 — 그날 잡음이 통째로 들어오기 때문이다."""
    data = {f"s{i}": _series(np.full(120, 0.001)) for i in range(MIN_PANEL_SYMBOLS)}
    # 마지막 날만 한 종목 빼고 전부 결측 + 그 하나가 큰 값
    for i in range(1, MIN_PANEL_SYMBOLS):
        data[f"s{i}"] = data[f"s{i}"].copy()
        data[f"s{i}"].iloc[-1] = np.nan
    data["s0"] = data["s0"].copy()
    data["s0"].iloc[-1] = 99.0
    folded = panel_diff(data)
    assert DATES[119] not in folded.index, (
        "한 종목만 남은 날이 패널 평균에 들어왔다 — 그날 잡음이 통계를 흔든다")
    assert folded.max() < 1.0, "얇은 날의 극단값이 남아 있다"


def test_the_gain_is_recorded_as_a_number_not_a_claim():
    """이득의 크기를 장부에 남긴다 — 선언이 아니라 측정.

    ⚠️ 관문을 바꿨는데 이득이 없거나 과하게 느슨해졌다면 그 사실이 숫자로
       보여야 한다. 안 보이면 다음 사람은 '패널로 바꿨으니 좋아졌겠지'로
       읽는다.
    """
    g = power_gain(_consistent(n_sym=16, noise=0.01))
    assert not g["skipped"], g
    assert g["variance_gain"] > 1.0, "패널로 접었는데 분산이 안 줄었다"
    assert g["variance_gain"] <= g["if_independent"] * 1.35, (
        f"분산 감소가 종목 수(완전 독립 상한)를 크게 넘었다: {g} — "
        "표본을 거짓으로 부풀리고 있다")
    assert g["t_gain"] == pytest.approx(g["variance_gain"] ** 0.5, rel=1e-6)


def test_perfectly_correlated_symbols_give_no_free_lunch():
    """대조군 — 종목들이 완전히 같이 움직이면 이득이 **없어야** 한다.

    이게 깨지면 상관을 무시하고 표본을 세고 있다는 뜻이고, 그건 관문을
    푸는 게 아니라 망가뜨리는 것이다.
    """
    rng = np.random.default_rng(7)
    common = rng.normal(0, 0.01, len(DATES))
    same = {f"s{i}": _series(common) for i in range(12)}   # 전부 동일 계열
    g = power_gain(same)
    assert not g["skipped"], g
    assert g["variance_gain"] == pytest.approx(1.0, rel=1e-6), (
        f"완전히 같이 움직이는 종목들인데 분산이 줄었다: {g}")


# ── 종목을 가로질러 **무엇을 묶어도 되는가** ─────────────────────────

def test_only_the_same_setting_is_pooled_across_symbols():
    """⚠️ 서로 다른 설정을 한 통에 담으면 그 평균은 아무 뜻도 없다.

    ``mutate_champion()``의 변형은 그 종목 챔피언 주변에서 나오므로 종목마다
    다르다. 그것들을 묶으면 "같은 설정이 여러 종목에서 좋았다"가 아니라
    **서로 다른 설정들의 평균**이 되는데, 그 숫자로 승격을 결정하면 아무도
    시험하지 않은 설정이 챔피언이 된다.
    """
    rng = np.random.default_rng(3)
    col = PanelCollector()
    shared = '{"model":"gb"}'
    for i in range(8):
        col.add(f"sym{i}", {
            shared: _series(0.002 + rng.normal(0, 0.01, len(DATES))),
            f"mut{i}": _series(rng.normal(0, 0.01, len(DATES))),   # 종목 고유
        })
    verdicts = {v["spec_key"]: v for v in col.verdicts(t_threshold=2.0)}
    assert not verdicts[shared]["skipped"], "여러 종목에 선 공통 설정이 판정 안 됐다"
    assert verdicts[shared]["n_symbols"] == 8
    for i in range(8):
        assert verdicts[f"mut{i}"]["skipped"], (
            f"종목 하나에만 선 변형(mut{i})이 패널 판정을 받았다 — 서로 다른 "
            "설정을 묶으면 아무도 시험하지 않은 설정이 챔피언이 된다")


def test_the_collector_does_not_decide_only_measures():
    """재는 자와 정하는 자를 나눈다 — 수집기는 문턱을 스스로 정하지 않는다.

    다중검정 보정은 **설정 개수**에 걸어야 하는데(종목 수가 아니라), 그
    보정을 어디서 거는지가 흐려지면 두 곳에서 서로 다르게 걸린다.
    """
    src = (ROOT / "quant" / "live" / "panel_gate.py").read_text("utf-8")
    body = src[src.index("def verdicts("):]
    body = body[:body.index("\n\n") if "\n\n" in body else len(body)]
    assert "confirm_threshold" not in body, (
        "수집기가 문턱을 스스로 계산한다 — 보정이 두 곳에서 걸리면 갈라진다")
    # ⚠️ 상수 계열은 쓰지 않는다 — 분산이 0이면 코드가 degenerate로 보고
    #    t=0을 돌려주므로(감사 146·149·159) 문턱을 시험할 수 없다.
    rng = np.random.default_rng(11)
    col = PanelCollector()
    for i in range(6):
        col.add(f"s{i}", {"cfg": _series(0.002 + rng.normal(0, 0.005, len(DATES)))})
    strict = col.verdicts(t_threshold=99.0)[0]
    loose = col.verdicts(t_threshold=0.0)[0]
    assert strict["t_stat"] == loose["t_stat"], "문턱이 통계량을 바꿨다"
    assert strict["pass"] is False and loose["pass"] is True


def test_the_gain_rides_along_with_every_verdict():
    """판정에는 **이득의 크기**가 함께 실린다 — 나중에 검증할 수 있어야 한다.

    사장님 ①안의 조건: "관문을 바꿔서 결과가 달라진 건가"를 뒤에 확인할 수
    있어야 한다. 판정만 남기고 이득을 안 남기면 그 확인이 불가능하다.
    """
    col = PanelCollector()
    rng = np.random.default_rng(5)
    for i in range(9):
        col.add(f"s{i}", {"cfg": _series(0.001 + rng.normal(0, 0.01, len(DATES)))})
    v = col.verdicts(t_threshold=2.0)[0]
    assert "gain" in v and not v["gain"]["skipped"], f"이득이 안 실렸다: {v}"
    assert v["gain"]["variance_gain"] > 1.0


# ── 못 잰 것을 통과로 읽지 않는다 (2026-08-27 변이 시험이 잡아낸 구멍) ──

def test_a_reality_check_that_could_not_run_blocks_promotion():
    """⚠️ 동시검정을 **재려다 실패한 것**은 '생략'이 아니다.

    발견 경위: 패널 관문을 붙이며 홀드아웃 차이 계산을 한 곳으로 모았는데,
    그 함수가 빈 결과를 돌려주도록 망가뜨려도 **아무 검사가 죽지 않았다**
    (변이 시험 놓침 1). 코드를 따라가 보니 행렬이 None이면 동시검정이
    '표본 부족'으로 흘러 생략되고, 그대로 **승격이 통과**했다.

    그 관문은 지금까지 결승을 이긴 20건 중 **19건**을 막아 온 자리다. 즉
    계산 한 줄이 고장 나면 가장 센 관문이 조용히 사라지는 경로였다.

    건너뜀에는 두 종류가 있다:
      · 홀드아웃이 짧다 → 잴 수 없는 것이 **사실**이다. 생략하고 기록한다.
      · 후보가 있는데 행렬이 비었다 → **고장**이다. 승격시키지 않는다.
    """
    import pandas as _pd

    from quant.live import retrain as R

    idx = _pd.date_range("2026-01-01", periods=400, freq="D")
    rng = np.random.default_rng(0)
    close = _pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))),
                       index=idx)
    df = _pd.DataFrame({"open": close, "high": close * 1.01,
                        "low": close * 0.99, "close": close,
                        "volume": 1_000.0}, index=idx)

    champ = {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}}
    chals = [{"strategy": "ma_cross", "params": {"fast": f, "slow": 20}}
             for f in (3, 4, 6, 7, 8)]

    real = R.holdout_diffs
    try:
        R.holdout_diffs = lambda *a, **k: {}          # 계산이 고장 난 상태
        out = R.nightly_retrain(df, champ, chals, confirm_window=120,
                                select_t=0.0, confirm_t=-99.0, min_obs=1)
    finally:
        R.holdout_diffs = real

    assert out["promoted"] is False, (
        "동시검정을 못 쟀는데 승격됐다 — 관문이 조용히 사라지는 경로다: "
        f"{out.get('reason')}")
    rc = out.get("reality_check") or {}
    assert rc.get("broken"), (
        "'재려다 실패'가 '표본 부족 생략'과 구별되지 않는다 — 장부만 보면 "
        f"정상적으로 생략한 밤과 똑같아 보인다: {rc}")


def test_the_reality_check_actually_runs_on_a_normal_night():
    """대조군 — 정상 경로에서 동시검정이 **실제로 계산되는가**.

    ⚠️ 위 검사만으로는 부족했다(변이 시험 실측). 그 검사는 계산을 스스로
       고장 낸 뒤 결과를 보므로, 계산이 **원래부터** 고장 나 있어도 똑같이
       통과한다. 고장을 넣어 보는 검사에는 **고장이 없을 때를 보는 짝**이
       반드시 있어야 한다.
    """
    import pandas as _pd

    from quant.live import retrain as R

    idx = _pd.date_range("2026-01-01", periods=400, freq="D")
    rng = np.random.default_rng(1)
    close = _pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))),
                       index=idx)
    df = _pd.DataFrame({"open": close, "high": close * 1.01,
                        "low": close * 0.99, "close": close,
                        "volume": 1_000.0}, index=idx)
    champ = {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}}
    chals = [{"strategy": "ma_cross", "params": {"fast": f, "slow": 20}}
             for f in (3, 4, 6, 7, 8)]

    diffs = R.holdout_diffs(champ, chals, df, 120, R.build_strategy, {})
    assert diffs, "정상 데이터인데 홀드아웃 차이가 하나도 안 나왔다"
    assert len(diffs) == len(chals), (
        f"후보 {len(chals)}개인데 차이 계열이 {len(diffs)}개다")
    for series in diffs.values():
        assert len(series) > 0 and series.index.is_monotonic_increasing, (
            "차이 계열에 날짜 색인이 없다 — 패널이 종목을 가로질러 같은 날끼리 "
            "묶을 수 없다")

    mat = R._holdout_diff_matrix(champ, chals, df, 120, R.build_strategy, {})
    assert mat is not None and mat.shape[1] == len(chals), (
        "동시검정 행렬이 비었다 — 승격 20건 중 19건을 막아 온 관문이 "
        "조용히 사라진다")

