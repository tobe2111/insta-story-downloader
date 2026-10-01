"""시장 민감도 — "시황만 따라가는 것 아니냐"에 숫자로 답하는가 (감사 331).

사장님 질문(2026-10-01): *"나스닥 시장 안좋으면 주식 떨어지고 오르면 같이
오르고 이러면 자동투자매매가 의미가 있나?"*

지키는 것:
  ① 회귀가 맞다 — 계좌 = 0.5×지수 + 일정한 초과분이면 민감도 0.5, 초과분이 알파.
  ② 표본이 짧으면 숫자를 안 낸다(표본 부족).
  ③ 주말이 있는 코인 계좌를 주말 없는 지수에 견줄 때 구간이 어긋나지 않는다.
  ④ 장부에서 직접 읽어 status.json에 싣는다.
  ⑤ 화면의 판정은 숫자에서 기계적으로 — 유의하지 않으면 플러스여도 "이겼다"고
     안 한다.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from quant.reporting import market_beta as MB

ROOT = Path(__file__).resolve().parent.parent


def _days(n, start="2026-08-03", weekdays_only=False):
    d = dt.date.fromisoformat(start)
    out = []
    while len(out) < n:
        if not weekdays_only or d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _series(days, rets, base=100.0):
    out, v = {}, base
    for d, r in zip(days, [0.0] + list(rets)):
        v *= 1 + r
        out[d] = v
    return out


# ── ① 회귀 ───────────────────────────────────────────────────────
def test_half_the_index_plus_a_steady_edge_is_read_as_beta_half_and_that_edge():
    rnd = random.Random(7)
    days = _days(60, weekdays_only=True)
    b = [rnd.gauss(0, 0.01) for _ in days[1:]]
    noise = [rnd.gauss(0, 0.0005) for _ in days[1:]]
    a = [0.5 * x + 0.001 + e for x, e in zip(b, noise)]
    m = MB.sensitivity(_series(days, a), _series(days, b))
    assert abs(m["beta"] - 0.5) < 0.05, m
    assert abs(m["alpha_bp"] - 10.0) < 3.0, m
    assert m["significant"] is True and m["t"] > MB.T_SIGNIFICANT


def test_an_account_that_only_rides_the_index_has_no_edge():
    rnd = random.Random(3)
    days = _days(60, weekdays_only=True)
    b = [rnd.gauss(0, 0.01) for _ in days[1:]]
    a = [1.0 * x + rnd.gauss(0, 0.002) for x in b]
    m = MB.sensitivity(_series(days, a), _series(days, b))
    assert abs(m["beta"] - 1.0) < 0.1 and m["corr"] > 0.9
    assert m["significant"] is False          # 따라만 갔다 — 실력이 아니다


# ── ② 표본 부족 ──────────────────────────────────────────────────
def test_a_short_sample_says_so_instead_of_giving_a_number():
    days = _days(MB.MIN_DAYS, weekdays_only=True)   # 수익은 MIN_DAYS-1개
    rets = [0.01] * (len(days) - 1)
    m = MB.sensitivity(_series(days, rets), _series(days, rets))
    assert m.get("short") is True and "beta" not in m


# ── ③ 주말 정렬 ──────────────────────────────────────────────────
def test_a_weekend_trading_account_is_compared_over_the_same_span_as_the_index():
    """코인 계좌가 지수를 1:1로 따라가되 주말에도 값이 있으면, 월요일 칸이
    '일→월' 대 '금→월'로 어긋나지 않아야 민감도가 1로 읽힌다."""
    rnd = random.Random(11)
    all_days = _days(84)
    wk = [d for d in all_days if dt.date.fromisoformat(d).weekday() < 5]
    b_rets = [rnd.gauss(0, 0.01) for _ in wk[1:]]
    bench = _series(wk, b_rets)
    acct, last = {}, None
    for d in all_days:
        if d in bench:
            last = bench[d]
            acct[d] = last
        elif last is not None:
            # 주말: 계좌가 움직였다가 월요일 전에 되돌아간다(지수 구간과 무관)
            acct[d] = last * (1 + rnd.choice([-0.03, 0.03]))
    m = MB.sensitivity(acct, bench)
    assert abs(m["beta"] - 1.0) < 1e-6 and m["corr"] > 0.999, m


# ── ④ 장부에서 읽어 싣는다 ───────────────────────────────────────
def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), "utf-8")


def test_the_public_block_reads_the_ledgers_directly(tmp_path):
    rnd = random.Random(5)
    days = _days(40, weekdays_only=True)
    q = _series(days, [rnd.gauss(0, 0.01) for _ in days[1:]], base=500.0)
    _write(tmp_path / "paper" / "us_stock_QQQ.json",
           {"history": [{"date": d, "price": v} for d, v in q.items()]})
    eq = {d: 1_000_000 * (q[d] / q[days[0]]) ** 0.3 for d in days}
    _write(tmp_path / "paper" / "portfolio_ALL.json",
           {"history": [{"date": d, "equity": v} for d, v in eq.items()]})
    out = MB.market_beta_public(str(tmp_path))
    main = next(t for t in out["tracks"] if t["track"] == "main")
    qqq = next(r for r in main["vs"] if r["bench"] == "us_stock:QQQ")
    assert abs(qqq["beta"] - 0.3) < 0.05, qqq
    assert out["basis"] and out["min_days"] == MB.MIN_DAYS
    # 장부가 없는 트랙·지수는 지어내지 않고 '표본 부족'이다
    fut = next(t for t in out["tracks"] if t["track"] == "futures")
    assert all(r.get("short") for r in fut["vs"])


def test_us_rounds_are_grouped_by_the_new_york_date():
    """뉴욕 16:00 마감 회차(UTC로는 다음날 새벽일 수 있다)는 뉴욕 날짜로 묶인다."""
    pts = [("2026-09-29T19:55:00+00:00", 100.0),      # 뉴욕 15:55 · 9/29
           ("2026-09-30T00:30:00+09:00", 101.0)]      # = UTC 9/29 15:30 · 뉴욕 9/29
    got = MB._daily_last(pts, "America/New_York")
    assert list(got) == ["2026-09-29"] and got["2026-09-29"] == 100.0


def test_the_status_writer_carries_both_new_blocks():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert 'status["market_beta"] = market_beta_public(state_dir)' in src
    assert 'status["guru13f"] = guru13f_public(state_dir)' in src


# ── ⑤ 화면 판정 ──────────────────────────────────────────────────
def _node():
    exe = shutil.which("node")
    assert exe, "node가 없으면 건너뛰지 않고 실패한다(사이트 스크립트 검사 규약)"
    return exe


def _js(expr: str) -> str:
    code = ("global.window={};require(%r);const M=window.MarketBeta;"
            "process.stdout.write(JSON.stringify(%s));"
            % (str(ROOT / "docs" / "assets" / "market-beta.js"), expr))
    return json.loads(subprocess.run([_node(), "-e", code], capture_output=True,
                                     text=True, check=True).stdout)


@pytest.mark.parametrize("row,want", [
    ({"short": True}, "표본 부족"),
    ({"significant": False, "alpha_bp": 80.0}, "우연과 구별 안 됨"),
    ({"significant": True, "alpha_bp": 5.0}, "시장을 이김 — 우연과 구별됨"),
    ({"significant": True, "alpha_bp": -5.0}, "시장에 짐 — 우연과 구별됨"),
])
def test_the_screen_never_calls_an_insignificant_edge_a_win(row, want):
    assert _js("M.verdict(%s).t" % json.dumps(row)) == want


def test_every_page_shows_13f_and_the_account_pages_show_sensitivity():
    pages = ["index", "paper", "today", "trust", "weekly", "ml", "intraday",
             "futures", "us"]
    for p in pages:
        html = (ROOT / "docs" / f"{p}.html").read_text("utf-8")
        assert "data-guru13f" in html and "assets/guru13f.js" in html, p
    for p, track in [("paper", "main"), ("intraday", "intraday"),
                     ("futures", "futures"), ("us", "intraday_us"),
                     ("index", "all")]:
        html = (ROOT / "docs" / f"{p}.html").read_text("utf-8")
        assert f'data-market-beta="{track}"' in html, p
        assert "assets/market-beta.js" in html, p
    keys = {t[0] for t in MB.TRACKS}
    assert {"main", "intraday", "futures", "intraday_us"} <= keys
