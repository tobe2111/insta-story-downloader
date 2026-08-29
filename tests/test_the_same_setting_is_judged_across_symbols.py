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

import os
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

_REAL_CACHE: dict = {}


def _real():
    """진짜 스냅샷으로 낸 증거 — **한 번만 계산한다.**

    ⚠️ 이 한 번이 40종목 백테스트라 **약 60초**다. 캐시가 없던 동안 이
       파일의 검사 일곱이 각자 다시 계산해서 혼자 7분을 썼고, CI의 35분
       한도(매달림 감지용)를 넘겨 잡이 잘렸다. 결과는 입력이 같으면 같으므로
       다시 계산할 이유가 없다 — 검사를 줄이지 않고 시간만 돌려받는다.
    """
    if "ev" not in _REAL_CACHE:
        _REAL_CACHE["ev"] = pooled_evidence("state")
    ev = _REAL_CACHE["ev"]
    if not ev:
        pytest.skip("스냅샷 없음")
    return ev


def test_every_symbol_is_counted_not_just_the_coins():
    """실측 그 장면 — 주식이 빠지면 20종목이 5종목으로 보인다."""
    ev = _real()
    assert ev["all"]["n"] >= 15, f"종목이 너무 적게 잡혔다: {ev['all']}"
    markets = set(ev["markets"])
    assert {"crypto", "kr_stock", "us_stock"} <= markets, markets


def test_the_stock_and_coin_verdicts_are_computed_separately():
    """두 시장이 **각각** 계산되는가 — 합쳐 버리면 이 지표는 무의미하다.

    ⚠️ 예전에는 `abs(주식 − 코인) > 0.2`를 요구했다(2026-08-23 빨간불).
       그 0.2는 그날 시장이 우연히 벌어져 있던 간격이었고, 코드가 아니라
       **시장이 움직이면 깨지는 검사**였다 — 실제로 간격이 0.184로 좁혀지자
       아무도 코드를 안 건드린 날에 빨간불이 됐다. 검사가 지켜야 할 것은
       "오늘 두 시장이 얼마나 다른가"(시장의 사정)가 아니라 "두 시장을
       따로 재고 있는가"(코드의 계약)다.
    """
    ev = _real()
    coin = (ev["markets"].get("crypto") or {}).get("sharpe_mean")
    stock = (ev.get("stocks") or {}).get("sharpe_mean")
    if coin is None or stock is None:
        pytest.skip("한쪽 시장이 비어 있다")
    # 두 값이 **완전히 같으면** 쪼개기가 깨진 것이다(같은 표본을 두 번 셌거나
    # 한쪽이 다른 쪽을 덮어썼거나).
    assert stock != coin, (
        f"주식과 코인의 값이 똑같다({stock}) — 시장별로 쪼개지지 않았다")
    # 그리고 표본이 실제로 양쪽에 있어야 한다.
    assert (ev["markets"]["crypto"].get("n") or 0) > 0
    assert (ev["stocks"].get("n") or 0) > 0


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


# ── 유니버스가 여러 밤에 나뉘어 찍힌다 (2026-08-29 실측) ────────────────

def test_a_whole_market_cannot_go_missing_because_of_the_relay():
    """어느 하루를 골라도 시장 하나가 빠지던 것 — 이 결함의 재현 검사.

    밤 배치가 이어달리기 + 멱등 가드로 바뀌면서 유니버스가 **여러 밤에
    나뉘어** 찍힌다. 실측 장부:

        2026-08-26  32종목  한국·미국   ← '가장 많이 담긴 날'
        2026-08-28  17종목  코인·한국·미국
        2026-08-29   5종목  코인

    '가장 많이 담긴 날'을 고르면 **코인이 통째로 빠진 채** 화면에 "전체
    32종목"이 찍힌다. 이 지표의 존재 이유가 "주식과 코인이 반대 방향이더라"
    인데 정작 한쪽을 안 보게 된다 — 그리고 빠진 자리는 '0종목'이 아니라
    **아예 줄이 없어서** 화면만 봐서는 알 수 없다.
    """
    ev = _real()
    assert {"crypto", "kr_stock", "us_stock"} <= set(ev["markets"]), (
        f"시장 하나가 통째로 빠졌다: {sorted(ev['markets'])}")


def test_it_says_out_loud_that_it_pooled_several_nights():
    """며칠에서 모았으면 **문장이 그렇게 말한다**.

    ⚠️ 안 말하면 여러 밤을 모은 숫자가 '하루치'로 읽힌다. 이 저장소가
       반복해서 막아 온 조용한 과장이고, 숫자를 부풀리지 않아도 **읽는
       방식**만으로 과장이 된다.
    """
    ev = _real()
    assert ev.get("days"), "어느 밤에서 모았는지 안 남긴다"
    assert ev["asof"] == ev["days"][-1], "asof가 가장 최근 밤이 아니다"
    text = format_pooled(ev)
    if len(ev["days"]) > 1:
        assert "밤 스냅샷" in text and ev["days"][0] in text, (
            f"여러 밤에서 모았는데 문장이 하루처럼 말한다: {text.splitlines()[0]}")
    else:
        assert "밤 스냅샷" not in text, "하루치인데 여러 밤인 척한다"


def test_each_symbol_carries_the_night_it_came_from():
    """종목마다 **어느 밤 스냅샷**인지 붙어 있다 — 안 붙으면 되짚을 수 없다."""
    ev = _real()
    for row in ev["symbols"]:
        assert row.get("asof") in ev["days"], f"밤 표식이 없다: {row['key']}"


def test_only_the_newest_snapshot_of_a_symbol_is_used(tmp_path):
    """한 종목이 여러 밤에 찍혔으면 **가장 최근 것 하나만** 센다.

    ⚠️ 안 그러면 같은 종목이 여러 번 표에 들어가 표본 수가 부풀고, t가
       근거 없이 커진다 — 관측을 늘리지 않고 숫자만 늘리는 종류다.
    """
    from quant.live.crosssection import latest_per_symbol

    root = tmp_path / "snapshots"
    for day, names in (("2026-08-01", ["crypto_BTC_USDT", "us_stock_AAPL"]),
                       ("2026-08-03", ["crypto_BTC_USDT"])):
        (root / day).mkdir(parents=True)
        for n in names:
            (root / day / f"{n}.csv.gz").write_bytes(b"")
    got = latest_per_symbol(str(tmp_path))
    assert set(got) == {"crypto:BTC/USDT", "us_stock:AAPL"}
    assert "2026-08-03" in got["crypto:BTC/USDT"], "옛 밤을 골랐다"
    assert "2026-08-01" in got["us_stock:AAPL"], "그 밤에만 있는 종목을 놓쳤다"


def test_the_lookback_window_is_respected(tmp_path):
    """대조군 — 창 밖의 묵은 스냅샷은 **안 끌어온다**.

    창이 없으면 반년 전 데이터로 오늘의 챔피언을 평가하게 되고, 그건
    증거가 아니라 소음이다.
    """
    from quant.live.crosssection import latest_per_symbol

    root = tmp_path / "snapshots"
    for day in ("2026-01-01", "2026-08-01", "2026-08-02", "2026-08-03"):
        (root / day).mkdir(parents=True)
        (root / day / "us_stock_SPY.csv.gz").write_bytes(b"")
    (root / "2026-01-01" / "crypto_BTC_USDT.csv.gz").write_bytes(b"")
    got = latest_per_symbol(str(tmp_path), lookback=3)
    assert "crypto:BTC/USDT" not in got, "창 밖의 묵은 스냅샷을 끌어왔다"
    assert "2026-08-03" in got["us_stock:SPY"]


def test_an_explicit_folder_still_means_that_one_night():
    """폴더를 명시하면 **그 하루만** 쓴다 — 재현 검증이 그것에 기댄다."""
    from quant.live.crosssection import latest_per_symbol, pooled_evidence

    day = sorted({os.path.dirname(p)
                  for p in latest_per_symbol("state").values()})[-1]
    ev = pooled_evidence("state", snapshot=day)
    if ev:
        assert ev["days"] == [os.path.basename(day)]
