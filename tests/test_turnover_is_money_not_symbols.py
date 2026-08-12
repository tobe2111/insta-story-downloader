"""회전율이 **거래 금액** 기준인가 (감사 119).

첫 화면은 이렇게 말하고 있었다.

    회전율 최근 1일 평균 65%/일 → 연 비용 약 70% vs 기대수익 12%
    ⚠️ 비용이 수익을 먹는 구간

그런데 그 65%의 정체는 이거였다.

    "turnover": {"filled": len(fills), "universe": n,
                 "ratio": len(fills) / n}          ← 몇 **종목을** 건드렸나

13종목을 각각 자산의 0.1%씩 움직였다면 실제 회전율은 1.3%지 65%가
아니다. **비용은 거래 금액에 비례하지 건드린 종목 수에 비례하지 않는다.**

이 숫자는 단순한 표시 오류가 아니었다 — 감사자(나)가 이 값을 근거로
운영자에게 "회전율을 줄이자"는 전략 변경을 제안했다. 잘못된 측정이
잘못된 의사결정으로 이어지기 직전이었다.

고침: 장부에 traded = Σ|Δ적용노출| 을 남기고, **그 값만** 비용으로
환산한다. 없는 옛 기록은 '체결 종목 비율'이라고만 적고 환산하지 않는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DAILY = (ROOT / "quant" / "live" / "daily.py").read_text("utf-8")
INDEX = (ROOT / "docs" / "index.html").read_text("utf-8")


def _fn_src() -> str:
    """_turnover_traded 본문 — 독스트링에 빈 줄이 있어 '\n\n'로 못 자른다."""
    seg = DAILY.split("def _turnover_traded(", 1)[1]
    return seg.split("\n    gross", 1)[0][:1200]


def _joined(text: str) -> str:
    """JS 문자열 이어붙이기를 지운다 — 문구가 '+ 로 쪼개져 있다."""
    return re.sub(r"'\s*\+\s*\n\s*'", "", text)


def test_the_ledger_records_money_turnover():
    assert '"traded": _turnover_traded(' in DAILY, (
        "장부가 거래 금액 기준 회전율을 남기지 않는다")


def test_the_misleading_key_was_renamed():
    """'ratio'라는 이름이 남아 있으면 다음 사람이 또 회전율로 읽는다."""
    seg = DAILY.split('"turnover": {', 1)[1][:300]
    assert '"symbols_ratio"' in seg, "종목 비율 키 이름이 모호하다"
    assert '"ratio"' not in seg.replace('"symbols_ratio"', ""), (
        "맨 'ratio' 키가 남아 있다 — 회전율로 오해된다")


def test_turnover_is_the_sum_of_exposure_changes():
    """정의 자체 — Σ|오늘 − 어제|."""
    fn = _fn_src()
    assert "abs(" in fn and "prev" in fn, fn[:200]
    assert "set(prev) | set(now)" in fn, (
        "한쪽에만 있는 종목(신규 진입·전량 청산)을 빠뜨린다")


def test_it_returns_none_when_yesterday_is_unknown():
    """모르면 숫자를 만들지 않는다 — 감사 91 이전 기록에는 applied가 없다."""
    assert "return None" in _fn_src()


def test_the_site_only_converts_money_turnover_to_cost():
    body = INDEX.split("/* 회전율·비용", 1)[1].split("if(vt){", 1)[0]
    assert "turnover.traded" in body, "장부의 traded를 쓰지 않는다"
    # 비용 환산(×252×0.0043)은 traded가 있는 가지 안에서만 일어나야 한다
    cost_lines = [ln for ln in body.splitlines() if "0.0043" in ln]
    assert len(cost_lines) == 1, f"비용 환산이 여러 곳에 있다: {cost_lines}"
    before = body.split("0.0043", 1)[0]
    assert "withT" in before, "traded가 없는 경우에도 비용을 환산한다"
    # ⚠️ 'withT'라는 이름이 있는 것만으로는 부족하다 — 그 안이 실제로
    #    traded를 거르는지 봐야 한다(변이 시험이 이 구멍을 잡았다:
    #    `const withT=hs;`로 바꿔도 통과했다).
    filt = re.search(r"const withT\s*=\s*(.+)", body)
    assert filt and "traded" in filt.group(1), (
        f"비용 환산 대상을 traded로 거르지 않는다: {filt and filt.group(1)}")


def test_the_fallback_says_what_it_actually_is():
    body = INDEX.split("/* 회전율·비용", 1)[1].split("if(vt){", 1)[0]
    assert "체결 종목 비율" in body, (
        "옛 기록을 여전히 '회전율'이라 부른다")
    assert "자산 대비 회전율이 아니라" in _joined(body), "오해를 짚어 주지 않는다"


def test_the_cost_rate_is_not_invented_on_the_page():
    """왕복비용률이 화면마다 다르면 같은 날 다른 비용이 나온다."""
    assert len(re.findall(r"0\.0043", INDEX)) == 1
