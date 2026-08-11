"""킬스위치가 실제로 노출을 줄이는가 — 브레이크가 밟히는지 확인한다.

배경(2026-08-11 감사, 이번 전수조사에서 가장 심각한 발견):
변동성 스케일을 **감쇠된 비중**으로 계산하고 있었다. 킬스위치가 비중을
절반으로 줄이면 스케일러는 "위험이 절반"이라 판단해 배수를 두 배로 올리고,
무레버리지 상한마저 감쇠된 총노출 기준으로 계산되어 **최종 노출이 감쇠 전과
똑같아진다.** 실측: eff_scale 0.25(75% 축소)를 걸어도 총노출 100%.

즉 사이트가 "낙폭 단계별 자동 브레이크"라고 광고하던 장치와 어드민의
'총노출 배수' 손잡이가 **둘 다 아무 일도 하지 않고 있었다.**

순서가 곧 의미다: 변동성 타깃이 '위험 예산'을 정하고, 킬스위치는 그 예산을
잘라낸다. 예산 계산에 이미 잘린 값을 넣으면 브레이크가 사라진다.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.risk.portfolio_vol import MAX_GROSS_EXPOSURE, vol_scale  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _rets(keys, n=90, seed=5):
    rng = random.Random(seed)
    return {k: [rng.gauss(0, 0.015) for _ in range(n)] for k in keys}


def _final_gross(base, rets, target, eff_scale):
    """수정된 순서: 감쇠 전 비중으로 배수를 정하고, 배수 뒤에 감쇠를 곱한다."""
    scale, _ = vol_scale(base, rets, target)
    return sum(abs(v) for v in base.values()) * scale * eff_scale


def test_damping_actually_reduces_exposure():
    keys = [f"s{i}" for i in range(20)]
    base = {k: 0.05 for k in keys}
    rets = _rets(keys)
    full = _final_gross(base, rets, 0.12, 1.0)
    assert abs(full - MAX_GROSS_EXPOSURE) < 1e-9
    for eff in (0.75, 0.5, 0.25):
        got = _final_gross(base, rets, 0.12, eff)
        assert abs(got - full * eff) < 1e-9, f"eff={eff}에서 브레이크가 안 먹는다"


def test_pause_means_zero():
    keys = [f"s{i}" for i in range(20)]
    base = {k: 0.05 for k in keys}
    assert _final_gross(base, _rets(keys), 0.12, 0.0) == 0.0


def test_damped_input_would_neutralize_the_brake():
    """옛 방식이 왜 틀렸는지를 고정한다 — 회귀하면 이 테스트가 증인이 된다."""
    keys = [f"s{i}" for i in range(20)]
    base = {k: 0.05 for k in keys}
    rets = _rets(keys)
    for eff in (0.5, 0.25):
        damped = {k: v * eff for k, v in base.items()}
        scale, _ = vol_scale(damped, rets, 0.12)          # 옛 계산
        old_gross = sum(abs(v) for v in damped.values()) * scale
        assert abs(old_gross - MAX_GROSS_EXPOSURE) < 1e-9  # 감쇠가 사라졌다
        assert old_gross > _final_gross(base, rets, 0.12, eff)


def test_daily_uses_undamped_weights_for_the_budget():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "base_w = {k: w * slices.get(k, 1.0 / n) for k, w in weights.items()}" in src
    assert "vol_scale(base_w, rets_map, tgt_vol)" in src
    # 감쇠된 비중을 예산 계산에 넣던 옛 코드가 되살아나면 안 된다
    assert "vol_scale(pre_w" not in src
    # 장부에 예산(scale)과 브레이크(damp)를 따로 남긴다
    assert '"damp"' in src and '"applied"' in src


# ── 같은 결함이 실적 가드·켈리 상한에도 있었다 ────────────────
#
# 둘 다 '비중 자체'에 곱하거나 잘라 넣고 있었는데, 그 뒤에 오는 변동성
# 스케일러가 "위험이 줄었다"고 보고 전체를 되돌려 키운다. 결과적으로
#   · 실적 가드: 절반으로 줄인 만큼 다시 커져 상대 비중만 바뀐다
#   · 켈리 상한: 상한 위로 다시 올라간다
# 공분산은 실적 발표를 모르므로, 하필 위험한 날에 목표보다 더 실린다.


def test_event_guard_survives_the_scaler():
    keys = [f"s{i}" for i in range(20)]
    base = {k: 0.05 for k in keys}
    rets = _rets(keys)
    scale, _ = vol_scale(base, rets, 0.12)

    guarded = "s0"
    # 수정 후: 감쇠는 스케일 뒤에 곱해지므로 그 종목만 정확히 절반이 된다
    after = {k: v * scale * (0.5 if k == guarded else 1.0)
             for k, v in base.items()}
    plain = {k: v * scale for k, v in base.items()}
    assert abs(after[guarded] - plain[guarded] * 0.5) < 1e-12
    # 그리고 계좌 전체 노출도 그만큼 줄어든다(위험한 날엔 덜 싣는다)
    assert sum(after.values()) < sum(plain.values())


def test_kelly_cap_binds_after_scaling():
    keys = [f"s{i}" for i in range(20)]
    base = {k: 0.05 for k in keys}
    scale, _ = vol_scale(base, _rets(keys), 0.12)
    kcap = 0.02
    capped = min(base["s0"] * scale, kcap)
    assert capped == kcap, "스케일 뒤에 걸어야 상한이 실제로 구속한다"


def test_guards_are_applied_after_the_scaler_in_source():
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "eff = w * eff_scale * vscale * guard_damp.get(key, 1.0)" in src
    assert "kelly_caps.get(key)" in src
    # 비중에 직접 곱하거나 잘라 넣던 옛 코드가 되살아나면 안 된다
    assert "weights[key] = float(weights[key] * ef)" not in src
    assert "np.clip(weights[key], -kcap, kcap)" not in src
    # 기록되는 총노출도 감쇠·상한을 반영해야 한다
    assert "def _applied(k: str, w: float)" in src
