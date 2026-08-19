"""실효 표본 — **종목 수가 아니라 정보의 양**을 잰다 (2026-08-19, 사장님 지시).

사장님: "많은 데이터를 최대한 모을 수 있는 방법"

⚠️ 이 파일이 있는 이유. 2026-08-19 이전 유니버스 20종목은 전부 위험자산
   한 덩어리였다 — 코인·미국주식·한국주식이 시장 빠지는 날 같이 빠졌다.
   그러면 장부에는 스무 줄이 쌓이지만 통계가 받는 정보는 스무 개가 아니다.
   비슷한 것을 더 넣으면 **정보는 안 늘고 다중검정 문턱만 올라가** 판정이
   오히려 느려진다.

   그래서 자산군을 늘렸고(금·채권·원자재·해외 등), 늘어난 것이 줄이 아니라
   정보인지를 **여기서 잰다.** 재지 않으면 "많이 넣었으니 좋아졌겠지"라는
   믿음만 남는데, 이 저장소는 믿음을 기록으로 바꾸는 것이 일이다.

재는 방법(고전적인 실효 표본 수):

    실효 N = N / (1 + (N−1)·평균상관)

    같이 움직이는 종목만 스물이면 실효 N은 1에 가깝고, 서로 무관하면 20에
    가깝다. 상관은 **일수익률**로 재고, 짝이 맞는 날만 쓴다.

정직한 한계:
    · 상관은 구간마다 변한다(위기에는 모든 것이 같이 움직인다). 여기 숫자는
      '지금 표본에서의' 값이고 미래 보장이 아니다.
    · 기록이 얇으면 상관 자체가 잡음이다 — 최소 일수 아래면 재지 않고
      "표본 부족"이라 적는다(빈칸으로 두면 '문제 없음'으로 읽힌다).
"""
from __future__ import annotations

import glob
import json
import os

MIN_DAYS = 10          # 이보다 얇으면 상관을 재지 않는다


def _price_series(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for r in st.get("history") or []:
        d, p = r.get("date"), r.get("price")
        if d and p:
            try:
                out[str(d)[:10]] = float(p)
            except (TypeError, ValueError):
                continue
    return out


def _returns(series: dict) -> dict:
    days = sorted(series)
    out = {}
    for a, b in zip(days, days[1:]):
        if series[a] > 0:
            out[b] = series[b] / series[a] - 1.0
    return out


def _corr(x: dict, y: dict) -> float | None:
    days = sorted(set(x) & set(y))
    if len(days) < MIN_DAYS:
        return None
    a = [x[d] for d in days]
    b = [y[d] for d in days]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((v - ma) ** 2 for v in a)
    vb = sum((v - mb) ** 2 for v in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    return cov / (va ** 0.5 * vb ** 0.5)


def effective_n(rets: dict) -> dict:
    """실효 표본 수 — 같이 움직이는 종목은 여러 개라도 한 개 몫이다."""
    keys = sorted(rets)
    n = len(keys)
    if n < 2:
        return {"n": n, "effective_n": float(n), "mean_corr": None,
                "pairs": 0, "reason": "종목이 둘 미만"}
    vals = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            c = _corr(rets[a], rets[b])
            if c is not None:
                vals.append(c)
    if not vals:
        return {"n": n, "effective_n": None, "mean_corr": None, "pairs": 0,
                "reason": f"짝이 맞는 날이 {MIN_DAYS}일 미만 — 아직 못 잽니다"}
    mean_c = sum(vals) / len(vals)
    # 음의 평균상관은 분산 공식을 깨뜨린다 — 0으로 눌러 보수적으로 본다.
    eff = n / (1.0 + (n - 1) * max(0.0, mean_c))
    return {"n": n, "effective_n": round(eff, 2),
            "mean_corr": round(mean_c, 4), "pairs": len(vals)}


def breadth(state_dir: str = "state") -> dict | None:
    """시장별·전체 실효 표본. 장부의 종목별 가격 기록에서만 읽는다."""
    from quant.live.ledger_basics import ledger_files

    rets: dict = {}
    for path in ledger_files(state_dir):
        base = os.path.basename(path)
        if base.startswith("portfolio"):
            continue                      # 통합 계좌는 종목이 아니다
        r = _returns(_price_series(path))
        if r:
            rets[base[:-5]] = r
    if not rets:
        return None

    def _group(prefix):
        sub = {k: v for k, v in rets.items() if k.startswith(prefix)}
        return effective_n(sub) if sub else None

    out = {
        "all": effective_n(rets),
        "crypto": _group("crypto_"),
        "kr_stock": _group("kr_stock_"),
        "us_stock": _group("us_stock_"),
        "note": ("종목 수가 아니라 **정보의 양**입니다. 같이 움직이는 종목은 "
                 "여러 개라도 한 개 몫이라, 실효 표본이 종목 수보다 훨씬 "
                 "작을 수 있습니다. 자산군을 늘리는 이유가 이것입니다. "
                 "상관은 구간마다 변하므로 이 숫자는 지금 표본에서의 값이고 "
                 "미래 보장이 아닙니다."),
    }
    return out
