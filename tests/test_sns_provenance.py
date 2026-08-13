"""SNS 캡션 출처 계약 검사 — 방송하는 숫자는 장부에서 나와야 한다.

배경(2026-08-11 감사에서 발견한 두 결함):
  ① 캡션의 훅이 **누적 수익률(원금 대비)** 을 "오늘 X%"라고 읽고 있었다.
     지금은 누적이 -0.06%라 차이가 안 보이지만, 누적이 +40%가 되면 매일
     "오늘 +40%. 좋은 날이지만…"을 방송하게 된다. 정직성이 유일한 자산인
     계정에서 이보다 치명적인 거짓말은 없다.
  ② '20종목'·'8만원'이 산문에 박혀 있었다. 설정이 바뀌면 SNS만 조용히
     거짓말을 한다(사이트에는 이미 같은 계약 검사를 걸어 뒀다).

핵심 계약:
  · 하루치와 누적은 서로 다른 값이며, 훅은 하루치를 쓴다
  · 종목 수·시작금은 설정에서 온다
  · 수익 보장 문구는 절대 없고, 모의투자 고지는 항상 있다
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import day_return_pct  # noqa: E402
from quant.reporting import social  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _status(hist, deposits=None, **extra):
    return {"updated": hist[-1]["date"] + "T00:00:00",
            "paper": {"portfolio:ALL": {
                "equity": hist[-1]["equity"], "principal": 80_000.0,
                "start_cash": 80_000.0, "deposits": deposits or [],
                "history": hist}},
            **extra}


def _rec(date, equity, day_pct=None, **kw):
    r = {"date": date, "equity": equity,
         "return_pct": round((equity / 80_000 - 1) * 100, 2),
         "weight": 0.5, "risk_scale": 1.0,
         "champion": {"symbols": 20}, "alloc": {}}
    if day_pct is not None:
        r["day_pct"] = day_pct
    return {**r, **kw}


# ── ① 하루치 계산 그 자체 ─────────────────────────────────────


def test_day_return_is_the_day_not_the_total():
    hist = [_rec("2026-01-01", 80_000), _rec("2026-01-02", 88_000)]
    assert day_return_pct(hist, [], start_cash=80_000) == 10.0
    hist.append(_rec("2026-01-03", 88_880))
    assert day_return_pct(hist, [], start_cash=80_000) == 1.0   # 누적은 11.1%
    assert hist[-1]["return_pct"] == 11.1


def test_day_return_excludes_deposits():
    """입금은 수익이 아니다 — 하루치도 TWR과 같은 규칙을 따라야 한다."""
    hist = [_rec("2026-01-01", 80_000), _rec("2026-01-02", 180_000)]
    deposits = [{"date": "2026-01-02", "amount": 100_000}]
    assert day_return_pct(hist, deposits, start_cash=80_000) == 0.0


def test_first_day_measures_against_start_cash():
    assert day_return_pct([_rec("2026-01-01", 84_000)], [],
                          start_cash=80_000) == 5.0


# ── ② 캡션이 하루치를 쓴다 ────────────────────────────────────


def test_hook_reports_the_day_not_the_cumulative():
    """누적 +40%, 오늘 -2%인 날 — 훅은 손실을 말해야 한다."""
    hist = [_rec("2026-01-01", 80_000), _rec("2026-01-02", 112_000),
            _rec("2026-01-03", 109_760, day_pct=-2.0)]
    caps = social.build_captions(_status(hist))
    assert "오늘 -2.00%" in caps["instagram"]
    assert "오늘 +40" not in caps["instagram"]
    assert "누적 +37.20%" in caps["instagram"]


def test_caption_labels_cumulative_as_cumulative():
    hist = [_rec("2026-01-01", 80_000, day_pct=0.0)]
    for text in social.build_captions(_status(hist)).values():
        if text.startswith("2026"):
            continue
        assert "누적" in text


def test_day_pct_is_recomputed_for_old_records_without_it():
    """장부에 day_pct가 없던 시절 기록도 올바른 하루치를 낸다."""
    hist = [_rec("2026-01-01", 80_000), _rec("2026-01-02", 79_200)]
    caps = social.build_captions(_status(hist))
    assert "오늘 -1.00%" in caps["instagram"]


def test_daily_record_carries_day_pct():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'record["day_pct"]' in src


def test_site_shows_the_day_separately_from_cumulative():
    html = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "day_pct" in html
    assert "누적 기준" in html


# ── ③ 종목 수·시작금은 설정에서 ───────────────────────────────


def test_symbol_count_comes_from_the_ledger():
    # 2026-08-12 감사 114에서 문구가 바뀌었다 — '분산'은 후보 전부에 퍼져
    # 있는 것처럼 읽혀서, 보유 수와 후보 수를 나눠 적는다.
    hist = [_rec("2026-01-01", 80_000, day_pct=0.0,
                 champion={"symbols": 7})]
    text = social.build_captions(_status(hist))["instagram"]
    assert "후보 7종목" in text, text
    assert "종목 분산" not in text, "'분산'이 되살아났다"


def test_start_cash_comes_from_config():
    """장부에 원금이 없으면 코드 기본값으로 되돌아간다(옛 기록 하위호환)."""
    from quant.live.daily import PORTFOLIO_START_CASH
    hist = [_rec("2026-01-01", 80_000, day_pct=0.0)]
    ig = social.build_captions(_status(hist))["instagram"]
    assert f"{PORTFOLIO_START_CASH / 10_000:,.0f}만원으로 시작" in ig


def test_no_hardcoded_counts_in_source():
    """캡션이 **내보내는 글자**에 숫자가 박혀 있으면 안 된다.

    ⚠️ 원래 소스 전체를 문자열로 훑었다. 그래서 이 결함을 고치면서 **왜
    고쳤는지 적은 주석**("…기본값(8만원)이지…")에 걸려 빨개졌다 — 계약은
    지켜졌는데 설명이 검사를 깨뜨린 것이다. 감사 183·199·204·211·212·213·
    217에 이어 **일곱 번째** 같은 함정이다.

    주석은 애초에 AST에 없다. 파싱해서 **실제 문자열 리터럴만** 본다 —
    그게 화면·방송에 나가는 것이고, 검사가 지키려던 것도 그것뿐이다.
    """
    import ast

    src = (ROOT / "quant" / "reporting" / "social.py").read_text("utf-8")
    tree = ast.parse(src)
    docstrings = {ast.get_docstring(n) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef,
                                    ast.FunctionDef, ast.AsyncFunctionDef))}
    emitted = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n.value not in docstrings]
    for bad in ("20종목", "8만원"):
        hits = [t for t in emitted if bad in t]
        assert not hits, (
            f"캡션이 내보내는 글자에 '{bad}'가 박혀 있다 — 설정이 바뀌면 "
            f"SNS만 조용히 거짓말을 한다:\n  " + "\n  ".join(hits[:3]))


# ── ④ 정직 고지(회귀 방지) ────────────────────────────────────


def test_captions_never_promise_returns():
    hist = [_rec("2026-01-01", 96_000, day_pct=20.0)]
    caps = social.build_captions(_status(hist))
    for key in ("instagram", "threads"):
        text = caps[key]
        assert "모의투자" in text
        for banned in ("수익 보장", "확실한 수익", "원금 보장", "무조건"):
            assert banned not in text.replace("수익 보장 없음", "")
    assert "수익을 보장하지 않으며" in caps["instagram"]


def test_threads_caption_stays_within_limit():
    hist = [_rec("2026-01-01", 80_000, day_pct=0.0,
                 alloc={f"m:{i}": 0.1 for i in range(20)})]
    caps = social.build_captions(_status(hist))
    assert len(caps["threads"]) <= social.THREADS_TEXT_LIMIT
