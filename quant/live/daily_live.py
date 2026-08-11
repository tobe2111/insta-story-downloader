"""하루 1회 실거래 집행 — 페이퍼와 '같은 결정'을 실제 계좌로 보낸다.

8마일 챌린지의 실거래 전환용 마지막 조각. 결정 재료(챔피언 전략·HAR
사이징·실적 가드·켈리 상한·어드민 설정)는 페이퍼 운용과 동일하고,
주문만 KIS(한국투자증권)로 나간다. 새벽 페이퍼 결정과 나란히 돌리면
"페이퍼 vs 실계좌"의 체결 차이(슬리피지)도 데이터로 남는다.

안전장치(겹겹이):
    1. 기본 모의투자(paper=True) — KIS 모의투자 도메인으로만 주문
    2. 실전(paper=False)은 환경변수 QUANT_LIVE_REAL=1 이 '함께' 있어야 동작
    3. 어드민 trading_paused → 주문 전체 중단
    4. exposure_scale(어드민 노출 배수) 곱 적용
    5. 주문 전 종목당 비중 [0,1] 클립 — 레버리지 절대 금지
    6. 무행동 밴드(5%p/n) — 잔조정 주문의 수수료 누수 차단
    7. 집행 내역은 state/live/kr.json에 기록(감사 추적)

⚠️ 이 코드는 수익을 보장하지 않는다. 페이퍼 검증(TWR vs 벤치마크)이
   충분히 쌓이기 전의 실전 전환은 통계가 아니라 도박이다.
"""
from __future__ import annotations

import os

from quant.live.retrain import STATE_DIR, champion_strategy
from quant.utils.logging import get_logger

log = get_logger("daily_live")


# 지원 증권사 — 어댑터는 quant/broker/에 이미 있고 여기서는 선택만 한다.
# 이름: (필수 환경변수, 생성자). 기본은 환경변수 QUANT_KR_BROKER, 없으면 kis.
KR_BROKER_KEYS = {
    "kis": ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_CANO"],
    "kiwoom": ["KIWOOM_APP_KEY", "KIWOOM_SECRET", "KIWOOM_ACCOUNT"],
}


def make_kr_broker(name: str | None = None, paper: bool = True):
    """증권사 이름(kis | kiwoom)으로 국내주식 브로커를 만든다.

    두 어댑터는 같은 Broker 인터페이스를 구현하므로 집행 코드는 증권사를
    모른다 — 키만 바꾸면 갈아탈 수 있다(증권사 종속 방지).
    """
    name = (name or os.getenv("QUANT_KR_BROKER") or "kis").strip().lower()
    if name == "kis":
        from quant.broker.kr_live import KISBroker
        return KISBroker(paper=paper)
    if name == "kiwoom":
        from quant.broker.kiwoom_live import KiwoomBroker
        return KiwoomBroker(paper=paper)
    raise RuntimeError(
        f"지원하지 않는 증권사: {name!r} — 'kis'(한국투자) 또는 "
        "'kiwoom'(키움) 중 선택하세요 (--broker 또는 QUANT_KR_BROKER).")


def run_daily_live(targets=None, *, paper: bool = True,
                   state_dir: str = STATE_DIR, broker=None,
                   broker_name: str | None = None) -> dict:
    """국내주식 대상 하루 1회 실거래 사이클. 반환: 집행 요약 dict.

    broker 주입은 테스트용(미주입 시 KISBroker). 시장이 열려 있는지는
    호출자(워크플로 스케줄·수동 실행)가 판단한다 — 장 마감 후 주문은
    다음 장 개시가로 체결되는 KIS 규칙을 그대로 따른다.
    """
    from quant.live.daily import (_kelly_cap_from_history, _load_paper,
                                  _rebalance_band_rel,
                                  _paper_path, _risk_for)
    from quant.markets import AUTO_TARGETS
    from quant.utils.settings import load_settings

    targets = [t for t in (targets or AUTO_TARGETS) if t[0] == "kr_stock"]
    if not targets:
        return {"skipped": "kr_stock 대상 없음"}

    if not paper and os.getenv("QUANT_LIVE_REAL") != "1":
        raise RuntimeError(
            "실전(REAL) 모드는 환경변수 QUANT_LIVE_REAL=1 이 함께 필요합니다 "
            "— 플래그 하나의 실수로 실탄이 나가지 않게 하는 이중 안전장치.")

    settings = load_settings()
    if settings["trading_paused"]:
        log.warning("⏸ 어드민 일시정지 — 실거래 주문을 내지 않습니다.")
        return {"skipped": "어드민 일시정지"}
    exposure = float(settings["exposure_scale"])

    if broker is None:
        broker = make_kr_broker(broker_name, paper=paper)

    from quant.data import get_provider
    n = len(targets)
    orders, decisions, skipped = [], {}, []
    for market, symbol in targets:
        try:
            df = get_provider(market).get_ohlcv(symbol, "1d", limit=400)
            if df.empty or df.attrs.get("synthetic_fallback"):
                raise RuntimeError("실데이터 수신 실패")
            from quant.data.krx import attach_krx_flows
            df = attach_krx_flows(df, symbol)
            from quant.data.crossasset import attach_cross_asset
            df = attach_cross_asset(df, market, symbol)

            strat = champion_strategy(market, symbol, state_dir)
            signals = strat.generate_signals(df)
            weight = float(_risk_for(market).size_positions(df, signals).iloc[-1])
            # 페이퍼와 같은 가드: 켈리 상한(그 종목 페이퍼 장부의 OOS 통계)
            kcap = _kelly_cap_from_history(
                _load_paper(_paper_path(market, symbol, state_dir))
                .get("history") or [])
            weight = max(-kcap, min(kcap, weight))
            # 실거래는 롱온리·무레버리지 — 음수(숏)·1 초과는 자르고 노출 배수 적용
            weight = max(0.0, min(1.0, weight)) * exposure
            decisions[symbol] = round(weight, 4)

            code = symbol.split(".")[0]            # KIS PDNO = 6자리 코드
            price = float(df["close"].iloc[-1])
            pos = broker.get_position(code)
            equity = broker.get_cash() + pos.quantity * price
            # 종목 예산 = 총자산의 균등 1/n 슬라이스.
            # ⚠️ 밴드를 종목 수로 나누던 것이 페이퍼에서 일 37% 회전의 원인이었다
            #    (0.05/20 = 0.25% → 사실상 밴드 없음). 페이퍼는 상대 밴드로
            #    고쳤는데 **실거래 경로만 옛 코드로 남아 있었다**(2026-08-11
            #    감사). 실제 수수료를 내는 쪽이 더 오래 방치돼 있던 셈이다.
            #    상대 밴드는 목표 대비 비율이라 슬라이스로 나눠도 촘촘해지지
            #    않고, 실측 체결 비용에 비례해 자동으로 넓어진다.
            order = broker.target_weight(
                code, weight / n, price, equity,
                rebalance_band_rel=_rebalance_band_rel(market, state_dir))
            if order is not None:
                orders.append({"symbol": symbol, "side": order.side,
                               "qty": order.quantity, "price": order.price,
                               "status": order.status,
                               "order_id": order.order_id})
        except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 나머지를 막으면 안 된다
            skipped.append(symbol)
            log.warning("실거래 %s 스킵: %s", symbol, exc)

    summary = {"mode": "모의투자" if paper else "실전",
               "broker": type(broker).__name__,
               "decisions": decisions, "orders": orders, "skipped": skipped,
               "exposure_scale": exposure}
    try:
        import datetime as _dt
        import json
        from quant.utils.jsonio import atomic_write_json
        path = os.path.join(state_dir, "live", "kr.json")
        hist = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                hist = json.load(f).get("history", [])
        hist.append({"date": _dt.date.today().isoformat(), **summary})
        atomic_write_json(path, {"history": hist[-400:]})
    except Exception:  # noqa: BLE001 — 기록 실패가 집행 결과 보고를 막으면 안 된다
        pass
    print(f"[{summary['mode']}] 결정 {len(decisions)}종목 · 주문 {len(orders)}건"
          + (f" · 스킵 {len(skipped)}" if skipped else ""))
    return summary


def check_readiness(paper: bool = True,
                    broker_name: str | None = None) -> list[tuple[str, bool, str]]:
    """실거래 전환 준비 진단 — 주문 없이 (항목, 통과, 설명) 목록을 반환한다."""
    name = (broker_name or os.getenv("QUANT_KR_BROKER") or "kis").strip().lower()
    out: list[tuple[str, bool, str]] = []
    keys = KR_BROKER_KEYS.get(name)
    if keys is None:
        out.append(("증권사 선택", False,
                    f"{name!r} 미지원 — kis(한국투자) | kiwoom(키움)"))
        return out
    label = {"kis": "한국투자(KIS)", "kiwoom": "키움"}[name]
    missing = [k for k in keys if not os.getenv(k)]
    out.append((f"{label} 키 {len(keys)}종(환경변수)", not missing,
                "설정됨" if not missing else f"누락: {', '.join(missing)}"))
    if missing:
        out.append(("인증·잔고", False, "키 등록 후 재시도"))
        return out
    try:
        b = make_kr_broker(name, paper=paper)
        cash = b.get_cash()                    # 인증(토큰)→잔고까지 한 번에 검증
        out.append(("인증·잔고 조회", True, f"예수금 {cash:,.0f}원"
                    + (" (모의투자 계좌)" if paper else " (⚠️ 실전 계좌)")))
    except Exception as exc:  # noqa: BLE001
        out.append((f"{label} 연결", False, str(exc)))
    return out
