"""배분이 **종목 목록 순서에 좌우되면 안 된다** (감사 147).

HRP는 상관 구조를 나무로 읽어 예산을 나눈다. 그런데 통계적으로 동일한
자산들 사이에서 단일 연결 군집의 '잎 순서'는 **입력 열 순서**로 갈리고,
재귀 이분은 그 순서를 그대로 비중으로 옮긴다. 고치기 전 실측:

    A,E,B,F,C,D →  A 0.127 · B 0.125 · C 0.487 · D 0.259
    F,C,A,D,E,B →  A 0.128 · B 0.483 · C 0.127 · D 0.260

같은 데이터인데 목록 순서만 바꿔서 한 종목 비중이 **4배** 뛴다.
호출 쪽 열 순서는 rets_map(=AUTO_TARGETS) 삽입 순서라, 종목을 한 줄 옮겨
넣거나 하나가 데이터 실패로 빠지는 것만으로 어제와 다른 포트폴리오가
나간다. 재현성이 이 시스템의 전제인데(env_fingerprint·시드 고정) 배분에는
그 규칙이 걸려 있지 않았다.

ERC는 같은 병이 없다(반복법이 대칭이라 순서 무관, 실측 차이 8e-17).
`_xsec_tilt`도 "동률은 평균 순위 — 유니버스 나열 순서가 배분을 좌우하면
안 된다"고 이미 못 박혀 있었다. **HRP 한 곳만 빠져 있었다**(FROZEN_IDEAS ⑭).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.daily import _erc_slices  # noqa: E402
from quant.live.hrp import hrp_weights  # noqa: E402

N = 250
IDX = pd.date_range("2025-01-01", periods=N, freq="D")
PERMS = [
    ["A", "E", "B", "F", "C", "D"],
    ["F", "C", "A", "D", "E", "B"],
    ["D", "C", "B", "A", "F", "E"],
    ["E", "F", "A", "B", "C", "D"],
]


def _panel() -> pd.DataFrame:
    """저변동 4종(A~D)과 고변동 2종(E,F). 각 군집은 같은 요인을 공유한다."""
    rng = np.random.default_rng(2)
    f1, f2 = rng.normal(0, 1, N), rng.normal(0, 1, N)

    def arm(f, scale):
        return scale * (f + 0.1 * rng.normal(0, 1, N))

    return pd.DataFrame(
        {"A": arm(f1, .002), "E": arm(f2, .03), "B": arm(f1, .002),
         "F": arm(f2, .03), "C": arm(f1, .002), "D": arm(f1, .002)},
        index=IDX)


def test_hrp_gives_the_same_weights_whatever_the_column_order():
    df = _panel()
    base = hrp_weights(df[PERMS[0]])
    assert base, "전제가 깨졌다 — 정상 입력에서 HRP가 답을 못 냈다"
    for perm in PERMS[1:]:
        got = hrp_weights(df[perm])
        worst = max(abs(base[k] - got[k]) for k in base)
        assert worst < 1e-12, (
            f"열 순서 {','.join(perm)}에서 비중이 최대 {worst:.4f} 달라진다 — "
            f"{ {k: round(base[k], 3) for k in sorted(base)} } vs "
            f"{ {k: round(got[k], 3) for k in sorted(got)} }")


def test_hrp_still_prefers_the_quiet_cluster():
    """대조군 — 순서를 고정하느라 HRP 자체를 망가뜨리지 않았는가.

    변동성이 15배 큰 군집(E,F)에 예산이 거의 가지 않아야 한다.
    """
    w = hrp_weights(_panel())
    assert w["E"] + w["F"] < 0.02, (
        f"고변동 군집이 예산의 {w['E'] + w['F']:.1%}를 가져간다 — "
        "위험 패리티가 작동하지 않는다")
    assert abs(sum(w.values()) - 1.0) < 1e-12


def test_erc_is_order_free_too():
    """형제 확인 — ERC는 원래 순서 무관하다(반복법이 대칭)."""
    df = _panel()
    base = _erc_slices({c: df[c] for c in PERMS[0]}, 6)
    assert base, "전제가 깨졌다 — 정상 입력에서 ERC가 답을 못 냈다"
    for perm in PERMS[1:]:
        got = _erc_slices({c: df[c] for c in perm}, 6)
        assert max(abs(base[k] - got[k]) for k in base) < 1e-9, perm


def test_a_dropped_symbol_keeps_the_risk_level_decision():
    """한 종목이 데이터 실패로 빠져도 **위험 수준 판단**은 그대로여야 한다.

    ⚠️ 여기서 하나 배웠다. 처음엔 '남은 종목의 상대 순위도 유지되어야 한다'로
       썼는데 **HRP는 그걸 만족할 수 없다.** 유니버스가 바뀌면 군집 나무가
       바뀌고 재귀 이분의 절반 경계(len//2)도 바뀐다. 실측:

           조용한 군집 합   0.9978 → 0.9979   (판단은 그대로)
           군집 내부 회전율 36.6%             (누가 얼마인지는 뒤바뀐다)

       통계적으로 동일한 네 자산 사이의 재배치라 위험은 변하지 않는다 —
       비용은 순수하게 **회전(수수료)**이다. 고칠 수 있는 결함이 아니라
       재귀 이분의 성질이므로, 고치는 대신 못 박아 둔다. 이 수치가 커지면
       배분 평활을 검토할 근거가 된다.
    """
    df = _panel()
    full = hrp_weights(df)
    part = hrp_weights(df.drop(columns=["F"]))
    assert full and part

    quiet_f = sum(full[k] for k in "ABCD")
    quiet_p = sum(part[k] for k in "ABCD")
    assert abs(quiet_f - quiet_p) < 0.01, (
        f"고변동 종목 하나가 빠졌더니 조용한 군집 예산이 {quiet_f:.4f} → "
        f"{quiet_p:.4f}로 바뀐다 — 위험 수준 판단이 유니버스에 흔들린다")

    turnover = sum(abs(full[k] / quiet_f - part[k] / quiet_p) for k in "ABCD") / 2
    assert turnover < 0.5, (
        f"군집 내부 회전율 {turnover:.1%} — 신호가 그대로인데 절반 넘게 갈아탄다")


# ── 군집 분산은 역분산 가중으로 재야 한다 ─────────────────────


def test_cluster_risk_is_measured_by_its_safest_achievable_mix():
    """군집의 '위험'은 **그 군집을 잘 들었을 때**의 분산이다.

    HRP는 군집 안을 역분산 비중으로 들었다고 보고 군집 분산을 잰다. 이걸
    균등가중으로 재면 군집 안의 가장 시끄러운 자산 하나가 군집 전체를
    '위험하다'고 낙인찍는다 — 조용한 자산이 그 옆에 있다는 이유만으로
    예산을 잃는다.

    정답을 아는 데이터: 군집1 = {변동성 0.1%, 변동성 5%}, 군집2 = {0.6%, 0.6%}.
    군집1은 lo 하나만 들면 군집2보다 훨씬 안전하다 → 예산 대부분을 받아야 한다.

        역분산으로 재면   군집1 = 0.973   (lo 0.972 · hi 0.000)
        균등가중으로 재면 군집1 = 0.053   ← 조용한 lo가 hi 때문에 버려진다
    """
    rng = np.random.default_rng(2)
    f1, f3 = rng.normal(0, 1, N), rng.normal(0, 1, N)

    def arm(f, scale):
        return scale * (f + 0.1 * rng.normal(0, 1, N))

    df = pd.DataFrame({"lo": arm(f1, .001), "hi": arm(f1, .05),
                       "m1": arm(f3, .006), "m2": arm(f3, .006)}, index=IDX)
    w = hrp_weights(df)
    assert w, "전제가 깨졌다 — HRP가 답을 못 냈다"
    assert w["lo"] + w["hi"] > 0.8, (
        f"조용한 자산이 든 군집이 예산의 {w['lo'] + w['hi']:.1%}밖에 못 받는다 — "
        "군집 분산을 균등가중으로 재고 있다")
    assert w["lo"] > 0.8 and w["hi"] < 0.01, (
        f"군집 안 배분도 역분산이어야 한다 — lo {w['lo']:.3f} · hi {w['hi']:.3f}")
