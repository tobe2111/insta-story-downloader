"""피처 건강 계측기가 **실재하는 컬럼**을 세는가 (감사 106).

`OPTIONAL_FEATURES`는 "외부 소스가 살아 있을 때만 붙는 피처" 목록이고,
매일 장부에 "오늘 몇 개나 붙었나"를 남긴다. 그 목적은 명확했다 —
소스가 죽으면 컬럼이 조용히 사라지는데 장부에는 여전히 같은 구조로
기록되므로, 판정 시계가 매일 다른 구조를 재게 된다.

그런데 목록에 적힌 이름 11개 중 **8개가 유령**이었다:

    적힌 이름        실제로 만들어지는 이름
    x_btc         →  x_btc_ret5
    x_spy         →  x_spy_ret5
    x_tnx         →  x_tnx_chg5
    x_usdkrw      →  x_usdkrw_ret5
    x_vixts       →  x_vix_ts
    x_fred_dgs10        (없음 — 어디서도 만들지 않는다)
    x_fred_t10y2y       (없음)
    x_fred_bamlh0a0hym2 (없음)

그래서 계측기는 **태어날 때부터 매일** "선택 피처 0/11 · 전부 누락"을
기록했다. 2026-08-11 기록의 `optional_max`도 0이다.

아무도 몰랐던 이유가 핵심이다: 그 값을 **어느 화면에도 보여주지
않았다**(감사 105). 고장난 계측기와 보이지 않는 계측기가 서로를 가려
주고 있었다. 105를 고치자마자 106이 드러났다.

여기서 고정하는 계약:
  ① 목록의 모든 이름은 코드 어딘가에서 **실제로 만들어져야** 한다.
  ② 실제로 만들어지는 선택 컬럼은 목록에 **있거나**, 왜 빠졌는지 적혀야
     한다(빠뜨리면 건강이 실제보다 나빠 보인다).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.strategies.ml import (            # noqa: E402
    BROKEN_METER_FINGERPRINT,
    OPTIONAL_FEATURES,
    optional_features_from_df,
)

DATA = ROOT / "quant" / "data"
ML = ROOT / "quant" / "strategies" / "ml.py"

# `funding`/`oi` 원본 컬럼에서 _features()가 파생시키는 이름들.
DERIVED = {"x_funding", "x_funding_chg", "x_oi_chg5"}


def _produced() -> set[str]:
    """코드가 실제로 만들어 내는 x_ 컬럼 이름 전부.

    ⚠️ 대입 구문(`out["x_.."] =`)만 찾으면 부족하다 — krx.py는 이름을
       `for col, feat in (("frgn", "x_frgn5"), ...)` 처럼 변수로 넘겨
       `out[feat] = ...` 로 붙인다(처음에 그렇게 짰다가 멀쩡한 이름 둘을
       '유령'이라고 잡았다). 그래서 **데이터 모듈에 등장하는 x_ 문자열은
       전부 '만들어지는 이름'으로 본다.** ml.py는 목록 자체가 들어 있으니
       대입 구문만 본다.
    """
    out: set[str] = set()
    for p in DATA.glob("*.py"):
        out |= set(re.findall(r'"(x_[a-z0-9_]+)"', p.read_text("utf-8")))
    ml = ML.read_text("utf-8")
    ml = ml.split("OPTIONAL_FEATURES = [", 1)[0] + \
        ml.split("OPTIONAL_FEATURES = [", 1)[1].split("]", 1)[1]
    for m in re.finditer(r'\[\s*"(x_[a-z0-9_]+)"\s*\]\s*=', ml):
        out.add(m.group(1))
    return out | DERIVED


# ── ① 유령 이름 금지 ────────────────────────────────────────────

def test_every_listed_feature_is_actually_produced():
    produced = _produced()
    ghosts = [c for c in OPTIONAL_FEATURES if c not in produced]
    assert not ghosts, (
        f"만들어지지 않는 이름을 세고 있다: {ghosts}\n"
        "  → 계측기가 매일 '누락'이라 기록하지만 실제로는 이름이 틀린 것이다.\n"
        f"  → 실제로 만들어지는 이름: {sorted(produced)}")


def test_the_list_is_not_empty_or_trivial():
    """목록이 비면 위 검사가 조용히 통과한다."""
    assert len(OPTIONAL_FEATURES) >= 8
    assert len(set(OPTIONAL_FEATURES)) == len(OPTIONAL_FEATURES), "중복"


# ── ② 실재하는데 빠뜨린 것 금지 ─────────────────────────────────

# 선택 피처가 아닌 x_ 컬럼 — 왜 목록에 없는지 이유를 적는다.
NOT_OPTIONAL = {
    # (지금은 없음 — 새 x_ 컬럼이 생기면 여기에 이유를 적거나 목록에 넣는다)
}


def test_no_produced_optional_column_is_forgotten():
    """실재하는 선택 컬럼을 빠뜨리면 건강이 실제보다 나빠 보인다."""
    forgotten = sorted(_produced() - set(OPTIONAL_FEATURES) - set(NOT_OPTIONAL))
    assert not forgotten, (
        f"만들어지는데 계측 목록에 없는 컬럼: {forgotten}\n"
        "  → 목록에 넣거나, NOT_OPTIONAL에 '왜 선택 피처가 아닌지'를 적을 것.")


# ── 실제로 세어 보기 ────────────────────────────────────────────

def test_the_meter_counts_a_frame_that_has_the_columns():
    """이름만 맞추면 끝이 아니다 — 실제 프레임을 넣어 세어 본다."""
    import pandas as pd
    df = pd.DataFrame({"close": [1.0, 2.0], "funding": [0.1, 0.2],
                       "oi": [10.0, 11.0], "x_btc_ret5": [0.0, 0.1],
                       "x_spy_ret5": [0.0, 0.1], "x_vix_ts": [0.9, 0.8]})
    got = set(optional_features_from_df(df))
    assert {"x_funding", "x_funding_chg", "x_oi_chg5",
            "x_btc_ret5", "x_spy_ret5", "x_vix_ts"} <= got, got


def test_the_meter_reports_zero_only_when_there_is_nothing():
    import pandas as pd
    assert optional_features_from_df(pd.DataFrame({"close": [1.0]})) == []


# ── 옛 기록과 새 기록을 구분할 수 있는가 ────────────────────────

def test_the_broken_meter_leaves_a_fingerprint():
    """교정 전 기록을 오늘의 사실처럼 말하지 않으려면 구별이 돼야 한다."""
    assert BROKEN_METER_FINGERPRINT not in OPTIONAL_FEATURES, (
        "지문으로 쓰는 이름이 현재 목록에도 있으면 옛 기록을 구별할 수 없다")
    idx = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert BROKEN_METER_FINGERPRINT in idx, (
        "사이트가 교정 전 기록을 구별하지 않는다 — 옛 0/11을 오늘의 "
        "사실처럼 '선택 피처 전멸'이라 말하게 된다")


def test_the_site_does_not_cry_wolf_on_pre_fix_records():
    """지문이 있는 기록에서는 '전멸' 경보 대신 '교정 전'이라 말해야 한다."""
    idx = (ROOT / "docs" / "index.html").read_text("utf-8")
    blk = idx.split("const fh=pfLast.feature_health;", 1)[1].split("const dq=", 1)[0]
    assert "fhOld" in blk and "else if" in blk, (
        "교정 전 기록과 진짜 전멸을 같은 경보로 다룬다")
    assert "교정 전" in blk
