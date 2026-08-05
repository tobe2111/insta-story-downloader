"""신호 근거 해설 — "오늘 왜 이 방향인가"를 사람 말로 만든다.

일봉 전략의 판단은 하루 1번(새벽)이다. 여기서 만든 문장은 그 시점의 근거이며,
방송·사이트에는 "새벽 판단 기준"으로 시점을 명시해 표시한다 — 장중에 근거가
실시간으로 바뀌는 것처럼 보이게 하면 그건 거짓이다.

⚠️ 이 해설은 '설명'이지 '보장'이 아니다. 모델이 그렇게 판단한 이유를 요약할
뿐, 판단이 맞다는 뜻이 아니다.
"""
from __future__ import annotations

# ML 피처 한글명 — 방송·사이트에서 그대로 노출된다
FEATURE_KO = {
    "ret1": "전일 수익률", "ret5": "5일 수익률", "ret10": "10일 수익률",
    "vol": "변동성(20일)", "vol_ratio": "변동성 레짐(단/장기)",
    "rsi14": "RSI(14)", "rsi7": "RSI(7)",
    "ma_dist20": "20일선 이격", "ma_dist50": "50일선 이격",
    "mom20": "20일 모멘텀", "mom60": "60일 모멘텀",
    "macd_hist": "MACD 히스토그램", "bb_pctb": "볼린저 위치",
    "atr": "평균 진폭(ATR)", "vol_z": "거래량 이상치",
}


def _direction(weight: float) -> str:
    if weight > 0.05:
        return f"매수 {weight:+.0%}"
    if weight < -0.05:
        return f"매도 {weight:+.0%}"
    return "관망 (현금)"


def explain_signal(spec: dict, df, weight: float, strategy=None) -> str:
    """전략 스펙 + 데이터 + 산출 비중으로 한국어 근거 문장을 만든다.

    strategy 인스턴스를 주면(직전에 generate_signals를 돌린 것) ML 피처
    중요도 같은 내부 상태까지 활용한다. 어떤 경우에도 예외를 밖으로 내지
    않는다 — 해설 실패가 매매·기록을 막으면 안 된다.
    """
    try:
        return _explain(spec, df, weight, strategy)
    except Exception:  # noqa: BLE001
        return f"{_direction(weight)} — 챔피언 전략 신호에 따름"


def _explain(spec: dict, df, weight: float, strategy) -> str:
    name = spec.get("strategy")
    p = spec.get("params", {})
    close = df["close"]
    head = _direction(weight)

    if name == "regime_wrap":
        tw = int(p.get("trend_window", 200))
        ma = float(close.rolling(tw).mean().iloc[-1])
        px = float(close.iloc[-1])
        if px < ma:
            return (f"{head} — 레짐 필터: 주가가 {tw}일선 아래(약세 국면) → "
                    "손실 회피를 위해 매매를 멈추고 관망")
        inner = _explain(p.get("inner", {}), df, weight,
                         getattr(strategy, "base", None))
        return f"{inner} · 레짐 필터: {tw}일선 위(매매 허용)"

    if name == "event_wrap":
        from datetime import date as _date

        from quant.events import is_event_day
        pad = int(p.get("pad_days", 1))
        last = df.index[-1]
        d = last.date() if hasattr(last, "date") else _date.today()
        if is_event_day(d, pad):
            return (f"{head} — 이벤트 가드: FOMC 등 예고된 거시 이벤트 창"
                    f"(±{pad}일) → 변동성 위험을 피해 비중 축소/관망")
        inner = _explain(p.get("inner", {}), df, weight,
                         getattr(strategy, "base", None))
        return f"{inner} · 이벤트 가드: 오늘은 주요 이벤트 없음(매매 허용)"

    if name == "ml":
        thr = float(p.get("threshold", 0.55))
        model = p.get("model", "logreg")
        model_ko = {"logreg": "로지스틱회귀", "rf": "랜덤포레스트",
                    "gb": "그라디언트부스팅", "vote": "앙상블"}.get(model, model)
        # 비중 → 대략의 상승확률 역산 (proba 사이징 공식의 역)
        gate = thr - 0.5
        span = max(1e-9, 0.5 - gate)
        prob = 0.5 + gate + abs(weight) * span if abs(weight) > 1e-9 else None
        top = ""
        imps = getattr(strategy, "last_importances_", None)
        if imps:
            best = sorted(imps.items(), key=lambda kv: -abs(kv[1]))[:3]
            top = " · 주요 판단 재료: " + ", ".join(
                FEATURE_KO.get(k, k) for k, _ in best)
        if prob is not None:
            body = (f"{model_ko} 모델이 내일 상승확률을 약 "
                    f"{prob:.0%}로 추정(기준 {thr:.0%} 초과)")
            # 신호는 났지만 변동성 위험 조절이 비중을 아주 작게 잡은 경우 —
            # '관망'이라고 쓰면 확률 초과 설명과 모순되므로 정확히 말한다.
            if abs(weight) <= 0.05:
                side = "매수" if weight > 0 else "매도"
                return (f"소액 {side} {weight:+.1%} — {body} · 최근 변동성이 "
                        f"커서 위험 조절이 비중을 낮게 잡음{top}")
            return f"{head} — {body}{top}"
        return (f"{head} — {model_ko} 모델의 상승확률이 기준({thr:.0%})에 "
                f"못 미쳐 관망{top}")

    if name == "ma_cross":
        f_, s_ = int(p.get("fast", 20)), int(p.get("slow", 60))
        fma = float(close.rolling(f_).mean().iloc[-1])
        sma = float(close.rolling(s_).mean().iloc[-1])
        rel = "위" if fma > sma else "아래"
        trend = "상승 추세 지속" if fma > sma else "하락/횡보 추세"
        return (f"{head} — 이동평균 교차: {f_}일선이 {s_}일선 {rel} "
                f"({trend} 판단)")

    if name == "breakout":
        w_ = int(p.get("window", 55))
        hi = float(df["high"].rolling(w_).max().iloc[-2])
        px = float(close.iloc[-1])
        state = ("최근 돌파 후 추세 추종 중" if weight > 0
                 else f"{w_}일 최고가({hi:,.0f}) 돌파 대기")
        return f"{head} — 채널 돌파: {state}"

    if name == "momentum":
        lb = int(p.get("lookback", 60))
        mom = float(close.pct_change(lb).iloc[-1])
        return (f"{head} — 모멘텀: 최근 {lb}일 수익률 {mom:+.1%} "
                f"({'상승 흐름 추종' if mom > 0 else '흐름 약화 → 축소/관망'})")

    if name == "rsi":
        period = int(p.get("period", 14))
        from quant.strategies.rsi import rsi as _rsi
        val = float(_rsi(close, period).iloc[-1])
        state = ("과매도 반등 노림" if val < 35
                 else "과매수 경계" if val > 65 else "중립 구간")
        return f"{head} — RSI({period})={val:.0f} ({state})"

    return f"{head} — {name} 전략 신호에 따름"
