"""승격의 마지막 관문 — "이 종목에서만 좋은가, 여러 종목에서 좋은가".

작업 #56. 사장님 ①안(2026-08-27)의 마지막 단계이고, 착수 조건은 날짜가
아니라 **두 관문이 갈린 장면**이었다. 2026-09-02 장부에서 그것이 왔다:

    같은 밤 · 같은 설정 3건 · 22종목 · 161일
      패널   t=−0.27 · −1.31 · −2.01  (문턱 1.35)  → 전부 불통과
      종목별 통과 1/22 · 1/22 · 1/22             → 셋 다 누군가를 통과시킴

세 판정이 전부 갈렸다(3/3). 방향도 패널을 만든 이유 그대로다 — 종목별
관문은 22종목 중 하나를 통과시키는데, 같은 설정을 전 종목에 놓고 보면
도움이 되기는커녕 **평균이 음수**다. 한 종목에서만 좋아 보이는 것은 대개
잡음이고, 그것을 거르는 것이 이 관문의 존재 이유다.

여기서 지키는 약속:

  ① 패널은 기존 관문을 **갈아 끼우지 않는다.** 선발전·결승전·동시검정은
     그대로 돌고 그대로 기록된다(①안의 조건). 패널은 그 위의 AND다.
     그래서 이 관문이 틀려도 일어나는 일은 "승격이 덜 되는 것"이지
     "나쁜 후보가 승격되는 것"이 아니다.
  ② **판정이 없으면 막지 않는다.** 언덕오르기 변이는 종목마다 달라 패널에
     담기지 않는다. 없는 것을 위반으로 세면 변이 후보가 영영 승격 못 하고
     언덕오르기가 죽는다.
  ③ 막았든 통과시켰든 **장부에 남긴다.** 막은 밤만 남기면 "관문이 없던
     때"와 "관문이 통과시킨 때"가 장부에서 똑같이 보인다.
  ④ 재현(verify)은 **그날 적힌 판정**으로 한다. 오늘의 패널 장부로 어제
     결정을 재생하면 그 사이 명단이 회전해 판정이 달라진다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live import retrain as R  # noqa: E402


def _df(n=400, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.01, n)))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": np.full(n, 1e6)}, index=idx)


CHAMP = {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}}
CHALL = [{"strategy": "ma_cross", "params": {"fast": 3, "slow": 10}}]


def _run(**kw):
    return R.nightly_retrain(_df(), CHAMP, CHALL, confirm_window=120, **kw)


# ── ① 관문이 실제로 막는다 ─────────────────────────────────────────────
def test_a_blocking_panel_verdict_stops_a_promotion():
    """종목별 관문을 다 통과해도 패널이 아니라면 승격하지 않는다."""
    blocked = {"blocked": True, "t_stat": -1.31, "t_threshold": 1.35,
               "n_symbols": 22, "n_dates": 161, "night": "2026-09-02"}
    # 관문 없이 승격되는 조건을 먼저 만든다(문턱을 아주 낮춰서).
    free = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False)
    if not free["promoted"]:
        pytest.skip("이 표본에서는 관문 없이도 승격이 안 난다")
    gated = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False,
                 panel_lookup=lambda spec: blocked)
    assert gated["promoted"] is False, "패널이 아니라는데 승격됐다"
    assert gated["panel_gate"] == blocked
    assert "패널 관문" in gated["reason"]


def test_a_passing_panel_verdict_does_not_stop_a_promotion():
    passing = {"blocked": False, "t_stat": 2.4, "t_threshold": 1.35,
               "n_symbols": 22, "n_dates": 161}
    free = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False)
    if not free["promoted"]:
        pytest.skip("이 표본에서는 관문 없이도 승격이 안 난다")
    out = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False,
               panel_lookup=lambda spec: passing)
    assert out["promoted"] is True
    assert out["panel_gate"] == passing


# ── ② 판정이 없으면 막지 않는다 ────────────────────────────────────────
def test_no_verdict_never_blocks():
    """변이 후보는 패널에 담기지 않는다 — 없는 것을 위반으로 세면 안 된다."""
    free = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False)
    out = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False,
               panel_lookup=lambda spec: None)
    assert out["promoted"] == free["promoted"]
    assert out.get("panel_gate") is None


def test_a_broken_lookup_never_blocks():
    """조회가 터져도 승격 판정이 죽지 않는다 — 장부 사고가 오디션을 못 멈춘다."""
    def _boom(spec):
        raise RuntimeError("장부 손상")
    free = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False)
    out = _run(select_t=-99.0, confirm_t=-99.0, reality_gate=False,
               panel_lookup=_boom)
    assert out["promoted"] == free["promoted"]


# ── ③ 기존 관문은 그대로다 (①안의 조건) ────────────────────────────────
def test_the_old_gates_still_run_and_are_still_recorded():
    """패널은 **덧붙는** 관문이다 — 결승·동시검정 기록이 그대로 남는다."""
    out = _run(select_t=-99.0, confirm_t=-99.0,
               panel_lookup=lambda spec: {"blocked": True, "t_stat": -1.0,
                                          "t_threshold": 1.35,
                                          "n_symbols": 22})
    assert out.get("final") is not None, "결승 기록이 사라졌다"
    assert "reality_check" in out, "동시검정 기록이 사라졌다"


def test_the_panel_gate_is_the_last_gate_not_the_first():
    """앞 관문에서 이미 떨어진 후보는 패널을 묻지도 않는다.

    순서가 뒤집히면 '패널이 막았다'가 장부에 잘못 적히고, 두 관문의 대조가
    오염된다 — 무엇이 실제로 막았는지 알 수 없게 된다.
    """
    calls = []

    def _spy(spec):
        calls.append(spec)
        return {"blocked": True, "t_stat": -1.0, "t_threshold": 1.35,
                "n_symbols": 22}
    out = _run(select_t=99.0, confirm_t=99.0, panel_lookup=_spy)
    assert out["promoted"] is False
    assert calls == [], "선발전에서 떨어진 후보에게 패널을 물었다"


# ── ④ 장부 조회기 ──────────────────────────────────────────────────────
def _write_panel(tmp_path, night, spec_key, passed, t=1.0, n=200):
    """실제 장부 한 줄을 흉내 낸다.

    ⚠️ 판정은 장부에 적힌 ``pass``를 그대로 읽는 것이 **아니라**, 날짜별
       합·개수(``daily``)에서 다시 계산된다(``panel_nights``). 그래야 한 밤의
       여러 회차를 포갤 수 있다. 그래서 여기서도 원하는 판정이 나오도록
       재료를 만든다 — 요약만 적으면 그 줄은 '합칠 수 없는 옛 줄'이 된다.
    """
    rng = np.random.default_rng(abs(hash(night)) % 2**31)
    # 통과시키려면 평균이 크게 양수여야 하고, 막으려면 음수면 된다.
    mu = 0.01 if passed else -0.01
    dates = [str(d.date()) for d in pd.bdate_range("2026-01-01", periods=n)]
    sums = list(rng.normal(mu, 0.0015, n))
    line = {"roster_asof": night, "asof": night, "n_symbols_seen": 22,
            "t_ref": 1.35,
            "specs": [{"spec_key": spec_key,
                       "daily": {"dates": dates, "sums": sums,
                                 "counts": [6] * n,
                                 # 최소 종목 수(5)를 넘겨야 판정이 난다 —
                                 # 모자라면 '못 잰 밤'이 되고, 못 잰 것은
                                 # 막지 않는다(그것도 옳은 동작이다).
                                 "symbols": [f"m{i}:S{i}" for i in range(6)]},
                       "symbol_terms": {f"m{i}:S{i}": [1.0, mu]
                                        for i in range(6)}}]}
    with open(tmp_path / R.PANEL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def test_the_lookup_reads_the_ledger_and_reports_the_symbol_gate_too(tmp_path):
    """①안 — 종목별 관문이 같은 설정을 어떻게 봤는지도 나란히 돌려준다."""
    spec = {"strategy": "ibs", "params": {"entry": 0.2, "exit": 0.8}}
    _write_panel(tmp_path, "2026-09-02", R.spec_key(spec), passed=False)
    got = R.panel_gate_lookup(str(tmp_path))(spec)
    assert got["blocked"] is True, got
    assert got["t_stat"] < 0, got
    assert got["symbol_pass"] is not None, "종목별 판정이 함께 안 실렸다"
    assert got["night"] == "2026-09-02"


def test_an_unknown_spec_returns_no_verdict(tmp_path):
    _write_panel(tmp_path, "2026-09-02",
                 R.spec_key({"strategy": "ibs", "params": {}}), passed=False)
    other = {"strategy": "ml", "params": {"model": "gb"}}
    assert R.panel_gate_lookup(str(tmp_path))(other) is None


def test_a_stale_verdict_is_not_used(tmp_path):
    """오래된 판정으로 오늘의 승격을 막지 않는다.

    명단이 3개씩 회전하므로 어떤 설정의 판정은 며칠 전 것이다. 그렇다고
    아무리 낡은 것이나 다 쓰면 "그때는 그랬다"로 오늘을 막게 된다.
    """
    spec = {"strategy": "ibs", "params": {}}
    _write_panel(tmp_path, "2026-08-20", R.spec_key(spec), passed=False)
    for d in range(21, 32):                       # 그 뒤로 밤이 여럿 지났다
        _write_panel(tmp_path, f"2026-08-{d}",
                     R.spec_key({"strategy": "rsi", "params": {"n": d}}),
                     passed=True)
    assert R.panel_gate_lookup(str(tmp_path), max_age_nights=3)(spec) is None
    assert R.panel_gate_lookup(str(tmp_path), max_age_nights=30)(spec) is not None


def test_the_newest_verdict_wins(tmp_path):
    """같은 설정에 판정이 여럿이면 **가장 최근 것**을 쓴다."""
    spec = {"strategy": "ibs", "params": {}}
    key = R.spec_key(spec)
    _write_panel(tmp_path, "2026-08-30", key, passed=False)
    _write_panel(tmp_path, "2026-08-31", key, passed=True)
    got = R.panel_gate_lookup(str(tmp_path))(spec)
    assert got["blocked"] is False, got
    assert got["t_stat"] > 0, got


def test_a_missing_ledger_never_blocks(tmp_path):
    assert R.panel_gate_lookup(str(tmp_path))({"strategy": "ibs"}) is None


# ── ⑤ 장부와 재현 ──────────────────────────────────────────────────────
def test_the_night_record_carries_the_panel_verdict():
    import inspect
    src = inspect.getsource(R)
    assert '"panel_gate": decision.get("panel_gate"),' in src, (
        "밤 기록에 패널 판정 칸이 없다 — 관문의 효과를 나중에 잴 수 없다")
    assert '"gate_version": 4,' in src, (
        "관문이 바뀌었으면 세대도 올려야 한다(재현이 옛 규칙으로 돌아간다)")


def test_verify_replays_the_recorded_verdict_not_todays():
    """재현은 **그날 적힌 판정**을 되먹인다.

    오늘의 패널 장부로 어제 결정을 재생하면, 그 사이 명단이 회전하고 종목이
    늘어 판정이 달라진다 — 재현이 코드가 아니라 장부 때문에 깨진다.
    """
    import inspect
    src = inspect.getsource(R.verify_recent) if hasattr(R, "verify_recent") \
        else inspect.getsource(R)
    assert '_pg=rec.get("panel_gate")' in src
    assert 'int(rec.get("gate_version", 1)) >= 4' in src, (
        "옛 기록(v1~v3)은 이 관문이 없던 세계다 — 그대로 재현해야 한다")


def test_a_verdict_that_could_not_be_measured_never_blocks(tmp_path):
    """종목이 모자라 **못 잰** 밤은 막지 않는다.

    패널에 5종목이 안 서면 판정 자체가 생략된다. 그 생략을 "통과 못 함"으로
    읽으면, 종목을 적게 돈 밤마다 승격이 통째로 얼어붙는다 — 못 잰 것과
    나쁜 것은 다른 사건이다.
    """
    spec = {"strategy": "ibs", "params": {}}
    rng = np.random.default_rng(3)
    n = 50
    line = {"roster_asof": "2026-09-02", "asof": "2026-09-02", "t_ref": 1.35,
            "n_symbols_seen": 3,
            "specs": [{"spec_key": R.spec_key(spec),
                       "daily": {"dates": [str(d.date()) for d in
                                           pd.bdate_range("2026-01-01", periods=n)],
                                 "sums": list(rng.normal(-0.01, 0.001, n)),
                                 "counts": [2] * n,
                                 "symbols": ["m0:A", "m1:B"]},   # 5 미만
                       "symbol_terms": {}}]}
    with open(tmp_path / R.PANEL_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    assert R.panel_gate_lookup(str(tmp_path))(spec) is None
