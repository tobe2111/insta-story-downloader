"""매일 1사이클 자동 페이퍼 운용 — 사용자가 아무것도 안 해도 돌아간다.

GitHub Actions가 매일 밤 이 모듈을 실행한다:
    1. 어제까지의 페이퍼 계좌 상태(현금·포지션)를 state/paper/에서 이어받고
    2. 최신 실데이터로 현재 챔피언 전략의 목표 비중을 계산해
    3. 가짜 돈으로 매매한 뒤(수수료 반영)
    4. 자산·적중률 기록을 다시 state/paper/에 저장하고 웹사이트용
       docs/status.json 을 갱신한다 → 사이트만 열어도 매일 결과가 보인다.

⚠️ 이것은 페이퍼(모의) 운용이다 — 실제 돈이 오가지 않으며, 결과가 좋아도
미래 수익을 보장하지 않는다. 목적은 '전략을 방치 상태에서 장기 검증'하는 것.
실거래 전환은 사람이 직접 결정해야 한다(자동으로 실거래를 켜지 않는다).
"""
from __future__ import annotations

import json
import math
import os
import re

import numpy as np

# 상수와 순수 계산은 **의존성 없는 모듈**에서 가져와 여기서 다시 내보낸다.
# SNS 캡션처럼 numpy가 없는 환경에서 도는 코드가 숫자 하나 읽으려고 매매
# 엔진 전체를 끌어오지 않게 하기 위함이다(2026-08-11 감사 102 — 그렇게
# 끌어오다가 그날 밤 게시가 ModuleNotFoundError로 죽었다).
from quant.live.ledger_basics import (          # noqa: F401 — 재수출
    GOAL_KRW,
    add_deposit,
    PORTFOLIO_START_CASH,
    START_CASH,
    chrono,
    day_return_pct,
    drawdown_from_index,
    _flows_by_date,
    equity_curve_kpis,
    holdings_view,
    is_archive,
    max_drawdown_from_index,
    pending_deposits,
    principal_of,
    time_weighted_return,
    twr_index,
)

from quant.live.retrain import STATE_DIR, champion_spec, champion_strategy
from quant.utils.logging import get_logger

log = get_logger("daily_paper")


# ── 체결 현실성 규칙 ────────────────────────────────────────────────
# 새벽 판단 시점(KST 05:30)에 실제로 체결 가능한 첫 시점은 시장마다 다르다:
#   코인: 24시간 시장 → 판단 직후 체결 가능(마지막 종가 근사)
#   한국/미국 주식: 장 마감 후 판단 → 다음 세션 '시가'에 체결(개장 갭을
#   그대로 감수한다 — 마감 종가로 즉시 체결 처리하면 실현 불가능한 가격이다)
IMMEDIATE_FILL_MARKETS = {"crypto", "synthetic"}

# 소수점 매매가 가능한 시장 — 페이퍼 계좌는 소수점 수량을 그대로 사지만,
# 실계좌에서는 시장마다 가능 여부가 다르다(감사 137).
#   crypto   : 원래 소수점이 정상
#   us_stock : 증권사에 따라 소수점 매매 지원(국내 증권사 다수가 제공)
#   kr_stock : **국내주식은 소수점 매매가 없다** — 1주 단위로만 산다
# 이 목록에 없는 시장은 '1주 미만 배정 = 실계좌에서 살 수 없음'이 된다.
FRACTIONAL_MARKETS = {"crypto", "synthetic", "us_stock"}


def _fit_to_budget(targets: dict, prices: dict, equity: float,
                   cap: float = 1.0, conviction: dict | None = None,
                   ) -> tuple[dict, dict]:
    """목표 비중을 **실제로 살 수 있는** 비중으로 바꾼다 (감사 137 후속).

    운영자 결정(2026-08-12): *"금액이 문제면 비싼 건 미루면 되잖아.
    예산에 맞게 투자하면 되지."*

    운영자 결정(2026-08-13): *"예산이 있는대로 유연하게. 1주 값이 그 종목
    예산을 넘으면 기존 투자한 종목을 매도하고 사도 된다."* 그리고 무엇을
    포기할지는 — *"이건 비율로 따지는 게 아니야. 수익률이 더 높을 것이라
    판단되는 최우선 선택을 하는 거지."*

    그래서 정수 주 시장의 예산은 **n등분이 아니라 확신도 순으로 채운다.**

    규칙
      ① 소수점 매매가 안 되는 시장(국내주식)은 **정수 주로 내림**한다.
      ② 그 시장에 배정된 돈을 **한 주머니(pool)로 모으고, 확신도가 높은
         종목부터** 채운다. 자기 배정금액으로 1주를 못 사는 종목도 주머니에
         남은 돈이 있으면 **1주는 산다** — 모자란 만큼은 확신도가 낮은
         종목이 쓸 돈이었다. 그 종목들의 목표가 0이 되므로 이미 들고 있던
         물량은 자연히 **매도**된다. 그것이 "팔아서라도 산다"의 실체다.
      ③ 주머니가 비면 나머지는 **미룬다**(deferred) — 억지로 사지 않는다.
      ④ 정수 주 시장에서 끝내 남은 돈은 **소수점 시장에 재배분**한다.
         현금으로 놀리면 총노출이 목표보다 낮아져 위험 예산이 샌다.
      ⑤ 재배분해도 한 종목 과집중 상한(cap)은 넘지 않는다.

    ⚠️ **집중도 상한을 따로 두지 않는 이유**(사장님 결정). 주머니 총액이
       원래 그 시장에 배정된 돈이라 총노출은 그대로다 — 한 종목이 커지면
       다른 종목이 그만큼 줄어들 뿐, 레버리지가 생기지 않는다. 대신 "오늘
       국내주식은 사실상 1~2종목"인 날이 생기고, 그 사실은 `lot_infeasible`
       과 `lot_priority`로 장부에 남는다. 숨기지 않는다.

    ⚠️ 1주 값이 주머니보다 비싼 종목은 **어차피 못 산다.** 실측(2026-08-13,
       원금 100만원): SK하이닉스 1주 1,504,000원 = 계좌 전체보다 비싸다.
       유연화로 풀리는 문제가 아니라 원금의 문제다 — 그대로 미루고 적는다.

    conviction: 종목별 확신도(클수록 우선). 없으면 |목표비중|을 쓴다.
        동점이면 키 이름 순 — 같은 입력이 같은 결과를 내야 한다(재현성).

    ⚠️ 주식은 '다음 세션 시가'에 체결되므로 여기서 쓴 오늘 가격과 체결가가
       다르다. 이 계산은 **계획 시점의 실현 가능성** 판단이고, 실제 수량은
       체결 시점에 브로커가 다시 정한다.

    반환: (조정된 목표 비중, 미룬 종목 {키: {budget, price, pool_left}})
    """
    import math
    if equity <= 0:
        return dict(targets), {}
    out: dict = {}
    deferred: dict = {}
    freed = 0.0

    # 정수 주 시장과 그 밖을 가른다. 가격을 모르는 종목은 손대지 않는다
    # (모르면 숫자를 만들지 않는다).
    lot_keys = []
    for key, w in targets.items():
        px = prices.get(key)
        if key.split(":")[0] in FRACTIONAL_MARKETS or not px or px <= 0:
            out[key] = w
        else:
            lot_keys.append(key)

    # 확신도 높은 순 → 같으면 키 순(재현성). 확신도가 없으면 |목표비중|.
    conv = conviction or {}
    lot_keys.sort(key=lambda k: (-abs(float(conv.get(k, targets[k]))), k))

    pool = sum(abs(float(targets[k])) for k in lot_keys) * equity
    for key in lot_keys:
        w = float(targets[key])
        px = float(prices[key])
        want = math.floor(abs(w) * equity / px)
        if want <= 0 and abs(w) > 0:
            want = 1          # 자기 예산으로 못 사도 1주는 노린다(② 유연화)
        lots = min(want, math.floor(pool / px)) if px > 0 else 0
        if lots <= 0:
            if abs(w) > 0:
                deferred[key] = {"budget": round(abs(w) * equity, 2),
                                 "price": round(px, 2),
                                 "pool_left": round(pool, 2)}
            out[key] = 0.0
            freed += abs(w)
            continue
        spent = lots * px
        pool -= spent
        got = spent / equity
        out[key] = math.copysign(got, w)
        freed += abs(w) - got
    if freed > 1e-12:
        # 재배분 대상 — 원래 사려던 종목 중 '얼마든 더 담을 수 있는' 쪽.
        # 정수 주 시장은 다시 내림에 걸리므로 여기서는 제외한다(자산이
        # 커지면 ①에서 자연히 한 주가 붙는다).
        room = {k: abs(v) for k, v in targets.items()
                if k.split(":")[0] in FRACTIONAL_MARKETS and abs(v) > 0}
        tot = sum(room.values())
        if tot > 0:
            for k, base in room.items():
                add = min(freed * base / tot, max(0.0, cap - abs(out[k])))
                out[k] = math.copysign(abs(out[k]) + add, targets[k])
    return out, deferred


def _fill_cost(market: str) -> float:
    """편도 체결 비용(수수료+거래세+슬리피지) — 시장별 현실 프리셋."""
    from quant.backtest.costs import CostModel
    cm = CostModel.for_market(market)
    return float(cm.fee + cm.slippage)


def _first_bar_after(df, bar_ts: str):
    """decided_bar 이후 첫 봉의 (타임스탬프, 시가). 없으면 (None, None)."""
    for ix, r in df.iterrows():
        if str(ix) > bar_ts:
            return str(ix), float(r["open"])
    return None, None


# 재현성 해시 — 공용 구현(quant.utils.repro)을 그대로 쓴다
from quant.utils.repro import code_sha as _code_sha
from quant.data.barclock import bar_status
from quant.data.fx import needs_fx, to_krw, usdkrw
from quant.utils.repro import data_sha256 as _data_sha256
from quant.utils.repro import env_fingerprint as _env_fingerprint

# 회계 기준 버전 — v0.5.0부터 '다음 시가 체결 + 거래세·슬리피지' 기준.
# 이전 기록(종가 즉시 체결)은 재계산하지 않고 그대로 둔다(과거 불변 약속).
# 이 태그로 어느 기준으로 계산된 기록인지 영구히 구분할 수 있다.
ACCOUNTING_VERSION = "next_open_v2"

# 무행동 밴드 — 목표 비중이 어제 대비 5%p 미만으로만 달라졌으면 리밸런싱을
# 생략한다. 확률·변동성의 미세한 흔들림이 만드는 잔조정은 기대수익 0에
# 왕복 수수료만 확정 지불하는 거래다. 청산(비중 0)은 밴드와 무관하게 실행.
# 종목 단위 데모 계좌의 절대 리밸런스 밴드(자산 대비).
#
# 통합 계좌는 상대 밴드(REBALANCE_BAND_REL_*)로 옮겼지만 종목 계좌는 이 값을
# 유지한다 — 의도적이다. 이 계좌들은 '측정 도구'다: 확률 보정 표본과 체결
# 갭(fill_check) 실측이 여기서 나온다. 회전을 줄이면 측정 표본도 함께 줄어
# 정작 통합 계좌의 밴드를 정할 근거가 늦게 쌓인다. 각 계좌가 단일 종목에
# 풀사이즈로 들어가므로 절대 밴드 5%도 상대적으로 촘촘하지 않다.
REBALANCE_BAND = 0.05


def _risk_for(market: str):
    """시장별 연율화 계수를 반영한 RiskManager — 코인 365일, 주식 252거래일.

    연율화가 틀리면 변동성 타깃팅 배율이 주식에서 약 20% 어긋난다(√(365/252)).
    """
    from quant.risk import RiskManager
    from quant.risk.manager import RiskConfig
    ppy = 365 if market in ("crypto", "synthetic") else 252
    # vol_model="har": 후행 변동성 대신 HAR-RV 예측(50/50 수축)으로 사이징 —
    # 변동성 군집의 초입에서 먼저 비중을 줄인다(수익 장치가 아니라 복리 방어).
    return RiskManager(RiskConfig(periods_per_year=ppy, vol_model="har"))


def _last_proba(strategy) -> float | None:
    """전략(래퍼 포함)에서 마지막 봉의 ML 예측확률을 꺼낸다. 없으면 None.

    핫리로드 래퍼(_impl)·레짐/이벤트 래퍼(base)를 재귀로 벗겨 가며 찾는다 —
    기록된 확률은 설명 문장·신뢰도 곡선과 '같은 숫자'여야 한다(사후 검증 가능).
    """
    seen = 0
    while strategy is not None and seen < 6:
        p = getattr(strategy, "last_proba_", None)
        if p is not None:
            return float(p)
        strategy = getattr(strategy, "_impl", None) or getattr(
            strategy, "base", None)
        seen += 1
    return None


# 드리프트 측정 창 — 기준(과거)과 비교(최근)의 길이. 문턱을 외우지 않고
# **이 크기의 귀무분포**와 견주기 위해 상수로 뽑아 둔다(감사 99).
DRIFT_N_REF, DRIFT_N_NEW = 250, 60


def _drift_psi(df) -> float | None:
    """최근 60일 수익률 분포의 PSI(기준: 그 이전 ~250일) — 레짐 이탈 감지.

    ⚠️ 예전 주석은 "0.25 이상이면 경고"라고 적혀 있었다. 그 문턱은 신용평가
       업계의 **대표본** 관행이라 여기(최근 60거래일)에는 맞지 않는다.
       드리프트가 전혀 없어도 이 크기에서는 중앙값 0.19가 나오고, 29%가
       0.25를 넘는다(감사 99). 판단은 `drift_grade()`에 맡긴다.
    표본 부족이면 None(계산불가를 0으로 위장하지 않는다).
    """
    try:
        from quant.robustness import psi
        rets = df["close"].pct_change().dropna()
        if len(rets) < 130:
            return None
        recent = rets.iloc[-DRIFT_N_NEW:]
        ref = rets.iloc[-(DRIFT_N_REF + DRIFT_N_NEW):-DRIFT_N_NEW]
        v = psi(list(ref), list(recent))
        return round(float(v), 4) if v == v else None
    except Exception:  # noqa: BLE001 — 감시 실패가 본류를 막으면 안 된다
        return None


def drift_grade(value) -> str | None:
    """PSI 값을 **이 저장소가 쓰는 표본 크기 기준으로** 등급화한다."""
    if not isinstance(value, (int, float)) or value != value:
        return None
    from quant.robustness import interpret_psi
    return interpret_psi(float(value),
                         n_ref=DRIFT_N_REF, n_new=DRIFT_N_NEW)


def drift_reference() -> dict:
    """같은 표본 크기에서 '아무 일도 없을 때' 나오는 PSI 분포(잣대)."""
    from quant.robustness.drift import psi_null
    ref = dict(psi_null(DRIFT_N_REF, DRIFT_N_NEW))
    ref["n_ref"], ref["n_new"] = DRIFT_N_REF, DRIFT_N_NEW
    return ref


def _paper_path(market: str, symbol: str, state_dir: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{market}_{symbol}")
    return os.path.join(state_dir, "paper", f"{safe}.json")


def _all_paper_histories(state_dir: str) -> list:
    """전 종목 페이퍼 장부의 history 목록 — 확률대 적중률의 합산 표본 재료.

    종목별 25건 축적에는 한 달 이상 걸리므로, 그때까지는 전 종목 합산으로
    표본을 조기 확보한다(이질성 트레이드오프는 해설 문구에 명시). 포트폴리오
    통합 계좌 파일은 종목 확률이 없으므로 제외. 실패는 빈 목록(해설 재료일
    뿐 — 실패가 기록을 막으면 안 된다).
    """
    import glob as _glob
    out = []
    for pth in sorted(_glob.glob(os.path.join(state_dir, "paper", "*.json"))):
        if "portfolio" in os.path.basename(pth).lower():
            continue
        try:
            with open(pth, encoding="utf-8") as f:
                h = json.load(f).get("history")
            if isinstance(h, list) and h:
                out.append(h)
        except (OSError, ValueError):
            continue
    return out


def _load_paper(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"cash": START_CASH, "quantity": 0.0, "avg_price": 0.0,
            "last_bar": None, "history": []}


def run_daily_paper(market: str, symbol: str, *, timeframe: str = "1d",
                    lookback: int = 400, state_dir: str = STATE_DIR,
                    require_real_data: bool = True) -> dict:
    """페이퍼 계좌 상태를 이어받아 하루치 사이클을 1회 수행한다(멱등).

    같은 봉에 두 번 실행되면 두 번째는 아무것도 하지 않는다 — 재실행/재시도가
    이중 매매를 만들지 않게 하는 안전장치.
    """
    from quant.broker import PaperBroker
    from quant.broker.base import Position
    from quant.data import get_provider
    from quant.robustness.accuracy import directional_accuracy
    from quant.utils.jsonio import atomic_write_json, cap_history

    df = get_provider(market).get_ohlcv(symbol, timeframe, limit=lookback)
    if df.empty:
        raise RuntimeError(f"{market}/{symbol}: 데이터 수신 실패")
    if require_real_data and df.attrs.get("synthetic_fallback"):
        raise RuntimeError(
            f"{market}/{symbol}: 실데이터 수신 실패 → 합성 폴백 감지. "
            "가짜 데이터로 페이퍼 기록을 오염시키지 않도록 중단합니다.")
    # 데이터 무결성 검사 — 통합 계좌와 같은 기준(2026-08-11 감사에서 배선).
    # 중복 봉·음수 가격·OHLC 모순 위의 기록은 그럴듯한 거짓말이 된다.
    from quant.data.quality import is_severe, scan_ohlcv
    _q = scan_ohlcv(df)
    if is_severe(_q):
        raise RuntimeError(
            f"{market}/{symbol}: 데이터 무결성 위반 "
            f"{ {k: v for k, v in _q.items() if v} } — 기록하지 않습니다.")
    if market == "crypto":
        # 펀딩비 컬럼 — ML의 x_funding 피처 재료(실패 시 조용히 생략)
        from quant.data.funding import attach_funding
        df = attach_funding(df, symbol)
        from quant.data.openinterest import attach_open_interest
        df = attach_open_interest(df, symbol)
    if market == "kr_stock":
        from quant.data.krx import attach_krx_flows
        df = attach_krx_flows(df, symbol)
    from quant.data.crossasset import attach_cross_asset
    df = attach_cross_asset(df, market, symbol)

    path = _paper_path(market, symbol, state_dir)
    st = _load_paper(path)
    last_bar = str(df.index[-1])
    if st.get("last_bar") == last_bar:
        log.info("%s/%s: 같은 봉(%s)에 이미 실행됨 — 건너뜀", market, symbol, last_bar)
        return {"skipped": True, "last_bar": last_bar}

    strategy = champion_strategy(market, symbol, state_dir)
    # 신호는 완성된 봉으로만 — 통합 계좌와 같은 규칙(감사 71).
    # 코인은 UTC 일봉의 '오늘' 봉이 항상 진행 중이라 그대로 쓰면 모델이
    # 미완성 봉(레인지 평균 36% 축소)을 마지막 행으로 받는다.
    df_sig = _signal_frame(market, df, timeframe)
    signals = strategy.generate_signals(df_sig)
    weight = float(_risk_for(market).size_positions(df_sig, signals).iloc[-1])
    price = float(df["close"].iloc[-1])      # 체결·평가는 지금 가격

    # 실적 가드 — 발표 ±1일 창에서는 비중 절반(미국 주식만). 발표일 갭 위험은
    # 하루짜리 방향 모델의 엣지가 가장 약한 지점이다. 쓴 캘린더는 state에
    # 캐시되고 발동 내역은 기록에 남는다(재현성·투명성).
    earnings_guard = None
    if market == "us_stock" and abs(weight) > 0:
        from datetime import date as _edate
        from quant.data.earnings import earnings_guard_factor
        ef, edate = earnings_guard_factor(
            symbol, _edate.fromisoformat(str(df_sig.index[-1])[:10]),
            state_dir=state_dir)
        if edate and ef < 1.0:
            weight = float(weight * ef)
            earnings_guard = {"date": edate, "factor": ef}

    # 부분 켈리 상한 — 이 종목의 OOS(페이퍼) 통계가 30일 이상 쌓이면
    # ½켈리로 최대 비중을 제한한다(과대 베팅의 복리 벌칙 방어).
    kelly_cap = _kelly_cap_from_history(st.get("history") or [])
    if kelly_cap < 1.0:
        weight = float(np.clip(weight, -kelly_cap, kelly_cap))

    # 오늘 판단의 근거를 사람 말로 — 방송·사이트에 "새벽 판단 기준"으로 표시.
    # 원비중(위험 조절 전)과 이 종목 장부(확률대 과거 적중률), 전 종목 합산
    # 장부(종목 표본 25건 미달 시 폴백)를 함께 넘겨 상세 해설을 만든다.
    from quant.live.explain import explain_signal
    reason = explain_signal(champion_spec(market, symbol, state_dir), df,
                            weight, getattr(strategy, "_impl", None),
                            raw_weight=float(signals.iloc[-1]),
                            history=st.get("history") or [],
                            pooled_history=_all_paper_histories(state_dir))
    if earnings_guard:
        reason += (f" · 🛡 실적 가드: 발표({earnings_guard['date']}) 임박 → "
                   "비중 절반")
    # 의회(혼합) 운용 중이면 구성을 함께.
    # ⚠️ 위 설명은 **의석 1위 의원**의 논리다. 의원이 둘 이상이면 오늘의 비중은
    #    의원 신호의 의석 가중합이라 리더 하나로 설명되지 않는다 — 그 사실을
    #    문장으로 밝힌다(2026-08-11 감사). 지금은 전 종목이 의원 1명이라
    #    설명이 곧 실제지만, 승격이 쌓이면 어긋나기 시작한다.
    try:
        from quant.live.parliament import parliament_summary
        from quant.live.retrain import _key, load_champions
        entry = load_champions(state_dir).get(_key(market, symbol))
        ps = parliament_summary(entry) if entry else None
        if ps:
            reason += (f" · 🏛 의회 운용: {ps} — 위 설명은 의석 1위 의원의 "
                       f"논리이며, 오늘의 비중은 의원 신호를 의석 비중으로 "
                       f"가중 평균한 값입니다")
    except Exception:  # noqa: BLE001 — 표기 실패가 기록을 막으면 안 된다
        pass

    broker = PaperBroker(cash=float(st["cash"]), fee=_fill_cost(market))
    if abs(float(st.get("quantity", 0.0))) > 0:
        broker._positions[symbol] = Position(       # 어제의 포지션 복원
            symbol, float(st["quantity"]), float(st.get("avg_price", 0.0)))

    fill = None
    # ① 어제 결정의 대기 주문 체결 — 주식은 '다음 세션 시가'에서만 체결된다.
    pending = st.get("pending")
    if pending and pending.get("decided_bar"):
        fbar, fopen = _first_bar_after(df, pending["decided_bar"])
        if fopen is not None:
            eq_open = broker.equity({symbol: fopen})
            broker.target_weight(symbol, float(pending["weight"]), fopen,
                                 eq_open, rebalance_band=REBALANCE_BAND)
            fill = {"price": round(fopen, 6), "bar": fbar,
                    "weight": round(float(pending["weight"]), 4),
                    "decided_bar": pending["decided_bar"]}
            st["pending"] = None
    # ② 오늘의 결정 — 코인은 즉시 체결, 주식은 다음 시가 대기열에 올린다
    if market in IMMEDIATE_FILL_MARKETS:
        eq_now = broker.equity({symbol: price})
        broker.target_weight(symbol, weight, price, eq_now,
                             rebalance_band=REBALANCE_BAND)
    else:
        st["pending"] = {"weight": round(weight, 4), "decided_bar": last_bar}

    pos = broker.get_position(symbol)
    equity = broker.equity({symbol: price})

    acc = directional_accuracy(df_sig, signals, window=60)
    psi_v = _drift_psi(df)
    record = {
        "date": last_bar[:10], "price": price, "weight": round(weight, 4),
        # ⚠️ 위 `weight`는 **오늘 내린 결정**이다. 주식은 '다음 세션 시가'
        #    체결이라, 기록 시점에 계좌가 실제로 들고 있는 것은 어제 결정의
        #    결과다. 둘을 같은 이름으로 부르면 화면이 거짓말을 한다 —
        #    실측(2026-08-13, 20개 참고 계좌 중 8개가 어긋남):
        #        us_stock:META  기록 비중 0.0000 / 실제 보유 0.1027
        #        us_stock:SPY   기록 비중 0.0000 / 실제 보유 0.0591
        #    "비중 0%"라고 적힌 계좌가 10%를 들고 있었다. 오늘 아침 통합
        #    계좌 카드에서 고친 것과 **같은 결함**이다(목표를 잔고라 부르기).
        #    결정과 잔고를 둘 다 남긴다.
        "held_weight": (round(pos.quantity * price / equity, 4)
                        if pos and equity else 0.0),
        # 소수점 매매가 없는 시장(한국 주식)에서 소수 주를 들고 있으면
        # **실계좌에서 재현할 수 없다**(감사 222). 참고 계좌는 1만원으로
        # 시작하는데 한국 주식은 1주가 10만~150만원이라, 정수 주를 강제하면
        # 대부분 영영 빈 계좌가 되어 종목별 비교 자체가 사라진다. 그래서
        # 막지 않고 **밝힌다** — 통합 계좌의 lot_infeasible과 같은 태도다.
        "fractional_lot": (
            bool(pos and pos.quantity
                 and market not in FRACTIONAL_MARKETS
                 and abs(pos.quantity - round(pos.quantity)) > 1e-9)),
        "equity": round(equity, 2),
        "return_pct": round((equity / START_CASH - 1) * 100, 2),
        "hit_rate": acc.get("hit_rate"),
        # ⚠️ 적중률은 **표본 수와 함께** 남긴다(2026-08-12 감사 111).
        #    포지션을 잡은 봉만 세므로 관망이 많은 종목은 n이 아주 작다.
        #    n 없이 "적중률 64%"만 보이면 n=3짜리 우연이 실력처럼 읽힌다 —
        #    감사 94(카드가 신뢰구간 없이 비율을 방송)와 같은 계열이고,
        #    이쪽은 첫 화면 전 종목 행에 매일 나간다.
        "hit_n": acc.get("n"),
        # 채점에서 뺀 보합 봉 수(감사 168). 방향이 없던 봉은 방향 예측을
        # 채점할 수 없어 분모에서 빼는데, 몇 봉을 뺐는지 안 남기면
        # '보합이 없었다'와 구별되지 않는다.
        "hit_flat": acc.get("n_flat"),
        "champion": champion_spec(market, symbol, state_dir)["params"],
        "reason": reason,
        # 체결 현실성: 실제 체결(다음 시가) 내역과 비용 반영 여부를 기록
        "fill": fill,
        "fill_cost": round(_fill_cost(market), 6),
        # 재현성: 코드 커밋 + 입력 데이터 해시 — verify로 재검증 가능
        "code_sha": _code_sha(),
        "data_sha256": _data_sha256(df),
        "env": _env_fingerprint(),
        "accounting": ACCOUNTING_VERSION,
        # 예측확률(ML 챔피언일 때) — 신뢰도 곡선("60%라고 한 날 실제 적중률")과
        # 설명 문장 대조의 원천 숫자. 서술은 이 숫자에서 기계 생성된다.
        "prob_up": _last_proba(strategy),
        # 드리프트 감시 — 최근 60일 수익률 분포가 기준 분포에서 벗어난 정도.
        # 숫자만 남기면 읽는 사람이 대표본 문턱(0.25)으로 읽는다. 그래서
        # **잣대와 등급을 같이** 남긴다 — 장부만 보고도 "이게 잡음인가"에
        # 답할 수 있어야 한다(감사 99).
        "drift_psi": psi_v,
        "drift_grade": drift_grade(psi_v),
        "drift_ref": drift_reference() if psi_v is not None else None,
        # 실적 가드 발동 흔적(발동 없으면 None) — 왜 비중이 절반인지의 답
        "earnings_guard": earnings_guard,
        # 부분 켈리 상한(1.0=비개입) — OOS 통계가 비중을 제한한 흔적
        "kelly_cap": round(kelly_cap, 4) if kelly_cap < 1.0 else None,
        # 결정에 쓴 마지막 봉이 아직 만들어지는 중이었는가(코인만 해당).
        # 값이 있으면 이 기록의 price는 그날 일봉 종가가 아니다 — 공개
        # 차트와 대조하려는 사람이 오해하지 않도록 장부에 남긴다(감사 56).
        "bar_partial": bar_status(market, df.index[-1], timeframe),
        # 어느 소스에서 받았는가(감사 135) — 통합 계좌와 같은 규칙.
        # 주식 보조 소스는 무조정가라 배당·분할 날 값이 미세하게 다르다.
        "data_source": str(df.attrs.get("source") or "?"),
    }
    # 확률 보정 준비(표시 전용) — '보정 어긋남'이 표본 30건 이상에서 통계로
    # 확정된 확률대에 한해 경험 보정값을 병기한다. 사이징에는 개입하지 않음.
    try:
        from quant.live.calibration_guard import recalibrated_prob
        adj, active = recalibrated_prob(
            record["prob_up"], _all_paper_histories(state_dir))
        if active:
            record["prob_up_cal"] = round(float(adj), 4)
    except Exception:  # noqa: BLE001 — 보정 준비 실패가 기록을 막으면 안 된다
        pass
    st.update({
        "market": market, "symbol": symbol, "start_cash": START_CASH,
        "cash": broker.get_cash(), "quantity": pos.quantity,
        "avg_price": pos.avg_price, "last_bar": last_bar,
    })
    st["history"] = cap_history(chrono(st["history"] + [record]))
    atomic_write_json(path, st)

    hr = record["hit_rate"]
    hr_txt = f"{hr:.1%}" if isinstance(hr, float) and hr == hr else "N/A"
    print(f"[{record['date']}] {market}/{symbol} 페이퍼 — 자산 {equity:,.2f} "
          f"({record['return_pct']:+.2f}%) · 비중 {weight:+.2f} · 적중률 {hr_txt}")
    return record


# 비용 비례 상대 리밸런스 밴드 — "얼마나 벗어나야 고쳐 잡을 것인가".
#
# 실측(2026-08-11): 매일 20종목 중 7.4개(37%)를 갈아타고 있었다. 총노출 100%
# 기준으로 환산하면 연 40%(낙관 가정으로도 11%)의 비용인데 기대수익은 8.8%다 —
# 엣지가 있든 없든 수익이 날 수 없는 구조. 원인은 포트폴리오가 밴드를 종목 수로
# 나눠(0.05/20=0.25%) 사실상 무력화한 것이었다.
#
# 고칠 때 절대 밴드를 키우는 대신 '목표 포지션 대비 상대 밴드'를 쓴다 —
# 노출이 커져도 밴드가 상대적으로 촘촘해지지 않는다. 그리고 밴드 폭을 그 시장의
# 왕복 비용에 비례시킨다: 비싼 시장일수록 더 많이 벗어나야 고쳐 잡는다.
# 한국주식(실측 왕복 ~93bp)은 약 28%, 코인·미국주식은 하한 15%가 적용된다.
# K는 정밀 최적화가 아니라 '한국주식이 저비용 시장의 약 2배 밴드를 갖는다'는
# 기준으로 잡은 휴리스틱이다(정확한 최적 밴드는 비용^(1/3)에 비례한다는
# 이론이 있으나, 표본이 쌓이기 전의 정밀 조정은 과적합이다).
# 실행 구조 세대 — '얼마를 어떻게 사고파는가'가 바뀌면 통계의 시계도 리셋된다.
#
# 판정 시계는 원래 피처셋만 세대로 쳤다. 그런데 2026-08-11에 사이징(총노출
# 6.8%→100%)과 회전율 통제를 크게 바꿨고, 피처는 그대로여서 시계가 돌지 않았다.
# 노출이 15배 다른 두 구간의 수익률은 같은 통계가 아니다 — 원칙의 구멍이었다.
# 실행 구조를 바꿀 때는 EPOCH를 그날로, TAG를 다음 번호로 올린다.
STRUCTURE_TAG = "krw1"
STRUCTURE_EPOCH = "2026-08-13"
STRUCTURE_WHY = ("계좌 통화를 원화로 통일(감사 212) — 그전에는 해외 종목"
                 " 가격을 환산하지 않아 한 계좌에 원화(한국주식)와 달러"
                 "(미국주식·코인)가 섞여 있었다. 자산 합계가 진짜 원화가"
                 " 아니었고 환위험이 통째로 빠져 있었다. 이제 체결·평가를"
                 " 원/달러로 환산해, 환율 변동이 매일의 재평가로 자산에"
                 " 반영된다. 신호는 현지 통화 그대로라 전략 동작은 그대로."
                 " 옛 계좌는 소급 환산이 불가능해(현금까지 단위가 섞였다)"
                 " 그대로 보관하고 원화 계좌를 새로 열었다."
                 " 직전 구조(sz2): 포트폴리오 변동성 타깃 + 회전율 통제"
                 " + 안전장치 복구")

# 신호 평활 계수 — 오늘 목표에 얼마나 무게를 둘 것인가(1.0=평활 없음).
# 0.5는 2일 지수평활 — 확률의 하루짜리 떨림은 절반으로 줄이되, 진짜 추세
# 전환은 이틀이면 대부분 반영된다. 청산 신호에는 적용하지 않는다.
SIGNAL_SMOOTH_ALPHA = 0.3
# 종목별 재조정 쿨다운(거래일) — "매일 판단하되 자주 고쳐 잡지는 않는다".
#
# 밴드와 평활만으로는 부족했다(실측 회전율 70%→40%, 연 비용 40% vs 기대수익
# 8.8%). 시뮬레이션상 주 1회 수준으로 재조정 빈도를 낮추면 연 비용이 7.9%로
# 떨어져 비로소 기대수익 아래로 내려온다. 판단(예측·기록)은 매일 그대로 하고,
# 포지션을 고쳐 잡는 행위만 뜸하게 한다 — 신호는 매일 검증되고 비용만 준다.
#
# 예외 두 가지는 쿨다운을 무시한다:
#   ① 청산(목표 0) — 나가는 길은 언제나 열려 있어야 한다
#   ② 큰 이탈(목표의 COOLDOWN_OVERRIDE_DRIFT 배 초과) — 시장이 크게 변했는데
#      달력을 이유로 방치하는 것은 규율이 아니라 태만이다
#
# ⚠️ 정직하게: 이 파라미터들의 효과는 **아직 검증되지 않았다**. 기록이 5일뿐
#    이라 시뮬레이션의 회전율 바닥이 33%(첫 거래)로 깔려서, 쿨다운이 실제로
#    얼마나 묶는지 측정할 수 없다. 그래서 값은 '표준적이고 방어 가능한 수준'
#    으로 두고, 진짜 검증은 매일 기록되는 turnover와 아래 경보에 맡긴다.
TRADE_COOLDOWN_DAYS = 5
# 쿨다운을 무시할 '큰 이탈'의 기준 — 목표 대비 드리프트 비율.
# 처음에는 밴드의 배수로 뒀는데, 밴드가 시장별로 다르다 보니 같은 크기의
# 변화가 시장에 따라 예외가 되기도 안 되기도 했다(코인 45%, 한국 84%).
# 목표의 100%(포지션이 두 배가 되거나 반토막)라는 단일 기준으로 통일한다.
COOLDOWN_OVERRIDE_DRIFT = 1.0
REBALANCE_BAND_REL_K = 30.0
REBALANCE_BAND_REL_MIN = 0.15
REBALANCE_BAND_REL_MAX = 0.40


# 실측 비용으로 갈아타는 최소 표본 — 코드가 행동을 바꾸는 그 숫자다.
# ⚠️ 경보 문구는 "표본 30건 이상 유지 시 검토"라고 말하는데 코드는 10건에서
#    이미 갈아타고 있었다(감사 66). 사장님은 아직 아무 일도 안 일어났다고
#    믿는 동안 오디션의 비용 모델이 조용히 바뀐다 — 말과 행동이 다른
#    자리라, 두 곳이 같은 상수를 읽게 한다.
MEASURED_COST_MIN_SAMPLES = 10


def _measured_roundtrip_cost(market: str, state_dir: str) -> float | None:
    """페이퍼 장부에서 실측한 **왕복** 체결 마찰(비율) — 없으면 None.

    가정(CostModel)은 한국주식 편도 14bp(왕복 28bp)라고 말하지만, 실측
    개장 갭은 그보다 훨씬 컸다(불리 갭 평균 99bp/편도). 밴드를 가정이 아니라
    **실측**에 연결하면, 체결이 실제로 비싼 시장에서 자동으로 덜 매매하게
    된다 — 측정이 관찰로 끝나지 않고 행동으로 이어지는 고리다. 표본이 얇으면
    가정으로 돌아간다.

    ⚠️ 단위(2026-08-11 감사에서 잡은 버그): fill_gap_report의 assumed_bp와
    mean_adverse_bp는 **둘 다 편도**다. 예전 구현은 그 편도 합을 '왕복'이라
    부르고 호출부가 다시 2로 나눠, 실제 마찰을 절반으로 축소해 쓰고 있었다.
    """
    try:
        from quant.reporting.fill_gap import fill_gap_report
        rep = fill_gap_report(state_dir)
        row = ((rep or {}).get("markets") or {}).get(market)
        if not row or row.get("n", 0) < MEASURED_COST_MIN_SAMPLES:
            return None                        # 표본 부족 — 가정을 쓴다
        # 편도 = 가정 수수료 + 실측 불리 갭(음수면 유리했다는 뜻 → 0으로 바닥)
        one_way_bp = row["assumed_bp"] + max(0.0, row["mean_adverse_bp"])
        return 2.0 * one_way_bp / 1e4          # 왕복
    except Exception:  # noqa: BLE001 — 실측 실패는 가정으로 폴백
        return None


def measured_cost_model(market: str, state_dir: str = STATE_DIR,
                        models_gap: bool = True):
    """오디션이 물어야 할 체결 비용 모델.

    ⚠️ 이중 계상 주의(2026-08-11 감사에서 제가 만든 결함을 되잡은 것):
    개장 갭을 반영하는 방법은 두 가지이고, **동시에 쓰면 두 번 물린다.**
        (a) 가격으로: 백테스트가 다음 봉 '시가'에 체결(next_open_fill)
        (b) 비용으로: 실측 불리 갭을 슬리피지에 더한다
    (b)는 (a)가 없던 시절의 대체물이었다. 지금 오디션은 갭이 존재하는 시장
    (한국·미국 주식)에서 항상 (a)를 쓰므로, 거기에 (b)까지 더하면 한국주식
    기준 갭을 두 번 — 실제보다 2배 비싸게 — 물게 된다. 그러면 이번엔 반대
    방향으로 고회전 전략이 부당하게 불리해진다.

    (a)를 남기는 이유: 평균 한 숫자가 아니라 **갭의 분포 전체**를 그대로
    겪는다. 평균으로 눌러 담는 것보다 충실하다.

    models_gap=False(백테스트가 종가 체결로 갭을 모델링하지 않을 때)일 때만
    실측 갭을 비용으로 얹는다. 표본이 얇으면 가정 그대로 — 소표본으로 선발
    기준을 흔드는 것이 더 위험하다.
    """
    from quant.backtest.costs import CostModel
    base = CostModel.for_market(market)
    if models_gap:
        return base                             # 갭은 이미 가격에 있다
    measured = _measured_roundtrip_cost(market, state_dir)
    if measured is None:
        return base
    one_way = max(0.0, measured / 2.0)          # 왕복 → 편도
    assumed_one_way = float(base.fee + base.slippage)
    if one_way <= assumed_one_way:
        return base                             # 실측이 더 싸면 가정 유지(보수적)
    # 초과분은 슬리피지로 붙인다 — 수수료는 계약이고 갭은 체결 미끄러짐이다
    return CostModel(fee=base.fee,
                     slippage=base.slippage + (one_way - assumed_one_way),
                     impact_coef=base.impact_coef,
                     short_borrow=base.short_borrow, funding=base.funding,
                     market_impact_coef=base.market_impact_coef,
                     participation_cap=base.participation_cap)


def rebalance_band_basis(market: str, state_dir: str = STATE_DIR) -> dict:
    """밴드와 **그 밴드가 나온 근거**를 함께 돌려준다.

    ⚠️ 왜 근거까지 남기나(2026-08-11 감사 74): 이 밴드는 표본이 문턱
    (MEASURED_COST_MIN_SAMPLES)을 넘는 순간 가정에서 실측으로 갈아탄다.
    한국주식은 그 전환에서 **0.150 → 0.400(2.67배)** 로 뛴다 — 하한 클립에서
    곧장 상한 클립까지다. 즉 어느 날 아침 갑자기 회전율이 크게 줄어드는데,
    예전에는 이 값이 계산되어 쓰이고 **아무 데도 기록되지 않았다.** 사장님이
    보시기엔 이유 없이 매매가 멎은 날이 된다.

    설계 자체는 옳다(비싼 시장에서 덜 매매한다). 고칠 것은 **말없이
    바뀐다**는 점이므로, 로직이 아니라 흔적을 추가한다 — 오늘 내내 나온
    "판단한 쪽이 결과를 남기고, 보여주는 쪽은 읽기만 한다"와 같은 처방이다.
    """
    measured = _measured_roundtrip_cost(market, state_dir)
    cost = measured if measured is not None else 2.0 * _fill_cost(market)
    band = max(REBALANCE_BAND_REL_MIN,
               min(REBALANCE_BAND_REL_MAX, REBALANCE_BAND_REL_K * cost))
    n = 0
    try:
        from quant.reporting.fill_gap import fill_gap_report
        row = (((fill_gap_report(state_dir) or {}).get("markets") or {})
               .get(market)) or {}
        n = int(row.get("n", 0) or 0)
    except Exception:  # noqa: BLE001 — 근거 표시 실패가 매매를 막으면 안 된다
        pass
    return {"band": round(band, 4),
            "source": "실측" if measured is not None else "가정",
            "roundtrip_bp": round(cost * 1e4, 1),
            "n": n, "min_samples": MEASURED_COST_MIN_SAMPLES,
            "clipped": ("하한" if band <= REBALANCE_BAND_REL_MIN
                        else "상한" if band >= REBALANCE_BAND_REL_MAX else None)}


def _rebalance_band_rel(market: str, state_dir: str = STATE_DIR) -> float:
    """시장별 상대 리밸런스 밴드 — 왕복 비용에 비례(하한·상한 클립).

    비용은 실측이 있으면 실측, 없으면 CostModel 가정을 쓴다.
    """
    return rebalance_band_basis(market, state_dir)["band"]


# 최소 주문금액(원) — 이보다 작은 매매는 비용만 남기므로 주문하지 않는다.
# 한국주식 실측 왕복 비용(가정 14bp + 개장 갭 79bp ≈ 93bp) 기준, 500원
# 주문의 기대 비용은 약 4.7원이다. 청산 주문에는 적용하지 않는다.
MIN_ORDER_KRW = 500.0



def random_strategy_percentile(history: list[dict], actual_twr_pct: float,
                               n: int = 1000, seed: str = "rand",
                               cost: float = 0.002) -> float | None:
    """무작위 '순열' 전략 n개의 수익률 분포에서 실제 TWR의 백분위(%)를 잰다.

    조건을 맞춘 무작위(순열 검정): 각 무작위 전략은 실제 기록의 일별 비중
    수열을 그대로 가져다 '순서만' 무작위로 섞어, 같은 지수(record.price) 위에서
    같은 비용을 내며 거래한 것이다. 매매 빈도·포지션 크기 분포가 실제와
    동일하므로, 백분위가 재는 것은 오직 '타이밍 실력'뿐이다 — 조건 없는
    동전 던지기와 비교하면 빈도 차이가 실력처럼 보이는 왜곡이 생긴다.
    반환 75.0 = "무작위 1,000개 중 상위 25%". 기록 2일 미만이면 None.
    시드가 날짜 기반이라 같은 날 재실행 시 같은 값(재현 가능).
    비중이 늘 일정했던 구간에서는 순열이 전부 같아져 백분위가 낮게(우위
    없음으로) 나온다 — 타이밍을 쓰지 않았으니 그것이 정직한 값이다.
    """
    import random as _random

    px, ws = [], []
    for r in history:
        if isinstance(r.get("price"), (int, float)):
            px.append(float(r["price"]))
            w = r.get("weight")
            ws.append(float(w) if isinstance(w, (int, float)) else 0.0)
    if len(px) < 3:
        return None
    rets = [px[i] / px[i - 1] - 1 for i in range(1, len(px))]
    base = ws[:-1]                    # t일 비중이 t→t+1 수익률에 노출된다
    rng = _random.Random(seed)
    finals = []
    for _ in range(n):
        perm = base[:]
        rng.shuffle(perm)
        eq, prev_w = 1.0, 0.0
        for w, r in zip(perm, rets):
            eq *= 1 + w * r
            eq -= eq * cost * abs(w - prev_w)      # 비중 변화분만 비용 지불
            prev_w = w
        finals.append(eq - 1.0)
    actual = actual_twr_pct / 100.0
    beaten = sum(1 for f in finals if f < actual)
    return round(beaten / n * 100, 1)


def _generation_info(state_dir: str) -> dict | None:
    """현재 구조 세대의 관찰 일수 — 90일 시계를 숨기지 않는다.

    구조(피처·모델·사이징)가 바뀔 때마다 성과 통계의 시계는 사실상 0으로
    리셋된다. 이 사실을 사이트에 명시해, 과거 세대의 기록이 현재 구조의
    실적처럼 읽히는 착시를 막는다.

    세대는 두 축으로 결정된다:
      ① 피처셋(FEATURE_SET) — 무엇을 보고 판단하는가
      ② 실행 구조(STRUCTURE_TAG/EPOCH) — 얼마를 어떻게 사고파는가
    ②를 뒤늦게 넣은 이유: 2026-08-11에 사이징(총노출 6.8%→100%)과 회전율
    통제를 크게 바꿨는데, 피처는 그대로라 시계가 리셋되지 않았다. 그러나
    노출이 15배 다른 두 구간의 수익률은 같은 통계가 아니다 — 피처만 세대로
    치는 것은 우리가 세운 원칙의 구멍이었다.

    since = ①이 처음 등장한 날과 ②의 마지막 변경일 중 **나중** 날짜.
    """
    try:
        import datetime as _dt
        from quant.strategies.ml import FEATURE_SET
        path = os.path.join(state_dir, "retrain_history.jsonl")
        since = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    if r.get("feature_set") == FEATURE_SET:
                        a = str(r.get("asof", ""))[:10]
                        if len(a) == 10 and (since is None or a < since):
                            since = a
        today = _dt.date.today()
        if since is None:
            since = today.isoformat()
        # 실행 구조가 더 최근에 바뀌었으면 그날부터 다시 센다
        if STRUCTURE_EPOCH > since:
            since = STRUCTURE_EPOCH
        days = (today - _dt.date.fromisoformat(since)).days
        return {"feature_set": f"{FEATURE_SET}/{STRUCTURE_TAG}",
                "since": since, "days": max(0, days), "target_days": 90,
                "structure": {"tag": STRUCTURE_TAG, "epoch": STRUCTURE_EPOCH,
                              "why": STRUCTURE_WHY}}
    except Exception:  # noqa: BLE001 — 표시 재료일 뿐
        return None


def _generation_archive(state: dict, since: str) -> dict | None:
    """통합 계좌 기록을 '이전 구조 / 현재 구조'로 갈라 각각의 TWR을 낸다.

    판정 시계의 짝: 세대 시작일(since) 이전 기록은 다른 구조의 실적이다.
    합산 수익률 하나로 보여주면 이전 세대의 성과가 현 구조의 실적처럼
    읽힌다 — 구간별 일수·TWR을 분리해 그 착시를 마저 없앤다.
    입금(매칭)은 날짜로 해당 구간에 귀속시켜 TWR 왜곡을 막는다.
    """
    try:
        hist = chrono(state.get("history") or [])   # 구간 분할도 시간순 전제
        if not hist:
            return None
        i0 = next((i for i, r in enumerate(hist)
                   if str(r.get("date", "")) >= since), len(hist))
        prev_hist, cur_hist = hist[:i0], hist[i0:]
        if not prev_hist:
            return None                    # 전 기록이 현 세대 — 분리할 게 없다
        deposits = state.get("deposits") or []
        sc = float(state.get("start_cash", PORTFOLIO_START_CASH))
        prev_dep = [d for d in deposits if str(d.get("date", "")) < since]
        cur_dep = [d for d in deposits if str(d.get("date", "")) >= since]
        cur_start = float(prev_hist[-1].get("equity") or sc)
        out = {
            "prev_days": len(prev_hist),
            "prev_twr_pct": time_weighted_return(prev_hist, prev_dep,
                                                 start_cash=sc),
            "cur_days": len(cur_hist),
            "cur_twr_pct": (time_weighted_return(cur_hist, cur_dep,
                                                 start_cash=cur_start)
                            if cur_hist else 0.0),
        }
        return out
    except Exception:  # noqa: BLE001 — 표시 재료일 뿐
        return None


def _kelly_cap_from_history(history: list, fraction: float = 0.5,
                            floor: float = 0.25, min_days: int = 30) -> float:
    """페이퍼 장부(OOS)의 보유일 수익 통계로 부분 켈리 '상한'을 만든다.

    보유일(그날 비중≠0)의 다음날 자산 수익으로 승률·평균손익을 추정해
    ½켈리를 계산하고 [floor, 1.0]로 클립한다. 표본 min_days 미만이면
    1.0(비개입) — 잡음 통계 위의 켈리는 수학의 탈을 쓴 도박이다.
    인샘플 백테스트가 아니라 실제 페이퍼 기록이라 켈리의 전제(OOS)에 맞다.
    엣지 추정이 음수여도 floor 밑으로는 안 내린다 — '걸지 마라'의 판정은
    켈리가 아니라 오디션·킬스위치의 몫이다(역할 분리).
    """
    try:
        rets = []
        for a, b in zip(history, history[1:]):
            if abs(float(a.get("weight") or 0.0)) > 0:
                ea = float(a.get("equity") or 0.0)
                eb = float(b.get("equity") or 0.0)
                if ea > 0 and eb > 0:
                    rets.append(eb / ea - 1.0)
        if len(rets) < min_days:
            return 1.0
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r < 0]
        if not wins or not losses:
            return 1.0
        from quant.risk import kelly_fraction
        k = kelly_fraction(len(wins) / len(rets),
                           sum(wins) / len(wins), sum(losses) / len(losses))
        return float(max(floor, min(1.0, fraction * k)))
    except Exception:  # noqa: BLE001 — 상한 계산 실패 = 비개입(1.0)
        return 1.0


def _regime_breakdown(history: list, window: int = 20) -> dict | None:
    """레짐별 성과 분해 — 챔피언이 '어떤 장'에서 벌고 잃었는지의 정직한 답.

    레짐 정의: 장부의 균등가중 지수(price)가 최근 window일 이동평균 위(상승
    국면)/아래(하락 국면). 각 국면에서의 우리 일별 수익을 복리로 합산한다.
    상승장에서만 벌었다면 그건 시장 베타지 엣지가 아닐 수 있다 — 그 구분을
    데이터로 보여주는 게 목적이다. 표본 부족(window+5일 미만)이면 None.
    """
    try:
        rows = [(str(r.get("date")), float(r.get("price") or 0),
                 float(r.get("equity") or 0)) for r in chrono(history)
                if r.get("price") and r.get("equity")]
        if len(rows) < window + 5:
            return None
        out = {"up": {"days": 0, "ret_pct": 1.0},
               "down": {"days": 0, "ret_pct": 1.0}}
        prices = [p for _, p, _ in rows]
        for i in range(window, len(rows)):
            ma = sum(prices[i - window:i]) / window
            regime = "up" if prices[i] >= ma else "down"
            prev_eq, eq = rows[i - 1][2], rows[i][2]
            if prev_eq > 0:
                out[regime]["days"] += 1
                out[regime]["ret_pct"] *= eq / prev_eq
        for v in out.values():
            v["ret_pct"] = round((v["ret_pct"] - 1) * 100, 2)
        out["window"] = window
        return out
    except Exception:  # noqa: BLE001 — 표시 재료일 뿐(실패가 기록을 막으면 안 된다)
        return None


# 시장별 '1차 소스' — 이 이름이 아니면 폴백으로 받은 것이다(감사 135).
# 주식은 yfinance(auto_adjust=조정가)가 1차이고, 보조 소스(yahoo-http·stooq)는
# 무조정가라 배당·액면분할 날 수익률에 가짜 점프가 생긴다.
# 코인은 거래소 id가 그대로 소스명이라 '1차/보조' 구분이 없다.
PRIMARY_SOURCE = {"us_stock": "yfinance", "kr_stock": "yfinance"}


def _source_fallbacks(sources: dict) -> dict:
    """1차 소스가 아닌 종목만 추린다 — {키: 실제로 쓴 소스}."""
    out = {}
    for key, name in sources.items():
        want = PRIMARY_SOURCE.get(key.split(":")[0])
        if want and name != want:
            out[key] = name
    return out


def _hrp_slices(rets_map: dict, n_total: int) -> dict | None:
    """HRP(계층적 리스크 패리티) 슬라이스 — ERC의 상위 호환(추정 오차에 강함).

    데이터 준비 규약은 ERC와 동일(40일 이상 공통 표본, 2종목 이상). 가용
    종목들의 총 예산(k/n_total)을 HRP 비율로 나누고 과집중 상한(3/n_total)을
    적용한다. 퇴화 시 None — 호출자는 ERC → 균등 순으로 폴백한다.
    """
    import pandas as pd
    try:
        cols = {}
        for key, s in rets_map.items():
            s = s.dropna()
            if len(s) >= 40:
                s.index = pd.DatetimeIndex(s.index).normalize()
                cols[key] = s[~s.index.duplicated()]
        if len(cols) < 2:
            return None
        R = pd.DataFrame(cols).dropna()
        if len(R) < 40:
            return None
        from quant.live.hrp import hrp_weights
        w = hrp_weights(R)
        if not w:
            return None
        budget = len(R.columns) / n_total
        cap = 3.0 / n_total
        return {c: min(float(budget * wi), cap) for c, wi in w.items()}
    except Exception:  # noqa: BLE001
        return None


def _erc_slices(rets_map: dict, n_total: int) -> dict | None:
    """공분산 기반 위험기여도 균등(ERC) 슬라이스 — 자본 균등(1/n)의 상위 호환.

    비트코인 만원과 은행주 만원은 위험 기여가 5~10배 다르다 — 종목별 변동성만
    보는 것도 부족하다(위험자산은 같이 움직인다). 최근 90일 수익률의 공분산에서
    각 종목의 위험 기여가 같아지는 비중을 반복법으로 구해, 가용 종목들의 총
    예산(k/n_total)을 그 비율로 나눈다. 슬라이스 상한 3/n_total(집중 방지).
    표본이 부족하거나 계산이 퇴화하면 None — 호출자는 균등 배분으로 폴백한다.
    """
    import pandas as pd
    try:
        cols = {}
        for key, s in rets_map.items():
            s = s.dropna()
            if len(s) >= 40:
                s.index = pd.DatetimeIndex(s.index).normalize()
                cols[key] = s[~s.index.duplicated()]
        if len(cols) < 2:
            return None
        R = pd.DataFrame(cols).dropna()
        if len(R) < 40:
            return None
        # 퇴화 열(거래정지·고정 시세)을 뺀다(감사 149). 반복법은 위험 기여를
        # 균등화하는데, 분산이 1e-38인 열은 기여가 사실상 0이라 반복이
        # 그 열의 비중을 무한히 키운다 — 실측으로 상한(3/n)을 꽉 채웠다.
        # ⚠️ 키를 지우면 안 된다. 호출 쪽이 `slices.get(key, 1.0/n)`이라
        #    빠진 키는 오히려 **기본 슬라이스**를 받는다. 0.0으로 남긴다.
        from quant.utils.numerics import REL_EPS
        _v = R.var()
        _keep = [c for c in R.columns
                 if np.isfinite(_v[c]) and _v[c] > REL_EPS * float(_v.max())]
        _dropped = [c for c in R.columns if c not in _keep]
        if len(_keep) < 2:
            return None
        R = R[_keep]
        cov = R.cov().values
        k = len(R.columns)
        w = np.ones(k) / k
        for _ in range(300):
            rc = w * (cov @ w)                 # 위험 기여
            if not np.isfinite(rc).all() or rc.sum() <= 0:
                return None
            w = w * np.sqrt(rc.mean() / np.maximum(rc, 1e-16))
            w = np.clip(w, 1e-6, None)
            w = w / w.sum()
        budget = len(R.columns) / n_total      # 가용 종목 수만큼의 자본 예산
        raw = {c: float(budget * wi) for c, wi in zip(R.columns, w)}
        cap = 3.0 / n_total                    # 한 종목 과집중 방지
        capped = {c: min(v, cap) for c, v in raw.items()}
        capped.update({c: 0.0 for c in _dropped})   # 퇴화 열은 명시적 0
        return capped
    except Exception:  # noqa: BLE001 — 배분 실패가 매매를 막으면 안 된다(균등 폴백)
        return None


def _xsec_tilt(weights: dict, lo: float = 0.75, hi: float = 1.25) -> dict:
    """횡단면 확신도 틸트 — 같은 위험예산 안에서 고확신 종목으로 자본을 기울인다.

    지금까지 배분(ERC)은 '위험'만 보고 종목을 나눴다 — 챔피언이 A는 확신
    100%, B는 확신 60%라고 말해도 두 종목의 자본 예산은 같았다. 이 틸트는
    각 챔피언의 |목표비중|(확신도)을 종목 간 '순위'로 바꿔 [lo, hi] 배수로
    매핑한다(꼴찌 lo배, 1등 hi배). 순위를 쓰는 이유: 종목마다 전략·보정이
    달라 확신도의 절대값은 비교 불가능하지만 순서는 비교 가능하다.
    동률은 평균 순위 — 유니버스 나열 순서가 배분을 좌우하면 안 된다.
    활성(|w|>0) 종목이 2개 미만이면 순위가 무의미하므로 전부 1.0.
    ⚠️ 이것은 '검증된 알파'가 아니라 배분 규칙이다. 배수는 호출자가 총예산
    보존으로 재정규화하며, 그날의 배수가 장부(xsec_tilt)에 남아 사후 검증
    가능하다. 확신도가 무정보라면 장기적으로 균등 배분과 다르지 않다.
    """
    active = {k: abs(float(w)) for k, w in weights.items() if abs(float(w)) > 0}
    if len(active) < 2:
        return {k: 1.0 for k in weights}
    order = sorted(active, key=lambda k: (active[k], k))   # 결정적 정렬
    n = len(order)
    # 동률 그룹에 평균 순위 부여
    rank: dict = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and active[order[j + 1]] == active[order[i]]:
            j += 1
        mean_rank = (i + j) / 2.0
        for kk in order[i:j + 1]:
            rank[kk] = mean_rank
        i = j + 1
    out = {}
    for k in weights:
        if k in rank:
            out[k] = lo + (hi - lo) * rank[k] / (n - 1)
        else:
            out[k] = 1.0                       # 관망 종목은 틸트 무의미(비중 0)
    return out


def _in_cooldown(key: str, last_trade: dict, today: str, target_w: float,
                 held_w: float, band: float = 0.0) -> bool:
    """이 종목을 오늘 고쳐 잡지 않고 넘길 것인가 — 쿨다운 판정.

    청산과 큰 이탈은 쿨다운을 무시한다. 그 외에는 마지막 조정 후
    TRADE_COOLDOWN_DAYS 거래일이 지나야 다시 손댄다.
    (band 인자는 하위 호환용 — 이제 예외 기준은 시장과 무관한 단일 값이다.)
    """
    if abs(target_w) < 1e-9:
        return False                            # 청산은 언제나 허용
    if abs(target_w - held_w) >= COOLDOWN_OVERRIDE_DRIFT * abs(target_w):
        return False                            # 큰 이탈은 즉시 대응
    last = last_trade.get(key)
    if not last:
        return False                            # 첫 진입
    try:
        import datetime as _dt
        d0 = _dt.date.fromisoformat(str(last)[:10])
        d1 = _dt.date.fromisoformat(str(today)[:10])
        # 거래일 근사: 달력일 × 5/7 (주말 제외). 정밀 달력이 필요한 판단이 아니다.
        return (d1 - d0).days * 5.0 / 7.0 < TRADE_COOLDOWN_DAYS
    except (ValueError, TypeError):
        return False


def _smooth_weights(new: dict, prev: dict, alpha: float = SIGNAL_SMOOTH_ALPHA
                    ) -> dict:
    """목표 비중을 어제 목표와 지수평활한다 — 마음이 덜 바뀌게.

    확률이 임계값 근처(0.55↔0.62)에서 떠는 것만으로 전 종목이 매매되는 것이
    회전율의 큰 원인이었다. 평활은 그 떨림을 걸러낸다. 다만 **관망(0)으로의
    전환은 평활하지 않는다** — "팔아라"는 신호를 반만 듣는 것은 위험 관리가
    아니라 미련이다. 새로 진입(0→양수)할 때만 서서히 들어간다.
    """
    out = {}
    for k, w in new.items():
        p = float(prev.get(k, 0.0) or 0.0)
        if abs(w) < 1e-9:
            out[k] = 0.0                    # 청산 신호는 즉시 반영
        else:
            out[k] = alpha * float(w) + (1.0 - alpha) * p
    return out


def required_bars(spec: dict, floor: int = 30) -> int:
    """이 챔피언이 신호를 내려면 최소 몇 봉이 필요한가 (감사 201).

    전략 파라미터에서 가장 긴 창(`slow=30`, `train_window=250` 등)을 찾아
    **그만큼**을 요구한다. 파라미터가 없거나 다 짧으면 floor를 쓴다.

    ⚠️ 처음에는 **그 두 배**를 요구했다가 과했다. 기본 챔피언의
    `train_window=250`이 500봉 요구가 되어, 300봉을 주는 정상 픽스처까지
    전부 '표본 부족'으로 막혔다(검사 5건이 빨개져서 알았다). 파라미터는
    전부 '창 길이'가 아니다 — 학습 구간·재학습 주기처럼 배수를 곱하면
    뜻이 달라지는 값이 섞여 있다. **선언한 가장 긴 창이 한 번 채워지는
    것**까지가 근거 있는 요구고, 그 이상은 내 추측이다.

    ⚠️ 왜 필요한가. 예전에는 `df.empty`만 봤다. 그래서 보조 거래소가 10봉만
    주는 날, 그 종목은 신호가 0으로 나오는데 **장부에는 아무 흔적도 없었다**:

        B0가 400봉일 때 → 장부 "3종목 분산" · 실제 포지션 3개
        B0가  10봉일 때 → 장부 "3종목 분산" · 실제 포지션 **2개**  ← 거짓말

    감사 59에서 "데이터 실패로 빠진 종목을 계획 수로 세지 말 것"을 고쳤는데,
    그건 **예외가 난 종목**만 잡는다. 데이터는 멀쩡히 왔는데 **표본이 모자란**
    종목은 그 그물에 안 걸린다 — 같은 거짓말의 다른 문이다(감사 200에서
    배운 것과 같은 형태: 무엇을 막는다고 적었으면 그 무엇이 지나는 문을
    전부 셀 것).

    그리고 이건 이 저장소가 가장 신경 쓰는 **오디션-현실 격차**이기도 하다.
    챔피언은 400봉으로 선발했는데 실전에서 10봉으로 굴리면, 선발된 조건과
    굴리는 조건이 다르다(감사 71과 같은 계열).
    """
    longest = 0
    for v in (spec.get("params") or {}).values():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            longest = max(longest, int(abs(v)))
    return max(floor, longest)


def _signal_frame(market: str, df, timeframe: str = "1d"):
    """신호·피처 계산에 쓸 프레임 — 아직 만들어지는 중인 봉은 뺀다.

    주식 제공자에는 _drop_unclosed가 있어 이미 완성 봉만 온다. 코인은
    24시간 시장이라 UTC 일봉의 '오늘' 봉이 항상 진행 중이므로 여기서 뺀다.
    뺄 봉이 없거나 뺐을 때 표본이 남지 않으면 원본을 그대로 돌려준다.

    체결 가격은 이 프레임이 아니라 원본의 마지막 종가(=현재가)를 쓴다 —
    "완성된 정보로 판단하고, 지금 가격에 체결한다".

    ⚠️ **타임프레임을 받는다**(감사 204). 예전에는 `bar_status(market, 봉)`만
    불러 **항상 일봉 자로 쟀다.** 같은 파일의 다른 두 자리(장부의
    `bar_partial`, 기록용 `bs`)는 진짜 타임프레임을 넘기고 있었는데 여기만
    빠져 있었다 — 같은 판정을 세 곳에서 부르면서 하나가 갈라진 것이다(㉞).

    실측(봇이 1시간봉으로 돌 때, 3시간 전에 **완성된** 봉):

        1h 자로 재면  → 1.0   (완성)
        1d 자로 재면  → 0.125 (진행 중)  ← 멀쩡한 완성 봉이 버려진다

    지금 운영은 일봉이라 새는 곳은 아니지만, `--timeframe`을 바꾸는 순간
    조용히 틀린다. 기본값을 `"1d"`로 둬 옛 호출부는 그대로 동작한다.
    """
    from quant.data.barclock import bar_status
    if len(df) < 2 or bar_status(market, df.index[-1], timeframe) is None:
        return df
    return df.iloc[:-1]


def _is_dust_order(broker, key: str, target_w: float, price, equity: float,
                   floor_krw: float = None) -> bool:
    """이 주문이 '잔돈'인가 — 목표와 현 보유의 차액이 최소 금액에 못 미치는가.

    소액 계좌에서 20종목에 1/n로 나누면 종목당 목표가 수십 원까지 내려간다.
    한국주식 실측 왕복 비용(가정 14bp + 개장 갭 79bp ≈ 93bp)을 생각하면
    그런 주문은 기대수익보다 비용이 크고, 체결 표본까지 오염시킨다.
    이미 보유 중인 종목의 청산(목표 0)은 잔돈이어도 막지 않는다 —
    빠져나오는 길을 막으면 리스크 관리가 아니라 덫이 된다.

    ⚠️ 보유 조회가 실패하면 '없음(0)'으로 치지 않는다(감사 53). 목표가 0인
       청산 상황에서 보유를 0으로 오인하면 delta도 0이 되어 **잔돈으로
       분류되고 청산 주문이 통째로 생략된다** — 위 문단이 약속한 '빠져나오는
       길'이 조회 실패 한 번에 막힌다. 모를 때는 잔돈이 아니라고 본다.
    """
    if price is None or equity <= 0:
        return False
    floor = MIN_ORDER_KRW if floor_krw is None else floor_krw
    try:
        pos = broker.get_position(key)
        cur_qty = float(getattr(pos, "quantity", 0.0) or 0.0)
    except Exception:  # noqa: BLE001 — 모르면 막지 않는다(청산 봉쇄 방지)
        return False
    cur_notional = cur_qty * float(price)
    if abs(target_w) < 1e-9 and abs(cur_notional) > 0:
        return False                       # 청산은 언제나 허용
    delta = abs(target_w * equity - cur_notional)
    return delta < floor


def _kill_switch_scale(prev: float, dd: float) -> float:
    """자동 킬스위치 — 낙폭 단계별 노출 축소와 '단계적' 복귀(히스테리시스).

    낙폭 -25% 이하: 전량 관망(0) · -15% 이하: 노출 절반(0.5).
    복귀는 한 번에 안 한다: 0 → (낙폭 -15% 안쪽 회복) 0.5 → (-10% 안쪽) 1.0.
    성과가 무너질 때 스스로 물러나는 규칙이 있다는 것 자체가
    '실전에 쓸 수 있는 시스템'의 증명이다.
    """
    if dd <= -0.25:
        return 0.0
    if dd <= -0.15:
        return 0.5 if prev > 0.0 else 0.0
    if dd <= -0.10:
        return max(0.5, prev) if prev >= 0.5 else 0.5
    return 1.0


def run_daily_portfolio(targets=None, *, timeframe: str = "1d",
                        lookback: int = 400, state_dir: str = STATE_DIR,
                        require_real_data: bool = True,
                        use_champions: bool = True,
                        state_file: str = "portfolio_ALL.json") -> dict:
    """통합 8마일 계좌(8만원) — 전 종목에 분산해 한 계좌로 운용한다(실전과 가장 유사).

    각 종목의 챔피언 전략 비중을 종목 수로 나눠(자본 균등 슬라이스) 한
    PaperBroker 계좌에 담는다. 실데이터를 못 받은 종목은 그날 매매하지 않고
    기존 포지션을 유지한다(가짜 데이터로 매매 금지). 멱등: 같은 봉 재실행 무시.
    사이트 벤치마크('그냥 보유')를 위해 균등가중 지수(첫 관측일=100)를 가격으로
    기록한다.
    """
    from quant.broker import PaperBroker
    from quant.broker.base import Position
    from quant.data import get_provider
    from quant.utils.jsonio import atomic_write_json, cap_history

    from quant.markets import AUTO_TARGETS
    targets = targets or AUTO_TARGETS

    path = os.path.join(state_dir, "paper", state_file)
    mkt_tag = "portfolio" if use_champions else "portfolio_shadow"
    sym_tag = "ALL" if use_champions else "SHADOW"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    else:
        st = {"market": mkt_tag, "symbol": sym_tag, "currency": "KRW",
              "start_cash": PORTFOLIO_START_CASH,
              "cash": PORTFOLIO_START_CASH, "positions": {}, "base_prices": {},
              "last_bar": None, "history": []}

    # ⚠️ **단위가 섞인 장부 위에서 돌면 안 된다**(감사 215).
    #
    # 감사 212에서 체결·평가를 원화로 환산하게 고쳤는데, 그 전에 쌓인 장부는
    # 보유 단가가 달러다. 그 위에서 이 함수를 돌리면 같은 수량이 원화
    # 가격으로 재평가되어 **자산이 1,470배로 뛴다** — 그리고 그 폭등이
    # 수익으로 기록된다.
    #
    # 실제로 통합 계좌만 다시 열고 **섀도 대조군을 빠뜨렸다.** 섀도는
    # "오디션이 가치를 더하는가"를 증명하는 유일한 대조군인데, 그쪽만
    # 폭등하면 그 비교가 통째로 거짓이 된다. 사람이 기억해서 지킬 일이
    # 아니므로 코드가 거절한다.
    if st.get("currency") != "KRW" and (st.get("positions") or st.get("history")):
        raise RuntimeError(
            f"{state_file}: 통화가 원화로 정리되지 않은 장부입니다"
            " — 이 위에서 돌리면 보유 평가액이 환율 배수만큼 뛰어 그 폭등이"
            " 수익으로 기록됩니다(감사 212·215)."
            f" `python -m quant redenominate --principal <원금> --state-file"
            f" {state_file}` 로 먼저 정리하세요.")

    # 원/달러를 **하루 한 번** 잡아 둔다(감사 212). 종목마다 따로 받으면
    # 같은 배치 안에서 종목별로 다른 환율이 적용돼 자산이 미세하게 어긋난다.
    # 못 받으면 None이고, 해외 종목은 그날 값을 매기지 못해 건너뛴다 —
    # 1.0으로 때우지 않는다.
    fx_rate = usdkrw()
    if fx_rate is None and any(needs_fx(m) for m, _ in targets):
        log.warning("원/달러 미확인 — 해외 종목은 오늘 매매하지 않습니다")

    prices, weights, skipped = {}, {}, []
    opens_after: dict = {}          # key → (체결봉, 시가) — 대기 주문 체결용
    last_bars: dict = {}
    last_dates = []
    rets_map: dict = {}             # key → 최근 90일 수익률 — 위험 배분 재료
    opt_present: dict = {}          # key → 오늘 붙은 선택 피처 목록(건강 기록용)
    earnings_guards: dict = {}      # key → 발표일 — 실적 가드 발동 흔적
    skipped_why: dict = {}          # key → 스킵 사유(데이터 장애/휴장 구분)
    data_quality: dict = {}         # key → 품질 스캔 결과(갭·스파이크 등)
    sources: dict = {}              # key → 그 종목 시세를 받은 소스(감사 135)
    partial_bars: dict = {}         # key → 결정 봉 완성도(1.0 미만이면 진행 중)
    guard_damp: dict = {}           # key → 이벤트 감쇠 계수(실적 가드 등)
    kelly_caps: dict = {}           # key → 최종 비중 상한(부분 켈리)
    pending = st.get("pending") or {}
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            df = get_provider(market).get_ohlcv(symbol, timeframe,
                                                limit=lookback)
            if df.empty or (require_real_data
                            and df.attrs.get("synthetic_fallback")):
                raise RuntimeError("실데이터 없음")
            # 데이터 무결성 검사 — 중복 봉·음수 가격·OHLC 모순은 그 종목의
            # 수익률 계산을 통째로 왜곡한다.
            # ⚠️ 이 검사는 원래 수동 backtest 명령에서만 돌았다(2026-08-11
            #    감사). 정작 **실제로 매매하는** 새벽 배치는 한 번도 데이터를
            #    검사하지 않았다 — 오염된 데이터 위의 기록은 그럴듯한
            #    거짓말이 되고, 그 기록이 사이트와 방송에 그대로 나간다.
            from quant.data.quality import is_severe, scan_ohlcv
            q = scan_ohlcv(df)
            if is_severe(q):
                bad = {k: v for k, v in q.items() if v}
                raise RuntimeError(f"데이터 무결성 위반 {bad}")
            data_quality[key] = q
            # 어느 소스에서 받았는가 — 주식 제공자는 야후가 흔들리면 조용히
            # 보조 소스(yahoo-http·stooq)로 넘어간다. 보조 소스는 **무조정가**라
            # 배당·액면분할 날 수익률에 가짜 점프가 생기고, 그 값이 학습
            # 라벨·백테스트·장부에 그대로 들어간다. 제공자는 이 사실을
            # attrs["source"]에 적고 있었지만 **읽는 곳이 한 곳도 없었다**
            # (감사 135) — 기록만 하고 아무도 안 보는 계측기였다.
            sources[key] = str(df.attrs.get("source") or "?")
            if market == "crypto":
                from quant.data.funding import attach_funding
                df = attach_funding(df, symbol)
                from quant.data.openinterest import attach_open_interest
                df = attach_open_interest(df, symbol)
            if market == "kr_stock":
                from quant.data.krx import attach_krx_flows
                df = attach_krx_flows(df, symbol)
            from quant.data.crossasset import attach_cross_asset
            df = attach_cross_asset(df, market, symbol)
            # 오늘 이 종목에 실제로 붙은 선택 피처 — 외부 소스가 죽으면
            # 조용히 줄어드는 것을 장부에 남긴다(같은 fs8 태그로 기록되므로
            # 개수를 함께 남기지 않으면 아무도 모른다)
            from quant.strategies.ml import optional_features_from_df
            opt_present[key] = optional_features_from_df(df)
            if use_champions:
                strat = champion_strategy(market, symbol, state_dir)
            else:
                # 섀도 대조군 — 진화 없이 최초 기본 챔피언으로 고정
                from quant.live.retrain import DEFAULT_CHAMPION, build_strategy
                strat = build_strategy(DEFAULT_CHAMPION)
            # ⚠️ 신호는 **완성된 봉으로만** 낸다(감사 71). 코인은 24시간
            #    시장이라 UTC 일봉의 '오늘' 봉이 항상 진행 중인데, 주식과 달리
            #    그 봉을 버리는 장치가 없어 모델이 미완성 봉을 마지막 행으로
            #    받고 있었다. 실측(스냅샷 2026-08-07~09, 코인 5종목 15봉):
            #      · 결정에 쓴 봉 15/15가 확정 봉과 다름
            #      · 종가 차이 평균 66.8bp(최대 150.8bp)
            #      · 고저 레인지 평균 36% 짧게(최대 89%)
            #    레인지가 짧으면 ATR·GK변동성이 낮게 읽혀 변동성 타깃의 분모가
            #    작아지고, 결국 **목표보다 큰 비중**이 실린다. 게다가 오디션은
            #    완성 봉으로만 평가하니 선발 조건과 실전 조건이 달랐다.
            #
            #    대가는 정직하게 적는다: 마지막 몇 시간의 가격 움직임을 신호가
            #    보지 못한다. 그래도 '오디션과 같은 조건'이 먼저다 — 오늘 하루
            #    고쳐 온 것이 전부 그 격차였다.
            #
            #    체결·평가 가격은 그대로 **지금 값**을 쓴다(아래 prices). 즉
            #    "완성된 정보로 판단하고, 지금 가격에 체결한다" — 실제 트레이더가
            #    하는 것과 같다.
            df_sig = _signal_frame(market, df, timeframe)
            # ⚠️ **표본이 모자라면 판단하지 않고, 그 사실을 남긴다**(감사 201).
            #    예전에는 `df.empty`만 봤다. 보조 거래소가 10봉만 주는 날
            #    신호는 0으로 나오는데 장부에는 흔적이 없어, "3종목 분산"이라
            #    적힌 날 실제 포지션은 2개였다. 조용한 0과 판단해서 낸 0은
            #    다르다 — 전자는 못 한 것이고 후자는 안 한 것이다.
            need = required_bars(champion_spec(market, symbol, state_dir))
            if len(df_sig) < need:
                raise RuntimeError(
                    f"표본 부족 — {len(df_sig)}봉(필요 {need}봉). 챔피언은 더 긴 "
                    f"표본으로 선발됐다(오디션-현실 격차)")
            signals = strat.generate_signals(df_sig)
            weights[key] = float(
                _risk_for(market).size_positions(df_sig, signals).iloc[-1])
            # 실적 가드(미국 주식) — 발표 ±1일 창에서 비중 절반, 흔적 기록.
            # ⚠️ 비중에 바로 곱하지 않고 '감쇠 계수'로 따로 둔다(2026-08-11).
            #    비중에 곱해 버리면 뒤의 변동성 스케일러가 "위험이 줄었다"고
            #    보고 전체를 그만큼 되돌려 키워 가드가 사라진다 — 킬스위치가
            #    무력화됐던 것과 정확히 같은 구조다. 게다가 공분산은 실적
            #    발표를 모르므로, 하필 위험한 날에 목표보다 더 실리게 된다.
            if market == "us_stock" and abs(weights[key]) > 0:
                from datetime import date as _edate

                from quant.data.earnings import earnings_guard_factor
                ef, edate = earnings_guard_factor(
                    symbol, _edate.fromisoformat(str(df_sig.index[-1])[:10]),
                    state_dir=state_dir)
                if edate and ef < 1.0:
                    guard_damp[key] = ef
                    earnings_guards[key] = edate
            # 부분 켈리 상한 — 이 종목 개별 페이퍼 장부(OOS)의 통계 사용.
            # 상한은 '자본 대비 최종 비중'에 걸어야 의미가 있다. 스케일 전
            # 비중에 걸면 스케일러가 상한 위로 다시 올려 놓는다(같은 결함).
            kcap = _kelly_cap_from_history(
                _load_paper(_paper_path(market, symbol, state_dir))
                .get("history") or [])
            if kcap < 1.0:
                kelly_caps[key] = kcap
            # 공분산도 완성 봉으로 — 진행 중인 봉의 '부분 하루' 수익률이
            # 섞이면 위험 추정이 실제보다 작아진다(같은 이유로 비중이 커진다).
            rets_map[key] = df_sig["close"].pct_change().iloc[-90:]
            # 체결·평가는 지금 가격(진행 중 봉의 종가 = 현재가)으로 한다.
            #
            # ⚠️ **원화로 환산해서** 담는다(감사 212). 예전에는 달러 표시
            #    가격을 그대로 더해서, 한 계좌 안에 원화(한국주식)와
            #    달러(미국주식·코인)가 섞여 있었다. "S&P500 ETF 12.25주 =
            #    9,466원"이 장부에 남았고(실제로는 1,300만원어치), 자산
            #    합계는 진짜 원화 금액이 아니었다. 환위험도 통째로 빠져
            #    있었다 — 원화가 절상되면 실제로는 잃는데 장부는 조용했다.
            #    신호는 현지 통화 그대로 낸다(전략 동작은 그대로). 환산은
            #    체결·평가에만 걸어서, 환율 변동이 매일의 재평가로 자산에
            #    흘러들게 한다.
            px_krw = to_krw(market, float(df["close"].iloc[-1]), fx_rate)
            if px_krw is None:
                # 환율을 모르면 값을 매길 수 없다. 1.0으로 때우지 않는다 —
                # 그것이 지금 고치고 있는 바로 그 결함이다.
                raise RuntimeError(
                    "원/달러를 확인하지 못해 원화로 평가할 수 없다 "
                    "(해외 종목은 환산 없이 기록하지 않는다)")
            prices[key] = px_krw
            st["base_prices"].setdefault(key, prices[key])
            last_bars[key] = str(df.index[-1])
            last_dates.append(str(df.index[-1])[:10])
            bs = bar_status(market, df.index[-1], timeframe)
            if bs:
                partial_bars[key] = bs["elapsed"]
            pend = pending.get(key)
            if pend and pend.get("decided_bar"):
                opens_after[key] = _first_bar_after(df, pend["decided_bar"])
        except Exception as exc:  # noqa: BLE001 — 해당 종목만 관망(포지션 유지)
            skipped.append(key)
            # 왜 빠졌는지도 남긴다 — 키만 있으면 '데이터 장애'인지 '거래소
            # 휴장'인지 구분할 수 없고, 구분 못 하면 대응도 못 한다.
            skipped_why[key] = str(exc)[:200]
            log.warning("포트폴리오 %s 스킵: %s", key, exc)
    if not prices:
        raise RuntimeError("포트폴리오: 전 종목 데이터 실패 — 기록하지 않음")

    # 시장별 '판단에 쓴 봉'이 얼마나 묵었나 — 배치 시각이 시장 마감보다
    # 이르면 그 시장만 조용히 하루 뒤처진다(감사 220).
    #
    # ⚠️ 배치는 05:30 KST(20:30 UTC)에 돈다. 미국장 마감은
    #        여름(EDT) 05:00 KST → 30분 여유, 정상
    #        겨울(EST) 06:00 KST → **장이 아직 열려 있다**
    #    겨울에는 오늘 봉이 미완성이라 버려지고 미국 신호만 **한 세션 전**
    #    봉으로 내려간다. 11월~3월 다섯 달을 그렇게 도는데 어디에도 표시가
    #    없었다 — 한국·코인은 최신이고 미국만 뒤처지니 종목 간 비교도
    #    어긋난다. 코드가 고칠 수 있는 것은 **그 사실을 드러내는 것**이다.
    from datetime import date as _bd
    bar_age: dict = {}
    _today = _bd.today()
    for _k, _b in last_bars.items():
        try:
            _age = (_today - _bd.fromisoformat(str(_b)[:10])).days
        except ValueError:
            continue
        _m = _k.split(":")[0]
        bar_age[_m] = max(bar_age.get(_m, 0), _age)
    stale_gap = (max(bar_age.values()) - min(bar_age.values())) if bar_age else 0
    if stale_gap >= 2:
        log.warning(
            "시장별 판단 봉 신선도가 어긋납니다 %s — 배치 시각이 어느 시장의 "
            "마감보다 이르면 그 시장만 한 세션 뒤처집니다(겨울 서머타임 해제 "
            "시 미국장은 06:00 KST에 닫습니다)", bar_age)

    bar = max(last_dates)
    if st.get("last_bar") == bar:
        log.info("포트폴리오: 같은 봉(%s)에 이미 실행됨 — 건너뜀", bar)
        return {"skipped": True, "last_bar": bar}

    broker = PaperBroker(cash=float(st["cash"]))
    for key, pos in st.get("positions", {}).items():
        if abs(float(pos.get("quantity", 0.0))) > 0:
            broker._positions[key] = Position(
                key, float(pos["quantity"]), float(pos.get("avg_price", 0.0)))
    n = len(targets)

    # ⚠️ 평가에 쓸 시세는 **오늘 받은 것 + 마지막으로 알던 것**이다(감사 152).
    #    오늘 데이터를 못 받은 종목은 prices에 없는데, 포지션은 위에서 그대로
    #    복원된다. 그러면 `PaperBroker.equity`가 그 종목을 **매입가**로 값을
    #    매긴다 — 즉 "산 뒤로 한 푼도 안 움직였다"고 치는 것이다.
    #
    #    그 자산 숫자가 그대로 (1) 장부의 자산·수익률 (2) 킬스위치가 읽는
    #    낙폭 (3) 사이트에 나가는 TWR로 흘러간다. 폭락한 종목이 하필 그날
    #    데이터 장애를 만나면 **손실이 장부에서 사라지고 브레이크도 안 걸린다.**
    #
    #    마지막으로 알던 시장가로 평가한다. 그것도 틀린 값이지만 '손실 0'보다
    #    훨씬 덜 틀리고, 무엇보다 아래 stale_marks로 **그 사실이 드러난다**.
    stale_marks = {}
    for key, pos in st.get("positions", {}).items():
        if key in prices or abs(float(pos.get("quantity", 0.0))) <= 0:
            continue
        lp = pos.get("last_price")
        if lp:
            stale_marks[key] = {"price": float(lp),
                                "as_of": pos.get("last_price_bar")}
    marks = {**{k: v["price"] for k, v in stale_marks.items()}, **prices}

    # 운영 설정(어드민 대시보드) — 일시정지·노출 배수. 파일이 없으면 정상 운용.
    from quant.utils.settings import load_settings
    settings = load_settings()
    paused = bool(settings["trading_paused"])
    if paused:
        # 신규 매매 중단: 보유 포지션은 유지하되 대기 주문은 폐기한다.
        # 폐기 이유 — 며칠 뒤 재개 시 '결정 당시 다음 시가'는 이미 과거라,
        # 그때 체결하면 옛 가격으로 사는 회계 왜곡(사실상 룩어헤드)이 된다.
        log.warning("⏸ 어드민 일시정지 — 신규 매매 중단, 대기 주문 %d건 폐기",
                    len(pending))
        pending = {}

    # ① 대기 주문 체결 — 주식은 결정 다음 세션의 '시가'에서만 체결(개장 갭 감수).
    #    평가 마크는 현재 종가 근사(스킵 종목은 평단가) — 체결가만 시가를 쓴다.
    fills = []
    # ⚠️ **매도를 먼저 낸다**(사장님 결정 2026-08-13). 순서를 정하지 않으면
    #    dict 순서대로 나가고, 그러면 판 돈이 같은 사이클의 매수에 안 쓰인다
    #    — 현금이 모자라 매수가 잘리거나 다음 날로 밀린다. 예산을 유연하게
    #    쓰기로 한 이상(한 종목의 1주를 사려고 다른 종목을 파는 이상)
    #    "먼저 팔고 그 돈으로 산다"가 지켜져야 그 결정이 그날 안에 완성된다.
    #    비중을 줄이는 쪽(=매도)부터, 줄이는 폭이 큰 순서로.
    #    ⚠️ 여기서는 아직 그날의 `equity`가 계산되기 전이다(체결이 끝나야
    #       정해진다). 순서를 정하는 데는 정확한 값이 필요 없으므로 지금
    #       시점의 평가액 스냅샷을 쓴다 — 못 구하면 정렬을 건드리지 않는다.
    try:
        eq_snap = float(broker.equity(marks))
    except Exception:  # noqa: BLE001
        eq_snap = 0.0

    def _sell_first(item):
        k, p = item
        if eq_snap <= 0:
            return (0.0, k)
        try:
            held = float(broker.get_position(k).quantity)
        except Exception:  # noqa: BLE001 — 모르면 중립(매수 앞에 두지 않는다)
            held = 0.0
        px = (opens_after.get(k) or (None, None))[1] or 0.0
        held_w = held * px / eq_snap
        return (abs(float(p.get("weight") or 0.0)) - abs(held_w), k)

    for key, pend in sorted(pending.items(), key=_sell_first):
        fbar, fopen = opens_after.get(key, (None, None))
        if fopen is None:
            continue
        broker.fee = _fill_cost(key.split(":")[0])
        eq_now = broker.equity({**marks, key: fopen})
        sl = float(pend.get("slice") or (1.0 / n))   # 결정 당시의 ERC 슬라이스
        order = broker.target_weight(
            key, float(pend["weight"]) * sl, fopen, eq_now,
            rebalance_band_rel=_rebalance_band_rel(key.split(":")[0]))
        if order is None:
            pending.pop(key, None)
            continue                       # 밴드 안 — 고쳐 잡지 않는다
        # ⚠️ 기록하는 비중은 **실제로 낸 주문**과 같아야 한다(감사 92).
        #    주문은 바로 위에서 `pend["weight"] * sl`로 나가는데 기록만
        #    슬라이스를 빼먹고 있었다 — 같은 값을 한 줄 사이에서 두 정의로
        #    쓴 셈이라, 장부가 실제보다 10~50배 큰 체결 비중을 말했다
        #    (2026-08-10 069500 체결: 장부 0.165 / 실제 주문 0.0036).
        # 수량·금액도 남긴다(2026-08-13). 예전에는 체결가와 결과 비중만
        # 적어서, "언제 얼마에 샀나"는 알아도 **얼마어치**를 샀는지는 장부
        # 어디에도 없었다 — 거래내역을 만들 수가 없었다. 주문 객체가 이미
        # 수량을 들고 있었는데 버리고 있었다.
        fills.append({"key": key, "price": round(fopen, 6), "bar": fbar,
                      "weight": round(float(pend["weight"]) * sl, 4),
                      "side": order.side,
                      "quantity": round(float(order.quantity), 10),
                      "amount": round(float(order.quantity) * float(fopen), 2),
                      "type": "시가"})           # 결정 다음 세션 시가 체결
        pending.pop(key, None)

    # ② 오늘의 결정 — 코인은 즉시 체결, 주식은 다음 시가 대기열로
    equity = broker.equity(marks)

    # 자동 킬스위치 — 계좌 낙폭 단계별 노출 축소·단계 복귀(히스테리시스).
    #
    # ⚠️ 낙폭은 자산(equity)이 아니라 **입금 효과를 제거한 성장 지수** 위에서
    #    잰다. 예전에는 자산 고점 대비로 쟀는데, 그러면 매칭 입금이 고점을
    #    끌어올려 손실이 그대로인데도 낙폭이 0으로 보인다 — 즉 **입금이
    #    킬스위치를 풀어버린다**(2026-08-11 감사). 하필 브레이크가 필요한
    #    상황에서 돈을 더 넣는 순간 브레이크가 풀리는 구조였다.
    #    (지금은 입금이 없어 두 방식의 값이 같다 — 첫 입금 날 발동할 결함이다.)
    _series = twr_index(
        st["history"] + [{"date": bar, "equity": equity}],
        st.get("deposits") or [],
        start_cash=float(st.get("start_cash", PORTFOLIO_START_CASH)))
    drawdown = drawdown_from_index(_series)
    risk_scale = _kill_switch_scale(float(st.get("risk_scale", 1.0)), drawdown)
    st["risk_scale"] = risk_scale
    if risk_scale < 1.0:
        log.warning("킬스위치: 낙폭 %.1f%% → 노출 %.0f%%로 제한",
                    drawdown * 100, risk_scale * 100)
    # 어드민 노출 배수·일시정지 — 킬스위치와 곱으로 적용(더 보수적인 쪽).
    # 기록되는 risk_scale(킬스위치 상태)은 유지하고 실효 노출만 줄인다.
    eff_scale = risk_scale * float(settings["exposure_scale"])
    if paused:
        eff_scale = 0.0

    # 위험 배분 슬라이스 — HRP(상관 추정 오차에 강함) → ERC → 균등 폴백 사다리
    # ⚠️ **`or` 폴백은 '전부 0인 배분'을 못 걸러낸다**(감사 183). 파이썬에서
    #    값이 전부 0인 dict는 **참(truthy)**이다. 배분기가 `{"A":0.0,"B":0.0}`을
    #    돌려주면 `hrp or erc or 균등`이 폴백으로 넘어가지 않고 그대로 채택된다
    #    — 전 종목 비중 0, 하루 통째로 관망인데 장부에는 "hrp로 배분함"이라
    #    적힌다. 조용한 무동작이라 알아채는 데 며칠 걸린다.
    #
    #    `hrp.py` 안에 같은 뜻의 검사가 있었지만 거기서는 정규화 뒤라 어떤
    #    입력으로도 안 걸렸다 — 방어를 위험한 자리가 아니라 만든 자리에 둔
    #    셈이다. 받아들이는 쪽으로 옮긴다.
    from quant.live.hrp import is_allocation

    hrp = _hrp_slices(rets_map, n)
    hrp = hrp if is_allocation(hrp) else None
    erc = None if hrp else _erc_slices(rets_map, n)
    erc = erc if is_allocation(erc) else None
    slices = hrp or erc or {k: 1.0 / n for k in weights}
    alloc_method = "hrp" if hrp else ("erc" if erc else "equal")
    # 횡단면 확신도 틸트 — ERC(위험만 봄) 위에 '챔피언 확신도 순위'를 곱해
    # 자본을 고확신 종목으로 기울인다. 총예산 보존 재정규화 후 과집중 상한
    # (3/n)을 다시 적용한다(상한 초과분은 재분배하지 않고 버림 — 보수적).
    # 신호 평활 — 확률의 하루짜리 떨림이 전 종목 매매를 부르는 것을 막는다.
    # 슬라이스·변동성 타깃보다 앞에 둔다(원 신호 단계에서 걸러야 뒤가 안정).
    weights = _smooth_weights(weights, st.get("prev_weights") or {})
    st["prev_weights"] = {k: round(v, 6) for k, v in weights.items()}

    tilt = _xsec_tilt(weights)
    budget = sum(slices.get(k, 1.0 / n) for k in weights)
    tilted = {k: slices.get(k, 1.0 / n) * tilt.get(k, 1.0) for k in weights}
    tot = sum(tilted.values())
    if budget > 0 and tot > 0:
        cap = 3.0 / n
        slices = {k: min(v * budget / tot, cap) for k, v in tilted.items()}
    # 포트폴리오 목표 변동성 — 종목 사이징(20% 목표) × 1/n 슬라이스의 이중
    # 감쇠로 총노출이 우연히 결정되던 것을 명시적 목표로 교정한다. 엣지가
    # 입증되기 전에는 게이트가 검증 목표(연 1%)를 상한으로 강제한다.
    from quant.risk.portfolio_vol import target_vol_now, vol_scale
    tgt_vol, vol_proven, vol_why = target_vol_now(state_dir)
    # ⚠️ 변동성 스케일은 **감쇠 전** 비중으로 계산한다(2026-08-11 감사).
    #    킬스위치가 걸린 비중(eff_scale 곱한 값)을 넣으면, 스케일러가 "위험이
    #    작다"고 판단해 그만큼 되돌려 키운다 — 무레버리지 상한도 감쇠된
    #    총노출 기준으로 계산되므로 **최종 노출이 감쇠 전과 똑같아진다.**
    #    실측: eff_scale 0.25(75% 축소)를 걸어도 최종 총노출 100%.
    #    즉 낙폭 브레이크와 어드민 노출 배수가 둘 다 죽어 있었다.
    #    순서가 곧 의미다: 변동성 타깃이 '위험 예산'을 정하고, 킬스위치는
    #    그 예산을 잘라낸다. 예산 계산에 이미 잘린 값을 넣으면 안 된다.
    base_w = {k: w * slices.get(k, 1.0 / n) for k, w in weights.items()}
    vscale, ex_ante = vol_scale(base_w, rets_map, tgt_vol)
    log.info("변동성 타깃: 목표 연 %.2f%% · 사전추정 %s · 배수 %.2f · "
             "감쇠 %.2f (%s)",
             tgt_vol * 100,
             f"{ex_ante * 100:.2f}%" if ex_ante else "추정불가",
             vscale, eff_scale, vol_why)

    def _target_w(key: str, w: float) -> float:
        """그 종목의 최종 목표 비중(부호 포함).

        ⚠️ **주문과 기록이 같은 값을 쓰게 하는 단 하나의 자리다.** 예전에는
           주문 루프와 기록(_applied)이 같은 식을 따로 적어, 한쪽만 고치면
           장부가 실제 주문과 다른 값을 말했다(감사 92가 그 사고였다).

        킬스위치×어드민 배수×변동성 타깃을 곱하고, 이벤트 감쇠(실적 가드)와
        켈리 상한은 **스케일 뒤에** 건다 — 앞에 두면 스케일러가 되돌려 키워
        둘 다 무효가 된다.
        """
        eff = w * eff_scale * vscale * guard_damp.get(key, 1.0)
        kcap = kelly_caps.get(key)
        if kcap is not None:
            eff = float(np.clip(eff, -kcap, kcap))
        return eff * slices.get(key, 1.0 / n)

    # 예산에 맞춰 실현 가능한 비중으로 바꾼다(정수 주 내림 · 못 사면 미룸 ·
    # 남은 예산은 살 수 있는 종목에 재배분) — 2026-08-12 운영자 결정.
    # ⚠️ 이름을 `targets`로 두면 **함수 인자 targets(종목 목록)를 가린다.**
    #    실제로 그렇게 썼다가 `"planned": len(targets)`가 계획 종목 수 대신
    #    오늘 판단한 종목 수를 세게 됐고, 감사 59에서 고쳤던 결함이 그대로
    #    되살아났다 — 검사가 잡았다(500줄짜리 함수에서 이름 하나가 그렇다).
    # 확신도 = 슬라이스·변동성 타깃을 곱하기 **전**의 원 신호 크기. 이것이
    # 이 시스템이 "어느 쪽이 더 오를 것 같은가"에 내놓는 답이고, `_xsec_tilt`도
    # 같은 값으로 자본을 기울인다. 정수 주 예산은 이 순서로 채운다
    # (사장님 2026-08-13: "비율로 따지는 게 아니야. 수익률이 더 높을 것이라
    #  판단되는 최우선 선택을 하는 거지.").
    fitted_w, deferred_lots = _fit_to_budget(
        {k: _target_w(k, w) for k, w in weights.items()},
        prices, equity, cap=3.0 / n,
        conviction={k: abs(float(w)) for k, w in weights.items()})
    if deferred_lots:
        log.info("1주 미만이라 오늘 미룬 종목 %d개: %s",
                 len(deferred_lots), ", ".join(sorted(deferred_lots)))
    # 자기 배정금액을 넘겨 산 종목 — "무엇을 포기하고 무엇을 샀는지"의 기록.
    # 예산 유연화는 공짜가 아니다: 이만큼은 확신도가 낮은 종목이 쓸 돈이었고,
    # 그 종목들은 목표가 0이 되어 이미 들고 있었다면 팔린다. 그 사실이 장부에
    # 남아야 사이트도 방송도 "왜 오늘 국내주식이 한 종목뿐인가"를 답할 수 있다.
    lot_priority = {}
    for k, base in ((k, _target_w(k, w)) for k, w in weights.items()):
        got = fitted_w.get(k, 0.0)
        if abs(got) > abs(base) + 1e-12 and prices.get(k):
            lot_priority[k] = {
                "budget": round(abs(base) * equity, 2),
                "spent": round(abs(got) * equity, 2),
                "price": round(float(prices[k]), 2),
                "gave_way": sorted(deferred_lots),
            }
    if lot_priority:
        log.info("배정금액을 넘겨 산 종목 %d개(확신도 우선): %s",
                 len(lot_priority), ", ".join(sorted(lot_priority)))

    n_orders_before = len(getattr(broker, "order_log", []))
    skipped_dust = []
    skipped_cool = []
    last_trade = st.get("last_trade") or {}
    # 보유 비중을 **한 번만** 조회해 둔다. 두 가지에 쓴다 —
    #   ① 매도 선집행 순서(아래 정렬)
    #   ② 쿨다운·잔돈 판정(루프 안)
    # 예전에는 루프 안에서만 조회했는데, 그러면 순서를 정하려고 한 번 더
    # 물어야 해서 브로커 호출이 두 배가 된다(레이트리밋).
    held_ws: dict = {}
    held_fail: dict = {}
    for key in weights:
        if not prices.get(key):
            continue
        try:
            held_ws[key] = (broker.get_position(key).quantity
                            * float(prices[key]) / equity) if equity > 0 else 0.0
        except Exception as exc:  # noqa: BLE001
            held_fail[key] = exc

    # ⚠️ **매도를 먼저 낸다**(사장님 결정 2026-08-13). 예산을 유연하게 쓰기로
    #    한 이상 — 확신도 높은 종목의 1주를 사려고 낮은 종목을 파는 이상 —
    #    "먼저 팔고 그 돈으로 산다"가 지켜져야 그 결정이 그날 안에 완성된다.
    #    순서를 안 정하면 dict 순서대로 나가고, 현금이 모자라 매수가 잘린다.
    def _sell_first(key: str):
        return (abs(fitted_w.get(key, 0.0)) - abs(held_ws.get(key, 0.0)), key)

    for key in sorted(weights, key=_sell_first):
        w = weights[key]
        market = key.split(":")[0]
        sl = slices.get(key, 1.0 / n)
        tw = fitted_w[key]             # 예산까지 반영한 최종 목표 비중
        if paused:
            continue                           # 일시정지: 신규 주문 없음(포지션 유지)
        # 재조정 쿨다운 — 매일 판단하되 자주 고쳐 잡지는 않는다
        #
        # ⚠️ 보유 조회가 실패하면 '없음(0)'으로 치지 않는다(감사 53). 보유를
        #    0으로 오인하면 목표와의 이탈이 100%로 계산돼 `큰 이탈은 즉시
        #    대응` 예외에 걸리고, 쿨다운(회전율 통제)이 통째로 무력화된다.
        #    조회가 흔들리는 날일수록 더 많이 매매하게 되는 정반대 결과다.
        #    모를 때는 손대지 않는다 — 다만 청산(목표 0)만은 막지 않는다.
        held_w = held_ws.get(key, 0.0)
        exc = held_fail.get(key)
        if exc is not None and abs(tw) >= 1e-9:   # 청산이 아니면 오늘은 건너뛴다
            skipped_why[key] = f"보유 조회 실패 — {type(exc).__name__}"
            pending.pop(key, None)
            continue
        if _in_cooldown(key, last_trade, bar, tw, held_w,
                        _rebalance_band_rel(market, state_dir)):
            skipped_cool.append(key)
            pending.pop(key, None)
            continue
        # 잔돈 주문 차단 — 목표와 현 보유의 차이가 최소 주문금액에 못 미치면
        # 주문하지 않는다. 40원짜리 매매는 비용(한국주식 실측 왕복 ~93bp)만
        # 남기고 체결 표본까지 오염시킨다.
        if _is_dust_order(broker, key, tw, prices.get(key), equity):
            skipped_dust.append(key)
            pending.pop(key, None)
            continue
        if market in IMMEDIATE_FILL_MARKETS:
            broker.fee = _fill_cost(market)
            # 비용 비례 상대 밴드 — 비싼 시장일수록 더 벗어나야 고쳐 잡는다
            broker.target_weight(key, tw, prices[key], equity,
                                 rebalance_band_rel=_rebalance_band_rel(market))
        else:
            # 예산 반영 후의 최종 비중을 통째로 남긴다(slice=1.0).
            # 예전에는 eff와 slice를 나눠 저장하고 체결 때 곱했는데,
            # 그러면 예산 조정이 체결 시점에 사라진다.
            pending[key] = {"weight": round(tw, 6), "slice": 1.0,
                            "decided_bar": last_bars[key]}
    if skipped_dust:
        log.info("잔돈 주문 %d건 생략(최소 %s원 미만): %s",
                 len(skipped_dust), f"{MIN_ORDER_KRW:,.0f}",
                 ", ".join(skipped_dust))
    st["pending"] = pending
    # 코인 즉시 체결 내역 — "오늘 얼마에 사고팔았나"를 사이트가 보여줄 재료.
    # 주식 시가 체결(fills 위쪽)과 함께 그날 기록에 남는다.
    for o in getattr(broker, "order_log", [])[n_orders_before:]:
        fills.append({"key": o.symbol, "price": round(float(o.price), 6),
                      "bar": last_bars.get(o.symbol, ""),
                      "side": o.side,
                      "quantity": round(float(o.quantity), 10),
                      "amount": round(float(o.quantity) * float(o.price), 2),
                      "type": "즉시"})
    # 쿨다운 기준일 갱신 — 오늘 실제로 고쳐 잡은 종목만
    for f in fills:
        last_trade[f["key"]] = str(bar)[:10]
    st["last_trade"] = last_trade
    if skipped_cool:
        log.info("쿨다운으로 재조정 보류 %d건: %s",
                 len(skipped_cool), ", ".join(skipped_cool))
    equity = broker.equity(marks)

    # 피처 건강 집계 — 종목마다 적용 가능한 선택 피처가 다르므로(코인만
    # 펀딩비, 한국주식만 KRX 수급) '가능한 최대치 대비 몇 개가 실제로
    # 붙었는가'를 종목별 최대값 기준으로 잰다. 소스가 죽은 날을 잡아내는 것이
    # 목적이지, 시장별 차이를 결함으로 보는 것이 아니다.
    feat_health = None
    if opt_present:
        from quant.strategies.ml import OPTIONAL_FEATURES
        best = max((len(v) for v in opt_present.values()), default=0)
        worst_key = min(opt_present, key=lambda k: len(opt_present[k]))
        union = sorted({c for v in opt_present.values() for c in v})
        feat_health = {
            "optional_max": best,
            "optional_possible": len(OPTIONAL_FEATURES),
            "union": len(union),
            "missing_everywhere": [c for c in OPTIONAL_FEATURES
                                   if c not in set(union)],
            "thinnest": {"key": worst_key,
                         "n": len(opt_present[worst_key])},
        }

    # 균등가중 지수(첫 관측=100) — 사이트의 '그냥 보유' 벤치마크용
    idx = 100.0 * sum(prices[k] / st["base_prices"][k]
                      for k in prices) / len(prices)
    # 기록되는 총노출은 '실제로 적용한' 비중의 합이어야 한다 — 감쇠(실적
    # 가드)와 켈리 상한을 빼먹으면 장부가 실제보다 큰 노출을 말하게 된다.
    # ⚠️ 여기서 다시 계산하지 않는다. 예전에는 주문 루프와 이 기록이 같은
    #    식을 **따로** 적어, 한쪽만 고치면 장부가 실제 주문과 다른 값을
    #    말했다(감사 92). 이제 둘 다 fitted_w 하나만 읽는다 — 예산 조정
    #    (정수 주 내림·미룸·재배분)도 자동으로 반영된다.
    gross = sum(abs(v) for v in fitted_w.values())

    def _turnover_traded(history: list, now: dict) -> float | None:
        """자산 대비 실제 회전율 = Σ|오늘 노출 − 어제 노출|.

        비용은 '몇 종목을 건드렸나'가 아니라 '얼마어치를 사고팔았나'에
        비례한다. 어제 기록에 종목별 적용 노출이 없으면(감사 91 이전)
        계산할 수 없으므로 None — 모르면 숫자를 만들지 않는다.
        """
        prev = (chrono(history)[-1].get("applied") if history else None)
        if not prev or not now:
            return None
        keys = set(prev) | set(now)
        return round(sum(abs(float(now.get(k, 0.0)) - float(prev.get(k, 0.0)))
                         for k in keys), 4)
    # 종목별 '실제로 적용한' 노출 — 사이트·SNS가 "오늘 뭘 얼마나 샀나"를
    # 말할 때 쓸 수 있는 유일한 숫자다. `alloc`은 **배분 예산**이라 모델이
    # 관망한 종목에도 붙어 있고, 그걸 "매수 8%"라 부르면 사지 않은 종목을
    # 샀다고 공개하게 된다(2026-08-11 감사 91). 합은 정의상 weight와 같다.
    applied = {k: round(abs(v), 4) for k, v in fitted_w.items() if abs(v) > 0}
    # 원금(시작금 + 매칭 입금)과 손익을 분리 — 입금이 수익처럼 보이면 안 된다.
    #
    # ⚠️ 여기가 입금이 **정산되는 유일한 자리**다(감사 211). 위에서 equity를
    #    현금+평가액으로 다시 쟀고, 그 현금에는 그동안 들어온 입금이 이미
    #    포함돼 있다. 즉 이 순간부로 그 돈은 자산의 일부다 — 그 사실을 봉
    #    이름으로 찍어 둔다. 찍기 **전에** 원금에 더하면 자산은 옛 기록,
    #    원금만 새 값이 되어 입금액이 통째로 손실로 보인다(실측 -920,749원).
    #    금액·날짜·메모는 건드리지 않는다.
    for _d in st.get("deposits", []):
        if not _d.get("settled_bar"):
            _d["settled_bar"] = bar
    principal = principal_of(st.get("start_cash", PORTFOLIO_START_CASH),
                             st.get("deposits", []))
    record = {"date": bar, "price": round(idx, 2), "weight": round(gross, 4),
              "equity": round(equity, 2),
              "return_pct": round((equity / principal - 1) * 100, 2),
              "principal": round(principal, 2),
              "pnl": round(equity - principal, 2),
              "hit_rate": None,
              "fills": fills,                      # 체결 현실성: 시가·즉시 체결 내역
              # 예약 주문 — 오늘 새벽 결정됐고 '다음 장 시가'에 체결될 것들.
              # 사이트가 "내일 뭘 얼마나 살 예정인가"를 보여줄 재료.
              "pending_next_open": {k: round(float(p["weight"])
                                             * float(p.get("slice") or 1.0 / n), 4)
                                    for k, p in pending.items()},
              "code_sha": _code_sha(),
              "env": _env_fingerprint(),
              "accounting": ACCOUNTING_VERSION,
              # 그날 적용한 원/달러 — **환산을 검산할 수 있어야 한다**(감사 216).
              # 감사 212에서 해외 종목을 원화로 환산하게 고쳤는데, 정작 어떤
              # 환율을 썼는지는 어디에도 안 남겼다. 사이트는 "원화로 환산했다"고
              # 말하면서 얼마로 했는지는 말하지 않았던 셈이라, 누구도 그 숫자를
              # 다시 계산해 볼 수 없었다. "누구든 검증할 수 있다"는 이 프로젝트의
              # 약속에서 검산 못 하는 변환은 그냥 믿어 달라는 말이다.
              "fx_usdkrw": (round(float(fx_rate), 4)
                            if fx_rate is not None else None),
              # 시장별 판단 봉의 나이(일). 배치 시각과 시장 마감이 어긋나면
              # 여기서 드러난다 — 로그만 남기면 아무도 안 본다(감사 220).
              "bar_age_days": bar_age or None,
              # 킬스위치·배분의 흔적 — 그날 왜 노출이 줄었는지 장부로 남는다
              "risk_scale": risk_scale,
              # 어드민 개입의 흔적 — 일시정지·노출 배수는 숨기지 않고 기록한다
              "paused": paused,
              "exposure_scale": float(settings["exposure_scale"]),
              "drawdown_pct": round(drawdown * 100, 2),
              # ⚠️ alloc은 **배분 예산**이다(관망 종목에도 붙는다).
              #    "얼마나 샀나"는 아래 applied를 봐야 한다.
              "alloc": {k: round(v, 4) for k, v in slices.items()},
              "applied": applied or None,
              "alloc_method": alloc_method,   # hrp | erc | equal — 폴백 흔적
              # 포트폴리오 변동성 타깃의 흔적 — 총노출이 왜 이 크기인지의 답.
              # proven=False면 게이트가 검증 목표를 상한으로 잠근 상태다.
              "vol_target": {
                  "target": round(tgt_vol, 5),
                  "ex_ante": round(ex_ante, 5) if ex_ante else None,
                  "scale": round(vscale, 4),
                  # 감쇠(킬스위치×어드민)까지 반영한 실제 적용 배수 —
                  # 예산(scale)과 브레이크(damp)를 따로 남겨야 "왜 오늘
                  # 노출이 이만큼인가"를 장부만으로 답할 수 있다.
                  "damp": round(eff_scale, 4),
                  "applied": round(vscale * eff_scale, 4),
                  "proven": vol_proven,
                  "reason": vol_why,
              },
              # 오늘 시세를 못 받아 **마지막으로 알던 가격**으로 평가한 종목
              # (감사 152). 이게 없으면 매입가로 평가돼 손실이 0으로 보이고,
              # 그 자산이 킬스위치가 읽는 낙폭과 사이트 TWR로 그대로 간다.
              "stale_marks": (
                  {k: {"price": round(v["price"], 6), "as_of": v["as_of"]}
                   for k, v in stale_marks.items()} or None),
              # 잔돈으로 판단해 생략한 주문 — 비용만 남기는 매매는 안 한다
              "skipped_dust": skipped_dust or None,
              # 쿨다운으로 보류한 재조정 — 왜 오늘 안 고쳤는지의 답
              "skipped_cooldown": skipped_cool or None,
              # 회전율 흔적 — 그날 실제로 몇 종목을 갈아탔는가. 비용이 수익을
              # 먹는지 사후가 아니라 매일 볼 수 있어야 한다.
              # ⚠️ ratio는 '오늘 **몇 종목을** 건드렸나'지 회전율이 아니다
              #    (2026-08-12 감사 119). 사이트가 이걸 자산 대비 회전율로
              #    읽고 왕복비용을 곱해 "연 비용 70%"를 냈는데, 13종목을
              #    각각 자산의 0.1%씩 움직였다면 실제 회전율은 1.3%지
              #    65%가 아니다. 비용은 **거래 금액**에 비례한다.
              #    그래서 진짜 회전율 traded = Σ|Δ적용노출| 을 함께 남긴다.
              "turnover": {"filled": len(fills), "universe": n,
                           "symbols_ratio": round(len(fills) / n, 4) if n else None,
                           "traded": _turnover_traded(st["history"], applied)},
              # 피처 건강 — 외부 소스가 죽으면 피처가 조용히 줄어드는데
              # 장부에는 같은 fs8로 남는다. 실제 개수를 함께 남긴다.
              "feature_health": feat_health or None,
              # 실적 가드 발동 종목(있을 때만) — 발표 임박으로 비중 절반
              "earnings_guard": earnings_guards or None,
              # 부분 켈리 상한이 실제로 비중을 깎은 종목(있을 때만).
              # 장부는 "왜 오늘 노출이 이만큼인가"에 답할 수 있어야 하는데,
              # 위험 장치 중 이것만 흔적이 없었다 — 상한이 총노출을 41%에서
              # 1%로 깎아도 장부에는 아무 이유가 안 남았다(감사 59).
              "kelly_caps": ({k: round(v, 4) for k, v in kelly_caps.items()}
                             or None),
              # 횡단면 확신도 틸트 배수 — 그날 왜 이 종목에 더 실렸는지의 흔적
              "xsec_tilt": {k: round(v, 3) for k, v in tilt.items()},
              # 오늘 실제로 몇 종목으로 굴렸는가. 20종목 중 15개가 빠진 날은
              # '20종목 분산'이 아니라 5종목 집중이다 — 그 사실이 장부에
              # 남아야 사이트도 경보도 진실을 말할 수 있다(2026-08-11).
              # 데이터 품질 집계 — 무결성 위반은 위에서 스킵되므로 여기 남는
              # 것은 '사람이 맥락으로 판단할' 항목(갭·스파이크·거래량 0)이다.
              "data_quality": ({
                  k: sum(q.get(k, 0) for q in data_quality.values())
                  for k in ("gaps", "spikes", "zero_volume")
              } if data_quality else None),
              # ⚠️ symbols는 '오늘 실제로 판단한 종목 수'다 — 계획(planned)이
              #    아니다. 예전에는 여기가 n(=len(targets), 즉 계획 수)이라
              #    20종목 중 15개가 데이터 실패로 빠진 날에도 "20종목 분산"이
              #    그대로 기록됐다. SNS 캡션이 이 값을 읽어 방송하므로, 계획을
              #    실적으로 말하는 셈이었다(감사 59). 오늘 아침 planned·skipped를
              #    추가하면서 정작 남들이 읽는 이 필드를 고치지 않았다.
              "champion": {"symbols": len(prices), "skipped": skipped,
                           "planned": len(targets),
                           "skipped_why": skipped_why or None},
              # 어느 소스에서 시세를 받았는가(감사 135). 주식 제공자는 야후가
              # 흔들리면 조용히 보조 소스로 넘어가는데, 보조 소스는 무조정가라
              # 배당·분할 날 수익률에 가짜 점프가 생긴다. 그 사실이 장부에
              # 남지 않으면 "누구든 검증할 수 있다"는 말이 약해진다 —
              # 공개 차트와 대조하는 사람은 왜 어긋나는지 알 수 없다.
              # 실계좌에서 1주도 못 사는 종목(감사 137). 소수점 매매가 없는
              # 시장(국내주식)에서 배정금액이 1주 값에 못 미치면, 이 기록의
              # 그 줄은 **현실에서 재현할 수 없는 보유**다. 숨기지 않는다.
              "lot_infeasible": deferred_lots or None,
              # 배정금액을 넘겨 산 종목(감사 200 · 사장님 결정 2026-08-13).
              # 유연화의 대가를 숨기지 않는다 — 이 돈은 gave_way의 종목이
              # 쓸 돈이었고, 그 종목들은 오늘 목표가 0이라 팔렸다.
              "lot_priority": lot_priority or None,
              "data_source": sources or None,
              # 그중 **1차 소스가 아닌** 것들. 사람이 매일 20줄을 읽지
              # 않아도 되도록, 봐야 할 것만 따로 뽑아 둔다.
              "data_source_fallback": _source_fallbacks(sources) or None,
              # 결정에 쓴 마지막 봉이 아직 만들어지는 중이던 종목들(감사 56).
              # 코인은 24시간 시장이라 UTC 일봉의 '오늘' 봉이 항상 진행 중인데,
              # 주식과 달리 그 봉을 버리는 장치가 없다. 그 봉의 종가·고저는
              # 확정값이 아니므로, 어느 종목이 몇 % 만들어진 봉으로 판단됐는지
              # 남긴다 — 공개 차트와 대조하려는 사람이 오해하지 않도록.
              "bar_partial": partial_bars or None,
              # 오늘 쓴 재조정 밴드와 그 근거(감사 74). 이 값은 실측 표본이
              # 문턱을 넘는 순간 가정→실측으로 갈아타며 한국주식 기준
              # 0.150→0.400(2.67배)까지 뛴다 — 그날 회전율이 크게 줄지만
              # 예전에는 장부에 아무 흔적이 없어 '이유 없이 매매가 멎은 날'로
              # 보였다. 판단한 쪽이 근거를 남긴다.
              "rebalance_band": {m: rebalance_band_basis(m, state_dir)
                                 for m in sorted({k.split(":")[0]
                                                  for k in weights})} or None}
    record["twr_pct"] = time_weighted_return(
        st["history"] + [record], st.get("deposits", []),
        start_cash=float(st.get("start_cash", PORTFOLIO_START_CASH)))
    # 하루치 수익률 — 누적(return_pct)과 절대 섞이면 안 되는 별개의 숫자.
    record["day_pct"] = day_return_pct(
        st["history"] + [record], st.get("deposits", []),
        start_cash=float(st.get("start_cash", PORTFOLIO_START_CASH)))
    # 무작위 전략 1,000개 분포 대비 백분위 — 바이앤홀드보다 반박이 어려운 기준.
    # 같은 기간·같은 지수·같은 비용으로 '동전 던지기 전략'들을 돌려 우리 TWR가
    # 그 분포의 몇 %에 드는지 잰다(날짜 시드 → 재현 가능).
    record["random_pctile"] = random_strategy_percentile(
        st["history"] + [record], record["twr_pct"], seed=f"rand:{bar}")
    # last_price를 함께 남긴다 — 내일 이 종목 시세를 못 받으면 이 값으로
    # 평가한다(감사 152). 없으면 매입가로 떨어져 손실이 0으로 보인다.
    st["positions"] = {
        p.symbol: {"quantity": p.quantity, "avg_price": p.avg_price,
                   "last_price": marks.get(p.symbol, p.avg_price),
                   "last_price_bar": (
                       str(bar) if p.symbol in prices
                       else (st.get("positions", {}).get(p.symbol, {})
                             .get("last_price_bar")))}
        for p in broker._positions.values() if abs(p.quantity) > 0}
    st.update({"cash": broker.get_cash(), "last_bar": bar})
    st["history"] = cap_history(chrono(st["history"] + [record]))
    atomic_write_json(path, st)

    print(f"[{bar}] 포트폴리오({n}종목 분산) — 자산 {equity:,.2f} "
          f"({record['return_pct']:+.2f}%) · 총노출 {gross:.0%}"
          + (f" · 스킵 {len(skipped)}종목" if skipped else ""))
    return record


def run_daily_paper_all(targets=None, **kwargs) -> dict:
    """AUTO_TARGETS 전체를 순회 페이퍼 운용한다 — 한 종목 실패가 나머지를 안 막는다.

    전 종목이 실패했을 때만 예외를 올린다(조기 경보). 반환에 성공/실패 요약.
    """
    from quant.markets import AUTO_TARGETS
    targets = targets or AUTO_TARGETS

    ok, failed, records = [], {}, {}
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            records[key] = run_daily_paper(market, symbol, **kwargs)
            ok.append(key)
        except Exception as exc:  # noqa: BLE001
            failed[key] = str(exc)
            log.warning("페이퍼 실패 %s: %s", key, exc)
            print(f"⚠️ {key}: 페이퍼 실패 — {exc}")
    print(f"\n요약: 성공 {len(ok)} · 실패 {len(failed)}"
          + (f" ({', '.join(failed)})" if failed else ""))
    # 부분 실패를 장부에 남긴다 — 예전에는 20종목 중 19개가 실패해도 잡이
    # 초록이고 콘솔에만 남았다(2026-08-11 감사). 전부 실패해야 예외였다.
    # 사이트·경보가 읽을 수 있게 기록해야 '조용한 절반 마비'가 보인다.
    _write_run_health(kwargs.get("state_dir") or STATE_DIR,
                      "paper", ok, failed)
    if targets and not ok:
        raise RuntimeError(f"전 종목 페이퍼 실패: {failed}")
    return {"ok": ok, "failed": failed, "records": records}


def _write_run_health(state_dir: str, kind: str, ok: list, failed: dict) -> None:
    """새벽 배치의 부분 실패를 장부에 남긴다(사이트·경보가 읽는 재료).

    '전부 실패'만 예외로 올리면 절반이 마비된 날이 성공으로 보인다. 실패한
    종목은 그날 판단·기록이 통째로 없는데도 아무 흔적이 남지 않았다.
    """
    from datetime import date as _date

    from quant.utils.jsonio import atomic_write_json

    path = os.path.join(state_dir, "run_health.json")
    cur: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                cur = json.load(f)
        except (OSError, ValueError):
            cur = {}
    cur[kind] = {"date": _date.today().isoformat(),
                 "ok": len(ok), "failed": len(failed),
                 "failed_keys": sorted(failed)[:20],
                 "errors": {k: str(v)[:200] for k, v in
                            list(failed.items())[:5]}}
    atomic_write_json(path, cur)


def weekly_summary(state_dir: str = STATE_DIR, days: int = 7) -> dict:
    """최근 7일(기록 기준) 요약 — 시장별 수익률·최고/최악일·챔피언 교체 이력.

    기준일은 벽시계가 아니라 '기록의 마지막 날짜'다 — 재실행해도 같은 결과가
    나오고(멱등), 데이터가 없는 날을 오늘로 착각하지 않는다.
    """
    from datetime import date, timedelta

    paper_dir = os.path.join(state_dir, "paper")
    files = (sorted(os.listdir(paper_dir))
             if os.path.isdir(paper_dir) else [])
    markets: dict = {}
    anchor: date | None = None
    states = []
    for name in files:
        if not name.endswith(".json") or is_archive(name):
            continue      # 보관된 옛 장부는 살아 있는 계좌가 아니다(감사 212)
        with open(os.path.join(paper_dir, name), encoding="utf-8") as f:
            st = json.load(f)
        if st.get("history"):
            states.append(st)
            d = date.fromisoformat(st["history"][-1]["date"])
            anchor = d if anchor is None else max(anchor, d)
    if anchor is None:
        return {"period": None, "markets": {}, "swaps": []}
    start = anchor - timedelta(days=days - 1)

    for st in states:
        key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        hist = chrono(st["history"])          # 시간순 전제 — 배열 순서를 믿지 않는다
        window = [r for r in hist if date.fromisoformat(r["date"]) >= start]
        if not window:
            continue
        # 주간 수익 기준점: 창 직전 마지막 기록(없으면 창 첫 기록의 자산)
        idx0 = hist.index(window[0])
        base = hist[idx0 - 1]["equity"] if idx0 > 0 else window[0]["equity"]
        # 입금은 수익이 아니다 — 자산 비율만 쓰면 매칭입금이 주간 수익으로
        # 둔갑한다(2026-08-11 감사에서 발견). TWR과 같은 규칙으로 그날의
        # 유입액을 빼고 구간수익을 연쇄 곱한다. 입금 날짜가 기록일 사이면
        # '그 이후 첫 기록일'에 귀속시킨다.
        # ⚠️ 귀속 규칙을 **여기서 다시 쓰지 않는다**(감사 219). 감사 211에서
        #    "입금은 날짜가 아니라 배치가 찍은 봉(settled_bar)으로 귀속한다"로
        #    바꾸면서 `_flows_by_date` 한 곳에 모았는데, 주간 요약만 자기
        #    복사본을 그대로 갖고 있었다. 그리고 이미 갈라져 있었다 —
        #    실측(입금 08-13 / 정산 봉 08-12):
        #        주간 요약  : +1149.06%   ← 92만원 입금이 '수익'
        #        장부(TWR) :    -0.94%
        #    이 숫자는 월요일 아침 주간 리포트로 나간다.
        flows = _flows_by_date(window, st.get("deposits") or [])
        days_chg = []
        chain = 1.0
        prev = base
        for r in window:
            if prev:
                r_t = (float(r["equity"]) - flows.get(r["date"], 0.0)) / prev - 1
                chain *= 1.0 + r_t
                days_chg.append((r["date"], r_t * 100))
            prev = float(r["equity"])
        week_ret = (chain - 1) * 100 if base else 0.0
        best = max(days_chg, key=lambda x: x[1]) if days_chg else None
        worst = min(days_chg, key=lambda x: x[1]) if days_chg else None
        markets[key] = {
            "week_return_pct": round(week_ret, 2),
            "equity": window[-1]["equity"],
            "total_return_pct": window[-1].get("return_pct"),
            "n_days": len(window),
            "best_day": best and {"date": best[0], "pct": round(best[1], 2)},
            "worst_day": worst and {"date": worst[0], "pct": round(worst[1], 2)},
        }

    swaps = []
    auditions = {"runs": 0, "candidates": 0, "promoted": 0}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not rec.get("asof"):
                    continue
                try:
                    in_window = date.fromisoformat(rec["asof"]) >= start
                except ValueError:
                    continue
                if not in_window:
                    continue
                # 이번 주 오디션 통계 — 몇 명이 도전해 몇 명이 승격했나
                auditions["runs"] += 1
                auditions["candidates"] += int(rec.get("n_candidates") or 0)
                if rec.get("promoted"):
                    auditions["promoted"] += 1
                    swaps.append({"asof": rec["asof"],
                                  "market": rec.get("market"),
                                  "symbol": rec.get("symbol"),
                                  "champion": rec.get("champion"),
                                  "strategy": rec.get("champion_strategy")})

    # 시스템 건강 — 수익률 밖의 상태(판정 시계·체결 가정·킬스위치)를 함께.
    # 주간 요약은 "이번 주 시스템 건강 보고서"다 — 숫자 자랑이 아니라.
    health: dict = {"auditions": auditions}
    gen = _generation_info(state_dir)
    if gen:
        health["generation"] = gen
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            health["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 건강 항목 실패가 요약을 막으면 안 된다
        pass
    for st in states:
        if st.get("market") == "portfolio" and st.get("history"):
            last = st["history"][-1]
            rs = last.get("risk_scale")
            if rs is not None and float(rs) < 1.0:
                health["killswitch"] = {
                    "risk_scale": float(rs),
                    "drawdown_pct": last.get("drawdown_pct")}
    return {"period": [str(start), str(anchor)], "markets": markets,
            "swaps": swaps, "health": health}


def format_weekly(summary: dict) -> str:
    """weekly_summary 결과를 사람이 읽는 한국어 요약으로 만든다(텔레그램/콘솔 공용)."""
    if not summary.get("markets"):
        return "📭 지난주 페이퍼 기록이 없습니다."
    a, b = summary["period"]
    lines = [f"🗓️ 주간 요약 ({a} ~ {b}) — 가상 8마일 챌린지"]
    for key, m in summary["markets"].items():
        sign = "🔺" if m["week_return_pct"] >= 0 else "🔻"
        line = (f"{sign} {key}: 주간 {m['week_return_pct']:+.2f}% · "
                f"자산 {m['equity']:,.0f} (누적 {m['total_return_pct']:+.2f}%)")
        if m.get("worst_day"):
            line += f" · 최악일 {m['worst_day']['date']} {m['worst_day']['pct']:+.2f}%"
        lines.append(line)
    if summary["swaps"]:
        for s in summary["swaps"]:
            lines.append(f"🔁 챔피언 교체: {s['market']}/{s['symbol']} → "
                         f"{s.get('strategy', '')} {s['champion']} ({s['asof']})")
    else:
        lines.append("🏆 챔피언 교체 없음 — 확실히 나은 후보가 없었다는 뜻(정상)")

    # 시스템 건강 보고 — 수익률 밖의 상태를 사이트 안 열어도 알 수 있게
    h = summary.get("health") or {}
    g = h.get("generation")
    if g:
        lines.append(f"🕰 판정 시계: 구조 {g['feature_set']} 관찰 "
                     f"{g['days']}일차/{g['target_days']}일 — 시계가 다 돌기 "
                     f"전의 수익률은 판정 근거가 아닙니다")
    a = h.get("auditions")
    if a and a["runs"]:
        lines.append(f"🎭 오디션: 이번 주 {a['runs']}회 · 후보 "
                     f"{a['candidates']}명 중 승격 {a['promoted']}회")
    fc = h.get("fill_check")
    if fc:
        for mk, r in (fc.get("markets") or {}).items():
            mark = " ⚠️ 가정 초과(백테스트 낙관 의심)" if r["optimistic"] else ""
            lines.append(f"🧾 체결 검증 {mk}: 불리 갭 평균 "
                         f"{r['mean_adverse_bp']:+.1f}bp vs 가정 "
                         f"{r['assumed_bp']:.1f}bp (표본 {r['n']}건){mark}")
    ks = h.get("killswitch")
    if ks:
        lines.append(f"🛡 킬스위치 발동 중: 노출 {ks['risk_scale'] * 100:.0f}%"
                     + (f" (낙폭 {ks['drawdown_pct']}%)"
                        if ks.get("drawdown_pct") is not None else ""))
    lines.append("⚠️ 페이퍼(모의) 운용 — 실제 돈이 아니며 수익 보장이 아닙니다.")
    return "\n".join(lines)


def write_docs_status(state_dir: str = STATE_DIR,
                      docs_path: str = os.path.join("docs", "status.json")) -> dict:
    """state/의 챔피언·페이퍼 기록을 사이트용 status.json 하나로 모은다.

    docs/는 push 때마다 Cloudflare Pages로 자동 배포되므로, 이 파일을 커밋하면
    사용자는 웹사이트만 열어도 매일의 결과를 본다(프로그램 실행 불필요).
    """
    from quant.utils.jsonio import atomic_write_json

    status: dict = {"champions": {}, "paper": {}, "updated": None, "swaps": [],
                    "retrain_recent": [],
                    # 유튜브 라이브 주소 — 저장소 변수(QUANT_LIVE_URL)를 설정하면
                    # 사이트에 '라이브 보러가기' 버튼이 자동으로 나타난다
                    "live_url": os.getenv("QUANT_LIVE_URL") or None}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for line in lines[-400:]:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("promoted"):
                # 사이트 차트의 '챔피언 교체' 마커용 — 진화의 서사를 새긴다
                status["swaps"].append({
                    "date": rec.get("asof"),
                    "key": f"{rec.get('market')}:{rec.get('symbol')}",
                    "strategy": rec.get("champion_strategy")})
        for line in lines[-120:]:
            # 탈락자 아카이브 — 몇 명이 도전해 몇 명이 떨어졌는지 그대로 공개.
            # 다중검정 정직성(운 좋은 승자를 얼마나 걸렀는가)의 시각화 재료.
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            status["retrain_recent"].append({
                "asof": rec.get("asof"),
                "key": f"{rec.get('market')}:{rec.get('symbol')}",
                "promoted": bool(rec.get("promoted")),
                "n_candidates": rec.get("n_candidates"),
                "trials_total": rec.get("trials_total")})
    champ_file = os.path.join(state_dir, "champions.json")
    if os.path.exists(champ_file):
        with open(champ_file, encoding="utf-8") as f:
            status["champions"] = json.load(f)

    paper_dir = os.path.join(state_dir, "paper")
    pf_state = None                       # 통합 계좌 원본(세대별 분해 재료)
    if os.path.isdir(paper_dir):
        for name in sorted(os.listdir(paper_dir)):
            # ⚠️ 보관본을 빼지 않으면 같은 키를 **덮어쓴다**(감사 212).
            #    `portfolio_ALL.pre-krw.json`이 알파벳순으로 뒤라, 새 원화
            #    계좌를 열었는데 사이트는 닫힌 옛 계좌를 계속 보여줬다.
            if not name.endswith(".json") or is_archive(name):
                continue
            with open(os.path.join(paper_dir, name), encoding="utf-8") as f:
                st = json.load(f)
            if st.get("market") == "portfolio":
                pf_state = st
            hist = chrono(st.get("history", []))   # 사이트 차트도 시간순으로
            key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
            # 최대낙폭(MDD) — 수익률만 보여주는 화면은 반쪽짜리 정직이다.
            # 킬스위치와 같은 기준(입금 효과 제거)으로 잰다 — 화면과 브레이크가
            # 다른 숫자를 보면 사장님이 보는 낙폭과 시스템이 반응하는 낙폭이
            # 어긋난다(2026-08-11).
            mdd = max_drawdown_from_index(twr_index(
                hist, st.get("deposits") or [],
                start_cash=float(st.get("start_cash", START_CASH))))
            status["paper"][key] = {
                "start_cash": st.get("start_cash", START_CASH),
                "equity": (hist[-1]["equity"] if hist else st.get("cash")),
                "return_pct": (hist[-1].get("return_pct") if hist else 0.0),
                "mdd_pct": round(mdd * 100, 2),
                "history": hist[-90:],            # 사이트에는 최근 90일이면 충분
            }
            if st.get("market") == "portfolio":   # 8마일 챌린지(8만원 → 1억) 필드
                deposits = st.get("deposits", [])
                sc = float(st.get("start_cash", PORTFOLIO_START_CASH))
                # 자산과 **같은 시점의** 원금만 쓴다(감사 211). 아직 배치가
                # 반영하지 않은 입금을 더하면 그 금액이 그대로 손실로 보인다.
                principal = principal_of(sc, deposits)
                eq_now = float(status["paper"][key]["equity"] or principal)
                status["paper"][key].update({
                    "goal": GOAL_KRW,
                    "principal": round(principal, 2),
                    "pnl": round(eq_now - principal, 2),
                    "twr_pct": time_weighted_return(hist, deposits,
                                                    start_cash=sc),
                    "deposits": deposits[-30:],
                })
                # 접수됐지만 아직 반영 안 된 입금 — 숨기지 않고 밝힌다.
                # 이게 없으면 "92만원 넣었는데 화면이 그대로다"가 된다.
                waiting = pending_deposits(deposits)
                if waiting:
                    status["paper"][key]["pending_deposits"] = waiting
                # 계좌를 다시 연 사실 — 사이트 제목이 이걸 읽어 "언제 왜
                # 새로 시작했는지"를 스스로 말한다(감사 212). 안 내보내면
                # 첫 화면이 옛 이야기를 계속 한다.
                if st.get("restarted"):
                    status["paper"][key]["restarted"] = st["restarted"]
                # 거래내역 — "언제 얼마에 얼마어치를 샀나". 잔고가 '지금'을
                # 말한다면 이쪽은 '어떻게 여기까지 왔나'를 말한다(증권사도
                # 잔고와 거래내역을 따로 둔다). 기록마다 흩어져 있는 체결을
                # 한 줄로 펴서 최근 것부터 싣는다.
                trades = []
                for rec in reversed(hist):
                    for f in rec.get("fills") or []:
                        trades.append({**f, "date": rec.get("date")})
                    if len(trades) >= 60:
                        break
                if trades:
                    status["paper"][key]["trades"] = trades[:60]
                # 종목별 잔고 — 사이트는 비중(%)만 보여주고 있었다. "삼성전자에
                # 얼마"에 답하려면 평단·수량·평가금액이 있어야 한다(2026-08-13).
                # 현금까지 함께 내보내야 합이 자산과 맞아떨어진다.
                status["paper"][key]["currency"] = st.get("currency")
                # 마지막 기록에 남은 적용 환율 — 잔고 표가 "1,412.5원/$ 적용"
                # 이라고 밝힐 수 있어야 검산이 가능하다(감사 216).
                if hist and hist[-1].get("fx_usdkrw") is not None:
                    status["paper"][key]["fx_usdkrw"] = hist[-1]["fx_usdkrw"]
                status["paper"][key]["holdings"] = holdings_view(st, eq_now)
                # ⚠️ 현금도 **자산과 같은 시점**이어야 한다(감사 211이 여기서
                #    한 번 더 나온다). 장부의 cash에는 아직 반영 안 된 입금이
                #    이미 들어 있어서, 그대로 실으면 표의 합이 자산을 넘어선다:
                #        보유 37,341 + 현금 961,910 = 999,251  ≠  자산 79,251
                #    현금 비중이 1213%로 찍히고 표가 스스로 모순된다.
                #    접수분은 빼고 싣는다 — 그 돈은 pending_deposits로 따로
                #    공개되고, 다음 배치가 자산·현금을 함께 다시 잰다.
                status["paper"][key]["cash"] = round(
                    float(st.get("cash") or 0.0)
                    - sum(float(d["amount"]) for d in waiting), 2)
                rb = _regime_breakdown(hist)
                if rb:                             # 레짐별 성과 분해(투명성)
                    status["paper"][key]["regime_breakdown"] = rb
            if hist:
                status["updated"] = max(status["updated"] or "", hist[-1]["date"])

    # 오늘의 시장 브리핑(표시 전용) — 있으면 사이트에도 싣는다
    from quant.live.briefing import load_briefing
    briefing = load_briefing(state_dir)
    if briefing and briefing.get("items"):
        status["briefing"] = briefing

    # 오늘의 거시(FRED, 표시 전용) — 키 없으면 조용히 생략
    try:
        from quant.live.macro_brief import macro_summary
        m = macro_summary()
        if m:
            status["macro"] = m
    except Exception:  # noqa: BLE001 — 브리핑 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 판정 시계 — 현재 구조 세대의 관찰 일수(구조가 바뀌면 0일부터 다시)
    gen = _generation_info(state_dir)
    if gen:
        # 세대별 기록 아카이브 — 이전 구조 기록을 현 구조 실적과 분리(착시 제거)
        if pf_state:
            arch = _generation_archive(pf_state, gen["since"])
            if arch:
                gen["archive"] = arch
        status["generation"] = gen

    # 새벽 배치의 부분 실패 — '전부 실패'만 예외로 올리던 탓에 절반이 마비된
    # 날도 초록으로 보였다. 실패는 숨길 이유가 없다(2026-08-11 감사).
    rh_path = os.path.join(state_dir, "run_health.json")
    if os.path.exists(rh_path):
        try:
            with open(rh_path, encoding="utf-8") as f:
                status["run_health"] = json.load(f)
        except (OSError, ValueError):
            pass

    # 체결 가정 검증(표시 전용) — 실측 개장 갭 vs 백테스트 슬리피지 가정.
    # 실측이 가정보다 불리하면 그 사실이 그대로 사이트에 공개된다.
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            status["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 검증 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 야간 검증(PBO·DSR) 장부 — 과최적화 감시가 사이트·경보로 이어지게
    vpath = os.path.join(state_dir, "validation.json")
    if os.path.exists(vpath):
        try:
            with open(vpath, encoding="utf-8") as f:
                status["validation"] = json.load(f)
        except (OSError, ValueError):
            pass

    # 종목 한글 이름·선정 이유 — 사이트가 코드 대신 이름을 보여줄 수 있게
    from quant.markets import SYMBOL_INFO
    status["symbols"] = SYMBOL_INFO

    atomic_write_json(docs_path, status)
    print(f"🌐 사이트 상태 갱신: {docs_path} (마지막 기록 {status['updated']})")

    # 플래그 파수꾼 — 새로 켜진 자기 고발 플래그(낙관 의심·보정 어긋남·
    # 판정 시계)를 알림 채널(디스코드 등)로도 발송한다. 이미 켜진 건 조용.
    try:
        from quant.live.flag_watch import check_and_notify_flags
        new_flags = check_and_notify_flags(status, state_dir)
        if new_flags:
            print(f"🚩 새 플래그 알림 발송: {', '.join(new_flags)}")
    except Exception:  # noqa: BLE001 — 알림 실패가 사이트 갱신을 막으면 안 된다
        pass
    return status
