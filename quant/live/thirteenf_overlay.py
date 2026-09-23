"""13F 겹쳐 담기 → 확신 오버레이. **단독 트리거가 아니다.**

사장님 결정(2026-09-22): 저명 투자자들이 겹쳐 담은 종목이면, *이미 모델이
사겠다고 한* 신호를 조금 더 키운다. 새로 사게 만들지는 않는다.

이 파일이 지키는 단 하나의 안전 성질:

    모델이 관망(신호 0)이거나 팔자(음수)면, 아무리 많은 저명 투자자가
    그 종목을 겹쳐 담았어도 **그대로 관망·팔자다.**

    오버레이는 0을 매수로 바꿀 수 없다. 겹쳐 담기는 확신의 '보조'이지
    매수의 '이유'가 아니다 — 13F는 최대 4.5개월 묵은 참고이기 때문이다
    (quant/data/thirteenf 머리말의 세 함정).

그래서 오버레이는 **양수 신호에만 곱하는 1.0~1.15 배수**다. 개수가 많을수록
커지되 상한이 있고, 곱한 뒤에도 1.0을 넘지 않게 자른다(사이징은 0~1이 몫의
비율이다). 확신도 눈금 재보정(quant/live/conviction)과 같은 자리·같은 순서로
곱해지지만, 그것과 별개의 장치다 — 하나는 확률→금액 눈금을 고치고, 이것은
외부 참고를 얹는다.

⚠️ 본 계좌(100만 챌린지)에는 걸지 않는다. 재보정과 같은 이유다 — 실제 원금이
   걸린 쪽의 위험을 외부 참고로 키우지 않는다. 실험(미국 장중 트랙)에서만
   신호 경로에 곱한다.
"""
from __future__ import annotations

# 이만큼(명) 겹치면 최대 보너스. 저명 투자자 셋이 같은 종목을 들면 '겹쳤다'.
CLUSTER_FULL = 3

# 증거가 없을 때의 기본 세기 — 양수 신호를 15%까지만 키운다. 이건 사람이
# 정한 '중립' 값이지 최적값이 아니다: 13F가 실제로 도움이 되는지 아직 아무도
# 재지 못했기 때문이다(과거 13F 시계열이 있어야 잰다).
NEUTRAL_BONUS = 0.15
MAX_BONUS = NEUTRAL_BONUS          # 옛 이름 — 기본값으로만 남긴다(호환)

# 사장님 지시(2026-09-23): *"13F의 영향을 상당히 크게 비중을 두는게 좋을듯."*
# 그런데 매매 로직의 세기를 사람이 손으로 크게 잡는 것은 2026-08-27 방침
# ("투자 로직은 기계가 개선한다")에 어긋나고, 무엇보다 **근거가 없다.**
# 그래서 상한만 크게 열고(최대 +100%), 그 안에서 **얼마를 쓸지는 기계가
# 증거로 정한다**(choose_strength). 증거가 없으면 중립(0.15)에 머문다 —
# 낡은 참고 데이터에 믿음만으로 크게 걸지 않는다.
BONUS_CEILING = 1.0
STRENGTH_CHOICES = [0.0, 0.15, 0.30, 0.50, 1.0]

# 세기를 올리려면 넘어야 하는 관문 — 패널 관문과 같은 자를 빌린다.
# ⚠️ 관측 단위는 **날짜(분기 제출)**다(quant.live.thirteenf_tune.measure_edge).
#    13F는 분기 1회라 날짜가 귀하다 — 여덟 분기(약 2년)는 있어야 '재 봤다'고
#    한다. 종목 수로 이 수를 대신하지 않는다(패널 관문과 같은 규칙).
MIN_EDGE_OBS = 8         # 이보다 관측(날짜)이 적으면 '아직 모른다' → 중립
EDGE_T_GATE = 1.35       # 패널 관문 문턱(PANEL_T_REF)과 같은 값

# 이 오버레이가 켜진 날.
ADOPTED_ON = "2026-09-22"
TUNED_ON = "2026-09-23"            # 세기를 기계가 정하도록 바꾼 날

STALENESS_NOTE = (
    "13F 공시는 분기말 후 최대 45일 뒤에야 나오고 롱·미국주식만 담깁니다 — "
    "우리가 보는 순간 그 매수는 최대 4.5개월 묵은 것이라, 저명 투자자가 "
    "'지금 사라'는 신호가 아니라 '지난 분기에 들고 있었다'는 참고입니다."
)

RULE = {
    "on": TUNED_ON,
    "what": "여러 저명 투자자(13F 공시)가 겹쳐 담은 미국 종목에 한해, 이미 "
            "모델이 사겠다고 한 신호를 키웁니다. **얼마나 키울지(최대 +100%)는 "
            "기계가 과거 13F 기록의 실제 성적으로 정합니다** — 증거가 없으면 "
            "중립(+15%)에 머뭅니다.",
    "why": "겹쳐 담기(cluster)는 약하게나마 문서화된 신호입니다. 세기를 사람이 "
           "손으로 크게 잡지 않는 이유는, 매매 로직은 기계가 증거로 개선한다는 "
           "방침 때문이고 무엇보다 13F가 도움이 되는지 아직 확인되지 않았기 "
           "때문입니다. 매수를 새로 만들지는 않습니다 — 모델이 관망(0)이면 "
           "아무리 겹쳐도, 세기가 아무리 커도 그대로 관망입니다. 실험 트랙에만 "
           "걸고, 본 계좌에는 걸지 않습니다.",
    "caveat": STALENESS_NOTE,
}


def choose_strength(edge: dict | None) -> dict:
    """겹쳐 담기의 **측정된 성적**으로 오버레이 세기를 정한다(사람이 아니라).

    edge = {"mean_diff", "t", "n"} — 과거 13F 기록에서 '겹쳐 담긴 종목이 그 뒤
    실제로 더 올랐나'를 point-in-time으로 잰 값(quant.live.thirteenf_tune).

    규칙(패널 관문과 같은 정신):
      · 관측이 적으면(n < MIN_EDGE_OBS) → **중립**. 못 잰 것을 큰 확신으로
        읽지 않는다.
      · 앞선 증거가 없으면(mean_diff ≤ 0 또는 t < 관문) → **중립**.
      · 유의하게 앞설 때만 t에 비례해 상한 쪽으로 올린다. 자기기만이 아니라
        측정이 세기를 정한다.

    돌려주는 것은 {"bonus", "why", "n", "t", "mean_diff"}.
    """
    n = int((edge or {}).get("n") or 0)
    try:
        t = float((edge or {}).get("t"))
        md = float((edge or {}).get("mean_diff"))
    except (TypeError, ValueError):
        t = md = 0.0
    if n < MIN_EDGE_OBS:
        return {"bonus": NEUTRAL_BONUS, "n": n, "t": t, "mean_diff": md,
                "why": f"관측 {n} < {MIN_EDGE_OBS} — 아직 모른다. 중립 유지."}
    if not (md > 0.0) or t < EDGE_T_GATE:
        return {"bonus": NEUTRAL_BONUS, "n": n, "t": round(t, 3),
                "mean_diff": md,
                "why": (f"앞선다는 증거가 약하다(t={t:.2f} < {EDGE_T_GATE} 또는 "
                        "차이≤0) — 중립 유지.")}
    # 유의: t가 문턱을 넘은 만큼 상한 쪽으로. 문턱에서 0.15, t≥3에서 상한.
    frac = min(1.0, (t - EDGE_T_GATE) / (3.0 - EDGE_T_GATE)) if t < 3.0 else 1.0
    target = NEUTRAL_BONUS + frac * (BONUS_CEILING - NEUTRAL_BONUS)
    # STRENGTH_CHOICES 중 target 이하의 가장 큰 값(계단식 — 미세 조정으로
    # 과최적화되지 않게).
    pick = max([c for c in STRENGTH_CHOICES if c <= target + 1e-9]
               or [NEUTRAL_BONUS])
    pick = max(pick, NEUTRAL_BONUS)
    return {"bonus": pick, "n": n, "t": round(t, 3), "mean_diff": md,
            "why": (f"과거 겹쳐 담긴 종목이 유의하게 앞섰다(t={t:.2f} ≥ "
                    f"{EDGE_T_GATE} · 관측 {n}) — 세기를 {pick:.2f}로 올린다.")}


def overlay_scale(sym: str, cluster: dict | None,
                  *, full: int = CLUSTER_FULL, max_bonus: float = MAX_BONUS) -> float:
    """이 종목의 양수 신호에 곱할 배수(1.0~1.0+max_bonus).

    겹쳐 담기가 없거나 모르면 1.0(그대로). 개수가 full 이상이면 상한.
    """
    info = (cluster or {}).get(sym)
    if not isinstance(info, dict):
        return 1.0
    try:
        n = int(info.get("count") or 0)
    except (TypeError, ValueError):
        return 1.0
    if n <= 0 or full <= 0:
        return 1.0
    frac = min(n, full) / float(full)
    return 1.0 + max_bonus * frac


def apply_overlay(signal, sym: str, cluster: dict | None,
                  *, full: int = CLUSTER_FULL, max_bonus: float = MAX_BONUS):
    """신호 하나에 오버레이를 얹는다. **양수만** 키운다.

    · None/NaN → 그대로(모른다는 뜻을 지어내지 않는다).
    · 0 이하 → 그대로(겹쳐 담아도 살 이유가 없으면 사지 않는다 — 단독
      트리거가 아니라는 성질이 여기서 지켜진다).
    · 양수 → 배수를 곱하고 1.0에서 자른다(몫의 비율은 100%를 못 넘는다).
    """
    if signal is None:
        return None
    try:
        x = float(signal)
    except (TypeError, ValueError):
        return None
    if x != x:                              # NaN
        return None
    if x <= 0.0:
        return x                            # 관망·팔자는 겹쳐 담기로 뒤집히지 않는다
    x *= overlay_scale(sym, cluster, full=full, max_bonus=max_bonus)
    return min(1.0, x)


def cluster_public(snapshot: dict | None) -> dict:
    """공개 보고용 요약 — 겹친 종목만, 개수 내림차순. 화면이 지어내지 않게."""
    cluster = (snapshot or {}).get("cluster") or {}
    names = []
    for sym, info in cluster.items():
        if not isinstance(info, dict) or int(info.get("count") or 0) <= 0:
            continue
        names.append({
            "symbol": sym,
            "count": int(info.get("count") or 0),
            "filers": list(info.get("filers") or []),
            "as_of": info.get("as_of"),
        })
    names.sort(key=lambda r: (-r["count"], r["symbol"]))
    return {
        "names": names,
        "fetched_on": (snapshot or {}).get("fetched_on"),
        "filers_total": (snapshot or {}).get("filers_total"),
        "filers_seen": (snapshot or {}).get("filers_seen"),
        "caveat": STALENESS_NOTE,
    }
