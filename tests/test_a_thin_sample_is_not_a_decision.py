"""표본이 모자란 종목이 '분산된 종목'으로 세어지지 않는가 (감사 201).

훑은 파일: `quant/data/crypto.py`(코인 시세 · 유일하게 즉시 체결되는 시장).

**제공자 자체에는 결함이 없었다.** 보조 거래소 사다리도, 빈 결과 검사도,
`end` 컷의 tz 처리도 제대로 되어 있었다. 문제는 **받은 뒤**였다.

받는 쪽(`run_daily_portfolio`)은 `df.empty`만 봤다. 그래서 보조 거래소가
10봉만 주는 날 — 상장 초기 코인, 그 페어의 이력이 짧은 거래소 — 신호는
0으로 나오는데 **장부에는 아무 흔적도 없었다.** 실측(고치기 전):

    B0가 400봉일 때 → 장부 "3종목 분산" · 실제 포지션 3개
    B0가  10봉일 때 → 장부 "3종목 분산" · 실제 포지션 **2개**   ← 거짓말
                      건너뛴 이유: 없음

감사 59에서 *"데이터 실패로 빠진 종목을 계획 수로 세지 말 것"*을 고쳤다.
그건 **예외가 난 종목**만 잡는다. 데이터가 멀쩡히 온 뒤 **표본이 모자라
아무것도 못 한 종목**은 그 그물에 안 걸린다 — 같은 거짓말의 다른 문이다
(감사 200에서 배운 형태: 무엇을 막는다고 적었으면 그 무엇이 지나는 문을
전부 셀 것).

그리고 이건 이 저장소가 가장 신경 쓰는 **오디션-현실 격차**다. 챔피언을
400봉으로 선발해 놓고 실전에서 10봉으로 굴리면 선발 조건과 실전 조건이
다르다(감사 71과 같은 계열).

**조용한 0과 판단해서 낸 0은 다르다** — 전자는 *못 한* 것이고 후자는
*안 한* 것이다. 장부는 둘을 구별해야 한다.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data as QD  # noqa: E402
import quant.live.daily as D  # noqa: E402
from quant.live.daily import required_bars  # noqa: E402
from quant.live.retrain import save_champions  # noqa: E402


def _frame(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    idx = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq="D")
    df = pd.DataFrame({"open": c * .99, "high": c * 1.02, "low": c * .98,
                       "close": c, "volume": 1e6}, index=idx)
    df.attrs["source"] = "okx"          # 보조 거래소에서 온 것처럼
    return df


def _run(tmp_path, thin_bars: int, *, thin="B0", n_syms=3):
    """B0만 `thin_bars`봉, 나머지는 400봉으로 하루를 돌린다."""
    save_champions({f"synthetic:B{i}": {"strategy": "ma_cross",
                                        "params": {"fast": 10, "slow": 30},
                                        "promotions": 0}
                    for i in range(n_syms)}, str(tmp_path))
    p = tmp_path / "paper"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio_ALL.json").write_text(json.dumps({
        "market": "portfolio", "symbol": "ALL", "start_cash": 100_000.0,
        "cash": 100_000.0, "positions": {}, "base_prices": {},
        "last_bar": None, "history": [],
    }), encoding="utf-8")

    class _P:
        def get_ohlcv(self, sym, *a, **k):
            # ⚠️ 시드를 `hash(sym)`으로 잡았다가 검사가 실행마다 달라졌다 —
            #    파이썬 문자열 해시는 **프로세스마다 랜덤화**된다(PYTHONHASHSEED).
            #    변이 시험이 한 번은 통과, 한 번은 '검사 자체 고장'을 내며
            #    번갈아 나와서 알았다. 검사는 시계에도 무작위에도 기대면
            #    안 된다(㊿+㉝의 쌍둥이).
            seed = int(str(sym)[-1]) if str(sym)[-1].isdigit() else 0
            return _frame(thin_bars if sym == thin else 400, seed)

    orig = QD.get_provider
    QD.get_provider = lambda m: _P()
    try:
        return D.run_daily_portfolio(
            [("synthetic", f"B{i}") for i in range(n_syms)],
            lookback=400, state_dir=str(tmp_path), require_real_data=False)
    finally:
        QD.get_provider = orig


# ── ① 못 한 종목은 '분산된 종목'이 아니다 ─────────────────────


def test_a_symbol_with_too_few_bars_is_not_counted_as_diversified(tmp_path):
    """10봉짜리 종목이 "3종목 분산"에 들어가면 안 된다."""
    rec = _run(tmp_path, thin_bars=10)
    ch = rec["champion"]
    assert ch["symbols"] == 2, f"못 한 종목을 세었다: {ch}"
    assert ch["planned"] == 3, "계획 수는 그대로여야 한다"
    why = ch.get("skipped_why") or {}
    assert "synthetic:B0" in why, f"왜 빠졌는지가 없다: {why}"
    assert "표본 부족" in why["synthetic:B0"], why["synthetic:B0"]
    assert "10봉" in why["synthetic:B0"], "몇 봉이었는지가 없다 — 판단 불가"


def test_a_full_sample_day_is_unchanged(tmp_path):
    """대조군 — 표본이 충분하면 예전과 똑같다.

    이게 없으면 위 검사는 "무엇이든 빼는" 구현도 통과시키고, 그러면
    평범한 날에 종목이 조용히 사라진다.
    """
    rec = _run(tmp_path, thin_bars=400)
    ch = rec["champion"]
    assert ch["symbols"] == 3 and not (ch.get("skipped_why") or {}), ch


def test_the_boundary_is_exactly_the_requirement(tmp_path):
    """딱 필요한 만큼이면 통과하고, 한 봉 모자라면 빠진다.

    ⚠️ 경계를 안 재면 `<`와 `<=`를 바꿔도 아무 검사가 안 깨진다. 이 규칙이
       **답을 정하는** 자리는 정확히 여기 한 봉이다(2026-08-13에 배운 것:
       다른 제약이 먼저 걸리면 변이가 빠져나간다).

    ma_cross(fast=10, slow=30) → 필요 30봉. 코인이 아니라 합성 시장이므로
    `_signal_frame`이 봉을 빼지 않아 받은 수가 그대로 표본이 된다.
    """
    need = required_bars({"params": {"fast": 10, "slow": 30}})
    assert need == 30

    ok = _run(tmp_path / "ok", thin_bars=need)
    assert not (ok["champion"].get("skipped_why") or {}), (
        f"딱 필요한 만큼인데 빠졌다: {ok['champion']}")
    assert ok["champion"]["symbols"] == 3

    short = _run(tmp_path / "short", thin_bars=need - 1)
    why = short["champion"].get("skipped_why") or {}
    assert "synthetic:B0" in why, f"한 봉 모자란데 통과했다: {short['champion']}"
    assert f"{need - 1}봉" in why["synthetic:B0"]


# ── ② 필요 봉수는 챔피언이 스스로 말한 값에서 나온다 ──────────


def test_the_requirement_comes_from_the_champion_itself():
    """상수를 박지 않고 전략이 선언한 가장 긴 창을 쓴다."""
    assert required_bars({"params": {"fast": 10, "slow": 30}}) == 30
    assert required_bars({"params": {"fast": 5, "slow": 200}}) == 200
    # 기본 챔피언(ml logreg)의 train_window가 그대로 요구치가 된다
    from quant.live.retrain import DEFAULT_CHAMPION
    assert required_bars(DEFAULT_CHAMPION) == 250


def test_the_requirement_is_not_doubled():
    """⚠️ 처음에 두 배를 요구했다가 과했다 — 검사 5건이 빨개져서 알았다.

    기본 챔피언의 `train_window=250`이 500봉 요구가 되어, 300봉을 주는
    정상 픽스처까지 전부 막혔다. 파라미터가 전부 '창 길이'는 아니다.
    선언한 창이 **한 번** 채워지는 것까지가 근거 있는 요구고, 그 이상은
    추측이다. 이 검사가 그 과욕이 되살아나는 것을 막는다.
    """
    assert required_bars({"params": {"train_window": 250}}) == 250
    assert required_bars({"params": {"slow": 300}}) == 300


def test_odd_parameters_do_not_break_the_requirement():
    """경계 — 파라미터가 없거나·문자열·불리언·NaN이어도 답이 나와야 한다."""
    assert required_bars({}) == 30
    assert required_bars({"params": {}}) == 30
    assert required_bars({"params": {"model": "logreg", "use_x": True}}) == 30
    assert required_bars({"params": {"threshold": 0.55}}) == 30
    assert required_bars({"params": {"bad": float("nan"),
                                     "worse": float("inf")}}) == 30
    assert required_bars({"params": {"slow": -60}}) == 60   # 부호는 무시


@pytest.mark.parametrize("floor", [10, 30, 100])
def test_the_floor_is_respected(floor):
    assert required_bars({"params": {"slow": 5}}, floor=floor) == floor
