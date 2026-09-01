"""첫 화면 배너의 "어젯밤 N종목"이 **밤**을 세는가 — 봉 날짜가 아니라.

■ 왜 (2026-09-01 장부 실측)

배너는 밤을 ``asof``(그 종목의 마지막 봉 날짜)의 최댓값으로 골랐다. 그런데
매일 봉이 생기는 시장은 코인뿐이라, 그 최댓값은 **언제나 코인 날짜**다.
주식의 봉 날짜는 주말 내내 금요일에 멈춰 있다. 실측:

    밤 8/29 실제 24종목(한국 15·미국 4·코인 5) → 배너 5
    밤 8/31 실제 17종목                        → 배너 5
    밤 9/1  실제 24종목(미국 19·코인 5)        → 배너 5
    밤 8/30 실제 21종목(전부 미국주식)         → 그 밤 줄이 하나도 안 잡힘

수가 5분의 1로 줄어드는 것보다 나쁜 것은 **승격이 숨는 것**이다. 주식에서
챔피언이 바뀌면 그 줄의 asof는 금요일이라 그날 목록에서 빠지고, 화면에는
"전원 챔피언 유지"가 나간다 — 이 배너가 존재하는 이유 그 자체를 놓친다.
"""
from __future__ import annotations

import json

# 실제 장부에서 본 모양 그대로: 한 밤에 코인은 그날 봉, 미국주식은 금요일 봉.
NIGHT = "2026-09-01"
FRIDAY = "2026-08-28"


def _row(symbol, market, asof, night=NIGHT, promoted=False, strategy="ml"):
    return {"asof": asof, "night": night, "market": market, "symbol": symbol,
            "promoted": promoted, "champion_strategy": strategy,
            "reason": "챔피언 유지", "n_candidates": 40}


def _ledger(tmp_path, rows):
    with open(tmp_path / "retrain_history.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _news(tmp_path) -> str:
    from quant.web.app import broadcast_json
    return json.loads(broadcast_json(state_dir=str(tmp_path),
                                     with_live=False)).get("news") or ""


def _one_night(promoted_symbol: str | None = None) -> list[dict]:
    rows = [_row(f"C{i}", "crypto", NIGHT) for i in range(5)]
    rows += [_row(f"S{i}", "us_stock", FRIDAY) for i in range(19)]
    if promoted_symbol:
        rows.append(_row(promoted_symbol, "us_stock", FRIDAY,
                         promoted=True, strategy="gb"))
    return rows


def test_the_banner_counts_every_symbol_judged_that_night(tmp_path):
    """한 밤에 24종목을 봤으면 배너도 24라고 말한다."""
    _ledger(tmp_path, _one_night())
    news = _news(tmp_path)
    assert "24종목 대결" in news, news
    assert NIGHT in news


def test_counting_by_bar_date_would_have_said_five(tmp_path):
    """대조군 — 봉 날짜로 세면 코인 5개만 잡힌다(고친 전의 값)."""
    rows = _one_night()
    last = max(r["asof"] for r in rows)
    assert last == NIGHT                       # 최댓값은 언제나 코인 날짜
    assert len([r for r in rows if r["asof"] == last]) == 5
    assert all(r["market"] == "crypto"
               for r in rows if r["asof"] == last)


def test_a_promotion_on_a_stock_is_not_hidden(tmp_path):
    """주식 승격은 배너에 나온다 — 그 줄의 봉 날짜가 금요일이어도."""
    _ledger(tmp_path, _one_night(promoted_symbol="AAPL"))
    news = _news(tmp_path)
    assert "챔피언 교체" in news, news
    assert "AAPL→gb" in news


def test_the_hidden_promotion_really_was_invisible_by_bar_date(tmp_path):
    """대조군 — 봉 날짜로 골랐으면 그 승격 줄은 그날 목록 밖이다."""
    rows = _one_night(promoted_symbol="AAPL")
    last = max(r["asof"] for r in rows)
    day = [r for r in rows if r["asof"] == last]
    assert not any(r["promoted"] for r in day)


def test_a_night_of_only_stocks_is_not_read_as_an_older_night(tmp_path):
    """코인이 안 돈 밤 — 그 밤이 '어젯밤'이 된다.

    봉 날짜로 골랐으면 그 밤의 줄은 전부 금요일이라, 코인이 돌았던 **앞선
    밤**이 최댓값을 쥐고 '어젯밤'이라 불렸다.
    """
    older = [_row(f"C{i}", "crypto", "2026-08-29", night="2026-08-29")
             for i in range(5)]
    tonight = [_row(f"S{i}", "us_stock", FRIDAY, night="2026-08-30")
               for i in range(21)]
    _ledger(tmp_path, older + tonight)
    news = _news(tmp_path)
    assert "2026-08-30" in news and "21종목 대결" in news, news
    # 대조군 — 봉 날짜의 최댓값은 앞선 밤의 코인 날짜다
    assert max(r["asof"] for r in older + tonight) == "2026-08-29"


def test_old_lines_without_a_night_key_still_group(tmp_path):
    """밤 열쇠가 없던 옛 줄은 봉 날짜로 되돌아간다 — 과거 기록은 고치지 않는다."""
    rows = []
    for i in range(3):
        r = _row(f"C{i}", "crypto", "2026-08-20")
        r.pop("night")
        rows.append(r)
    _ledger(tmp_path, rows)
    news = _news(tmp_path)
    assert "2026-08-20" in news and "3종목 대결" in news, news


# ── 배선: 밤 열쇠가 실제로 기록되는가 ──────────────────────────────────────
#
# 위 검사들은 장부에 `night`가 있다고 **가정**한다. 그 칸이 실제로 안 적히면
# 배너는 언제나 옛 경로(봉 날짜)로 되돌아가고, 화면은 고치기 전과 똑같은데
# 검사는 전부 초록이다 — 이 저장소가 이미 여러 번 겪은 모양이다.

def _thin_retrain(rt, tmp_path, **kw):
    orig = rt.DEFAULT_CHALLENGERS
    rt.DEFAULT_CHALLENGERS = [{"model": "logreg", "threshold": 0.60}]
    try:
        return rt.run_retrain("synthetic", "DEMO", limit=400,
                              state_dir=str(tmp_path), confirm_window=100,
                              require_real_data=False, evolve=False, **kw)
    finally:
        rt.DEFAULT_CHALLENGERS = orig


def _last_record(tmp_path) -> dict:
    lines = (tmp_path / "retrain_history.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


def test_the_ledger_really_carries_the_night_key(tmp_path):
    """밤 배치가 넘긴 명단 날짜가 그 줄의 밤 열쇠로 남는다."""
    import quant.live.retrain as rt
    _thin_retrain(rt, tmp_path, panel_asof="2026-09-01")
    rec = _last_record(tmp_path)
    assert rec["night"] == "2026-09-01"


def test_the_night_key_is_not_the_bar_date(tmp_path):
    """대조군 — 밤 열쇠와 봉 날짜는 실제로 다른 값이다.

    둘이 늘 같다면 위 검사는 아무것도 못 지킨다(봉 날짜를 그대로 베껴 써도
    통과한다).
    """
    import quant.live.retrain as rt
    _thin_retrain(rt, tmp_path, panel_asof="2099-12-31")
    rec = _last_record(tmp_path)
    assert rec["night"] == "2099-12-31"
    assert rec["asof"] != rec["night"]


def test_a_standalone_run_still_gets_a_night(tmp_path):
    """명단 날짜 없이 혼자 돌아도 밤 열쇠는 비지 않는다(한국 달력일)."""
    import quant.live.retrain as rt
    _thin_retrain(rt, tmp_path)
    rec = _last_record(tmp_path)
    assert rec["night"] == rt.night_key()
    assert len(rec["night"]) == 10
