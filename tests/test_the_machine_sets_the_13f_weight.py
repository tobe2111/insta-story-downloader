"""13F 오버레이 세기를 **기계가 증거로** 정한다 — 사람이 손으로 크게 안 잡는다.

사장님 지시(2026-09-23): "13F 영향을 상당히 크게." 방침(2026-08-27): 매매
로직은 기계가 개선한다. 그래서 상한만 크게 열고, 얼마를 쓸지는 과거 13F
기록의 앞선 성적으로 정한다(quant.live.thirteenf_tune).

이 검사가 지키는 계약(대조군을 짝지어 둔다):
  ① point-in-time 이력은 **제출일**로 재생한다 — 보고 기준일로 앞당기면
     미래를 훔쳐본다. cluster_asof는 그 날 공개돼 있던 것만 돌려준다.
  ② 겹쳐 담긴 종목이 뒤에 더 오르면 t가 양수, 덜 오르면 음수(대조군).
  ③ 증거가 없으면(관측 부족·t 낮음·차이≤0) 세기는 **중립(0.15)**. 낡은
     참고에 믿음만으로 크게 걸지 않는다.
  ④ 강한 증거가 있을 때만 상한 쪽으로 오른다.
  ⑤ 세기가 아무리 커도 관망(0)은 매수로 안 바뀐다(단독 트리거 아님 — 유지).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.thirteenf as TF               # noqa: E402
import quant.live.thirteenf_overlay as OV       # noqa: E402
import quant.live.thirteenf_tune as TU          # noqa: E402
import quant.live.intraday_us as IU             # noqa: E402


# ── ① point-in-time 이력 ─────────────────────────────────────────
def test_history_is_replayed_by_filing_date_not_report_date():
    filings_by_cik = {
        "0001067983": [
            {"filed": "2026-05-15", "report": "2026-03-31",
             "holdings": [{"issuer": "APPLE INC", "cusip": "037833100"}]},
            {"filed": "2026-08-14", "report": "2026-06-30",
             "holdings": [{"issuer": "APPLE INC", "cusip": "037833100"},
                          {"issuer": "NVIDIA CORP", "cusip": "67066G104"}]},
        ],
        "0001649339": [
            {"filed": "2026-08-14", "report": "2026-06-30",
             "holdings": [{"issuer": "NVIDIA CORP", "cusip": "67066G104"}]},
        ],
    }
    hist = TF.build_cluster_history(filings_by_cik)
    assert [h["as_of"] for h in hist] == ["2026-05-15", "2026-08-14"]
    # 5/15 시점: AAPL 1명만
    assert TF.cluster_asof(hist, "2026-06-01")["AAPL"]["count"] == 1
    assert "NVDA" not in TF.cluster_asof(hist, "2026-06-01")
    # 8/20 시점: AAPL 1명(버크셔) · NVDA 2명(버크셔+사이언)
    c = TF.cluster_asof(hist, "2026-08-20")
    assert c["AAPL"]["count"] == 1 and c["NVDA"]["count"] == 2


def test_cluster_asof_is_empty_before_the_first_filing():
    """대조군 — 제출 전 날짜에는 아무것도 공개돼 있지 않다(미래 참조 방지)."""
    hist = TF.build_cluster_history({"0001067983": [
        {"filed": "2026-05-15", "report": "2026-03-31",
         "holdings": [{"issuer": "APPLE INC", "cusip": "037833100"}]}]})
    assert TF.cluster_asof(hist, "2026-01-01") == {}
    assert TF.cluster_asof([], "2026-05-20") == {}


# ── ② 앞선 성적 측정 (관측 단위 = 분기 제출일) ──────────────────
import random as _random   # noqa: E402


def _walk(seed, days, drift, start="2024-01-01", noise=0.01):
    """드리프트+잡음 있는 일봉 랜덤워크 — 앞선 성적에 분산이 생긴다."""
    rng = _random.Random(seed)
    out, px = [], 100.0
    d = pd.Timestamp(start)
    for _ in range(days):
        out.append((d.strftime("%Y-%m-%d"), px))
        px *= (1 + drift + rng.uniform(-noise, noise))
        d += pd.Timedelta(days=1)
    return out


def _quarterly_history(n=14, cluster_syms=("AAPL",)):
    """분기마다(약 90일) AAPL이 겹쳐 담긴 point-in-time 이력 n개."""
    hist, d = [], pd.Timestamp("2024-02-01")
    for _ in range(n):
        hist.append({"as_of": d.strftime("%Y-%m-%d"),
                     "cluster": {s: {"count": 2, "filers": ["a", "b"]}
                                 for s in cluster_syms}})
        d += pd.Timedelta(days=90)
    return hist


def TF_measure(hist, prices):
    return TU.measure_edge(hist, lambda s: prices.get(s),
                           ["AAPL", "MSFT"], horizon=20)


def test_a_cluster_name_that_outperforms_gives_positive_t():
    hist = _quarterly_history()
    prices = {"AAPL": _walk(1, 1400, 0.004),    # 겹친 종목: 상승 드리프트
              "MSFT": _walk(2, 1400, 0.0)}       # 비겹침: 평평
    edge = TF_measure(hist, prices)
    assert edge["n"] >= 8 and edge["mean_diff"] > 0 and edge["t"] > 0


def test_a_cluster_name_that_underperforms_gives_negative_t():
    """대조군 — 겹친 종목이 오히려 덜 오르면 t가 음수다."""
    hist = _quarterly_history()
    prices = {"AAPL": _walk(1, 1400, -0.003),   # 겹친 종목: 하락
              "MSFT": _walk(2, 1400, 0.003)}
    edge = TF_measure(hist, prices)
    assert edge["mean_diff"] < 0 and edge["t"] < 0


def test_no_cluster_observation_measures_nothing():
    """대조군 — 겹친 종목이 하나도 없으면 잴 게 없다(n=0)."""
    hist = [{"as_of": r["as_of"], "cluster": {}} for r in _quarterly_history()]
    prices = {"AAPL": _walk(1, 1400, 0.004), "MSFT": _walk(2, 1400, 0.0)}
    edge = TF_measure(hist, prices)
    assert edge["n"] == 0


# ── ③④ 세기 결정 (증거 → 세기) ──────────────────────────────────
def test_weak_or_missing_evidence_stays_neutral():
    assert OV.choose_strength(None)["bonus"] == OV.NEUTRAL_BONUS
    assert OV.choose_strength({"n": 5, "t": 9, "mean_diff": 0.1})["bonus"] == OV.NEUTRAL_BONUS
    assert OV.choose_strength({"n": 999, "t": 0.3, "mean_diff": 0.01})["bonus"] == OV.NEUTRAL_BONUS


def test_negative_edge_never_raises_the_weight():
    """대조군 — 겹친 종목이 못했으면 세기를 절대 안 올린다."""
    r = OV.choose_strength({"n": 999, "t": 5.0, "mean_diff": -0.02})
    assert r["bonus"] == OV.NEUTRAL_BONUS


def test_strong_evidence_raises_toward_the_ceiling():
    r = OV.choose_strength({"n": 999, "t": 5.0, "mean_diff": 0.02})
    assert r["bonus"] == OV.BONUS_CEILING
    assert OV.BONUS_CEILING > OV.NEUTRAL_BONUS       # 상한이 실제로 크다


def test_the_ceiling_is_large():
    """사장님 지시대로 상한이 '상당히 크게' 열려 있다(최대 +100%)."""
    assert OV.BONUS_CEILING >= 0.5
    assert max(OV.STRENGTH_CHOICES) == OV.BONUS_CEILING


# ── run_tune 파이프라인 ──────────────────────────────────────────
def test_run_tune_with_strong_edge_writes_a_larger_weight(tmp_path):
    prices = {"AAPL": _walk(1, 1400, 0.004),   # 겹친 종목이 유의하게 앞선다
              "MSFT": _walk(2, 1400, 0.0)}
    out = TU.run_tune(str(tmp_path), history=_quarterly_history(),
                      price_lookup=lambda s: prices.get(s),
                      universe=["AAPL", "MSFT"])
    assert out["strength"] > OV.NEUTRAL_BONUS, out
    assert TU.load_strength(str(tmp_path)) == out["strength"]


def test_refresh_history_builds_a_point_in_time_series_from_edgar(tmp_path):
    """EDGAR 조회 경로 — 여러 분기 제출을 받아 제출일 순 이력을 만든다."""
    filings = [("0001234567-26-000003", "2026-06-01", "2026-03-31"),
               ("0001234567-26-000002", "2026-03-01", "2025-12-31"),
               ("0001234567-26-000001", "2025-12-01", "2025-09-30")]
    info = ('<?xml version="1.0"?><informationTable><infoTable>'
            '<nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip>'
            '<value>1</value></infoTable></informationTable>')

    def fetch(url, timeout=12.0):
        if "submissions" in url:
            return json.dumps({"filings": {"recent": {
                "form": ["13F-HR"] * len(filings),
                "accessionNumber": [a for a, _, _ in filings],
                "filingDate": [f for _, f, _ in filings],
                "reportDate": [r for _, _, r in filings]}}})
        if "index.json" in url:
            return json.dumps({"directory": {"item": [{"name": "it.xml"}]}})
        return info

    hist = TF.refresh_history(str(tmp_path), fetch=fetch,
                              filers={"0001067983": "Berkshire"})
    assert [h["as_of"] for h in hist] == ["2025-12-01", "2026-03-01", "2026-06-01"]
    assert all(h["cluster"]["AAPL"]["count"] == 1 for h in hist)
    assert TF.load_history(str(tmp_path)) == hist    # 캐시 왕복


def test_run_tune_without_data_falls_back_to_neutral(tmp_path):
    """대조군 — 이력·시세가 없으면 중립(0.15). 못 잰 것을 큰 확신으로 안 읽는다."""
    out = TU.run_tune(str(tmp_path), history=[],
                      price_lookup=lambda s: None, universe=["AAPL"])
    assert out["strength"] == OV.NEUTRAL_BONUS
    assert TU.load_strength(str(tmp_path)) == OV.NEUTRAL_BONUS


def test_load_strength_defaults_to_neutral_when_never_tuned(tmp_path):
    assert TU.load_strength(str(tmp_path)) == OV.NEUTRAL_BONUS


# ── ⑤ 세기가 커져도 관망은 매수 안 됨 (통합) ─────────────────────
class _PartialLong:
    def generate_signals(self, df):
        return pd.Series(0.5, index=df.index)


class _Flat:
    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index)


def _ubars(n=80, freq="1h", end="2026-08-19T14:00:00"):
    idx = pd.date_range(end=end, periods=n, freq=freq)
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px}, index=idx)


_SNAP = {"cluster": {"AAPL": {"count": 3, "filers": ["a", "b", "c"],
                              "as_of": "2026-06-30"}}}
OPEN_NOW = "2026-08-19T15:00:00+00:00"


def _write_strength(tmp_path, v):
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / TU.STRENGTH_FILE).write_text(
        json.dumps({"strength": v, "evidence": {"why": "test"}}), "utf-8")


def test_a_large_weight_amplifies_more(tmp_path):
    _write_strength(tmp_path, 1.0)          # 기계가 상한을 골랐다고 가정
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _ubars()},
                    strategy_factory=lambda s: _PartialLong(), cluster=_SNAP)
    rec = json.loads((tmp_path / "intraday" / "us_challenger.json")
                     .read_text("utf-8"))["rounds"][-1]
    # 0.5 × (1 + 1.0) = 1.0 (상한에서 잘림). 중립(0.15)이었다면 0.575였다.
    assert abs(rec["signals"]["AAPL"] - 1.0) < 1e-6, rec["signals"]


def test_a_large_weight_still_cannot_trade_a_flat_signal(tmp_path):
    """가장 중요한 계약 — 세기가 상한이어도 관망은 관망이다."""
    _write_strength(tmp_path, 1.0)
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _ubars()},
                    strategy_factory=lambda s: _Flat(), cluster=_SNAP)
    rec = json.loads((tmp_path / "intraday" / "us_challenger.json")
                     .read_text("utf-8"))["rounds"][-1]
    assert rec["signals"]["AAPL"] == 0.0
    assert not rec.get("trades")


def test_the_report_shows_the_machine_chosen_strength(tmp_path):
    _write_strength(tmp_path, 0.5)
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _ubars()},
                    strategy_factory=lambda s: _PartialLong(), cluster=_SNAP)
    out = json.loads((tmp_path / "docs" / "intraday_us.json").read_text("utf-8"))
    assert out["cluster_13f"]["strength"] == 0.5
    assert out["cluster_13f"]["strength_pct"] == 50
