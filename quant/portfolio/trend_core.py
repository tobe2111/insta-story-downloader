"""추세추종 코어 — 다자산 시계열 모멘텀 + 변동성 타깃 (감사 335).

사장님 지시(2026-10-09): *"투자 실력이 지금 너무 형편이 없어"* → *"그냥 이 세상에
현존하는 가장 고성능의 퀀트 자동 투자 프로그램을 만들면 돼. 어떠한 제약 없이.
대신 수수료는 철저히 계산하고."*

■ 왜 이 엔진인가 — 실측이 가리킨 자리

  2026-08-13 ~ 10-09, 비트코인 +29% 동안 본 계좌의 코인 몫은 사실상 0이었다.
  ① 배분(HRP)이 변동성 큰 자산에 예산을 거의 안 준다 — BTC 0.07%.
  ② 그 위에서 신호도 상승을 못 잡았다 — 안전장치를 다 뺀 그림자 계좌도 −0.1%.
  즉 문제는 안전장치가 아니라 **"내일 오를까"를 800봉으로 맞히려는 신호**다.

  이 엔진은 그 질문을 바꾼다: **"요즘 오르고 있나"** — 시계열 모멘텀(TSMOM).
  공개된 증거 가운데 가장 오래·가장 넓게 살아남은 효과다(주식·채권·원자재·
  통화 지수에서 1880년대부터, Hurst·Ooi·Pedersen 2017 "A Century of Evidence
  on Trend-Following Investing"; Moskowitz·Ooi·Pedersen 2012). 코인에서도 같은
  모양이 보고됐다. 그리고 **회전이 낮다** — 수수료를 철저히 따지면 그것이
  가장 중요한 성질이다.

■ 규칙(파라미터는 문헌의 관례값 — 이 데이터로 고르지 않았다)

  · 신호: 21·63·126·252 거래일 수익 중 **양수인 비율**(0·¼·½·¾·1).
    본 계좌는 현물이라 롱/현금만 — 내림 추세는 숏이 아니라 **현금**이다.
  · 위험 예산: 자산군 5개(코인·주식·채권·실물·통화)에 **같은 위험**을 주고,
    군 안에서는 똑같이 나눈다. 그래서 코인이 HRP처럼 0.07%로 눌리지 않는다 —
    코인의 위험 몫은 5분의 1이고, 변동성이 크므로 금액은 그만큼 작다.
  · 크기: 각 자산 비중 ∝ 예산 × 신호 ÷ 그 자산의 변동성(60일 지수가중).
    포트폴리오 전체는 **사전 변동성 12%**에 맞추되, 빚은 안 낸다(총노출 ≤ 1).
    한 자산 상한 25%.
  · 매매: **주 1회**(금요일 종가 신호 → 다음 거래일 체결). 목표와 보유의 차가
    `band`보다 작으면 그 자산은 안 고친다 — 기대수익 0의 왕복 비용만 내는
    미세 조정을 막는다. 청산(목표 0)은 밴드와 무관하게 항상 실행한다.
  · 비용: **종목별 실측 편도**(`measured_cost_model`, 한국 ETF 비과세 반영)에
    호가 한 칸 하한까지. 회전 × 편도 비용을 그날 수익에서 뺀다.

■ 정직한 한계

  · 추세추종은 **횡보장에서 꾸준히 조금씩 잃는다**(잦은 진입·이탈). 그 대가로
    긴 추세와 폭락에서 번다. 기대 샤프는 대략 0.5~1.0 — 마법이 아니다.
  · 유니버스는 **오늘** 고른 40종목이다(NVDA처럼 지나고 보니 오른 종목 포함).
    과거 검증에 생존 편향이 섞인다 — 그래서 검증은 ETF만 쓴 판을 함께 낸다.
  · 현금 이자는 0으로 둔다(보수적).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

LOOKBACKS = (21, 63, 126, 252)
VOL_HALFLIFE = 60
TARGET_VOL = 0.12
MAX_GROSS = 1.0
ASSET_CAP = 0.25
BAND = 0.02
COV_WINDOW = 126
PERIODS = 252

# 자산군 — 위험 예산의 단위. 새 종목이 들어오면 여기 없을 수 있다:
# 그때는 시장으로 추정한다(코인은 crypto, 나머지는 equity).
ASSET_CLASS = {
    # 채권
    "us_stock:TLT": "rates", "us_stock:IEF": "rates", "us_stock:LQD": "rates",
    "us_stock:TIP": "rates", "kr_stock:148070.KS": "rates",
    "kr_stock:273130.KS": "rates",
    # 실물(귀금속·원자재)
    "us_stock:GLD": "real", "us_stock:SLV": "real", "us_stock:DBC": "real",
    "kr_stock:132030.KS": "real",
    # 통화
    "us_stock:UUP": "fx",
}
CLASSES = ("crypto", "equity", "rates", "real", "fx")


def asset_class(key: str) -> str:
    if key in ASSET_CLASS:
        return ASSET_CLASS[key]
    return "crypto" if key.startswith("crypto:") else "equity"


def trend_score(close: pd.Series, lookbacks=LOOKBACKS) -> pd.Series:
    """각 날짜에서 여러 기간 수익 중 **양수인 비율**(0~1). 그날 종가까지만 본다."""
    parts = []
    for lb in lookbacks:
        r = close / close.shift(lb) - 1.0
        parts.append((r > 0).astype(float).where(r.notna()))
    s = pd.concat(parts, axis=1)
    # 가장 긴 기간이 안 찬 날은 신호를 내지 않는다(짧은 기간만으로 판단 금지).
    return s.mean(axis=1).where(s.notna().all(axis=1))


@dataclass
class TrendConfig:
    lookbacks: tuple = LOOKBACKS
    target_vol: float = TARGET_VOL
    max_gross: float = MAX_GROSS
    asset_cap: float = ASSET_CAP
    band: float = BAND
    rebalance: str = "W-FRI"          # "D" · "W-FRI" · "M"
    vol_halflife: int = VOL_HALFLIFE
    cov_window: int = COV_WINDOW
    class_budget: dict = field(default_factory=lambda: {c: 1.0 for c in CLASSES})
    # 크기 방식 — 빚을 못 내는 계좌에서 둘은 크게 갈린다(2026-10-09 실측):
    #   "risk"     자산군에 같은 **위험**. 변동성 낮은 채권·달러가 금액을 다
    #              가져가 총노출 1에서 막히고, 실현 변동성이 목표의 ⅓에 그친다.
    #   "notional" 자산군에 같은 **금액**. 다만 변동성이 vol_ref보다 큰 자산은
    #              vol_ref/σ 만큼 줄인다(코인을 통째로 담지 않는다). 키우지는 않는다.
    sizing: str = "risk"
    vol_ref: float = 0.20


def target_weights(closes: pd.DataFrame, cfg: TrendConfig | None = None) -> pd.DataFrame:
    """날짜 × 자산의 **목표 비중**(그날 종가로 정한 것 — 체결은 다음 날).

    closes: 영업일 달력에 맞춘 종가(열 = 'market:symbol'). 상장 전은 NaN.
    """
    cfg = cfg or TrendConfig()
    rets = closes.pct_change(fill_method=None)
    score = pd.DataFrame({k: trend_score(closes[k], cfg.lookbacks)
                          for k in closes.columns})
    vol = rets.ewm(halflife=cfg.vol_halflife, min_periods=cfg.vol_halflife
                   ).std() * np.sqrt(PERIODS)
    out = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    classes = {k: asset_class(k) for k in closes.columns}
    for i, day in enumerate(closes.index):
        live = [k for k in closes.columns
                if pd.notna(score.at[day, k]) and pd.notna(vol.at[day, k])
                and vol.at[day, k] > 0]
        if not live:
            continue
        # 그날 살아 있는 자산군끼리 예산을 나눈다(군 안은 균등).
        by_cls: dict = {}
        for k in live:
            by_cls.setdefault(classes[k], []).append(k)
        tot_budget = sum(cfg.class_budget.get(c, 1.0) for c in by_cls)
        raw = {}
        for c, ks in by_cls.items():
            per = cfg.class_budget.get(c, 1.0) / tot_budget / len(ks)
            for k in ks:
                if cfg.sizing == "notional":
                    raw[k] = per * score.at[day, k] * min(
                        1.0, cfg.vol_ref / vol.at[day, k])
                else:
                    raw[k] = per * score.at[day, k] / vol.at[day, k]
        w = pd.Series(raw)
        if (w <= 0).all():
            continue
        if cfg.sizing == "notional":
            out.loc[day, w.index] = w.clip(upper=cfg.asset_cap).values
            continue
        # 사전 변동성 — 최근 cov_window일 공분산. 표본이 모자라면 대각 근사.
        win = rets.iloc[max(0, i - cfg.cov_window + 1): i + 1][list(w.index)]
        cov = win.cov() * PERIODS
        if cov.isna().values.any():
            d = vol.loc[day, w.index] ** 2
            cov = pd.DataFrame(np.diag(d), index=w.index, columns=w.index)
        ex_ante = float(np.sqrt(max(w.values @ cov.values @ w.values, 0.0)))
        if ex_ante <= 0:
            continue
        w = w * (cfg.target_vol / ex_ante)
        w = w.clip(upper=cfg.asset_cap)
        gross = float(w.sum())
        if gross > cfg.max_gross:
            w = w * (cfg.max_gross / gross)
        out.loc[day, w.index] = w.values
    return out


def _rebalance_days(index: pd.DatetimeIndex, rule: str) -> pd.Series:
    """그 날이 리밸런스 날인가. 주·월 단위면 그 구간의 **마지막 영업일**."""
    s = pd.Series(index, index=index)
    if rule == "D":
        return pd.Series(True, index=index)
    if rule == "M":
        last = s.groupby([index.year, index.month]).transform("max")
    else:  # 주 단위 — ISO 주의 마지막 영업일
        iso = index.isocalendar()
        last = s.groupby([iso.year.values, iso.week.values]).transform("max")
    return pd.Series(index == last.values, index=index)


@dataclass
class TrendResult:
    equity: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    cost: pd.Series
    gross: pd.Series


def simulate(closes: pd.DataFrame, one_way_cost: dict,
             cfg: TrendConfig | None = None, targets: pd.DataFrame | None = None
             ) -> TrendResult:
    """목표 비중 → 체결(다음 영업일) → 비용 차감 → 자산 곡선.

    one_way_cost: {열 이름: 편도 비용률}. 없는 열은 0.002(보수적).
    ⚠️ 룩어헤드 방지: t일 종가로 정한 목표는 t+1일 종가에 체결되고, 그 날
       수익(t→t+1)은 **옛 보유**가 번다. 새 보유는 t+1→t+2부터 번다.
    """
    cfg = cfg or TrendConfig()
    tgt = targets if targets is not None else target_weights(closes, cfg)
    rets = closes.pct_change(fill_method=None).fillna(0.0)
    rb = _rebalance_days(closes.index, cfg.rebalance)
    cost_rate = pd.Series({k: float(one_way_cost.get(k, 0.002))
                           for k in closes.columns})
    held = pd.Series(0.0, index=closes.columns)
    pending: pd.Series | None = None
    eq = 1.0
    eqs, rs, tos, cs, gs, ws = [], [], [], [], [], []
    for day in closes.index:
        # ① 오늘 수익은 어제 끝의 보유가 번다(보유는 가격 따라 표류한다)
        r_vec = rets.loc[day]
        port_r = float((held * r_vec).sum())
        eq *= (1.0 + port_r)
        grown = held * (1.0 + r_vec)
        denom = 1.0 + port_r
        held = grown / denom if denom > 0 else grown * 0.0
        # ② 어제 정한 목표를 오늘 종가에 체결
        turnover = 0.0
        cost = 0.0
        if pending is not None:
            new = held.copy()
            for k in closes.columns:
                t = float(pending.get(k, 0.0))
                cur = float(held.get(k, 0.0))
                if t == 0.0 and cur != 0.0:
                    new[k] = 0.0                       # 청산은 항상
                elif abs(t - cur) >= cfg.band:
                    new[k] = t
            delta = (new - held).abs()
            turnover = float(delta.sum())
            cost = float((delta * cost_rate).sum())
            eq *= (1.0 - cost)
            held = new
            pending = None
        # ③ 오늘 종가로 다음 목표를 정한다(리밸런스 날에만)
        if bool(rb.loc[day]):
            pending = tgt.loc[day].fillna(0.0)
        eqs.append(eq)
        rs.append(port_r)
        tos.append(turnover)
        cs.append(cost)
        gs.append(float(held.abs().sum()))
        ws.append(held.copy())
    idx = closes.index
    equity = pd.Series(eqs, index=idx)
    return TrendResult(equity=equity,
                       returns=equity.pct_change().fillna(equity.iloc[0] - 1.0),
                       weights=pd.DataFrame(ws, index=idx),
                       turnover=pd.Series(tos, index=idx),
                       cost=pd.Series(cs, index=idx),
                       gross=pd.Series(gs, index=idx))


def stats(equity: pd.Series, periods: int = PERIODS) -> dict:
    """연 수익·변동성·샤프·최대낙폭 — 비용을 뺀 자산 곡선에서."""
    equity = equity.dropna()
    if len(equity) < 2:
        return {}
    r = equity.pct_change().dropna()
    years = len(r) / periods
    cagr = float(equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0
    vol = float(r.std() * np.sqrt(periods))
    sharpe = float(r.mean() / r.std() * np.sqrt(periods)) if r.std() > 0 else 0.0
    dd = float((equity / equity.cummax() - 1).min())
    return {"cagr": round(cagr * 100, 2), "vol": round(vol * 100, 2),
            "sharpe": round(sharpe, 2), "mdd": round(dd * 100, 2),
            "calmar": round(cagr / abs(dd), 2) if dd < 0 else None,
            "years": round(years, 1)}


def align_business_days(frames: dict) -> pd.DataFrame:
    """{열: 종가 시리즈} → 영업일(월~금) 달력. 코인 주말 움직임은 월요일에 접힌다.

    ⚠️ 앞으로만 채운다(ffill) — 상장 전은 NaN 그대로다. 뒤로 채우면 상장 전
       가격이 생겨 그 기간 수익 0으로 위장된 자산이 예산을 먹는다.
    """
    cols = {}
    for k, s in frames.items():
        s = s.dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        cols[k] = s[~s.index.duplicated(keep="last")]
    if not cols:
        return pd.DataFrame()
    start = min(s.index.min() for s in cols.values())
    end = max(s.index.max() for s in cols.values())
    bdays = pd.bdate_range(start, end)
    out = {}
    for k, s in cols.items():
        full = s.reindex(s.index.union(bdays)).ffill()
        out[k] = full.reindex(bdays).where(bdays >= s.index.min())
    return pd.DataFrame(out)
