"""어드민 대시보드 계약 검사 — 설정 로더·일시정지·노출 배수·SNS 스위치·시세 프록시.

핵심 계약:
  ① 설정 파일이 없거나 깨져도 자동화는 기본값(정상 운용)으로 절대 죽지 않는다
  ② exposure_scale은 [0,1] 클램프 — 오타가 레버리지가 되면 안 된다
  ③ 일시정지: 신규 주문 없음·대기 주문 폐기·보유 포지션 유지, 장부에 기록
  ④ 노출 배수는 킬스위치와 곱으로 적용되고 장부에 기록된다
  ⑤ SNS 게시 스위치가 꺼지면 게시하지 않는다
  ⑥ 워커(시세 프록시)·어드민 페이지가 배포 구성에 포함된다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.utils.settings import DEFAULTS, load_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# ── ①② 설정 로더 ───────────────────────────────────────────────


def test_settings_defaults_on_missing_and_corrupt(tmp_path):
    assert load_settings(str(tmp_path / "없는파일.json")) == DEFAULTS
    bad = tmp_path / "bad.json"
    bad.write_text("{부서진 json", encoding="utf-8")
    assert load_settings(str(bad)) == DEFAULTS
    notdict = tmp_path / "arr.json"
    notdict.write_text("[1,2]", encoding="utf-8")
    assert load_settings(str(notdict)) == DEFAULTS


def test_settings_clamp_and_types(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"exposure_scale": 10, "trading_paused": 1,
                             "social_post": 0, "note": "x" * 900}),
                 encoding="utf-8")
    s = load_settings(str(p))
    assert s["exposure_scale"] == 1.0            # 10 → 1.0 (레버리지 금지)
    assert s["trading_paused"] is True
    assert s["social_post"] is False
    assert len(s["note"]) == 500
    p.write_text(json.dumps({"exposure_scale": -0.5}), encoding="utf-8")
    assert load_settings(str(p))["exposure_scale"] == 0.0
    p.write_text(json.dumps({"exposure_scale": "많이"}), encoding="utf-8")
    assert load_settings(str(p))["exposure_scale"] == 1.0


def test_repo_settings_file_is_valid():
    """저장소의 실제 config/settings.json이 유효한 기본 상태다."""
    s = load_settings(str(ROOT / "config" / "settings.json"))
    assert s["trading_paused"] is False
    assert s["exposure_scale"] == 1.0
    assert s["social_post"] is True


# ── ③④ 일시정지·노출 배수 (통합 포트폴리오) ────────────────────


def _run_portfolio(tmp_path, monkeypatch, settings: dict):
    from quant.live.daily import run_daily_portfolio
    from quant.live.retrain import save_champions
    import quant.utils.settings as us
    monkeypatch.setattr(us, "load_settings",
                        lambda path=us.SETTINGS_PATH: {**DEFAULTS, **settings})
    d = str(tmp_path)
    save_champions({
        "synthetic:DEMO": {"strategy": "ma_cross",
                           "params": {"fast": 10, "slow": 30}, "promotions": 0},
        "synthetic:DEMO2": {"strategy": "ma_cross",
                            "params": {"fast": 5, "slow": 20}, "promotions": 0},
    }, d)
    return run_daily_portfolio([("synthetic", "DEMO"), ("synthetic", "DEMO2")],
                               lookback=200, state_dir=d,
                               require_real_data=False)


def test_paused_blocks_orders_and_is_recorded(tmp_path, monkeypatch):
    rec = _run_portfolio(tmp_path, monkeypatch, {"trading_paused": True})
    assert rec["paused"] is True
    assert rec["weight"] == 0.0                  # 목표 총노출 0
    st = json.loads((tmp_path / "paper" / "portfolio_ALL.json")
                    .read_text(encoding="utf-8"))
    assert st["positions"] == {}                 # 신규 주문이 없었다
    assert st.get("pending") in ({}, None)       # 대기 주문 폐기


def test_exposure_scale_halves_gross_and_is_recorded(tmp_path, monkeypatch):
    full = _run_portfolio(tmp_path, monkeypatch, {})
    half = _run_portfolio(Path(str(tmp_path) + "_h"), monkeypatch,
                          {"exposure_scale": 0.5})
    assert full["exposure_scale"] == 1.0 and full["paused"] is False
    assert half["exposure_scale"] == 0.5
    if full["weight"] > 0:                       # 신호가 있는 날이면 절반이다
        # 장부 기록이 소수 4자리 반올림이라 그 오차까지 허용
        assert abs(half["weight"] - full["weight"] * 0.5) < 1e-4


# ── ⑤ SNS 게시 스위치 ──────────────────────────────────────────


def test_social_post_disabled_by_admin(tmp_path, monkeypatch):
    import quant.utils.settings as us
    from quant.reporting.social_post import run
    monkeypatch.setattr(us, "load_settings",
                        lambda path=us.SETTINGS_PATH: {**DEFAULTS,
                                                       "social_post": False})
    out = run(str(tmp_path), "https://example.com",
              env={"THREADS_USER_ID": "u", "THREADS_ACCESS_TOKEN": "t"},
              wait_public=False)
    assert out == {"skipped": "disabled_by_admin"}


# ── ⑥ 배포 구성 — 워커·어드민 페이지 ───────────────────────────


def test_worker_serves_quotes_proxy_and_assets():
    w = (ROOT / "worker.js").read_text(encoding="utf-8")
    assert "/api/quotes" in w and "ASSETS.fetch" in w
    assert "query1.finance.yahoo.com" in w
    cfg = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    assert '"main": "worker.js"' in cfg
    assert '"binding": "ASSETS"' in cfg


def test_admin_page_edits_settings_via_github_api():
    a = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
    assert "config/settings.json" in a            # 편집 대상
    assert "trading_paused" in a and "exposure_scale" in a
    assert "social_post" in a
    assert "localStorage" in a                    # 토큰은 브라우저에만
    assert "noindex" in a                         # 검색 비노출


def test_ticker_polls_stock_quotes_proxy():
    idx = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "/api/quotes" in idx and "준실시간" in idx
