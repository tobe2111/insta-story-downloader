"""시장 민감도 — "그냥 시황을 따라가는 것 아니냐"에 숫자로 답한다.

사장님 질문(2026-10-01): *"그냥 지금 보니까 시황만 따라가네 전체적으로
나스닥 시장 안좋으면 주식 떨어지고 오르면 같이 오르고 이러면 자동투자매매가
의미가 있나?"*

맞는 질문이고, 화면이 그 답을 안 주고 있었다. 화면은 계좌의 수익만 보여
줬다 — 그러면 시장이 오른 날은 실력처럼, 내린 날은 억울하게 보인다.
이 파일은 각 계좌의 하루 수익을 지수의 하루 수익에 견줘 **둘로 가른다**:

  · **민감도(베타)** — 지수가 1% 움직일 때 계좌가 평균 몇 % 따라 움직이나.
    1이면 지수를 그대로 산 것과 같고, 0이면 지수와 무관하다.
  · **시장 몫을 뺀 하루 성적(알파)** — 민감도만큼의 시장 움직임을 빼고 남는
    것. 이것이 자동매매가 **스스로** 더한(또는 잃은) 몫이다.

그리고 그 알파가 **우연과 구별되는가**(t)를 함께 적는다. 표본이 짧으면
알파는 거의 언제나 우연이다 — 그 사실을 숨기면 이 칸은 광고가 된다.

정직한 한계(코드로 강제):
  · 장부의 자산은 **비용을 뺀 값**이다(BASIS). 알파도 비용 뒤 성적이다.
  · 표본이 MIN_DAYS일보다 짧으면 숫자를 내지 않는다 — "표본 부족"이라고만.
  · 날짜는 각 트랙이 실제로 체결하는 시장의 달력으로 묶는다(코인은 UTC,
    미국은 뉴욕). 계좌와 지수의 날짜가 하루 어긋나면 민감도가 0으로 보이는
    **거짓 무관**이 나온다 — 그래서 묶는 규칙을 트랙마다 명시한다.
  · 판정 문턱(|t| ≥ 2)은 이 자리에서 고른 값이 아니라 통상적인 95% 수준이다.
  · **매매 판단은 이 숫자를 읽지 않는다.** 보이게만 한다.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os

MIN_DAYS = 15
T_SIGNIFICANT = 2.0
BASIS = "비용을 뺀 장부 자산의 하루 변화"

# (트랙 열쇠, 화면 이름, 날짜를 묶는 달력, 견줄 지수들 — 첫째가 대표)
TRACKS = [
    ("main", "본 계좌", "ledger", ["us_stock:QQQ", "kr_stock:069500.KS",
                                  "crypto:BTC/USDT"]),
    ("intraday_us", "미국주식 장중", "America/New_York", ["us_stock:QQQ"]),
    ("intraday", "코인 장중", "UTC", ["crypto:BTC/USDT", "us_stock:QQQ"]),
    ("futures", "코인 선물", "UTC", ["crypto:BTC/USDT", "us_stock:QQQ"]),
]

BENCH_NAMES = {"us_stock:QQQ": "나스닥100(QQQ)",
               "kr_stock:069500.KS": "코스피200(KODEX 200)",
               "crypto:BTC/USDT": "비트코인"}


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _day(stamp, calendar: str) -> str | None:
    """시각을 그 트랙의 달력 날짜로. 'ledger'는 장부의 날짜를 그대로."""
    s = str(stamp or "")
    if not s:
        return None
    if calendar == "ledger":
        return s[:10]
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10]
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(calendar)
    except Exception:  # noqa: BLE001 — 달력을 모르면 UTC
        tz = _dt.timezone.utc
    return t.astimezone(tz).date().isoformat()


def _instant(stamp) -> float:
    """정렬용 절대 시각. 날짜만 있으면 그 날의 0시(UTC)로 본다."""
    s = str(stamp or "")
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return float("-inf")
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.timestamp()


def _daily_last(points, calendar: str) -> dict[str, float]:
    """[(시각, 자산)] → {날짜: 그날 마지막 자산}. 시각 순으로 정렬해 묶는다.

    ⚠️ **글자가 아니라 시각으로** 정렬한다. 미국 장중 장부는 `+00:00`과
       `+09:00`이 섞여 있어(실측), 글자로 정렬하면 '2026-09-30T00:30+09:00'
       (= UTC 9/29 15:30)이 '2026-09-29T19:55+00:00'보다 뒤로 가서 그날의
       마지막 자산을 더 이른 회차의 값으로 고른다.
    """
    out: dict[str, float] = {}
    for stamp, eq in sorted(points, key=lambda p: _instant(p[0])):
        d = _day(stamp, calendar)
        try:
            v = float(eq)
        except (TypeError, ValueError):
            continue
        if d and v > 0 and math.isfinite(v):
            out[d] = v
    return out


def account_points(state_dir: str, track: str) -> list:
    """트랙의 (시각, 자산) 목록 — 각 트랙의 원장에서 직접 읽는다."""
    if track == "main":
        h = _read(os.path.join(state_dir, "paper", "portfolio_ALL.json")).get("history") or []
        return [(r.get("date"), r.get("equity")) for r in h]
    if track == "intraday_us":
        r = _read(os.path.join(state_dir, "intraday", "us_challenger.json")).get("rounds") or []
        return [(x.get("time"), x.get("equity")) for x in r]
    if track == "intraday":
        r = _read(os.path.join(state_dir, "intraday", "challenger.json")).get("rounds") or []
        return [(x.get("time"), x.get("equity")) for x in r]
    if track == "futures":
        c = _read(os.path.join(state_dir, "futures", "futures.json")).get("curve") or []
        return [(x.get("at"), x.get("equity")) for x in c]
    return []


def bench_closes(state_dir: str, key: str) -> dict[str, float]:
    """지수 종가 {봉 날짜: 종가} — 그 종목의 페이퍼 원장이 매일 남기는 값."""
    market, sym = key.split(":", 1)
    name = f"{market}_{sym.replace('/', '_')}.json"
    h = _read(os.path.join(state_dir, "paper", name)).get("history") or []
    out = {}
    for r in h:
        try:
            p = float(r.get("price"))
        except (TypeError, ValueError):
            continue
        if r.get("date") and p > 0:
            out[str(r["date"])[:10]] = p
    return out


def _returns(series: dict[str, float]) -> dict[str, float]:
    days = sorted(series)
    return {d: series[d] / series[p] - 1.0
            for p, d in zip(days, days[1:]) if series[p] > 0}


def sensitivity(acct: dict[str, float], bench: dict[str, float]) -> dict:
    """하루 수익끼리 회귀 — 같은 날짜에 둘 다 있는 날만 쓴다.

    반환: {n, beta, corr, alpha_bp, t, significant} 또는 {n, short: True}.
    """
    # ⚠️ **공통 날짜로 먼저 자른 뒤** 수익을 낸다. 코인 계좌는 주말에도
    #    봉이 있고 지수는 없다 — 각자 수익을 내고 겹치는 날만 고르면, 월요일
    #    칸이 계좌는 '일→월', 지수는 '금→월'을 담아 서로 다른 구간을 견주게
    #    된다. 잘라 두면 둘 다 '금→월'이다.
    common = set(acct) & set(bench)
    ra = _returns({d: acct[d] for d in common})
    rb = _returns({d: bench[d] for d in common})
    days = sorted(set(ra) & set(rb))
    n = len(days)
    if n < MIN_DAYS:
        return {"n": n, "short": True}
    a = [ra[d] for d in days]
    b = [rb[d] for d in days]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)
    vb = sum((y - mb) ** 2 for y in b) / (n - 1)
    va = sum((x - ma) ** 2 for x in a) / (n - 1)
    if vb <= 0:
        return {"n": n, "short": True}
    beta = cov / vb
    corr = cov / math.sqrt(va * vb) if va > 0 else 0.0
    resid = [x - beta * y for x, y in zip(a, b)]
    mr = sum(resid) / n
    sr = math.sqrt(sum((e - mr) ** 2 for e in resid) / (n - 1))
    t = (mr / sr * math.sqrt(n)) if sr > 0 else 0.0
    return {"n": n, "beta": round(beta, 3), "corr": round(corr, 3),
            "alpha_bp": round(mr * 1e4, 2), "t": round(t, 2),
            "significant": abs(t) >= T_SIGNIFICANT,
            "from": days[0], "to": days[-1]}


def market_beta_public(state_dir: str = "state") -> dict:
    """status.json 탑재용 — 트랙마다, 지수마다 민감도와 시장을 뺀 성적."""
    tracks = []
    for key, label, cal, benches in TRACKS:
        acct = _daily_last(account_points(state_dir, key), cal)
        rows = []
        for bk in benches:
            m = sensitivity(acct, bench_closes(state_dir, bk))
            rows.append({"bench": bk, "bench_name": BENCH_NAMES.get(bk, bk), **m})
        tracks.append({"track": key, "label": label, "calendar": cal,
                       "days": len(acct), "vs": rows})
    return {"tracks": tracks, "min_days": MIN_DAYS,
            "t_significant": T_SIGNIFICANT, "basis": BASIS}
