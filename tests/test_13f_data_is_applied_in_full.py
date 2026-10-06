"""13F를 '있는 만큼 다' 쓰되, 틀리게 쓰지 않는가 (감사 333).

사장님 지시(2026-10-06): *"13F 최대한 모든 데이터를 적용시키는 것이 중요하고."*

수집이 살아난 뒤(감사 331) 실제 공시를 열어 보니 쓰는 방식에 구멍이 있었다:
  ① 옵션(풋·콜) 줄을 주식 보유로 셌다 — 하락 베팅이 '들고 있다'로 둔갑한다.
  ② 공시를 멈춘 투자자의 옛 보유가 영원히 '지금 든 것'으로 남았다.
  ③ 정정 공시(13F-HR/A)를 그 분기 전체로 읽었다 — 부분 공시라 나머지가 '다 팔았다'가 된다.
  ④ 알파벳 C주(GOOG)는 A주(GOOGL)로 세어져 GOOG에 재료가 안 갔다.
  ⑤ '늘렸다/줄였다'(흐름)는 공시에 있는데 아무 데도 안 썼다.
  ⑥ CIK를 손으로 적은 목록이 틀려도 다른 회사의 보유를 조용히 셌을 것이다.
  ⑦ 성적 측정이 "든 사람 0 vs 1 이상"으로 갈라 잰 날이 2일뿐이었다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quant.data.crossasset as CA                    # noqa: E402
import quant.data.thirteenf as TF                     # noqa: E402
from quant.live.thirteenf_tune import measure_edge    # noqa: E402
from quant.reporting.guru13f import guru13f_public    # noqa: E402
from quant.strategies.ml import OPTIONAL_FEATURES, UNMETERED_OPTIONAL  # noqa: E402

BRK = "0001067983"


def _row(issuer, cusip, shares=100, put_call="", title="COM"):
    return {"issuer": issuer, "cusip": cusip, "value": 1.0, "shares": shares,
            "put_call": put_call, "title": title}


AAPL = lambda n=100: _row("APPLE INC", "037833100", n)          # noqa: E731
NVDA = lambda n=100: _row("NVIDIA CORP", "67066G104", n)        # noqa: E731


# ── ① 옵션은 보유가 아니다 ───────────────────────────────────────
def test_the_parser_reads_the_put_call_and_class_columns():
    xml = ('<informationTable><infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer>'
           '<titleOfClass>COM</titleOfClass><cusip>67066G104</cusip><value>5</value>'
           '<shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt>'
           '<putCall>Put</putCall></infoTable></informationTable>')
    rows = TF.parse_information_table(xml)
    assert rows[0]["put_call"] == "PUT"
    assert rows[0]["title"] == "COM"
    assert rows[0]["shares"] == 10.0


def test_a_put_position_is_not_counted_as_holding_the_stock():
    put = _row("NVIDIA CORP", "67066G104", put_call="PUT")
    assert TF.is_option(put)
    assert TF._match_symbol(put) is None
    assert TF.stock_shares([put, AAPL()]) == {"AAPL": 100.0}
    cl = TF.cluster_from_filings({BRK: ("2026-06-30", [put])})
    assert "NVDA" not in cl, "풋옵션(하락 베팅)이 '들고 있다'로 세어졌다"


# ── ④ 알파벳 두 주식 ─────────────────────────────────────────────
def test_alphabet_class_c_goes_to_goog_and_class_a_to_googl():
    assert TF._match_symbol(_row("ALPHABET INC", "02079K107")) == "GOOG"
    assert TF._match_symbol(_row("ALPHABET INC", "02079K305")) == "GOOGL"
    # CUSIP이 없을 때는 주식 종류 표기로 가른다
    assert TF._match_symbol(_row("ALPHABET INC", "", title="CAP STK CL C")) == "GOOG"
    assert TF._match_symbol(_row("ALPHABET INC", "", title="CAP STK CL A")) == "GOOGL"
    # 종류를 모르면 A주로 본다(예전 동작)
    assert TF._match_symbol(_row("ALPHABET INC", "", title="")) == "GOOGL"


# ── ⑤ 흐름 ───────────────────────────────────────────────────────
def test_flows_tell_new_added_trimmed_and_exited_apart():
    prev = {"AAPL": 100.0, "NVDA": 100.0, "MSFT": 100.0, "AMZN": 100.0}
    cur = {"AAPL": 150.0, "NVDA": 50.0, "MSFT": 102.0, "TSLA": 10.0}
    assert TF.flows(prev, cur) == {"AAPL": 1, "NVDA": -1, "AMZN": -1, "TSLA": 1}
    # 문턱(5%) 안의 변화는 흐름이 아니다 — MSFT
    # 직전 공시가 없으면 모든 보유를 '샀다'로 세지 않는다
    assert TF.flows(None, cur) == {}


def test_holding_is_presence_even_without_a_share_count():
    # 주식 수 칸이 빈 공시도 있다 — 목록에 있으면 든 것이다
    prev = {"AAPL": 0.0}
    cur = {"AAPL": 0.0}
    assert TF.flows(prev, cur) == {}
    assert TF.flows({}, cur) == {"AAPL": 1}


# ── ② 공시가 멈춘 투자자는 만료된다 ─────────────────────────────
def test_a_filer_who_stops_filing_expires_from_the_cluster():
    hist = TF.build_cluster_history(
        {BRK: [{"filed": "2025-01-10", "holdings": [AAPL()]}]}, until="2026-01-01")
    assert TF.cluster_asof(hist, "2025-02-01").get("AAPL", {}).get("count") == 1
    assert "AAPL" not in TF.cluster_asof(hist, "2025-12-01"), \
        "공시를 멈춘 투자자의 옛 보유가 '지금 든 것'으로 남았다"


def test_expiry_rows_are_not_written_for_days_that_have_not_come():
    hist = TF.build_cluster_history(
        {BRK: [{"filed": "2026-09-01", "holdings": [AAPL()]}]}, until="2026-10-01")
    assert [r["as_of"] for r in hist] == ["2026-09-01"]


def test_a_timely_next_filing_keeps_the_filer_alive():
    hist = TF.build_cluster_history({BRK: [
        {"filed": "2025-01-10", "holdings": [AAPL()]},
        {"filed": "2025-04-10", "holdings": [AAPL(), NVDA()]},
    ]}, until="2025-06-01")
    row = TF.cluster_asof_row(hist, "2025-05-01")
    assert row["cluster"]["AAPL"]["count"] == 1
    assert row["flow"] == {"NVDA": {"buy": 1, "sell": 0}}


# ── ③ 정정 공시는 쓰지 않는다 · ⑥ 이름 확인 ─────────────────────
def _subs(name, forms):
    n = len(forms)
    return json.dumps({"name": name, "filings": {"recent": {
        "form": forms, "accessionNumber": [f"0000-{i}" for i in range(n)],
        "reportDate": ["2026-06-30"] * n,
        "filingDate": [f"2026-08-{10 + i:02d}" for i in range(n)]}}})


def _fetcher(name, forms, seen):
    info = ('<informationTable><infoTable><nameOfIssuer>APPLE INC</nameOfIssuer>'
            '<cusip>037833100</cusip></infoTable></informationTable>')

    def fetch(url):
        seen.append(url)
        if "submissions" in url:
            return _subs(name, forms)
        if url.endswith("index.json"):
            return json.dumps({"directory": {"item": [{"name": "info.xml"}]}})
        return info
    return fetch


def test_amended_filings_are_skipped():
    seen = []
    out = TF.filings_history(BRK, fetch=_fetcher("BERKSHIRE HATHAWAY INC",
                                                 ["13F-HR/A", "13F-HR"], seen))
    assert len(out) == 1
    assert out[0]["filed"] == "2026-08-11"
    assert not any("00000/" in u for u in seen), "정정 공시를 열었다"


def test_a_cik_whose_official_name_does_not_match_is_dropped_and_reported():
    rep = {"unverified": []}
    out = TF.filings_history(BRK, fetch=_fetcher("SOME OTHER FUND LP", ["13F-HR"], []),
                             report=rep)
    assert out == []
    assert rep["unverified"] and rep["unverified"][0]["cik"] == BRK
    assert rep["unverified"][0]["got"] == "SOME OTHER FUND LP"


def test_every_listed_filer_has_a_name_check():
    missing = [c for c in TF.FILERS if c not in TF.FILER_VERIFY]
    assert not missing, f"이름 확인 낱말이 없는 제출자: {missing}"
    assert len(TF.FILERS) >= 20


# ── ⑤ 흐름이 ML 재료로 — point-in-time ──────────────────────────
def _bars(start="2026-05-01", end="2026-06-10"):
    idx = pd.date_range(start=start, end=end, freq="D")
    px = [100.0 + i * 0.1 for i in range(len(idx))]
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px,
                         "volume": [1e6] * len(idx)}, index=idx)


def test_the_flow_feature_appears_only_from_its_filing_date(monkeypatch):
    monkeypatch.setattr(TF, "load_history", lambda state_dir="state": [
        {"as_of": "2026-05-15", "cluster": {"AAPL": {"count": 2}},
         "flow": {"AAPL": {"buy": 2, "sell": 0}}},
        {"as_of": "2026-05-25", "cluster": {"AAPL": {"count": 2}},
         "flow": {"AAPL": {"buy": 0, "sell": 1}}},
    ])
    out = CA.attach_cross_asset(_bars(), "us_stock", "AAPL", fetch=lambda *a, **k: None)
    f = out["x_guru13f_flow"]
    assert pd.isna(f.loc["2026-05-14"]), "공개 전 흐름이 붙었다(미래 참조)"
    assert f.loc["2026-05-15"] == 2.0
    assert f.loc["2026-05-30"] == -1.0
    assert "x_guru13f_flow" in OPTIONAL_FEATURES
    assert "x_guru13f_flow" in UNMETERED_OPTIONAL


def test_old_history_without_flow_does_not_invent_a_zero_flow(monkeypatch):
    monkeypatch.setattr(TF, "load_history", lambda state_dir="state": [
        {"as_of": "2026-05-15", "cluster": {"AAPL": {"count": 2}}}])
    out = CA.attach_cross_asset(_bars(), "us_stock", "AAPL", fetch=lambda *a, **k: None)
    assert "x_guru13f_flow" not in out.columns


# ── ⑦ 성적 측정이 실제로 날짜를 얻는다 ──────────────────────────
def test_the_edge_is_measured_even_when_everyone_holds_something():
    days = pd.date_range("2026-01-01", periods=200, freq="D")

    def lookup(sym):
        g = 0.002 if sym in ("AAPL", "NVDA") else 0.0
        return [(d.date().isoformat(), 100 * (1 + g) ** i) for i, d in enumerate(days)]

    hist = [{"as_of": f"2026-01-{d:02d}",
             "cluster": {"AAPL": {"count": 3}, "NVDA": {"count": 3},
                         "MSFT": {"count": 1}, "AMZN": {"count": 1}}}
            for d in (5, 15, 25)]
    uni = ["AAPL", "NVDA", "MSFT", "AMZN"]
    old = measure_edge(hist, lookup, uni, horizon=20, cluster_min=1, split="threshold")
    new = measure_edge(hist, lookup, uni, horizon=20, cluster_min=1)   # 기본 split
    assert old["n"] == 0, "옛 규칙은 아무도 안 든 종목이 없으면 못 잰다"
    assert new["n"] == 3 and new["mean_diff"] > 0


def test_a_day_where_everyone_has_the_same_count_is_skipped():
    days = pd.date_range("2026-01-01", periods=60, freq="D")
    lookup = lambda s: [(d.date().isoformat(), 100.0 + i) for i, d in enumerate(days)]  # noqa: E731
    hist = [{"as_of": "2026-01-05", "cluster": {"AAPL": {"count": 2},
                                                "MSFT": {"count": 2}}}]
    assert measure_edge(hist, lookup, ["AAPL", "MSFT"], horizon=10)["n"] == 0


# ── 화면 재료 ────────────────────────────────────────────────────
def test_the_public_block_carries_flows_exits_and_unverified(tmp_path):
    (tmp_path / TF.CACHE_FILE).write_text(json.dumps({
        "cluster": {"AAPL": {"count": 2, "filers": ["a", "b"], "buy": 1, "sell": 0}},
        "flow": {"AAPL": {"buy": 1, "sell": 0}, "TSLA": {"buy": 0, "sell": 2}},
        "fetched_on": "2026-10-06", "filers_total": 20, "filers_seen": 18}))
    (tmp_path / TF.HISTORY_FILE).write_text(json.dumps({
        "history": [{"as_of": "2026-08-14", "cluster": {}}],
        "filers": [{"name": "x", "bought": ["AAPL"], "sold": ["TSLA"],
                    "options_excluded": 3, "stale": True}],
        "fetch": {"on": "2026-10-06", "unverified": [{"cik": "0000000001"}]}}))
    g = guru13f_public(str(tmp_path))
    aapl = g["names"][0]
    assert (aapl["buy"], aapl["sell"]) == (1, 0)
    assert g["exited"] == ["TSLA"], "모두가 판 종목이 화면에서 사라졌다"
    assert g["fetch"]["unverified"][0]["cik"] == "0000000001"
    assert g["filers"][0]["stale"] is True


def test_the_card_draws_every_new_field():
    js = (ROOT / "docs/assets/guru13f.js").read_text(encoding="utf-8")
    for key in ("r.buy", "r.sell", "g.exited", "r.bought", "r.sold",
                "r.stale", "options_excluded", "unverified"):
        assert key in js, f"화면이 {key}를 안 읽는다"
