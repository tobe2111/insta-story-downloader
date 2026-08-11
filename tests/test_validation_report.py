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


# ── 돌지 못한 검증을 판정처럼 그리지 않는다 (감사 52) ─────────


def test_failed_stage_shows_measurement_failure_not_a_number():
    """크래시한 단계에 그럴듯한 기본값을 채워 넣지 않는다.

    예전 render_validation_report는 PBO가 터지면 조용히 0.5를 넣었다.
    화면에는 "PBO 50% · IS 1등이 OOS서 손실일 확률 50%"라는, 아무도
    측정한 적 없는 숫자가 측정값처럼 떴다. 세 카드가 모두 채워져 있으니
    보는 사람은 세 검증이 다 돌았다고 읽는다 — 실패가 판정으로 보이는
    전형적 형태다.
    """
    doc = _sample_html(failed={"pbo": "PBO — ValueError: 표본 부족"})
    assert "측정 실패" in doc
    assert "돌지 못한 검증이 있습니다" in doc
    assert "표본 부족" in doc                     # 이유를 그대로 남긴다
    assert "PBO 50%" not in doc and "50%</div>" not in doc


def test_overall_verdict_is_never_pass_when_a_stage_did_not_run():
    """전부 초록이어도, 한 단계가 안 돌았으면 '신뢰할 만함'이 될 수 없다."""
    ok = _sample_html()
    assert "신뢰할 만함" in ok                    # 기준선: 세 검증 다 통과
    for stage in ("wf", "pbo", "cpcv"):
        doc = _sample_html(failed={stage: "테스트"})
        assert "신뢰할 만함" not in doc, stage
        assert "판정 불가" in doc, stage


def test_failure_does_not_masquerade_as_a_clean_drawdown():
    """워크포워드가 터지면 낙폭 0.00%가 '무손실'처럼 보이던 자리."""
    doc = _sample_html(failed={"wf": "테스트"}, oos_mdd=0.0, oos_return=0.0)
    assert "측정 실패" in doc and "판정 불가" in doc


def test_orchestrator_records_failure_reasons():
    src = (Path(__file__).resolve().parent.parent / "quant" / "reporting"
           / "validation_report.py").read_text(encoding="utf-8")
    for key in ('failed["wf"]', 'failed["pbo"]', 'failed["cpcv"]'):
        assert key in src, key
    assert "failed=failed" in src                 # 렌더러에 실제로 전달
