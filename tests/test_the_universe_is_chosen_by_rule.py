"""규칙 유니버스 — 종목 선정을 사람 손에서 규칙으로 (2026-08-18).

외부 검토의 최대 지적(생존 편향)에 대한 반영. 지켜야 할 약속:
- 규칙은 사전 등록대로: 코인 BTC·ETH 고정+거래대금 상위, 한국 KODEX200
  고정+시총 상위(우선주 제외), 미국은 순위 소스 미부착을 **명시하고** 유지.
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


def test_the_rule_composes_each_market(tmp_path):
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
                     rank_crypto=_fake_crypto, rank_kr=_fake_kr)
    t = {f"{m}:{s}" for m, s in (tuple(x) for x in snap["targets"])}
    # 코인: 고정 2 + 순위 상위 3(고정 제외)
    assert {"crypto:BTC/USDT", "crypto:ETH/USDT", "crypto:SOL/USDT",
            "crypto:DOGE/USDT", "crypto:XRP/USDT"} <= t
    assert "crypto:TON/USDT" not in t, "상위 3을 넘겨 뽑았다"
    # 한국: KODEX200 고정 + 시총 상위 6
    assert "kr_stock:069500.KS" in t and "kr_stock:005930.KS" in t
    assert "kr_stock:068270.KS" in t and "kr_stock:035420.KS" not in t
    # 미국: 명시된 유지 규칙
    assert "us_stock:SPY" in t and "us_stock:QQQ" in t
    assert snap["rationale"]["us_stock"]["rule"].startswith("지수 ETF")
    assert "미부착" in snap["rationale"]["us_stock"]["note"]


def test_a_failed_market_keeps_previous_and_says_why(tmp_path):
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr)

    def boom(*a):
        raise RuntimeError("KRX 점검 중")
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
                     rank_crypto=_fake_crypto, rank_kr=boom)
    kr = [s for m, s in (tuple(x) for x in snap["targets"]) if m == "kr_stock"]
    assert "005930.KS" in kr and len(kr) == 1 + U.KR_TOP, (
        "실패한 시장이 직전 구성을 유지하지 않는다")
    assert "KRX 점검 중" in snap["rationale"]["kr_stock"]["reason"]


def test_no_snapshot_means_the_fixed_list(tmp_path):
    from quant.markets import AUTO_TARGETS
    assert U.active_targets(str(tmp_path)) == list(AUTO_TARGETS)


def test_monthly_gate(tmp_path):
    assert U.due(str(tmp_path), dt.date(2026, 8, 18)), "첫 계산도 안 하려 한다"
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr)
    assert not U.due(str(tmp_path), dt.date(2026, 8, 30)), "같은 달에 또 돈다"
    assert U.due(str(tmp_path), dt.date(2026, 9, 1)), "달이 바뀌었는데 안 돈다"


def test_changes_are_history_and_clock_versions(tmp_path):
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr)

    def kr2(asof):                     # 다음 달: 상위 6 안에서 한 종목 교체
        return ["005930.KS", "000660.KS", "373220.KS", "207940.KS",
                "005380.KS", "035720.KS", "068270.KS"]
    snap = U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
                     rank_crypto=_fake_crypto, rank_kr=kr2)
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
              rank_crypto=_fake_crypto, rank_kr=_fake_kr)

    def kr2(asof):
        return ["005930.KS", "000660.KS", "373220.KS", "207940.KS",
                "005380.KS", "035720.KS", "068270.KS"]
    U.rebuild(str(tmp_path), today=dt.date(2026, 9, 1),
              rank_crypto=_fake_crypto, rank_kr=kr2)
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
              rank_crypto=_fake_crypto, rank_kr=_fake_kr)
    st = write_docs_status(str(tmp_path), docs_path=str(tmp_path / "s.json"))
    row = st["paper"]["crypto:OLD/USDT"]
    assert row["universe_excluded"] is True, "제외 사실이 표기되지 않는다"
    assert row["history"], "장부 기록이 사라졌다 — 기록 보존 위반"


def test_the_daily_batch_reads_the_rule_universe(tmp_path, monkeypatch):
    """일일 배치가 스냅샷 목록을 실제로 쓴다 — 선언만 있고 배선이 없으면 거짓."""
    import quant.live.daily as D
    U.rebuild(str(tmp_path), today=dt.date(2026, 8, 18),
              rank_crypto=_fake_crypto, rank_kr=_fake_kr)
    seen = []
    monkeypatch.setattr(D, "run_daily_paper",
                        lambda mk, sym, **k: seen.append((mk, sym)) or
                        {"skipped": True})
    D.run_daily_paper_all(state_dir=str(tmp_path))
    assert ("crypto", "SOL/USDT") in seen and ("kr_stock", "068270.KS") in seen
    assert ("kr_stock", "105560.KS") not in seen, (
        "스냅샷이 있는데 옛 고정 목록으로 돌았다")
