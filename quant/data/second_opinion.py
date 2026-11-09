"""두 번째 소스의 의견 — 오늘 매매에 쓰는 시세를 **다른 소스**와 대조한다 (2026-11-09 감사 363).

사장님: *"모두 진행해"* — 개선 ②. 장기 시세와 매일 시세가 사실상 무료 소스
하나(야후)에 기대고 있었다. 그 소스가 틀린 값을 주면(분할 미반영 · 통화 혼동 ·
잘린 봉) 엔진 선택·검증·장부가 **조용히** 틀어진다 — 숫자는 멀쩡해 보인다.
`quant/data/crosscheck.py`가 대조 함수를 이미 갖고 있었는데 **아무도 부르지
않았다**(만들어 두고 안 쓰는 계측기 — 감사 105의 또 다른 얼굴).

■ 무엇을 대조하나

  **최근 며칠의 일수익**을 견준다(가격 수준이 아니다). 주 소스(yfinance)는
  배당 조정가, 보조 소스(Stooq)는 무조정가라 수준은 원래 다르다. 수익률은 배당일
  하루를 빼면 같아야 한다 — 그래서 문턱을 **하루 2%p**로 넉넉히 둔다(ETF 분배금은
  대개 1% 아래). 2%p를 넘게 갈리면 둘 중 하나는 그 종목의 하루를 틀리게 말하고 있다.

■ 어긋나면

  그 종목은 **그날 매매하지 않는다**(데이터 장애와 같은 길 — 보유는 그대로,
  평가는 마지막으로 알던 값). 어느 쪽이 맞는지는 이 함수가 알 수 없다 — 그래서
  고르지 않고 멈춘다. 장부에 사유가 남고 결손 경보가 울린다.

■ 정직한 한계

  · **한국 종목은 독립 소스가 없다**(야후 HTTP는 같은 회사의 같은 자료다). 그렇다고
    적고 대조하지 않는다 — '같은 소스 두 번'을 대조라고 부르면 거짓 안심이다.
  · 보조 소스가 응답하지 않으면 **못 쟀다**로 적고 막지 않는다(못 잰 것과 틀린
    것은 다른 사건이다).
"""
from __future__ import annotations

import pandas as pd

DAYS = 5
TOL = 0.02
#: 보조 소스가 연달아 이만큼 응답하지 않으면 그 시장은 그날 더 묻지 않는다 —
#: 응답 없는 소스에 40종목을 하나씩 기다리면 배치가 그만큼 늦어진다.
BREAK_AFTER = 3
_dead: dict[str, int] = {}


def _second(market: str, symbol: str, primary: str):
    """(이름, 가져오기) 또는 (None, 이유) — 주 소스와 **다른** 소스만."""
    if market == "us_stock":
        from quant.data.stock import StockDataProvider
        p = StockDataProvider(market="us_stock")
        if primary != "stooq":
            return "stooq", lambda: p._via_stooq(symbol, "1d", None, None, 30)
        return "yahoo-http", lambda: p._via_yahoo_http(symbol, "1d", None, None, 30)
    if market == "crypto":
        from quant.data.crypto import CryptoDataProvider, spot_ladder
        for ex in spot_ladder():
            if ex != primary:
                def fetch(ex=ex):
                    df = CryptoDataProvider(exchange=ex).get_ohlcv(symbol, "1d", limit=30)
                    if str(df.attrs.get("source") or ex) == primary:
                        raise ValueError("보조 거래소가 주 거래소로 넘어갔다")
                    return df
                return ex, fetch
        return None, "다른 거래소 없음"
    return None, "독립 소스 없음(같은 회사의 같은 자료뿐)"


def compare_returns(primary: pd.DataFrame, second: pd.DataFrame,
                    days: int = DAYS, tol: float = TOL) -> dict:
    a = primary["close"].astype(float)
    b = second["close"].astype(float)
    a.index = pd.to_datetime(a.index).normalize()
    b.index = pd.to_datetime(b.index).normalize()
    a, b = a[~a.index.duplicated(keep="last")], b[~b.index.duplicated(keep="last")]
    common = a.index.intersection(b.index).sort_values()[-(days + 1):]
    if len(common) < 3:
        return {"ok": None, "why": f"겹치는 날 {len(common)}일 — 못 쟀다", "n": len(common)}
    ra = a.loc[common].pct_change().dropna()
    rb = b.loc[common].pct_change().dropna()
    gap = (ra - rb).abs()
    worst = float(gap.max())
    out = {"n": int(len(gap)), "max_gap_pct": round(worst * 100, 3),
           "ok": bool(worst <= tol)}
    if not out["ok"]:
        day = gap.idxmax()
        out["why"] = (f"{day.date()} 하루 수익 {ra[day]*100:+.2f}% vs {rb[day]*100:+.2f}% "
                      f"(차이 {worst*100:.2f}%p > {tol*100:.0f}%p)")
    return out


def second_opinion(market: str, symbol: str, primary_df: pd.DataFrame) -> dict:
    """주 소스 시세를 다른 소스와 대조한 결과. 대조할 수 없으면 ok=None과 이유."""
    primary = str(primary_df.attrs.get("source") or "?")
    name, fetch = _second(market, symbol, primary)
    if name is None:
        return {"ok": None, "why": fetch, "primary": primary}
    if _dead.get(market, 0) >= BREAK_AFTER:
        return {"ok": None, "why": f"{name} 연속 무응답 {BREAK_AFTER}회 — 오늘은 더 묻지 않는다",
                "primary": primary, "second": name}
    try:
        df2 = fetch()
        if df2 is None or df2.empty:
            raise ValueError("빈 결과")
    except Exception as exc:  # noqa: BLE001 — 못 잰 것은 막지 않는다
        _dead[market] = _dead.get(market, 0) + 1
        return {"ok": None, "why": f"{name} 응답 없음: {str(exc)[:80]}",
                "primary": primary, "second": name}
    _dead[market] = 0
    out = compare_returns(primary_df, df2)
    out.update({"primary": primary, "second": name})
    return out
