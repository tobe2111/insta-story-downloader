"""포트폴리오 목표 변동성 — 우연히 정해지던 리스크를 '명시적 결정'으로 바꾼다.

배경(2026-08-11 전수조사에서 발견한 구조 결함):
    종목별 사이징은 이미 "이 종목 하나가 계좌 전부"라는 가정으로 20% 목표
    변동성까지 비중을 줄인다(예: 원비중 69% → 9%). 그런데 통합 계좌는 거기에
    다시 1/n 슬라이스(합 1.0)를 곱한다. 결과적으로 통합 계좌의 총노출은
    '종목 비중의 평균'(≈7%)이 되고, 실현 변동성은 연 0.6% — 목표 20%의
    1/33이었다. 분산의 이익을 "같은 리스크를 더 안전하게"가 아니라 "리스크
    자체를 소멸"시키는 데 써버린 것이다. 20종목으로 나눴으면 종목당 리스크를
    키울 수 있어야 하는데 반대로 갔다.

이 모듈은 그 이중 감쇠를 '사전(ex-ante) 변동성 측정 → 목표까지 스케일'로
교정한다. 분산으로 줄어든 위험을 공분산으로 측정해 그만큼 되돌려 키우는 것이라,
'분산을 리스크 소멸이 아니라 리스크 예산'으로 쓰는 정석에 맞는다.

무엇이 한도인가 — 배수가 아니라 노출이다. 초기 구현에서 배수 상한(3배)을
한도로 뒀다가, 엣지가 입증돼도 목표에 영원히 도달할 수 없는 구조가 되는 것을
발견하고 분리했다. 진짜 한도는 MAX_GROSS_EXPOSURE(무레버리지선)이다 —
계좌 자산을 넘겨 사지 않으면 파산 경로가 없다.

리스크 수준은 이제 두 개의 명시적 숫자다:
    VERIFY_TARGET_VOL  — 판정 시계가 도는 동안의 목표(기본 연 12%)
    PROVEN_TARGET_VOL  — 엣지가 통계로 입증된 뒤의 목표(기본 연 20%)
전환은 사람의 기분이 아니라 게이트(edge_proven)가 판정한다. 다만 소유자는
risk_override_ack로 그 잠금을 명시적으로 열 수 있다 — 안전장치는 사고를 막기
위한 것이지 주인의 손을 묶기 위한 것이 아니다.

⚠️ 정직하게: 이 교정은 '엣지를 만들지' 않는다. 노출이 커지면 엣지가 있을 때
   더 벌고 없을 때 더 잃는다. 적중률이 아직 46.9%(n=64, 통계적 확정 불가)라는
   사실은 그대로다 — 다만 연 1%로 굴린 기록은 그 질문에 영원히 답하지 못하고,
   비용·슬리피지·낙폭도 측정되지 않는다. 검증하려면 의미 있게 굴려야 한다.
"""
from __future__ import annotations

import math
import os

# 검증 기간 목표 변동성(연율).
#
# 처음에는 1%로 잡았다가 계산해보고 올렸다. 근거: 20종목 분산 후 총노출
# 100%(무레버리지)일 때 이 포트폴리오의 예상 변동성은 연 8.8%다 — SPY 하나
# 사는 것(연 15~18%)보다 2배 안전하다. 즉 '전액 투자'가 이 계좌에서는
# 공격적인 선택이 아니라 평범한 분산투자다. 반면 연 1%는 8만원 중 9천원만
# 굴린다는 뜻이고, 그 기록은 "실제로 굴리면 어떻게 되는가"라는 질문에
# 아무 답도 주지 못한다 — 페이퍼 계좌의 존재 이유가 사라진다.
#
# 그래서 검증 기간에도 '의미 있게 투자하되 종목 단위 목표(20%)보다는 낮게'로
# 정한다. 리스크의 진짜 한도는 이 숫자가 아니라 아래 무레버리지 상한이다.
VERIFY_TARGET_VOL = 0.12
# 엣지 입증 후 목표(연율) — 종목 단위 목표와 정렬한다.
PROVEN_TARGET_VOL = 0.20
# 사전 변동성 추정의 하한(연율) — 추정이 0에 가까울 때 배수가 폭주하는 것을
# '배수를 자르는' 대신 '추정을 바닥 처리'해서 막는다. 이렇게 해야 실제 한도가
# 항상 총노출(무레버리지선)로 유지된다 — 배수 상한이 먼저 걸리면 신호가 약한
# 날에 노출이 목표에 못 미치고, 그건 문서화된 의도와 다르다(실측에서 실제로
# 배수 25배가 먼저 걸려 총노출이 34%에서 멈추는 것을 확인했다).
# 0으로 나누는 것만 막으면 되므로 아주 작게 잡는다 — 이 값이 실제로 걸리면
# 그것 역시 '노출이 한도'라는 설계에 어긋난다(0.005로 뒀다가 저변동성 구간에서
# 총노출이 32%에 묶이는 것을 실측하고 낮췄다).
MIN_EX_ANTE_VOL = 0.0005
# 스케일 배수 상한 — 최후의 안전핀. 배수가 커도 아래 총노출 상한이 실제 노출을
# 100%로 묶으므로 위험하지 않다(배수는 수단이고 노출이 한도다).
MAX_VOL_SCALE = 200.0
# 총노출 상한 — 1.0 = 레버리지 금지(계좌 자산을 넘겨 사지 않는다).
# 변동성 타깃이 아무리 크게 요구해도 이 선을 넘지 않는다.
MAX_GROSS_EXPOSURE = 1.0
# 게이트 통과 최소 표본(방향 적중 짝) — 90일 시계와 별개의 통계 요건.
MIN_EDGE_SAMPLES = 200


def ex_ante_vol(weights: dict, rets_map: dict,
                periods_per_year: int = 252) -> float | None:
    """현재 목표 비중의 사전 포트폴리오 변동성(연율)을 추정한다.

    종목 간 상관을 무시하지 않는다 — 공분산으로 계산해야 '분산이 실제로
    리스크를 얼마나 줄였는지'가 반영되고, 그만큼 되돌려 키울 수 있다.
    공통 관측일이 부족하면 None(스케일 미적용 — 모르면 건드리지 않는다).
    """
    keys = [k for k in weights if k in rets_map and abs(weights[k]) > 0]
    if len(keys) < 2:
        return None
    series = {}
    for k in keys:
        r = rets_map[k]
        vals = list(r.values()) if isinstance(r, dict) else list(r)
        series[k] = [float(x) for x in vals if x is not None
                     and not (isinstance(x, float) and math.isnan(x))]
    n = min((len(v) for v in series.values()), default=0)
    if n < 20:
        return None
    # 뒤에서 n개로 길이를 맞춘다(최근 구간 정렬 — 날짜 인덱스가 없을 때의 근사)
    cols = {k: v[-n:] for k, v in series.items()}
    means = {k: sum(v) / n for k, v in cols.items()}
    var = 0.0
    for a in keys:
        for b in keys:
            cov = sum((cols[a][i] - means[a]) * (cols[b][i] - means[b])
                      for i in range(n)) / (n - 1)
            var += weights[a] * weights[b] * cov
    if var <= 0:
        return None
    return math.sqrt(var) * math.sqrt(periods_per_year)


def edge_proven(state_dir: str = "state") -> tuple[bool, str]:
    """엣지가 통계로 입증됐는가 — (판정, 사유).

    두 관문을 모두 넘어야 한다:
      ① 판정 시계 완주 — 현재 구조 세대의 관찰 일수가 기준(90일) 이상
      ② 방향 적중률의 윌슨 95% 신뢰구간 하한이 50% 초과 (표본 200건 이상)
    ②는 '동전보다 낫다'를 신뢰구간으로 요구한다 — 점추정이 50%를 넘었다는
    이유로 노출을 키우면, 우리가 그토록 걸러낸 '운 좋은 승자'가 된다.
    """
    try:
        import json

        from quant.live.calibration_guard import collect_pairs
        from quant.live.daily import _generation_info
        from quant.live.explain import _wilson_ci

        gen = _generation_info(state_dir)
        if not gen:
            return False, "판정 시계 정보 없음"
        if gen["days"] < gen["target_days"]:
            # 수정 공지(2026-08-18) — 시계는 개선해도 리셋되지 않는 연속
            # 시계다. 대신 시계가 도는 동안의 구조 변경 횟수를 함께 말한다.
            nv = len(gen.get("versions") or [])
            return False, (f"판정 시계 진행 중 — {gen['feature_set']} "
                           f"{gen['days']}일차/{gen['target_days']}일"
                           + (f" · 그동안 개선 {nv}회 공개" if nv else ""))
        # ⚠️ 보관본(*.pre-*.json)을 빼야 한다(감사 228). 사본이 섞이면 같은
        #    기록이 두 번 세어져 표본 n만 부풀고, 윌슨 하한은 n이 커질수록
        #    올라간다 — 적중 55%에서 n=200(하한 48.1%, 미입증)이 n=400(하한
        #    50.1%, **입증**)으로 뒤집힌다. 표본 복사로 엣지를 만들어내는 것이고,
        #    그 판정이 곧장 목표 변동성을 12%→20%로 올린다.
        from quant.live.ledger_basics import ledger_files
        hists = []
        for f in ledger_files(state_dir):
            try:
                with open(f, encoding="utf-8") as fh:
                    st = json.load(fh)
            except (OSError, ValueError):
                continue
            if str(st.get("market", "")).startswith("portfolio"):
                continue
            hists.append(st.get("history") or [])
        pairs = collect_pairs(hists)
        n = len(pairs)
        if n < MIN_EDGE_SAMPLES:
            return False, f"방향 표본 부족 — {n}/{MIN_EDGE_SAMPLES}건"
        hits = sum(1 for p, h in pairs if (p > 0.5) == (h > 0.5))
        lo, _hi = _wilson_ci(hits / n, n)
        if lo <= 0.5:
            return False, (f"적중률 {hits / n * 100:.1f}% (n={n}) — 95% 하한 "
                           f"{lo * 100:.1f}%가 50% 이하라 동전과 구별 불가")
        return True, (f"적중률 {hits / n * 100:.1f}% (n={n}) — 95% 하한 "
                      f"{lo * 100:.1f}% > 50%")
    except Exception as exc:  # noqa: BLE001 — 판정 실패는 '미입증'으로 취급
        return False, f"판정 불가({exc})"


def target_vol_now(state_dir: str = "state") -> tuple[float, bool, str]:
    """지금 적용할 목표 변동성 — (목표, 입증여부, 사유).

    어드민 설정(portfolio_target_vol)이 있으면 그 값을 쓰되, **미입증
    상태에서는 검증 목표를 상한으로 강제한다** — 설정 실수로 검증 전에
    노출이 커지는 사고를 막는다(리스크는 올릴 때보다 되돌릴 때가 비싸다).
    """
    proven, why = edge_proven(state_dir)
    base = PROVEN_TARGET_VOL if proven else VERIFY_TARGET_VOL
    override = False
    try:
        from quant.utils.settings import load_settings
        s = load_settings()
        raw = s.get("portfolio_target_vol")
        if raw is not None:
            base = float(raw)
        # 소유자의 명시적 우회 — 안전장치는 사고를 막기 위한 것이지
        # 주인의 손을 묶기 위한 것이 아니다. 다만 '실수로 켜지는 일'은
        # 없어야 하므로 별도의 확인 플래그를 요구한다.
        override = bool(s.get("risk_override_ack"))
    except Exception:  # noqa: BLE001 — 설정 없으면 기본값
        pass
    if not proven and not override:
        base = min(base, VERIFY_TARGET_VOL)
    elif not proven and override:
        why = f"⚠️ 소유자 우회(risk_override_ack) — 미입증 상태에서 상향: {why}"
    return base, proven, why


def vol_scale(weights: dict, rets_map: dict, target: float,
              periods_per_year: int = 252,
              max_gross: float = MAX_GROSS_EXPOSURE
              ) -> tuple[float, float | None]:
    """목표 변동성에 맞추는 스케일 배수 — (배수, 사전 변동성 추정치).

    추정 불가면 배수 1.0(모르면 건드리지 않는다). 배수는 세 가지로 잘린다:
      ① 목표/사전추정 — 원하는 크기
      ② MAX_VOL_SCALE — 사전추정이 0에 가까울 때의 폭주 안전핀
      ③ 총노출 상한 — 레버리지 금지선. 실질적으로 이것이 한도다.
    """
    ex = ex_ante_vol(weights, rets_map, periods_per_year)
    if not ex or ex <= 0:
        return 1.0, ex
    # 추정을 바닥 처리한 뒤 배수를 낸다 — 한도는 배수가 아니라 노출이어야 한다
    scale = min(target / max(ex, MIN_EX_ANTE_VOL), MAX_VOL_SCALE)
    gross = sum(abs(w) for w in weights.values())
    if gross > 0 and max_gross > 0:
        scale = min(scale, max_gross / gross)     # 레버리지 금지
    return max(0.0, scale), ex
