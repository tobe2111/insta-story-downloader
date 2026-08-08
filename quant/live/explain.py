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
    "gk_vol": "GK 변동성(고저가 기반)", "rv_5_60": "실현변동성 비율(5/60일)",
    "x_funding": "펀딩비(포지셔닝 과열도)",
}


def _direction(weight: float) -> str:
    if weight > 0.05:
        return f"매수 {weight:+.0%}"
    if weight < -0.05:
        return f"매도 {weight:+.0%}"
    return "관망 (현금)"


def _feature_note(name: str, value: float) -> str:
    """피처 하나를 '현재값 + 사람이 읽는 상태'로 만든다.

    "주요 판단 재료: gk_vol, MACD"처럼 이름만 나열하면 보는 사람에게 아무
    정보가 없다 — 지금 그 재료가 어떤 상태라서 판단에 쓰였는지를 붙인다.
    """
    ko = FEATURE_KO.get(name, name)
    v = float(value)
    if name in ("rsi14", "rsi7"):                  # 0~1 스케일 → 0~100
        r = v * 100
        state = "과매도권" if r < 35 else "과열권" if r > 65 else "중립"
        return f"{ko} {r:.0f}({state})"
    if name in ("ma_dist20", "ma_dist50"):
        return f"{ko} {v:+.1%}({'선 위' if v > 0 else '선 아래'})"
    if name in ("mom20", "mom60", "ret1", "ret5", "ret10"):
        return f"{ko} {v:+.1%}"
    if name in ("vol", "atr", "gk_vol"):
        return f"{ko} 일 {v:.1%}"
    if name in ("vol_ratio", "rv_5_60"):
        state = ("변동성 확장 국면" if v > 1.2
                 else "변동성 수축 국면" if v < 0.8 else "보통 수준")
        return f"{ko} {v:.2f}({state})"
    if name == "macd_hist":
        return f"{ko} {'+(상승 우위)' if v > 0 else '−(하락 우위)'}"
    if name == "bb_pctb":
        state = ("상단 접근" if v > 0.8 else "하단 접근" if v < 0.2 else "밴드 중간")
        return f"{ko} {v:.2f}({state})"
    if name == "vol_z":
        state = "거래량 급증" if v > 2 else "거래량 급감" if v < -2 else "평소 수준"
        return f"{ko} {v:+.1f}({state})"
    if name.startswith("x_funding"):
        return f"펀딩비 {v:+.3%}({'롱 과열' if v > 0.0005 else '숏 과열' if v < -0.0005 else '중립'})"
    return f"{ko} {v:+.2f}"


def _band_accuracy(history: list, prob: float, band: float = 0.10) -> str:
    """이 종목 장부에서 '오늘과 비슷한 확률대'의 과거 실제 적중률을 찾는다.

    새벽에 기록된 prob_up(t)과 다음 기록의 가격 방향(t+1)을 짝지어, 오늘
    확률 ±band 구간의 실제 상승 비율을 계산한다 — 신뢰도 곡선의 종목판.
    표본이 3일 미만이면 빈 문자열(숫자 놀음 방지).
    """
    pairs = []
    for a, b in zip(history, history[1:]):
        p = a.get("prob_up")
        pa, pb = a.get("price"), b.get("price")
        if p is None or pa in (None, 0) or pb is None:
            continue
        if abs(float(p) - prob) <= band:
            pairs.append(1.0 if float(pb) > float(pa) else 0.0)
    if len(pairs) < 3:
        return ""
    acc = sum(pairs) / len(pairs)
    caveat = " — 표본 적음" if len(pairs) < 10 else ""
    return (f" · 참고: 이 종목에서 모델이 {prob:.0%}±10%p라 말한 최근 "
            f"{len(pairs)}일의 실제 상승 비율 {acc:.0%}{caveat}")


def explain_signal(spec: dict, df, weight: float, strategy=None,
                   raw_weight: float | None = None,
                   history: list | None = None) -> str:
    """전략 스펙 + 데이터 + 산출 비중으로 한국어 근거 문장을 만든다.

    strategy 인스턴스를 주면(직전에 generate_signals를 돌린 것) ML 피처
    중요도 같은 내부 상태까지 활용한다. raw_weight(위험 조절 전 신호 원비중)와
    history(그 종목의 일별 장부)를 주면 사이징 사슬·확률대 과거 적중률까지
    붙인다. 어떤 경우에도 예외를 밖으로 내지 않는다 — 해설 실패가 매매·기록을
    막으면 안 된다.
    """
    try:
        return _explain(spec, df, weight, strategy,
                        raw_weight=raw_weight, history=history)
    except Exception:  # noqa: BLE001
        return f"{_direction(weight)} — 챔피언 전략 신호에 따름"


def _explain(spec: dict, df, weight: float, strategy,
             raw_weight: float | None = None,
             history: list | None = None) -> str:
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
                         getattr(strategy, "base", None),
                         raw_weight=raw_weight, history=history)
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
                         getattr(strategy, "base", None),
                         raw_weight=raw_weight, history=history)
        return f"{inner} · 이벤트 가드: 오늘은 주요 이벤트 없음(매매 허용)"

    if name == "ml":
        thr = float(p.get("threshold", 0.55))
        model = p.get("model", "logreg")
        model_ko = {"logreg": "로지스틱회귀", "rf": "랜덤포레스트",
                    "gb": "그라디언트부스팅", "vote": "앙상블"}.get(model, model)
        # 확률은 모델의 실제 출력(last_proba_)을 우선 사용한다 — 서술과 기록
        # 숫자(prob_up)가 같은 원천에서 나와야 사후 대조가 성립한다.
        # 없을 때만 비중 → 상승확률 역산(proba 사이징 공식의 역)으로 근사.
        real = getattr(strategy, "last_proba_", None)
        gate = thr - 0.5
        span = max(1e-9, 0.5 - gate)
        if real is not None and abs(weight) > 1e-9:
            prob = float(real)
        elif abs(weight) > 1e-9:
            prob = 0.5 + gate + abs(weight) * span
        else:
            prob = None
        # 주요 판단 재료 — 이름만이 아니라 '현재값 + 상태'로. 중요도 상위
        # 3개 피처의 마지막 봉 값을 계산해 사람이 읽는 문장으로 만든다.
        top = ""
        imps = getattr(strategy, "last_importances_", None)
        if imps:
            best = [k for k, _ in
                    sorted(imps.items(), key=lambda kv: -abs(kv[1]))[:3]]
            try:
                from quant.strategies.ml import _features
                vals = _features(df).iloc[-1]
                notes = [_feature_note(k, vals[k]) for k in best if k in vals]
            except Exception:  # noqa: BLE001 — 값 계산 실패 시 이름만이라도
                notes = [FEATURE_KO.get(k, k) for k in best]
            top = " · 판단 재료: " + " / ".join(notes)

        # 사이징 사슬 — 신호 원비중(확률 매핑)과 최종 비중(위험 조절 후)이
        # 다르면 그 과정을 보여준다: "왜 확률은 높은데 비중은 작은가"의 답.
        chain = ""
        if (raw_weight is not None and abs(weight) > 1e-9
                and abs(raw_weight - weight) > 0.02):
            chain = (f" · 사이징: 신호 원비중 {abs(raw_weight):.0%} → "
                     f"변동성 타깃 조절 후 {abs(weight):.0%}")

        # 확률대 과거 적중률 — 오늘과 비슷한 확률을 말했던 날들의 실제 성적.
        # 검증이 확률 서술 바로 옆에 붙어야 과신도 불신도 데이터로 말한다.
        band = _band_accuracy(history or [], prob) if prob is not None else ""

        if prob is not None:
            body = (f"{model_ko} 모델이 내일 상승확률을 약 "
                    f"{prob:.0%}로 추정(기준 {thr:.0%} 초과)")
            # 신호는 났지만 변동성 위험 조절이 비중을 아주 작게 잡은 경우 —
            # '관망'이라고 쓰면 확률 초과 설명과 모순되므로 정확히 말한다.
            if abs(weight) <= 0.05:
                side = "매수" if weight > 0 else "매도"
                return (f"소액 {side} {weight:+.1%} — {body} · 최근 변동성이 "
                        f"커서 위험 조절이 비중을 낮게 잡음{top}{chain}{band}")
            return f"{head} — {body}{top}{chain}{band}"
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
