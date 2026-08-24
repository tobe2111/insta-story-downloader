"""머신러닝 전략 — '다음 봉 상승 확률'을 예측한다 (진짜 ML).

이것이 "AI 투자"의 정통 형태다. GPT 같은 LLM에게 매매를 맡기는 게 아니라,
과거 데이터로 **모델을 학습**시켜 확률을 추정한다. sklearn을 내 컴퓨터에서
돌리므로 API 토큰·요금이 전혀 들지 않는다.

    1. 피처: 수익률(다기간)·변동성 레짐·RSI·MACD·볼린저·거래량 z 등 (모두 '과거')
    2. 라벨: 다음 봉이 올랐는가(nextbar, 기본) 또는 트리플 배리어(triple —
       ±k·변동성 이익/손절 배리어와 수직 만료 중 무엇을 먼저 치는가)
    3. 학습: 로지스틱회귀 / 랜덤포레스트 / 그라디언트부스팅 / 소프트보팅 앙상블
       (선택: 표본 시간감쇠 가중 · 메타라벨링 — 방향은 추세 규칙, 크기만 ML)
    4. 사이징: 상승확률을 목표비중으로 매핑 — 확신할수록 크게(conviction sizing)

⚠️ 룩어헤드 방지가 생명이다. 각 시점의 예측은 '그 이전' 데이터로만 학습한
모델을 쓴다(walk-forward). 미래를 조금이라도 훔쳐보면 백테스트만 화려하고
실전에서 무너진다. 그리고 ML도 수익을 보장하지 않는다 — 시장의 방향 예측
정확도 상한은 대개 52~55%에 불과하며, 대부분의 모델은 거래비용을 넘는 엣지를
내지 못한다. 반드시 워크포워드·몬테카를로로 검증할 것.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.base import Strategy
from quant.strategies.rsi import rsi

# 학습에 쓰는 피처 순서(고정) — feature_importances 해석 시 이 순서를 참조한다.
FEATURE_NAMES = [
    "ret1", "ret5", "ret10", "vol", "vol_ratio", "rsi14", "rsi7",
    "ma_dist20", "ma_dist50", "mom20", "mom60", "macd_hist",
    "bb_pctb", "atr", "vol_z",
    # fs2 — 변동성 구조: 고가·저가를 쓰는 Garman-Klass 추정량(같은 기간에
    # 종가 표준편차보다 정확)과 단기/장기 실현변동성 비율(레짐 신호).
    "gk_vol", "rv_5_60",
]

# 피처셋 버전 — 피처를 '가설 그룹' 단위로 추가·기록하기 위한 태그.
# 재학습 장부에 함께 남겨, 성과 변화가 어느 피처 배치 이후인지 추적 가능하다.
#   fs1: 기본 15개 (가격 유도 지표)
#   fs2: +변동성 구조(gk_vol, rv_5_60) +코인 펀딩비(x_funding, 컬럼 있을 때)
#   fs3: +크로스에셋(x_btc_ret5·x_spy_ret5·x_tnx_chg5·x_usdkrw_ret5, 컬럼
#        있을 때) +펀딩 변화(x_funding_chg — 수급 모멘텀)
#   fs4: +미결제약정 변화(x_oi_chg5) +FRED 장단기 금리차(x_t10y2y, 키 있을 때)
#   fs5: +VIX 수준(x_vix, 미국·한국 주식) +김치 프리미엄(x_kimchi, 코인)
#   fs6: +VIX 기간구조(x_vix_ts = VIX/VIX3M — 백워데이션은 스트레스 급성기)
#   fs7: +KRX 수급(x_frgn5·x_inst5 — 외국인·기관 5일 순매수 z, 한국 주식)
#   fs8: +FRED 거시 3종(x_hy_spread 신용 스트레스 · x_usd_chg5 달러 유동성 ·
#        x_t10yie_chg5 기대인플레 변화) — 키 있을 때만
FEATURE_SET = "fs8:+fredmacro"

# 선택 피처 — 외부 소스(야후·바이낸스·FRED·KRX)가 살아 있을 때만 붙는다.
# 소스가 죽으면 컬럼이 조용히 사라지는데, 장부에는 여전히 fs8로 기록된다.
# 그러면 판정 시계가 매일 다른 구조를 재게 된다(2026-08-11 발견) — 그래서
# '오늘 실제로 몇 개가 붙었는가'를 측정해 기록·경보한다.
#
# ⚠️ 이 목록은 **실제로 만들어지는 컬럼 이름**이어야 한다(2026-08-12 감사 106).
#    전에는 여기 8개가 유령 이름이었다 — `x_btc`(실제 x_btc_ret5),
#    `x_spy`(x_spy_ret5), `x_tnx`(x_tnx_chg5), `x_usdkrw`(x_usdkrw_ret5),
#    `x_vixts`(x_vix_ts), 그리고 `x_fred_dgs10`·`x_fred_t10y2y`·
#    `x_fred_bamlh0a0hym2`는 **어디서도 만들지 않는 이름**이었다.
#    그래서 건강 계측기가 태어날 때부터 매일 "선택 피처 0/11, 전부 누락"을
#    기록했다. 아무도 몰랐던 이유는 그 값을 **어느 화면에도 안 보여줬기**
#    때문이다(감사 105) — 고장난 계측기와 보이지 않는 계측기가 서로를
#    가려 주고 있었다. tests/test_feature_health_measures_real_columns.py가
#    이름이 실제로 만들어지는지 매번 확인한다.
OPTIONAL_FEATURES = [
    "x_funding", "x_funding_chg",          # 코인 펀딩비 (_features에서 파생)
    "x_oi_chg5",                           # 미결제약정 (_features에서 파생)
    "x_btc_ret5", "x_spy_ret5",            # 크로스에셋 — 코인/미국 조류
    "x_tnx_chg5", "x_usdkrw_ret5", "x_usd_chg5",   # 금리·환율
    "x_vix", "x_vix_ts",                   # 변동성 수준·기간구조
    "x_t10y2y", "x_t10yie_chg5", "x_hy_spread",    # FRED 거시
    "x_fng", "x_kimchi",                   # 심리·김치프리미엄
    "x_frgn5", "x_inst5",                  # KRX 수급(한국주식만)
]

# 고장난 계측기가 남긴 기록의 지문 — 이 이름이 missing 목록에 있으면 그
# 기록은 2026-08-12 교정 **이전**의 것이다(사이트가 옛 0/11을 오늘의
# 사실처럼 말하지 않도록 구분한다). 과거 기록은 고치지 않는다.
BROKEN_METER_FINGERPRINT = "x_fred_dgs10"

# ── 시장·종목별로 '붙을 수 있는' 선택 피처 ─────────────────────────────
# 계측기가 건강과 고장을 구별하려면 **분모**를 알아야 한다. 예전에는 어느
# 종목이든 OPTIONAL_FEATURES 전체(17개)를 기대치로 삼았다. 그런데 코인에
# KRX 수급(x_frgn5)이 붙을 리 없고, 한국주식에 펀딩비(x_funding)가 붙을 리
# 없다. 시장마다 애초에 존재하지 않는 재료를 분모에 넣은 것이다.
#
# 결과(2026-08-14 실측): 모든 소스가 살아 있어도 한 종목이 받을 수 있는
# 최대는 9개(한국주식)였다. 그래서 사이트의 '피처 결손' 경고(최대치가
# 분모의 절반 미만이면 점등 = 8.5개 미만)는 **정상 상태에서도 거의 항상
# 켜져 있었다.** 켜져 있는 게 정상인 경고등은 꺼져 있는 것과 같다 —
# 이 저장소가 감사 105·106에서 이미 한 번 겪은 실패다.
#
# ⚠️ 이 표는 attach_cross_asset()·attach_funding()·attach_open_interest()·
#    attach_krx_flows()가 **실제로 만드는 컬럼**과 일치해야 한다. 손으로 적은
#    목록이 실제와 어긋나 계측기가 유령을 세던 사고가 이미 있었다(감사 106).
#    tests/test_feature_health.py가 진짜 부착 함수를 '모든 소스 성공' 상태로
#    돌려 이 표와 대조한다 — 표만 고치고 코드를 안 고치면 검사가 실패한다.
MARKET_OPTIONAL_FEATURES: dict[str, list[str]] = {
    # 코인: 거래소 파생(펀딩·미결제약정) + 심리·김프 + 달러/신용 거시
    "crypto": ["x_funding", "x_funding_chg", "x_oi_chg5", "x_btc_ret5",
               "x_fng", "x_kimchi", "x_usd_chg5", "x_hy_spread"],
    # 미국주식: 금리·변동성 기간구조 + FRED 거시
    "us_stock": ["x_spy_ret5", "x_tnx_chg5", "x_vix", "x_vix_ts",
                 "x_t10y2y", "x_hy_spread", "x_usd_chg5", "x_t10yie_chg5"],
    # 한국주식: 미국 전일 흐름·환율·VIX + KRX 수급 + FRED 거시
    "kr_stock": ["x_spy_ret5", "x_usdkrw_ret5", "x_vix", "x_vix_ts",
                 "x_frgn5", "x_inst5", "x_t10y2y", "x_hy_spread",
                 "x_usd_chg5"],
}

# 자기 자신은 벤치마크가 될 수 없다 — attach_cross_asset이 이 종목들에는
# 해당 컬럼을 붙이지 않는다(BTC에 x_btc_ret5, SPY에 x_spy_ret5는 자기 값).
SELF_BENCHMARK: dict[tuple[str, str], str] = {
    ("crypto", "BTC/USDT"): "x_btc_ret5",
    ("us_stock", "SPY"): "x_spy_ret5",
}


def applicable_optional_features(market: str,
                                 symbol: str | None = None) -> list[str]:
    """이 시장·종목에 **붙을 수 있는** 선택 피처 목록 (계측의 분모).

    모르는 시장이면 전체 목록을 돌려준다 — 새 시장이 추가됐을 때 분모를
    조용히 0으로 만들어 '완벽한 건강'으로 위장하지 않기 위해서다.
    """
    names = MARKET_OPTIONAL_FEATURES.get(market)
    if names is None:
        return list(OPTIONAL_FEATURES)
    drop = SELF_BENCHMARK.get((market, symbol or ""))
    return [c for c in OPTIONAL_FEATURES if c in set(names) and c != drop]


def optional_features_from_df(df) -> list[str]:
    """이 원본 df로 만들어질 선택 피처 목록 — 피처 행렬을 다시 계산하지 않는다.

    _features()의 조건과 같은 규칙을 쓴다: funding 컬럼이 있으면 x_funding·
    x_funding_chg가, oi가 있으면 x_oi_chg5가, x_로 시작하는 컬럼은 그대로
    통과한다. 매일 20종목마다 피처 행렬을 다시 만드는 비용을 피하려는 것이라,
    _features()가 바뀌면 여기도 함께 바뀌어야 한다(테스트가 일치를 강제한다).
    """
    cols = set(getattr(df, "columns", []))
    out = []
    if "funding" in cols:
        out += ["x_funding", "x_funding_chg"]
    if "oi" in cols:
        out += ["x_oi_chg5"]
    out += [c for c in cols if str(c).startswith("x_")]
    return [c for c in OPTIONAL_FEATURES if c in set(out)]


def feature_health(feats, market: str | None = None,
                   symbol: str | None = None) -> dict:
    """오늘 실제로 만들어진 피처의 건강 상태 — (총계, 필수, 선택, 누락).

    필수 피처(FEATURE_NAMES)는 가격에서 유도되므로 항상 있어야 한다. 하나라도
    없으면 데이터 자체가 망가진 것이다. 선택 피처는 외부 소스에 달려 있어
    빠질 수 있고, 빠진 사실이 기록되지 않으면 아무도 모른다.

    market(·symbol)을 주면 **그 시장에 붙을 수 있는 것**만 분모로 센다.
    안 주면 예전처럼 전체 목록이 분모다 — 시장을 모르는 호출자가 조용히
    후한 점수를 받지 않도록, 모를 때가 더 엄격한 쪽으로 남겨 둔다.
    """
    cols = set(getattr(feats, "columns", []))
    expected = (applicable_optional_features(market, symbol)
                if market else list(OPTIONAL_FEATURES))
    missing_req = [c for c in FEATURE_NAMES if c not in cols]
    present_opt = [c for c in expected if c in cols]
    missing_opt = [c for c in expected if c not in cols]
    # 이 시장에 붙을 수 없는데도 들어와 있는 컬럼 — 표가 실제와 어긋났다는
    # 신호다. 조용히 무시하면 감사 106(유령 이름)이 반대 방향으로 재발한다.
    unexpected = [c for c in OPTIONAL_FEATURES
                  if c in cols and c not in set(expected)]
    return {
        "total": len(cols),
        "required": len(FEATURE_NAMES) - len(missing_req),
        "required_expected": len(FEATURE_NAMES),
        "optional": len(present_opt),
        "optional_expected": len(expected),
        "coverage": (len(present_opt) / len(expected)) if expected else 1.0,
        "missing_required": missing_req,
        "missing_optional": missing_opt,
        "unexpected_optional": unexpected,
    }


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _features(df: pd.DataFrame, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """과거 정보만으로 구성한 피처 행렬 (룩어헤드 없음).

    모든 값은 '해당 봉 종가까지'의 정보만 사용한다. 미래 봉을 참조하는 항목은
    하나도 없다. 결측이 있는 초기 구간은 상위 로직에서 무효 처리한다.
    """
    close = df["close"]
    high = df.get("high", close)
    low = df.get("low", close)
    volume = df.get("volume")

    ret1 = close.pct_change()
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    vol20 = ret1.rolling(20).std()
    vol60 = ret1.rolling(60).std()

    # MACD 히스토그램(가격 대비 정규화)
    macd_line = _ema(close, 12) - _ema(close, 26)
    macd_hist = (macd_line - _ema(macd_line, 9)) / close

    # 볼린저 %b: 밴드 내 위치 (0=하단, 1=상단)
    bb_std = close.rolling(20).std()
    bb_pctb = (close - (ma20 - 2 * bb_std)) / (4 * bb_std)

    # ATR 유사치(가격 대비 정규화된 평균 진폭)
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean() / close

    feats = pd.DataFrame(index=df.index)
    feats["ret1"] = ret1
    feats["ret5"] = close.pct_change(5)
    feats["ret10"] = close.pct_change(10)
    feats["vol"] = vol20
    feats["vol_ratio"] = vol20 / vol60            # 변동성 레짐(단기/장기)
    feats["rsi14"] = rsi(close, 14) / 100.0
    feats["rsi7"] = rsi(close, 7) / 100.0
    feats["ma_dist20"] = (close - ma20) / ma20
    feats["ma_dist50"] = (close - ma50) / ma50
    feats["mom20"] = close.pct_change(20)
    feats["mom60"] = close.pct_change(60)
    feats["macd_hist"] = macd_hist
    feats["bb_pctb"] = bb_pctb
    feats["atr"] = atr
    # Garman-Klass 변동성(고저가 활용) — 하루 봉 하나에서도 분산 정보를 뽑아
    # 종가 표준편차보다 같은 윈도에서 추정 오차가 작다. 가격 유도지만 OHLC
    # 4개를 모두 쓰는 유일한 변동성 추정량이라 vol(종가 std)과 정보가 다르다.
    opn = df.get("open", close)
    log_hl = np.log((high / low).replace([np.inf, -np.inf], np.nan))
    log_co = np.log((close / opn).replace([np.inf, -np.inf], np.nan))
    gk_var = 0.5 * log_hl ** 2 - (2 * np.log(2) - 1) * log_co ** 2
    feats["gk_vol"] = np.sqrt(gk_var.rolling(20).mean().clip(lower=0.0))
    # 단기/장기 실현변동성 비율(5일/60일) — 1보다 크면 변동성 확장 국면.
    # 사이징의 변동성 타깃팅과 같은 재료를 예측 피처로도 재사용한다.
    feats["rv_5_60"] = ret1.rolling(5).std() / vol60
    if volume is not None and float(volume.abs().sum()) > 0:
        vmean = volume.rolling(20).mean()
        vstd = volume.rolling(20).std()
        feats["vol_z"] = (volume - vmean) / vstd
    else:
        feats["vol_z"] = 0.0

    out = feats[FEATURE_NAMES].copy()
    # 코인 펀딩비 — 데이터 로더가 df에 'funding' 컬럼을 붙여 준 경우에만 쓴다.
    # 가격에서 유도할 수 없는 진짜 신규 정보(포지셔닝 과열도)이며, 컬럼으로
    # 받는 이유는 재현성 때문이다: 입력 스냅샷(csv.gz)에 함께 보존돼
    # verify가 같은 피처로 그날의 결정을 재현할 수 있다.
    if "funding" in df.columns:
        fnd = pd.to_numeric(df["funding"], errors="coerce").ffill()
        out["x_funding"] = fnd
        # 펀딩비 '변화'(5봉) — 수준(과열도)과 다른 정보: 과열이 쌓이는 중인가
        # 풀리는 중인가(수급 모멘텀). 같은 재료의 1차 차분이라 추가 조회 없음.
        out["x_funding_chg"] = fnd.diff(5)
    # 미결제약정(수급의 두 번째 축) — 포지션이 쌓이나 풀리나. 수준은 비정상
    # 시계열이라 5봉 변화율만 피처로 쓴다. 이력이 ~30일뿐이라(거래소 보관
    # 한계) 초기 구간 NaN — valid는 기본 피처만 보므로 무해.
    if "oi" in df.columns:
        oi = pd.to_numeric(df["oi"], errors="coerce").ffill()
        out["x_oi_chg5"] = oi.pct_change(5)
    # 크로스에셋 컬럼(데이터 로더가 부착, x_ 접두) — 스냅샷·해시에 함께
    # 보존되는 재현 가능한 외부 맥락. funding과 같은 원리로 자동 포함한다.
    for col in df.columns:
        if str(col).startswith("x_") and col not in out.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
    # 외부(거시) 피처 병합 — 예: 공포탐욕지수, 펀딩비, 금리. 날짜로 정렬 후
    # 전진충전(ffill)한다. 해당 봉 시점까지 알려진 값만 쓰므로 룩어헤드 없음.
    if extra is not None and len(extra.columns):
        ext = extra.reindex(df.index).ffill()
        for col in extra.columns:
            out[f"x_{col}"] = ext[col]
    return out.replace([np.inf, -np.inf], np.nan)


def _triple_barrier_labels(df: pd.DataFrame, horizon: int = 10,
                           k: float = 1.5) -> np.ndarray:
    """트리플 배리어 라벨 — '다음 봉 방향'보다 잡음이 적은 라벨링 (López de Prado).

    각 봉 i에서 상단(진입가+k·변동성)·하단(진입가-k·변동성)·수직(horizon봉)
    세 배리어를 치고, 이후 고가/저가 경로가 어느 배리어를 먼저 치는지 본다:
        상단 먼저 → 1 (이익실현), 하단 먼저 → 0 (손절),
        같은 봉에서 둘 다 → 0 (보수적: 손절이 먼저였다고 가정),
        수직 만료 → 만료 시점 종가가 진입가보다 높으면 1, 아니면 0.
    다음-봉 라벨은 하루짜리 잡음을 그대로 배우지만, 이 라벨은 '의미 있는
    폭의 움직임'만 배운다. ⚠️ 라벨 하나가 미래 horizon봉을 보므로, 학습창
    상한도 horizon만큼 당겨야 룩어헤드가 없다(generate_signals에서 처리).
    마지막 horizon봉과 변동성 미정의 구간은 NaN(학습 제외).
    """
    close = df["close"]
    high = df.get("high", close).to_numpy(dtype=float)
    low = df.get("low", close).to_numpy(dtype=float)
    cl = close.to_numpy(dtype=float)
    vol = close.pct_change().rolling(20).std().to_numpy()
    n = len(df)
    up = cl * (1.0 + k * vol)
    dn = cl * (1.0 - k * vol)
    never = horizon + 1                      # '한 번도 안 침'을 뜻하는 오프셋
    first_up = np.full(n, never, dtype=int)
    first_dn = np.full(n, never, dtype=int)
    for h in range(horizon, 0, -1):          # 역순: 가까운 터치가 최종값이 된다
        idx = np.arange(0, n - h)
        first_up[idx] = np.where(high[idx + h] >= up[idx], h, first_up[idx])
        first_dn[idx] = np.where(low[idx + h] <= dn[idx], h, first_dn[idx])
    y = np.full(n, np.nan)
    have = np.arange(n) < n - horizon        # 수직 배리어까지 관측 가능한 봉만
    have &= np.isfinite(vol) & (vol > 0)
    i = np.where(have)[0]
    win = first_up[i] < first_dn[i]                          # 상단 먼저
    expire = (first_up[i] > horizon) & (first_dn[i] > horizon)   # 무터치 만료
    y[i] = np.where(win, 1.0,
                    np.where(expire, (cl[i + horizon] > cl[i]).astype(float),
                             0.0))          # 하단 먼저·동시 터치 → 0(보수적)
    return y


def _fit(model, X: np.ndarray, y: np.ndarray, sw: np.ndarray | None) -> None:
    """표본 가중을 지원하는 경로로 학습한다 — 미지원 조합은 무가중 폴백.

    sklearn 추정기마다 sample_weight 전달 방법이 다르다(직접 인자, 파이프라인
    단계 접두사). 조용한 실패 대신 명시적 폴백 사다리: 직접 → 파이프라인
    접두사 → 무가중. 폴백해도 학습 자체는 항상 성공한다.
    """
    if sw is None:
        model.fit(X, y)
        return
    try:
        model.fit(X, y, sample_weight=sw)
        return
    except (TypeError, ValueError):
        pass
    try:                                     # Pipeline: 마지막 단계로 라우팅
        step = model.steps[-1][0]
        model.fit(X, y, **{f"{step}__sample_weight": sw})
        return
    except Exception:  # noqa: BLE001 — 가중 미지원 조합(vote 등)은 무가중으로
        model.fit(X, y)


def _build_model(kind: str):
    """모델 팩토리. sklearn 추정기를 반환한다.

    logreg : 스케일링 + 로지스틱회귀 (빠르고 견고, 기본값)
    rf     : 랜덤포레스트 (비선형·상호작용 포착)
    gb     : 히스토그램 그라디언트부스팅 (대개 가장 강력)
    vote   : 위 셋의 소프트보팅 앙상블 (확률 평균 → 분산 감소)
    """
    from sklearn.ensemble import (
        HistGradientBoostingClassifier,
        RandomForestClassifier,
        VotingClassifier,
    )
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def logreg():
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=500, class_weight="balanced"),
        )

    def rf():
        return RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=20,
            max_features="sqrt", class_weight="balanced_subsample",
            random_state=0, n_jobs=1)

    def gb():
        return HistGradientBoostingClassifier(
            max_depth=3, max_iter=200, learning_rate=0.05,
            l2_regularization=1.0, random_state=0)

    if kind == "rf":
        return rf()
    if kind == "gb":
        return gb()
    if kind in ("vote", "ensemble"):
        return VotingClassifier(
            estimators=[("lr", logreg()), ("rf", rf()), ("gb", gb())],
            voting="soft", n_jobs=1)
    return logreg()


def pool_ready(pool, state_dir: str = "state", min_days: int = 1) -> bool:
    """이 풀 설정이 **지금** 실제로 표본을 만들 수 있는가.

    ⚠️ 왜 미리 묻나 (2026-08-20 감사 297).
       다중검정 문턱은 "얼마나 뒤졌나"에 비례해 올라간다. 그런데 풀을 못
       만들어 챔피언과 똑같은 신호를 내는 후보는 **뒤진 것이 아니라** 같은
       답을 낸 것이다. 그 후보를 시도 수에 넣으면 문턱만 올라가, 진짜로
       뒤져서 찾은 결과까지 같이 깎인다.

       실측 2026-08-19: 후보 802개 중 35개가 무동작이었고 그중 13개가
       `pool="peers"`였다. 스냅샷이 14일치뿐이라 학습 블록 대부분이 자기
       시점의 스냅샷 폴더를 못 찾는다.

    ⚠️ **후보에서 빼자는 뜻이 아니다** (사장님 지적 2026-08-20:
       "죽은 peers도 나중엔 성과 좋을 수 있는 거 아니야?"). 맞다 — peers는
       성과가 나쁜 게 아니라 아직 못 도는 것이고, 스냅샷이 쌓이면 스스로
       깨어난다. 게다가 universe와 달리 **생존 편향이 없어** 장기적으로는
       더 정직한 쪽이다. 여기서 하는 일은 '지금 돌 수 있는가'를 묻는 것뿐이고,
       돌 수 있게 되는 날 이 함수는 저절로 True가 된다.
    """
    if pool is None:
        return True
    if isinstance(pool, list):
        return bool(pool)
    from quant.utils.repro import latest_snapshot_day, snapshot_days
    if pool == "universe":
        return latest_snapshot_day(state_dir) is not None
    if pool == "peers":
        try:
            days = snapshot_days(state_dir)
        except Exception:      # noqa: BLE001 — 못 세면 막지 않는다
            return True
        return len(days) >= max(1, int(min_days))
    return True


def _labels_of(df, label: str, horizon: int, k: float, cost: float):
    """라벨 한 벌 + 그 라벨이 보는 미래 봉 수(span). **여기가 유일한 자리다.**

    ⚠️ 왜 함수로 묶었나 (2026-08-25 감사 313 — 야간 변이 전수가 잡았다).
       예전에는 이 계산이 **두 곳**에 따로 적혀 있었다:

           _build_pool()      — 동료 종목 데이터를 붙일 때
           generate_signals() — 실제 신호를 만들 때

       그런데 감사 298이 추가한 `cost` 라벨은 **_build_pool에만** 들어갔다.
       generate_signals의 분기는 `if triple ... else nextbar`라, `cost`를
       고르면 조용히 **옛 라벨로 학습**됐다. 즉 "맞혀도 손해인 상승은 사지
       않는다"는 장치가 실제 신호 경로에서는 **한 번도 켜진 적이 없다**
       (감사 289와 같은 모양 — 장치는 있는데 발동하지 않는다).

       검사도 못 잡았다. 검사가 전략을 부르지 않고 **식을 다시 적어** 두었기
       때문이다("전략이 쓰는 것과 같은 식"이라고 주석까지 달아 두고서).
       소스를 베낀 검사는 그 소스가 안 불려도 초록이다.

    ⚠️ 라벨을 또 어딘가에 적고 싶어지면, 그 자리에서 이 함수를 부르는 것이
       맞다. 세 번째 사본이 생기는 순간 같은 사고가 다시 난다.
    """
    if label == "triple":
        return _triple_barrier_labels(df, horizon, k), horizon
    nxt = df["close"].shift(-1)
    if label == "cost":
        # 다음 봉 수익이 **왕복 비용을 넘는가**. 넘지 못하는 상승은 0이다 —
        # 맞혀도 손해이므로 사는 이유가 없다(감사 298).
        lab = ((nxt / df["close"] - 1.0) > cost).astype(float)
    else:
        lab = (nxt > df["close"]).astype(float)
    lab[nxt.isna()] = np.nan        # 마지막 행은 미래가 없다
    return lab.to_numpy(), 1


class MLStrategy(Strategy):
    """워크포워드로 재학습하며 상승확률을 목표비중으로 매핑하는 ML 전략."""

    name = "ml"

    def __init__(self, model: str = "logreg", train_window: int = 250,
                 retrain_every: int = 20, threshold: float = 0.55,
                 sizing: str = "proba", min_train: int = 50,
                 allow_short: bool = False, extra_features=None,
                 calibrate: str | None = None, weight_step: float = 0.0,
                 label: str = "nextbar", label_horizon: int = 10,
                 label_k: float = 1.5, label_cost: float = 0.0,
                 meta: bool = False,
                 sample_weight: str | None = None,
                 weight_halflife: int = 125,
                 top_features: int = 0,
                 pool: object | None = None):
        if calibrate not in (None, "sigmoid", "isotonic"):
            raise ValueError(
                f"calibrate는 None·'sigmoid'·'isotonic' 중 하나여야 합니다: {calibrate!r}")
        if label not in ("nextbar", "triple", "cost"):
            raise ValueError(
                "label은 'nextbar'·'triple'·'cost' 중 하나여야 합니다: "
                f"{label!r}")
        if sample_weight not in (None, "decay"):
            raise ValueError(
                f"sample_weight는 None·'decay' 중 하나여야 합니다: {sample_weight!r}")
        if pool is not None and not (pool in ("peers", "universe")
                                     or isinstance(pool, list)):
            raise ValueError(
                "pool은 None·'peers'·'universe'·DataFrame 목록 중 "
                f"하나여야 합니다: {pool!r}")
        if pool is not None and meta:
            raise ValueError(
                "pool과 meta는 함께 쓸 수 없습니다 — 메타 라벨은 종목별 1차 "
                "방향에 종속이라 종목 간 합산이 정의되지 않습니다.")
        self.model_kind = model
        self.train_window = train_window
        self.retrain_every = max(1, retrain_every)
        self.threshold = min(0.99, max(0.5, threshold))
        self.sizing = sizing            # "proba"(확신도 비례) | "binary"(0/1)
        self.min_train = max(30, min_train)
        self.allow_short = allow_short
        # 확률 보정: 학습창 내부 3-겹 CV로 CalibratedClassifierCV를 적합한다.
        # ⚠️ 보정은 엣지를 만들지 않는다 — 모델이 말하는 70%가 실제 70%가 되게
        # 맞출 뿐이며, 과대확신 확률로 사이징할 때의 기하(복리) 손실을 줄이는
        # 용도다. 기본 None = 기존 동작 그대로.
        self.calibrate = calibrate
        # Δ비중 양자화 격자(예: 0.1). 확률의 미세한 흔들림이 매 봉 소량 매매로
        # 새는 것을 막는 회전율 절감 장치 — 수익 개선 장치가 아니다. 0 = 끔(기존).
        self.weight_step = max(0.0, float(weight_step))
        # 라벨 재설계 — nextbar(다음 봉 방향, 기존) | triple(트리플 배리어).
        # triple은 ±label_k·변동성 배리어와 label_horizon봉 수직 배리어 중
        # 어느 쪽을 먼저 치는지 배운다 — 하루짜리 잡음 대신 '의미 있는 움직임'.
        self.label = label
        self.label_horizon = max(2, int(label_horizon))
        self.label_k = max(0.1, float(label_k))
        # 비용 문턱 — label="cost"일 때 "이만큼은 넘어야 산 보람이 있다".
        #
        # ⚠️ 왜 필요한가 (2026-08-20 사장님 지시).
        #    기본 라벨 nextbar는 **다음 봉이 오르기만 하면 1**이다. 그런데
        #    우리가 실제로 벌어야 하는 것은 왕복 비용을 넘는 움직임이다 —
        #    편도 0.15%(코인)면 왕복 0.30%이고, 그 아래 움직임은 **맞혀도
        #    손해**다. 즉 모델은 지금까지 "맞히면 이기는 게임"이 아니라
        #    "맞혀도 질 수 있는 게임"을 배우고 있었다.
        #
        #    2026-08-20 실측이 그 그림자를 보여준다: 장중 실험이 순 +2.03%인데
        #    비용 전으로는 +2.32%였다 — 번 것의 상당 부분을 비용이 가져갔다.
        #
        # ⚠️ 이것은 **가설이지 개선이 아니다.** 문턱을 올리면 '산다'는 라벨이
        #    귀해져 표본이 불균형해지고, 그 자체가 학습을 어렵게 만들 수 있다.
        #    그래서 강제 적용하지 않고 오디션 후보로만 세운다 — 2단계 관문을
        #    통과할 때만 챔피언이 되고, 승격되면 장부의 파라미터에 그대로 남는다.
        #
        # 기본 0.0 = nextbar와 **완전히 같다**(대조군이 성립한다).
        self.label_cost = max(0.0, float(label_cost))
        # 메타라벨링 — 방향은 단순 추세 규칙(종가 vs MA50)이 정하고, ML은
        # '그 판단이 이익이 될 확률'만 추정해 크기를 정한다(방향·크기 분업).
        self.meta = bool(meta)
        # 표본 시간감쇠 가중 — 최근 표본에 더 큰 학습 가중(반감기 weight_halflife봉).
        # 옛 국면을 창에서 자르는 롤링 창의 연속화 버전이다.
        self.sample_weight = sample_weight
        self.weight_halflife = max(5, int(weight_halflife))
        # 풀링(패널) 학습 — 다른 종목들의 (피처, 라벨)을 학습 표본에 합친다.
        # 종목당 일봉 ~800개는 ML 기준 극소 표본이라, 전 종목 합산으로 표본을
        # ~20배 키우는 것이 남은 가장 큰 지렛대다(시장 공통 패턴만 남고 종목
        # 고유 잡음은 씻긴다). "peers"면 스냅샷(전일까지, 불변 보존)에서
        # 로드해 verify가 같은 풀을 재구성할 수 있다. 리스트 주입은 테스트용.
        # 룩어헤드 차단: 각 재학습 블록의 학습 상한 날짜 '이전' 풀 행만 쓴다.
        self.pool = pool
        # 풀 구성 결과의 흔적 — 조용한 실패가 감사 127을 몇 주 숨겼다.
        # None이면 성공(또는 아직 안 돌림), 문자열이면 그날의 실패 사유.
        self.pool_error_: str | None = None
        self.pool_rows_: int = 0
        # 스냅샷 폴더 단위 캐시 — 블록마다 풀을 다시 고르되(감사 129)
        # 같은 폴더를 여러 번 읽지 않는다.
        self._pool_cache: dict = {}
        # 피처 가지치기 — 블록마다 전체 피처로 1차 학습해 중요도 상위 K개만
        # 남기고 재학습한다(0=끔). 피처가 세대를 거듭해 늘면(fs6+) 중복·잡음
        # 피처가 과적합 재료가 된다 — 추가의 반대 방향 레버. 채택은 오디션이
        # 결정한다(챌린저로만 참전, 강제 적용 없음).
        self.top_features = max(0, int(top_features))
        # 외부(거시) 피처: DataFrame 또는 callable(df)->DataFrame. 예: 공포탐욕지수.
        self.extra_features = extra_features
        # 최근 학습에 쓰인 피처 이름(기본 15개 + 외부 피처)
        self.feature_names_: list[str] = list(FEATURE_NAMES)
        # 최근 학습 모델의 피처 중요도(있으면) — 사후 해석용
        self.last_importances_: dict[str, float] | None = None
        # 마지막 봉의 예측 상승확률 — 신뢰도 곡선(보정 검증) 기록용
        self.last_proba_: float | None = None

    # ── 확률 → 목표비중 매핑 ────────────────────────────────────────────
    def _size(self, prob_up: np.ndarray, *, long_only: bool = False) -> np.ndarray:
        """상승확률 배열을 [-1,1] 목표비중으로 변환한다.

        proba 모드: threshold를 데드존 경계로 두고 확신할수록 크게 태운다.
                    weight_step>0이면 결과를 격자에 반올림(양자화)한다.
        binary 모드: 임계 넘으면 풀 포지션(1/-1), 아니면 관망(0).
        long_only=True: 낮은 확률을 숏이 아니라 관망으로 해석한다 — 메타라벨링
        (확률='이익 확률')처럼 방향이 이미 정해진 경우의 크기 계산용.
        """
        if self.sizing == "binary":
            w = np.where(prob_up >= self.threshold, 1.0, 0.0)
            if self.allow_short and not long_only:
                w = np.where(prob_up <= 1.0 - self.threshold, -1.0, w)
            return w

        gate = self.threshold - 0.5            # 데드존 반폭 (예: 0.05)
        span = max(1e-9, 0.5 - gate)           # 경계~확신(1.0)까지의 폭
        edge = prob_up - 0.5
        w = np.zeros_like(edge, dtype=float)
        long = edge > gate
        w[long] = np.clip((edge[long] - gate) / span, 0.0, 1.0)
        if self.allow_short and not long_only:
            short = edge < -gate
            w[short] = -np.clip((-edge[short] - gate) / span, 0.0, 1.0)
        if self.weight_step > 0.0:
            # Δ비중 양자화: 확률 지터로 인한 소량 리밸런스 주문을 죽인다.
            # 가장 가까운 격자점으로 반올림 → 오차는 step/2 이내, 경계는 유지.
            w = np.clip(np.round(w / self.weight_step) * self.weight_step, -1.0, 1.0)
        return w

    def _pool_at(self, cols, cutoff) -> tuple | None:
        """그 **학습 블록 시점에 존재하던** 스냅샷으로 풀을 만든다 (감사 129).

        예전에는 프레임 **맨 끝** 날짜로 폴더를 한 번만 골랐다. 그러면 같은
        과거 봉이라도 뒤에 미래 데이터가 얼마나 붙어 있느냐에 따라 풀이
        달라진다 — 미래를 잘라내면 과거 신호가 바뀐다. 이 저장소가 가장
        엄격하게 지키는 성질(인과성)이 정확히 그렇게 깨졌고, 링 인과성
        검사가 54봉이 바뀐다고 잡았다.

        (감사 127에서 풀링을 살리기 전까지는 풀 자체가 죽어 있어 이 결함도
         보이지 않았다 — 죽은 장치가 또 하나를 가려 주고 있었다.)

        블록마다 폴더를 다시 고르되 **폴더 단위로 캐시**한다. 인접 블록은
        대개 같은 폴더를 쓰므로 실제 읽기 횟수는 폴더 수만큼이다.
        """
        from quant.utils.repro import (latest_snapshot_day,
                                       load_snapshot_pool,
                                       load_snapshot_pool_day,
                                       snapshot_pool_day)
        if self.pool == "universe":
            # ── 오늘의 유니버스로 푼다 (생존 편향을 감수하고 표본을 얻는다)
            # "peers"는 인과성이 완벽하지만 **6개월 뒤에야 쓸모가 생긴다** —
            # 스냅샷이 매일 하나씩 쌓이므로, 선발 구간(끝에서 120봉 앞)까지
            # 닿으려면 그만큼의 날이 필요하다. 실측(2026-08-14): 재학습 블록
            # 28개 중 **28개**가 풀을 찾지 못했다. 즉 지금 이 순간 종목당
            # 800봉이라는 ML 극소 표본을 개선할 방법이 없다는 뜻이다.
            #
            # 이 모드는 **가장 최근 스냅샷 폴더**를 쓴다. 가격 행은 여전히
            # 학습 상한 이전만 쓰므로(_merge_pool) 시계열 룩어헤드는 없다 —
            # 미래를 잘라내도 과거 신호가 바뀌지 않는다.
            #
            # ⚠️ 대신 **생존 편향**이 들어온다. 그 폴더의 종목 목록은
            #    '오늘까지 살아남아 유니버스에 있는' 종목이고, 그건 사후
            #    정보다. README가 모든 백테스트에 깔려 있다고 인정하는 바로
            #    그 편향을 학습 표본에까지 들이는 것이다.
            #
            #    그래서 강제 적용하지 않는다 — 오디션 후보로만 참전하고,
            #    2단계 관문을 통과할 때만 챔피언이 된다. 승격되면 그 사실이
            #    장부의 파라미터(pool: universe)에 그대로 남는다.
            day = latest_snapshot_day("state")
            if day is None:
                self.pool_error_ = "스냅샷 폴더가 없다"
                return None
            key = ("universe", day, tuple(cols))
            if key not in self._pool_cache:
                self._pool_cache[key] = self._build_pool(
                    cols, load_snapshot_pool_day("state", day))
            return self._pool_cache[key]

        day = snapshot_pool_day("state", str(cutoff)[:10])
        if day is None:
            return None
        key = (day, tuple(cols))
        if key not in self._pool_cache:
            self._pool_cache[key] = self._build_pool(
                cols, load_snapshot_pool("state", str(cutoff)[:10]))
        return self._pool_cache[key]

    def _build_pool(self, cols, frames) -> tuple | None:
        """풀 표본 (날짜, X, y)를 만든다 — 타깃 피처 열 순서에 정렬.

        각 풀 프레임에 타깃과 같은 피처·라벨 규칙을 적용하고, 타깃에 없는
        컬럼은 버리고 없는 값은 0(정보 없음)으로 채운다. 실패해도 학습은
        계속하되(풀은 보너스 표본) **죽었다는 사실은 남긴다**(감사 127).
        """
        try:
            dates, xs, ys = [], [], []
            for pdf in frames:
                if pdf is None or len(pdf) < 80 or "close" not in pdf:
                    continue
                pf = _features(pdf)
                # 라벨은 **한 곳**에서 만든다(_labels_of) — 신호 경로와 같은
                # 규칙이어야 한다. 두 곳에 적었더니 한쪽에만 `cost`가 있었다.
                py, _span = _labels_of(pdf, self.label, self.label_horizon,
                                       self.label_k, self.label_cost)
                base_cols = [c for c in pf.columns if c in FEATURE_NAMES]
                # ⚠️ 제자리 연산(&=) 금지 — pandas 3.0의 to_numpy()는 **읽기
                #    전용** 배열을 돌려준다. 예전 코드는 여기서
                #    `ValueError: output array is read-only`를 냈고, 아래
                #    `except Exception: return None`이 그것을 삼켜
                #    **풀링(패널) 학습이 통째로 죽어 있었다**(감사 127).
                #    풀을 넣든 안 넣든 신호가 한 봉도 다르지 않았는데,
                #    오디션 링에는 '풀링 후보'가 매일 두 개씩 올라갔다.
                #    isfinite는 NaN도 걸러내므로 ~isnan은 필요 없다.
                ok = np.asarray(pf[base_cols].notna().all(axis=1), dtype=bool)
                ok = ok & np.isfinite(np.asarray(py, dtype=float))
                if not ok.any():
                    continue
                pX = pf.reindex(columns=cols).fillna(0.0).to_numpy()
                # ⚠️ 정수 epoch로 바꾸지 않는다(감사 128). 예전에는 `.asi8`를
                #    썼는데 pandas 3.0의 asi8은 **마이크로초**를 돌려주고,
                #    비교 상대인 `pd.Timestamp.value`는 **나노초**였다.
                #    1000배 차이라 `dates < cut`이 **언제나 전부 참** —
                #    학습 상한 필터가 통째로 없는 것과 같았고, 미래 종목의
                #    행이 모든 학습 블록에 섞여 들어갔다. 룩어헤드다.
                #    단위가 붙은 datetime64로 두면 numpy가 알아서 맞춘다.
                idx = pd.DatetimeIndex(pdf.index).normalize().to_numpy(
                    dtype="datetime64[ns]")
                dates.append(idx[ok])
                xs.append(pX[ok])
                ys.append(py[ok])
            if not xs:
                self.pool_error_ = "풀 프레임에서 쓸 수 있는 표본이 없다"
                return None
            self.pool_error_ = None
            self.pool_rows_ = int(sum(len(d) for d in dates))
            return (np.concatenate(dates), np.vstack(xs), np.concatenate(ys))
        except Exception as exc:  # noqa: BLE001
            # ⚠️ 조용히 넘어가지 않는다(감사 127). 이 자리의 침묵이 위 결함을
            #    몇 주 동안 숨겼다. 풀이 없어도 학습은 계속하되(보너스 표본이
            #    맞다), **죽었다는 사실은 남긴다.**
            from quant.utils.logging import get_logger
            get_logger("strategies.ml").warning(
                "풀링 표본 구성 실패 — 풀 없이 학습한다: %s: %s",
                type(exc).__name__, exc)
            self.pool_error_ = f"{type(exc).__name__}: {exc}"[:200]
            return None

    def _merge_pool(self, X_tr, y_tr, sw_tr, pool_rows, cutoff):
        """학습 상한(cutoff) '이전' 풀 행을 학습 표본 뒤에 붙인다."""
        dates, Xp, yp = pool_rows
        # ⚠️ 정수 epoch 비교 금지(감사 128) — 단위가 어긋나도 조용히 통과한다.
        #    datetime64끼리 비교하면 numpy가 단위를 맞춰 준다.
        cut = np.datetime64(pd.Timestamp(cutoff).normalize(), "ns")
        sel = dates < cut
        if not sel.any():
            return X_tr, y_tr, sw_tr
        X2 = np.vstack([X_tr, Xp[sel]])
        y2 = np.concatenate([y_tr, yp[sel].astype(int)])
        if sw_tr is not None:
            # 풀 행의 시간감쇠는 달력일 기준(일봉이라 봉 나이와 사실상 동일).
            # 여기도 같은 이유로 timedelta64로 나눈다 — 상수 나눗셈은 단위가
            # 바뀌는 순간 조용히 1000배 틀린 가중치를 만든다.
            days = ((cut - dates[sel]) / np.timedelta64(1, "D")).astype(float)
            sw2 = np.concatenate([
                sw_tr, np.power(0.5, days / self.weight_halflife)])
        else:
            sw2 = None
        return X2, y2, sw2

    def _record_importances(self, model) -> None:
        """가능하면 피처 중요도/계수를 기록한다(해석용, 실패해도 무시)."""
        try:
            est = model
            if hasattr(est, "feature_importances_"):
                imp = np.asarray(est.feature_importances_, dtype=float)
            elif hasattr(est, "named_steps"):  # 파이프라인(logreg)
                clf = list(est.named_steps.values())[-1]
                imp = np.abs(np.asarray(clf.coef_, dtype=float)).ravel()
            else:
                return
            if len(imp) == len(self.feature_names_):
                self.last_importances_ = dict(zip(self.feature_names_, imp.tolist()))
        except Exception:  # noqa: BLE001  # pragma: no cover
            pass

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        try:
            import sklearn  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "ML 전략에는 scikit-learn이 필요합니다: pip install scikit-learn") from exc

        extra = self.extra_features
        if callable(extra):
            extra = extra(df)
        feats = _features(df, extra)
        self.feature_names_ = list(feats.columns)
        # 라벨은 **한 곳**에서 만든다(_labels_of) — 동료 데이터 경로와 같은
        # 규칙이어야 한다. 두 곳에 적었더니 `cost` 라벨이 여기에만 빠져,
        # 그 장치가 실제 신호 경로에서 한 번도 켜지지 않았다(감사 313).
        y, span = _labels_of(df, self.label, self.label_horizon,
                             self.label_k, self.label_cost)

        # 메타라벨링의 1차 신호 — 단순 추세 규칙(종가 vs MA50). 학습이 필요
        # 없는 결정적 규칙이라 룩어헤드가 없고, ML(2차)은 '이 방향 판단이
        # 이익이 될 확률'만 배운다. 롱온리면 하락 추세는 0(관망).
        side = np.zeros(len(df))
        if self.meta:
            ma50 = df["close"].rolling(50).mean()
            trend = np.sign((df["close"] - ma50).to_numpy())
            side = trend if self.allow_short else np.clip(trend, 0.0, 1.0)
            side[~np.isfinite(side)] = 0.0
            # 메타 라벨: '1차 방향대로 갔으면 이익이었나' — 방향이 있는 봉만.
            #   롱(+1)이고 라벨 1(상승/이익배리어) → 1 · 숏(-1)이고 라벨 0 → 1
            y_meta = np.where(np.isnan(y), np.nan,
                              ((side > 0) & (y == 1))
                              | ((side < 0) & (y == 0)))
            y_meta = np.where(side == 0, np.nan, y_meta)  # 관망 봉은 학습 제외
            y = y_meta.astype(float)

        # 외부 피처(x_*)의 결측은 0으로 대치한다(아래 valid는 기본 피처만 보므로
        # 이 대치가 실제로 쓰인다). 0은 이상적 중립값은 아니지만, 외부 피처가
        # 아직 시작 전인 구간에서 상수(정보 없음)로 취급돼 무해하다.
        X = feats.fillna(0.0).to_numpy()
        # ⚠️ valid는 '기본 15개 피처'만으로 판정한다. 외부 피처까지 AND에 넣으면,
        # 외부 피처가 시작 전(예: 공포탐욕지수는 ~2018년부터)이거나 정렬이 어긋나
        # NaN인 구간이 학습·예측에서 통째로 빠져 모델이 '조용히 전 구간 무거래'가
        # 된다(에러도 없이). 외부 피처는 선택적 맥락일 뿐 필수가 아니다.
        base_cols = [c for c in feats.columns if c in FEATURE_NAMES]
        valid = feats[base_cols].notna().all(axis=1).to_numpy()
        n = len(df)
        out = np.zeros(n)
        probs = np.full(n, np.nan)     # 봉별 예측확률 — 신뢰도 곡선(보정 검증)용
        model = None
        active_cols = None             # 가지치기 시 이 블록 모델이 쓰는 피처 열
        # 주입형(리스트)은 호출자가 준 프레임이 전부라 한 번만 만들면 된다.
        # 스냅샷형("peers")은 **블록마다** 그 시점의 폴더로 다시 고른다
        # (감사 129 — 프레임 끝 날짜로 한 번만 고르면 인과성이 깨진다).
        pool_rows = (self._build_pool(feats.columns, self.pool)
                     if isinstance(self.pool, list) else None)

        # 재학습 구간(블록) 단위로 학습→배치 예측: 행마다 예측하던 것보다 훨씬 빠르다.
        i = self.train_window
        while i < n:
            # 최근 train_window봉만 학습에 사용(롤링) → 옛 국면을 버리고 학습량도 O(n²)로
            # 커지지 않는다. 상한은 i-span: 라벨 하나가 미래 span봉을 보므로
            # (nextbar=1, triple=horizon), 마지막 학습 라벨이 참조하는 미래가
            # 예측 시점 i를 절대 넘지 않게 한다(엄격한 룩어헤드 차단).
            lo = max(0, i - self.train_window)
            hi = i - span
            mask = valid[lo:hi] & ~np.isnan(y[lo:hi])
            if mask.sum() >= self.min_train:
                yt = y[lo:hi][mask].astype(int)
                if len(np.unique(yt)) > 1:      # 두 클래스 모두 있어야 학습 가능
                    # 확률 보정: 학습창 '내부'의 3-겹 CV로만 적합 → 룩어헤드 없음.
                    # 소수 클래스 표본이 3 미만이면 3-겹 층화 CV가 불가능하므로
                    # 그 블록만 비보정 모델로 학습한다(조용한 실패 대신 명시적 규칙).
                    def _wrapped():
                        m = _build_model(self.model_kind)
                        if (self.calibrate is not None
                                and np.bincount(yt).min() >= 3):
                            from sklearn.calibration import CalibratedClassifierCV
                            m = CalibratedClassifierCV(
                                m, method=self.calibrate, cv=3)
                        return m
                    sw = None
                    if self.sample_weight == "decay":
                        # 시간감쇠: 창의 최신 표본 가중 1.0, 반감기마다 절반.
                        age = (hi - 1) - np.arange(lo, hi)[mask]
                        sw = np.power(0.5, age / self.weight_halflife)
                    X_tr, y_tr, sw_tr = X[lo:hi][mask], yt, sw
                    rows = pool_rows
                    if rows is None and self.pool is not None:
                        rows = self._pool_at(feats.columns, df.index[hi])
                    if rows is not None:
                        # 풀링: 학습 상한 날짜 이전의 타 종목 표본을 합친다
                        X_tr, y_tr, sw_tr = self._merge_pool(
                            X_tr, y_tr, sw_tr, rows, df.index[hi])
                    model = _wrapped()
                    _fit(model, X_tr, y_tr, sw_tr)
                    self._record_importances(model)
                    # 가지치기: 전체 피처 1차 학습의 중요도로 상위 K개를 골라
                    # 그 열만으로 재학습한다 — 이 블록의 예측도 같은 열만 쓴다.
                    # 중요도를 못 뽑는 조합(보정 래퍼 등)은 가지치기 생략.
                    active_cols = None
                    if (self.top_features
                            and self.top_features < X.shape[1]
                            and self.last_importances_):
                        ranked = sorted(self.last_importances_,
                                        key=lambda k: -abs(
                                            self.last_importances_[k]))
                        keep = set(ranked[:self.top_features])
                        active_cols = np.array(
                            [j for j, nm in enumerate(self.feature_names_)
                             if nm in keep])
                        model = _wrapped()
                        _fit(model, X_tr[:, active_cols], y_tr, sw_tr)

            block_end = min(i + self.retrain_every, n)
            if model is not None:
                rows = np.arange(i, block_end)
                rows = rows[valid[i:block_end]]
                if self.meta:                   # 1차 방향이 없는 봉은 관망
                    rows = rows[side[rows] != 0]
                if len(rows):
                    Xp = X[rows] if active_cols is None else X[rows][:, active_cols]
                    p = model.predict_proba(Xp)[:, 1]
                    if self.meta:
                        # p = '1차 방향 판단이 이익이 될 확률' → 크기만 정하고
                        # 방향은 1차 규칙(side)이 정한다. 기록용 상승확률은
                        # 롱이면 p, 숏이면 1-p로 환산(신뢰도 곡선과 호환).
                        out[rows] = side[rows] * self._size(p, long_only=True)
                        probs[rows] = np.where(side[rows] > 0, p, 1.0 - p)
                    else:
                        out[rows] = self._size(p)
                        probs[rows] = p
            i = block_end

        # 마지막 봉(오늘 판단)의 예측확률 — 매일 기록에 남겨, "AI가 60%라고
        # 한 날들의 실제 적중률"(신뢰도 곡선)을 사이트에서 검증할 수 있게 한다.
        self.last_proba_ = (float(probs[-1])
                            if n and np.isfinite(probs[-1]) else None)
        return self._finalize(pd.Series(out, index=df.index), df.index)
