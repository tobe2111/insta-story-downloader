"""후원 랭킹·일간 각주 계약 검사.

핵심 계약:
  ① sponsors.json이 유효한 JSON이고 회계 분리 고지를 담는다
  ② 홈페이지가 후원 랭킹 섹션을 갖고, 후원이 없으면 숨겨진 채 시작한다
  ③ 어드민에 후원 기록 카드가 있고 회계 분리 경고를 표시한다
  ④ today 카드의 '일간' 열에 계좌 기준·체결 시차 각주가 붙는다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def test_sponsors_ledger_valid_and_separated():
    d = json.loads((ROOT / "docs" / "sponsors.json").read_text(encoding="utf-8"))
    assert isinstance(d.get("sponsors"), list)
    assert "분리" in d.get("note", "")            # 회계 분리 고지


def test_homepage_sponsor_section_hidden_by_default():
    idx = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'id="sponsors"' in idx and "후원 랭킹" in idx
    assert "sponsors.json" in idx
    # 후원이 없으면 섹션이 보이지 않게 시작한다
    assert 'id="sponsors" style="display:none"' in idx
    assert "회계 분리" in idx


def test_admin_sponsor_card_with_separation_warning():
    a = (ROOT / "docs" / "admin.html").read_text(encoding="utf-8")
    assert "후원 기록 추가" in a and "docs/sponsors.json" in a
    assert "매칭입금" in a                        # 원금 입금과 분리 안내


def test_today_daily_column_footnote():
    t = (ROOT / "docs" / "today.html").read_text(encoding="utf-8")
    assert "어제 보유분" in t and "다음 시가 체결" in t


def test_reliability_table_has_wilson_ci_and_flag():
    """사이트 신뢰도 곡선 — 신뢰구간 열과 보정 어긋남 플래그가 있다."""
    p = (ROOT / "docs" / "paper.html").read_text(encoding="utf-8")
    assert "95% 신뢰구간" in p and "wilson" in p
    assert "보정 어긋남" in p
