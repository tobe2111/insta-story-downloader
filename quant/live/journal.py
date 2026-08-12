"""거래 저널 & 성과 복기 — 봇이 실제로 무엇을 했고, 무엇이 되고 안 됐는지.

두 가지를 한다:
    1. 주문 감사 로그: 실행된 주문을 append-only JSONL로 기록(재현·감사용).
    2. 성과 복기: 봇이 이미 저장하는 상태(state.json의 history: 자본·목표비중
       시계열)에서 개별 라운드트립 거래를 뽑아 거래 단위 통계를 낸다. 기존
       backtest.trades(extract_trades·trade_stats)를 재사용하므로 백테스트와
       '같은 자'로 실거래 성과를 잰다. 하이퍼루프를 건드리지 않는다.

⚠️ 정직한 해석: 거래 수가 적으면(대략 <30) 승률·이익팩터는 노이즈다. 중요한 건
   '거래 1회당 기대손익(expectancy)'이 비용을 넘느냐다. 승률이 높아도 기대손익이
   0 이하면 그 전략은 돈을 잃는다. 이 복기는 수익을 예측하지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def record_order(path: str | Path, order: dict, context: dict | None = None) -> None:
    """실행된 주문 한 건을 JSONL로 덧붙인다(감사 로그). 실패해도 예외를 삼킨다.

    order   : 주문 결과 dict(symbol·side·quantity·price·status·order_id 등)
    context : 부가 정보(time·equity·weight·mode 등)

    ⚠️ **여기서 예외가 새면 안 되는 이유**(감사 174): 이 함수는 주문을
       **보낸 뒤에** 불린다. 여기서 죽으면 돈은 이미 움직였는데 배치가
       그 자리에서 멈춘다 — 남은 종목은 처리되지 않고, 방금 낸 주문은
       장부에도 안 남는다. 가장 나쁜 순간의 실패다.

       예전에는 `except OSError`만 잡았다. 독스트링은 "실패해도 예외를
       삼킨다"라고 적혀 있는데 실제로는 두 종류가 새어 나갔다:
           직렬화 불가 키(datetime 키 등) → TypeError
           순환 참조                      → ValueError
       약속과 코드가 어긋나 있었다(㊾와 같은 계열).

       감사 로그는 곁가지다. 곁가지가 본류를 죽이면 안 된다 — 다만 조용히
       삼키지는 않고 경고를 남긴다.
    """
    try:
        rec = {**(context or {}), **(order or {})}
        fp = Path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with fp.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001 — 감사 로그가 매매를 죽이면 안 된다
        from quant.utils.logging import get_logger
        get_logger("live.journal").warning(
            "주문 감사 로그 기록 실패(%s) — 매매는 계속합니다", exc)


def load_orders(path: str | Path) -> list[dict]:
    """주문 감사 로그(JSONL)를 읽는다(없으면 빈 목록)."""
    fp = Path(path)
    if not fp.exists():
        return []
    out: list[dict] = []
    for line in fp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def build_review(history: list[dict]) -> dict:
    """상태 history(자본·목표비중 시계열)에서 거래 단위 통계를 낸다.

    ⚠️ 예전에는 `periods_per_year` 인자를 받았는데 **본문에서 한 번도 쓰지
       않았다**(감사 174). 그런데 CLI는 시장에 맞춰(코인 365 / 주식 252)
       그 값을 성실히 계산해 넘기고 있었다 — 사장님이 시장을 고르면 뭔가
       달라질 것처럼 보이지만 아무 일도 일어나지 않는 **죽은 손잡이**였다.
       trade_stats에는 연율화 지표가 없어 쓸 자리 자체가 없다. 지웠다.
       (감사 135와 같은 계열 — 있는 척하는 손잡이가 없는 것보다 나쁘다.)

    history 원소는 {equity, weight, ...} 형태(LiveTrader/MultiTrader가 저장). 이를
    자본곡선·포지션 Series로 만들어 extract_trades→trade_stats로 복기한다.
    거래가 없거나 데이터가 부족하면 num_trades=0으로 반환(크래시 없음).
    """
    import pandas as pd

    from quant.backtest.trades import extract_trades, trade_stats

    rows = [h for h in history if isinstance(h, dict) and "equity" in h]
    if len(rows) < 3:
        base = trade_stats([])
        base.update({"total_return": 0.0, "n_points": len(rows)})
        return base

    eq = pd.Series([float(h.get("equity", 0.0)) for h in rows], dtype=float)
    # 목표비중을 포지션 대용으로 쓴다(부호=방향). 없으면 0.
    pos = pd.Series([float(h.get("weight", 0.0) or 0.0) for h in rows], dtype=float)
    eq.index = range(len(eq))
    pos.index = range(len(pos))

    trades = extract_trades(eq, pos)
    stats = trade_stats(trades)
    total_ret = float(eq.iloc[-1] / eq.iloc[0] - 1.0) if eq.iloc[0] else 0.0
    stats.update({"total_return": total_ret, "n_points": len(rows)})
    return stats


def review_report(review: dict) -> str:
    """거래 복기 통계를 사람이 읽을 한국어 리포트로."""
    n = review.get("num_trades", 0)
    if n == 0:
        return ("아직 완결된 거래(라운드트립)가 없습니다. 더 오래 운용한 뒤 다시 "
                "복기하세요.")
    pf = review["profit_factor"]
    pf_s = "∞" if pf == float("inf") else f"{pf:.2f}"
    exp = review["expectancy"]
    lines = [
        f"거래 수        : {n}",
        f"총 수익률      : {review.get('total_return', 0.0):.2%}",
        f"승률           : {review['win_rate']:.1%}",
        f"평균 이익/손실 : +{review['avg_win']:.2%} / {review['avg_loss']:.2%}",
        f"기대손익(1회)  : {exp:+.3%}   ← 가장 중요",
        f"이익팩터       : {pf_s}",
        f"평균 보유      : {review['avg_bars_held']:.1f}봉",
    ]
    if review.get("num_open"):
        lines.append(f"(아직 안 판 포지션 {review['num_open']}건은 위 통계에서 "
                     "뺐습니다 — 평가손익이지 실현손익이 아닙니다.)")
    # 정직한 판정 — 표본·기대손익·비용 관점
    if n < 30:
        lines.append(f"⚠️ 거래 {n}건은 통계적으로 부족합니다 — 승률·이익팩터는 아직 "
                     "노이즈일 수 있습니다(최소 30건 이상 권장).")
    if exp <= 0:
        lines.append("🚨 기대손익이 0 이하입니다 — 승률과 무관하게 이 운용은 평균적으로 "
                     "돈을 잃고 있습니다. 비용·전략을 재점검하세요.")
    else:
        lines.append("기대손익이 양수입니다. 다만 이 값이 실제 왕복 거래비용보다 "
                     "충분히 큰지 확인하세요(작으면 실전에서 상쇄됩니다).")
    lines.append("⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.")
    return "\n".join(lines)


def review_state_file(state_path: str | Path) -> dict[str, Any]:
    """상태 파일(state.json)을 읽어 거래 복기 통계를 반환한다(없으면 빈 통계)."""
    fp = Path(state_path)
    if not fp.exists():
        return build_review([])
    try:
        state = json.loads(fp.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return build_review([])
    return build_review(state.get("history", []) or [])
