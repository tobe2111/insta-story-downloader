"""키를 만드는 곳과 검증하는 곳이 같은 키를 내는지 아무도 안 봤다 (감사 251).

이 저장소에는 같은 알고리즘의 구현이 **둘** 있습니다:

    발급  worker.js `issueKey`              — Cloudflare, 판매자가 누르는 버튼
    검증  quant/licensing.py `generate_key` — 구매자 컴퓨터

둘이 어긋나면 **판 키가 전부 무효**가 됩니다. 저장소는 이 위험을 알고
지문(fingerprint) 장치를 만들어 뒀는데, 그건 **'비밀이 같은가'만** 봅니다.
알고리즘이 갈라지면(자르는 길이 15바이트, 그룹 6자, 소유자 소문자·공백
정규화 중 하나만 달라져도) **지문은 그대로인데 키만 안 맞습니다.**

그런데 `worker.js`는 336줄인데 **변이 항목이 0건**이었고, 발급 경로를
지나가는 검사도 없었습니다. 결함이 아직 안 났을 뿐, 막는 장치가
없었습니다(FROZEN ② — 검사가 초록인 것과 장치가 동작하는 것은 다르다).

지금은 두 구현이 일치합니다(실측 2026-08-15, 이 파일의 시험용 비밀 기준):

    worker  QUANT-EPUDPB-AKGK7C-VE6UGW-DYEMZS · hmac:3357dad8b539
    python  QUANT-EPUDPB-AKGK7C-VE6UGW-DYEMZS · 3357dad8b539

이 검사는 **그 일치를 고정합니다.** 정답 벡터는 파이썬이 만들고 워커를
진짜로 실행해 대조합니다 — 진실의 출처는 하나입니다.

함께 고정한 것(모두 실행으로 확인): 어드민 로그인이 꺼져 있으면 발급도
잠긴다 · 자격증명이 틀리면 401이고 키가 안 나온다 · 어드민 페이지도 같은
문으로 막힌다 · 이메일이 아니면 발급하지 않는다 · 발급 응답은 교차출처로
열지 않고 캐시하지 않는다 · 비밀이 없으면 키처럼 생긴 것을 지어내지 않는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.licensing import generate_key, secret_fingerprint  # noqa: E402

SECRET = "감사251-테스트-비밀"
OWNERS = ["buyer@x.com", "BUYER@X.COM", "  buyer@x.com  ",
          "한글이름@메일.한국", "a+tag@sub.domain.co.kr"]


def _node() -> str:
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node 없음 — 워커 실행 검사 생략")
    return node


def test_the_worker_and_the_verifier_make_the_same_key():
    """어긋나면 판 키가 전부 무효다 — 지문만으로는 못 잡는다."""
    node = _node()
    cases = [{"owner": o,
              "key": generate_key(o, secret=SECRET),
              "fingerprint": secret_fingerprint(SECRET)} for o in OWNERS]
    spec = json.dumps({"secret": SECRET, "cases": cases}, ensure_ascii=False)
    r = subprocess.run(
        [node, str(ROOT / "tests" / "worker_license_check.mjs"), spec],
        capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_the_python_side_normalizes_the_owner_the_same_way():
    """대소문자·앞뒤 공백이 같은 키로 모여야 한다(워커도 같은 규칙)."""
    base = generate_key("buyer@x.com", secret=SECRET)
    for variant in ("BUYER@X.COM", "  buyer@x.com  ", "Buyer@X.Com"):
        assert generate_key(variant, secret=SECRET) == base, variant


def test_a_different_owner_gets_a_different_key():
    """대조군 — 정규화가 지나쳐 모두 같은 키가 되면 1인 1키가 무너진다."""
    a = generate_key("buyer@x.com", secret=SECRET)
    b = generate_key("other@x.com", secret=SECRET)
    assert a != b


def test_a_different_secret_gets_a_different_key():
    """대조군 — 비밀이 달라도 같은 키가 나오면 자물쇠가 아니다."""
    assert generate_key("buyer@x.com", secret=SECRET) != generate_key(
        "buyer@x.com", secret=SECRET + "다른")


def test_the_key_shape_is_fixed():
    """모양이 바뀌면 옛 구매자의 키가 형식 검사에서 걸린다."""
    import re
    key = generate_key("buyer@x.com", secret=SECRET)
    assert re.fullmatch(r"QUANT(-[A-Z2-7]{6}){4}", key), key


def test_the_worker_is_covered_by_mutation_testing():
    """336줄짜리 돈 만지는 코드에 변이 항목이 0건이었다.

    변이 시험에 안 실린 파일은 '검사가 있다'는 말이 검증되지 않는다 —
    안전장치를 지우는 변이를 아무도 안 잡아 본 것이다.
    """
    import ast

    src = (ROOT / "scripts" / "mutation_check.py").read_text("utf-8")
    tree = ast.parse(src)
    targets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 5:
            try:
                targets.append(ast.literal_eval(node)[1])
            except Exception:  # noqa: BLE001 — 상수가 아닌 튜플은 건너뛴다
                continue
    assert "worker.js" in targets, (
        "worker.js에 변이 항목이 없다 — 발급·인증 안전장치가 무방비다")


def test_the_pinned_vectors_in_the_harness_are_still_right():
    """하네스에 못 박은 정답 벡터가 조용히 낡지 않게 한다.

    변이 시험은 하네스를 **인자 없이** 부른다 — 그때는 못 박은 값으로
    돈다. 그 값이 파이썬과 갈라지면 변이 시험 전체가 거짓 기준 위에서
    돌게 되므로, 여기서 매번 다시 만들어 대조한다.
    """
    import re

    src = (ROOT / "tests" / "worker_license_check.mjs").read_text("utf-8")
    block = src.split("const PINNED = {", 1)[1].split("};", 1)[0]
    secret = re.search(r'secret:\s*"([^"]+)"', block).group(1)
    fp = re.search(r'fingerprint:\s*"([^"]+)"', block).group(1)
    assert fp == secret_fingerprint(secret), "못 박은 지문이 낡았다"
    pairs = re.findall(r'owner:\s*"([^"]*)",\s*key:\s*"([^"]+)"', block)
    assert len(pairs) >= 5, f"못 박은 벡터가 너무 적다: {len(pairs)}"
    for owner, key in pairs:
        assert generate_key(owner, secret=secret) == key, (
            f"못 박은 키가 파이썬과 다르다: {owner}")
