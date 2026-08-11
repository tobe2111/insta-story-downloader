"""플래그 파수꾼 — 사이트 표시 전용이던 경고가 새로 켜지면 알림으로도 쏜다.

사이트의 자기 고발 플래그(백테스트 낙관 의심·보정 어긋남·판정 시계
리셋/만료)는 매일 새벽 status.json에 계산되지만, 사장님이 사이트를 열어야
보인다. 이 모듈은 플래그 집합을 state/flag_state.json에 기억해 두고,
'새로 켜진' 플래그만 알림 채널(디스코드·텔레그램·슬랙 — 환경변수에 설정된
곳 전부)로 발송한다. 이미 켜져 있던 플래그는 조용하다 — 매일 같은 경고를
반복하면 경고가 소음이 된다. 꺼졌다가 다시 켜지면 다시 알린다.
"""
from __future__ import annotations

import json
import os


def _current_flags(status: dict) -> dict[str, str]:
    """status.json 재료에서 지금 켜져 있는 플래그를 {키: 알림 문구}로 모은다."""
    flags: dict[str, str] = {}

    # ① 체결 가정 검증 — 실측 불리 갭이 백테스트 가정을 초과(낙관 의심)
    fc = status.get("fill_check") or {}
    for market, r in (fc.get("markets") or {}).items():
        if r.get("optimistic"):
            flags[f"optimistic:{market}"] = (
                f"⚠️ 체결 가정 검증: {market} 실측 불리 갭 평균 "
                f"{r['mean_adverse_bp']}bp > 백테스트 가정 {r['assumed_bp']}bp "
                f"(표본 {r['n']}건) — 백테스트가 낙관적일 수 있습니다. "
                f"표본 30건 이상 유지 시 비용 프리셋 상향 검토.")

    # ② 보정 어긋남 — 예측확률이 실제 적중률의 신뢰구간 밖(표본 확정 구간만)
    try:
        from quant.live.calibration_guard import calibration_table
        hists = [(p.get("history") or [])
                 for k, p in (status.get("paper") or {}).items()
                 if not k.startswith("portfolio")]
        for row in calibration_table(hists):
            if row["confirmed"]:
                key = f"miscal:{int(row['lo'] * 100)}-{int(row['hi'] * 100)}"
                flags[key] = (
                    f"⚠️ 보정 어긋남 확정: 예측 {int(row['lo'] * 100)}~"
                    f"{int(row['hi'] * 100)}% 구간의 실제 상승 비율 "
                    f"{row['actual'] * 100:.0f}% (표본 {row['n']}건, 95% CI "
                    f"{row['ci_lo'] * 100:.0f}~{row['ci_hi'] * 100:.0f}%) — "
                    f"사이트에 경험 보정값 병기 중(사이징 개입 없음).")
    except Exception:  # noqa: BLE001 — 보정표 실패가 다른 플래그를 막으면 안 된다
        pass

    # ③ 회전율 비용 — 비용이 기대수익을 넘으면 엣지가 있든 없든 수익이 없다.
    #    2026-08-11 실측에서 일 37% 회전 → 연 40% 비용 vs 기대수익 8.8%였다.
    #    밴드·평활·쿨다운으로 고쳤지만 효과는 미검증 — 그래서 매일 감시한다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = [r for r in (p.get("history") or []) if r.get("turnover")]
        recent = hist[-20:]
        if len(recent) < 10:
            continue                       # 표본이 얇으면 판정하지 않는다
        ratios = [float(r["turnover"].get("ratio") or 0.0) for r in recent]
        avg = sum(ratios) / len(ratios)
        # 가중평균 왕복 비용 43bp(코인 30·미국 12·한국 실측 93 기준 근사)
        annual_cost = avg * 252 * 0.0043
        vt = (hist[-1].get("vol_target") or {}) if hist else {}
        expected = float(vt.get("target") or 0.12)   # 샤프 1.0 가정
        if annual_cost > expected:
            flags["turnover_cost"] = (
                f"⚠️ 회전율 경보: 최근 {len(recent)}일 평균 {avg * 100:.0f}%/일 "
                f"→ 연 비용 약 {annual_cost * 100:.0f}%가 기대수익 "
                f"{expected * 100:.0f}%를 넘습니다. 비용이 엣지를 먹는 구조 — "
                f"밴드·쿨다운을 더 넓히거나 고비용 시장(한국주식) 비중을 "
                f"재검토해야 합니다.")

    # ④ 킬스위치 — 통합 계좌가 낙폭으로 노출을 줄인 순간은 즉시 알아야 할
    #    사건이다. 단계가 더 내려가면(0.75→0.5) 키가 바뀌어 다시 알리고,
    #    1.0 복귀는 조용히 플래그만 끈다(복귀 후 재발동 시 재알림).
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        last = hist[-1] if hist else {}
        rs = last.get("risk_scale")
        if rs is not None and float(rs) < 1.0:
            dd = last.get("drawdown_pct")
            dd_txt = f" (낙폭 {dd}%)" if dd is not None else ""
            flags[f"killswitch:{key}:{rs}"] = (
                f"🛡 킬스위치 발동: 통합 계좌 노출을 {float(rs) * 100:.0f}%로 "
                f"축소{dd_txt} — 낙폭 단계별 자동 브레이크입니다. 회복 시 "
                f"단계적으로 복귀합니다(수동 개입 불필요).")

    # ⑤ 과최적화 감시 — 야간 검증(PBO·DSR)이 콘솔에만 찍히고 사라지던 것을
    #    장부에 남겨 여기서 읽는다. PBO는 'IS 1등이 OOS에서 동전던지기일 확률'
    #    이라 0.5를 넘으면 백테스트 우위가 과적합일 가능성이 높다는 뜻이다.
    #    (예전에는 아무도 안 쓰는 ma_cross를 검증하고 있었다 — 2026-08-11 수정)
    for key, r in (status.get("validation") or {}).items():
        pbo = r.get("pbo")
        if pbo is not None and float(pbo) > 0.5:
            flags[f"overfit:{key}"] = (
                f"⚠️ 과최적화 의심: {key}({r.get('strategy')}) PBO "
                f"{float(pbo) * 100:.0f}% — 백테스트 1등이 실전에서 동전던지기일 "
                f"확률입니다. 파라미터 탐색을 줄이거나 표본을 늘려야 합니다.")
        dsr = r.get("dsr")
        if dsr is not None and float(dsr) < 0.95:
            flags[f"dsr_low:{key}"] = (
                f"⚠️ 실력 미확인: {key}({r.get('strategy')}) DSR "
                f"{float(dsr):.2f} — 다중검정 보정 후 '운이 아니다'라고 말할 "
                f"신뢰도(0.95)에 못 미칩니다.")

    # ⑥ 판정 시계 — 새 구조 세대 시작(리셋)과 90일 만료는 각각 한 번만 알린다
    gen = status.get("generation")
    if gen:
        fs, days, target = gen["feature_set"], gen["days"], gen["target_days"]
        flags[f"generation:{fs}"] = (
            f"🕰 판정 시계 리셋: 새 구조({fs}) 관찰 {days}일차/{target}일 "
            f"({gen['since']}~). 이전 구조 기록은 아카이브로 분리됐고, "
            f"엣지 판정은 시계가 다 돌 때까지 유보합니다.")
        if days >= target:
            flags[f"generation_done:{fs}"] = (
                f"🎯 판정 시계 만료: 구조({fs}) 관찰 {days}일 완료 — "
                f"엣지 유무를 통계로 판정할 때가 됐습니다.")
    return flags


def check_and_notify_flags(status: dict, state_dir: str = "state") -> list[str]:
    """새로 켜진 플래그만 알림 발송하고 현재 집합을 저장한다. 반환: 새 키들."""
    from quant.utils.jsonio import atomic_write_json

    path = os.path.join(state_dir, "flag_state.json")
    prev: set[str] = set()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                prev = set(json.load(f).get("flags") or [])
        except (OSError, ValueError):
            prev = set()
    cur = _current_flags(status)
    new = [k for k in cur if k not in prev]
    if new:
        from quant.live.notifications import get_notifier
        notifier = get_notifier()
        for k in new:
            notifier.send(cur[k])
    atomic_write_json(path, {"flags": sorted(cur)})
    return new
