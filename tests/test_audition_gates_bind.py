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
    kw = dict(build=build, confirm_window=120, select_folds=0)

    lenient = nightly_retrain(df, champ, ch, select_t=0.0, confirm_t=0.0, **kw)
    # ⚠️ 결승 문턱도 같이 올린다. 2026-08-14부터 선별 문턱은 결승 문턱을
    #    넘지 못하게 클램프된다(선별기가 검정보다 엄격하면 결승전이 죽는다).
    #    여기서 confirm_t를 0으로 두면 select_t=99가 0으로 깎여 이 검사가
    #    '문턱이 안 걸린다'고 거짓 실패한다.
    strict = nightly_retrain(df, champ, ch, select_t=99.0, confirm_t=99.0, **kw)

    assert lenient["candidates"][0]["swap"], (
        "문턱 0에서도 통과하지 못했다 — 테스트 전제가 깨졌다")
    assert lenient["promoted"]
    assert not strict["candidates"][0]["swap"], (
        "문턱 99에서도 통과했다 — 문턱이 아무것도 거르지 않는다")
    assert not strict["promoted"], "선발전을 못 넘었는데 승격됐다"


def test_default_threshold_is_not_zero():
    """기본 문턱이 0으로 되돌려지면(보정 해제) 잡는다.

    ⚠️ 2026-08-14 이전에는 여기서 select_t ≥ 1.5를 요구했다. 그런데 보정을
    **선발전에** 걸어 둔 것이 애초에 잘못된 자리였다(아래 불변식 검사 참조).
    이제 선발전은 선별기이므로 '0이 아니다'만 요구하고, 다중검정 보정이
    살아 있는지는 결승 문턱(confirm_threshold)으로 확인한다.
    """
    import inspect

    from quant.live.retrain import CONFIRM_T_CAP, confirm_threshold

    sig = inspect.signature(nightly_retrain)
    assert sig.parameters["select_t"].default > 0.0, (
        "선별 문턱이 0이다 — 잡음만으로 이긴 후보가 그대로 결승에 간다")
    assert sig.parameters["confirm_window"].default >= 60
    # 진짜 다중검정 보정은 결승 문턱이 맡는다 — 시도가 쌓이면 올라가야 한다
    assert confirm_threshold(0) >= 1.0
    assert confirm_threshold(50_000) > confirm_threshold(0), (
        "시도 수가 늘어도 결승 문턱이 그대로다 — 다중검정 보정이 해제됐다")
    assert confirm_threshold(10 ** 9) <= CONFIRM_T_CAP


def test_the_screen_can_never_be_stricter_than_the_test_it_feeds():
    """선별기가 검정보다 엄격하면 2단계 관문은 이름만 남는다.

    2026-08-14 실측: 선발 t≥2.45 · 결승 t≥1.03이었고, 스냅샷 15종목에서
    **결승에 도달한 후보가 0개**였다. 결승전(선발전이 보지 못한 구간에서의
    재검증)은 이 설계의 핵심 방어선인데 한 번도 작동한 적이 없었다.
    원인은 같은 다중성을 두 번 센 것 — 선발전과 결승전은 겹치지 않는 구간을
    보므로 그날의 후보 수는 결승전을 부풀리지 않는다.

    이 검사는 '깎였는가'가 아니라 **그 결과 결승전이 실제로 돌았는가**를 본다.
    """
    df = _frame(seed=11)
    ret = df["close"].pct_change().shift(-1).fillna(0.0)
    rng = np.random.default_rng(5)
    weak = pd.Series(np.sign(ret) * (rng.random(len(df)) < 0.56),
                     index=df.index)
    flat = pd.Series(0.0, index=df.index)

    def build(spec):
        return _Fixed(weak if spec.get("params", {}).get("kind") == "weak"
                      else flat)

    champ = {"strategy": "fixed", "params": {"kind": "flat"}}
    ch = [{"strategy": "fixed", "params": {"kind": "weak"}}]
    # 선별 문턱을 결승보다 훨씬 높게 넘긴다 — 클램프가 없으면 여기서 막힌다
    out = nightly_retrain(df, champ, ch, build=build, confirm_window=120,
                          select_folds=0, select_t=99.0, confirm_t=0.5)
    assert out["candidates"][0]["swap"], (
        "선별 문턱 99가 그대로 적용됐다 — 결승전은 영원히 열리지 않는다")
    assert "final" in out, "선발전 1위가 결승전에 도달하지 못했다"

    # 반대 방향: 클램프를 끄면(옛 기록 재현 경로) 옛 규칙이 그대로 살아난다
    old = nightly_retrain(df, champ, ch, build=build, confirm_window=120,
                          select_folds=0, select_t=99.0, confirm_t=0.5,
                          clamp_screen=False)
    assert not old["candidates"][0]["swap"]
    assert "final" not in old, "클램프를 껐는데도 결승전이 열렸다"


def test_an_inert_challenger_is_not_counted_as_a_candidate():
    """챔피언과 신호가 한 봉도 다르지 않은 후보는 후보가 아니라 사본이다.

    실측(2026-08-14, 스냅샷 15종목): 풀링 후보 2개가 **모든 종목에서** 챔피언과
    동일한 신호를 냈다. 스냅샷이 9일치뿐이라 재학습 블록 28개 중 28개가 풀을
    찾지 못했기 때문이다. 매일 백테스트를 두 번 헛돌리고, 후보 수를 부풀려
    다중검정 문턱을 올리고, 오디션 링에는 '그 기능을 시험 중'이라는 인상만
    남겼다 — 아무것도 하지 않으면서 진짜 후보의 승격을 방해했다.
    """
    df = _frame(seed=13)
    flat = pd.Series(0.0, index=df.index)
    live = pd.Series(np.where(np.arange(len(df)) % 3 == 0, 1.0, 0.0),
                     index=df.index)

    def build(spec):
        return _Fixed(live if spec.get("params", {}).get("kind") == "live"
                      else flat)

    champ = {"strategy": "fixed", "params": {"kind": "flat"}}
    ch = [{"strategy": "fixed", "params": {"kind": "clone"}},   # 챔피언과 동일
          {"strategy": "fixed", "params": {"kind": "live"}}]
    out = nightly_retrain(df, champ, ch, build=build, confirm_window=120,
                          select_folds=0, select_t=0.0, confirm_t=0.0)
    kinds = [c["spec"]["params"]["kind"] for c in out["candidates"]]
    assert kinds == ["live"], f"무효 후보가 링에 남아 있다: {kinds}"
    # 조용히 버리지 않는다 — 무엇이 죽어 있었는지 이름을 남긴다
    assert [s["params"]["kind"] for s in out["inert"]] == ["clone"], (
        "무효 후보를 뺐지만 기록을 남기지 않았다 — 죽은 장치가 다시 숨는다")


def test_the_ledger_names_the_inert_candidates():
    """장부만 봐도 '꺼져 있던 기능'이 드러나야 한다."""
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"inert_candidates"' in src, (
        "무효 후보가 장부에 기록되지 않는다 — 감사 127이 그대로 재발한다")
    assert '"gate_version"' in src, (
        "관문 세대 표식이 없다 — verify가 옛 결정을 옛 규칙으로 재현할 수 없다")


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


def test_an_audition_that_compared_nothing_is_not_reported_as_normal():
    """'이긴 후보가 없다'(정상)와 '비교를 못 했다'(고장)는 다른 사건이다.

    실측(2026-08-14): 코인 5종목은 스냅샷이 300봉인데 선발 구간은 180봉이라
    챔피언(학습창 250봉)이 **한 번도 학습하지 못했다**. 후보 19개 중 18개가
    신호 0으로 챔피언과 똑같았는데, 장부에는 "후보 19개 — 챔피언 유지.
    정상입니다"라고 적혔다. 검증하지 못한 것을 검증했다고 말한 것이다.
    """
    df = _frame(seed=17)
    flat = pd.Series(0.0, index=df.index)

    def build(_spec):
        return _Fixed(flat)                    # 모두가 관망 — 대결이 성립 안 함

    champ = {"strategy": "fixed", "params": {"kind": "flat"}}
    ch = [{"strategy": "fixed", "params": {"kind": f"c{i}"}} for i in range(6)]
    out = nightly_retrain(df, champ, ch, build=build, confirm_window=120,
                          select_folds=0, select_t=0.0, confirm_t=0.0)
    assert out["promoted"] is False
    assert out["vacuous"] is True, "대결이 성립하지 않았는데 공회전 표식이 없다"
    assert "정상입니다" not in out["reason"], (
        f"아무것도 비교하지 못한 날을 '정상'이라고 말한다: {out['reason']}")
    assert "평가 불가" in out["reason"]


def test_a_real_audition_is_still_called_normal():
    """반대 방향 — 진짜로 대결이 벌어졌는데 공회전으로 몰지 않는다."""
    df = _frame(seed=19)
    flat = pd.Series(0.0, index=df.index)
    live = pd.Series(np.where(np.arange(len(df)) % 4 == 0, 1.0, 0.0),
                     index=df.index)

    def build(spec):
        return _Fixed(flat if spec["params"]["kind"] == "flat" else live)

    champ = {"strategy": "fixed", "params": {"kind": "flat"}}
    ch = [{"strategy": "fixed", "params": {"kind": f"live{i}"}} for i in range(5)]
    out = nightly_retrain(df, champ, ch, build=build, confirm_window=120,
                          select_folds=0, select_t=99.0, confirm_t=99.0)
    assert out["vacuous"] is False
    assert out["inert"] == []
    assert "정상입니다" in out["reason"]


def test_the_ledger_carries_the_vacuous_flag():
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"vacuous"' in src, (
        "공회전 표식이 장부에 남지 않는다 — 검증 못 한 날과 검증한 날이 "
        "기록상 구별되지 않는다")


def test_a_vacuous_audition_raises_an_alarm(tmp_path, monkeypatch):
    """공회전은 장부에만 남으면 안 된다 — 사람에게 닿아야 한다."""
    from quant.live import flag_watch

    class _Spy:
        def __init__(self): self.sent = []
        def send(self, m): self.sent.append(m)

    spy = _Spy()
    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: spy)
    st = {"retrain_recent": [
        {"asof": "2026-08-13", "key": "crypto:BTC/USDT", "promoted": False,
         "n_candidates": 1, "inert": 18, "vacuous": True},
        {"asof": "2026-08-13", "key": "us_stock:SPY", "promoted": False,
         "n_candidates": 17, "inert": 2, "vacuous": False}]}
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert any(k.startswith("audition_vacuous:") for k in new), (
        "공회전 오디션이 경보로 올라오지 않는다")
    msg = next(m for m in spy.sent if "공회전" in m)
    assert "crypto:BTC/USDT" in msg
    assert "us_stock:SPY" not in msg, "정상 오디션까지 공회전으로 몰았다"


def test_a_normal_audition_does_not_raise_the_vacuous_alarm(tmp_path, monkeypatch):
    """항상 울리는 경보는 꺼진 경보와 같다 — 정상일 때는 조용해야 한다."""
    from quant.live import flag_watch

    class _Spy:
        def __init__(self): self.sent = []
        def send(self, m): self.sent.append(m)

    monkeypatch.setattr("quant.live.notifications.get_notifier", lambda: _Spy())
    st = {"retrain_recent": [
        {"asof": "2026-08-13", "key": "us_stock:SPY", "promoted": False,
         "n_candidates": 17, "inert": 2, "vacuous": False}]}
    new = flag_watch.check_and_notify_flags(st, str(tmp_path))
    assert not any(k.startswith("audition_vacuous:") for k in new)


def test_the_status_feed_carries_the_vacuous_flag():
    """장부 → status → 화면 배선이 끊기면 경보가 영원히 안 켜진다."""
    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"vacuous": bool(rec.get("vacuous"))' in src, (
        "retrain_recent에 공회전 표식이 실리지 않는다")


def test_a_mostly_inert_ring_is_flagged_even_when_one_candidate_survives():
    """후보가 '하나는' 남아도 대다수가 사본이면 그날 대결은 성립하지 않았다.

    실측된 모양이 정확히 이것이다 — 코인 5종목은 후보 19개 중 18개가
    챔피언 사본이고 살아남은 1~2개만 실제로 대결했다. 그런데 장부에는
    "후보 19개 — 챔피언 유지. 정상입니다"로 남았다. 한 명이라도 남았다고
    '정상'이라 부르면, 18명이 유령이었다는 사실이 사라진다.
    """
    df = _frame(seed=23)
    flat = pd.Series(0.0, index=df.index)
    # 챔피언보다 확실히 나쁜 후보 하나 — 살아남되 이기지는 못한다
    ret = df["close"].pct_change().shift(-1).fillna(0.0)
    loser = pd.Series(-np.sign(ret), index=df.index)

    def build(spec):
        return _Fixed(loser if spec["params"]["kind"] == "loser" else flat)

    champ = {"strategy": "fixed", "params": {"kind": "flat"}}
    ch = ([{"strategy": "fixed", "params": {"kind": f"clone{i}"}}
           for i in range(9)]
          + [{"strategy": "fixed", "params": {"kind": "loser"}}])
    out = nightly_retrain(df, champ, ch, build=build, confirm_window=120,
                          select_folds=0, select_t=0.0, confirm_t=0.0)
    assert len(out["candidates"]) == 1 and len(out["inert"]) == 9
    assert out["vacuous"] is True, (
        "후보 10개 중 9개가 사본인데 공회전으로 표시되지 않았다")
    assert "정상입니다" not in out["reason"], out["reason"]
    assert "9개" in out["reason"], (
        f"몇 개가 유령이었는지 근거에 안 적힌다: {out['reason']}")
