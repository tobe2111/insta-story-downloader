"""규칙 유니버스 — 종목 선정을 사람 손에서 규칙으로 (2026-08-18).

외부 검토의 최대 지적(생존 편향)에 대한 반영. 지켜야 할 약속:
- 규칙은 사전 등록대로: 코인 BTC·ETH 고정+거래대금 상위, 한국 KODEX200
  고정+시총 상위(우선주 제외), 미국 SPY·QQQ 고정+시총 상위(나스닥 공개
  스크리너 — 2026-08-18 부착, 복수클래스·워런트 표기 제외).
- 조회 실패 시장은 직전 구성 유지 + 사유 기록 — 즉흥 선정 금지.
- 리밸런스는 매월 1회. 변경은 이력에 남고 판정 시계의 버전에 실린다(리셋 없음).
- 스냅샷이 없으면 기존 고정 목록(AUTO_TARGETS) 그대로 — 조용한 공백 없음.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.universe as U                              # noqa: E402


def _fake_crypto():
    return ["BTC/USDT", "SOL/USDT", "ETH/USDT", "DOGE/USDT", "XRP/USDT",
            "TON/USDT", "ADA/USDT"]


def _fake_kr(asof):
    return ["005930.KS", "000660.KS", "373220.KS", "207940.KS",
            "005380.KS", "068270.KS", "051910.KS", "035420.KS"]


def _fake_us():
    return ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA"]


def test_the_rule_composes_each_market(tmp_path):
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
                     rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)
    t = {f"{m}:{s}" for m, s in (tuple(x) for x in snap["targets"])}
    # ⚠️ 개수는 **규칙 상수에서 읽는다**(2026-08-19). 예전에는 "상위 3"처럼
    #    숫자를 검사에 박아 뒀는데, 자산군을 늘리려고 상수를 바꾸자 규칙이
    #    옳게 동작하는데도 검사가 빨개졌다. 지켜야 할 계약은 **"코어는 반드시
    #    들어가고, 선언한 개수보다 더 뽑지 않는다"**이지 특정 숫자가 아니다.
    def _count(prefix):
        return len([1 for x in t if x.startswith(prefix)])

    # 코인: 고정 코어 + 순위 상위 CRYPTO_TOP(코어 제외)
    assert {"crypto:BTC/USDT", "crypto:ETH/USDT"} <= t, "코어가 빠졌다"
    assert _count("crypto:") <= len(U.CRYPTO_CORE) + U.CRYPTO_TOP, (
        "선언한 개수보다 많이 뽑았다")
    # 한국: KODEX200 + 자산군 ETF 고정 + 시총 상위 KR_TOP
    assert "kr_stock:069500.KS" in t and "kr_stock:005930.KS" in t
    for core in U.KR_ASSET_CORE:
        assert f"kr_stock:{core}" in t, f"자산군 코어 {core}가 빠졌다"
    assert _count("kr_stock:") <= len(U.KR_CORE) + len(U.KR_ASSET_CORE) \
        + U.KR_TOP, "선언한 개수보다 많이 뽑았다"
    # 미국: SPY·QQQ + 자산군 ETF 고정 + 시총 상위 US_TOP
    assert "us_stock:SPY" in t and "us_stock:QQQ" in t
    for core in U.US_ASSET_CORE:
        assert f"us_stock:{core}" in t, f"자산군 코어 {core}가 빠졌다"
    assert "us_stock:NVDA" in t and "us_stock:META" in t
    assert _count("us_stock:") <= len(U.US_CORE) + len(U.US_ASSET_CORE) \
        + U.US_TOP, "선언한 개수보다 많이 뽑았다"
    assert snap["rationale"]["us_stock"]["rule"].startswith("지수 ETF")
    assert snap["rationale"]["us_stock"]["top10"][0] == "NVDA"


def test_a_failed_market_keeps_previous_and_says_why(tmp_path):
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)

    def boom(*a):
        raise RuntimeError("KRX 점검 중")
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
                     rank_crypto=_fake_crypto, rank_kr=boom, rank_us=_fake_us)
    kr = [s for m, s in (tuple(x) for x in snap["targets"]) if m == "kr_stock"]
    assert "005930.KS" in kr and len(kr) == len(U.KR_CORE) \
        + len(U.KR_ASSET_CORE) + U.KR_TOP, (
        "실패한 시장이 직전 구성을 유지하지 않는다")
    assert "KRX 점검 중" in snap["rationale"]["kr_stock"]["reason"]


def test_no_snapshot_means_the_fixed_list(tmp_path):
    from quant.markets import AUTO_TARGETS
    assert U.active_targets(str(tmp_path)) == list(AUTO_TARGETS)


def test_monthly_gate(tmp_path):
    assert U.due(str(tmp_path), dt.date(2026, 8, 18)), "첫 계산도 안 하려 한다"
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)
    assert not U.due(str(tmp_path), dt.date(2026, 8, 30)), "같은 달에 또 돈다"
    assert U.due(str(tmp_path), dt.date(2026, 9, 1)), "달이 바뀌었는데 안 돈다"


def test_changes_are_history_and_clock_versions(tmp_path):
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)

    def kr2(asof):                     # 다음 달: 상위 6 안에서 한 종목 교체
        return ["005930.KS", "000660.KS", "373220.KS", "207940.KS",
                "005380.KS", "035720.KS", "068270.KS"]
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
                     rank_crypto=_fake_crypto, rank_kr=kr2, rank_us=_fake_us)
    last = snap["history"][-1]
    assert last["on"] == "2026-09-01"
    assert any("035720" in a for a in last["added"])
    assert any("068270" in r for r in last["removed"])
    # 판정 시계 이력 재료 — 리셋이 아니라 공개
    vers = U.version_entries(str(tmp_path), after="2026-08-13")
    assert any(v["axis"] == "유니버스" and v["on"] == "2026-09-01"
               for v in vers), vers


def test_the_clock_lists_universe_changes_without_reset(tmp_path):
    """유니버스가 바뀌어도 판정 시계는 흐르고, 이력에는 실린다."""
    from quant.live.daily import STRUCTURE_EPOCH, _generation_info
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)

    def kr2(asof):
        return ["005930.KS", "000660.KS", "373220.KS", "207940.KS",
                "005380.KS", "035720.KS", "068270.KS"]
    U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
              rank_crypto=_fake_crypto, rank_kr=kr2, rank_us=_fake_us)
    g = _generation_info(str(tmp_path))
    assert g["since"] == STRUCTURE_EPOCH, "유니버스 변경이 시계를 리셋했다"
    assert any(v["axis"] == "유니버스" for v in g["versions"]), g["versions"]


def test_excluded_symbols_keep_their_ledger_and_get_a_flag(tmp_path):
    """빠진 종목의 장부는 남고, status.json에 제외 표식이 붙는다."""
    import os
    from quant.live.daily import write_docs_status
    os.makedirs(tmp_path / "paper", exist_ok=True)
    (tmp_path / "paper" / "crypto_OLD_USDT.json").write_text(json.dumps({
        "market": "crypto", "symbol": "OLD/USDT", "start_cash": 10000,
        "history": [{"date": "2026-08-15", "equity": 10000,
                     "return_pct": 0.0}]}), "utf-8")
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)
    st = write_docs_status(str(tmp_path), docs_path=str(tmp_path / "s.json"))
    row = st["paper"]["crypto:OLD/USDT"]
    assert row["universe_excluded"] is True, "제외 사실이 표기되지 않는다"
    assert row["history"], "장부 기록이 사라졌다 — 기록 보존 위반"


def test_the_daily_batch_reads_the_rule_universe(tmp_path, monkeypatch):
    """일일 배치가 스냅샷 목록을 실제로 쓴다 — 선언만 있고 배선이 없으면 거짓."""
    import quant.live.daily as D
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)
    seen = []
    monkeypatch.setattr(D, "run_daily_paper",
                        lambda mk, sym, **k: seen.append((mk, sym)) or
                        {"skipped": True})
    D.run_daily_paper_all(state_dir=str(tmp_path))
    assert ("crypto", "SOL/USDT") in seen and ("kr_stock", "068270.KS") in seen
    assert ("kr_stock", "105560.KS") not in seen, (
        "스냅샷이 있는데 옛 고정 목록으로 돌았다")


# ── 미국 순위 소스 (2026-08-18 부착) ────────────────────────────

def test_us_ranking_parses_and_excludes_share_class_notation():
    """스크리너 파싱: 시총 정렬·중복 제거·복수클래스(점·캐럿) 제외.

    KR의 우선주 제외와 같은 원리 — 같은 회사를 두 번 세면 분산이 명목만
    늘어난다. 시총 문자열($·콤마)도 그대로 파싱돼야 한다.
    """
    rows = [
        {"symbol": "AAPL", "marketCap": "3,000,000,000,000"},
        {"symbol": "MSFT", "marketCap": "$3,100,000,000,000.00"},
        {"symbol": "BRK.A", "marketCap": "900,000,000,000"},   # 복수 클래스
        {"symbol": "SPY^W", "marketCap": "500,000,000,000"},   # 워런트 표기
        {"symbol": "AAPL", "marketCap": "2,999,000,000,000"},  # 거래소 중복
        {"symbol": "NOCAP", "marketCap": ""},                  # 시총 없음
        {"symbol": "TINY", "marketCap": "1000"},
    ]
    ranked = U._rank_us(fetch_rows=lambda: rows)
    assert ranked == ["MSFT", "AAPL", "TINY"], f"순위가 틀렸다: {ranked}"


def test_us_failure_keeps_previous_and_says_why(tmp_path):
    """미국 조회 실패도 다른 시장과 같은 원칙 — 직전 구성 유지 + 사유.

    ⚠️ 2026-08-20에 계약이 조금 날카로워졌다(감사 296). 예전에는 실패하면
       그 시장을 **통째로** 직전 구성으로 되돌렸는데, 그러면 순위와 무관한
       고정 코어(금·국채·리츠 ETF)까지 함께 버려졌다. 이제 코어는 언제나
       들어가고 **순위로 뽑는 꼬리만** 직전 것을 쓴다. 그래서 표식 이름도
       `kept_previous`(시장 전체) → `ranking_failed` + `kept_previous_tail`
       (꼬리만)로 바뀌었다. 지켜야 할 것 — 직전 종목이 남고 사유가 적힌다 —
       은 그대로다.
    """
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=_fake_us)

    def boom():
        raise RuntimeError("스크리너 점검 중")
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
                     rank_crypto=_fake_crypto, rank_kr=_fake_kr, rank_us=boom)
    us = [s for m, s in (tuple(x) for x in snap["targets"]) if m == "us_stock"]
    assert "NVDA" in us and len(us) == len(U.US_CORE) \
        + len(U.US_ASSET_CORE) + U.US_TOP, (
        "실패한 시장이 직전 구성을 유지하지 않는다")
    r = snap["rationale"]["us_stock"]
    assert r["ranking_failed"] is True and r["core_applied"] is True
    assert "NVDA" in r["kept_previous_tail"], (
        "순위가 죽었으면 꼬리는 직전 것을 써야 한다")
    assert "스크리너 점검 중" in r["reason"]
    # 고정 코어는 실패와 무관하게 들어간다 — 이것이 이번 감사의 요지다.
    for sym in U.US_ASSET_CORE:
        assert sym in us, f"{sym}은 순위가 필요 없는 고정 코어인데 빠졌다"


def test_us_empty_screener_is_a_failure_not_an_empty_universe():
    """빈 표를 받으면 예외 — 조용히 0종목이 되면 미국 매매가 소리 없이 꺼진다."""
    import pytest
    with pytest.raises(RuntimeError):
        U._rank_us(fetch_rows=lambda: [])
