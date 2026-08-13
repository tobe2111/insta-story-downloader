"""앙상블·게이트·유틸 7파일의 계약을 못 박는다 (감사 171).

전수조사에서 아래를 같은 눈으로 훑었다. **결함은 못 찾았다.**

    quant/strategies/ensemble.py    앙상블(고정·역변동성·HRP·적응형)
    quant/strategies/adx.py         추세 강도 게이트
    quant/strategies/liquidity.py   거래대금 게이트
    quant/portfolio/screener.py     종목 선별기 껍데기
    quant/utils/envfile.py          .env 로더
    quant/utils/logging.py          공통 로거
    quant/utils/manifest.py         재현성 매니페스트

가장 중요한 확인은 **앙상블의 인과성**이었다. 앙상블은 하위 전략들의 과거
손익으로 가중치를 정하는데, 그 계산이 한 봉이라도 미래를 보면 백테스트가
통째로 거짓말이 된다. 7가지 조합(고정·역변동성·HRP·리밸런스·적응형×2·
기본 앙상블)을 시계열 절단으로 검사했고 전부 통과했다 —
`_strategy_pnl`은 `shift(1)`, `_rolling_hrp`는 `iloc[i-lookback:i]`,
`_hold_weights`는 `ffill`로 셋 다 t-1까지만 쓴다.

이 파일들에는 변이 항목이 한 건도 없었다. 계약을 고정해 둔다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies import get_strategy  # noqa: E402
from quant.strategies.adx import ADXFilter  # noqa: E402
from quant.strategies.base import Strategy  # noqa: E402
from quant.strategies.ensemble import (  # noqa: E402
    AdaptiveEnsemble,
    StrategyEnsemble,
)
from quant.strategies.liquidity import LiquidityFilter  # noqa: E402


class _AlwaysLong(Strategy):
    """항상 롱 — 게이트가 무엇을 막는지만 보이게 한다."""

    name = "always"
    allow_short = False

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return self._finalize(pd.Series(1.0, index=df.index), df.index)


def _frame(close, volume=1e6) -> pd.DataFrame:
    s = pd.Series(np.asarray(close, dtype=float),
                  index=pd.date_range("2024-01-01", periods=len(close), freq="D"))
    return pd.DataFrame({"open": s, "high": s * 1.01, "low": s * 0.99,
                         "close": s, "volume": volume}, index=s.index)


@pytest.fixture(scope="module")
def noisy() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    return _frame(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 300))))


def _subs():
    return [get_strategy("ma_cross"), get_strategy("rsi"),
            get_strategy("mean_reversion")]


ENSEMBLES = {
    "fixed": lambda: StrategyEnsemble(_subs(), weighting="fixed"),
    "inverse_vol": lambda: StrategyEnsemble(_subs(), weighting="inverse_vol",
                                            vol_lookback=40),
    "hrp": lambda: StrategyEnsemble(_subs(), weighting="hrp", vol_lookback=40),
    "rebalanced": lambda: StrategyEnsemble(_subs(), weighting="inverse_vol",
                                           vol_lookback=40, rebalance=5),
    "adaptive": lambda: AdaptiveEnsemble(_subs(), lookback=40),
    "adaptive_hrp": lambda: AdaptiveEnsemble(_subs(), lookback=40,
                                             weighting="hrp"),
}


# ── 앙상블: 가중치가 미래를 보지 않는가 ───────────────────────


@pytest.mark.parametrize("name", list(ENSEMBLES))
def test_ensemble_weights_never_look_ahead(name, noisy):
    """앙상블은 과거 손익으로 가중을 정한다 — 한 봉이라도 미래를 보면 안 된다."""
    strat = ENSEMBLES[name]()
    full = strat.generate_signals(noisy)
    for k in (150, 220, 280):
        part = ENSEMBLES[name]().generate_signals(noisy.iloc[:k])
        diff = (full.iloc[:k] - part).abs()
        assert float(diff.max()) < 1e-12, (
            f"{name}: {k}봉까지만 주면 앞부분이 {int((diff > 1e-12).sum())}봉 "
            "달라진다 — 가중 계산이 미래를 봤다")


def test_the_pnl_matrix_uses_yesterdays_signal():
    """⚠️ 절단 검사로는 **봉 안쪽 룩어헤드**를 못 잡는다.

    `sigs.shift(1)`를 빼면 "그 봉에 정한 신호로 그 봉의 수익을 벌었다"가 된다.
    실전에서는 불가능한 일인데, 시계열을 잘라 봐도 앞부분이 안 달라진다 —
    그 봉의 신호와 그 봉의 수익은 둘 다 잘린 프레임 안에 있기 때문이다.
    그래서 정의 자체를 손으로 확인한다.
    """
    from quant.strategies.ensemble import _strategy_pnl

    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    close = pd.Series([100.0, 110.0, 121.0, 121.0, 100.0], index=idx)
    df = pd.DataFrame({"close": close}, index=idx)
    # 마지막 봉에만 롱을 잡는다 — 그 봉의 -17% 하락을 벌었으면 안 된다
    sig = pd.Series([0.0, 0.0, 0.0, 0.0, 1.0], index=idx)

    pnl = _strategy_pnl(df, [sig])
    assert float(pnl[0].iloc[-1]) == 0.0, (
        "마지막 봉에 처음 잡은 포지션이 그 봉의 수익을 벌었다 — 봉 안쪽 룩어헤드")

    sig2 = pd.Series([0.0, 0.0, 0.0, 1.0, 0.0], index=idx)
    got = float(_strategy_pnl(df, [sig2])[0].iloc[-1])
    want = float(close.iloc[-1] / close.iloc[-2] - 1.0)
    assert got == pytest.approx(want), (
        f"직전 봉 신호가 이번 봉 수익을 벌어야 한다: {got} vs {want}")


def test_the_rolling_hrp_never_sees_the_current_bar():
    """가중치는 t-1까지의 손익만 써야 한다.

    이번 봉의 손익을 바꿔도 **이번 봉의 가중치**는 그대로여야 한다.
    (이것도 절단 검사로는 안 잡힌다 — 잘린 프레임에도 그 봉이 들어 있다.)
    """
    from quant.strategies.ensemble import _rolling_hrp

    rng = np.random.default_rng(4)
    pnl = pd.DataFrame(rng.normal(0.0, 0.01, (80, 3)),
                       index=pd.date_range("2024-01-01", periods=80, freq="D"))
    base = _rolling_hrp(pnl, lookback=20, rebalance=1)

    tampered = pnl.copy()
    tampered.iloc[40] = [5.0, -5.0, 0.0]          # 그 봉만 극단으로 바꾼다
    after = _rolling_hrp(tampered, lookback=20, rebalance=1)

    assert np.allclose(base.iloc[40].to_numpy(), after.iloc[40].to_numpy(),
                       equal_nan=True), (
        "이번 봉의 손익이 이번 봉의 가중치를 바꾼다 — 미래를 봤다")
    assert not np.allclose(base.iloc[41].to_numpy(), after.iloc[41].to_numpy(),
                           equal_nan=True), (
        "다음 봉 가중치는 바뀌어야 한다 — 안 바뀌면 이 검사가 헛돈다")


@pytest.mark.parametrize("name", list(ENSEMBLES))
def test_the_weights_always_form_a_full_allocation(name, noisy):
    """행 합이 1이 아니면 결합 신호가 개별 신호 범위를 벗어난다(숨은 레버리지)."""
    strat = ENSEMBLES[name]()
    strat.generate_signals(noisy)
    rows = strat.last_weights_.sum(axis=1)
    assert float(rows.min()) == pytest.approx(1.0), float(rows.min())
    assert float(rows.max()) == pytest.approx(1.0), float(rows.max())
    assert float(strat.last_weights_.min().min()) >= 0.0, "음수 가중"


def test_rebalancing_actually_holds_the_weights(noisy):
    """리밸런스 주기는 회전율 절감 장치다 — 실제로 가중이 고정돼야 의미가 있다."""
    every = StrategyEnsemble(_subs(), weighting="inverse_vol", vol_lookback=40)
    held = StrategyEnsemble(_subs(), weighting="inverse_vol", vol_lookback=40,
                            rebalance=10)
    every.generate_signals(noisy)
    held.generate_signals(noisy)

    def _changes(w):
        return int((w.diff().abs().sum(axis=1) > 1e-12).sum())

    assert _changes(held.last_weights_) < _changes(every.last_weights_) / 3, (
        f"리밸런스를 걸었는데 가중이 {_changes(held.last_weights_)}번 바뀐다 "
        f"(매 봉은 {_changes(every.last_weights_)}번)")


def test_a_combined_signal_stays_within_the_component_range(noisy):
    """대조군 — 가중 결합이 개별 신호보다 큰 비중을 만들면 안 된다."""
    sig = StrategyEnsemble(_subs(), weighting="hrp", vol_lookback=40) \
        .generate_signals(noisy)
    assert float(sig.max()) <= 1.0 and float(sig.min()) >= 0.0


# ── 게이트: 막을 때 막고, 통과시킬 때 통과시키는가 ────────────


def test_the_adx_gate_blocks_a_rangebound_market():
    rng = np.random.default_rng(2)
    trend = [100 * (1.01 ** i) for i in range(120)]
    chop = list(100 + rng.normal(0.0, 0.6, 120))
    assert float(ADXFilter(_AlwaysLong()).generate_signals(
        _frame(trend)).max()) == 1.0, "뚜렷한 추세인데 막는다"
    assert float(ADXFilter(_AlwaysLong()).generate_signals(
        _frame(chop)).max()) == 0.0, "횡보장인데 통과시킨다"


def test_the_liquidity_gate_blocks_a_thin_symbol():
    trend = [100 * (1.01 ** i) for i in range(120)]
    rich = LiquidityFilter(_AlwaysLong(), min_dollar_vol=1e6)
    thin = LiquidityFilter(_AlwaysLong(), min_dollar_vol=1e12)
    assert float(rich.generate_signals(_frame(trend, volume=1e6)).max()) == 1.0
    assert float(thin.generate_signals(_frame(trend, volume=1e2)).max()) == 0.0, (
        "거래대금이 문턱에 한참 못 미치는데 매매를 허용한다")


def test_a_gate_with_no_threshold_is_transparent():
    """대조군 — 문턱을 안 걸면 하위 전략을 그대로 통과시켜야 한다."""
    trend = [100 * (1.01 ** i) for i in range(120)]
    sig = LiquidityFilter(_AlwaysLong(), min_dollar_vol=0.0) \
        .generate_signals(_frame(trend))
    assert float(sig.min()) == 1.0


# ── 스크리너 껍데기: 못 받은 종목을 지어내지 않는가 ───────────


def test_the_screener_drops_symbols_it_could_not_fetch():
    from quant.portfolio import screen_symbols

    data = {"AAA": {"pe": 8.0, "pb": 0.8, "roe": 0.25},
            "BBB": {"pe": 15.0, "pb": 1.5, "roe": 0.10},
            "CCC": {"pe": 40.0, "pb": 4.0, "roe": 0.02}}
    res = screen_symbols(["AAA", "BBB", "CCC", "ZZZ"],
                         ratios_fn=lambda s: data.get(s, {}), top_n=2)
    assert "ZZZ" not in res["ratios"], (
        "재무를 못 받은 종목이 빈 dict로 후보에 들어간다")
    assert "ZZZ" not in res["selected"]
    assert set(res["selected"]) <= {"AAA", "BBB", "CCC"}


def test_the_screener_returns_nothing_when_no_data_arrives():
    """대조군 — 아무것도 못 받으면 아무것도 고르면 안 된다."""
    from quant.portfolio import screen_symbols

    res = screen_symbols(["AAA", "BBB"], ratios_fn=lambda s: {})
    assert res["selected"] == [] and res["weights"] == {}


# ── .env 로더 ─────────────────────────────────────────────────


def test_the_shell_environment_wins_over_the_env_file(tmp_path, monkeypatch):
    """셸에서 직접 준 값이 파일보다 우선이다 — 뒤집히면 키가 조용히 바뀐다."""
    from quant.utils.envfile import load_env_file

    fp = tmp_path / ".env"
    fp.write_text("QUANT_T_A=from_file\nQUANT_T_B=from_file\n", encoding="utf-8")
    monkeypatch.setenv("QUANT_T_A", "from_shell")
    monkeypatch.delenv("QUANT_T_B", raising=False)

    load_env_file(fp)
    assert os.environ["QUANT_T_A"] == "from_shell"
    assert os.environ["QUANT_T_B"] == "from_file"


def test_a_secret_file_is_created_private_from_the_first_byte(tmp_path):
    """쓰고 나서 조이면 그 사이 다른 사용자가 읽는다(감사 ㊾)."""
    from quant.utils.envfile import is_private, write_private

    fp = tmp_path / "license.key"
    ok = write_private(fp, "owner: me\nkey: SECRET\n")
    if os.name == "posix":
        assert ok and is_private(fp), oct(fp.stat().st_mode)
        assert fp.stat().st_mode & 0o077 == 0, oct(fp.stat().st_mode)


def test_the_env_parser_ignores_comments_and_junk():
    from quant.utils.envfile import parse_env_text

    got = parse_env_text('# c\n\nA=1\nB="two"\nC=\nbad line\n9!=x\n')
    assert got == {"A": "1", "B": "two", "C": ""}, got


# ── 매니페스트·로거 ───────────────────────────────────────────


def test_the_data_checksum_notices_every_field():
    """지문이 한 칸이라도 안 보면 '데이터가 바뀌었다'를 놓친다."""
    from quant.utils.manifest import data_checksum

    base = ("2024-01-01", "2024-06-01", 100, 10.0, 20.0)
    h = data_checksum(*base)
    assert data_checksum(*base) == h, "같은 입력인데 지문이 흔들린다"
    for i in range(len(base)):
        other = list(base)
        other[i] = 101 if i == 2 else (
            str(other[i]) + "x" if isinstance(other[i], str) else other[i] + 1.0)
        assert data_checksum(*other) != h, f"{i}번째 칸이 바뀌어도 지문이 같다"


def test_the_json_logger_emits_the_context_fields():
    import json
    import logging

    from quant.utils.logging import _JsonFormatter

    rec = logging.LogRecord("quant.t", logging.INFO, __file__, 1,
                            "order_filled", None, None)
    rec.ctx = {"order_id": "A1", "qty": 0.1}
    got = json.loads(_JsonFormatter().format(rec))
    assert got["msg"] == "order_filled" and got["order_id"] == "A1"
    assert got["level"] == "INFO" and got["logger"] == "quant.t"


@pytest.mark.parametrize("value,want", [("1", True), ("true", True),
                                        ("YES", True), ("0", False),
                                        ("", False), ("no", False)])
def test_the_json_switch_reads_the_environment(value, want, monkeypatch):
    from quant.utils.logging import _json_enabled

    monkeypatch.setenv("QUANT_LOG_JSON", value)
    assert _json_enabled() is want


# ── 로그가 자기 시각·메시지를 잃지 않는가 (감사 208) ──────────────
#
# `_JsonFormatter`는 `payload.update(ctx)`였다. 그래서 컨텍스트에 `msg`나
# `time`이라는 이름이 있으면 **진짜 메시지와 시각이 통째로 바뀌었다.** 실측:
#
#     log_event(log, "진짜 메시지", msg="가짜 메시지", time="가짜 시각")
#     →  {"time": "가짜 시각", "msg": "가짜 메시지", ...}
#
# 로그가 "언제 무슨 일이 있었는지"를 거짓으로 말하는 것이다 — 감사 추적용
# 기록에서는 가장 나쁜 실패다. 게다가 유일한 호출부는 `**result`로 **임의의
# dict를 통째로 펼친다** — 부르는 쪽은 무엇이 예약 키인지 알 수 없고,
# `"time"`은 이 저장소 장부가 어디서나 쓰는 이름이다.


def _fmt(msg: str, ctx: dict) -> dict:
    import json
    import logging

    from quant.utils.logging import _JsonFormatter

    rec = logging.LogRecord("quant.t", logging.INFO, __file__, 1, msg, (), None)
    rec.ctx = ctx
    return json.loads(_JsonFormatter().format(rec))


def test_a_context_field_cannot_rewrite_the_message_or_the_time():
    got = _fmt("진짜 메시지", {"msg": "가짜 메시지", "time": "가짜 시각",
                              "logger": "가짜 로거", "level": "가짜 레벨"})
    assert got["msg"] == "진짜 메시지", got
    assert got["time"] != "가짜 시각", got
    assert got["logger"] == "quant.t" and got["level"] == "INFO", got


def test_the_colliding_value_is_kept_not_thrown_away():
    """덮어쓰지도 버리지도 않는다 — 값을 잃는 것도 조용한 손실이다."""
    got = _fmt("진짜 메시지", {"msg": "가짜 메시지", "time": "가짜 시각"})
    assert got["ctx_msg"] == "가짜 메시지", got
    assert got["ctx_time"] == "가짜 시각", got


def test_ordinary_context_fields_are_untouched():
    """대조군 — 충돌하지 않는 필드는 접두어 없이 그대로 나가야 한다.

    이게 없으면 위 검사들은 "모든 필드에 ctx_를 붙이는" 구현도 통과시키고,
    그러면 JSON 로그를 읽는 쪽의 키가 전부 바뀐다.
    """
    got = _fmt("order_filled", {"order_id": "A1", "side": "buy", "qty": 0.1})
    assert got["order_id"] == "A1" and got["side"] == "buy" and got["qty"] == 0.1
    assert not [k for k in got if k.startswith("ctx_")], got


def test_a_non_dict_context_is_ignored():
    """경계 — ctx가 dict가 아니면 무시하고 로그는 계속 나가야 한다."""
    for bad in (None, "문자열", 42, ["a"]):
        got = _fmt("x", bad) if isinstance(bad, dict) else None
        if got is None:
            import json
            import logging

            from quant.utils.logging import _JsonFormatter
            rec = logging.LogRecord("quant.t", logging.INFO, __file__, 1,
                                    "x", (), None)
            rec.ctx = bad
            got = json.loads(_JsonFormatter().format(rec))
        assert got["msg"] == "x", (bad, got)
