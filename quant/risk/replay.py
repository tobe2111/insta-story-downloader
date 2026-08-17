"""위험 재생 — 지난 3년 시장을 **지금의 브레이크 그대로** 다시 지나가 본다.

무엇을 재는가
    수익 엔진이 아니라 **위험 층**이다. 변동성 타깃(연 12%로 노출을 줄이는
    장치)과 킬스위치(낙폭 단계별로 물러나는 장치)가, 2024-08 급락 같은
    실제 위기 구간을 지날 때 설계대로 움직였는지를 잰다.

왜 과거로 이것만 재는가
    전략의 '수익'을 과거로 재면 그 수치는 오염돼 있다 — 지금의 전략은
    과거 데이터를 보고 좋아 보여서 고른 것이라, 같은 과거에서의 성적은
    예측력이 아니라 기억력이다. 그래서 수익 입증은 90일 전방 관찰만 쓴다.
    하지만 **위험 장치는 다르다.** "폭락에서 물러나는가"는 전략 선택과
    독립적인 기계적 성질이라, 과거 위기로 검증하는 것이 정당하고
    실제 기관들이 하는 방식이다(시나리오·위기 재생은 리스크 데스크의 표준).

무엇으로 재는가
    전략 신호 없이 **균등 바스켓**(전 종목 1/n 보유)에 위험 층만 얹는다.
    비교 대상은 같은 바스켓의 '브레이크 없음' 버전 — 차이가 곧 브레이크의
    기여다. 데이터는 그날 배치가 남긴 스냅샷(csv.gz)만 쓴다(재현 가능).

여기서 지키는 것
    ① 브레이크 로직을 **다시 적지 않는다** — 실전이 쓰는 함수를 그대로
       import 한다(vol_scale·_kill_switch_scale·probability_of_ruin).
       복사본을 검증하면 복사본만 안전해진다(FROZEN_IDEAS ①).
    ② 결과는 실측 장부와 **다른 파일**에 산다(docs/risk.json) — 시뮬레이션
       숫자가 실전 성적처럼 읽히는 순간 이 제품의 정체성이 무너진다.

정직한 한계
    · 거래 비용·슬리피지 미반영 — 위험(낙폭·변동성)을 재는 목적이라
      영향이 작지만, 여기 나온 수익 배수를 성과로 읽으면 안 된다.
    · 지금 살아 있는 종목만 들어 있다(생존 편향) — 낙폭은 실제보다
      **얕게** 나올 수 있다. 좋게 읽는 쪽으로 기울어진 오차임을 명시한다.
    · 다루는 구간은 스냅샷이 닿는 범위(약 2023-05~)다. 2020·2022년의
      더 깊은 위기는 데이터가 없어 재생하지 못했다.
"""
from __future__ import annotations

import glob
import gzip
import io
import math
import os

import pandas as pd

from quant.risk.portfolio_vol import VERIFY_TARGET_VOL, vol_scale

# 재생 파라미터 — 실전 배치와 같은 정신: 주 1회 정도 리밸런스, 60일 창.
REB_EVERY = 5          # 며칠마다 변동성 타깃을 다시 맞추는가
VOL_WINDOW = 60        # 사전 변동성 추정에 쓰는 과거 일수
WARMUP = 20            # 종목이 재생에 참여하기 위한 최소 관측 일수


def _kill_switch(prev: float, dd: float) -> float:
    """실전 킬스위치를 그대른 가져온다 — 여기 문턱을 다시 적지 않는다."""
    from quant.live.daily import _kill_switch_scale
    return _kill_switch_scale(prev, dd)


def load_snapshot_closes(root: str = "state/snapshots") -> dict[str, pd.Series]:
    """스냅샷 폴더 전체에서 종목별로 **가장 깊은 역사**를 이어 붙인다.

    같은 종목의 스냅샷이 여러 날짜에 있으면 전부 합쳐 중복 날짜는 최신
    스냅샷 값을 쓴다 — 코인은 2026-03 스냅샷(800봉)과 최근 스냅샷을 이으면
    2023-12까지 닿는다. 스냅샷은 그날 배치가 실제로 본 데이터의 보존본이라
    이 재생은 언제 다시 돌려도 같은 답을 준다.
    """
    frames: dict[str, list[pd.Series]] = {}
    for path in sorted(glob.glob(os.path.join(root, "*", "*.csv.gz"))):
        name = os.path.basename(path)[:-len(".csv.gz")]
        market, _, sym = name.partition("_")
        if market == "kr" or market == "us":          # kr_stock_XXX / us_stock_XXX
            market2, _, sym = sym.partition("_")
            market = f"{market}_{market2}"
        key = f"{market}:{sym.replace('_', '/')}"
        try:
            with gzip.open(path, "rt") as fh:
                df = pd.read_csv(io.StringIO(fh.read()), index_col=0,
                                 parse_dates=True)
        except Exception:  # noqa: BLE001 — 깨진 스냅샷 하나가 재생을 막으면 안 됨
            continue
        if "close" not in df.columns or len(df) < WARMUP:
            continue
        s = df["close"].astype(float)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        frames.setdefault(key, []).append(s)
    out: dict[str, pd.Series] = {}
    for key, parts in frames.items():
        merged = pd.concat(parts)
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        # 날짜 인덱스를 일 단위로 정규화(코인 스냅샷은 시각이 붙어 있다)
        merged.index = pd.DatetimeIndex(merged.index).normalize()
        merged = merged[~merged.index.duplicated(keep="last")]
        out[key] = merged
    return out


def replay_risk_layer(closes: dict[str, pd.Series],
                      target_vol: float = VERIFY_TARGET_VOL) -> dict | None:
    """균등 바스켓 위에 실전 위험 층을 얹고 하루씩 재생한다.

    반환 dict의 두 축:
      raw    — 브레이크 없이 총노출 100%로 그냥 들고 간 바스켓
      braked — 변동성 타깃 × 킬스위치를 매일 적용한 같은 바스켓
    차이가 곧 '브레이크가 위기에서 실제로 한 일'이다.
    """
    if not closes:
        return None
    rets = pd.DataFrame({k: s.pct_change() for k, s in closes.items()})
    rets = rets.iloc[1:]
    if len(rets) < WARMUP * 2:
        return None

    from quant.live.ledger_basics import drawdown_from_index

    eq_raw = eq_br = 1.0
    br_vals: list[float] = []   # 브레이크 계좌의 성장 지수(낙폭은 공용 헬퍼로)
    ks = 1.0                    # 킬스위치 배수(히스테리시스 상태)
    scale = 1.0                 # 변동성 타깃 배수
    ex_est = None
    raw_curve, br_curve, exposure_curve = [], [], []
    episodes: list[dict] = []   # 킬스위치가 물러난 구간들
    open_ep: dict | None = None

    dates = list(rets.index)
    for i, day in enumerate(dates):
        row = rets.iloc[i]
        active = [k for k in rets.columns
                  if rets[k].iloc[:i].notna().sum() >= WARMUP
                  and not math.isnan(row[k])]
        if not active:
            raw_curve.append((day, eq_raw))
            br_curve.append((day, eq_br))
            exposure_curve.append((day, 0.0))
            continue
        w = 1.0 / len(active)

        # 변동성 타깃 — 실전과 같은 함수, 같은 상한(총노출 100%)으로.
        if i % REB_EVERY == 0:
            hist = rets.iloc[max(0, i - VOL_WINDOW):i]
            rmap = {k: [x for x in hist[k].tolist() if not math.isnan(x)]
                    for k in active}
            scale, ex_est = vol_scale({k: w for k in active}, rmap,
                                      target_vol)

        # 킬스위치 — 재생 계좌 자신의 낙폭에 실전 함수를 그대로.
        # 낙폭의 정의도 실전과 같은 헬퍼에서 온다(손으로 다시 적지 않는다).
        dd = drawdown_from_index(br_vals)
        prev_ks = ks
        ks = _kill_switch(ks, dd)
        if ks < 1.0 and prev_ks >= 1.0:
            open_ep = {"from": str(day.date()), "dd_at_trigger": round(dd, 4),
                       "min_scale": ks}
        if open_ep is not None:
            open_ep["min_scale"] = min(open_ep["min_scale"], ks)
            if ks >= 1.0:
                open_ep["to"] = str(day.date())
                open_ep["days"] = (pd.Timestamp(day)
                                   - pd.Timestamp(open_ep["from"])).days
                episodes.append(open_ep)
                open_ep = None

        day_r = float(sum(row[k] for k in active)) * w
        eq_raw *= 1.0 + day_r
        exposure = min(1.0, scale) * ks               # 레버리지 금지선 유지
        eq_br *= 1.0 + day_r * exposure
        br_vals.append(eq_br)
        raw_curve.append((day, eq_raw))
        br_curve.append((day, eq_br))
        exposure_curve.append((day, exposure))

    if open_ep is not None:                            # 재생이 끝날 때까지 열림
        open_ep["to"] = None
        open_ep["days"] = (pd.Timestamp(dates[-1])
                           - pd.Timestamp(open_ep["from"])).days
        episodes.append(open_ep)

    def _stats(curve: list) -> dict:
        s = pd.Series([v for _, v in curve], index=[d for d, _ in curve])
        r = s.pct_change().dropna()
        peak = s.cummax()
        dd = s / peak - 1.0
        under = dd < -0.001
        # 최장 수면하 구간(연속으로 고점 아래에 있던 일수)
        longest = run = 0
        for u in under:
            run = run + 1 if u else 0
            longest = max(longest, run)
        return {
            "final_multiple": round(float(s.iloc[-1]), 4),
            "ann_vol": round(float(r.std() * math.sqrt(252)), 4),
            "mdd": round(float(dd.min()), 4),
            "worst_day": round(float(r.min()), 4),
            "worst_20d": round(float(s.pct_change(20).min()), 4),
            "longest_underwater_days": int(longest),
        }

    br_rets = pd.Series([v for _, v in br_curve]).pct_change().dropna()
    from quant.robustness.ruin import probability_of_ruin
    ruin = probability_of_ruin(br_rets.tolist(), leverage=1.0)

    mean_exp = sum(v for _, v in exposure_curve) / max(1, len(exposure_curve))
    return {
        "kind": "simulation",       # ← 실측이 아니다. 읽는 쪽이 반드시 표시할 것
        "period": {"from": str(dates[0].date()), "to": str(dates[-1].date()),
                   "days": len(dates)},
        "n_symbols": int(rets.shape[1]),
        "target_vol": target_vol,
        "raw": _stats(raw_curve),
        "braked": _stats(br_curve),
        "mean_exposure": round(mean_exp, 4),
        "kill_switch_episodes": episodes,
        "ruin": {"probability": (None if math.isnan(ruin.probability)
                                 else round(float(ruin.probability), 4)),
                 "reason": ruin.reason},
        "honest_limits": [
            "거래 비용·슬리피지 미반영 — 낙폭·변동성 측정 목적. 수익 배수를 성과로 읽지 말 것",
            "지금 살아 있는 종목만 포함(생존 편향) — 낙폭이 실제보다 얕게 나올 수 있음",
            "전략 신호 없는 균등 바스켓 — 위험 층의 검증이지 수익 엔진의 검증이 아님",
            "수익률은 각 종목의 현지 통화 기준 — 환율 변동의 위험이 빠져 있음",
        ],
    }
