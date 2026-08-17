"""횡단면 랭킹 — "오를까?"가 아니라 "누가 더 셀까?" (감사 259).

지금까지 이 시스템이 던진 질문은 하나였습니다: **"이 종목이 내일 오를까?"**
20종목에 20번 물었지만 **19종목이 같은 챔피언**을 써서 사실상 한 개의
실험이었습니다. 그 한계가 숫자로 나왔습니다(2026-08-16 실측):

    125구간 중 '그냥 보유'를 이긴 구간   **39개(31%)**
    오디션에서 실제로 이긴 전략          **buy_hold(그냥 보유)**

그래서 **다른 축**을 하나 더합니다. 같은 날 20종목을 나란히 세워 순위를
매기고 상위권일 때만 삽니다 — 시장 방향이 아니라 **상대 강도**를 봅니다.

실측(2026-08-14 스냅샷, lookback 60·상위 30%): 보유 비율이 종목마다 크게
갈립니다 — SPY 9% · NVDA 49% · SK하이닉스 68%. 지금 챔피언은 전 종목이
사실상 같은 신호를 내므로, 이것이 실제로 **새로운 정보**입니다.

⚠️ 이 파일에서 가장 중요한 검사는 **룩어헤드**입니다. 또래 시세를 내 봉에
   맞출 때 뒤채움(bfill)을 한 줄만 넣어도 **내일 가격이 오늘 순위에 실립니다.**
   그러면 백테스트가 환상적으로 좋아지고, 실전에서는 재현되지 않습니다.
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.retrain import DEFAULT_CHALLENGERS  # noqa: E402
from quant.strategies import get_strategy  # noqa: E402
from quant.strategies.cross_rank import CrossRank  # noqa: E402


def _frame(vals, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="D")
    c = pd.Series(vals, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1000.0}, index=idx)


def _snapshot(tmp_path, day: str, frames: dict) -> str:
    d = tmp_path / "snapshots" / day
    d.mkdir(parents=True)
    for name, f in frames.items():
        with gzip.open(d / f"{name}.csv.gz", "wt", encoding="utf-8") as fh:
            f.to_csv(fh)
    return str(tmp_path)


# ── ① 룩어헤드 — 이 파일의 핵심 ──────────────────────────────

def test_tomorrows_peer_price_cannot_change_todays_rank(tmp_path):
    """또래의 **미래** 가격을 바꿔도 오늘까지의 신호는 그대로여야 한다.

    뒤채움이 한 줄이라도 있으면 이 검사가 빨개진다.
    """
    n = 200
    mine = _frame([100 + i * 0.1 for i in range(n)])
    peers = {f"us_stock_P{k}": _frame([100 + i * 0.05 * (k + 1)
                                       for i in range(n)]) for k in range(6)}

    base = _snapshot(tmp_path, "2023-12-01", {**peers, "us_stock_ME": mine})
    sig_a = CrossRank(lookback=20, state_dir=base).generate_signals(mine)

    # 같은 또래인데 **마지막 40봉만** 완전히 다른 미래를 준다.
    tmp2 = tmp_path / "b"
    tmp2.mkdir()
    futured = {}
    for name, f in peers.items():
        g = f.copy()
        g.iloc[-40:, :] = g.iloc[-40:, :] * 5.0     # 미래를 폭등시킨다
        futured[name] = g
    base2 = _snapshot(tmp2, "2023-12-01", {**futured, "us_stock_ME": mine})
    sig_b = CrossRank(lookback=20, state_dir=base2).generate_signals(mine)

    cut = n - 40
    pd.testing.assert_series_equal(sig_a.iloc[:cut], sig_b.iloc[:cut])


def test_the_peer_series_is_only_forward_filled():
    """소스에 뒤채움이 있으면 안 된다 — 구조로도 못박는다."""
    src = (ROOT / "quant" / "strategies" / "cross_rank.py").read_text("utf-8")
    code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    import re
    code = re.sub(r'"""(?:.|\n)*?"""', "", code)
    for bad in ("bfill", "backfill", "interpolate", 'method="bfill"'):
        assert bad not in code, f"뒤채움({bad})이 코드에 있다 — 룩어헤드다"
    assert ".ffill()" in code, "과거 방향 채움이 없다"


def test_the_pool_folder_is_strictly_earlier(tmp_path):
    """같은 날 폴더를 쓰면 배치가 채우는 중인 파일을 읽어 재현이 깨진다."""
    from quant.utils.repro import snapshot_pool_day

    (tmp_path / "snapshots" / "2026-08-14").mkdir(parents=True)
    (tmp_path / "snapshots" / "2026-08-15").mkdir()
    assert snapshot_pool_day(str(tmp_path), "2026-08-15") == "2026-08-14"


# ── ② 순위가 실제로 순위인가 ─────────────────────────────────

def test_the_strongest_is_held_and_the_weakest_is_not(tmp_path):
    """가장 센 종목은 사고, 가장 약한 종목은 안 산다 — 그게 전부다."""
    n = 200
    strong = _frame([100 * (1.01 ** i) for i in range(n)])
    weak = _frame([100 * (0.995 ** i) for i in range(n)])
    peers = {f"us_stock_P{k}": _frame([100 + i * (k + 1) * 0.02
                                       for i in range(n)]) for k in range(6)}
    sd = _snapshot(tmp_path, "2023-12-01",
                   {**peers, "us_stock_S": strong, "us_stock_W": weak})

    s = CrossRank(lookback=20, top_frac=0.3, state_dir=sd)
    held_strong = float((s.generate_signals(strong).iloc[40:] > 0).mean())
    held_weak = float((s.generate_signals(weak).iloc[40:] > 0).mean())
    assert held_strong > 0.8, f"가장 센 종목을 {held_strong:.0%}만 들었다"
    assert held_weak < 0.2, f"가장 약한 종목을 {held_weak:.0%}나 들었다"


def test_a_wider_top_fraction_holds_more(tmp_path):
    """상위 50%가 상위 10%보다 더 자주 들어야 한다 — 손잡이가 손잡이인가."""
    n, mine = 200, None
    mine = _frame([100 + i * 0.06 for i in range(200)])
    peers = {f"us_stock_P{k}": _frame([100 + i * (k * 0.03)
                                       for i in range(n)]) for k in range(8)}
    sd = _snapshot(tmp_path, "2023-12-01", {**peers, "us_stock_ME": mine})
    narrow = CrossRank(lookback=20, top_frac=0.1, state_dir=sd)
    wide = CrossRank(lookback=20, top_frac=0.5, state_dir=sd)
    a = float((narrow.generate_signals(mine).iloc[40:] > 0).mean())
    b = float((wide.generate_signals(mine).iloc[40:] > 0).mean())
    assert b >= a, f"상위 50%({b:.0%})가 상위 10%({a:.0%})보다 적게 들었다"


# ── ③ 모르면 지어내지 않는가 ─────────────────────────────────

def test_no_peers_means_no_signal(tmp_path):
    """또래가 없으면 순위가 없다 — 0을 내고 조용히 무효 후보가 된다."""
    mine = _frame([100 + i * 0.1 for i in range(200)])
    sd = _snapshot(tmp_path, "2023-12-01", {"us_stock_ME": mine})
    sig = CrossRank(lookback=20, state_dir=sd).generate_signals(mine)
    assert (sig == 0).all(), "또래도 없이 순위를 지어냈다"


def test_too_few_peers_is_also_no_signal(tmp_path):
    """⚠️ **3종목 중 1등은 등수가 아니다.**

    또래가 0개일 때만 막으면 부족하다 — 2~3개일 때가 더 위험하다. 순위가
    나오긴 하는데 아무 의미가 없고, 화면에는 '1등이라 샀다'로 보인다.
    """
    n = 200
    mine = _frame([100 * (1.01 ** i) for i in range(n)])       # 압도적으로 셈
    weak = {f"us_stock_P{k}": _frame([100 - i * 0.05 for i in range(n)])
            for k in range(2)}                                  # 또래 2개뿐
    sd = _snapshot(tmp_path, "2023-12-01", {**weak, "us_stock_ME": mine})
    sig = CrossRank(lookback=20, min_peers=4, state_dir=sd).generate_signals(mine)
    assert (sig == 0).all(), (
        "또래 2개로 순위를 매겼다 — 최소 인원 문턱이 죽어 있다")


def test_a_missing_snapshot_dir_is_not_a_crash():
    sig = CrossRank(lookback=20,
                    state_dir="/tmp/quant-없는곳-259").generate_signals(
        _frame([100 + i * 0.1 for i in range(100)]))
    assert (sig == 0).all()


def test_the_warmup_is_flat(tmp_path):
    """모멘텀을 아직 못 재는 구간에서 사면 근거 없는 매수다."""
    n = 200
    mine = _frame([100 + i * 0.1 for i in range(n)])
    peers = {f"us_stock_P{k}": _frame([100 + i * 0.02 * k for i in range(n)])
             for k in range(6)}
    sd = _snapshot(tmp_path, "2023-12-01", {**peers, "us_stock_ME": mine})
    sig = CrossRank(lookback=60, state_dir=sd).generate_signals(mine)
    assert (sig.iloc[:60] == 0).all(), "학습 전 구간에서 포지션을 잡았다"


def test_no_rank_is_possible_while_the_peers_are_still_warming(tmp_path):
    """⚠️ 내 모멘텀만 있고 **또래 모멘텀이 아직 없는** 구간이 있다.

    또래가 나보다 늦게 상장(또는 늦게 기록 시작)하면 그렇다. 그때 비교
    대상이 0개인데 순위를 만들면 **혼자서 1등**이 된다. 내 결측만 보고
    또래 결측을 안 보면 이 구간에서 근거 없이 산다.
    """
    n = 200
    mine = _frame([100 + i * 0.1 for i in range(n)])
    # 또래는 120봉 뒤에야 시작한다 — 그 전 구간엔 또래 모멘텀이 없다.
    peers = {f"us_stock_P{k}": _frame([100 + i * 0.02 * (k + 1)
                                       for i in range(n - 120)],
                                      start="2024-04-29") for k in range(6)}
    sd = _snapshot(tmp_path, "2023-12-01", {**peers, "us_stock_ME": mine})
    sig = CrossRank(lookback=20, state_dir=sd).generate_signals(mine)
    assert (sig.iloc[:120] == 0).all(), (
        "또래 모멘텀이 없는 구간에서 순위를 지어내 매수했다")


def test_an_unknown_bar_never_becomes_a_max_short(tmp_path):
    """⚠️ 롱온리에서는 우연히 무해하지만 **숏을 켜면 치명적인** 자리.

    내 모멘텀이 아직 NaN인 워밍업 구간에서 `또래 < 나`는 전부 거짓이라
    백분위가 NaN이 아니라 **0.0**으로 계산된다. 그 0.0은 "꼴찌"로 읽히고,
    숏이 켜져 있으면 **아무것도 모르는 구간에서 최대 숏**을 잡는다.

    숏은 아직 링에 세우지 않지만, 켜는 날 이 함정이 남아 있으면 안 된다.

    ⚠️ 이 장면은 **또래가 나보다 오래됐을 때** 나온다(신규 상장 종목이 오래된
       종목들 사이에 들어오는 경우). 또래는 이미 모멘텀이 있는데 나만 아직
       없어서, 비교가 "가능해 보이지만" 내 값이 없다.
    """
    mine = _frame([100 + i * 0.1 for i in range(200)])          # 2024-01-01~
    peers = {f"us_stock_P{k}": _frame([100 + i * 0.02 * (k + 1)
                                       for i in range(400)],
                                      start="2023-06-01") for k in range(6)}
    sd = _snapshot(tmp_path, "2023-12-01", {**peers, "us_stock_ME": mine})
    sig = CrossRank(lookback=40, state_dir=sd,
                    allow_short=True).generate_signals(mine)
    assert (sig.iloc[:40] == 0).all(), (
        f"내 모멘텀도 모르는데 포지션을 잡았다: {set(sig.iloc[:40])}")


# ── ④ 설정이 말이 되는가 ─────────────────────────────────────

@pytest.mark.parametrize("kw", [
    {"top_frac": 0.0}, {"top_frac": 1.5}, {"top_frac": -0.1}, {"lookback": 1},
])
def test_a_nonsense_setting_is_refused(kw):
    """조용히 이상하게 도는 것보다 시끄럽게 멈추는 게 낫다."""
    with pytest.raises(ValueError):
        CrossRank(**kw)


def test_short_is_off_by_default():
    """하위권 공매도는 체결·차입비용·제도를 따로 검증해야 하는 별개의 일이다.

    여기서 몰래 켜지면 오디션이 실전에서 낼 수 없는 성과로 챔피언을 뽑는다.
    """
    assert CrossRank().allow_short is False
    for c in DEFAULT_CHALLENGERS:
        if c.get("strategy") == "cross_rank":
            assert not (c.get("params") or {}).get("allow_short"), (
                "링에 선 횡단면 후보가 숏을 켜고 있다")


# ── ⑤ 링에 실제로 서는가 ─────────────────────────────────────

def test_it_is_a_registered_strategy():
    s = get_strategy("cross_rank", lookback=30, top_frac=0.4)
    assert isinstance(s, CrossRank) and s.lookback == 30


def test_it_stands_in_the_audition_ring():
    """만들어 놓고 아무도 부르지 않는 전략은 없는 전략과 같다."""
    ring = [c for c in DEFAULT_CHALLENGERS if c.get("strategy") == "cross_rank"]
    combos = {(c["params"]["lookback"], c["params"]["top_frac"]) for c in ring}
    assert len(combos) == len(ring), "같은 설정이 중복돼 있다"
    # ⚠️ 개수만 세면 하나를 지워도 통과한다(변이 시험이 그 자리를 찔렀다).
    #    **짧은 기간·긴 기간·넓은 컷**이 모두 서 있어야 무엇이 효과인지 갈린다.
    assert len(ring) >= 3, f"횡단면 후보가 {len(ring)}개뿐이다"
    looks = {c["params"]["lookback"] for c in ring}
    assert min(looks) <= 20 and max(looks) >= 120, (
        f"기간 축이 안 갈린다: {sorted(looks)}")
    assert len({c["params"]["top_frac"] for c in ring}) >= 2, "상위 컷이 한 값뿐이다"


def test_it_gives_a_different_signal_than_the_champion():
    """실측 그 장면 — 챔피언과 같은 신호면 링에 세워도 대결이 성립하지 않는다."""
    from quant.live.walkforward import _snapshot_frame

    df = _snapshot_frame("state", "us_stock", "SPY")
    if df is None:
        pytest.skip("스냅샷 없음")
    champ = get_strategy("ml", model="logreg", threshold=0.55,
                         train_window=250, retrain_every=20)
    xr = get_strategy("cross_rank", lookback=60, top_frac=0.3)
    a, b = champ.generate_signals(df), xr.generate_signals(df)
    assert not a.equals(b)
    assert (b != 0).mean() > 0.02, "전 구간 관망이면 후보가 아니다"
