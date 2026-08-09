"""거래소 리베이트 링크 계약 검사 — 초기 상태·홈페이지·어드민 배선.

핵심 계약:
  ① referrals.json 초기 상태는 links 빈 목록 — 홈페이지 섹션 숨김 유지
  ② 홈페이지: referrals.json을 읽어 렌더링하고 리베이트 투명 고지가 있다
  ③ 어드민: 깃허브 커밋으로 업서트(같은 거래소 이름은 덮어씀), https 검증
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def test_initial_referrals_empty_and_valid_json():
    data = json.loads((ROOT / "docs" / "referrals.json").read_text("utf-8"))
    assert data["links"] == []


def test_homepage_renders_with_disclosure():
    h = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert "referrals.json" in h and 'id="referrals"' in h
    assert "리베이트" in h and "투명 고지" in h            # 제휴 링크 고지 의무
    assert "sponsored" in h                               # rel 속성(검색엔진 규약)
    assert "가입하기" in h


def test_admin_upsert_and_https_guard():
    a = (ROOT / "docs" / "admin.html").read_text("utf-8")
    assert "referrals.json" in a and "rf-add" in a
    assert "filter(function(l){return l.name!==name})" in a   # 업서트(덮어쓰기)
    assert 'https:\\/\\//' in a or "https://" in a            # https 검증
    assert "리베이트" in a
