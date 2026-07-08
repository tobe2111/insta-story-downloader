"""과최적화 검증(validate) 결과를 사람이 눈으로 판단할 HTML 리포트로 렌더한다.

`validate`는 워크포워드(+DSR)·PBO·CPCV의 숫자를 텍스트로 준다. 이 모듈은 그
숫자를 그래프로 바꿔 "이 전략을 믿어도 되는가"를 한 화면에서 판단하게 한다:
    · OOS 자본곡선 (워크포워드 검증 구간의 실현 자산)
    · PBO 분포 (IS 1등이 OOS에서 뒤처지는 정도의 히스토그램)
    · CPCV 경로별 샤프 분포 (여러 OOS 경로에서 성과가 일관적인가)
    · 판정 카드 (DSR·PBO·CPCV 최소샤프의 통과/주의/실패)

렌더러 자체는 순수 stdlib(인라인 SVG)라 matplotlib이 필요 없다. 오케스트레이터
render_validation_report만 pandas(백테스트)를 쓴다.

⚠️ 세 검증을 통과해도 미래 수익은 보장되지 않는다. 이 리포트의 목적은 '수익
   예측'이 아니라 '그럴듯한 거짓말(과최적화)을 눈으로 걸러내기'다.
"""
from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Sequence


def _minmax(vals: Sequence[float]) -> tuple[float, float]:
    fin = [v for v in vals if v == v]        # NaN 제외
    if not fin:
        return 0.0, 1.0
    lo, hi = min(fin), max(fin)
    return (lo, hi) if hi > lo else (lo - 1.0, hi + 1.0)


def _svg_area(values: Sequence[float], w: int = 720, h: int = 200,
              pad: int = 6) -> str:
    """자본곡선용 면적+선 차트(SVG). 값 리스트만 받는다(stdlib)."""
    vals = [float(v) for v in values if v == v]
    if len(vals) < 2:
        return '<p class="muted">그릴 데이터가 부족합니다.</p>'
    lo, hi = _minmax(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    def x(i): return pad + i * (w - 2 * pad) / (n - 1)
    def y(v): return pad + (h - 2 * pad) * (1 - (v - lo) / rng)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    area = f"{pad},{h - pad} {pts} {w - pad},{h - pad}"
    up = vals[-1] >= vals[0]
    col = "#16a34a" if up else "#dc2626"
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" '
            f'preserveAspectRatio="none" role="img">'
            f'<polygon points="{area}" fill="{col}" fill-opacity="0.12"/>'
            f'<polyline points="{pts}" fill="none" stroke="{col}" '
            f'stroke-width="2"/></svg>')


def _svg_hist(values: Sequence[float], bins: int = 20, w: int = 720, h: int = 160,
              pad: int = 6, mark: float | None = None, mark_label: str = "") -> str:
    """히스토그램(SVG). mark 위치에 세로선(예: 0 경계·PBO 값)."""
    vals = [float(v) for v in values if v == v]
    if not vals:
        return '<p class="muted">그릴 데이터가 부족합니다.</p>'
    lo, hi = _minmax(vals)
    rng = (hi - lo) or 1.0
    counts = [0] * bins
    for v in vals:
        b = min(bins - 1, int((v - lo) / rng * bins))
        counts[b] += 1
    cmax = max(counts) or 1
    bw = (w - 2 * pad) / bins
    bars = []
    for i, c in enumerate(counts):
        bh = (h - 2 * pad) * c / cmax
        bx = pad + i * bw
        by = h - pad - bh
        bars.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw - 1:.1f}" '
                    f'height="{bh:.1f}" fill="#3b82f6" fill-opacity="0.75"/>')
    marker = ""
    if mark is not None and lo <= mark <= hi:
        mx = pad + (mark - lo) / rng * (w - 2 * pad)
        marker = (f'<line x1="{mx:.1f}" y1="{pad}" x2="{mx:.1f}" y2="{h - pad}" '
                  f'stroke="#f59e0b" stroke-width="2" stroke-dasharray="4 3"/>'
                  f'<text x="{mx + 4:.1f}" y="{pad + 12}" font-size="11" '
                  f'fill="#f59e0b">{_html.escape(mark_label)}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" role="img">'
            + "".join(bars) + marker + '</svg>')


def _card(label: str, value: str, verdict: str, hint: str) -> str:
    color = {"pass": "#16a34a", "warn": "#d97706", "fail": "#dc2626"}.get(verdict, "#93a1b8")
    return (f'<div class="card"><div class="clab">{_html.escape(label)}</div>'
            f'<div class="cval" style="color:{color}">{_html.escape(value)}</div>'
            f'<div class="chint">{_html.escape(hint)}</div></div>')


def build_validation_html(*, title: str, dsr: float, n_trials: int,
                          oos_sharpe: float, oos_return: float, oos_mdd: float,
                          equity: Sequence[float],
                          pbo: float, pbo_lambdas: Sequence[float],
                          mean_oos_rank: float, prob_oos_loss: float,
                          cpcv_sharpe_mean: float, cpcv_sharpe_min: float,
                          cpcv_sharpe_std: float, cpcv_worst_return: float,
                          cpcv_path_sharpes: Sequence[float],
                          n_paths: int) -> str:
    """검증 결과(plain 데이터)를 HTML 문자열로 렌더한다(순수 stdlib)."""
    dsr_v = "pass" if dsr >= 0.95 else ("warn" if dsr >= 0.7 else "fail")
    pbo_v = "pass" if pbo < 0.2 else ("warn" if pbo < 0.5 else "fail")
    cpcv_v = "pass" if cpcv_sharpe_min > 0 else ("warn" if cpcv_sharpe_mean > 0 else "fail")
    overall = ("신뢰할 만함 — 세 검증 모두 통과" if {dsr_v, pbo_v, cpcv_v} == {"pass"}
               else ("실전 금지 — 검증 실패 항목 있음" if "fail" in {dsr_v, pbo_v, cpcv_v}
                     else "주의 — 애매한 항목 있음, 페이퍼로 더 확인"))
    overall_col = ("#16a34a" if overall.startswith("신뢰")
                   else "#dc2626" if overall.startswith("실전") else "#d97706")

    cards = (
        _card("DSR (다중검정 보정 샤프)", f"{dsr:.2f}", dsr_v,
              f"시행 {n_trials}회 보정 · ≥0.95 실력 가능성") +
        _card("PBO (과적합 확률)", f"{pbo:.0%}", pbo_v,
              f"IS 1등이 OOS서 손실일 확률 {prob_oos_loss:.0%} · <20% 양호") +
        _card("CPCV 최소경로 샤프", f"{cpcv_sharpe_min:.2f}", cpcv_v,
              f"경로 {n_paths}개 평균 {cpcv_sharpe_mean:.2f}±{cpcv_sharpe_std:.2f}"))

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)}</title><style>
 body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;
   background:#0b1220;color:#e6edf7;line-height:1.6}}
 @media(prefers-color-scheme:light){{body{{background:#f4f6fb;color:#0f172a}}}}
 .wrap{{max-width:860px;margin:0 auto;padding:28px 20px 56px}}
 h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:15px;margin:30px 0 8px}}
 .muted{{color:#93a1b8;font-size:13px}}
 .verdict{{font-size:16px;font-weight:700;padding:14px 18px;border-radius:12px;
   margin:14px 0;border:1px solid currentColor}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
 .card{{background:#111a2e;border:1px solid #22304d;border-radius:12px;padding:14px 16px}}
 @media(prefers-color-scheme:light){{.card{{background:#fff;border-color:#e2e8f0}}}}
 .clab{{font-size:12px;color:#93a1b8}} .cval{{font-size:26px;font-weight:800;margin:2px 0}}
 .chint{{font-size:11.5px;color:#93a1b8}}
 .panel{{background:#111a2e;border:1px solid #22304d;border-radius:12px;padding:14px 16px;margin:10px 0}}
 @media(prefers-color-scheme:light){{.panel{{background:#fff;border-color:#e2e8f0}}}}
 .warn{{color:#d97706;font-size:12.5px;margin-top:24px}}
</style></head><body><div class="wrap">
<h1>🧪 {_html.escape(title)}</h1>
<p class="muted">과최적화 검증 리포트 — 워크포워드(DSR)·PBO·CPCV. 수익 예측이 아니라
'그럴듯한 거짓말(과최적화) 걸러내기'가 목적입니다.</p>
<div class="verdict" style="color:{overall_col}">판정: {_html.escape(overall)}</div>
<div class="cards">{cards}</div>

<h2>OOS 자본곡선 (워크포워드 검증 구간)</h2>
<div class="panel">{_svg_area(equity)}
<p class="muted">총수익 {oos_return:.2%} · 샤프 {oos_sharpe:.2f} · 최대낙폭 {oos_mdd:.2%}.
보지 않은 미래(OOS)에서의 성과입니다. 우상향이 매끄러울수록·낙폭이 얕을수록 좋습니다.</p></div>

<h2>PBO 분포 (과적합 확률 {pbo:.0%})</h2>
<div class="panel">{_svg_hist(pbo_lambdas, mark=0.0, mark_label="0 = 동전던지기 경계")}
<p class="muted">각 IS/OOS 조합에서 'IS 1등이 OOS서 얼마나 앞섰나(λ)'의 분포.
주황선(0) 왼쪽 비율이 PBO입니다. 분포가 오른쪽에 치우칠수록(λ&gt;0) 선택이
노이즈가 아니라 실제 성과를 골랐다는 뜻입니다. IS 1등의 평균 OOS 순위: 상위 {(1 - mean_oos_rank):.0%}.</p></div>

<h2>CPCV 경로별 샤프 분포 ({n_paths}개 경로)</h2>
<div class="panel">{_svg_hist(cpcv_path_sharpes, bins=min(15, max(4, n_paths)), mark=0.0, mark_label="0")}
<p class="muted">여러 독립 OOS 경로의 샤프 분포. 전부 0 오른쪽에 모여야 신뢰할 수
있습니다. 최소 경로 샤프 {cpcv_sharpe_min:.2f} · 최악 경로 수익 {cpcv_worst_return:.2%}.
경로마다 들쭉날쭉하면(0을 걸치면) 한 번의 좋은 워크포워드 성과는 운일 수 있습니다.</p></div>

<p class="warn">⚠️ 세 검증을 모두 통과해도 <b>미래 수익은 보장되지 않습니다.</b> 통과는
'선택 절차가 노이즈를 고르고 있지 않다'는 뜻일 뿐입니다. 다음 단계는 페이퍼
트레이딩으로 실데이터 검증입니다. 하나라도 실패면 그 전략/파라미터는 실전에 올리지 마세요.</p>
</div></body></html>"""


def render_validation_report(df, strategy_cls, param_grid, *, path,
                             title=None, is_window=250, oos_window=125,
                             embargo=5, pbo_blocks=10, cpcv_groups=6,
                             periods_per_year=365):
    """검증 3종을 실행하고 HTML 리포트를 저장한다. 저장 경로를 반환.

    각 단계가 데이터 부족 등으로 실패하면 그 부분만 비우고 계속한다.
    """
    from quant.optimize import cpcv as _cpcv
    from quant.optimize import walk_forward
    from quant.robustness import param_returns_matrix, pbo as _pbo

    title = title or f"{getattr(strategy_cls, '__name__', '전략')} 검증"

    # 워크포워드 + DSR
    try:
        wf = walk_forward(df, strategy_cls, param_grid, is_window=is_window,
                          oos_window=oos_window, embargo=embargo,
                          periods_per_year=periods_per_year)
        m = wf["oos_metrics"]
        equity = wf["equity"].to_numpy().tolist()
        dsr, n_trials = wf["dsr"], wf["n_trials"]
        oos_sharpe, oos_return, oos_mdd = m.sharpe, m.total_return, m.max_drawdown
    except Exception:  # noqa: BLE001
        equity, dsr, n_trials = [], 0.0, 1
        oos_sharpe = oos_return = oos_mdd = 0.0

    # PBO
    try:
        mat = param_returns_matrix(df, strategy_cls, param_grid,
                                   periods_per_year=periods_per_year)
        pr = _pbo(mat, n_blocks=pbo_blocks)
        pbo_val, pbo_lambdas = pr["pbo"], pr["lambda_values"]
        mean_rank, prob_loss = pr["mean_oos_rank"], pr["prob_oos_loss"]
    except Exception:  # noqa: BLE001
        pbo_val, pbo_lambdas, mean_rank, prob_loss = 0.5, [], 0.5, 0.5

    # CPCV
    try:
        cv = _cpcv(df, strategy_cls, param_grid, n_groups=cpcv_groups, n_test=2,
                   embargo=embargo, periods_per_year=periods_per_year)
        cpcv_paths = [p["sharpe"] for p in cv["paths"]]
        cpcv_mean, cpcv_min = cv["sharpe_mean"], cv["sharpe_min"]
        cpcv_std, cpcv_worst, n_paths = cv["sharpe_std"], cv["worst_path_return"], cv["n_paths"]
    except Exception:  # noqa: BLE001
        cpcv_paths, cpcv_mean, cpcv_min, cpcv_std, cpcv_worst, n_paths = [], 0.0, 0.0, 0.0, 0.0, 0

    doc = build_validation_html(
        title=title, dsr=dsr, n_trials=n_trials, oos_sharpe=oos_sharpe,
        oos_return=oos_return, oos_mdd=oos_mdd, equity=equity, pbo=pbo_val,
        pbo_lambdas=pbo_lambdas, mean_oos_rank=mean_rank, prob_oos_loss=prob_loss,
        cpcv_sharpe_mean=cpcv_mean, cpcv_sharpe_min=cpcv_min, cpcv_sharpe_std=cpcv_std,
        cpcv_worst_return=cpcv_worst, cpcv_path_sharpes=cpcv_paths, n_paths=n_paths)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
