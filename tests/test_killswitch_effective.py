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
    """옛 실수가 되살아나지 않았는지만 본다(부정형).

    ⚠️ 예전에는 `def _applied(k: str, w: float)`가 소스에 있는지도 확인했다.
       "기록되는 총노출도 감쇠·상한을 반영한다"는 뜻이었지만, 실제로 본 것은
       **함수 이름의 존재**였다. 2026-08-12에 주문과 기록이 같은 값을 쓰도록
       계산을 한 곳(_target_w → _fit_to_budget)으로 모으자 — 즉 그 주장을
       **더 강하게 만들었는데** — 이 검사가 깨졌다.
       확인해야 할 것(감쇠·상한이 기록에 반영되는가)은 아래 행동 검사로 옮겼다.
    """
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    # 비중에 직접 곱하거나 잘라 넣던 옛 코드가 되살아나면 안 된다
    assert "weights[key] = float(weights[key] * ef)" not in src
    assert "np.clip(weights[key], -kcap, kcap)" not in src


def test_the_recorded_exposure_reflects_the_damping(tmp_path, monkeypatch):
    """감쇠(킬스위치×어드민 배수)가 **장부의 총노출**에 반영되는가.

    소스에 무엇이 적혀 있는지가 아니라, 진짜 배치를 두 번 돌려 값을 비교한다.
    감쇠 0.5면 총노출도 정확히 절반이어야 한다 — 부등호로 두면 스케일러가
    되돌려 키우던 옛 결함(2026-08-11)이 조금 남아도 통과한다.
    """
    import json

    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    import quant.utils.settings as us

    def _run(scale: float) -> float:
        d = tmp_path / f"s{scale}"
        monkeypatch.setattr(
            us, "load_settings",
            lambda path=us.SETTINGS_PATH: {"trading_paused": False,
                                           "exposure_scale": scale,
                                           "social_post": True, "note": "",
                                           "portfolio_target_vol": None})
        save_champions({f"synthetic:D{i}": {"strategy": "ma_cross",
                                            "params": {"fast": 10, "slow": 30},
                                            "promotions": 0}
                        for i in range(3)}, str(d))
        p = d / "paper"
        p.mkdir(parents=True, exist_ok=True)
        (p / "portfolio_ALL.json").write_text(json.dumps({
            "market": "portfolio", "symbol": "ALL",
            "start_cash": 1_000_000.0, "cash": 1_000_000.0, "positions": {},
            "base_prices": {}, "last_bar": None, "history": [],
        }), encoding="utf-8")
        return run_daily_portfolio(
            [("synthetic", f"D{i}") for i in range(3)], lookback=200,
            state_dir=str(d), require_real_data=False)["weight"]

    full = _run(1.0)
    assert full > 0, "평시 노출이 0이면 이 비교가 헛것이 된다"
    assert abs(_run(0.5) - full * 0.5) < 1e-4, (
        "노출 배수를 절반으로 줄였는데 기록된 총노출이 절반이 아니다")
