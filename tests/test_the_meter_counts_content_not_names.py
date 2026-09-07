"""재료 계측기는 **이름이 아니라 내용**을 센다.

2026-09-07 스냅샷 실측. 이것도 화면에 아무 이상이 안 뜨는 종류의 고장이다 —
계측기가 후한 쪽으로 틀렸다.

■ 무엇이 일어나고 있었나

``optional_features_from_df``는 **열이 있는가**만 본다(``"oi" in cols``).
그래서 열은 있지만 대부분의 봉이 비어 있는 재료도 "붙었다"로 세어졌다.
코인 5종목 × 800봉 스냅샷:

    x_funding · x_fng · x_usd_chg5 · x_hy_spread   100.0%
    x_btc_ret5                                      99.4%
    x_kimchi                                        25.0%  ← 200봉
    x_oi_chg5                                        3.9%  ← 31봉

그리고 학습은 ``feats.fillna(0.0)``이다. 즉 나머지 769봉에 대해 모델은
**"미결제약정이 안 변했다"**는 구체적 주장을 배운다 — 못 받은 것과 0은
다른 사건인데 이 자리에서 같아진다. 장부에는 그날 밤 XRP가
``features_used: [... x_oi_chg5 ...]``로 적혔고, 유실 경보는
``x_frgn5,x_inst5``(열이 통째로 없는 것)만 말했다.

이 모듈의 첫머리가 이미 같은 병을 두 번 적어 두었다(감사 105·106: 계측기가
**만들어지지도 않는 이름**을 세고 있었고, 그 값을 아무 화면에도 안 보여줘서
고장난 계측기와 보이지 않는 계측기가 서로를 가려 줬다). 이번은 세 번째
얼굴이다 — 이름은 맞는데 **내용이 없다**.

■ 고친 것 — 재기만 한다, 신호는 안 바꾼다

  · ``optional_feature_fill`` — 붙을 재료의 채움률.
  · ``thin_features`` — 문턱 아래만. 깨끗하면 **빈 dict**다.
  · 밤 장부에 ``features_thin``, 배치 건강에 ``thin``, 경보에
    ``features_thin:``.

⚠️ **얇은 재료를 빼지 않는다.** 뺄지 말지는 오디션의 ``top_features`` 축이
   정한다 — 사람이 손으로 정할 자리가 아니다(사장님 2026-08-27 방침).
   여기서 하는 일은 **아무도 못 보던 사실을 보이게 하는 것**뿐이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.live.flag_watch import _current_flags  # noqa: E402
from quant.strategies.ml import (  # noqa: E402
    DERIVED_FROM, THIN_FILL, optional_feature_fill, optional_features_from_df,
    thin_features,
)


def _df(n: int = 100, oi_filled: int = 4, kimchi_filled: int = 100):
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    oi = [None] * (n - oi_filled) + [100.0 + i for i in range(oi_filled)]
    km = [None] * (n - kimchi_filled) + [0.01] * kimchi_filled
    return pd.DataFrame({"close": range(1, n + 1),
                         "funding": [0.0001] * n,
                         "oi": oi,
                         "x_kimchi": km,
                         "x_fng": [50.0] * n}, index=idx)


# ── 이 검사가 이 파일의 존재 이유다 ───────────────────────────────────
def test_a_column_that_is_almost_empty_is_not_reported_as_attached():
    """실측된 사고 그 자체 — 800봉 중 31봉만 채워진 재료가 '붙었다'였다."""
    df = _df()
    assert "x_oi_chg5" in optional_features_from_df(df), (
        "옛 계측기는 여전히 이름을 센다 — 그 뜻은 바꾸지 않았다")
    fill = optional_feature_fill(df)
    assert fill["x_oi_chg5"] == 0.04, fill
    assert "x_oi_chg5" in thin_features(df), (
        "4%만 채워진 재료를 얇다고 말하지 않는다")


def test_a_full_column_is_never_called_thin():
    """깨끗한 재료는 아무 말도 안 나온다 — 매일 켜진 표시는 표시가 아니다."""
    df = _df(kimchi_filled=100)
    thin = thin_features(df)
    assert "x_funding" not in thin and "x_fng" not in thin, thin
    assert "x_kimchi" not in thin, thin


def test_a_clean_frame_says_nothing_at_all():
    df = _df(oi_filled=100, kimchi_filled=100)
    assert thin_features(df) == {}, thin_features(df)


def test_an_empty_frame_does_not_invent_a_number():
    """봉이 없으면 채움률이 **없다** — 0%도 NaN도 아니다.

    ⚠️ 열은 다 있는데 행이 0인 프레임이 진짜 함정이다(데이터를 못 받은 날).
       그때 ``notna().mean()``은 NaN을 주는데, 그 NaN이 그대로 장부에 실리면
       JSON에서 ``null``이 되고 경보는 "문턱 미만"으로 읽어 **못 받은 날마다
       거짓 경보**를 낸다. 못 잰 것과 0은 다른 사건이다.
    """
    empty = pd.DataFrame({"funding": [], "oi": [], "x_kimchi": []})
    assert list(empty.columns), "열조차 없으면 이 함정을 못 밟는다"
    assert optional_feature_fill(empty) == {}, optional_feature_fill(empty)
    assert thin_features(empty) == {}, "봉이 0인 날 '얇다'고 말했다"
    assert optional_feature_fill(pd.DataFrame()) == {}
    assert optional_feature_fill(None) == {}


# ── 파생 재료는 **원본 열**을 봐야 한다 ───────────────────────────────
def test_a_derived_feature_is_measured_on_its_source_column():
    """`x_oi_chg5`는 df에 없는 이름이다 — `oi`를 안 보면 아무것도 못 잰다.

    ⚠️ 손으로 적은 표가 실제와 어긋나 계측기가 유령을 세던 사고가 이미 두 번
       있었다(감사 105·106). 그래서 이 대응표를 못 박는다.
    """
    assert DERIVED_FROM["x_oi_chg5"] == "oi"
    assert DERIVED_FROM["x_funding"] == "funding"
    assert DERIVED_FROM["x_funding_chg"] == "funding"
    src = (ROOT / "quant" / "strategies" / "ml.py").read_text("utf-8")
    # _features()가 실제로 그 열에서 만드는지 — 표만 고치고 코드를 안 고치면
    # 계측기가 다시 유령을 센다.
    assert 'out["x_oi_chg5"] = oi.pct_change(5)' in src
    for name, source in DERIVED_FROM.items():
        assert f'"{source}"' in src, f"{name}의 원본 열 {source}가 코드에 없다"


def test_a_passthrough_feature_is_measured_on_itself():
    df = _df(kimchi_filled=10)
    assert optional_feature_fill(df)["x_kimchi"] == 0.1


# ── 문턱 ──────────────────────────────────────────────────────────────
def test_the_floor_sits_between_healthy_and_broken():
    """문턱 근거는 실측이다 — 건강한 재료 99.4~100% vs 문제 25%·3.9%."""
    assert 0.25 < THIN_FILL < 0.994, THIN_FILL


def test_the_floor_can_be_overridden_without_editing_the_module():
    df = _df(kimchi_filled=30)
    assert "x_kimchi" not in thin_features(df, floor=0.2)
    assert "x_kimchi" in thin_features(df, floor=0.5)


# ── 경보 ──────────────────────────────────────────────────────────────
#
# ⚠️ **경보 검사는 배치가 실제로 만드는 모양으로 먹인다.** 처음에는
#    `{"feature_health": {...}}`라는 **있지도 않은 모양**을 먹여 초록을
#    받았다 — 배치는 건강 블록을 본 계좌 장부의 그날 줄 안에 넣는데,
#    그 사실을 검사가 안 봤다. 그대로 뒀으면 이 경보는 검사에서만 울리고
#    실제로는 영원히 침묵했을 것이다. 그러니 여기서 모양을 **못 박는다.**
def _status(features: dict | None) -> dict:
    """배치가 넘기는 status의 진짜 모양(실측: docs/status.json)."""
    fh = {"optional_max": 8, "missing_everywhere": []}
    if features is not None:
        fh["thin"] = {"floor": 0.5, "features": features}
    return {"paper": {"portfolio:ALL": {"history": [{"feature_health": fh}]}}}


def test_the_alarm_reads_where_the_batch_actually_writes():
    """이 검사가 죽은 배선을 막는다 — 재료가 없는 자리를 읽으면 못 운다."""
    src = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert '"feature_health": feat_health or None,' in src, (
        "배치가 건강 블록을 어디에 넣는지 바뀌었다 — 경보도 함께 봐야 한다")
    import json as _json
    real = _json.loads((ROOT / "docs" / "status.json").read_text("utf-8"))
    assert "feature_health" not in real, (
        "status 최상위에 건강 블록이 생겼다면 경보를 그리로 옮겨도 된다")
    hist = real["paper"]["portfolio:ALL"]["history"][-1]
    assert "feature_health" in hist, (
        "본 계좌 장부의 그날 줄에 건강 블록이 없다 — 경보가 읽을 자리가 없다")


def test_the_alarm_names_the_feature_and_its_fill_rate():
    """이름만 부르면 읽는 쪽이 '얼마나 비었나'를 모른다."""
    flags = _current_flags(_status({"x_oi_chg5": 0.0387, "x_kimchi": 0.25}))
    hit = [v for k, v in flags.items() if k.startswith("features_thin")]
    assert hit, flags
    assert "x_oi_chg5 3.9%" in hit[0] and "x_kimchi 25.0%" in hit[0], hit[0]
    # 빈칸을 0으로 채운다는 사실이 문장에 있어야 한다 — 그게 피해의 정체다.
    assert "0으로 채웁니다" in hit[0]


def test_the_alarm_is_silent_when_nothing_is_thin():
    assert not [k for k in _current_flags(_status(None))
                if k.startswith("features_thin")]
    assert not [k for k in _current_flags({}) if k.startswith("features_thin")]


def test_the_alarm_key_is_the_names_so_it_speaks_once():
    """열쇠가 이름 목록이라 같은 상태에서는 한 번만 알린다.

    소스 깊이는 대개 그 상태로 오래 간다 — 매일 울리면 꺼진 경보와 같다
    (감사 99). `features_missing`과 같은 규약이다.
    """
    a = _current_flags(_status({"x_oi_chg5": 0.04}))
    b = _current_flags(_status({"x_oi_chg5": 0.05}))
    assert set(a) == set(b), "채움률이 조금 달라졌다고 새 경보가 된다"


# ── 배선 ──────────────────────────────────────────────────────────────
def test_the_batch_collects_it_and_the_ledger_carries_it():
    """장치만 있고 전선이 없으면 경보는 영영 안 울린다."""
    daily = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
    assert "thin_features(df)" in daily, "배치가 채움률을 안 잰다"
    assert '"thin": {"floor": THIN_FILL' in daily, "건강 기록에 안 싣는다"
    retrain = (ROOT / "quant" / "live" / "retrain.py").read_text("utf-8")
    assert '"features_thin"' in retrain, "밤 장부에 안 남는다"


def test_the_signal_is_not_changed_by_this_work():
    """⚠️ 얇은 재료를 **빼지 않는다** — 뺄지는 오디션이 정한다.

    사장님 2026-08-27 방침: 투자 로직은 기계가 개선한다. 이 작업은 계측기이지
    손잡이가 아니다. 재료를 고르는 축(`top_features`)은 이미 있고, 그 축이
    빼 보기를 매일 밤 시도한다.
    """
    ml = (ROOT / "quant" / "strategies" / "ml.py").read_text("utf-8")
    i = ml.index("def optional_feature_fill(")
    body = ml[i:i + 2000]
    assert "신호를" in body, (
        "이 함수가 신호를 안 바꾼다는 사실이 코드에 안 적혀 있다")
    assert "오디션의 ``top_features`` 축이" in body, (
        "빼는 결정을 누가 하는지가 코드에 안 적혀 있다")
    # 그리고 재료를 고르는 축은 이미 기계 쪽에 있다.
    from quant.live.retrain import ml_search_axes
    assert "top_features" in set(ml_search_axes({"model": "gb"})), (
        "재료를 고르는 축이 없다 — 그러면 얇은 재료를 뺄 주체가 사람뿐이다")
