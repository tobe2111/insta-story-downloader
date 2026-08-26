"""유니버스 정의와 실제가 어긋나면 사이트 전체가 어긋난다 (감사 194).

`quant/markets.py`는 무엇을 굴리는지 정하는 한 곳이다. 여기가 어긋나면
사이트 문구·배분·방송 카드가 전부 그 위에 쌓인다. **결함은 못 찾았다** —
확인한 것을 적어 둔다.

곁들여 실측한 것(코드 결함은 아니고 **운영 사실**): 계좌가 작으면 비싼
주식은 배정 예산이 1주 값에 못 미쳐 **담기지 못한다**(감사 185에서 사이트에
표시하게 했다). 오늘 기준 2종목이 그렇고, 원금을 100만원으로 올려도 한
종목(1주 274,000원)은 여전히 못 산다. 이 파일은 그 사실을 **경고가 살아
있는지**로만 지킨다 — 유니버스에서 뺄지 말지는 사람이 정할 일이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.markets import AUTO_TARGETS, SYMBOL_INFO  # noqa: E402
from quant.universe import (  # noqa: E402
    CRYPTO_CORE, KR_ASSET_CORE, KR_CORE, US_ASSET_CORE, US_CORE,
    active_targets,
)


def _keys():
    return [f"{m}:{s}" for m, s in AUTO_TARGETS]


def _fixed_cores() -> list[str]:
    """규칙으로 **박아 둔** 종목 — 매달 회전하지 않으므로 이름이 있어야 한다."""
    return ([f"crypto:{s}" for s in CRYPTO_CORE]
            + [f"kr_stock:{s}" for s in KR_CORE + KR_ASSET_CORE]
            + [f"us_stock:{s}" for s in US_CORE + US_ASSET_CORE])


def _must_be_named() -> list[str]:
    """이름표가 반드시 덮어야 하는 목록.

    ⚠️ 예전에는 이 검사가 ``AUTO_TARGETS``(옛 고정 20종목)만 봤다. 유니버스가
       규칙 스냅샷으로 42종목이 된 2026-08-19 이후, 새로 들어온 스물두 종목은
       **아무도 이름을 확인하지 않는 종목**이었다 — 그래서 사이트 전체에서
       "UUP", "XLE", "132030.KS"로 나왔다(2026-08-26 사장님: "내용들이 무슨
       말인지 모르겠어"). 하필 그날 잔고 1위가 UUP였다.

       이제 셋을 합쳐 본다: 스냅샷이 없을 때 쓰는 고정 목록(AUTO_TARGETS),
       규칙으로 박아 둔 코어, 그리고 **지금 실제로 운용 중인 목록**.
    """
    live = [f"{m}:{s}" for m, s in active_targets(str(ROOT / "state"))]
    return sorted(set(_keys()) | set(_fixed_cores()) | set(live))


def test_every_traded_symbol_has_a_name_and_a_reason():
    """이름이 없으면 사이트가 종목코드를 그대로 노출하고, 이유가 없으면
    '왜 이걸 굴리나'에 답할 수 없다."""
    keys = _must_be_named()
    missing = [k for k in keys if k not in SYMBOL_INFO]
    assert not missing, f"유니버스에 있는데 설명이 없는 종목: {missing}"
    for k in keys:
        info = SYMBOL_INFO[k]
        assert info.get("name"), f"{k}: 이름이 비었다"
        assert info.get("why"), f"{k}: 편입 이유가 비었다"


def test_a_name_is_a_meaning_not_a_ticker():
    """이름이 종목 코드를 그대로 베낀 것이면 이름을 붙인 게 아니다.

    대조군 — 위 검사만 있으면 ``{"name": "UUP"}``도 초록이다. 읽는 사람에게
    "UUP"는 글자 셋이고 "달러"는 뜻이다. 이 저장소의 독자는 비개발자다.
    """
    bad = []
    for key, info in SYMBOL_INFO.items():
        symbol = key.split(":", 1)[1]
        name = str(info.get("name", ""))
        if name == symbol or name == symbol.split(".")[0]:
            bad.append(f"{key} → {name!r}")
    assert not bad, f"이름이 종목 코드 그대로다(뜻을 안 적었다): {bad}"


def test_there_is_no_orphan_description():
    """설명만 남고 유니버스에서 빠진 종목 — 사이트가 안 굴리는 걸 소개한다.

    ⚠️ 회전분(매달 시총 상위로 갈리는 종목)은 여기서 고아로 치지 않는다.
       이번 달에 빠졌다고 이름을 지우면 다음 달에 다시 들어올 때 또 생
       티커가 된다. 기록도 남아 있어(장부는 지우지 않는다) 이름이 계속
       필요하다. 고아는 **고정 코어도 아니고 옛 고정 목록도 아니고 지금
       운용 목록도 아닌** 것만 뜻한다.
    """
    known = set(_must_be_named())
    orphans = sorted(set(SYMBOL_INFO) - known)
    assert not orphans, f"유니버스에 없는데 설명이 남아 있다: {orphans}"


def test_no_symbol_is_listed_twice():
    keys = _keys()
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"같은 종목이 두 번 들어 있다(비중이 두 배가 된다): {dupes}"


def test_no_two_symbols_share_a_display_name():
    """화면에 같은 이름 둘이 뜨면 어느 쪽 성적인지 알 수 없다."""
    names = [v.get("name") for v in SYMBOL_INFO.values()]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"표시 이름이 겹친다: {dupes}"


def test_every_market_has_a_real_provider():
    """오타 난 시장 이름은 그 종목이 조용히 합성 데이터로 도는 것과 같다."""
    from quant.data import get_provider

    for market in sorted({m for m, _ in AUTO_TARGETS}):
        assert get_provider(market) is not None, market


def test_the_universe_is_diversified_across_markets():
    """대조군 — 한 시장에 몰리면 '분산'이라 말할 수 없다."""
    markets = {m for m, _ in AUTO_TARGETS}
    assert len(markets) >= 3, f"시장이 {len(markets)}종뿐이다: {markets}"
    for m in markets:
        share = sum(1 for mm, _ in AUTO_TARGETS if mm == m) / len(AUTO_TARGETS)
        assert share <= 0.6, f"{m}이 유니버스의 {share:.0%}를 차지한다"


def test_the_site_still_warns_about_symbols_it_cannot_buy():
    """계좌가 작으면 비싼 주식은 담기지 못한다 — 그 사실이 화면에 남아야 한다.

    감사 185에서 붙인 경고다. 유니버스를 늘리거나 원금이 바뀌어도 이 경고가
    사라지면, 사이트는 다시 '전 종목 분산'이라고만 말하게 된다.
    """
    index = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "lot_infeasible" in index, (
        "살 수 없는 종목 경고가 사이트에서 사라졌다")
    assert "살 수 없는 종목" in index
