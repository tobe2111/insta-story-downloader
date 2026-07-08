"""검증 HTML 리포트 렌더러 테스트. 렌더러 코어는 순수 stdlib(로컬 실행 가능),
오케스트레이터는 pandas(백테스트) — CI.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 렌더러를 패키지 __init__(pandas 지연이지만 안전) 없이 파일에서 직접 로드 → stdlib 실행
_spec = importlib.util.spec_from_file_location(
    "vr", str(Path(__file__).resolve().parent.parent
              / "quant" / "reporting" / "validation_report.py"))
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)


def _sample_html(**over):
    kw = dict(
        title="테스트 검증", dsr=0.97, n_trials=4, oos_sharpe=1.2,
        oos_return=0.18, oos_mdd=-0.12, equity=[10000, 10500, 10300, 11200, 11800],
        pbo=0.1, pbo_lambdas=[0.2, 0.5, -0.1, 0.8, 0.3, 0.6, -0.2, 0.4],
        mean_oos_rank=0.75, prob_oos_loss=0.1,
        cpcv_sharpe_mean=1.1, cpcv_sharpe_min=0.6, cpcv_sharpe_std=0.3,
        cpcv_worst_return=0.04, cpcv_path_sharpes=[0.6, 0.9, 1.1, 1.3, 1.5], n_paths=5)
    kw.update(over)
    return vr.build_validation_html(**kw)


def test_report_renders_and_has_sections():
    doc = _sample_html()
    assert "<svg" in doc                       # 그래프 렌더됨
    assert "OOS 자본곡선" in doc and "PBO 분포" in doc and "CPCV" in doc
    assert "보장되지 않습니다" in doc           # 정직성 고지 필수
    assert doc.count("<svg") == 3              # 자본곡선 + PBO + CPCV


def test_verdict_pass_when_all_good():
    doc = _sample_html(dsr=0.98, pbo=0.05, cpcv_sharpe_min=0.7)
    assert "신뢰할 만함" in doc


def test_verdict_fail_when_any_fails():
    doc = _sample_html(dsr=0.5, pbo=0.05, cpcv_sharpe_min=0.7)   # DSR fail
    assert "실전 금지" in doc
    doc2 = _sample_html(dsr=0.98, pbo=0.7, cpcv_sharpe_min=0.7)  # PBO fail
    assert "실전 금지" in doc2


def test_verdict_warn_when_ambiguous():
    doc = _sample_html(dsr=0.8, pbo=0.1, cpcv_sharpe_min=0.5)    # DSR warn, 나머지 pass
    assert "주의" in doc


def test_handles_empty_equity_gracefully():
    doc = _sample_html(equity=[])
    assert "데이터가 부족" in doc               # 크래시 없이 안내


def test_svg_area_and_hist_are_stdlib():
    assert "polyline" in vr._svg_area([1, 2, 3, 2, 4])
    assert "<rect" in vr._svg_hist([0.1, 0.2, 0.2, 0.9, -0.3])


def test_render_validation_report_end_to_end(tmp_path):
    """오케스트레이터가 실제 검증 3종을 돌려 파일을 저장한다(pandas — CI)."""
    from quant.data import SyntheticDataProvider
    from quant.strategies import MovingAverageCross

    df = SyntheticDataProvider(seed=4).get_ohlcv("V", "1d", limit=600)
    out = vr.render_validation_report(
        df, MovingAverageCross, {"fast": [5, 10], "slow": [40, 60]},
        path=tmp_path / "validate.html", is_window=250, oos_window=125)
    assert out.exists()
    doc = out.read_text(encoding="utf-8")
    assert "<svg" in doc and "판정:" in doc
