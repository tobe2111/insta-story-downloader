"""같은 설정을 20번 따로 검증하고 있었다 (감사 255).

오디션은 종목마다 **따로** 열립니다. BTC 챔피언은 BTC 800봉으로만, SPY
챔피언은 SPY 800봉으로만 검증됩니다. 그런데 실측(2026-08-15):

    20종목 중 **19종목이 똑같은 챔피언**을 씁니다
    (ml / logreg / 문턱 0.55 / 학습창 250)

같은 설정을 20번 검증하면서 **매번 1/20의 증거만** 쓰고 있었습니다. 결과가
숫자로 나옵니다 — 오디션 **179회 중 승격 1회(0.6%)**, 그중 **93%**가
"후보가 챔피언을 통계적으로 못 이김"입니다. 문턱이 높아서가 아니라
**표본이 모자라 아무것도 증명되지 않는** 상태입니다.

그래서 반대로 잽니다. 오늘의 챔피언 설정을 전 종목에 그대로 적용해 몇
곳에서 통했는지 셉니다 — 종목 하나가 한 표입니다.

실측(2026-08-14 스냅샷):

    주식(한국+미국)  15종목 중 13 플러스(87%) · 샤프평균 +0.48 · **t = +4.37**
    코인              5종목 중  1 플러스(20%) · 샤프평균 -0.76 · **t = -1.76**

**주식과 코인이 반대 방향입니다.** 종목별 오디션은 이것을 영영 볼 수
없습니다.

⚠️ 이 숫자는 **인샘플**입니다(감사 240과 같은 주의). 그리고 종목 간
   상관이 있어 유효 표본은 종목 수보다 작습니다. 그래서 이 지표는
   **판정이 아니라 관찰**로만 남깁니다 — 승격을 자동으로 바꾸지 않습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.crosssection import (  # noqa: E402
    _split_key,
    _stats,
    format_pooled,
    pooled_evidence,
)


# ── 파일 이름에서 시장·종목을 가르는가 ────────────────────────

@pytest.mark.parametrize("name,want", [
    ("crypto_BTC_USDT.csv.gz", ("crypto", "BTC/USDT")),
    ("kr_stock_005930.KS.csv.gz", ("kr_stock", "005930.KS")),
    ("us_stock_SPY.csv.gz", ("us_stock", "SPY")),
    ("kr_stock_069500.KS.csv.gz", ("kr_stock", "069500.KS")),
])
def test_the_market_prefix_is_split_correctly(name, want):
    """⚠️ 시장 이름에 밑줄이 있다(`kr_stock`).

    `split("_", 1)`로 자르면 주식이 통째로 빠진다 — 처음 이 분석을 돌렸을 때
    20종목 중 5개(코인)만 나왔고, 그 숫자로 결론을 낼 뻔했다.
    """
    assert _split_key(name) == want


def test_a_stranger_file_is_ignored():
    assert _split_key("portfolio_ALL.csv.gz") is None
    assert _split_key("읽을수없음.txt") is None


# ── 표본 통계 ─────────────────────────────────────────────────

def test_the_t_needs_at_least_two_symbols():
    """한 종목으로는 t를 만들 수 없다 — 모르면 None이다."""
    s = _stats([0.5], wins=1)
    assert s["n"] == 1 and s["t"] is None and s["sharpe_sd"] is None


def test_no_symbols_is_not_a_zero():
    s = _stats([], wins=0)
    assert s["n"] == 0 and s["win_rate"] is None and s["t"] is None


def test_identical_symbols_give_no_t():
    """분산이 0이면 t가 무한대다 — 숫자를 지어내지 않는다."""
    assert _stats([0.5, 0.5, 0.5], wins=3)["t"] is None


def test_the_sign_of_t_follows_the_mean():
    up = _stats([1.0, 0.8, 1.2, 0.9], wins=4)
    down = _stats([-1.0, -0.8, -1.2, -0.9], wins=0)
    assert up["t"] > 0 and down["t"] < 0
    assert up["win_rate"] == 1.0 and down["win_rate"] == 0.0


# ── 진짜 스냅샷으로 도는가 ────────────────────────────────────

def _real():
    ev = pooled_evidence("state")
    if not ev:
        pytest.skip("스냅샷 없음")
    return ev


def test_every_symbol_is_counted_not_just_the_coins():
    """실측 그 장면 — 주식이 빠지면 20종목이 5종목으로 보인다."""
    ev = _real()
    assert ev["all"]["n"] >= 15, f"종목이 너무 적게 잡혔다: {ev['all']}"
    markets = set(ev["markets"])
    assert {"crypto", "kr_stock", "us_stock"} <= markets, markets


def test_the_stock_and_coin_verdicts_actually_differ():
    """두 시장이 같은 답을 주면 이 지표는 아무것도 안 알려준다."""
    ev = _real()
    coin = (ev["markets"].get("crypto") or {}).get("sharpe_mean")
    stock = (ev.get("stocks") or {}).get("sharpe_mean")
    if coin is None or stock is None:
        pytest.skip("한쪽 시장이 비어 있다")
    assert abs(stock - coin) > 0.2, (
        f"주식({stock})과 코인({coin})이 갈리지 않는다 — 전제 확인 필요")


def test_a_half_written_snapshot_day_is_not_used(tmp_path):
    """⚠️ 하루가 통째로 안 찍히는 날이 있다.

    실측(2026-08-15): 그날 스냅샷에는 **코인 5종목만** 저장됐다(주식 배치가
    기록을 못 남김). '가장 최근'을 그대로 쓰면 "20종목 중 14 플러스
    (t=+0.97)"가 "5종목 중 1 플러스(t=-1.39)"가 되어 **정반대 결론**이 나온다.
    """
    from quant.live.crosssection import _fullest_snapshot

    snaps = tmp_path / "snapshots"
    (snaps / "2026-08-14").mkdir(parents=True)
    (snaps / "2026-08-15").mkdir()
    for i in range(20):
        (snaps / "2026-08-14" / f"us_stock_S{i}.csv.gz").write_bytes(b"x")
    for i in range(5):
        (snaps / "2026-08-15" / f"crypto_C{i}.csv.gz").write_bytes(b"x")
    got = _fullest_snapshot(str(tmp_path))
    assert got.endswith("2026-08-14"), f"반쪽 날을 골랐다: {got}"


def test_a_complete_newer_day_wins(tmp_path):
    """대조군 — 최신 날이 멀쩡하면 최신을 써야 한다(옛날에 눌러앉으면 안 된다)."""
    from quant.live.crosssection import _fullest_snapshot

    snaps = tmp_path / "snapshots"
    for day in ("2026-08-14", "2026-08-15"):
        (snaps / day).mkdir(parents=True)
        for i in range(20):
            (snaps / day / f"us_stock_S{i}.csv.gz").write_bytes(b"x")
    assert _fullest_snapshot(str(tmp_path)).endswith("2026-08-15")


def test_it_never_forgets_to_say_it_is_in_sample():
    """이 표식이 빠지면 화면이 실전 성적으로 읽는다(감사 240)."""
    ev = _real()
    assert ev["in_sample"] is True
    assert "인샘플" in ev["note"] and "상관" in ev["note"]


def test_the_human_line_says_the_caveat_too():
    text = format_pooled(_real())
    assert "횡단면 증거" in text and "인샘플" in text
    for label in ("전체", "주식", "코인"):
        assert label in text, f"{label} 묶음이 문장에 없다"


def test_an_empty_state_is_not_an_error():
    """스냅샷이 없으면 빈 값 — 지어내지 않고 죽지도 않는다."""
    assert pooled_evidence("/tmp/quant-없는곳-254") == {}
    assert "아직 없습니다" in format_pooled({})


# ── 배치가 실어 보내는가 ──────────────────────────────────────

def test_the_batch_ships_it_to_the_site():
    """계산해도 안 실으면 화면은 영영 빈칸이다(감사 229)."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["crosssection"] = xs' in src


def test_it_does_not_change_promotion():
    """관찰이지 판정이 아니다 — 승격 규칙을 건드리면 안 된다.

    표본이 인샘플이고 종목 간 상관이 있어 t가 부풀려져 있다. 이 값으로
    자동 승격을 바꾸면 그 편향이 그대로 매매에 들어간다.
    """
    retrain = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert "crosssection" not in retrain, (
        "횡단면 지표가 승격 경로에 들어갔다 — 관찰로만 두기로 한 값이다")
