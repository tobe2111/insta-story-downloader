"""스트레스 시나리오 — "내일 아침 무엇이 우리를 다치게 하는가"를 미리 센다.

리스크 데스크의 표준 질문이다. 과거 재생(replay)이 "지나온 위기에서
브레이크가 작동했는가"를 본다면, 여기는 **아직 안 온 위기**를 지금 계좌에
직접 가해 본다: 하룻밤 폭락, 연쇄 하락, 단일 종목 사고, 환율 급변,
멈춘 시세 속의 하락.

여기서 지키는 것
    ① 시나리오의 결과에 **실전 킬스위치 함수를 그대로** 묻는다 — "그러면
       시스템이 다음 날 어떻게 반응하는가"까지가 답이다. 문턱을 여기 다시
       적으면 실전과 갈라진다(FROZEN_IDEAS ①).
    ② 지금 장부의 **실제 노출**로 계산한다. 총노출 42%면 시장 -30%는
       계좌 -12.6%다 — 현금이 완충한다는 사실을 빼고 겁주지 않고,
       넣고 안심시키지도 않는다(노출이 커지면 결과도 커진다).

정직한 한계
    · 시나리오는 가정이다. 실제 위기는 여기 없는 모양으로 온다 —
      이 표는 "최소한 이 정도는 견딘다"는 하한 점검이지 보증이 아니다.
    · 폭락 중의 유동성 증발(호가 공백·체결 불가)은 모델에 없다.
"""
from __future__ import annotations


def _kill_switch(prev: float, dd: float) -> float:
    """실전 킬스위치를 그대로 — 문턱을 여기 다시 적지 않는다."""
    from quant.live.daily import _kill_switch_scale
    return _kill_switch_scale(prev, dd)


def _dd(eq: float, peak: float) -> float:
    """낙폭도 공용 헬퍼로 잰다 — 낙폭의 정의가 사는 곳은 한 군데다.

    직접 나눗셈을 적었다가 이 저장소의 감시(test_killswitch_deposits)에
    걸렸다. 정당한 지적이었다: 고점보다 위에 있으면 낙폭은 +가 아니라
    0이어야 하는데, 손으로 적은 식은 환율이 유리하게 움직인 시나리오에
    '+4% 낙폭'이라는 뜻 없는 값을 적고 있었다. 헬퍼는 그걸 알고 있다.
    """
    from quant.live.ledger_basics import drawdown_from_index
    return drawdown_from_index([eq / peak]) if peak > 0 else 0.0


# (이름, 설명, 하루 수익률 경로 — 노출 자산에 가해지는 시장 충격)
# 경로가 여러 날이면 킬스위치가 중간에 개입해 뒤의 손실을 줄이는지 본다.
SCENARIOS = (
    ("gap_-10", "하룻밤 갭 -10% (전 종목 동반 하락, 상관 1)", [-0.10]),
    ("gap_-20", "하룻밤 갭 -20% (2020-03 규모)", [-0.20]),
    ("gap_-30", "하룻밤 갭 -30% (역대급 단일일)", [-0.30]),
    ("cascade_5x-8", "닷새 연속 -8% (2022 루나·FTX형 연쇄 붕괴)",
     [-0.08] * 5),
    ("slow_bleed_20x-2", "20일 연속 -2% (완만한 침식형 약세)",
     [-0.02] * 20),
)


def stress_portfolio(*, equity: float, principal: float, gross_weight: float,
                     fx_share: float, worst_single_weight: float,
                     peak_equity: float | None = None) -> dict:
    """지금 계좌 상태에 시나리오를 가하고, 실전 브레이크의 반응까지 적는다.

    equity/principal    — 현재 자산·원금(원)
    gross_weight        — 총노출(0.42 = 자산의 42%가 위험자산)
    fx_share            — 노출 중 외화 표시 자산의 비중(환율 충격 대상)
    worst_single_weight — 가장 큰 단일 종목의 비중(단일 사고 시나리오)
    peak_equity         — 낙폭 계산 기준 고점(없으면 원금과 현 자산 중 큰 쪽)
    """
    peak = max(peak_equity or 0.0, principal, equity)
    out: list[dict] = []

    for name, desc, path in SCENARIOS:
        eq = equity
        ks = 1.0
        exposure = gross_weight
        engaged_on = None                     # 며칠째에 브레이크가 잡았나
        for day, shock in enumerate(path, start=1):
            eq *= 1.0 + exposure * shock
            dd = _dd(eq, peak)
            prev = ks
            ks = _kill_switch(ks, dd)
            if ks < prev and engaged_on is None:
                engaged_on = day
            # 다음 날의 노출 — 킬스위치가 물러난 만큼 손실도 줄어든다.
            exposure = gross_weight * ks
        dd = _dd(eq, peak)
        out.append({
            "scenario": name, "desc": desc,
            "days": len(path),
            "equity_after": round(eq, 2),
            "loss_pct": round((eq / equity - 1.0) * 100, 2),
            "drawdown_pct": round(dd * 100, 2),
            "kill_switch_after": _kill_switch(ks, dd),
            "engaged_on_day": engaged_on,
        })

    # 환율 쇼크 — 시장이 아니라 원화가 움직인다. 외화 자산만 맞는다.
    for name, fx_move in (("krw_+15", +0.15), ("krw_-15", -0.15)):
        eq = equity * (1.0 + gross_weight * fx_share * fx_move)
        dd = _dd(eq, peak)
        out.append({
            "scenario": name,
            "desc": f"원/달러 {fx_move:+.0%} — 외화 자산({fx_share:.0%})만 영향",
            "days": 1, "equity_after": round(eq, 2),
            "loss_pct": round((eq / equity - 1.0) * 100, 2),
            "drawdown_pct": round(dd * 100, 2),
            "kill_switch_after": _kill_switch(1.0, dd),
            "engaged_on_day": None,
        })

    # 단일 종목 -50% — 분산이 실제로 지켜주는가.
    eq = equity * (1.0 - worst_single_weight * 0.50)
    dd = _dd(eq, peak)
    out.append({
        "scenario": "single_-50",
        "desc": f"최대 비중 종목({worst_single_weight:.1%}) 하루 -50%",
        "days": 1, "equity_after": round(eq, 2),
        "loss_pct": round((eq / equity - 1.0) * 100, 2),
        "drawdown_pct": round(dd * 100, 2),
        "kill_switch_after": _kill_switch(1.0, dd),
        "engaged_on_day": None,
    })

    # 멈춘 시세 — 위 어느 것과도 다른 종류: 손실이 아니라 **실명(失明)**.
    # 시세가 5일 멈춘 사이 시장이 -20% 가면, 장부 낙폭은 0이고 킬스위치는
    # 반응할 수 없다. 이 시나리오의 산출물은 손실액이 아니라 '보지 못하는
    # 동안 쌓이는 위험'의 크기다. stale_marks 감시가 이 실명을 줄인다.
    blind_loss = equity * gross_weight * 0.20
    out.append({
        "scenario": "stale_5d_-20",
        "desc": "시세가 5일 멈춘 사이 시장 -20% — 장부는 그동안 낙폭 0을 보고한다",
        "days": 5, "equity_after": round(equity - blind_loss, 2),
        "loss_pct": round(-gross_weight * 0.20 * 100, 2),
        "drawdown_pct": round(_dd(equity - blind_loss, peak) * 100, 2),
        "kill_switch_after": None,      # 못 본다 — 그것이 이 시나리오의 요점
        "engaged_on_day": None,
        "blind": True,
    })

    worst = min(out, key=lambda r: r["drawdown_pct"])
    return {
        "kind": "simulation",
        "inputs": {"equity": round(equity, 2), "principal": principal,
                   "gross_weight": gross_weight, "fx_share": round(fx_share, 4),
                   "worst_single_weight": round(worst_single_weight, 4)},
        "scenarios": out,
        "worst": {"scenario": worst["scenario"],
                  "drawdown_pct": worst["drawdown_pct"]},
        "honest_limits": [
            "시나리오는 가정 — 실제 위기는 여기 없는 모양으로 온다. 하한 점검이지 보증이 아님",
            "폭락 중의 유동성 증발(호가 공백·체결 불가)은 모델에 없음",
            "노출이 지금(입력값)과 다르면 결과도 달라짐 — 매일 다시 계산해야 의미가 있음",
        ],
    }


def stress_from_state(state_dir: str = "state") -> dict | None:
    """지금 통합 계좌 장부에서 입력을 읽어 스트레스를 돌린다."""
    import json
    import os
    path = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        rec = st["history"][-1]
        equity = float(rec["equity"])
        principal = float(rec.get("principal") or 1_000_000)
        gross = float(rec.get("weight") or 0.0)
        applied = rec.get("applied") or {}
        fx_w = sum(w for k, w in applied.items()
                   if not k.startswith("kr_stock"))
        tot_w = sum(applied.values()) or 1.0
        worst_single = max(applied.values(), default=0.0)
        peak = max((float(r["equity"]) for r in st["history"]
                    if r.get("equity")), default=equity)
        return stress_portfolio(
            equity=equity, principal=principal, gross_weight=gross,
            fx_share=fx_w / tot_w, worst_single_weight=worst_single,
            peak_equity=peak)
    except Exception:  # noqa: BLE001 — 분석 도구가 본류를 막으면 안 된다
        return None
