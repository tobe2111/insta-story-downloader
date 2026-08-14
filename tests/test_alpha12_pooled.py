"""알파 12차 계약 검사 — 풀링(패널) 학습.

핵심 계약:
  ① 풀 주입 학습이 동작하고, pool=None(기본)은 기존과 동일 결과
  ② 룩어헤드 차단: 학습 상한 이후의 풀 행은 결과에 영향을 못 준다 —
     '미래 풀 행'을 극단값으로 바꿔도 신호가 안 변한다
  ③ meta+pool 조합은 명시적 거부, 잘못된 pool 값도 거부
  ④ 스냅샷 로더: 당일 폴더 제외(엄격히 이전 날짜의 최신 폴더 — verify
     재현 보존), 폴더 없으면 빈 목록
  ⑤ 풀링 챌린저 2종이 링에 있고, explain이 풀링을 표기한다
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.strategies.ml import MLStrategy  # noqa: E402
from quant.utils.repro import load_snapshot_pool, save_snapshot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _df(n: int = 200, seed: int = 11, drift: float = 0.0005) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100.0 * np.cumprod(1 + rng.normal(drift, 0.02, n))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1000.0 + rng.integers(0, 500, n)},
                        index=idx)


def _strat(**kw) -> MLStrategy:
    return MLStrategy(model="logreg", train_window=100, retrain_every=20,
                      min_train=40, **kw)


# ── ① 학습 동작 + 기본 불변 ────────────────────────────────────


def test_pooled_trains_and_default_unchanged():
    df = _df()
    peers = [_df(seed=s) for s in (21, 22, 23)]
    sig_pool = _strat(pool=peers).generate_signals(df)
    assert len(sig_pool) == len(df)
    assert np.isfinite(sig_pool.to_numpy()).all()
    a = _strat().generate_signals(df)
    b = _strat(pool=None).generate_signals(df)
    assert (a.to_numpy() == b.to_numpy()).all()


# ── ② 룩어헤드 차단 ────────────────────────────────────────────


#
# ⚠️ 이 절의 검사는 2026-08-12(감사 127·128)까지 **장식이었다.** 그리고 그
#    뒤에 진짜 룩어헤드가 숨어 있었다.
#
#    옛 판은 `poisoned.index >= df.index[-1]`, 즉 **마지막 봉 하나만**
#    오염시켰다. 그 행은 라벨(다음 봉 수익)이 없어 어차피 학습에서 빠지므로,
#    날짜 필터를 통째로 지워도 결과가 똑같았다 — 변이 시험이 그것을 잡았다.
#
#    검사를 제대로 고치려다 두 결함이 연달아 나왔다.
#      감사 127 — 풀링 학습이 **통째로 죽어 있었다.** `ok &= …`가 pandas 3.0의
#                 읽기 전용 배열에서 예외를 냈고 `except: return None`이 삼켰다.
#      감사 128 — 살려 놓고 보니 **미래 행이 다 들어오고 있었다.** `.asi8`는
#                 마이크로초, `Timestamp.value`는 나노초 — 1000배 차이라
#                 `dates < cut`이 언제나 전부 참이었다.
#
#    오염은 두 가지를 만족해야 한다.
#      · **가운데**에 둘 것 — 앞쪽 블록에게는 미래이고, 라벨도 붙는 구간
#      · **수익률**을 바꿀 것 — 가격 수준만 배로 키우면 피처가 안 변한다
#
#    비교 구간은 신호가 실제로 0이 아닌 구간이어야 한다(train_window 이후).
#    그래서 아래 검사는 300봉을 쓰고 131봉부터 비교한다 — 200봉·120봉부터로
#    두었더니 그 구간이 전부 0이라 검사가 헛돌았다(대조군이 그것을 잡았다).

_LEAK_N = 300          # 신호가 0이 아닌 구간을 확보하려면 이만큼 필요하다
_LEAK_LO = 131         # 첫 예측 블록이 신호를 내기 시작하는 봉
_LEAK_CUT = 200        # 이 봉 이후를 '미래'로 본다


def _poison(peer, mask):
    """부호가 매 봉 뒤집히는 ±50% — 수익률·라벨이 통째로 오염된다."""
    out = peer.copy()
    flip = np.where(np.arange(int(mask.sum())) % 2 == 0, 1.5, 0.5)
    out.loc[mask, "close"] = out.loc[mask, "close"].to_numpy() * flip
    for col in ("open", "high", "low"):
        out.loc[mask, col] = out.loc[mask, "close"].to_numpy()
    return out


def test_pool_rows_after_cutoff_cannot_leak():
    df = _df(_LEAK_N)
    peer = _df(_LEAK_N, seed=31)
    base = _strat(pool=[peer]).generate_signals(df)
    future = _strat(pool=[_poison(peer, peer.index > df.index[_LEAK_CUT])]
                    ).generate_signals(df)
    a = base.to_numpy()[_LEAK_LO:_LEAK_CUT + 1]
    b = future.to_numpy()[_LEAK_LO:_LEAK_CUT + 1]
    assert np.array_equal(a, b), (
        f"미래 풀 행을 오염시켰더니 **과거 신호**가 {int((a != b).sum())}봉 "
        "바뀐다 — 학습 상한 필터가 동작하지 않는다(룩어헤드)")


def test_the_poison_is_strong_enough_to_be_seen():
    """탐지기 자체 시험 — 오염이 모델을 못 흔들면 위 검사는 헛것이다.

    같은 오염을 **상한 앞쪽**(정당하게 학습에 들어가는 구간)에 두면 신호가
    실제로 달라져야 한다. 이 검사가 없었다면 감사 127(풀이 죽어 있음)을
    '룩어헤드 없음 ✅'으로 읽었을 것이다 — 실제로 그럴 뻔했다.
    """
    df = _df(_LEAK_N)
    peer = _df(_LEAK_N, seed=31)
    base = _strat(pool=[peer]).generate_signals(df)
    past = _strat(pool=[_poison(peer, peer.index <= df.index[_LEAK_CUT])]
                  ).generate_signals(df)
    a = base.to_numpy()[_LEAK_LO:_LEAK_CUT + 1]
    b = past.to_numpy()[_LEAK_LO:_LEAK_CUT + 1]
    assert (a != 0).any(), "비교 구간 신호가 전부 0이다 — 위 검사가 헛돈다"
    assert not np.array_equal(a, b), (
        "학습에 들어가는 구간을 오염시켰는데도 신호가 그대로다 — "
        "풀이 학습에 안 쓰이고 있다(감사 127의 재발)")


def test_the_pool_actually_reaches_the_model(monkeypatch):
    """풀을 넣으면 결과가 달라지는가 — 감사 127의 직접 계약.

    풀링은 '표본을 늘려 잡음을 씻는' 장치다. 넣으나 마나 같다면 그것은
    보너스가 아니라 **거짓말**이다. 오디션 링에는 풀링 후보가 매일 두 개씩
    오르고, 다중검정 보정은 그 둘을 '서로 다른 시도'로 세기 때문이다.
    """
    df = _df(_LEAK_N)
    peer = _df(_LEAK_N, seed=31)
    s = _strat(pool=[peer])
    with_pool = s.generate_signals(df).to_numpy()
    assert s.pool_error_ is None, f"풀 구성이 실패했다: {s.pool_error_}"
    assert s.pool_rows_ > 0, "풀 표본이 한 행도 안 붙었다"
    without = _strat(pool=None).generate_signals(df).to_numpy()
    assert not np.array_equal(with_pool, without), (
        "풀을 넣어도 신호가 한 봉도 다르지 않다 — 풀링이 죽어 있다")


def test_a_dead_pool_leaves_a_trace():
    """조용한 실패 금지 — 죽으면 죽었다고 남겨야 한다(감사 127의 원인).

    이 침묵이 없었다면 풀링이 죽은 날 로그 한 줄이라도 남았을 것이다.
    """
    df = _df(_LEAK_N)

    class _Boom:
        """프레임인 척하다 피처 계산에서 터진다."""
        def __len__(self):
            return 200

        def __contains__(self, k):
            return True

        def __getitem__(self, k):
            raise RuntimeError("풀 프레임이 깨졌다")

    s = _strat(pool=[_Boom()])
    s.generate_signals(df)
    assert s.pool_error_, "풀이 죽었는데 아무 흔적도 안 남는다"


# ── ③ 조합·값 검증 ─────────────────────────────────────────────


def test_pool_rejects_meta_and_bad_values():
    import pytest
    with pytest.raises(ValueError, match="meta"):
        _strat(pool="peers", meta=True, label="triple")
    with pytest.raises(ValueError, match="pool"):
        _strat(pool="everything")


# ── ④ 스냅샷 로더 규칙 ─────────────────────────────────────────


def test_snapshot_pool_strictly_before_cutoff(tmp_path):
    d = str(tmp_path)
    save_snapshot(_df(60, seed=1), d, "2026-08-07", "crypto", "BTC/USDT")
    save_snapshot(_df(60, seed=2), d, "2026-08-08", "crypto", "BTC/USDT")
    save_snapshot(_df(60, seed=3), d, "2026-08-08", "us_stock", "SPY")
    # 당일(08-09) 폴더는 순회 중 채워지는 중일 수 있어 제외 — 전일 폴더 사용
    save_snapshot(_df(60, seed=4), d, "2026-08-09", "crypto", "BTC/USDT")
    pool = load_snapshot_pool(d, "2026-08-09")
    assert len(pool) == 2                      # 08-08 폴더의 2종목
    assert load_snapshot_pool(d, "2026-08-07") == []  # 그 이전 폴더 없음
    assert load_snapshot_pool(str(tmp_path / "없음"), "2026-08-09") == []


# ── ⑤ 링·explain 배선 ──────────────────────────────────────────


def test_pool_challengers_in_ring_and_explained():
    from quant.live.retrain import DEFAULT_CHALLENGERS
    pooled = [c for c in DEFAULT_CHALLENGERS if c.get("pool") == "peers"]
    assert {c["model"] for c in pooled} == {"gb", "logreg"}

    from quant.live.explain import explain_signal
    df = _df(120)
    spec = {"strategy": "ml",
            "params": {"model": "gb", "threshold": 0.55, "pool": "peers"}}
    txt = explain_signal(spec, df, 0.3)
    assert "풀링" in txt


# ── ⑥ 'universe' 모드 — 편향은 감수하되 인과성은 지킨다 (2026-08-14) ──

"""배경. "peers"는 인과성이 완벽한 대신 **스냅샷이 쌓일 때까지 아무 일도
하지 않는다.** 실측(2026-08-14, SPY 800봉): 재학습 블록 28개 중 **28개**가
풀을 못 찾아 챔피언과 신호가 한 봉도 다르지 않았다. 선발 구간까지 닿으려면
스냅샷이 ≈6개월 쌓여야 한다. 그동안 종목당 800봉이라는 ML 극소 표본은
개선할 방법이 없다.

"universe"는 **가장 최근 스냅샷 폴더**를 풀로 쓴다. 실측으로 풀 표본이
0행 → 12,280행(자기 800봉의 15배)이 됐다.

⚠️ 대가는 **생존 편향**이다 — 그 폴더의 종목 목록은 '오늘까지 살아남은'
종목이라 사후 정보다. 하지만 **시계열 룩어헤드는 아니다**: 가격 행은 학습
상한 이전만 쓰므로 미래를 잘라내도 과거 신호가 바뀌지 않는다.

이 구분이 이 모드의 존재 근거 전부다. 아래 검사가 그 구분을 못으로 박는다 —
인과성이 깨지는 순간 이 모드는 정당성을 잃는다."""


def _universe_dir(tmp_path, monkeypatch, n_peers=3, bars=400):
    """state/snapshots/<날짜>/ 에 동료 종목 스냅샷을 깔고 그곳을 보게 한다."""
    from quant.utils.repro import save_snapshot
    d = tmp_path / "state"
    for i in range(n_peers):
        save_snapshot(_df(bars, seed=100 + i), str(d), "2026-08-13",
                      "synthetic", f"P{i}")
    monkeypatch.chdir(tmp_path)
    return d


def test_universe_pool_actually_supplies_samples(tmp_path, monkeypatch):
    """peers가 0행일 상황에서 universe는 표본을 실제로 공급한다."""
    _universe_dir(tmp_path, monkeypatch)
    df = _df(400, seed=1)
    s = _strat(pool="universe")
    s.generate_signals(df)
    assert s.pool_error_ is None, s.pool_error_
    assert s.pool_rows_ > len(df), (
        f"풀 표본이 {s.pool_rows_}행 — 자기 데이터({len(df)}봉)보다 많아야 "
        "표본을 늘린 의미가 있다")


def test_universe_pool_does_not_break_causality(tmp_path, monkeypatch):
    """미래를 잘라내도 과거 신호가 한 봉도 바뀌지 않는다.

    이게 깨지면 'universe'는 생존 편향이 아니라 **룩어헤드**이고, 그 순간
    이 모드는 폐기해야 한다.
    """
    _universe_dir(tmp_path, monkeypatch)
    df = _df(400, seed=2)
    full = _strat(pool="universe").generate_signals(df).to_numpy()
    for cut in (300, 340, 380):
        part = _strat(pool="universe").generate_signals(
            df.iloc[:cut]).to_numpy()
        diff = int((np.abs(part - full[:cut]) > 1e-12).sum())
        assert diff == 0, (
            f"{cut}봉으로 자르니 과거 신호 {diff}봉이 달라졌다 — "
            "universe 풀에 미래가 새고 있다")


def test_universe_pool_survives_a_perturbed_future(tmp_path, monkeypatch):
    """미래 구간을 크게 흔들어도 과거가 그대로여야 한다(절단보다 강한 검사)."""
    _universe_dir(tmp_path, monkeypatch)
    df = _df(400, seed=3)
    full = _strat(pool="universe").generate_signals(df).to_numpy()
    poisoned = df.copy()
    cols = [c for c in ("open", "high", "low", "close") if c in poisoned]
    poisoned.loc[poisoned.index[300:], cols] *= 1.5
    got = _strat(pool="universe").generate_signals(poisoned).to_numpy()
    diff = int((np.abs(got[:300] - full[:300]) > 1e-12).sum())
    assert diff == 0, f"미래를 흔드니 과거 신호 {diff}봉이 달라졌다"


def test_universe_mode_is_a_candidate_not_a_default():
    """생존 편향을 감수하는 모드는 **강제 적용되지 않는다** — 오디션만 통과 가능."""
    import inspect

    from quant.live.retrain import DEFAULT_CHAMPION, DEFAULT_CHALLENGERS
    from quant.strategies.ml import MLStrategy

    assert MLStrategy().pool is None, "기본값이 풀링이 되면 편향이 기본이 된다"
    assert "pool" not in DEFAULT_CHAMPION["params"], (
        "기본 챔피언이 생존 편향 모드다 — 승격 없이 적용되면 안 된다")
    univ = [c for c in DEFAULT_CHALLENGERS if c.get("pool") == "universe"]
    assert {c["model"] for c in univ} == {"gb", "logreg"}, univ
    # 편향을 코드가 스스로 밝히는가 — 모르고 쓰는 것이 가장 나쁘다
    src = inspect.getsource(MLStrategy._pool_at)
    assert "생존 편향" in src


def test_an_unknown_pool_mode_is_rejected():
    import pytest as _pt

    from quant.strategies.ml import MLStrategy
    with _pt.raises(ValueError, match="universe"):
        MLStrategy(pool="whatever")
