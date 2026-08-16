"""안전장치를 일부러 망가뜨렸을 때 검사가 정말 잡는가 — 통합 계좌 끝단.

2026-08-11 감사 58. 오늘 고친 안전장치들의 계약 검사를 **변이 시험**으로
확인했다: 프로덕션 코드를 일부러 망가뜨리고 해당 검사를 돌려, 실패하면
검사가 살아 있는 것이고 통과하면 검사가 장식이라는 뜻이다. 8건 중 2건이
장식이었다.

  ❌ 켈리 상한을 통째로 없애도(`eff = clip(...)` → `pass`) 통과
     — 기존 검사는 테스트 안에서 min()을 계산해 보거나 소스에
       `kelly_caps.get(key)` 문자열이 있는지만 봤다. 그 줄은 남기고
       clip만 지우면 아무도 모른다.
  ❌ 통합 계좌의 데이터 무결성 게이트를 꺼도 통과
     — 행동 검사는 종목별 경로(run_daily_paper)만 있었다. 정작 8만원을
       굴리는 통합 계좌 경로는 `scan_ohlcv`가 소스에 2번 나오는지 세는
       검사뿐이라, `if False and is_severe(q)`로 껐을 때 그대로 통과했다.

두 경우 모두 '소스에 문자열이 있는가'를 '동작하는가'로 착각한 검사였다.
문자열 검사는 배선이 사라지는 것은 잡지만 **배선이 무력화되는 것은 못
잡는다** — 그리고 오늘 잡은 결함은 전부 후자였다.

이 파일은 통합 계좌를 실제로 하루 돌려서 결과 숫자로 확인한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.live import daily as dl  # noqa: E402

TARGETS = [("synthetic", "AAA"), ("synthetic", "BBB"), ("synthetic", "CCC")]


def _bars(n=300, seed=3, start=100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, 0.02, n)
    close = start * np.exp(np.cumsum(r))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1_000_000.0}, index=idx)


class _Provider:
    """모든 종목에 같은(또는 지정한) 봉을 주는 가짜 제공자."""

    def __init__(self, frames: dict | None = None, default=None):
        self.frames = frames or {}
        self.default = default if default is not None else _bars()

    def get_ohlcv(self, symbol, timeframe="1d", limit=None, **kw):
        return self.frames.get(symbol, self.default).copy()


def _run(monkeypatch, tmp_path, provider, weight=0.9, **kw) -> dict:
    """통합 계좌를 하루 돌리고 그날의 기록을 돌려준다."""
    monkeypatch.setattr("quant.data.get_provider", lambda m: provider)

    class _Strat:
        name = "fixed"
        allow_short = False

        def generate_signals(self, df):
            return pd.Series(weight, index=df.index)

    monkeypatch.setattr(dl, "champion_strategy", lambda *a, **k: _Strat())
    monkeypatch.setattr(dl, "champion_spec",
                        lambda *a, **k: {"strategy": "fixed", "params": {}})
    out = dl.run_daily_portfolio(
        TARGETS, state_dir=str(tmp_path), require_real_data=False, **kw)
    path = tmp_path / "paper" / "portfolio_ALL.json"
    st = json.loads(path.read_text(encoding="utf-8"))
    return {"result": out, "state": st, "record": (st["history"] or [{}])[-1]}


# ── ① 통합 계좌도 오염된 데이터로는 매매하지 않는다 ───────────


def test_portfolio_path_refuses_corrupt_data(monkeypatch, tmp_path):
    """8만원을 굴리는 경로에서 무결성 위반 종목이 실제로 빠지는가.

    변이 시험에서 이 게이트를 꺼도(`if False and is_severe(q)`) 기존 검사가
    통과했다 — 종목별 경로만 행동으로 검사하고 통합 계좌는 소스 문자열만
    세고 있었기 때문이다.
    """
    bad = _bars(seed=9)
    bad.iloc[50, bad.columns.get_loc("high")] = bad["low"].iloc[50] * 0.5  # high<low
    out = _run(monkeypatch, tmp_path,
               _Provider({"BBB": bad}, default=_bars(seed=4)))
    ch = out["record"]["champion"]
    why = ch["skipped_why"] or {}
    assert "synthetic:BBB" in why, "오염된 종목이 그대로 매매됐다"
    assert "무결성" in why["synthetic:BBB"]
    assert "synthetic:BBB" in ch["skipped"]
    # 나머지 종목은 정상 운용된다(한 종목 오염이 계좌를 멈추지 않는다).
    # ⚠️ symbols는 '실제로 판단한 수'이지 계획 수가 아니다 — 예전에는 여기가
    #    len(targets)라 3종목 중 1개가 빠진 날에도 3이 기록됐고, SNS가 그
    #    숫자를 "N종목 분산"으로 방송했다(감사 59).
    assert ch["symbols"] == 2, "빠진 종목이 여전히 '분산 종목 수'에 세어진다"
    assert ch["planned"] == 3


def test_all_symbols_corrupt_means_no_record_at_all(monkeypatch, tmp_path):
    """전 종목이 오염이면 기록 자체를 남기지 않는다(그럴듯한 거짓 기록 금지)."""
    bad = _bars(seed=9)
    bad.iloc[50, bad.columns.get_loc("high")] = bad["low"].iloc[50] * 0.5
    monkeypatch.setattr("quant.data.get_provider", lambda m: _Provider(default=bad))
    with pytest.raises(RuntimeError, match="전 종목"):
        dl.run_daily_portfolio(TARGETS, state_dir=str(tmp_path),
                               require_real_data=False)


# ── ② 켈리 상한이 최종 비중을 실제로 구속한다 ─────────────────


def test_kelly_cap_binds_the_recorded_weight(monkeypatch, tmp_path):
    """상한을 걸면 장부에 적히는 비중이 그 아래로 내려가는가.

    변이 시험에서 clip을 통째로 지워도 기존 검사가 통과했다 — 검사가
    테스트 안에서 min()을 계산해 보거나 소스에 `kelly_caps.get(key)`
    문자열이 있는지만 확인했기 때문이다. 그 줄을 남기고 clip만 지우면
    아무도 모른다.
    """
    prov = _Provider(default=_bars(seed=11))

    # 상한 없음(1.0) — 기준선
    base = _run(monkeypatch, tmp_path / "a", prov)
    free_gross = base["record"]["weight"]
    assert free_gross > 0.05, "기준선 노출이 너무 작아 상한 효과를 못 잰다"

    # 아주 낮은 상한을 걸면 최종 비중이 그 아래여야 한다
    CAP = 0.01
    monkeypatch.setattr(dl, "_kelly_cap_from_history", lambda *a, **k: CAP)
    capped = _run(monkeypatch, tmp_path / "b", prov)

    # 장부의 'weight'는 실제로 적용한 비중의 합(총노출)이다.
    # 종목당 상한 CAP × 슬라이스이므로 총합은 CAP를 넘을 수 없다.
    gross = capped["record"]["weight"]
    assert gross <= CAP + 1e-9, (
        f"켈리 상한 {CAP}을 걸었는데 총노출이 {gross:.4f} — 상한이 구속하지 "
        "않는다(스케일러가 상한 위로 되돌려 올렸을 가능성)")
    assert gross < free_gross, "상한이 아무 차이도 만들지 않았다"
    # 장부는 '왜 노출이 이만큼인가'에 답할 수 있어야 한다 — 상한이 41%를
    # 1%로 깎았는데 아무 흔적이 없으면 그 답을 못 한다.
    caps = capped["record"].get("kelly_caps") or {}
    assert caps, "켈리 상한이 총노출을 깎았는데 장부에 흔적이 없다"
    assert all(v == pytest.approx(CAP) for v in caps.values())


def test_kelly_cap_of_one_changes_nothing(monkeypatch, tmp_path):
    """상한 1.0(비개입)은 결과를 바꾸지 않는다 — 상한이 늘 깎으면 안 된다."""
    prov = _Provider(default=_bars(seed=12))
    a = _run(monkeypatch, tmp_path / "a", prov)
    monkeypatch.setattr(dl, "_kelly_cap_from_history", lambda *a, **k: 1.0)
    b = _run(monkeypatch, tmp_path / "b", prov)
    assert a["record"]["weight"] == b["record"]["weight"]
    assert b["record"].get("kelly_caps") is None     # 비개입은 흔적을 안 남긴다


def test_recorded_gross_matches_what_was_actually_executed(monkeypatch,
                                                           tmp_path):
    """장부의 총노출(_applied)과 실제 체결(실행 루프)이 같은 규칙을 쓰는가.

    두 곳에 같은 계산이 따로 적혀 있으면 한쪽만 고쳐져 어긋난다 — 오늘
    /monitor의 손익·낙폭에서 정확히 그 대가를 치렀다. 켈리 상한을 걸었을 때
    장부가 말하는 총노출과 브로커가 실제로 잡은 비중이 일치하는지 본다.
    """
    monkeypatch.setattr(dl, "_kelly_cap_from_history", lambda *a, **k: 0.05)
    out = _run(monkeypatch, tmp_path, _Provider(default=_bars(seed=13)))
    st, rec = out["state"], out["record"]
    equity = float(rec["equity"])
    held = sum(abs(float(p["quantity"])) * float(p.get("avg_price", 0.0))
               for p in st.get("positions", {}).values())
    # 잔돈 차단·밴드로 체결이 생략될 수 있으므로 '기록 ≥ 실제'만 요구한다.
    # 반대(기록이 실제보다 작음)는 장부가 노출을 축소 보고하는 것이라 금지.
    assert rec["weight"] + 1e-6 >= held / equity - 1e-6, (
        f"장부 총노출 {rec['weight']:.4f} < 실제 보유 {held / equity:.4f} — "
        "장부가 실제보다 작은 노출을 말하고 있다")


# ── ③ 운영 손잡이가 실제로 노출을 움직인다 (감사 61) ──────────


def _settings(monkeypatch, **over):
    from quant.utils.settings import DEFAULTS
    cfg = {**DEFAULTS, **over}
    monkeypatch.setattr("quant.utils.settings.load_settings",
                        lambda *a, **k: cfg)
    return cfg


def test_admin_exposure_scale_actually_reduces_gross(monkeypatch, tmp_path):
    """어드민의 '총노출 배수'가 장부의 총노출을 그대로 줄이는가.

    변이 시험에서 `eff_scale = risk_scale * exposure_scale`을
    `eff_scale = risk_scale`로 바꿔도(손잡이 무시) 아무 검사가 실패하지
    않았다. 이 손잡이는 오늘 아침 '스케일러가 되돌려 키운다'는 결함을
    고친 바로 그 장치다 — 고쳐 놓고 지키는 검사가 없었다.
    """
    prov = _Provider(default=_bars(seed=17))
    _settings(monkeypatch)
    full = _run(monkeypatch, tmp_path / "a", prov)["record"]["weight"]
    assert full > 0.05, "기준선 노출이 너무 작아 배수 효과를 못 잰다"

    for scale in (0.5, 0.25):
        _settings(monkeypatch, exposure_scale=scale)
        got = _run(monkeypatch, tmp_path / f"s{scale}", prov)["record"]["weight"]
        # ⚠️ 장부의 weight는 소수 4자리로 반올림된 값이다. 비례 관계는 그
        #    격자보다 더 정밀하게 확인할 수 없다 — rel 허용오차만 두면
        #    총노출이 작아지는 변경(2026-08-14 검증 게이트)에서 반올림만으로
        #    깨진다. 검사의 뜻은 "손잡이가 총노출을 그만큼 줄인다"이지
        #    "부동소수까지 똑같다"가 아니다.
        assert got == pytest.approx(full * scale, rel=1e-6, abs=1e-4), (
            f"노출 배수 {scale}인데 총노출이 {got:.4f} (기대 {full * scale:.4f})")


def test_admin_pause_stops_new_orders(monkeypatch, tmp_path):
    """'일시정지'면 신규 주문이 나가지 않는다(보유는 유지)."""
    prov = _Provider(default=_bars(seed=18))
    _settings(monkeypatch, trading_paused=True)
    out = _run(monkeypatch, tmp_path, prov)
    assert out["record"]["paused"] is True
    assert not out["state"].get("positions"), "일시정지인데 포지션이 잡혔다"
    assert not out["record"]["fills"], "일시정지인데 체결이 났다"


# ── ④ 같은 봉 재실행은 기록을 두 번 남기지 않는다 ─────────────


def test_same_bar_rerun_is_idempotent(monkeypatch, tmp_path):
    """재시도 크론이 같은 날 두 번 돌아도 장부에 하루가 두 번 적히면 안 된다.

    2026-08-07에 한국 주식 6종목이 중복 기록된 사고의 방어선이다. 변이
    시험에서 이 가드를 없애도 아무 검사가 실패하지 않았다.
    """
    prov = _Provider(default=_bars(seed=19))
    first = _run(monkeypatch, tmp_path, prov)
    assert len(first["state"]["history"]) == 1

    second = _run(monkeypatch, tmp_path, prov)
    assert second["result"].get("skipped") is True, "같은 봉인데 또 기록했다"
    assert len(second["state"]["history"]) == 1, "장부에 같은 날이 두 번 적혔다"
