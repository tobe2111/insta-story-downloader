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

# ── 넓은 ETF 목록(감사 336 ③) — **규칙으로 정한** 거래 후보 ───────────────
#
# 지금 40종목은 사람이 하나씩 고른 것이라 생존 편향이 있다(오늘 살아 있고
# 잘 나간 종목). 여기는 반대로 "자산군마다 가장 크고 오래된 상장지수펀드"라는
# 규칙으로 고른다 — 미국 상장, 2012년 이전 상장, 하루 거래대금이 큰 것.
# 그래서 개별 회사가 아니라 **시장 전체의 조각**이고, 망한 회사가 빠지는
# 문제가 거의 없다. 자산군은 위험 예산의 단위다.
BROAD_ETFS = {
    # 미국 주식(지수·업종)
    "SPY": "equity", "QQQ": "equity", "IWM": "equity", "MDY": "equity",
    "XLK": "equity", "XLF": "equity", "XLE": "equity", "XLV": "equity",
    "XLI": "equity", "XLP": "equity", "XLU": "equity", "XLY": "equity",
    "XLB": "equity", "VNQ": "equity", "IBB": "equity", "SMH": "equity",
    # 해외 주식
    "EFA": "equity", "EEM": "equity", "EWJ": "equity", "VGK": "equity",
    "EWZ": "equity", "FXI": "equity", "EWY": "equity", "EWT": "equity",
    "EWA": "equity", "EWC": "equity", "EWG": "equity", "EWU": "equity",
    "INDA": "equity",
    # 채권(국채·물가채·회사채·신흥국)
    "SHY": "rates", "IEF": "rates", "TLT": "rates", "TIP": "rates",
    "LQD": "rates", "HYG": "rates", "EMB": "rates", "BWX": "rates",
    "MUB": "rates",
    # 실물(귀금속·원자재)
    "GLD": "real", "SLV": "real", "DBC": "real", "USO": "real",
    "UNG": "real", "DBA": "real", "DBB": "real",
    # 통화
    "UUP": "fx", "FXE": "fx", "FXY": "fx", "FXF": "fx", "FXA": "fx",
}
for _t, _c in BROAD_ETFS.items():
    ASSET_CLASS.setdefault(f"us_stock:{_t}", _c)


def asset_class(key: str) -> str:
    if key in ASSET_CLASS:
        return ASSET_CLASS[key]
    return "crypto" if key.startswith("crypto:") else "equity"


def trend_sign(close: pd.Series, lookbacks=LOOKBACKS) -> pd.Series:
    """여러 기간 수익 **부호의 평균**(−1~1) — 양방향 트랙용. 그날 종가까지만."""
    parts = []
    for lb in lookbacks:
        r = close / close.shift(lb) - 1.0
        parts.append(np.sign(r).where(r.notna()))
    s = pd.concat(parts, axis=1)
    return s.mean(axis=1).where(s.notna().all(axis=1))


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
    # 선물 트랙(감사 335 ②) — 내림 추세에 **숏**을 잡는다. 신호는 여러 기간
    # 수익 부호의 평균(−1~1). 현물 본 계좌는 False(내림 = 현금).
    allow_short: bool = False
    # 보유 비용 — 선물 자금조달(펀딩)을 **롱·숏 모두** 연율로 물린다(보수적:
    # 실제로는 방향마다 부호가 반대라 한쪽은 받는다). 현물은 0.
    carry_annual: float = 0.0


def target_weights(closes: pd.DataFrame, cfg: TrendConfig | None = None) -> pd.DataFrame:
    """날짜 × 자산의 **목표 비중**(그날 종가로 정한 것 — 체결은 다음 날).

    closes: 영업일 달력에 맞춘 종가(열 = 'market:symbol'). 상장 전은 NaN.
    """
    cfg = cfg or TrendConfig()
    rets = closes.pct_change(fill_method=None)
    score = pd.DataFrame({k: (trend_sign(closes[k], cfg.lookbacks)
                              if cfg.allow_short
                              else trend_score(closes[k], cfg.lookbacks))
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
        if (w == 0).all():
            continue
        if cfg.sizing == "notional":
            out.loc[day, w.index] = w.clip(-cfg.asset_cap, cfg.asset_cap).values
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
        w = w.clip(-cfg.asset_cap, cfg.asset_cap)
        gross = float(w.abs().sum())
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
        # 선물 보유 비용(펀딩) — 영업일당 연율/252를 총노출에 물린다.
        port_r -= float(held.abs().sum()) * cfg.carry_annual / PERIODS
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


# 검증에서 잰 후보들 — 이름으로 부른다(장부·엔진 스위치가 같은 이름을 쓴다).
VARIANTS = {
    "risk12": dict(sizing="risk", target_vol=0.12),
    "risk20": dict(sizing="risk", target_vol=0.20),
    "notional30": dict(sizing="notional", vol_ref=0.30),
    "notional50": dict(sizing="notional", vol_ref=0.50),
}

# 선물 트랙 후보(감사 335 ②) — 코인 5종목 · 레버리지 상한 3배(트랙의 기존 한도)
# · 한 종목 상한 1배 · 펀딩 연 11%를 롱·숏 모두에 물린다(0.01%/8시간, 보수적).
FUTURES_CARRY = 0.1095
FUTURES_VARIANTS = {
    "fut_long20": dict(target_vol=0.20, max_gross=3.0, asset_cap=1.0,
                       carry_annual=FUTURES_CARRY),
    "fut_long40": dict(target_vol=0.40, max_gross=3.0, asset_cap=1.0,
                       carry_annual=FUTURES_CARRY),
    "fut_ls20": dict(target_vol=0.20, max_gross=3.0, asset_cap=1.0,
                     allow_short=True, carry_annual=FUTURES_CARRY),
    "fut_ls40": dict(target_vol=0.40, max_gross=3.0, asset_cap=1.0,
                     allow_short=True, carry_annual=FUTURES_CARRY),
}


def variant_config(name: str | None) -> TrendConfig:
    return TrendConfig(**({**VARIANTS, **FUTURES_VARIANTS}.get(name or "", {})))


# ── 두 번째 수익원: 종목 간 상대 강세(횡단면 모멘텀) — 감사 336 ─────────
#
# 추세추종은 "이 자산이 오르고 있나"(시계열)를 본다. 이것은 "같은 날 여럿 중
# 누가 더 센가"(횡단면)를 본다. 두 효과는 문헌에서 따로 측정되고(Jegadeesh·
# Titman 1993; Asness·Moskowitz·Pedersen 2013 "Value and Momentum Everywhere"),
# 서로 완전히 겹치지 않는다 — 섞으면 횡보장 손실을 일부 덜어 준다.
#
# 규칙(문헌 관례값): 12개월 수익에서 최근 1개월을 뺀 값(최근 1개월은 되돌림이
# 있어 뺀다)으로 줄 세워 **상위 ¼**만, 그중 **절대 수익도 양수**인 것만(이중
# 모멘텀 — 다 같이 빠지는 장에서 '덜 빠진 것'을 사지 않는다) 역변동성으로 담는다.
# 월 1회. 롱/현금만.
XS_LOOKBACK = 252
XS_SKIP = 21
XS_TOP = 0.25


def xsmom_weights(closes: pd.DataFrame, cfg: TrendConfig | None = None) -> pd.DataFrame:
    cfg = cfg or TrendConfig()
    rets = closes.pct_change(fill_method=None)
    mom = closes.shift(XS_SKIP) / closes.shift(XS_LOOKBACK) - 1.0
    vol = rets.ewm(halflife=cfg.vol_halflife, min_periods=cfg.vol_halflife
                   ).std() * np.sqrt(PERIODS)
    out = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for i, day in enumerate(closes.index):
        m = mom.loc[day].dropna()
        v = vol.loc[day]
        m = m[v.reindex(m.index).notna() & (v.reindex(m.index) > 0)]
        if len(m) < 4:
            continue
        k = max(1, int(round(len(m) * XS_TOP)))
        pick = m.sort_values(ascending=False).iloc[:k]
        pick = pick[pick > 0]                         # 이중 모멘텀
        if pick.empty:
            continue
        w = (1.0 / v[pick.index])
        w = w / w.sum()
        win = rets.iloc[max(0, i - cfg.cov_window + 1): i + 1][list(w.index)]
        cov = win.cov() * PERIODS
        if cov.isna().values.any():
            cov = pd.DataFrame(np.diag(v[w.index] ** 2), index=w.index,
                               columns=w.index)
        ex = float(np.sqrt(max(w.values @ cov.values @ w.values, 0.0)))
        if ex > 0:
            w = w * (cfg.target_vol / ex)
        w = w.clip(upper=cfg.asset_cap)
        if w.sum() > cfg.max_gross:
            w = w * (cfg.max_gross / w.sum())
        out.loc[day, w.index] = w.values
    return out


def combine_sleeves(closes: pd.DataFrame, sleeves: list,
                    cfg: TrendConfig | None = None, shares: list | None = None
                    ) -> pd.DataFrame:
    """여러 소매(sleeve)의 목표 비중을 **위험 기준으로** 섞는다 (감사 337).

    각 소매는 이미 자기 목표 변동성으로 만들어져 있다. 몫대로 더한 뒤, 서로
    덜 겹치는 만큼 줄어든 변동성을 목표로 다시 키운다 — 총노출은 max_gross,
    한 종목은 ±asset_cap까지(숏 허용 소매가 섞일 수 있어 절댓값으로 잰다).
    """
    cfg = cfg or TrendConfig()
    n = len(sleeves)
    shares = shares or [1.0 / n] * n
    w = sum(sl.reindex(index=closes.index, columns=closes.columns).fillna(0.0) * sh
            for sl, sh in zip(sleeves, shares))
    rets = closes.pct_change(fill_method=None)
    out = w.copy()
    for i, day in enumerate(closes.index):
        row = w.loc[day]
        row = row[row != 0]
        if row.empty:
            continue
        win = rets.iloc[max(0, i - cfg.cov_window + 1): i + 1][list(row.index)]
        cov = win.cov() * PERIODS
        if cov.isna().values.any():
            continue
        ex = float(np.sqrt(max(row.values @ cov.values @ row.values, 0.0)))
        if ex <= 0:
            continue
        r = (row * (cfg.target_vol / ex)).clip(-cfg.asset_cap, cfg.asset_cap)
        g = float(r.abs().sum())
        if g > cfg.max_gross:
            r = r * (cfg.max_gross / g)
        out.loc[day] = 0.0
        out.loc[day, r.index] = r.values
    return out


def blend_weights(closes: pd.DataFrame, cfg: TrendConfig | None = None,
                  share: float = 0.5) -> pd.DataFrame:
    """추세(시계열)와 상대 강세(횡단면)를 **위험 기준 반반**으로 섞는다.

    두 소매(sleeve)는 각자 목표 변동성으로 만든 뒤 반씩 더한다 — 둘의 상관이
    1보다 낮으면 섞은 쪽 변동성이 목표보다 작아지므로, 그만큼 다시 키우되
    빚은 안 낸다(총노출 ≤ max_gross).
    """
    cfg = cfg or TrendConfig()
    return combine_sleeves(closes, [target_weights(closes, cfg),
                                    xsmom_weights(closes, cfg)],
                           cfg, [1 - share, share])
