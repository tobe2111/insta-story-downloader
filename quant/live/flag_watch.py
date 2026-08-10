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

    # ③ 판정 시계 — 새 구조 세대 시작(리셋)과 90일 만료는 각각 한 번만 알린다
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
