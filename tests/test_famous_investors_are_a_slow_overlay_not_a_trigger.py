"""저명 투자자 13F 공시 — 확신 오버레이이지, 매수 트리거가 아니다.

사장님 지시(2026-09-22): *"13F 같은 유명 투자자들 공시를 최대한 정보 활용."*
결정: **확신 오버레이** — 이미 모델이 사겠다고 한 신호만 조금 키운다.

이 검사가 지키는 계약(대조군을 짝지어 둔다 — "키운다"는 검사마다 "안 키운다"가
있어야, 장치가 조용히 항상 켜지거나 항상 꺼지는 것을 잡는다):

  ① 13F 정보표(XML)를 형식 변화에도 파싱하고, 우리 유니버스가 아닌 종목은
     매칭하지 않는다(엉뚱한 종목에 가점이 가면 안 된다).
  ② 겹쳐 담기는 **개수**로 센다(금액 아님) — 금액 단위 함정을 안 탄다.
  ③ 오버레이는 **양수 신호만** 키운다. 관망(0)·팔자(음수)는 겹쳐 담기로
     뒤집히지 않는다 — 이게 '단독 트리거가 아니다'의 본질이다.
  ④ 참고 데이터가 죽으면(네트워크·형식) 그냥 빈 결과 → 오버레이 없음(1.0).
     못 받은 것을 '아무도 안 샀다'로 지어내지 않는다.
  ⑤ 실험 트랙에만 건다 — 본 계좌(100만 챌린지)에는 얹지 않는다.
  ⑥ 화면에 실리는 문장은 세 한계(지연·롱만·후행)를 함께 말한다. '수익 보장'류
     표현은 없다(사기죄 소지).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.thirteenf as TF                    # noqa: E402
import quant.live.intraday_us as IU                  # noqa: E402
import quant.live.thirteenf_overlay as OV            # noqa: E402

OPEN_NOW = "2026-08-19T15:00:00+00:00"   # 수요일 11:00 뉴욕 — 정규장

INFO_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
 <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
   <cusip>037833100</cusip><value>1000000</value>
   <shrsOrPrnAmt><sshPrnamt>10000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
 <infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><cusip>67066G104</cusip><value>500000</value>
   <shrsOrPrnAmt><sshPrnamt>2000</sshPrnamt></shrsOrPrnAmt></infoTable>
 <infoTable><nameOfIssuer>SOME RANDOM CO</nameOfIssuer><cusip>999999999</cusip><value>1</value></infoTable>
</informationTable>"""


# ── ① 파싱·매칭 ──────────────────────────────────────────────────
def test_the_information_table_parses():
    rows = TF.parse_information_table(INFO_XML)
    assert len(rows) == 3
    first = rows[0]
    assert first["issuer"] == "APPLE INC"
    assert first["cusip"] == "037833100"
    assert first["value"] == 1000000.0
    assert first["shares"] == 10000.0


def test_broken_xml_is_an_empty_table_not_a_crash():
    assert TF.parse_information_table("<not xml") == []
    assert TF.parse_information_table("") == []


def test_a_universe_name_is_matched_by_name_and_cusip():
    rows = TF.parse_information_table(INFO_XML)
    assert TF._match_symbol(rows[0]) == "AAPL"
    assert TF._match_symbol(rows[1]) == "NVDA"
    # 이름만 다르고 CUSIP만 맞아도 잡힌다
    assert TF._match_symbol({"issuer": "APL WHATEVER", "cusip": "037833100"}) == "AAPL"
    # CUSIP이 틀려도 이름으로 잡힌다
    assert TF._match_symbol({"issuer": "Apple Inc.", "cusip": "000"}) == "AAPL"


def test_a_name_outside_the_universe_is_not_matched():
    """대조군 — 유니버스 밖 종목은 절대 매칭되지 않는다(엉뚱한 가점 방지)."""
    rows = TF.parse_information_table(INFO_XML)
    assert TF._match_symbol(rows[2]) is None            # SOME RANDOM CO
    assert TF._match_symbol({"issuer": "", "cusip": ""}) is None


def test_index_etfs_are_deliberately_out_of_the_map():
    """지수 ETF는 지도에 없다 — 지수를 든 건 종목 선택 신호가 아니다."""
    for etf in ("SPY", "QQQ", "TLT", "IEF"):
        assert etf not in TF.SYMBOL_ISSUERS


# ── ② 겹쳐 담기는 개수로 센다 ────────────────────────────────────
def test_the_cluster_counts_filers_not_dollars():
    rows = TF.parse_information_table(INFO_XML)
    filings = {
        "0001067983": ("2026-06-30", rows),   # AAPL + NVDA
        "0001649339": ("2026-03-31",           # AAPL 만 (금액은 딴판)
                       [{"issuer": "Apple Inc.", "cusip": "037833100",
                         "value": 9.0, "shares": 1.0}]),
    }
    cl = TF.cluster_from_filings(filings)
    assert cl["AAPL"]["count"] == 2            # 두 제출자 → 2 (금액 무관)
    assert cl["NVDA"]["count"] == 1
    assert len(cl["AAPL"]["filers"]) == 2


def test_one_filer_listing_a_name_twice_counts_once():
    """한 제출자가 같은 종목을 두 줄에 적어도 1표다(클래스별 분리 등)."""
    filings = {"0001067983": ("2026-06-30", [
        {"issuer": "APPLE INC", "cusip": "037833100", "value": 1, "shares": 1},
        {"issuer": "APPLE INC", "cusip": "037833100", "value": 2, "shares": 2},
    ])}
    assert TF.cluster_from_filings(filings)["AAPL"]["count"] == 1


def test_the_cluster_keeps_the_oldest_as_of():
    """묵은 정도는 최악(가장 오래된 기준일)을 대표로 삼는다."""
    filings = {
        "0001067983": ("2026-06-30", [{"issuer": "APPLE INC",
                                        "cusip": "037833100", "value": 1}]),
        "0001649339": ("2026-03-31", [{"issuer": "APPLE INC",
                                        "cusip": "037833100", "value": 1}]),
    }
    assert TF.cluster_from_filings(filings)["AAPL"]["as_of"] == "2026-03-31"


# ── ③ 오버레이는 양수만 키운다 (핵심 안전 성질) ──────────────────
def _full_cluster():
    return {"AAPL": {"count": 3, "filers": ["a", "b", "c"], "as_of": "2026-06-30"},
            "NVDA": {"count": 1, "filers": ["a"], "as_of": "2026-06-30"}}


def test_a_full_cluster_lifts_a_buy_signal_a_little():
    cl = _full_cluster()
    assert OV.overlay_scale("AAPL", cl) == 1.0 + OV.MAX_BONUS      # 3명 → 상한
    assert abs(OV.apply_overlay(0.5, "AAPL", cl) - 0.5 * 1.15) < 1e-9


def test_one_filer_lifts_less_than_three():
    cl = _full_cluster()
    assert 1.0 < OV.overlay_scale("NVDA", cl) < OV.overlay_scale("AAPL", cl)


def test_the_overlay_never_exceeds_full_size():
    """몫의 비율은 100%를 못 넘는다 — 큰 신호를 키워도 1.0에서 자른다."""
    assert OV.apply_overlay(0.95, "AAPL", _full_cluster()) == 1.0


def test_no_cluster_is_no_lift():
    """대조군 — 겹쳐 담기가 없으면 배수 1.0, 신호 그대로."""
    assert OV.overlay_scale("TSLA", _full_cluster()) == 1.0     # 지도엔 있지만 겹치기 없음
    assert OV.overlay_scale("AAPL", {}) == 1.0
    assert OV.overlay_scale("AAPL", None) == 1.0
    assert OV.apply_overlay(0.5, "TSLA", _full_cluster()) == 0.5


def test_the_overlay_cannot_start_a_position_from_flat():
    """가장 중요한 계약 — 관망(0)은 아무리 겹쳐도 관망이다(단독 트리거 아님)."""
    assert OV.apply_overlay(0.0, "AAPL", _full_cluster()) == 0.0


def test_the_overlay_cannot_flip_a_sell_into_a_buy():
    """대조군 — 팔자(음수)도 겹쳐 담기로 매수가 되지 않는다."""
    assert OV.apply_overlay(-0.4, "AAPL", _full_cluster()) == -0.4


def test_the_overlay_keeps_dont_know_as_dont_know():
    assert OV.apply_overlay(None, "AAPL", _full_cluster()) is None
    assert OV.apply_overlay(float("nan"), "AAPL", _full_cluster()) is None


# ── ④ 신선도·실패 폴백 ───────────────────────────────────────────
def _fake_edgar(info_xml=INFO_XML):
    def fetch(url, timeout=12.0):
        if "submissions" in url:
            return json.dumps({"filings": {"recent": {
                "form": ["10-K", "13F-HR"],
                "accessionNumber": ["0000-00", "0001234567-26-000001"],
                "reportDate": ["2026-01-01", "2026-06-30"]}}})
        if "index.json" in url:
            return json.dumps({"directory": {"item": [
                {"name": "primary_doc.xml"}, {"name": "form13fInfoTable.xml"}]}})
        return info_xml
    return fetch


def test_a_fresh_cache_is_not_refetched(tmp_path):
    d = str(tmp_path)
    TF.refresh(d, now="2026-08-15", fetch=_fake_edgar(),
               filers={"0001067983": "Berkshire"})

    def boom(*a, **k):
        raise AssertionError("캐시가 신선한데 EDGAR를 다시 두드렸다")

    snap = TF.refresh(d, now="2026-08-16", fetch=boom,
                      filers={"0001067983": "Berkshire"})
    assert "AAPL" in snap["cluster"]


def test_a_broken_fetch_falls_back_to_empty(tmp_path):
    """대조군 — 조회가 터지면 빈 결과다(오버레이 전부 1.0)."""
    def boom(*a, **k):
        raise RuntimeError("network")

    snap = TF.refresh(str(tmp_path), now="2026-08-16", fetch=boom,
                      filers={"0001067983": "Berkshire"})
    assert snap["cluster"] == {}
    assert snap["filers_seen"] == 0
    assert OV.overlay_scale("AAPL", snap["cluster"]) == 1.0


# ── ⑤ 미국 트랙 통합 ─────────────────────────────────────────────
class _PartialLong:
    """관망도 매수도 아닌 중간 신호(0.5) — 오버레이 효과가 보이는 크기."""
    def generate_signals(self, df):
        return pd.Series(0.5, index=df.index)


class _Flat:
    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index)


def _bars(n=80, freq="1h", end="2026-08-19T14:00:00"):
    idx = pd.date_range(end=end, periods=n, freq=freq)
    px = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({"open": px, "high": [p * 1.01 for p in px],
                         "low": [p * 0.99 for p in px], "close": px}, index=idx)


_SNAP = {"cluster": {"AAPL": {"count": 3, "filers": ["Berkshire", "Scion",
                                                     "Pershing"],
                              "as_of": "2026-06-30"}},
         "fetched_on": "2026-08-15", "filers_total": 3, "filers_seen": 3}


def _state(tmp_path):
    p = tmp_path / "intraday" / "us_challenger.json"
    return json.loads(p.read_text("utf-8"))


def test_the_round_applies_the_overlay_and_records_it(tmp_path):
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _bars()},
                    strategy_factory=lambda s: _PartialLong(), cluster=_SNAP)
    rec = _state(tmp_path)["rounds"][-1]
    # 0.5 → ×1.15 = 0.575 (재보정은 규칙 아닌 전략이라 1.0)
    assert abs(rec["signals"]["AAPL"] - 0.575) < 1e-6, rec["signals"]
    assert rec["overlay_13f"]["AAPL"] == 1.15


def test_a_round_without_cluster_records_no_overlay(tmp_path):
    """대조군 — 겹쳐 담기를 주지 않으면 오버레이 기록도, 신호 변화도 없다."""
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _bars()},
                    strategy_factory=lambda s: _PartialLong())   # cluster 없음
    rec = _state(tmp_path)["rounds"][-1]
    assert abs(rec["signals"]["AAPL"] - 0.5) < 1e-6
    assert "overlay_13f" not in rec


def test_a_full_cluster_still_cannot_trade_a_flat_signal(tmp_path):
    """통합 수준의 안전 성질 — 관망 전략은 겹쳐 담기가 가득해도 매수가 없다."""
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _bars()},
                    strategy_factory=lambda s: _Flat(), cluster=_SNAP)
    rec = _state(tmp_path)["rounds"][-1]
    assert rec["signals"]["AAPL"] == 0.0
    assert not rec.get("trades"), rec.get("trades")


def test_the_public_report_carries_the_cluster_and_its_caveat(tmp_path):
    IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                    docs_dir=str(tmp_path / "docs"), data={"AAPL": _bars()},
                    strategy_factory=lambda s: _PartialLong(), cluster=_SNAP)
    out = json.loads((tmp_path / "docs" / "intraday_us.json").read_text("utf-8"))
    block = out["cluster_13f"]
    names = {r["symbol"]: r for r in block["names"]}
    assert names["AAPL"]["count"] == 3
    assert "45일" in block["caveat"] and "롱" in block["caveat"]
    # 규칙 변경 목록에 오버레이 규칙이 실린다
    ons = [r.get("on") for r in out["rule_changes"]]
    assert OV.RULE["on"] in ons          # 세기를 기계가 정하도록 바꾼 날(TUNED_ON)


def test_an_injected_data_run_never_touches_the_network(tmp_path):
    """주입 데이터 실행은 EDGAR로 나가지 않는다 — 검사가 재현 가능해야 한다."""
    def boom(*a, **k):
        raise AssertionError("주입 실행인데 EDGAR를 두드렸다")

    import quant.data.thirteenf as tfmod
    orig = tfmod._urllib_fetch
    tfmod._urllib_fetch = boom
    try:
        IU.run_us_round(OPEN_NOW, state_dir=str(tmp_path),
                        docs_dir=str(tmp_path / "docs"), data={"AAPL": _bars()},
                        strategy_factory=lambda s: _PartialLong())  # cluster 없음
    finally:
        tfmod._urllib_fetch = orig


# ── ⑥ 실험만·정직 ────────────────────────────────────────────────
def test_the_overlay_is_only_on_the_experiment_not_the_main_account():
    """본 계좌(daily.py)는 이 오버레이를 쓰지 않는다 — 실제 원금 위험 불가산."""
    main_src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "thirteenf_overlay" not in main_src
    assert "apply_overlay" not in main_src
    # 실험 트랙은 실제로 쓴다
    us_src = (ROOT / "quant" / "live" / "intraday_us.py").read_text("utf-8")
    assert "apply_overlay" in us_src


def test_the_rule_discloses_the_staleness():
    cav = OV.RULE["caveat"]
    assert "45일" in cav and "4.5개월" in cav and "롱" in cav
    assert OV.RULE["what"] and OV.RULE["why"]


def test_no_promise_of_returns_in_the_new_strings():
    """새 문장에 '수익 보장'류가 없다(사기죄 소지)."""
    blobs = [
        (ROOT / "quant" / "data" / "thirteenf.py").read_text("utf-8"),
        (ROOT / "quant" / "live" / "thirteenf_overlay.py").read_text("utf-8"),
    ]
    for text in blobs:
        for bad in ("수익을 보장", "손실 없", "무조건", "반드시 오른", "반드시 수익"):
            assert bad not in text, f"{bad!r} 가 새 코드에 있다"


def test_the_overlay_is_bounded_and_small():
    """상한이 '조금'인지 못 박는다 — 참고 데이터에 크게 걸지 않는다."""
    assert OV.MAX_BONUS <= 0.20
    assert OV.CLUSTER_FULL >= 1
    assert math.isclose(OV.overlay_scale("AAPL", _full_cluster()),
                        1.0 + OV.MAX_BONUS)
