"""하루 1회 실거래 집행 — 페이퍼와 '같은 결정'을 실제 계좌로 보낸다.

100만 챌린지의 실거래 전환용 마지막 조각. 결정 재료(챔피언 전략·HAR
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

import datetime as _dt
import os

from quant.live.journal import record_order
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


def _harden(broker, *, sleep=None, now=None):
    """실거래 브로커를 RobustBroker로 감싼다 (감사 148).

    ⚠️ **자동으로 매일 도는 이 경로에만 견고화가 빠져 있었다.**

        cli `trade`  (사람이 '실전' 두 글자를 입력)      → RobustBroker ✅
        cli `webhook`(사람이 'yes'를 입력)               → RobustBroker ✅
        `live-daily` (kr-live.yml이 매일 무인 실행)      → 생 KISBroker ❌

    사람이 지켜보는 경로에는 재시도·체결확인·규격검사가 다 있고, **아무도
    안 보는 경로에만 없었다.** 순서가 반대다.

    이 래퍼가 없으면 세 가지가 동시에 빠진다.

        1. 재시도 — HTTP 오류 한 번에 그 종목은 그날 통째로 건너뛴다.
        2. 체결 확인 — KIS 시장가는 접수 응답이 status='accepted',
           filled_quantity=0으로 온다. kr_live.py는 "실제 체결은
           RobustBroker의 confirm_fills가 측정한다"고 적어 두었는데,
           **그 래퍼가 이 경로엔 없어서 아무도 측정하지 않았다.**
           결과: 접수만 되고 한 주도 안 체결된 날도 장부에는 '주문 N건'.
           감사 138이 0주 잘림을 고쳤지만, 접수-미체결은 그대로 남아 있었다.
        3. 규격 — min_qty·qty_step이 0이라 1주 미만도 그대로 내려간다.

    이미 감싼 브로커는 두 번 감싸지 않는다(테스트 주입 포함).
    fill_timeout 90초는 cli `trade`의 주식 설정과 같은 값으로 맞춘다 —
    같은 시장에 다른 규약을 쓰면 그 자체가 다음 결함이다.

    sleep·now는 **검사용 주입구**다. 실제 시계로 두면 미체결 한 건을 확인하는
    데 90초를 그대로 기다리게 되어, 배선을 확인하는 검사가 검사 시간을 분
    단위로 늘린다. 주입 없이 부르면 진짜 시계를 쓴다(운영 경로 무영향).

    운영 쪽 비용도 같은 계산이다: **미체결 종목 하나당 최대 90초**. 국내주식
    대상이 5종목이므로 최악 7분 30초 — 하루 한 번 도는 배치에는 감당할 수
    있는 값이다. 종목이 크게 늘면 이 값을 다시 볼 것(그때는 병렬화가 아니라
    타임아웃을 줄이는 쪽이 맞다 — 90초 안에 안 채워진 시장가는 그날 안
    채워질 가능성이 높다).
    """
    import time as _t

    from quant.broker import RobustBroker

    if isinstance(broker, RobustBroker):
        return broker
    return RobustBroker(broker, retries=3, backoff=2.0,
                        confirm_fills=True, fill_timeout=90.0,
                        fill_poll_interval=3.0,
                        sleep=sleep or _t.sleep, now=now or _t.time)


def _account_equity(broker, prices: dict) -> float:
    """계좌 전체 자산 = 현금 + Σ(보유수량 × 현재가).

    조회가 실패한 종목은 **빼고 센다.** 0으로 치면 그 종목이 사라진 것처럼
    보여 낙폭이 실제보다 크게 잡히고, 킬스위치가 데이터 장애에 반응한다.
    """
    try:
        cash = float(broker.get_cash())
    except Exception:  # noqa: BLE001
        return 0.0
    total = cash
    for symbol, px in prices.items():
        try:
            code = symbol.split(".")[0]
            total += float(broker.get_position(code).quantity) * float(px)
        except Exception:  # noqa: BLE001 — 한 종목 조회 실패로 자산을 왜곡하지 않는다
            log.warning("실거래 자산 계산: %s 포지션 조회 실패 — 제외", symbol)
    return total


def _kill_switch_for_live(state_dir: str, equity: float) -> tuple[float, float]:
    """실거래 계좌의 (노출 배수, 낙폭). 규칙은 페이퍼와 **같은 함수**를 쓴다.

    ⚠️ 여기에 문턱을 다시 적지 않는다. 같은 규칙을 두 곳에 적으면 반드시
       어긋나고, 어긋나는 쪽은 늘 나중에 손대는 쪽이다(FROZEN_IDEAS ①).
       -3%/-15% 같은 숫자가 이 파일에 등장하면 그건 결함이다.
    """
    import json

    from quant.live.daily import _kill_switch_scale
    from quant.live.ledger_basics import drawdown_from_index, twr_index

    path = os.path.join(state_dir, "live", "kr.json")
    hist: list = []
    prev_scale = 1.0
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                blob = json.load(f)
            hist = blob.get("history") or []
            for row in reversed(hist):
                if row.get("risk_scale") is not None:
                    prev_scale = float(row["risk_scale"])
                    break
        except (OSError, ValueError):
            hist = []
    series = [{"date": r.get("date"), "equity": r.get("equity")}
              for r in hist if r.get("equity")]
    if equity > 0:
        series.append({"date": _dt.date.today().isoformat(), "equity": equity})
    if len(series) < 2:
        # 기록이 없으면 낙폭을 모른다 — 모를 때는 **줄이지도 열지도 않는다**.
        # (0.0으로 잠그면 첫날 아무것도 못 사고, 이 계좌는 영원히 첫날이다.)
        return prev_scale, 0.0
    dd = drawdown_from_index(twr_index(series, [], start_cash=series[0]["equity"]))
    return _kill_switch_scale(prev_scale, dd), dd


def _validation_damping(targets, state_dir: str) -> dict:
    """과최적화 검증(PBO·DSR) 결과 → 종목별 비중 배수. 페이퍼와 같은 판정기.

    검증 기록이 없으면 그 종목은 **절반**이다 — '안 재봤다'와 '괜찮다'를
    같게 두면 검증이 고장난 날 시스템이 가장 공격적으로 굴러간다.
    """
    keys = [f"{m}:{s}" for m, s in targets]
    try:
        from quant.live.validation_gate import gate_summary, validation_grades
        grades = validation_grades(keys, state_dir=state_dir)
    except Exception as exc:  # noqa: BLE001 — 못 재면 보수적으로 절반
        log.warning("검증 게이트를 부르지 못했습니다(%s) — 전 종목 비중 절반", exc)
        return dict.fromkeys(keys, 0.5)
    log.info("%s (실거래)", gate_summary(grades))
    out = {}
    for key, g in grades.items():
        scale = float(g["scale"])
        out[key] = scale
        if scale < 1.0:
            log.warning("검증 게이트(실거래) %s → 비중 ×%.2f · %s",
                        key, scale, g.get("why", ""))
    return out


def run_daily_live(targets=None, *, paper: bool = True,
                   state_dir: str = STATE_DIR, broker=None,
                   broker_name: str | None = None,
                   _clock=None) -> dict:
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
    broker = _harden(broker, sleep=(_clock or {}).get('sleep'),
                     now=(_clock or {}).get('now'))

    from quant.data import get_provider
    n = len(targets)
    orders, decisions, skipped = [], {}, []
    zero_qty: list = []          # 1주 미만이라 0주로 잘린 주문(감사 138)
    unfilled: list = []          # 접수됐지만 체결 0인 주문(감사 148)

    # ── 시세 선취 + 계좌 자산 계산 (감사 268) ───────────────────────
    #
    # ⚠️ **왜 여기서 자산을 재는가.** 킬스위치는 '지금 계좌가 고점 대비
    #    얼마나 깨졌나'로 판단하므로 **주문을 내기 전에** 계좌 전체 자산을
    #    알아야 한다. 예전 이 함수는 종목 루프 안에서 그 종목 하나의
    #    포지션만으로 equity를 냈고(현금 + 그 종목), 계좌 전체 자산은
    #    어디에도 없었다 — 그래서 낙폭을 **잴 수조차 없었다.**
    prices: dict = {}
    frames: dict = {}
    for market, symbol in targets:
        try:
            df = get_provider(market).get_ohlcv(symbol, "1d", limit=400)
            if df.empty or df.attrs.get("synthetic_fallback"):
                raise RuntimeError("실데이터 수신 실패")
            frames[symbol] = df
            prices[symbol] = float(df["close"].iloc[-1])
        except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 나머지를 막지 않는다
            skipped.append(symbol)
            log.warning("실거래 %s 시세 스킵: %s", symbol, exc)

    account_equity = _account_equity(broker, prices)

    # 킬스위치·검증 게이트 — **페이퍼와 같은 함수를 부른다.**
    #
    # ⚠️ 2026-08-16까지 이 경로에는 둘 다 없었다(감사 268). 페이퍼 계좌는
    #    낙폭이 커지면 자동으로 노출을 줄이고 과최적화 검증 결과를 비중에
    #    곱하는데, **실제로 돈이 나가는 쪽에는 그 둘이 배선돼 있지 않았다.**
    #    문서와 사이트는 "킬스위치가 실거래를 막는다"고 말하고 있었다.
    #    이 파일은 같은 병을 이미 한 번 앓았다 — 재조정 밴드를 페이퍼만
    #    고치고 실거래 경로는 옛 코드로 남겨 뒀던 2026-08-11이다.
    #    규칙은 여기 다시 적지 않는다. 한 곳에서 가져와 곱하기만 한다.
    risk_scale, drawdown = _kill_switch_for_live(state_dir, account_equity)
    valid_damp = _validation_damping(targets, state_dir)
    eff_exposure = exposure * risk_scale
    if risk_scale < 1.0:
        log.warning("🛡 킬스위치(실거래): 낙폭 %.1f%% → 노출 %.0f%%로 제한",
                    drawdown * 100, risk_scale * 100)

    for market, symbol in targets:
        try:
            df = frames.get(symbol)
            if df is None:
                continue                    # 위에서 이미 skipped에 담았다
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
            # 실거래는 롱온리·무레버리지 — 음수(숏)·1 초과는 자르고, 그다음
            # **킬스위치·어드민 배수·검증 게이트**를 차례로 곱한다(감사 268).
            # ⚠️ 자르기 **뒤**에 곱해야 한다. 앞에 두면 상한이 축소분을 다시
            #    끌어올려 장치가 무력화된다 — 페이퍼에서 2026-08-11에 실제로
            #    그렇게 킬스위치가 죽었고, 그래서 같은 순서를 여기서도 지킨다.
            weight = max(0.0, min(1.0, weight)) * eff_exposure
            weight *= valid_damp.get(f"{market}:{symbol}", 1.0)
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
                # ⚠️ qty는 '내려고 한 수량', filled는 '실제로 채워진 수량'이다
                #    (감사 148). 둘을 한 칸에 담으면 접수-미체결이 체결로
                #    읽힌다 — 감사 138이 0주 잘림에 대해 고쳤던 것과 같은 병이
                #    접수 단계에 그대로 남아 있었다.
                filled = float(getattr(order, "filled_quantity", 0.0) or 0.0)
                orders.append({"symbol": symbol, "side": order.side,
                               "qty": order.quantity, "filled": filled,
                               "price": order.price,
                               "status": order.status,
                               "order_id": order.order_id})
                if order.status not in ("skipped",) and filled <= 0:
                    unfilled.append({"symbol": symbol, "side": order.side,
                                     "qty": order.quantity,
                                     "status": order.status})
                # 주문 단위 감사 로그(감사 150). `journal.record_order`는
                # 모듈 설명에 "두 가지를 한다"고 적혀 있는 그 첫 번째인데
                # **운영 코드에서 부르는 곳이 한 곳도 없었다** — 검사에서만
                # 불렸다. 아래 kr.json은 하루 한 줄 요약이고 400일치만
                # 남기지만, 이쪽은 append-only라 증권사 체결 내역과
                # order_id로 대사할 수 있는 유일한 기록이다.
                record_order(
                    os.path.join(state_dir, "live", "orders.jsonl"),
                    {"symbol": symbol, "side": order.side,
                     "quantity": order.quantity, "filled": filled,
                     "price": order.price, "status": order.status,
                     "order_id": order.order_id},
                    {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                     "mode": "paper" if paper else "real",
                     "broker": type(broker).__name__,
                     "weight": round(weight / n, 6), "equity": round(equity, 2)})
                # ⚠️ 국내주식은 정수 주만 산다. 목표 금액이 1주 값에 못 미치면
                #    브로커가 int(quantity)=0으로 잘라 status='skipped'를
                #    돌려준다 — **한 주도 안 샀는데 orders에는 한 줄이 남는다.**
                #    예전에는 아래 요약이 그걸 "주문 N건"으로 세어, 실제로는
                #    아무것도 안 산 날에도 주문이 나간 것처럼 보고했다(감사 138).
                #    왜 0주가 됐는지(목표 금액 vs 1주 값)까지 남겨야 운영자가
                #    '유니버스를 바꿔야 하는 상황'임을 알 수 있다.
                if order.status == "skipped":
                    want = weight / n * equity
                    zero_qty.append({"symbol": symbol,
                                     "budget": round(want, 2),
                                     "price": round(price, 2),
                                     "shares": round(want / price, 6)
                                     if price > 0 else None})
        except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 나머지를 막으면 안 된다
            skipped.append(symbol)
            log.warning("실거래 %s 스킵: %s", symbol, exc)

    summary = {"mode": "모의투자" if paper else "실전",
               "broker": type(broker).__name__,
               "decisions": decisions, "orders": orders, "skipped": skipped,
               # 접수된 주문 중 **실제로 0주**였던 것들. 이게 없으면
               # "주문 N건"이 곧 "N종목을 샀다"로 읽힌다(감사 138).
               "zero_qty": zero_qty,
               # 접수는 됐는데 체결이 0인 주문. 주식 시장가는 접수와 체결이
               # 별개라 이 칸이 없으면 "주문 N건"이 곧 "N종목을 샀다"로
               # 읽힌다 — zero_qty(감사 138)와 같은 병의 다른 단계다.
               "unfilled": unfilled,
               "exposure_scale": exposure,
               # 계좌 전체 자산 — **낙폭을 재려면 이게 있어야 한다**(감사 268).
               # 예전에는 주문 한 줄마다 '현금 + 그 종목' 값만 남고 계좌
               # 자산은 어디에도 없었다. 그래서 킬스위치는 배선이 없던 게
               # 아니라 **잴 재료조차 없었다.**
               "equity": round(account_equity, 2) if account_equity else None,
               # 오늘 실제로 적용된 자동 브레이크. 남기지 않으면 "왜 오늘
               # 덜 샀나"에 장부가 답하지 못한다.
               "risk_scale": risk_scale,
               "drawdown_pct": round(drawdown * 100, 2),
               "validation_gate": {k: v for k, v in valid_damp.items()
                                   if v < 1.0} or None}
    try:
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
    # ⚠️ 접수 건수와 **실제로 산 건수**를 구분해서 말한다(감사 138).
    #    국내주식은 1주 미만이 0주로 잘리므로, 둘을 합쳐 세면
    #    한 주도 안 산 날에도 "주문 5건"으로 보고된다.
    placed = len(orders) - len(zero_qty)
    filled_n = sum(1 for o in orders if float(o.get("filled") or 0.0) > 0)
    print(f"[{summary['mode']}] 결정 {len(decisions)}종목 · 접수 {placed}건 "
          f"· 체결 {filled_n}건"
          + (f" · 1주 미만이라 미집행 {len(zero_qty)}종목"
             f"({', '.join(z['symbol'] for z in zero_qty)})" if zero_qty else "")
          + (f" · 접수됐지만 미체결 {len(unfilled)}종목"
             f"({', '.join(u['symbol'] for u in unfilled)})" if unfilled else "")
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
