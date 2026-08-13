"""줄이라는 신호를 반만 듣지 않는다 — 신호 평활 (감사 230).

배경:
  `_smooth_weights`의 독스트링은 이렇게 적혀 있었다.

      "**관망(0)으로의 전환은 평활하지 않는다** — '팔아라'는 신호를 반만
       듣는 것은 위험 관리가 아니라 미련이다. 새로 진입(0→양수)할 때만
       서서히 들어간다."

  그런데 코드는 **0이 아닌 모든 변화**를 똑같이 평활했다. 즉 원칙이
  지켜지는 곳은 목표가 **정확히 0**일 때뿐이었다. 실측(alpha=0.3):

      어제 0.500 → 오늘 목표 0.006  ⇒  실제 0.352
      어제 0.500 → 오늘 목표 0.050  ⇒  실제 0.365
      어제 0.500 → 오늘 목표 0.000  ⇒  실제 0.000   (여기서만 지켜짐)

  전략이 "0.6%만 들고 있어라"라고 말한 날 계좌는 35%를 들고 있었다.
  0.006과 0.0은 위험 관리로는 사실상 같은 지시인데 한쪽만 즉시 반영됐다 —
  가드가 있다는 것이 막힌다는 뜻은 아니다. 문턱이 '정확히 0'이라는 등호였을
  뿐이다(감사 198·213과 같은 계열).

핵심 계약:
  · 키울 때만 서서히 — 줄일 때는 크게 줄이면 즉시
  · 작은 떨림에는 여전히 평활이 걸린다(회전율 통제라는 원래 목적)
  · 방향 전환은 청산보다 강한 신호다
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live.daily import (  # noqa: E402
    SIGNAL_SMOOTH_ALPHA, SMOOTH_CUT_RATIO, _smooth_weights,
)


# ── ① 줄이라는 신호 ───────────────────────────────────────────


def test_a_near_liquidation_is_not_softened_into_a_big_position():
    """이것이 감사 230의 결함이다 — 고치기 전에는 0.352가 나왔다."""
    out = _smooth_weights({"k": 0.006}, {"k": 0.5})
    assert out["k"] == 0.006, (
        f"전략은 0.6%를 말했는데 계좌는 {out['k'] * 100:.1f}%를 든다")


def test_cutting_to_a_tenth_is_immediate():
    out = _smooth_weights({"k": 0.05}, {"k": 0.5})
    assert out["k"] == 0.05


def test_the_exact_zero_case_still_works():
    """원래 지켜지던 유일한 경우 — 회귀 방지."""
    assert _smooth_weights({"k": 0.0}, {"k": 0.5})["k"] == 0.0


def test_the_threshold_is_exactly_the_declared_ratio():
    """경계 고정 — cut배 '이하'에서 즉시, 그보다 크면 평활."""
    prev = 0.4
    at = prev * SMOOTH_CUT_RATIO                    # 정확히 문턱
    over = at + 1e-6                                # 문턱보다 조금 큼
    assert _smooth_weights({"k": at}, {"k": prev})["k"] == at
    got = _smooth_weights({"k": over}, {"k": prev})["k"]
    assert got > over, "문턱을 살짝 넘겼는데도 평활이 안 걸렸다"


# ── ② 작은 떨림에는 여전히 평활이 걸린다 (대조군) ─────────────


def test_a_small_wobble_is_still_smoothed():
    """⚠️ 이 대조군이 없으면 '전부 즉시 반영'으로 고쳐도 위 검사가 통과한다.

    평활의 원래 목적(확률이 0.55↔0.62에서 떠는 것만으로 전 종목이 매매되는
    것을 막기)이 살아 있어야 한다.
    """
    prev, new = 0.50, 0.45                          # 10% 축소 — 떨림 수준
    got = _smooth_weights({"k": new}, {"k": prev})["k"]
    expect = SIGNAL_SMOOTH_ALPHA * new + (1 - SIGNAL_SMOOTH_ALPHA) * prev
    assert abs(got - expect) < 1e-12
    assert got > new, "작은 축소까지 즉시 반영하면 회전율 통제가 사라진다"


def test_scaling_up_is_still_gradual():
    """키우는 쪽은 그대로 서서히 — 이 규칙은 바뀌지 않았다."""
    got = _smooth_weights({"k": 0.5}, {"k": 0.1})["k"]
    expect = SIGNAL_SMOOTH_ALPHA * 0.5 + (1 - SIGNAL_SMOOTH_ALPHA) * 0.1
    assert abs(got - expect) < 1e-12
    assert got < 0.5


def test_a_fresh_entry_still_eases_in():
    """어제 없던 종목은 목표의 alpha배로 들어간다(첫날 배치가 이 경로다)."""
    got = _smooth_weights({"k": 0.4}, {})["k"]
    assert abs(got - SIGNAL_SMOOTH_ALPHA * 0.4) < 1e-12


# ── ③ 방향 전환 ───────────────────────────────────────────────


def test_a_reversal_does_not_leave_us_on_the_old_side():
    """"반대로 가라"는 청산보다 강한 신호다.

    지금은 전 전략이 long-only(allow_short=False)라 도달하지 않지만,
    숏이 켜지는 날 평활이 **옛 방향에 남게** 만드는 것을 막아 둔다.
    고치기 전 계산: 0.3×(-0.5) + 0.7×(+0.5) = **+0.20** — 숏 신호를 받고도
    롱을 20% 들고 있게 된다.
    """
    out = _smooth_weights({"k": -0.5}, {"k": 0.5})
    assert out["k"] == -0.5, f"숏 신호인데 {out['k']:+.2f}를 든다"
    out = _smooth_weights({"k": 0.5}, {"k": -0.5})
    assert out["k"] == 0.5


# ── ④ 상수와 설명이 어긋나지 않는다 ───────────────────────────


def test_the_comment_does_not_describe_a_different_number():
    """주석이 값보다 오래 살아 있었다 — "0.5는 2일 평활"인데 값은 0.3이었다.

    설명이 코드를 설명하지 못하면 그 설명은 거짓말이다.
    """
    import ast

    src = (Path(__file__).resolve().parent.parent
           / "quant" / "live" / "daily.py").read_text("utf-8")
    lines = src.split("\n")
    i = next(n for n, ln in enumerate(lines)
             if ln.startswith("SIGNAL_SMOOTH_ALPHA"))
    comment = "\n".join(lines[max(0, i - 8):i])
    assert str(SIGNAL_SMOOTH_ALPHA) in comment, (
        f"주석이 실제 값({SIGNAL_SMOOTH_ALPHA})을 말하지 않는다:\n{comment}")
    # 값 자체는 AST로 확인 — 주석에 숫자가 있다고 값이 그런 것은 아니다
    tree = ast.parse(src)
    got = next(n.value.value for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               and any(getattr(t, "id", "") == "SIGNAL_SMOOTH_ALPHA"
                       for t in n.targets))
    assert got == SIGNAL_SMOOTH_ALPHA
