"""의회에 문이 **하나뿐**이라 20계좌가 전부 1석이었다 (감사 276).

사장님 2026-08-17: *"모두 가장 이상적이다는 말이 나오게끔 구현해줘."*

실측부터. 2026-08-17 기준 `state/champions.json`:

    19종목  ml  logreg · threshold 0.55 · train_window 250 · retrain_every 20
     1종목  ml  logreg · threshold 0.52 · train_window 250 · retrain_every 20

**전략 분산이 0입니다.** 종목은 20개인데 모델은 하나이고, 그 모델이 틀리는
국면에서는 20종목이 동시에 틀립니다. 배분(HRP·ERC)은 종목 상관을 낮추지만
**모델 상관은 1.0**입니다. 의회 장부도 `[{"strategy":"ml","weight":1.0}]` —
3석짜리 장치가 1인 체제로 잠들어 있었습니다.

구조가 없어서가 아닙니다. `parliament.py`의 `seat_census`가 이미 원인을
적어 두고 있었습니다 — **의석은 오직 승격자만 얻는데 승격은 189회 중 1회**
(0.5%)입니다. 문이 하나이고, 그 문은 이 질문만 합니다.

    "이 후보가 챔피언보다 **더 나은가?**"        (우월성 검정)

포트폴리오 이론이 말하는 두 번째 질문이 통째로 빠져 있었습니다.

    "이 후보가 챔피언만큼 하면서 **상관이 낮은가?**"  (비열등성 + 다양성)

기대수익이 같고 상관이 낮은 자산을 섞으면 **샤프가 오릅니다.** 그건 관문을
무르게 하는 것이 아니라 **다른 질문을 묻는 것**입니다. 그래서 승격 문턱은
그대로 두고, 의회에만 두 번째 문을 답니다.

이 파일은 그 문이 **아무나 들여보내지 않는다**는 것을 검사합니다 — 통과
경로 하나마다 대조군을 붙였습니다. 다양성이라는 이름으로 나쁜 전략을
들이면, 그건 다양화가 아니라 그냥 손실입니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.parliament import (  # noqa: E402
    DIVERSIFIER_CORR_MAX,
    DIVERSIFIER_PER_NIGHT,
    DIVERSIFIER_T_FLOOR,
    DIVERSIFIER_WEIGHT,
    ENTRY_WEIGHT,
    update_parliament,
)

IDX = pd.date_range("2025-01-01", periods=260, freq="D")
RNG = np.random.default_rng(20260817)


def _df() -> pd.DataFrame:
    close = pd.Series(np.linspace(100, 130, len(IDX)), index=IDX)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1.0}, index=IDX)


def _stub(monkeypatch, returns_by_name: dict, idle: set | None = None):
    import quant.backtest as B

    idle = idle or set()

    class _Res:
        def __init__(self, r, flat):
            self.returns = r
            self.positions = pd.Series(0.0 if flat else 1.0, index=r.index)

    class _Fake:
        def __init__(self, strat, **kw):
            self._name = getattr(strat, "name", "?")

        def run(self, df):
            if self._name not in returns_by_name:
                raise AssertionError(f"모르는 전략을 돌렸다: {self._name}")
            return _Res(returns_by_name[self._name], self._name in idle)

    monkeypatch.setattr(B, "Backtester", _Fake)


def _build(spec):
    class _S:
        name = spec["strategy"]
    return _S()


def _entry(*pairs) -> dict:
    ms = [{"strategy": n, "params": {}, "weight": w} for n, w in pairs]
    return {"strategy": ms[0]["strategy"], "params": {}, "parliament": ms}


def _app(name: str, select_t: float | None = 0.0) -> dict:
    return {"strategy": name, "params": {}, "select_t": select_t}


# 챔피언: 완만한 우상향. 잡음이 있어야 상관·t가 의미를 갖는다.
CHAMP = pd.Series(0.0010 + RNG.normal(0, 0.004, len(IDX)), index=IDX)


def _uncorrelated(mean: float) -> pd.Series:
    """챔피언과 상관 없는 계열 — 다른 베팅."""
    return pd.Series(mean + RNG.normal(0, 0.004, len(IDX)), index=IDX)


def _twin(scale: float = 1.0, mean_shift: float = 0.0) -> pd.Series:
    """챔피언을 그대로 따라가는 계열 — 같은 베팅(상관 ≈ 1)."""
    return CHAMP * scale + mean_shift


# ── ① 문이 열리는가 ──────────────────────────────────────────────

def test_a_different_but_equal_strategy_gets_a_seat(monkeypatch):
    """**이 파일이 생긴 이유.** 이기지 못해도 다르면 자리를 준다."""
    _stub(monkeypatch, {"champ": CHAMP, "other": _uncorrelated(0.0010)})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("other")])
    names = {m["strategy"] for m in out}
    assert names == {"champ", "other"}, out
    assert len(out) == 2, out


def test_the_newcomer_gets_less_than_a_promoted_champion(monkeypatch):
    """이긴 것과 다른 것은 같은 대우를 받지 않는다."""
    assert DIVERSIFIER_WEIGHT < ENTRY_WEIGHT, (DIVERSIFIER_WEIGHT, ENTRY_WEIGHT)
    _stub(monkeypatch, {"champ": CHAMP, "other": _uncorrelated(0.0010)})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("other")])
    new = next(m for m in out if m["strategy"] == "other")
    assert new["weight"] < 0.5, f"신입이 절반 넘게 가져갔다: {out}"


# ── ② 대조군 — 아무나 들여보내지 않는가 ─────────────────────────

def test_the_same_bet_in_a_new_costume_is_refused(monkeypatch):
    """상관이 높으면 이름이 달라도 **같은 베팅**이다.

    이 줄이 없으면 "다양성"이라는 이름으로 같은 모델을 두 자리에 앉힐 수
    있고, 그러면 이 장치는 분산이 아니라 **분산인 척**이 된다.
    """
    _stub(monkeypatch, {"champ": CHAMP, "clone": _twin()})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("clone")])
    assert [m["strategy"] for m in out] == ["champ"], out


def test_a_significantly_worse_strategy_is_refused(monkeypatch):
    """다르기만 하면 되는 게 아니다 — **못하면 안 된다.**

    다양성이라는 이름으로 손해 보는 전략을 들이면 그건 분산이 아니라 손실이다.
    """
    _stub(monkeypatch, {"champ": CHAMP, "loser": _uncorrelated(-0.0040)})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("loser")])
    assert [m["strategy"] for m in out] == ["champ"], out


def test_a_candidate_the_audition_already_buried_is_refused(monkeypatch):
    """선발전에서 **유의하게 진** 후보는 결승을 보지도 않는다."""
    _stub(monkeypatch, {"champ": CHAMP, "other": _uncorrelated(0.0010)})
    out = update_parliament(
        _entry(("champ", 1.0)), _df(), build=_build,
        applicants=[_app("other", select_t=-DIVERSIFIER_T_FLOOR - 0.5)])
    assert [m["strategy"] for m in out] == ["champ"], out


def test_a_cash_only_applicant_is_refused(monkeypatch):
    """채점 구간에 한 번도 포지션이 없으면 전략이 아니라 **현금**이다.

    현금에 의석을 주면 그만큼 책이 조용히 쉬면서 장부에는 "의회가 그렇게
    배분했다"고 적힌다.
    """
    _stub(monkeypatch, {"champ": CHAMP, "idler": _uncorrelated(0.0010)},
          idle={"idler"})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("idler")])
    assert [m["strategy"] for m in out] == ["champ"], out


def test_an_already_seated_strategy_does_not_get_a_second_seat(monkeypatch):
    _stub(monkeypatch, {"champ": CHAMP, "other": _uncorrelated(0.0010)})
    e = _entry(("champ", 0.7), ("other", 0.3))
    out = update_parliament(e, _df(), build=_build,
                            applicants=[_app("other")])
    assert sorted(m["strategy"] for m in out) == ["champ", "other"], out


# ── ③ 급변하지 않는가 ───────────────────────────────────────────

def test_at_most_one_new_seat_per_night(monkeypatch):
    """하룻밤에 의회가 통째로 갈리면 그건 의회가 아니라 쿠데타다."""
    assert DIVERSIFIER_PER_NIGHT == 1
    _stub(monkeypatch, {"champ": CHAMP,
                        "a": _uncorrelated(0.0011),
                        "b": _uncorrelated(0.0009)})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("a"), _app("b")])
    assert len(out) == 2, f"하룻밤에 두 석이 열렸다: {out}"


def test_no_applicants_changes_nothing(monkeypatch):
    """대조군 — 지원자가 없으면 예전과 똑같이 돈다."""
    _stub(monkeypatch, {"champ": CHAMP})
    before = _entry(("champ", 1.0))
    out = update_parliament(before, _df(), build=_build)
    assert [m["strategy"] for m in out] == ["champ"], out
    out2 = update_parliament(before, _df(), build=_build, applicants=[])
    assert [m["strategy"] for m in out2] == ["champ"], out2


# ── ④ 문턱이 실제로 그 값인가 ───────────────────────────────────

def test_the_correlation_bar_is_a_real_bar(monkeypatch):
    """상한을 1.0 근처로 두면 문이 사실상 없는 것과 같다.

    승격 쪽 CORR_CAP(0.97)은 '중복 제거'용이라 느슨해도 되지만, 다양성
    입성은 **적극적으로 다른** 것만 들여야 한다.
    """
    assert DIVERSIFIER_CORR_MAX <= 0.6, DIVERSIFIER_CORR_MAX
    # 상한 바로 위/아래를 실제로 태워 본다 — 숫자만 보는 검사는 배선을 못 본다.
    base = CHAMP - CHAMP.mean()
    noise = pd.Series(RNG.normal(0, base.std() * 3, len(IDX)), index=IDX)
    near = 0.0010 + base * 0.25 + noise          # 상관 낮음
    _stub(monkeypatch, {"champ": CHAMP, "near": near})
    c = float(near.corr(CHAMP))
    assert abs(c) < DIVERSIFIER_CORR_MAX, f"이 계열은 상한 아래여야 한다: {c}"
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("near")])
    assert len(out) == 2, f"상한 아래인데 못 들어왔다(상관 {c:.2f}): {out}"


def test_an_unmeasurable_correlation_counts_as_duplicate(monkeypatch):
    """상관을 못 재면 '무상관'이 아니라 **'중복'**으로 본다(감사 53의 규칙).

    0으로 치면 계산 실패가 곧 통과가 되어, 다양성 장치가 하필 흔들리는 날에
    정반대로 동작한다.
    """
    flat = pd.Series(0.0010, index=IDX)          # 상수 → corr가 NaN
    _stub(monkeypatch, {"champ": CHAMP, "flat": flat})
    out = update_parliament(_entry(("champ", 1.0)), _df(), build=_build,
                            applicants=[_app("flat")])
    assert [m["strategy"] for m in out] == ["champ"], out


# ── ⑤ 배선 — 오디션이 진 후보를 실제로 넘겨주는가 ───────────────

def test_the_audition_actually_hands_its_losers_to_the_parliament(
        tmp_path, monkeypatch):
    """문을 달아 놓고 **아무도 안 보내면** 문이 없는 것과 같다.

    ⚠️ 이 검사가 없어서 변이 하나가 살아남았다 — `applicants=[]`로 바꿔도
       위 검사들이 전부 통과했다. 위 검사들은 `update_parliament`를 직접
       부르기 때문이다. 부품이 옳은 것과 **배선이 돼 있는 것**은 다른 말이다
       (이 저장소가 감사 135·139·243에서 반복해 겪은 자리).
    """
    import quant.live.parliament as P
    from quant.live.retrain import DEFAULT_CHAMPION, run_retrain, save_champions

    seen = {}
    real = P.update_parliament

    def _spy(entry, df, **kw):
        seen["applicants"] = kw.get("applicants")
        return real(entry, df, **kw)

    monkeypatch.setattr(P, "update_parliament", _spy)

    d = str(tmp_path)
    save_champions({"synthetic:T0": {**DEFAULT_CHAMPION, "promotions": 0}}, d)
    run_retrain("synthetic", "T0", state_dir=d, limit=600,
                require_real_data=False)

    apps = seen.get("applicants")
    assert apps, "오디션이 후보를 하나도 안 넘겼다 — 두 번째 문이 굶는다"
    assert all(a.get("strategy") for a in apps), apps
    # 오디션이 이미 잰 선발전 t를 함께 넘겨야 ①번 관문이 작동한다.
    assert any(a.get("select_t") is not None for a in apps), apps
