"""알파 10차 계약 검사 — 피처 가지치기 챌린저 + KRX 수급 피처(fs7).

핵심 계약:
  ① top_features=K: 학습·예측이 동작하고, 0(기본)이면 기존과 동일 결과
  ② 가지치기 챌린저가 링에 있다(강제 적용 아님 — 오디션으로만 승격)
  ③ KRX 수급: z-점수 부착·ffill 정렬·실패 시 원본 그대로(예외 없음)
  ④ kr_stock 세 경로(재학습·페이퍼·포트폴리오) 배선 + 워크플로 pykrx 설치
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.data.krx import attach_krx_flows  # noqa: E402
from quant.strategies.ml import MLStrategy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _df(n: int = 200, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100.0 * np.cumprod(1 + rng.normal(0.0005, 0.02, n))
    return pd.DataFrame({"open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close,
                         "volume": 1000.0 + rng.integers(0, 500, n)},
                        index=idx)


# ── ① 가지치기 학습·예측 ───────────────────────────────────────


def test_top_features_trains_and_predicts():
    df = _df()
    s = MLStrategy(model="gb", train_window=100, retrain_every=20,
                   min_train=40, top_features=5)
    sig = s.generate_signals(df)
    assert len(sig) == len(df) and np.isfinite(sig.to_numpy()).all()
    # 기본(0)은 기존 경로 그대로 — 가지치기 없는 결과와 동일해야 한다
    a = MLStrategy(model="gb", train_window=100, retrain_every=20,
                   min_train=40).generate_signals(df)
    b = MLStrategy(model="gb", train_window=100, retrain_every=20,
                   min_train=40, top_features=0).generate_signals(df)
    assert (a.to_numpy() == b.to_numpy()).all()


def test_prune_challenger_in_ring():
    from quant.live.retrain import DEFAULT_CHALLENGERS
    pruned = [c for c in DEFAULT_CHALLENGERS if c.get("top_features")]
    assert len(pruned) == 1 and pruned[0]["top_features"] == 10


# ── ③ KRX 수급 부착 ────────────────────────────────────────────


def test_krx_flows_attach_zscore_and_ffill():
    df = _df(120)
    flows = pd.DataFrame({
        "frgn": np.linspace(-1e9, 1e9, 100),
        "inst": np.linspace(1e9, -1e9, 100),
    }, index=pd.date_range("2025-01-01", periods=100, freq="D"))
    out = attach_krx_flows(df, "005930.KS", fetch=lambda s: flows)
    assert "x_frgn5" in out.columns and "x_inst5" in out.columns
    z = out["x_frgn5"].dropna()
    assert len(z) and z.abs().max() <= 4.0 + 1e-9          # z 클립
    # 수급 데이터가 끝난 뒤 봉은 마지막 z가 ffill — 새 정보가 없다
    tail = out["x_frgn5"].iloc[-15:]
    assert tail.nunique() == 1


def test_krx_failure_returns_original():
    df = _df(60)
    out = attach_krx_flows(df, "005930.KS",
                           fetch=lambda s: (_ for _ in ()).throw(RuntimeError()))
    assert list(out.columns) == list(df.columns)
    out2 = attach_krx_flows(df, "005930.KS", fetch=lambda s: None)
    assert list(out2.columns) == list(df.columns)


def test_ml_and_explain_cover_krx_features():
    from quant.live.explain import FEATURE_KO, _feature_note
    from quant.strategies.ml import FEATURE_SET, _features
    assert int(FEATURE_SET.split(":")[0][2:]) >= 7
    df = _df(120)
    df["x_frgn5"] = 1.5
    feats = _features(df)
    assert "x_frgn5" in feats.columns
    assert "x_frgn5" in FEATURE_KO and "x_inst5" in FEATURE_KO
    assert "순매수" in _feature_note("x_frgn5", 1.5)
    assert "순매도" in _feature_note("x_inst5", -1.5)


# ── ④ 배선 ─────────────────────────────────────────────────────


def test_krx_wired_into_three_paths_and_workflows():
    rt = (ROOT / "quant" / "live" / "retrain.py").read_text(encoding="utf-8")
    dl = (ROOT / "quant" / "live" / "daily.py").read_text(encoding="utf-8")
    assert rt.count("attach_krx_flows") >= 2         # import + 호출
    assert dl.count("attach_krx_flows") >= 4         # 페이퍼·포트폴리오
    # ⚠️ 워크플로에 'pykrx'라는 **글자**가 있는지가 아니라, 그 워크플로가
    #    pykrx를 **실제로 설치하는지**를 본다(2026-08-15). 선택 의존성을
    #    버전과 함께 requirements-extra.txt로 옮기면서 글자는 사라졌지만
    #    설치는 그대로다 — 자리를 고정한 검사는 그때 엉뚱하게 실패한다.
    extra = (ROOT / "requirements-extra.txt").read_text(encoding="utf-8")
    assert "pykrx" in extra, "선택 의존성 파일에 pykrx가 없다"
    for wf in ("nightly-retrain.yml", "daily-paper.yml"):
        y = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert "pykrx" in y or "-r requirements-extra.txt" in y, (
            f"{wf}가 pykrx를 설치하지 않는다 — 한국주식 수급 피처가 "
            f"통째로 사라진다")


def test_the_individual_column_is_collected_but_never_a_champion_feature():
    """개인 순매수 (2026-08-18, 수급 논문 재현 재료) — 부착과 동결의 경계.

    처음에는 수집만 하고 부착하지 않았다(보수적 경계). 같은 날 저녁,
    약속했던 다음 단계인 **도전자 전용 부착**이 구현되면서 경계가 옮겨졌다:
    개인 수급은 이제 flow_indi5로 데이터에 붙지만, 챔피언의 입력은 한 개도
    변하지 않아야 한다. ⚠️ 이름이 x_indi5가 **아닌** 것이 동결의 핵심이다 —
    챔피언 피처 빌더(_features)는 x_* 컬럼을 전부 자동 포함하므로, x_로
    붙였다면 챔피언 구조가 조용히 바뀌었을 것이다. 외부 검토 ③("피처는
    추가가 아니라 삭제")은 챔피언에 대한 말이고, 도전자(supply_som)는
    오디션에서 검증받는 것이 일이다.
    """
    df = _df(120)
    flows = pd.DataFrame({
        "frgn": np.linspace(-1e9, 1e9, 100),
        "inst": np.linspace(1e9, -1e9, 100),
        "indi": np.linspace(-5e8, 5e8, 100),
    }, index=pd.date_range("2025-01-01", periods=100, freq="D"))
    out = attach_krx_flows(df, "005930.KS", fetch=lambda s: flows)
    assert "x_frgn5" in out.columns and "x_inst5" in out.columns
    assert "flow_indi5" in out.columns, (
        "개인 수급이 부착되지 않는다 — 3주체 도전자가 재료 없이 돈다")
    z = out["flow_indi5"].dropna()
    assert len(z) and z.abs().max() <= 4.0 + 1e-9          # 같은 z 규약
    # 동결의 실체 — 이름표가 아니라 **행동**으로 잰다: 챔피언 피처 행렬에
    # 이 컬럼이 실제로 들어가지 않는다.
    from quant.strategies.ml import OPTIONAL_FEATURES, _features
    feats = _features(out)
    assert "flow_indi5" not in feats.columns, (
        "개인 수급이 챔피언 피처 행렬에 들어갔다 — 구조 동결 위반")
    assert "x_indi5" not in feats.columns and "x_indi5" not in OPTIONAL_FEATURES, (
        "x_ 이름으로 붙어 챔피언 세계에 새어 들었다")


def test_the_collector_maps_all_three_investor_columns(monkeypatch):
    """KRX 실제 컬럼 이름(기관합계·외국인합계·개인)이 frgn/inst/indi로 옮겨진다.

    이 컨테이너에서는 KRX가 막혀 있어(프록시) 실호출 검증은 야간 배치의
    몫이다 — 여기서는 pykrx를 가짜로 꽂아 **매핑 로직**만 정확히 잰다.
    """
    import sys
    import types
    idx = pd.date_range("2025-01-01", periods=10, freq="D")
    raw = pd.DataFrame({
        "기관합계": np.arange(10) * 1e8,
        "기타법인": np.ones(10),
        "개인": -np.arange(10) * 1e8,
        "외국인합계": np.arange(10) * 2e8,
        "전체": np.zeros(10),
    }, index=idx)
    fake_stock = types.SimpleNamespace(
        get_market_trading_value_by_date=lambda s, e, c: raw)
    monkeypatch.setitem(sys.modules, "pykrx", types.SimpleNamespace(stock=fake_stock))
    from quant.data.krx import fetch_investor_net
    out = fetch_investor_net("005930.KS", limit=10)
    assert set(out.columns) == {"frgn", "inst", "indi"}, out.columns
    assert (out["indi"] <= 0).all() and (out["frgn"] >= 0).all()
