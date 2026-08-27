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



# ── 배선 — 재료가 실제로 모이는가, 그리고 아직 판정에 손대지 않는가 ──────

def _price_frame(seed: int, n: int = 400):
    import pandas as _pd

    idx = _pd.date_range("2026-01-01", periods=n, freq="D")
    rng = np.random.default_rng(seed)
    close = _pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                       index=idx)
    return _pd.DataFrame({"open": close, "high": close * 1.01,
                          "low": close * 0.99, "close": close,
                          "volume": 1_000.0}, index=idx)


_CHAMP = {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}}
_CHALS = [{"strategy": "ma_cross", "params": {"fast": f, "slow": 20}}
          for f in (3, 6, 9)]


def test_the_material_is_collected_on_ordinary_nights_not_only_finals():
    """⚠️ 재료를 **결승에 간 밤에만** 주우면 패널은 영원히 안 찬다.

    동시검정용 홀드아웃 계산은 결승까지 간 밤에만 돈다. 그런데 장부 실측으로
    시행 11,721회 중 결승은 186회뿐이다 — 그 자리에서 재료를 주우면 대부분의
    밤에 아무것도 안 모이고, 패널은 최소 종목 수(5)를 몇 달이 지나도 못
    채운다. **판정이 어떻게 끝났든** 재료는 모여야 한다.
    """
    from quant.live import retrain as R

    df = _price_frame(2)
    # 결승에 아무도 못 가도록 문턱을 아주 높게 — 승격은 확실히 없다.
    out = R.nightly_retrain(df, _CHAMP, _CHALS, panel_specs=_CHALS,
                            confirm_window=120, select_t=99.0, confirm_t=99.0,
                            min_obs=1)
    assert out["promoted"] is False, "이 검사는 승격이 없는 밤을 본다"
    diffs = out.get("panel_diffs")
    assert diffs, ("아무도 결승에 못 간 밤에 패널 재료가 하나도 안 모였다 — "
                   "이러면 패널은 최소 종목 수를 영원히 못 채운다")
    for series in diffs.values():
        assert isinstance(series.index, pd.DatetimeIndex), (
            "패널 재료에 날짜가 없다 — 종목을 가로질러 같은 날끼리 묶을 수 없다")


def test_asking_for_no_panel_costs_nothing():
    """대조군 — ``panel_specs``를 안 넘기면 **추가 계산이 아예 없다**.

    위 검사만 있으면 "언제나 재료를 만든다"도 초록이다. 그런데 그 계산은
    후보를 홀드아웃에서 한 번 더 재생하는 일이고, 밤 배치는 시간 예산 안에서
    도는 이어달리기다 — 한 종목이 느려지면 그만큼 다른 종목이 오늘 밤 못
    돈다. 재현 검증(verify)도 이 비용을 낼 이유가 없다.
    """
    from quant.live import retrain as R

    out = R.nightly_retrain(_price_frame(3), _CHAMP, _CHALS,
                            confirm_window=120, select_t=99.0, confirm_t=99.0,
                            min_obs=1)
    assert "panel_diffs" not in out, (
        "패널을 요청하지 않았는데 재료를 만들었다 — 아무도 안 쓰는 계산에 "
        "밤 배치의 시간 예산을 쓴다")


def test_the_panel_does_not_yet_decide_who_gets_promoted():
    """⚠️ 지금 단계에서 패널은 **관측이지 관문이 아니다**(사장님 ①안).

    조건이 "관문을 바꾸되 기존 관문도 계속 기록한다"이므로, 먼저 두 관문이
    같은 밤에 각각 뭐라고 하는지를 쌓는다. 그 대조 없이 갈아 끼우면 나중에
    성적이 변했을 때 **관문 때문인지 시장 때문인지 구별할 수 없다.**

    그래서 재료를 모으든 안 모으든 승격 결정은 **한 글자도 달라지지 않아야
    한다.** 달라진다면 그건 조용히 관문이 바뀐 것이고, 이 저장소에서 가장
    하지 말아야 할 종류의 변경이다.
    """
    from quant.live import retrain as R

    df = _price_frame(4)
    kw = dict(confirm_window=120, select_t=0.0, confirm_t=-99.0, min_obs=1)
    without = R.nightly_retrain(df, _CHAMP, _CHALS, **kw)
    with_panel = R.nightly_retrain(df, _CHAMP, _CHALS, panel_specs=_CHALS, **kw)
    assert without["promoted"] == with_panel["promoted"], (
        "패널 재료를 모았다는 이유만으로 승격 결정이 달라졌다 — "
        "관측이 관문으로 조용히 승격됐다")
    assert without["reason"] == with_panel["reason"], (
        "같은 밤인데 근거 문장이 다르다 — 판정 경로가 갈렸다는 뜻이다")


def test_every_panel_spec_means_the_same_thing_on_every_symbol():
    """패널에 서는 설정은 **종목이 달라도 글자 그대로 같아야** 한다.

    ⚠️ 실제 스냅샷 32종목 연기시험이 잡아낸 결함이다(2026-08-27). 고정 격자의
       ML 항목은 ``{"model": "gb", "threshold": 0.55}`` 같은 **덧씌우기 형태**
       이고, 오디션은 그것을 **그 종목 챔피언의 파라미터 위에** 얹어 해석한다.
       챔피언은 종목마다 다르므로 같은 한 줄이 종목마다 다른 설정을 뜻한다 —
       그걸 한 통에 담으면 "같은 설정이 여러 종목에서 좋았다"가 아니라 서로
       다른 설정들의 평균이 되고, 아무 뜻도 없는 숫자가 된다.

       게다가 덧씌우기 형태는 그 자체로 전략을 만들 수 없어서(``strategy``
       키가 없다) 홀드아웃 재생이 **종목마다 조용히 실패**했다. 경고만 쌓이고
       판정은 계속 돌았다.
    """
    from quant.live.retrain import build_strategy, shared_panel_specs

    specs = shared_panel_specs()
    assert len(specs) >= 5, f"패널에 세울 설정이 너무 적다: {len(specs)}"
    for spec in specs:
        assert "strategy" in spec and "params" in spec, (
            f"덧씌우기 형태가 패널에 섞였다: {spec} — 이건 종목마다 다른 "
            "설정을 뜻하고, 그 자체로는 전략을 만들 수도 없다")
        build_strategy(spec)          # 못 만들면 여기서 죽는다(조용한 실패 금지)


def test_the_panel_roster_depends_on_the_date_and_nothing_else():
    """패널 명단은 **날짜로만** 갈린다 — 종목으로는 절대 갈리지 않는다.

    그날 밤 모든 종목이 **같은 부분집합**을 돌아야 한 통에 담을 수 있다.
    종목별로 다르게 뽑으면 설정마다 참여 종목이 한둘로 쪼개져 패널이 영원히
    최소 종목 수를 못 채운다 — **비용만 쓰고 아무것도 못 재는 상태**가 된다.
    """
    import inspect

    from quant.live.retrain import shared_panel_specs, spec_key

    params = set(inspect.signature(shared_panel_specs).parameters)
    assert params <= {"asof"}, (
        f"패널 명단이 날짜 말고 다른 것에 의존한다: {params} — 종목마다 다른 "
        "명단이 될 수 있는 문이 열려 있다")
    a = [spec_key(s) for s in shared_panel_specs("2026-08-27")]
    b = [spec_key(s) for s in shared_panel_specs("2026-08-27")]
    assert a == b, "같은 날인데 명단이 달랐다 — 종목을 가로질러 묶을 수 없다"
    assert len(set(a)) == len(a), f"명단에 중복이 있다: {a}"


def test_the_nightly_roster_is_capped_so_the_relay_still_finishes():
    """⚠️ 하룻밤 명단에 **상한**이 있다 — 없으면 오디션이 절반만 돈다.

    실측(2026-08-27, 한국주식 6종목): 명단 전체(28개)를 매일 재면 종목당
    시간이 오디션 69.8초 → 145.7초로 **+109%**가 된다. 시간 예산 1800초
    기준으로 하룻밤에 도는 종목이 **26 → 12**로 반토막 난다. 그러면 각
    종목의 오디션 주기가 1.5일에서 3일로 늘어나는데 **화면에는 아무
    빨간불도 안 뜬다** — 커서에 '못 돈 종목'이 조금 늘 뿐이다.

    이 저장소가 반복해서 막아 온 종류의 조용한 퇴행이라, 상한을 검사로
    못 박는다.
    """
    from quant.live.retrain import (PANEL_ROSTER_PER_NIGHT, panel_roster,
                                    shared_panel_specs)

    assert len(shared_panel_specs("2026-08-27")) == PANEL_ROSTER_PER_NIGHT, (
        "하룻밤 명단이 상한을 안 지킨다")
    assert PANEL_ROSTER_PER_NIGHT * 4 <= len(panel_roster()) * 2, (
        f"하룻밤 명단({PANEL_ROSTER_PER_NIGHT})이 전체({len(panel_roster())})에 "
        "비해 너무 크다 — 회전의 뜻이 없어지고 밤 배치가 느려진다")


def test_the_roster_rotates_so_every_setting_eventually_gets_measured():
    """대조군 — 상한을 뒀는데 **같은 6개만 매일** 돌면 나머지는 영영 안 잰다.

    상한 검사만 있으면 "명단 = 앞에서 6개 고정"도 초록이다. 그러면 22개
    설정은 한 번도 패널에 못 서고, 그 사실은 어디에도 안 드러난다.
    """
    from quant.live.retrain import panel_roster, shared_panel_specs, spec_key

    seen = set()
    for day in range(1, 15):
        seen |= {spec_key(s) for s in shared_panel_specs(f"2026-09-{day:02d}")}
    total = len(panel_roster())
    assert len(seen) >= total * 0.7, (
        f"2주를 돌려도 명단 {total}개 중 {len(seen)}개만 패널에 섰다 — "
        "회전이 안 돌고 같은 설정만 반복해서 재고 있다")


def test_the_ledger_line_is_plain_json_and_says_how_many_symbols_stood(tmp_path):
    """장부 한 줄은 **그대로 JSON**이어야 하고, 실제 종목 수를 적어야 한다.

    ⚠️ 이어달리기 때문에 하룻밤에 전 종목을 못 돈다(시간 예산). "40종목
       패널"이라고 적어 두고 실제로는 12종목이면, 그건 이 저장소가 반복해서
       막아 온 종류의 거짓말이다. 그리고 pandas 객체가 섞이면 그 줄은 아예
       안 써지고 밤마다 조용히 사라진다.
    """
    import json as _json

    from quant.live.retrain import PANEL_FILE, record_panel

    coll = PanelCollector()
    for i in range(7):
        coll.add(f"us_stock:S{i}", {"spec-A": _series(
            0.002 + np.random.default_rng(i).normal(0, 0.01, len(DATES)))})
    rec = record_panel("2026-08-27", coll, str(tmp_path))

    line = (tmp_path / PANEL_FILE).read_text("utf-8").strip()
    assert _json.loads(line) == _json.loads(_json.dumps(rec, ensure_ascii=False)), (
        "장부 줄이 반환값과 다르다 — 화면과 장부가 갈라진다")
    assert rec["specs"][0]["n_symbols"] == 7, (
        f"패널에 실제로 선 종목 수가 장부와 다르다: {rec['specs'][0]}")
    assert rec["specs"][0]["n_dates"] == len(DATES)


def test_a_thin_panel_is_recorded_as_skipped_not_as_a_pass(tmp_path):
    """종목이 모자란 밤은 **판정하지 않았다**고 적힌다 — 통과가 아니다.

    감사 226의 규칙(건너뜀은 통과가 아니다)이 새 장부에서도 지켜지는지 본다.
    """
    from quant.live.retrain import record_panel

    coll = PanelCollector()
    for i in range(MIN_PANEL_SYMBOLS - 1):          # 최소 종목 수에 하나 모자람
        coll.add(f"us_stock:S{i}", {"spec-A": _series(
            np.random.default_rng(i).normal(0, 0.01, len(DATES)))})
    rec = record_panel("2026-08-27", coll, str(tmp_path))

    assert rec["n_specs_judged"] == 0, "종목이 모자란데 판정했다"
    assert rec["skipped"], "못 잰 사실이 장부에 안 남는다"
    assert not rec["specs"], "판정 못 한 설정이 판정 목록에 들어갔다"
    assert rec["reality_check"].get("skipped"), (
        "패널 표가 비었는데 동시검정이 '통과'로 남았다")


def test_the_panel_multiple_testing_counts_settings_not_symbols(tmp_path):
    """다중검정은 **설정 개수**를 센다 — 종목 수가 아니다.

    한 설정을 40종목에 돌리는 것은 40번의 시도가 아니라 한 번의 시도를
    정밀하게 재는 것이다. 종목 수를 시도 수로 세면 관문이 거짓으로 빡빡해지고
    (아무것도 승격 못 함), 반대로 설정 수를 안 세면 거짓으로 열린다.

    ⚠️ **대조 방법이 까다롭다.** 후보를 늘린 두 밤의 p를 그냥 비교하면 안
       된다 — 서로 다른 난수에서 나온 최고 성적을 비교하는 것이라 어느
       방향으로든 나올 수 있다(첫 시도에서 실제로 반대로 나왔다). 이기는
       설정은 **똑같이 고정**해 두고, 그 옆에 잡음 설정만 더 세운다.
       그러면 관측된 최고 t는 그대로인데 귀무 세계의 최고 t만 커지므로,
       보정이 살아 있다면 p는 **반드시** 오른다.
    """
    from quant.live.retrain import record_panel

    def _coll(n_noise: int) -> PanelCollector:
        c = PanelCollector()
        for i in range(8):
            # 이기는 설정 — 종목 시드를 고정해 두 판에서 **완전히 같다**.
            rng = np.random.default_rng(1000 + i)
            specs = {"winner": _series(0.0012 + rng.normal(0, 0.01, len(DATES)))}
            for j in range(n_noise):                   # 옆에 세우는 잡음 설정
                nr = np.random.default_rng(50_000 + 100 * j + i)
                specs[f"noise-{j}"] = _series(nr.normal(0, 0.01, len(DATES)))
            c.add(f"us_stock:S{i}", specs)
        return c

    alone = record_panel("2026-08-27", _coll(0), str(tmp_path))
    crowded = record_panel("2026-08-27", _coll(11), str(tmp_path))

    assert alone["reality_check"]["n_cand"] == 1
    assert crowded["reality_check"]["n_cand"] == 12, (
        "동시검정이 세는 것이 설정 개수가 아니다 — 패널의 다중검정 보정이 "
        "엉뚱한 것을 세고 있다")

    # 이기는 설정의 관측 성적은 두 판에서 같다 — 달라진 것은 옆에 선 수뿐.
    def _t(rec):
        return next(x["t_stat"] for x in rec["specs"] if x["spec_key"] == "winner")

    assert _t(alone) == pytest.approx(_t(crowded)), (
        "대조가 성립하지 않는다 — 이기는 설정의 성적이 두 판에서 다르다")
    assert (alone["reality_check"]["t_max"]
            == pytest.approx(crowded["reality_check"]["t_max"])), (
        "대조가 성립하지 않는다 — 관측된 최고 성적이 두 판에서 다르면 p의 "
        "차이가 보정 때문인지 잡음 때문인지 구별할 수 없다")
    assert crowded["reality_check"]["p"] > alone["reality_check"]["p"], (
        "같은 성적인데 옆에 선 설정을 11개 더 세워도 '우연일 확률'이 그대로다 "
        f"({alone['reality_check']['p']} → {crowded['reality_check']['p']}) — "
        "설정을 많이 세울수록 하나쯤 우연히 좋아 보인다는 사실이 반영되지 않는다")


def test_the_material_never_leaks_into_the_nightly_ledger():
    """패널 재료(pandas 객체)가 **재학습 장부에 실리지 않는다.**

    장부는 필드를 하나씩 골라 쓰므로 지금은 새지 않는다. 하지만 나중에
    누군가 편하게 ``**decision``으로 펼치면 그날부터 장부 줄이 통째로
    **안 써진다**(JSON 직렬화 실패). 밤 배치는 그 예외를 삼키도록 돼 있어
    화면은 조용하고, 며칠 뒤에야 "장부가 비었다"로 발견된다.

    그래서 장부에 적는 필드 목록을 계약으로 못 박는다.
    """
    import re as _re

    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    body = src[src.index("def run_retrain("):]
    call = body[body.index("append_history({"):]
    call = call[:call.index("\n    }, state_dir)")]
    keys = set(_re.findall(r'^\s{8}"([a-z_0-9]+)":', call, _re.M))
    assert "asof" in keys, "장부 필드를 못 읽었다 — 이 검사가 헛돈다"
    assert "panel_diffs" not in keys, (
        "패널 재료가 재학습 장부 필드에 들어갔다 — pandas 객체라 그날부터 "
        "장부 줄이 통째로 안 써진다")
    assert "**decision" not in call, (
        "판정 결과를 통째로 장부에 펼쳤다 — 앞으로 결정 dict에 무엇이 "
        "붙든 장부로 새어 나간다")


def test_the_nightly_batch_asks_for_the_roster_by_date_not_by_symbol():
    """밤 배치가 명단을 **날짜로** 요청한다 — 종목 열쇠로 요청하지 않는다.

    ⚠️ 이 한 글자가 패널 전체를 무력화한다. ``shared_panel_specs(key)``라고
       쓰면 함수는 정상적으로 6개를 돌려주고 계산도 정상적으로 돌지만,
       종목마다 **다른 6개**가 나온다. 그러면 설정마다 참여 종목이 한둘로
       쪼개져 최소 종목 수(5)를 영원히 못 채운다 — **비용은 그대로 다 쓰고
       패널은 매일 아무것도 안 재는** 상태가 되는데, 장부에는 그냥
       "판정 0/6"이 찍힐 뿐이라 고장처럼 보이지 않는다.

    호출 한 줄을 계약으로 못 박는다(변이 시험이 이 자리를 놓쳤다).
    """
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    body = src[src.index("def run_retrain("):]
    call = body[body.index("shared_panel_specs("):]
    arg = call[len("shared_panel_specs("):call.index(")")].strip()
    assert arg == "asof", (
        f"밤 배치가 패널 명단을 '{arg}'로 요청한다 — 날짜(asof)가 아니면 "
        "종목마다 다른 명단이 되고, 패널은 비용만 쓰고 아무것도 못 잰다")


# ── 침묵을 없앤다 — 못 잰 밤도 장부에 남는다 ───────────────────────────

def test_a_night_that_measured_nothing_still_leaves_a_line(tmp_path):
    """⚠️ 재료가 하나도 안 모인 밤에도 **줄을 남긴다**.

    예전에는 재료가 0이면 장부에 아무것도 안 적혔다. 그러면 장부에서
    "패널이 아무것도 못 쟀다"(고장)와 "밤 배치가 아예 안 돌았다"(다른
    경보가 맡는 사건)가 **똑같이 보인다** — 줄이 없다는 사실만 남는다.
    구별할 방법이 없으면 둘 다 늦게 발견되고, 그동안 패널은 매일 비용을
    쓰면서 아무것도 안 잰다.

    없는 줄은 침묵이고, 침묵은 이 저장소에서 가장 비싼 실패다.
    """
    import json as _json

    from quant.live.retrain import PANEL_FILE, record_panel

    rec = record_panel("2026-08-27", PanelCollector(), str(tmp_path),
                       n_symbols_seen=12)
    line = (tmp_path / PANEL_FILE).read_text("utf-8").strip()
    assert line, "재료가 0인 밤에 장부 줄이 아예 안 써졌다"
    assert _json.loads(line)["n_specs_judged"] == 0
    assert rec["n_symbols_seen"] == 12, (
        "그날 오디션을 연 종목 수가 장부에 없다 — '배치가 안 돌았다'와 "
        "'돌았는데 못 쟀다'를 구별할 수 없다")


def test_the_batch_records_the_panel_even_when_it_collected_nothing():
    """대조군 — 밤 배치가 그 기록을 **조건 없이** 부른다(호출 한 줄 계약).

    위 검사는 함수만 본다. 배치 쪽에서 `if panel.specs:`로 다시 감싸면
    함수는 멀쩡한데 그 밤은 여전히 아무 줄도 안 남는다.
    """
    src = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    body = src[src.index("def run_retrain_all("):]
    between = body[body.index("panel_rec = None"):body.index("record_panel(")]
    code = [ln.strip() for ln in between.splitlines()[1:]
            if ln.strip() and not ln.strip().startswith("#")]
    # 기록 호출까지 가는 길에 서 있어도 되는 것은 try: 와 대입 시작뿐이다.
    allowed = {"try:", "panel_rec ="}   # 마지막 줄은 호출 직전에서 잘린 대입
    intruders = [ln for ln in code if ln not in allowed]
    assert not intruders, (
        f"패널 기록 앞에 조건이 끼어 있다: {intruders} — 못 잰 밤이 장부에서 "
        "'배치가 안 돈 밤'과 구별되지 않는다")


def test_the_panel_roster_includes_the_hypothesis_rules():
    """가설 규칙들이 패널 명단에 **들어 있다**.

    패널은 "한 설정이 여러 종목에서 **함께** 도움이 되는가"를 묻는 장치다.
    가설 규칙 여섯 개(월말 수급·PEAD·만기 주간·FOMC 표류·펀딩 과열 회피·
    월말 강제 리밸런싱)는 파라미터까지 전 종목이 동일해서, 그 질문에 가장
    잘 어울리는 후보들이다. 처음에는 고정 격자만 봐서 이들이 명단 밖에
    있었다 — 정작 재야 할 것을 안 재고 있었던 셈이다.
    """
    from quant.live.retrain import panel_roster

    names = {s["strategy"] for s in panel_roster()}
    for rule in ("turn_of_month", "pead", "expiry_week", "fomc_drift",
                 "funding_guard", "rebalance_flow"):
        assert rule in names, f"가설 규칙이 패널 명단에 없다: {rule}"


def test_one_list_feeds_both_the_ring_and_the_panel():
    """링과 패널이 **같은 출처**를 본다 — 두 곳에 적으면 언젠가 갈라진다.

    갈라지면 한쪽에만 있는 후보가 생기고, 그 후보는 조용히 측정에서
    빠진다(FROZEN_IDEAS ①의 재발 방지).
    """
    from quant.live.retrain import (FIXED_CHALLENGERS, build_challengers,
                                    panel_roster, spec_key)

    champ = {"strategy": "ml", "params": {"model": "logreg"}}
    ring = {spec_key({"strategy": c["strategy"],
                      "params": dict(c.get("params", {}))})
            for c in build_challengers(champ, seed="2026-08-27:us:AAPL",
                                       evolve=False) if "strategy" in c}
    roster = {spec_key(s) for s in panel_roster()}
    missing = [spec_key(c) for c in FIXED_CHALLENGERS
               if spec_key({"strategy": c["strategy"],
                            "params": dict(c.get("params", {}))}) not in roster]
    assert not missing, f"링에는 서는데 패널 명단에 없는 고정 후보: {missing}"
    assert len(ring & roster) >= len(FIXED_CHALLENGERS), (
        "링과 패널 명단이 갈라졌다 — 같은 목록을 봐야 한다")
