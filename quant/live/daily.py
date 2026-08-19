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
    ledger_files,
    live_hit_rate,
    max_drawdown_from_index,
    pending_deposits,
    principal_of,
    settled_deposits,
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
    """decided_bar 이후 첫 봉의 (타임스탬프, 시가). 없으면 (None, None).

    ⚠️ 여기서 돌려주는 시가는 **현지 통화**다. 통합 계좌에 넣기 전에
    반드시 `_to_krw_or_die`를 거쳐야 한다 — 안 거치면 감사 254가 재발한다.
    """
    for ix, r in df.iterrows():
        if str(ix) > bar_ts:
            return str(ix), float(r["open"])
    return None, None


def _to_krw_or_die(market: str, price: float, fx_rate: float | None) -> float:
    """통합 계좌에 들어가는 **모든** 가격이 지나야 하는 단 하나의 문.

    환율을 모르면 1.0으로 때우지 않고 그 종목을 통째로 뺀다 — 때우는 것이
    감사 212가 고친 결함이고, 이 함수를 **안 부르는 것**이 감사 254가
    고친 결함이다. 평가가격과 체결가격이 각자 환산하면 언젠가 한쪽이
    빠지므로, 두 경로가 같은 함수를 부른다(FROZEN_IDEAS ①).
    """
    krw = to_krw(market, float(price), fx_rate)
    if krw is None:
        raise RuntimeError(
            "원/달러를 확인하지 못해 원화로 평가할 수 없다 "
            "(해외 종목은 환산 없이 기록하지 않는다)")
    return krw


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

# 체결가가 평가가격의 몇 배까지 그럴듯한가(감사 254). 하룻밤 갭·액면분할이
# 만들 수 있는 폭보다는 넉넉하고, 통화를 안 바꾼 값(원/달러 ≈ 1,400배)보다는
# 한참 낮다. 이 사이를 벗어나면 시장이 아니라 코드가 만든 숫자다.
FILL_MARK_MAX_RATIO = 5.0

# 요청한 봉 수의 몇 할 아래로 받으면 '덜 받았다'로 보는가(감사 266).
# 거래소 점검·신규 상장으로 몇 봉이 비는 것은 정상이므로 넉넉히 두되,
# okx 폴백이 800봉 요청에 300봉(37%)을 주던 상황은 반드시 걸려야 한다.
BARS_SHORTFALL_RATIO = 0.9


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


def _holidays_for(state_dir: str) -> dict | None:
    """휴장일 달력 — 못 만들면 None(모른다). 실패가 기록을 막지 않는다."""
    try:
        from quant.data.market_calendar import holiday_map
        return holiday_map(state_dir)
    except Exception:  # noqa: BLE001
        return None


def _all_paper_histories(state_dir: str) -> list:
    """전 종목 페이퍼 장부의 history 목록 — 확률대 적중률의 합산 표본 재료.

    종목별 25건 축적에는 한 달 이상 걸리므로, 그때까지는 전 종목 합산으로
    표본을 조기 확보한다(이질성 트레이드오프는 해설 문구에 명시). 포트폴리오
    통합 계좌 파일은 종목 확률이 없으므로 제외. 실패는 빈 목록(해설 재료일
    뿐 — 실패가 기록을 막으면 안 된다).
    """
    out = []
    # 아카이브는 과거 장부의 사본이라 그대로 합치면 같은 표본을 두 번 센다 —
    # 확률대 적중률이 실제보다 촘촘해 보인다(감사 227). 목록은 한 자리에서.
    for pth in ledger_files(state_dir):
        if "portfolio" in os.path.basename(pth).lower():
            continue
        try:
            with open(pth, encoding="utf-8") as f:
                d = json.load(f)
            h = d.get("history")
            # ⚠️ **시장을 함께 싣는다**(감사 247). 이 목록을 쓰는 두 곳(해설의
            #    신뢰도 곡선·확률 경험 보정)은 "다음 세션"으로 짝을 짓는데,
            #    세션이 무엇인지는 시장마다 다르다 — 코인은 매일, 주식은
            #    거래일이다. 시장이 없으면 하루 결측과 주말을 구별할 수 없다.
            if isinstance(h, list) and h:
                out.append((str(d.get("market") or ""), h))
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
        from quant.data.krx import attach_krx_flows, attach_krx_value
        df = attach_krx_flows(df, symbol)
        # 가치(도전자 전용, 2026-08-19) — val_* 이름이라 챔피언 동결 무관.
        df = attach_krx_value(df, symbol)
    from quant.data.crossasset import attach_cross_asset
    df = attach_cross_asset(df, market, symbol)

    path = _paper_path(market, symbol, state_dir)
    st = _load_paper(path)
    last_bar = str(df.index[-1])
    # 종목별 참고 계좌도 같은 규칙 — 시간이 거꾸로 가면 멈춘다(감사 262).
    # 통합 계좌에서만 막으면 같은 사고가 이쪽 장부를 조용히 오염시킨다.
    prev = st.get("last_bar")
    if prev and str(last_bar) < str(prev):
        log.error("%s/%s: 판정 봉이 과거로 갔다 — 기록 %s → 오늘 %s. "
                  "시세가 뒤처졌다는 뜻이라 기록하지 않는다.",
                  market, symbol, prev, last_bar)
        return {"skipped": True, "last_bar": prev, "backwards": str(last_bar)}
    if prev == last_bar:
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

    # ── 검증 게이트를 여기 걸지 **않는** 이유 (2026-08-14, 의도된 경계) ──
    # 실전 배치는 계좌 두 종류를 돌린다:
    #   ① 종목별 참고 계좌(이 함수) — 그 전략이 그 종목에서 어떻게 행동하는지
    #      **재는 계기**다. 켈리 상한·적중률·신뢰도 곡선이 여기서 나온다.
    #   ② 통합 분산 계좌(run_daily_portfolio) — 실제로 돈이 도는 쪽. 공개
    #      챌린지(100만원 → 1억)가 이것이고, 검증 게이트는 **그쪽에** 걸린다.
    #
    # ①에도 게이트를 걸면 순환이 된다: 게이트로 깎인 수익이 장부에 쌓이고,
    # 그 장부에서 뽑은 켈리 상한이 다시 ②의 비중을 정한다. 계기를 그 계기가
    # 재는 대상으로 감쇠시키는 셈이라, "이 전략이 원래 어떻게 행동하는가"를
    # 영영 알 수 없게 된다. 그래서 계기는 감쇠 없이 둔다.
    #
    # ⚠️ 이 경계는 문서에도 그대로 적어야 한다 — README·사이트가 "검증이
    #    비중에 반영된다"고만 말하고 어느 계좌인지 안 밝히면, 종목별 화면을
    #    본 사람은 게이트가 안 걸린 줄 안다.

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
                            pooled_history=_all_paper_histories(state_dir),
                            # 세션 판정에 필요한 것 둘(감사 247) — 이 종목의
                            # 시장과 휴장일 달력. 없으면 안 거른다.
                            market=market,
                            holidays=_holidays_for(state_dir))
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
    # 오늘 기록을 붙이기 **전까지의** 장부로 잰다 — 오늘의 결과는 내일
    # 가격이 나와야 채점된다(미래를 당겨 쓰지 않는다).
    _lh = live_hit_rate(st.get("history") or [])
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
        # ⚠️ 표본만으로는 부족하다(2026-08-14, 사장님 지적 "솔라나 64% n=11").
        #    20종목을 전부 재 봤더니 **19개**의 95% 신뢰구간이 50%를 품고
        #    있었다 — n=81짜리 60%(구간 50~70%)도 그랬다. 그때까지 화면은
        #    n<20일 때만 n을 흐리게 붙였으므로 n=81은 아무 단서 없이 "60%"
        #    라는 단정으로 나가고 있었다. **n이 아니라 구간이 판정한다.**
        #    구간과 판정을 장부에 남겨, 화면이 자기 계산을 시작하지 않게 한다.
        "hit_lo": acc.get("lo"),
        "hit_hi": acc.get("hi"),
        "hit_conclusive": acc.get("conclusive"),
        # ⚠️ **위 적중률은 인샘플이다**(2026-08-14 감사 240). 표본 400봉이
        #    챔피언을 뽑은 오디션(800봉)과 100% 겹치고, 그중 70%는 선발전
        #    구간이다 — 그 챔피언은 그 데이터에서 이겨서 뽑혔다.
        #    아래는 **장부에서만** 잰 값이다. 표본은 작지만 아무도 고르지
        #    않은 구간이라, 둘을 나란히 놓아야 읽는 사람이 속지 않는다.
        "live_hit": _lh.get("hit_rate"),
        "live_hit_n": _lh.get("n"),
        "live_hit_flat": _lh.get("n_flat"),
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
            record["prob_up"], _all_paper_histories(state_dir),
            holidays=_holidays_for(state_dir))
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

# 판정 시계 수정 공지 (2026-08-18, 사장님 결정: "앞으로는 리셋하지 말고
# 모두 개선해줘. 개선하는 것도 과정이니까").
#
# 측정 대상을 재선언한다: '얼어붙은 전략 하나'가 아니라 **개선을 계속하는
# 과정 전체**다. 그래서 구조가 바뀌어도 시계는 리셋되지 않고 계좌 탄생일
# (STRUCTURE_EPOCH)부터 연속으로 흐른다. 대신 정직 장치 세 개가 그 자리를
# 지킨다:
#   ① 모든 변경은 날짜와 함께 **버전 이력**으로 공개된다(versions).
#   ② 과거 기록은 절대 소급 수정하지 않는다.
#   ③ 누적 성적과 구간별 성적을 함께 볼 수 있게 경계 날짜를 남긴다 —
#      옛 성적으로 새 구성을 포장하는 착시를 막는 것은 리셋이 아니라
#      **공개된 경계**다.
# 직전 리셋(2026-08-17) 이틀 뒤, 결과가 쌓이기 전의 수정이라 골대 이동이
# 아니다 — 장중 실험의 30일→90일 수정과 같은 원칙이다.
JUDGEMENT_AMENDED = {
    "on": "2026-08-18",
    "what": "구조 변경 시 시계 리셋 → 연속 시계 + 변경 이력 공개",
    "why": "측정 대상을 '개선하는 과정'으로 재선언(사장님 결정). 결과가 "
           "쌓이기 전의 수정이며, 이후 모든 구조 변경은 리셋 대신 날짜 "
           "박힌 버전 이력으로 공개된다.",
}
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
# ⚠️ 주석이 값보다 오래 살아 있었다: 예전엔 "0.5는 2일 지수평활"이라 적혀
#    있었는데 실제 값은 0.3이었다. 설명이 코드를 설명하지 못하면 그 설명은
#    거짓말이다 — 값이 바뀔 때 함께 고친다.
# 0.3 = 목표에 도달하는 데 대략 나흘(0.30 → 0.51 → 0.66 → 0.76). 확률의
# 하루짜리 떨림은 크게 눌리고, 진짜 추세 전환은 며칠에 걸쳐 반영된다.
SIGNAL_SMOOTH_ALPHA = 0.3
# 대폭 감액 문턱 — 오늘 목표가 어제의 이 비율 이하면 평활 없이 즉시 반영한다
# (감사 230). 0.5 = "절반 이하로 줄이라"는 지시는 떨림이 아니라 결정이다.
SMOOTH_CUT_RATIO = 0.5
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


def is_etf(market: str, symbol: str | None) -> bool:
    """이 종목이 ETF인가 — **호가 단위가 다르다**(2026-08-14).

    KRX는 ETF·ETN 호가 단위가 전 가격대 5원으로 주식과 다르다. 주식 표를
    그대로 적용하면 KODEX 200(97,570원)에 100원 단위를 물려 **20배**를
    씌운다. 표시가 없으면 주식으로 본다 — 그쪽이 비싸게 치는 방향이라
    보수적이지만, 새 ETF를 넣고 표시를 빠뜨리면 그 종목만 조용히 비싸진다.
    `tests/test_the_spread_cannot_be_cheaper_than_a_tick.py`가 운영 종목이
    전부 분류돼 있는지 확인한다.
    """
    if not symbol:
        return False
    from quant.markets import SYMBOL_INFO
    return bool((SYMBOL_INFO.get(f"{market}:{symbol}") or {}).get("etf"))


def measured_cost_model(market: str, state_dir: str = STATE_DIR,
                        models_gap: bool = True, symbol: str | None = None):
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
    base = CostModel.for_market(market, is_etf=is_etf(market, symbol))
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
    # ⚠️ market·is_etf를 함께 옮긴다 — 빠뜨리면 호가 단위 하한이 조용히
    #    사라진다(같은 값을 새 객체로 옮길 때 늘 생기는 종류의 누락).
    return CostModel(fee=base.fee,
                     slippage=base.slippage + (one_way - assumed_one_way),
                     impact_coef=base.impact_coef,
                     short_borrow=base.short_borrow, funding=base.funding,
                     market_impact_coef=base.market_impact_coef,
                     participation_cap=base.participation_cap,
                     market=base.market, is_etf=base.is_etf)


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


# 실측 피처가 며칠 연속 달라져야 '세대가 바뀌었다'로 보는가 (감사 271).
#
# 1로 두면 외부 소스가 하룻밤 흔들릴 때마다 90일 시계가 0으로 돌아가
# **영원히 90일에 못 닿는다.** 크게 두면 진짜 변화가 며칠 묻힌다. 3밤은
# 이 저장소에서 관측된 소스 장애 길이(대개 하루, 길어야 이틀)의 바로 위다.
GEN_CONFIRM_NIGHTS = 3


def _nightly_realized(path: str) -> dict[str, list[tuple[str, frozenset]]]:
    """밤마다 **실제로 붙은** 선택 피처 — 시장별 {시장: [(날짜, 피처집합)]}.

    종목별이 아니라 그 시장 전체의 합집합을 쓴다. 한 종목에서만 소스가
    빠진 것과 그 소스가 통째로 죽은 것은 다른 사건이고, 세대를 가르는 것은
    후자다.

    ⚠️ **시장을 섞어 날짜로만 묶으면 안 된다.** 기록의 날짜(asof)는 그
    종목 데이터의 마지막 봉이라, 같은 밤에 돌아도 코인은 오늘, 주식은
    직전 거래일로 적힌다. 날짜로만 묶으면 하루는 '코인 피처만', 다음
    하루는 '주식 피처만' 붙은 것처럼 보여 구성이 매일 뒤집힌다 — 그러면
    이 장치가 매일 세대 교체를 선언하는 고장난 경보가 된다.

    `features_used`가 없는 옛 기록은 아예 세지 않는다 — '안 적혔다'를
    '아무것도 안 붙었다'로 읽으면, 기록을 시작한 날 없던 변화가 있었던
    것처럼 보인다.
    """
    by_market: dict[str, dict[str, set]] = {}
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            used = r.get("features_used")
            if used is None:
                continue
            a = str(r.get("asof", ""))[:10]
            mkt = str(r.get("market") or "?")
            if len(a) == 10:
                by_market.setdefault(mkt, {}).setdefault(a, set()).update(
                    str(c) for c in used)
    return {m: [(d, frozenset(days[d])) for d in sorted(days)]
            for m, days in by_market.items()}


def _realized_since(nights: list[tuple[str, frozenset]]) -> tuple[str, frozenset] | None:
    """지금의 피처 구성이 **언제부터 유지되고 있나** — (시작일, 피처집합).

    최신 밤에서 과거로 거슬러 가며, 지금과 같은 구성이 나오면 시작일을
    거기까지 늘린다. 다른 구성이 `GEN_CONFIRM_NIGHTS`밤 연속 나오면 거기서
    세대가 끊긴 것으로 본다 — 하루이틀짜리 소스 장애는 건너뛰고, 정말로
    달라진 구간만 경계가 된다.
    """
    if not nights:
        return None
    # 가장 최근 구성이 **며칠째 이어지고 있나.** 아직 확정 문턱을 못 넘었으면
    # 세대 교체를 선언하지 않는다 — 안 그러면 공개 시계가 하룻밤 장애에
    # 0일차로 떨어졌다가 다음 날 45일차로 되돌아온다. 보는 사람에게는 그게
    # 사고로 읽히고, 실제로는 아무 일도 없었던 것이다.
    newest = nights[-1][1]
    run = 0
    for _, fs in reversed(nights):
        if fs != newest:
            break
        run += 1
    current = (newest if (run >= GEN_CONFIRM_NIGHTS or run == len(nights))
               else nights[-run - 1][1])

    since = nights[-1][0]
    gap = 0
    for date, fs in reversed(nights):
        if fs == current:
            since, gap = date, 0
        else:
            gap += 1
            if gap >= GEN_CONFIRM_NIGHTS:
                break
    return since, current


def _realized_tag(features: frozenset) -> str:
    """피처 구성을 짧은 이름표로 — 개수가 같아도 구성이 다르면 달라야 한다."""
    import hashlib
    h = hashlib.sha1("|".join(sorted(features)).encode()).hexdigest()[:4]
    return f"opt{len(features)}:{h}"


def _generation_info(state_dir: str) -> dict | None:
    """현재 구조 세대의 관찰 일수 — 90일 시계를 숨기지 않는다.

    구조(피처·모델·사이징)가 바뀔 때마다 성과 통계의 시계는 사실상 0으로
    리셋된다. 이 사실을 사이트에 명시해, 과거 세대의 기록이 현재 구조의
    실적처럼 읽히는 착시를 막는다.

    세대는 세 축으로 결정된다:
      ① 피처셋(FEATURE_SET) — 무엇을 보겠다고 **선언**했는가
      ② 실행 구조(STRUCTURE_TAG/EPOCH) — 얼마를 어떻게 사고파는가
      ③ 실측 피처 구성 — 그래서 **실제로 무엇을 보고 있었는가** (감사 271)

    ②를 뒤늦게 넣은 이유: 2026-08-11에 사이징(총노출 6.8%→100%)과 회전율
    통제를 크게 바꿨는데, 피처는 그대로라 시계가 리셋되지 않았다. 그러나
    노출이 15배 다른 두 구간의 수익률은 같은 통계가 아니다 — 피처만 세대로
    치는 것은 우리가 세운 원칙의 구멍이었다.

    ③을 넣은 이유는 같은 병의 다른 얼굴이다. ①은 사람이 손으로 적는
    이름표라, 외부 소스가 죽어 피처 3개가 통째로 빠져도 태그는 그대로다.
    실제로 코인 펀딩·미결제약정 3개는 몇 주 동안 하나도 안 붙었고, 그걸
    되살리는 순간 **모델이 보는 것이 달라지는데 시계는 안 멈춘다.** 그러면
    90일 표본은 앞부분(3개 없음)과 뒷부분(3개 있음)이 섞인 채 "한 세대의
    90일"로 발표된다. 우리가 지금까지 잡아 온 것과 정확히 같은 계열의
    구멍이다 — **선언만 돼 있고 실제로는 안 맞는 장치.**

    since = ①이 처음 등장한 날, ②의 마지막 변경일, ③의 마지막 변경일 중
    **가장 나중** 날짜.
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
        # ⚠️ 수정 공지(2026-08-18, JUDGEMENT_AMENDED) — 아래 경계들은 이제
        #    시계를 **리셋하지 않는다.** 시계는 현 계좌 탄생일
        #    (STRUCTURE_EPOCH)부터 연속으로 흐르고, 경계들은 '언제 무엇이
        #    바뀌었나'의 버전 이력(versions)으로 공개된다. 측정 대상이
        #    '얼어붙은 전략'이 아니라 '개선하는 과정'이기 때문이다 —
        #    착시는 리셋이 아니라 공개된 경계 날짜가 막는다.
        versions: list[dict] = []
        if since > STRUCTURE_EPOCH:
            # 피처 선언이 계좌 탄생 뒤에 바뀐 적 있음 — 버전으로 남긴다
            versions.append({"on": since, "axis": "피처 선언",
                             "what": FEATURE_SET})
        since = STRUCTURE_EPOCH
        # 실측 피처 구성의 변경 — 예전엔 시계를 다시 세웠지만, 이제는
        # 버전 이력으로 남긴다(수정 공지). 시장마다 따로 재고, 가장 최근
        # 경계를 '가장 최근 버전'으로 기록한다 — 그날부터 다른 입력을 보는
        # 시스템이라는 사실은 여전히 공개된다. 다만 그것이 시계를 되돌리진
        # 않는다.
        tag = f"{FEATURE_SET}/{STRUCTURE_TAG}"
        info_realized = None
        per_market = {m: _realized_since(nights)
                      for m, nights in _nightly_realized(path).items()}
        per_market = {m: v for m, v in per_market.items() if v}
        if per_market:
            r_since = max(v[0] for v in per_market.values())
            r_feats = frozenset().union(*(v[1] for v in per_market.values()))
            if r_since > STRUCTURE_EPOCH:
                versions.append({"on": r_since, "axis": "실측 피처 구성",
                                 "what": f"확인된 피처 {len(r_feats)}개"})
            tag = f"{tag}/{_realized_tag(r_feats)}"
            info_realized = {
                "since": r_since, "n": len(r_feats),
                "features": sorted(r_feats),
                "confirm_nights": GEN_CONFIRM_NIGHTS,
                "by_market": {m: {"since": v[0], "n": len(v[1])}
                              for m, v in sorted(per_market.items())}}
        # 유니버스 변경도 이력에 싣는다 — 종목 구성이 바뀐 날은 공개된다
        # (리셋 없음, 수정 공지와 같은 원칙).
        try:
            from quant.universe import version_entries
            versions += version_entries(state_dir, after=STRUCTURE_EPOCH)
        except Exception:  # noqa: BLE001 — 표시 재료일 뿐
            pass
        days = (today - _dt.date.fromisoformat(since)).days
        out = {"feature_set": tag,
               "since": since, "days": max(0, days), "target_days": 90,
               # 연속 시계의 정직 장치 — 시계가 도는 동안 무엇이 언제
               # 바뀌었는지. 리셋 대신 이 목록이 착시를 막는다.
               "versions": sorted(versions, key=lambda v: v["on"]),
               "amended": JUDGEMENT_AMENDED,
               "structure": {"tag": STRUCTURE_TAG, "epoch": STRUCTURE_EPOCH,
                             "why": STRUCTURE_WHY}}
        if info_realized:
            out["realized"] = info_realized
        return out
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


# 자산의 몇 배까지는 봐 주는가. **레버리지가 잠겨 있으므로 한 종목·한 건이
# 계좌 전체보다 클 수는 없다** — 1.0이 물리적 상한이고, 반올림·수수료 여유로
# 아주 조금만 더 준다. 여기를 헐겁게 잡으면(예: 1.5) 실측 사고 중
# 비트코인 1.09배짜리를 놓친다 — 그 줄도 화면에 "1,086,327원/배정
# 1,080,408원"으로 그대로 나갔다.
AMOUNT_SANITY_RATIO = 1.02


def amounts_over_equity(equity: float, fills: list | None,
                        lot_priority: dict | None) -> dict:
    """그날 계좌보다 큰 금액을 찾아낸다 (감사 273).

    레버리지가 잠긴 계좌에서 **한 건의 체결이나 한 종목의 예산이 자산 전체를
    넘을 수는 없다.** 넘었다면 시장이 아니라 코드가 만든 숫자이고, 거의 언제나
    통화 환산이 어딘가에서 빠진 것이다(감사 212·254가 그랬다).

    ⚠️ 비중만 보는 검사로는 못 잡는다. 2026-08-15 사고 때 체결 비중은
       0.0878, 그날 총노출은 0.4215 — **비중은 전부 정상 범위**였는데
       금액은 6,361,687원(자산의 6.4배)이었다. 비중과 금액이 다른 통화로
       계산되면 한쪽만 보는 검사는 통과한다.

    반환: {"fills": [...], "lot_priority": [...]} — 넘은 항목만. 없으면 {}.
    """
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        return {}
    if not (eq > 0):
        return {}
    cap = eq * AMOUNT_SANITY_RATIO
    bad: dict = {}
    over = [{"key": f.get("key"), "amount": round(float(f.get("amount") or 0), 2)}
            for f in (fills or [])
            if abs(float(f.get("amount") or 0)) > cap]
    if over:
        bad["fills"] = over
    over = [{"key": k, "spent": round(float((v or {}).get("spent") or 0), 2)}
            for k, v in sorted((lot_priority or {}).items())
            if abs(float((v or {}).get("spent") or 0)) > cap]
    if over:
        bad["lot_priority"] = over
    if bad:
        bad["equity"] = round(eq, 2)
    return bad


def _rejected_rows(broker, kind: str, limit: int = 20) -> list[dict]:
    """브로커가 거부한 주문 중 **그 종류만** 장부용으로 추린다 (감사 264).

    ⚠️ 왜 종류를 나누나. `broker.rejected`에는 서로 다른 사고가 섞여 들어온다.

        현금 부족   {"symbol", "need", "cash"}        — 감사 233
        공매도 한도 {"symbol", "short_over", "allowance"} — 감사 260

    장부는 오랫동안 **모든 줄이 현금 부족이라고 가정하고** `r["need"]`를
    꺼냈다. 그래서 숏이 한 번이라도 거부되면 배치가 `KeyError`로 죽는다 —
    실제로 그렇게 죽는 것을 실행해서 봤다. 그리고 죽지 않았더라도 더 나쁘다:
    증거금 사고가 "현금 부족"이라는 **틀린 이름**으로 경보에 나간다.

    ``kind``에 그 종류를 특정하는 열쇠(``need`` 또는 ``short_over``)를 준다.
    없는 줄은 조용히 건너뛰지 않고 **다른 목록으로 간다** — 어느 쪽에도 안
    담기는 줄이 생기면 그건 새로 생긴 거부 유형이므로, 여기가 아니라
    `unknown` 항목으로 드러난다.
    """
    rows = []
    for r in (getattr(broker, "rejected", None) or []):
        if kind not in r:
            continue
        row = {"key": r.get("symbol")}
        for k, v in r.items():
            if k == "symbol":
                continue
            row[k] = round(float(v), 2) if isinstance(v, (int, float)) else v
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


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


def _smooth_weights(new: dict, prev: dict, alpha: float = SIGNAL_SMOOTH_ALPHA,
                    cut: float = SMOOTH_CUT_RATIO) -> dict:
    """목표 비중을 어제 목표와 지수평활한다 — 마음이 덜 바뀌게.

    확률이 임계값 근처(0.55↔0.62)에서 떠는 것만으로 전 종목이 매매되는 것이
    회전율의 큰 원인이었다. 평활은 그 떨림을 걸러낸다. 다만 **비중을 줄이는
    쪽 신호는 반만 듣지 않는다** — "팔아라"를 반만 듣는 것은 위험 관리가
    아니라 미련이다. 서서히 움직이는 것은 **키울 때**뿐이다.

    ⚠️ 예전에는 그 원칙이 **정확히 0일 때만** 지켜졌다(2026-08-13 감사 230).
    독스트링은 "청산은 즉시, 새로 진입할 때만 서서히"라고 적혀 있는데 코드는
    0이 아닌 모든 변화를 똑같이 평활했다. 실측(alpha=0.3):

        어제 0.500 → 오늘 목표 0.006  ⇒  실제 0.352
        어제 0.500 → 오늘 목표 0.050  ⇒  실제 0.365
        어제 0.500 → 오늘 목표 0.000  ⇒  실제 0.000  (여기서만 지켜졌다)

    즉 전략이 "0.6%만 들고 있어라"라고 말한 날 계좌는 **35%를 들고 있었다.**
    0.006과 0.0은 위험 관리 관점에서 사실상 같은 지시인데, 한쪽만 즉시
    반영됐다. 가드가 있다는 것이 막힌다는 뜻은 아니다 — 문턱이 정확히 0인
    등호였을 뿐이다(감사 198·213과 같은 계열).

    그래서 문턱을 '비율'로 바꾼다: 목표가 어제의 cut배 이하로 줄면 평활
    없이 즉시 반영한다(0은 그 규칙의 극한이다). 작은 떨림에는 여전히
    평활이 걸리므로 회전율 통제라는 원래 목적은 그대로다.
    """
    out = {}
    for k, w in new.items():
        p = float(prev.get(k, 0.0) or 0.0)
        w = float(w)
        if abs(w) < 1e-9:
            out[k] = 0.0                    # 청산 신호는 즉시 반영
        elif abs(p) > 0 and abs(w) <= cut * abs(p):
            out[k] = w                      # 대폭 감액도 즉시 (감사 230)
        elif p and (w > 0) != (p > 0):
            # 방향 전환 — "반대로 가라"는 청산보다 강한 신호다. 지금은 전
            # 전략이 long-only(allow_short=False)라 도달하지 않지만, 숏이
            # 켜지는 날 평활이 **옛 방향에 남게** 만드는 것을 막아 둔다.
            out[k] = w
        else:
            out[k] = alpha * w + (1.0 - alpha) * p
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


def _signal_frame(market: str, df, timeframe: str = "1d", now=None):
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

    ⚠️ **시각도 받는다**(2026-08-13). 안 받으면 이 판정은 벽시계에 매달려
    있어서 검사가 특정 순간을 재현할 수 없다. 실제로 그래서
    `test_signal_frame_measures_with_the_timeframe_it_was_given`이 **하루 중
    21:00 UTC 이후 세 시간 동안만 빨개지는** 검사였다 — 그 창은 하필 야간
    배치(20:15·21:15·22:15·23:45 UTC)가 도는 시간대다. 가끔 빨간 검사는
    "무시해도 되는 것"이 되고, 그러면 진짜 신호도 함께 묻힌다.
    오늘 화면 쪽 `marketOpenish`에 적용한 것과 같은 처방이다.
    운영 호출부는 None을 넘겨 지금까지와 똑같이 동작한다.
    """
    from quant.data.barclock import bar_status
    if len(df) < 2 or bar_status(market, df.index[-1], timeframe, now) is None:
        return df
    return df.iloc[:-1]


# 하루를 여는 데 필요한 최소 봉 완성도. UTC 자정 직후의 코인 봉(완성도
# 0.00x)이 '새 날'을 열지 못하게 하는 값이면 충분하고, 정상 배치 시각의
# 완성도(22:15 UTC → 0.927)와는 멀찍이 떨어져 있어야 한다.
NEW_DAY_MIN_ELAPSED = 0.10          # = UTC 02:24 이전 봉은 하루를 열지 못한다


def judgement_day(last_bars: dict, partial_bars: dict,
                  min_elapsed: float = NEW_DAY_MIN_ELAPSED) -> str:
    """이 배치가 판단한 날짜 — **갓 시작한 봉은 하루를 열지 않는다**.

    포트폴리오 멱등 가드의 열쇠다. 예전에는 그냥 `max(봉 날짜)`였는데,
    코인 일봉은 UTC 자정에 롤오버하므로 **자정을 조금만 넘겨 돌면 새 날이
    열려 버린다**. 2026-08-14에 실제로 그랬다(감사 232):

        예비 배치가 23:15 UTC에 걸려 있었고 Actions가 43분 늦게 띄워
        23:58에 시작 → 자정을 넘긴 시점의 코인 봉(완성도 0.0003)이
        '2026-08-14'을 열었다. 그 기록의 주식은 하루 묵은 봉으로 판단한
        것이고(bar_age us_stock 1 · kr_stock 1), 그러면 **다음 날 정규
        배치는 같은 날짜를 보고 건너뛴다** — 재시도가 다음 날을 선점해
        묵은 판단으로 확정해 버린다.

    그래서 하루의 이름은 **어느 정도 형태를 갖춘 봉**만 정할 수 있게 한다.
    완성된 봉은 `bar_status`가 None을 주므로 `partial_bars`에 없고, 기본값
    1.0으로 취급돼 그대로 하루를 연다(주식이 여기 해당한다).

    ⚠️ 주말을 죽이지 않는다. 정규 시각(22:15 UTC)의 코인 봉 완성도는
       0.927이라 문턱을 한참 넘는다 — 토·일에도 코인은 지금처럼 돈다.
       막히는 것은 오직 '자정 직후'뿐이다.

    한 종목도 문턱을 못 넘는 극단(전 종목이 자정 직후 코인)에서는 원래대로
    최대 날짜를 쓴다 — 판단을 멈추느니 기록을 남기고 `bar_partial`로
    드러낸다.
    """
    if not last_bars:
        raise ValueError("판단할 봉이 없다")
    formed = [str(b)[:10] for k, b in last_bars.items()
              if float(partial_bars.get(k, 1.0)) >= min_elapsed]
    return max(formed) if formed else max(str(b)[:10] for b in last_bars.values())


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
    """통합 계좌(시작 100만원) — 전 종목에 분산해 한 계좌로 운용한다(실전과 가장 유사).

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

    # 규칙 유니버스(2026-08-18) — 스냅샷이 있으면 그 목록, 없으면 기존
    # 고정 목록. 빠진 종목의 장부는 지우지 않는다(기록 보존, 매매만 정지).
    from quant.universe import active_targets
    targets = targets or active_targets(state_dir)

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
    rets_map: dict = {}             # key → 최근 90일 수익률 — 위험 배분 재료
    opt_present: dict = {}          # key → 오늘 붙은 선택 피처 목록(건강 기록용)
    source_fails: dict = {}         # key → {소스: 실패 사유} — '왜 안 붙었나'의 답
    earnings_guards: dict = {}      # key → 발표일 — 실적 가드 발동 흔적
    skipped_why: dict = {}          # key → 스킵 사유(데이터 장애/휴장 구분)
    data_quality: dict = {}         # key → 품질 스캔 결과(갭·스파이크 등)
    sources: dict = {}              # key → 그 종목 시세를 받은 소스(감사 135)
    partial_bars: dict = {}         # key → 결정 봉 완성도(1.0 미만이면 진행 중)
    bars_short: dict = {}           # key → 요청보다 적게 받은 봉 수(감사 266)
    guard_damp: dict = {}           # key → 이벤트 감쇠 계수(실적 가드 등)
    kelly_caps: dict = {}           # key → 최종 비중 상한(부분 켈리)
    # 검증 게이트 — 과최적화 검증(PBO·DSR)을 비중으로 번역한 계수.
    # ⚠️ **판단한 종목 전부**에 대해 채운다. 목록에서 빠진 종목은 감쇠가
    #    1.0이 되어 '측정 안 됨'이 조용히 '통과'가 된다.
    valid_grades: dict = {}         # key → {"grade","scale","why",…}
    valid_damp: dict = {}           # key → 비중 배수(0.0/0.5/1.0)
    pending = st.get("pending") or {}
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            df = get_provider(market).get_ohlcv(symbol, timeframe,
                                                limit=lookback)
            if df.empty or (require_real_data
                            and df.attrs.get("synthetic_fallback")):
                raise RuntimeError("실데이터 없음")
            # **몇 봉으로 판단했는가** (감사 266). 장부는 마지막 봉이 얼마나
            # 묵었는지(bar_age_days)와 얼마나 만들어졌는지(bar_partial)는
            # 남기면서, 정작 **표본이 몇 개였는지**는 남기지 않았다.
            #
            # 그래서 코인 5종목이 요청한 800봉 대신 300봉만 받고 있던 것이
            # 몇 주 동안 안 보였다(거래소 폴백의 1회 응답 상한 — 감사 251).
            # 장부에는 매일 "정상"이라 적혔고, 그 사이 챔피언은 학습창
            # 250봉을 선발 구간 180봉에서 겨루었고 과최적화 지표(BTC PBO
            # 0.78)도 표본 부족의 산물이었다. **받은 양을 안 적으면 덜 받은
            # 것을 알 방법이 없다.**
            got = int(len(df))
            if got < int(lookback * BARS_SHORTFALL_RATIO):
                bars_short[key] = {"asked": int(lookback), "got": got}
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
                from quant.data.krx import (attach_krx_flows,
                                            attach_krx_value)
                df = attach_krx_flows(df, symbol)
                df = attach_krx_value(df, symbol)
            from quant.data.crossasset import attach_cross_asset
            df = attach_cross_asset(df, market, symbol)
            # 오늘 이 종목에 실제로 붙은 선택 피처 — 외부 소스가 죽으면
            # 조용히 줄어드는 것을 장부에 남긴다(같은 fs8 태그로 기록되므로
            # 개수를 함께 남기지 않으면 아무도 모른다)
            from quant.strategies.ml import optional_features_from_df
            opt_present[key] = optional_features_from_df(df)
            # 왜 안 붙었는지 — 부착 함수들이 df.attrs에 남긴 사유를 걷는다.
            # 계측기는 "이 다섯이 빠졌다"까지만 말했고 **왜**는 실행 로그에만
            # 있다가 며칠 뒤 사라졌다. 원인을 좁히려면 사유가 장부에 있어야 한다.
            from quant.data.source_health import source_errors
            errs = source_errors(df)
            if errs:
                source_fails[key] = errs
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
            px_krw = _to_krw_or_die(market, float(df["close"].iloc[-1]),
                                    fx_rate)
            prices[key] = px_krw
            st["base_prices"].setdefault(key, prices[key])
            last_bars[key] = str(df.index[-1])
            bs = bar_status(market, df.index[-1], timeframe)
            if bs:
                partial_bars[key] = bs["elapsed"]
            pend = pending.get(key)
            if pend and pend.get("decided_bar"):
                # ⚠️ **체결가도 원화로 환산한다**(감사 254). 감사 212가 평가
                #    가격만 환산하고 여기를 빼먹어서, 대기 주문은 달러 시가로
                #    체결되고 그 포지션은 원화 종가로 평가됐다 — 같은 종목의
                #    같은 하루가 두 통화로 계산된 셈이다. 2026-08-15에
                #    META를 달러 시가(596.98)로 사서 원화 종가(832,868)로
                #    평가하는 바람에, 100만원 계좌의 자산이 7,249만원으로
                #    찍혔다(+7,150%). 환산이 필요한 곳을 **두 군데에 나눠
                #    적으면 반드시 한 곳이 빠진다** — 그래서 두 곳 모두
                #    같은 한 함수를 부른다.
                fbar, fopen = _first_bar_after(df, pend["decided_bar"])
                opens_after[key] = (
                    (fbar, _to_krw_or_die(market, fopen, fx_rate))
                    if fopen is not None else (None, None))
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

    bar = judgement_day(last_bars, partial_bars)
    # ⚠️ **시간이 거꾸로 가면 멈춘다** (2026-08-16 실전 사고, 감사 262).
    #    멱등 가드는 `==`만 봤다. 그래서 판정일이 **이전 기록보다 과거**로
    #    떨어지면 그대로 통과해 이미 있는 날짜 뒤에 한 줄을 더 붙였다.
    #
    #    실측(2026-08-16 배치): 코인 시세가 165일 묵어(감사 261) 판정일이
    #    2026-08-15 → **2026-08-14**로 뒷걸음쳤고, 장부에 08-14가 두 번
    #    적혔다. 장부 관문이 커밋을 막아 공개되지는 않았지만, 관문이 없었다면
    #    그 기록이 다음 날의 출발 상태가 된다.
    #
    #    같은 봉은 '이미 했다'(정상)이고, 과거로 가는 봉은 '입력이 고장났다'
    #    (사고)다. 둘을 같은 가지에 두면 사고가 정상으로 보인다.
    prev_bar = st.get("last_bar")
    if prev_bar and str(bar) < str(prev_bar):
        log.error("포트폴리오: 판정일이 과거로 갔다 — 기록 %s → 오늘 %s. "
                  "시세 공급이 뒤처졌다는 뜻이라 기록하지 않는다.", prev_bar, bar)
        return {"skipped": True, "last_bar": prev_bar, "backwards": str(bar)}
    if prev_bar == bar:
        log.info("포트폴리오: 같은 봉(%s)에 이미 실행됨 — 건너뜀", bar)
        return {"skipped": True, "last_bar": bar}

    broker = PaperBroker(cash=float(st["cash"]))
    for key, pos in st.get("positions", {}).items():
        if abs(float(pos.get("quantity", 0.0))) > 0:
            broker._positions[key] = Position(
                key, float(pos["quantity"]), float(pos.get("avg_price", 0.0)))
    n = len(targets)

    # ── 검증 게이트 — 과최적화 검증 결과를 실제 비중에 반영한다 ──────────
    # 2026-08-14까지 PBO·DSR은 계산·경보·표시만 했고 **아무것도 막지 않았다.**
    # 문서는 "통과한 전략만 씁니다"라고 말하는 동안 PBO 0.78짜리 종목이 매일
    # 그대로 굴러갔다. 여기서 등급을 비중 배수로 번역하고, _target_w가
    # 킬스위치·변동성 타깃 **뒤에** 곱한다(앞에 두면 스케일러가 되돌려 키운다).
    from quant.live.validation_gate import gate_summary, validation_grades
    valid_grades = validation_grades(
        [f"{m}:{s}" for m, s in targets], state_dir, str(bar)[:10])
    valid_damp = {k: float(g["scale"]) for k, g in valid_grades.items()}
    log.info("%s", gate_summary(valid_grades))
    for key, g in sorted(valid_grades.items()):
        if g["scale"] < 1.0:
            log.warning("검증 게이트 %s → 비중 ×%.2f · %s",
                        key, g["scale"], g["why"])

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
    fill_refused: dict = {}         # key → 왜 체결을 거부했나(감사 254)
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
        # 체결가가 같은 종목의 평가가격과 **자릿수부터** 다르면 그 둘은
        # 같은 통화가 아니다(감사 254). 하룻밤 갭으로는 3배가 날 수 없으니,
        # 이 문턱을 넘는 값은 시장이 아니라 코드가 만든 것이다. 위의 환산이
        # 다시 빠지더라도 여기서 멈춘다 — 선언이 아니라 실제로 막는다.
        mark_px = marks.get(key)
        if mark_px and fopen and not (
                1.0 / FILL_MARK_MAX_RATIO
                <= float(fopen) / float(mark_px) <= FILL_MARK_MAX_RATIO):
            fill_refused[key] = {"open": round(float(fopen), 6),
                                 "mark": round(float(mark_px), 6),
                                 "why": "체결가와 평가가격의 배율이 비상식적 "
                                        "— 통화 환산 누락 의심"}
            log.error("포트폴리오 %s 체결 거부: 시가 %.6f vs 평가 %.6f",
                      key, float(fopen), float(mark_px))
            continue                       # 대기 주문은 남겨 둔다(재시도)
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
        # ⚠️ **주문은 체결이 아니다**(감사 273). 코인 즉시 체결 쪽은 감사 233이
        #    이미 상태를 보게 고쳤는데(아래 `order_log` 루프), **바로 이 짝은
        #    안 고쳤다.** 그래서 현금 부족으로 거부된 주문이 "오늘 얼마에
        #    샀다"로 장부에 남는다.
        #
        #    가정이 아니다. 2026-08-15 장부에 이렇게 남아 있다:
        #        fills: 아마존 매수 24,017.24주 · 6,361,687.93원
        #        cash_short: 아마존 need 6,365,504.94 · cash 677,061.47
        #    **한 주도 안 샀는데** 사이트의 '오늘의 체결' 표는 "아마존 매수"를
        #    보여줬고, 같은 화면의 잔고 표에는 아마존이 없었다.
        _filled = float(getattr(order, "filled_quantity", 0.0) or 0.0)
        if getattr(order, "status", "filled") not in ("filled", "partial") \
                or _filled <= 0:
            log.error("포트폴리오 %s 대기 주문 미체결(%s) — 체결로 적지 않는다",
                      key, getattr(order, "status", "?"))
            pending.pop(key, None)
            continue
        # 요청 수량이 아니라 **실제로 체결된 수량**을 적는다. 부분 체결이
        # 통째로 체결된 것처럼 남으면 금액도 그만큼 부풀려진다.
        fills.append({"key": key, "price": round(fopen, 6), "bar": fbar,
                      "weight": round(float(pend["weight"]) * sl, 4),
                      "side": order.side,
                      "quantity": round(_filled, 10),
                      "amount": round(_filled * float(fopen), 2),
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

    # 배분 사다리(2026-08-19) — 같은 신호·같은 데이터에 배분 방법만 바꾼
    # 가상 계좌 4개를 나란히 굴린다(상대 비교 전용, 본 계좌 판정 미사용).
    # 본 계좌 경로는 이 아래로도 그대로다 — 실험의 어떤 실패도 본 계좌
    # 배치를 죽이면 안 되므로 예외는 삼키고 사유만 남긴다.
    try:
        from quant.live.alloc_ladder import run_alloc_ladder
        run_alloc_ladder(bar=bar, weights=weights, rets_map=rets_map,
                         marks=marks, n_total=n, state_dir=state_dir)
    except Exception as exc:  # noqa: BLE001 — 실험이 본 계좌를 볼모로 못 잡게
        log.warning("배분 사다리 실패(본 계좌 무관): %s", exc)

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

        킬스위치×어드민 배수×변동성 타깃을 곱하고, 이벤트 감쇠(실적 가드)·
        **검증 게이트**·켈리 상한은 **스케일 뒤에** 건다 — 앞에 두면 스케일러가
        되돌려 키워 전부 무효가 된다.

        검증 게이트(valid_damp)는 과최적화 검증(PBO·DSR) 결과를 비중으로
        번역한 값이다. 2026-08-14까지 이 검증은 **경보만 울리고 아무것도 막지
        않았다** — 문서는 "통과한 전략만 씁니다"라고 말하는 동안 PBO 0.78짜리
        종목이 매일 그대로 굴러갔다. quant/live/validation_gate.py 참조.
        """
        eff = (w * eff_scale * vscale * guard_damp.get(key, 1.0)
               * valid_damp.get(key, 1.0))
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
        # ⚠️ **주문 로그는 체결 내역이 아니다**(2026-08-14 감사 233). 여기는
        #    상태를 안 보고 통째로 베끼고 있었다 — 미체결(지정가 open)이나
        #    현금 부족 거부(rejected)가 생기면 **돈이 한 푼도 안 움직인
        #    주문이 장부에 '오늘 얼마에 샀다'로 남는다.** 그 줄은 사이트
        #    거래내역·SNS 캡션·체결비용 표본으로 그대로 흘러간다.
        if getattr(o, "status", "filled") not in ("filled", "partial"):
            continue
        # ⚠️ 상태는 봤는데 **수량은 요청분을 적고 있었다**(감사 273). 부분
        #    체결이면 `quantity`(요청)와 `filled_quantity`(실제)가 다르고,
        #    그 차이만큼 금액이 부풀려진 채로 사이트·캡션·비용 표본에 간다.
        _q = float(getattr(o, "filled_quantity", 0.0) or 0.0) or float(o.quantity)
        fills.append({"key": o.symbol, "price": round(float(o.price), 6),
                      "bar": last_bars.get(o.symbol, ""),
                      "side": o.side,
                      "quantity": round(_q, 10),
                      "amount": round(_q * float(o.price), 2),
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
    # 펀딩비, 한국주식만 KRX 수급) **개수가 아니라 충족률**(붙은 수 ÷ 붙을 수
    # 있는 수)로 잰다. 소스가 죽은 날을 잡아내는 것이 목적이지, 시장별 차이를
    # 결함으로 보는 것이 아니다.
    #
    # ⚠️ 2026-08-14 이전에는 종목별 최대 개수를 전체 목록(17)과 비교했다.
    #    모든 소스가 살아 있어도 한 종목 최대는 9개라, 사이트의 '피처 결손'
    #    경고가 정상일 때도 켜져 있었다 — 항상 켜진 경고등은 꺼진 것과 같다.
    feat_health = None
    if opt_present:
        from quant.strategies.ml import (OPTIONAL_FEATURES,
                                         applicable_optional_features)

        def _applicable(key: str) -> list[str]:
            mkt, _, sym = key.partition(":")
            return applicable_optional_features(mkt, sym)

        best = max((len(v) for v in opt_present.values()), default=0)
        union = sorted({c for v in opt_present.values() for c in v})
        # 붙을 수 있었던 것의 합집합 — '누락'의 올바른 분모. 유니버스에
        # 한국주식이 없으면 x_frgn5는 애초에 붙을 수 없으니 누락이 아니다.
        can = sorted({c for k in opt_present for c in _applicable(k)})
        # 종목별 충족률(붙은 수 / 붙을 수 있는 수) — 시장이 달라도 비교 가능한
        # 유일한 척도. 개수만 보면 코인(최대 8)이 한국주식(최대 9)보다 항상
        # 아파 보인다.
        cov = {k: (len(v) / len(_applicable(k)) if _applicable(k) else 1.0)
               for k, v in opt_present.items()}
        worst_key = min(cov, key=lambda k: (cov[k], k))
        feat_health = {
            # 옛 필드 — 뜻을 바꾸지 않는다(과거 기록과 같은 척도로 읽히도록)
            "optional_max": best,
            "optional_possible": len(OPTIONAL_FEATURES),
            "union": len(union),
            # 새 필드 — 시장별 기대치를 반영한 진짜 분모와 충족률
            "optional_applicable": len(can),
            "coverage": round(len(union) / len(can), 4) if can else 1.0,
            # 분모가 can으로 좁혀졌다(옛 필드지만 뜻이 정확해졌다). 유니버스에
            # 코인만 있는 날 x_frgn5(한국 수급)를 '전 종목 누락'이라 부르면
            # 상시 오경보가 된다. 세 시장이 다 있는 지금은 결과가 같다.
            "missing_everywhere": [c for c in can if c not in set(union)],
            "thinnest": {"key": worst_key,
                         "n": len(opt_present[worst_key]),
                         "applicable": len(_applicable(worst_key)),
                         "coverage": round(cov[worst_key], 4)},
            # 왜 빠졌는가 — 소스별 사유를 '같은 사유끼리' 묶어 남긴다.
            # 20종목치를 그대로 실으면 장부가 부풀고, 정작 원인은 대개
            # 종목마다 같다.
            "why_missing": {
                src: {"reason": reason,
                      "symbols": sorted(k for k, e in source_fails.items()
                                        if e.get(src) == reason)}
                for src, reason in sorted(
                    {s2: r for e in source_fails.values()
                     for s2, r in e.items()}.items())
            } or None,
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
    # ⚠️ **부호를 지우면 숏이 롱으로 보인다** (감사 264). 예전에는 `abs()`라
    #    숏 -0.3과 롱 +0.3이 장부·화면에 똑같이 0.3으로 남았다. 지금은 숏이
    #    링에 없어 값이 늘 양수지만, 켜는 날 화면이 거짓말을 시작한다 —
    #    그리고 그날은 아무도 이 줄을 기억하지 못한다.
    #    회전율(Σ|오늘−어제|)도 부호가 있어야 맞다: +0.3 → -0.3은 회전율
    #    0이 아니라 0.6이다.
    applied = {k: round(v, 4) for k, v in fitted_w.items() if abs(v) > 0}
    # 총노출(gross)과 순노출(net)은 다른 질문이다 — 롱숏이 반반이면 gross는
    # 100%인데 net은 0%(시장 중립)다. gross만 적으면 그 구별이 사라진다.
    net_exposure = sum(fitted_w.values())
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
    # ⚠️ **금액이 계좌보다 클 수 없다** (감사 273). 레버리지가 잠긴 계좌에서
    #    한 건의 체결이나 한 종목의 예산이 자산 전체를 넘으면, 그것은 시장이
    #    아니라 코드가 만든 숫자다 — 거의 언제나 통화 환산이 어딘가에서
    #    빠진 것이다.
    #
    #    이 검사가 없어서 2026-08-15 장부에 이런 숫자가 남았고 사이트가 그대로
    #    보여줬다(자산 997,198원 계좌에서):
    #        체결   아마존 6,361,687.93원   (6.4배)
    #        예산   비앤비 4,501,932.95원   (4.5배 · 네 종목 합계 9.8배)
    #    비중만 보는 검사는 이걸 못 잡는다 — 그 비중들은 전부 정상 범위였다.
    #
    #    **기록을 지우지 않는다.** 지우면 사고가 없었던 것처럼 보인다.
    #    그대로 남기되 `impossible_amounts`로 표시해, 화면이 그 숫자를
    #    사실처럼 말하지 않게 한다.
    impossible = amounts_over_equity(equity, fills, lot_priority)
    if impossible:
        log.error("금액이 계좌(%s원)를 넘는다 — 통화 환산 누락 의심: %s",
                  f"{equity:,.0f}", impossible)
    record = {"date": bar, "price": round(idx, 2), "weight": round(gross, 4),
              "equity": round(equity, 2),
              "return_pct": round((equity / principal - 1) * 100, 2),
              "principal": round(principal, 2),
              "pnl": round(equity - principal, 2),
              "hit_rate": None,
              "fills": fills,                      # 체결 현실성: 시가·즉시 체결 내역
              # 계좌보다 큰 금액이 이 기록에 있다는 표식(감사 273) — 숫자는
              # 지우지 않고, 화면이 그것을 사실처럼 말하지 못하게 한다.
              "impossible_amounts": impossible or None,
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
              # 검증 게이트의 흔적 — 어느 종목이 왜 깎였는지. 감쇠가 걸린
              # 종목만 남긴다(전부 통과한 날은 조용). 이게 없으면 "왜 오늘
              # BTC를 안 샀나"에 장부가 답하지 못한다.
              "validation_gate": {
                  k: {"grade": g["grade"], "scale": g["scale"],
                      "pbo": g["pbo"], "dsr": g["dsr"], "why": g["why"]}
                  for k, g in sorted(valid_grades.items())
                  if g["scale"] < 1.0} or None,
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
              # 현금이 모자라 브로커가 **거부한** 주문(감사 233). 지금 구조
              # 에서는 나오면 안 되는 값이다 — 레버리지 금지선·수수료
              # 버퍼·매도 우선 순서가 셋 다 막고 있다. 그래서 여기 숫자가
              # 찍히면 그 셋 중 하나가 새고 있다는 뜻이고, 계좌는 이유 없이
              # 작아진 채로 굴러간다. 조용히 덜 사는 것을 장부에 드러낸다.
              # 순노출 — 숏이 켜지면 gross와 갈린다(감사 264).
              "net_weight": round(net_exposure, 4),
              # ⚠️ **거부에는 두 종류가 있다**(감사 264). 여기는 오랫동안
              #    `broker.rejected`의 모든 줄이 현금 부족이라고 가정하고
              #    `r["need"]`를 그대로 꺼냈다. 감사 260이 공매도 한도
              #    거부(`short_over`)를 같은 목록에 넣으면서, 숏이 한 번이라도
              #    거부되는 순간 **배치 전체가 KeyError로 죽는다.**
              #    실행해서 찾았다 — 소스만 읽었으면 두 줄이 같은 목록을
              #    쓴다는 사실이 보이지 않는다.
              "cash_short": _rejected_rows(broker, "need") or None,
              # 증거금 없이 팔려다 잘린 주문 — 현금 부족과 **다른 사고**다.
              # 같은 이름으로 묶으면 경보가 원인을 잘못 말한다.
              "short_refused": _rejected_rows(broker, "short_over") or None,
              # 자릿수가 안 맞아 **체결을 거부한** 주문(감사 254). 여기 값이
              # 찍히면 통화 환산이 어딘가에서 다시 빠졌다는 뜻이다.
              "fill_refused": fill_refused or None,
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
              # 요청한 것보다 **적게 받은** 종목(감사 266). 판단의 표본이
              # 몇 개였는지는 성적만큼 중요한 사실이다 — 300봉으로 낸
              # 결론과 800봉으로 낸 결론은 같은 무게가 아니다.
              "bars_short": bars_short or None,
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


PAPER_STALE_SESSIONS = 2
"""이 이상 세션을 놓친 종목은 '주말이라서'로 설명되지 않는다(감사 243).

    코인   2세션 = 이틀 연속 새 봉 없음 (코인은 매일 연다)
    주식   2세션 = 거래일 이틀 연속 없음 (주말·공휴일은 애초에 안 센다)

1세션은 정상이다 — 배치가 그 시장의 마감보다 이르면 한 세션 뒤처진다.
"""


def paper_stale_targets(skipped: list, state_dir: str = STATE_DIR,
                        today: str | None = None,
                        holidays: dict | None = None,
                        threshold: int = PAPER_STALE_SESSIONS) -> dict:
    """건너뛴 종목 중 **주말·휴장으로 설명되지 않는** 것들 → {키: 놓친 세션 수}.

    ⚠️ 이 판정은 이미 있었다 — 그런데 **재학습 배치에만 붙어 있었다**(감사
       243). 돈을 굴리는 쪽인 페이퍼 배치는 `_write_run_health`에 `stale`을
       아예 넘기지 않아, 사이트의 '정체' 경보가 그쪽에서는 영영 울리지 않는
       구조였다. 감사 139(거래소 규격을 아무도 안 물었다)와 같은 계열 —
       만들어 놓고 배선하지 않은 장치.

       그동안 무엇이 가려졌나: 시세 공급이 얼어붙으면 멱등 가드가 매일 조용히
       건너뛴다. 챔피언은 옛 가격으로 계속 돈을 굴리고, 화면의 종목표는
       며칠 전 숫자를 오늘 것처럼 보여준다.
    """
    from quant.data.market_calendar import holiday_map, missed_sessions

    if not skipped:
        return {}
    if holidays is None:
        # ⚠️ 안 실어 보내면 공휴일이 전부 '거래일'로 세어진다 — 실측: 광복절
        #    대체휴일(2026-08-17)이 낀 구간에서 국내주식이 2세션 대신 3세션
        #    밀린 것으로 잡혔다. 즉 **정상 휴장이 장애로 보고된다.**
        holidays = holiday_map(state_dir)
    out: dict[str, int] = {}
    for key in skipped:
        market, _, symbol = str(key).partition(":")
        try:
            with open(_paper_path(market, symbol, state_dir),
                      encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        hist = st.get("history") or []
        last = (hist[-1].get("date") if hist else None) or st.get("last_bar")
        if not last:
            continue
        n = missed_sessions(market, last, today, holidays)
        if n is not None and n > threshold:
            out[key] = n
    return out


def run_daily_paper_all(targets=None, **kwargs) -> dict:
    """AUTO_TARGETS 전체를 순회 페이퍼 운용한다 — 한 종목 실패가 나머지를 안 막는다.

    전 종목이 실패했을 때만 예외를 올린다(조기 경보). 반환에 성공/실패 요약.
    """
    # 규칙 유니버스(2026-08-18) — 통합 계좌와 같은 목록을 본다.
    from quant.universe import active_targets
    targets = targets or active_targets(kwargs.get("state_dir", STATE_DIR))

    ok, failed, records, skipped = [], {}, {}, []
    for market, symbol in targets:
        key = f"{market}:{symbol}"
        try:
            records[key] = run_daily_paper(market, symbol, **kwargs)
            # 멱등 가드에 걸린 종목은 '성공'이 아니라 '건너뜀'이다(감사 226).
            (skipped if records[key].get("skipped") else ok).append(key)
        except Exception as exc:  # noqa: BLE001
            failed[key] = str(exc)
            log.warning("페이퍼 실패 %s: %s", key, exc)
            print(f"⚠️ {key}: 페이퍼 실패 — {exc}")
    print(f"\n요약: 성공 {len(ok)} · 건너뜀 {len(skipped)} · 실패 {len(failed)}"
          + (f" ({', '.join(failed)})" if failed else ""))
    # 부분 실패를 장부에 남긴다 — 예전에는 20종목 중 19개가 실패해도 잡이
    # 초록이고 콘솔에만 남았다(2026-08-11 감사). 전부 실패해야 예외였다.
    # 사이트·경보가 읽을 수 있게 기록해야 '조용한 절반 마비'가 보인다.
    _sd = kwargs.get("state_dir") or STATE_DIR
    _write_run_health(_sd, "paper", ok, failed, skipped=skipped,
                      stale=paper_stale_targets(skipped, _sd),
                      stale_unit="거래일")
    # ⚠️ 건너뜀은 실패가 아니다 — 예비(재시도) 크론은 정상적으로 전 종목을
    #    건너뛴다. `not ok`만 보면 그 실행이 매번 잡을 빨갛게 만든다.
    if targets and not ok and not skipped:
        raise RuntimeError(f"전 종목 페이퍼 실패: {failed}")
    return {"ok": ok, "failed": failed, "skipped": skipped,
            "records": records}


def _write_run_health(state_dir: str, kind: str, ok: list, failed: dict,
                      skipped: list | None = None,
                      stale: dict | None = None,
                      stale_unit: str = "일") -> None:
    """새벽 배치의 부분 실패를 장부에 남긴다(사이트·경보가 읽는 재료).

    '전부 실패'만 예외로 올리면 절반이 마비된 날이 성공으로 보인다. 실패한
    종목은 그날 판단·기록이 통째로 없는데도 아무 흔적이 남지 않았다.

    ⚠️ **건너뜀은 통과가 아니다**(2026-08-13 감사 226). 이 규칙은 이미 변이
    시험에 적혀 있는데, 정작 배치 건강 기록에서는 지키지 않고 있었다:
    멱등 가드에 걸려 아무 일도 안 한 종목이 `ok`에 그대로 쌓여, 장부는
    "성공 20 · 실패 0"이라고 말한다. 시세 공급이 얼어붙어 며칠째 같은 봉을
    받고 있어도 화면은 매일 초록이다 — 주말과 구별이 안 된다.

    그래서 세 칸으로 나눈다: **실제로 돈 것(ok) · 실패(failed) ·
    건너뛴 것(skipped)**. 그리고 주말로 설명되지 않는 정체(stale)는 따로
    센다 — 며칠이나 묵었는지는 건너뛴 쪽만 아는 사실이라, 판단한 자리에서
    같이 남긴다.
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
    today = _date.today().isoformat()
    # ⚠️ **하루에 두 번 돈다**(본 크론 + 예비 크론). 그냥 덮어쓰면 나중에 도는
    #    예비 크론이 본 크론의 성적을 지운다 — 예비 크론은 이미 기록된 종목을
    #    정상적으로 전부 건너뛰기 때문에 그 기록은 항상 "성공 0 · 건너뜀 20"
    #    이다(감사 244).
    #
    #    실측(2026-08-14, 커밋 순서대로):
    #        paper   ok=20 skip=0   ← 본 크론이 20종목을 다 돌았다
    #        paper   ok=0  skip=20  ← 예비 크론이 덮어썼다. 이게 화면에 남는다
    #        retrain ok=16 skip=4 → ok=4 skip=16 (08-13, 같은 일)
    #
    #    그래서 **잘 돈 날과 배치가 아예 안 뜬 날이 같은 기록**으로 남는다.
    #    부분 마비를 잡으려고 만든 장부가 정작 자기 자신을 지우고 있었다.
    #
    #    같은 날짜면 종목 단위로 합친다: 오늘 한 번이라도 성공한 종목은 성공,
    #    끝까지 실패한 종목만 실패, 한 번도 안 돈 종목만 건너뜀이다
    #    (건너뜀은 여전히 통과가 아니다 — 감사 226).
    prev = cur.get(kind) or {}
    ok_set, failed_map = set(ok), dict(failed)
    skip_set = set(skipped or [])
    if str(prev.get("date")) == today:
        ok_set |= set(prev.get("ok_keys") or [])
        for k, v in (prev.get("errors") or {}).items():
            failed_map.setdefault(k, v)
        for k in (prev.get("failed_keys") or []):
            failed_map.setdefault(k, "")
        skip_set |= set(prev.get("skipped_keys") or [])
        entry_runs = int(prev.get("runs") or 1) + 1
    else:
        entry_runs = 1
    failed_map = {k: v for k, v in failed_map.items() if k not in ok_set}
    skip_set -= ok_set | set(failed_map)
    entry = {"date": today, "runs": entry_runs,
             "ok": len(ok_set), "failed": len(failed_map),
             "skipped": len(skip_set),
             "ok_keys": sorted(ok_set)[:100],
             "skipped_keys": sorted(skip_set)[:20],
             "failed_keys": sorted(failed_map)[:20],
             "errors": {k: str(v)[:200] for k, v in
                        list(failed_map.items())[:5] if v}}
    if stale:
        entry["stale"] = {k: int(v) for k, v in sorted(stale.items())[:20]}
        entry["max_stale_days"] = int(max(stale.values()))
        # 배치마다 세는 단위가 다르다 — 재학습은 달력 일수, 페이퍼는 거래일
        # (감사 243). 단위를 안 적으면 화면이 둘을 같은 말로 읽는다.
        entry["stale_unit"] = stale_unit
    cur[kind] = entry
    atomic_write_json(path, cur)


def _week_base_principal(st: dict, first_date: str) -> float:
    """계좌가 그 주를 시작할 때 갖고 있던 원금 (감사 241).

    **시작금 그 자체**다. 입금을 여기 더하면 안 된다 — 계좌에 기록이 하나도
    없던 시절의 입금은 필연적으로 첫 기록의 자산에 들어가 있고, 주간 수익
    계산의 `flows`가 그 첫 기록에서 이미 빼 준다. 둘 다 하면 두 번 세는 것이
    되어 **입금이 통째로 손실로 보인다**(실측: -92%).

    시작금을 모르면 첫 기록의 자산으로 물러난다 — 옛 장부는 그 필드가
    없을 수 있고, 그때는 지금까지와 같은 값이 나온다(하위 호환).
    """
    del first_date          # 규칙이 날짜에 의존하지 않는다는 것을 명시
    try:
        base = float(st.get("start_cash"))
    except (TypeError, ValueError):
        return float(st["history"][0]["equity"])
    return base if base > 0 else float(st["history"][0]["equity"])


def _window_return(hist: list, window: list, st: dict) -> tuple[float, list]:
    """구간 수익률(%)과 (날짜, 그날 %) 목록 — **주간 셈은 여기 한 곳에서 한다.**

    ⚠️ 이 셈이 두 벌이었다(감사 246). 텔레그램 주간 리포트는 여기(파이썬),
       공개 주간 아카이브 페이지는 자기 자바스크립트 복사본을 갖고 있었고,
       그 복사본은 아예 **다른 값**을 쓰고 있었다:

           const ret = cur.day_pct != null ? cur.day_pct : ...

       `day_pct`는 **그 주 마지막 날 하루치**다. 열 제목은 "주간 수익률"인데
       매주 마지막 하루를 주간 성적으로 내보내고 있었다. 실측(2026-08-10 주):

           아카이브 페이지  **+0.02%**   ← 08-14 하루치
           사실(원금 대비)  **-0.02%**

       **부호가 반대다.** 감사 241에서 파이썬 쪽을 고쳤는데, 같은 병을 가진
       화면 쪽은 그대로 남아 있었다 — 형제를 안 찾은 자리다(㉞ 같은 판정을
       두 곳에서 쓰면 언젠가 갈라진다).

    규칙(감사 241과 같다):
      · 기준선은 창 직전 마지막 기록. 없으면 **원금**(첫날 손익이 사라지지
        않게).
      · 입금은 수익이 아니다 — 그날 유입액을 빼고 구간수익을 연쇄 곱한다.
      · 입금 귀속은 `_flows_by_date`가 **전체 기록**으로 잡는다.
    """
    idx0 = hist.index(window[0])
    base = (hist[idx0 - 1]["equity"] if idx0 > 0
            else _week_base_principal(st, window[0]["date"]))
    src = hist                  # 귀속은 창이 아니라 **전체 기록**(감사 241)
    flows = _flows_by_date(src, st.get("deposits") or [])
    days_chg: list = []
    chain, prev = 1.0, base
    for r in window:
        if prev:
            r_t = (float(r["equity"]) - flows.get(r["date"], 0.0)) / prev - 1
            chain *= 1.0 + r_t
            days_chg.append((r["date"], r_t * 100))
        prev = float(r["equity"])
    return ((chain - 1) * 100 if base else 0.0), days_chg


def _monday_of(day: str) -> str:
    """그 날짜가 속한 주의 월요일(ISO) — 화면과 배치가 같은 주 경계를 쓴다."""
    from datetime import date, timedelta

    d = date.fromisoformat(str(day)[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def weekly_archive(state_dir: str = STATE_DIR, weeks: int = 52) -> dict:
    """주 단위 아카이브 — 계좌별 {월요일: {수익률·자산·입금}} (감사 246).

    공개 주간 아카이브 페이지가 읽는 재료다. **페이지는 이제 계산하지 않고
    읽기만 한다** — 같은 판정을 두 곳에서 하면 언젠가 갈라지고, 실제로
    갈라져 있었다(위 `_window_return` 참고).
    """
    from datetime import date

    out: dict = {}
    for path in ledger_files(state_dir):
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        hist = chrono(st.get("history") or [])
        if not hist:
            continue
        key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        deposits = st.get("deposits") or []
        by_week: dict = {}
        for r in hist:
            by_week.setdefault(_monday_of(r["date"]), []).append(r)
        rows: dict = {}
        for wk in sorted(by_week)[-weeks:]:
            window = by_week[wk]
            ret, _ = _window_return(hist, window, st)
            dep = 0.0
            for d in deposits:
                when = d.get("settled_bar") or d.get("date")
                try:
                    if _monday_of(when) == wk:
                        dep += float(d.get("amount") or 0.0)
                except (TypeError, ValueError):
                    continue
            rows[wk] = {"return_pct": round(ret, 2),
                        "equity": window[-1].get("equity"),
                        "deposit": round(dep, 2) or None,
                        "n_days": len(window)}
        if rows:
            out[key] = rows
    del date
    return out


def weekly_summary(state_dir: str = STATE_DIR, days: int = 7) -> dict:
    """최근 7일(기록 기준) 요약 — 시장별 수익률·최고/최악일·챔피언 교체 이력.

    기준일은 벽시계가 아니라 '기록의 마지막 날짜'다 — 재실행해도 같은 결과가
    나오고(멱등), 데이터가 없는 날을 오늘로 착각하지 않는다.
    """
    from datetime import date, timedelta

    markets: dict = {}
    anchor: date | None = None
    states = []
    # 보관된 옛 장부는 살아 있는 계좌가 아니다(감사 212) — ledger_files가 뺀다
    for path in ledger_files(state_dir):
        with open(path, encoding="utf-8") as f:
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
        # 주간 수익 기준점: 창 직전 마지막 기록.
        #
        # ⚠️ **직전 기록이 없으면 원금이 기준이다**(2026-08-14 감사 241).
        #    예전에는 `window[0]["equity"]`, 즉 **첫 기록 자기 자신**을 기준
        #    으로 삼았다. 그러면 첫날 수익이 항상 0이 되고, 계좌가 문을 연
        #    첫 주의 성적에서 첫날의 움직임이 통째로 빠진다.
        #
        #    실측(원화 계좌 첫 주, 원금 1,000,000원):
        #        기록      999,635.06 → 999,847.15
        #        리포트    주간 **+0.02%** · 최악일 08-13 **+0.00%**
        #        사실      주간 **-0.0153%** · 최악일 08-13 **-0.0365%**
        #    **부호가 반대다.** 이 리포트는 월요일 아침 텔레그램으로 나간다.
        #
        #    감사 239(낙폭이 원금을 고점으로 안 친다)와 **같은 병**이다 —
        #    기준선에서 원금이 빠지면 첫날 손실이 사라진다.
        #
        #    창 시작 **전에** 정산된 입금은 그때 이미 자산에 들어가 있으므로
        #    기준에 더한다. 창 **안에서** 정산된 입금은 아래 `flows`가 따로
        #    빼므로 여기서 더하면 두 번 세는 것이 된다.
        # 이 셈은 `_window_return`이 한 곳에서 한다(감사 246) — 주간 아카이브
        # 페이지가 자기 복사본을 갖고 있다가 갈라진 자리다.
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
        # ⚠️ 귀속은 **전체 기록**으로 잡는다(감사 241). 창만 넘기면 창보다
        #    오래된 입금이 "창 첫 기록"으로 끌려와 그 주의 수익에서 빠진다 —
        #    그 돈은 이미 창 이전 자산에 들어가 있으므로 두 번 빼는 것이다.
        #    실측: 시작금 8만 + 08-01 입금 92만인 계좌의 첫 주가 **-92%**.
        week_ret, days_chg = _window_return(hist, window, st)
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
    # vacuous = **대결이 열리지 않은** 오디션. '승격 0회'와 전혀 다른 상태다 —
    # 후보가 못 이긴 것이 아니라 비교 자체가 성립하지 않은 것이다. 이 숫자는
    # 사이트(retrain_recent)에는 실려 있었지만 **주간 보고서에는 없었다**.
    # 사장님에게 실제로 도착하는 문서가 그 구별을 못 하면 없는 것과 같다.
    auditions = {"runs": 0, "candidates": 0, "promoted": 0, "vacuous": 0}
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
                if rec.get("vacuous"):
                    auditions["vacuous"] += 1
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
    # 굴린 자본 — **자산이 아니라 노출**. 100만원을 1억으로 만들겠다면서
    # 자본의 절반이 늘 현금이면 그 사실이 매주 눈에 보여야 한다. 이 숫자는
    # 장부에 계속 있었지만(`weight`) 어떤 보고서도 읽지 않았다.
    for st in states:
        if st.get("market") == "portfolio" and st.get("history"):
            w = [float(r["weight"]) for r in chrono(st["history"])[-days:]
                 if r.get("weight") is not None]
            if w:
                health["deployed"] = {
                    "gross_mean": round(sum(w) / len(w), 4),
                    "gross_last": round(w[-1], 4),
                    "n_days": len(w),
                }
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
    lines = [f"🗓️ 주간 요약 ({a} ~ {b}) — 가상 100만 챌린지"]
    for key, m in summary["markets"].items():
        # ⚠️ **화살표는 화면에 찍히는 숫자와 같은 값을 봐야 한다**
        #    (감사 241에서 함께 발견). 예전에는 원본 값의 부호를 썼는데,
        #    파이썬의 음의 0(-0.0)은 `>= 0`이 참이면서 `+.2f`로는 "-0.00"
        #    으로 찍힌다. 실제로 그렇게 나갔다 — "🔺 QQQ: 주간 -0.00%".
        #    화면이 스스로 모순되면 나머지 숫자도 함께 의심받는다.
        shown = round(m["week_return_pct"], 2) + 0.0    # -0.0 → 0.0
        sign = "🔺" if shown > 0 else ("🔻" if shown < 0 else "➖")
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
        # '승격 0회'는 정상일 수 있지만 '대결이 안 열림'은 절대 정상이 아니다.
        if a.get("vacuous"):
            lines.append(f"   ⚠️ 그중 {a['vacuous']}회는 **대결 자체가 열리지 "
                         "않았습니다** — 승격 없음이 아니라 심사 없음입니다")
    dep = h.get("deployed")
    if dep:
        lines.append(
            f"💰 굴린 자본: 평균 {dep['gross_mean']:.0%} · 최근 "
            f"{dep['gross_last']:.0%} (나머지는 현금 · {dep['n_days']}일 기준)")
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
                # 공회전 표식 — 후보 대부분이 챔피언과 같은 신호라 대결이
                # 성립하지 않은 날. 이게 없으면 '이긴 후보가 없었다'(정상)와
                # '아무것도 비교하지 못했다'(고장)가 화면에서 같아 보인다.
                "vacuous": bool(rec.get("vacuous")),
                "inert": len(rec.get("inert_candidates") or []),
                "trials_total": rec.get("trials_total")})
    champ_file = os.path.join(state_dir, "champions.json")
    if os.path.exists(champ_file):
        with open(champ_file, encoding="utf-8") as f:
            status["champions"] = json.load(f)

    # 실효 독립 베팅 수 — 2026-08-18 외부 검토 ①: "종목 수가 아니라
    # 실제로 몇 개의 독립 베팅인지 공개하라". 진단 전용이며 사이징에는
    # 반영하지 않는다(구조 동결). 실패는 None — 진단이 기록을 막으면 안 된다.
    try:
        from quant.risk.effective_bets import effective_bets
        status["diversification"] = effective_bets(state_dir)
    except Exception:  # noqa: BLE001
        status["diversification"] = None

    # 배분 사다리(2026-08-19) — 같은 신호에 배분 방법만 바꾼 가상 계좌들.
    # 상대 비교 전용 실험이라 본 계좌 판정에는 쓰지 않고, 주의 문구가
    # 요약(note)에 함께 실린다. 실패는 None — 실험이 기록을 막으면 안 된다.
    try:
        from quant.live.alloc_ladder import ladder_public
        status["alloc_ladder"] = ladder_public(state_dir)
    except Exception:  # noqa: BLE001
        status["alloc_ladder"] = None

    # 실험 판정 기준의 사전 등록(2026-08-19) — 골대 이동 방지. 판정일·통계·
    # 문턱이 데이터보다 먼저 공개돼 있어야 몇 달 뒤의 판정이 의심받지 않는다.
    try:
        from quant.live.prereg import public as _prereg_public
        status["prereg"] = _prereg_public()
    except Exception:  # noqa: BLE001
        status["prereg"] = None

    # 수동 킬스위치 상태 — 사장님이 멈춘 날의 공백이 고장처럼 보이지 않게,
    # "왜 기록이 없는지"를 사이트가 말할 수 있는 재료를 싣는다.
    try:
        from quant.live.manual_halt import status as _halt_status
        status["manual_halt"] = _halt_status(state_dir)
    except Exception:  # noqa: BLE001
        status["manual_halt"] = None

    pf_state = None                       # 통합 계좌 원본(세대별 분해 재료)
    # ⚠️ 보관본을 빼지 않으면 같은 키를 **덮어쓴다**(감사 212).
    #    `portfolio_ALL.pre-krw.json`이 알파벳순으로 뒤라, 새 원화
    #    계좌를 열었는데 사이트는 닫힌 옛 계좌를 계속 보여줬다.
    for path in ledger_files(state_dir):
        with open(path, encoding="utf-8") as f:
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
        # 규칙 유니버스에서 빠진 종목 표식(2026-08-18) — 장부는 남기되,
        # "왜 이 종목만 기록이 멈췄나"가 고장으로 읽히지 않게 사실을 싣는다.
        try:
            from quant.universe import active_targets
            _act = {f"{m}:{s}" for m, s in active_targets(state_dir)}
            if st.get("market") != "portfolio" and key not in _act:
                status["paper"][key]["universe_excluded"] = True
        except Exception:  # noqa: BLE001
            pass
        if st.get("market") == "portfolio":   # 100만 챌린지(100만원 → 1억) 필드
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

    # 주간 아카이브 — **셈은 배치가 하고 페이지는 읽기만 한다**(감사 246).
    # 페이지가 자기 복사본으로 계산하던 시절, 그 복사본은 "주간 수익률" 칸에
    # 그 주 **마지막 하루치**를 넣고 있었다(실측 +0.02% vs 사실 -0.02%).
    try:
        wk = weekly_archive(state_dir)
        if wk:
            status["weekly"] = wk
    except Exception:  # noqa: BLE001 — 집계 실패가 사이트 갱신을 막으면 안 된다
        log.warning("주간 아카이브 집계 실패 — 페이지는 '집계 없음'으로 표시된다")

    # 횡단면 증거 — **같은 설정이 몇 종목에서 통했나**(감사 260).
    # 종목별 오디션은 하루에 표본 1개를 쌓지만 이건 20개를 쌓는다. 실측에서
    # 주식(t=+4.37)과 코인(t=-1.76)이 반대 방향으로 갈렸는데, 종목마다 따로
    # 여는 오디션은 그 사실을 영영 볼 수 없다.
    try:
        from quant.live.crosssection import pooled_evidence
        xs = pooled_evidence(state_dir)
        if xs:
            status["crosssection"] = xs
    except Exception:  # noqa: BLE001 — 관찰 지표 실패가 사이트 갱신을 막지 않는다
        log.warning("횡단면 증거 집계 실패 — 이 칸은 비워 둔다")

    # 체결 가정 검증(표시 전용) — 실측 개장 갭 vs 백테스트 슬리피지 가정.
    # 실측이 가정보다 불리하면 그 사실이 그대로 사이트에 공개된다.
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            status["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 검증 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 장중 감시가 **실제로** 얼마나 자주 돌았나(감사 267). 예약값이 아니라
    # 심장박동에서 잰 값이다. 여기서 status에 실어 두는 이유: 경보를 만드는
    # 쪽(flag_watch)이 파일을 직접 읽으면 그 함수가 **저장소의 지금 상태에
    # 묶인다.** 실제로 그렇게 만들었다가, 감시 기록이 쌓이자 아무 상관 없는
    # 검사들이 "경보 없음"을 확인하지 못하고 무너졌다. 재료는 여기서 모으고
    # 판정은 저기서 한다 — 원래 이 파일들이 나눠 갖던 역할이다.
    try:
        from quant.live.guard import (GUARD_INTERVAL_MINUTES,
                                      observed_gap_median,
                                      observed_gap_minutes)
        _gap = observed_gap_minutes(state_dir)
        if _gap is not None:
            # 최악만 실으면 꼬리 하나가 전체를 설명한다 — 중앙값도 함께
            # 싣는다(감사 285). 한도 계산은 계속 최악값이다(안전 쪽).
            _mid = observed_gap_median(state_dir)
            status["guard"] = {"observed_gap_min": round(float(_gap), 1),
                               "interval_min": GUARD_INTERVAL_MINUTES}
            if _mid is not None:
                status["guard"]["median_gap_min"] = round(float(_mid), 1)
    except Exception:  # noqa: BLE001 — 감시 기록이 없어도 사이트는 갱신된다
        pass

    # 사용자 고정(pin) — 설치형 사용자가 심사와 무관하게 자기 전략을 지정한
    # 종목. 화면이 이 사실을 말하지 않으면, 그 성적이 시스템 심사의 결과처럼
    # 읽힌다(우리 공개 계좌에는 고정이 없어 이 칸은 비어 있다).
    try:
        from quant.live.pin import load_pins
        _pins = load_pins(state_dir)
        if _pins:
            status["pins"] = {k: {"name": v.get("name"),
                                  "since": v.get("since")}
                              for k, v in _pins.items()}
    except Exception:  # noqa: BLE001 — 고정 파일 문제로 사이트가 죽으면 안 된다
        pass

    # 야간 검증(PBO·DSR) 장부 — 과최적화 감시가 사이트·경보로 이어지게
    vpath = os.path.join(state_dir, "validation.json")
    if os.path.exists(vpath):
        try:
            with open(vpath, encoding="utf-8") as f:
                status["validation"] = json.load(f)
        except (OSError, ValueError):
            pass

    # 의석 현황 — "최대 3석 분산 운용"이 지금 실제인가(감사 225).
    # 사이트는 이 구조를 현재형으로 약속하고 있었는데 장부는 전 계좌 1석이다.
    # 판단한 쪽(재학습)이 숫자를 남기고 보여주는 쪽은 읽기만 한다 — 오늘 하루
    # 종일 나온 그 처방을 여기에도 적용한다.
    try:
        from quant.live.parliament import seat_census
        from quant.live.retrain import load_champions
        census = seat_census(load_champions(state_dir))
        if census["accounts"]:
            status["parliament"] = census
    except Exception:  # noqa: BLE001 — 표시 항목 실패가 사이트 갱신을 막으면 안 된다
        pass

    # 휴장일 달력 — **브라우저에도 보낸다**(2026-08-14). 사이트는 파이썬을
    # 못 돌리므로, 배치가 아는 것을 파일로 실어 보내지 않으면 화면은 영영
    # 주말만 아는 상태로 남는다. 그러면 명절 내내 15초마다 시세를 조르고
    # (무료 한도를 아무도 안 보는 날에 태우고), 값이 안 변하는 것이 휴장인지
    # 고장인지 보는 사람도 알 수 없다.
    # 앞으로 60일치만 보낸다 — status.json은 매번 통째로 내려받는 파일이다.
    try:
        from datetime import date as _hdate
        from datetime import timedelta as _htd

        from quant.data.market_calendar import holiday_map
        _hol = holiday_map(state_dir)
        if _hol:
            _from = _hdate.today().isoformat()
            _to = (_hdate.today() + _htd(days=60)).isoformat()
            status["holidays"] = {m: [d for d in days if _from <= d <= _to]
                                  for m, days in _hol.items()}
    except Exception:  # noqa: BLE001 — 표시 항목 실패가 사이트 갱신을 막으면 안 된다
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
