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

    # ⑥ 피처 유실 — 외부 소스(야후·바이낸스·FRED·KRX)가 죽으면 피처가
    #    조용히 줄어드는데 장부에는 같은 fs8로 기록된다. 그러면 판정 시계가
    #    매일 다른 구조를 재게 된다(2026-08-11 발견). 어느 소스가 통째로
    #    빠졌는지 알린다 — 한 종목만 빠진 것은 시장 차이라 경보하지 않는다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        fh = (hist[-1].get("feature_health") if hist else None) or {}
        gone = fh.get("missing_everywhere") or []
        if gone:
            flags["features_missing:" + ",".join(sorted(gone))] = (
                f"⚠️ 피처 유실: {len(gone)}개가 전 종목에서 빠졌습니다 "
                f"({', '.join(gone)}). 외부 데이터 소스 장애일 가능성이 큽니다 — "
                f"장부에는 같은 구조 태그로 기록되지만 모델은 다른 피처로 "
                f"학습·판단합니다.")

    # ⑦ 새벽 배치 부분 실패 — '전 종목 실패'만 예외로 올리던 탓에 20종목 중
    #    19개가 실패한 날도 잡은 초록이었다(2026-08-11 발견). 실패한 종목은
    #    그날 판단·기록이 통째로 없고 옛 챔피언을 그대로 쓴다.
    for kind, r in (status.get("run_health") or {}).items():
        n = int(r.get("failed") or 0)
        if not n:
            continue
        keys = ", ".join((r.get("failed_keys") or [])[:5])
        more = "…" if len(r.get("failed_keys") or []) > 5 else ""
        err = next(iter((r.get("errors") or {}).values()), "")
        label = {"paper": "페이퍼", "retrain": "재학습"}.get(kind, kind)
        flags[f"run_failed:{kind}:{r.get('date')}:{n}"] = (
            f"⚠️ {label} 부분 실패: {r.get('date')} {n}종목 실패 "
            f"(성공 {r.get('ok')}) — {keys}{more}. "
            f"실패 종목은 그날 기록이 없고 이전 판단을 그대로 씁니다."
            + (f"\n첫 오류: {err}" if err else ""))

    # ⑧ 종목 스킵 — 데이터 장애로 빠진 종목은 그날 관망(포지션 유지)이라
    #    조용히 지나간다. 하지만 20종목 중 다섯만 남은 날은 '20종목 분산'이
    #    아니라 5종목 집중이고, 그건 완전히 다른 위험이다(2026-08-11).
    #    소수 스킵(휴장·상장폐지 등)은 정상이라 1/4 이상일 때만 알린다.
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        ch = (hist[-1].get("champion") if hist else None) or {}
        gone = ch.get("skipped") or []
        planned = int(ch.get("planned") or 0) or (len(gone) + int(ch.get("symbols") or 0))
        if not gone or not planned or len(gone) * 4 < planned:
            continue
        why = ch.get("skipped_why") or {}
        first = next(iter(why.values()), "")
        flags[f"symbols_skipped:{hist[-1].get('date')}:{len(gone)}"] = (
            f"⚠️ 종목 스킵 과다: {planned}종목 중 {len(gone)}개가 빠져 "
            f"{int(ch.get('symbols') or 0)}종목으로 운용했습니다 "
            f"({', '.join(gone[:5])}{'…' if len(gone) > 5 else ''}). "
            f"분산이 계획보다 얕아진 날입니다 — 데이터 소스 장애일 수 있습니다."
            + (f"\n첫 사유: {first}" if first else ""))

    # ⑨ 데이터 품질 — 무결성 위반(중복·음수가격·OHLC 모순)은 그 종목을
    #    아예 스킵시키므로 여기 오지 않는다. 여기서 보는 것은 '사람이 맥락으로
    #    판단할' 스파이크다: 하루 ±20%가 넘는 봉이 갑자기 늘면 분할·배당
    #    미조정일 가능성이 크고, 그러면 수익률이 통째로 거짓이 된다.
    #    (품질 검사 자체가 수동 백테스트에서만 돌던 것을 2026-08-11에
    #     새벽 배치로 옮겼다 — 정작 매매하는 쪽이 검사받지 않고 있었다.)
    for key, p in (status.get("paper") or {}).items():
        if not key.startswith("portfolio:"):
            continue
        hist = p.get("history") or []
        dq = (hist[-1].get("data_quality") if hist else None) or {}
        spikes = int(dq.get("spikes") or 0)
        if spikes <= 0:
            continue
        prev = [int(((r.get("data_quality") or {}).get("spikes") or 0))
                for r in hist[-8:-1]]
        base = max(prev) if prev else 0
        if spikes > max(3, base * 2):
            flags[f"data_spikes:{hist[-1].get('date')}:{spikes}"] = (
                f"⚠️ 가격 스파이크 급증: 전 종목 합계 {spikes}건 "
                f"(최근 기준 {base}건) — 하루 ±20% 넘는 봉이 갑자기 늘었습니다. "
                f"분할·배당 미조정일 가능성이 크고, 그렇다면 수익률 계산이 "
                f"통째로 어긋납니다. 해당 종목의 원본 시세를 확인하세요.")

    # ⑩ 판정 시계 — 새 구조 세대 시작(리셋)과 90일 만료는 각각 한 번만 알린다
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
    # 전송에 실패한 경보는 '보냈다'로 적지 않는다 — 적으면 다음 실행부터
    # '이미 켜져 있던 플래그'로 분류돼 **영원히 다시 오지 않는다**. 웹훅이
    # 한 번 죽은 날 하필 킬스위치가 발동하면 그 사실을 끝내 모르게 된다
    # (2026-08-11 감사에서 발견). 실패분은 빼 두고 다음 실행에 다시 시도한다.
    failed: set[str] = set()
    if new:
        from quant.live.notifications import get_notifier
        notifier = get_notifier()
        for k in new:
            if notifier.send(cur[k]) is False:   # None(구식 구현)은 성공 취급
                failed.add(k)
    atomic_write_json(path, {"flags": sorted(set(cur) - failed)})
    return [k for k in new if k not in failed]
