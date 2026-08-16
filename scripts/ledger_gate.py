#!/usr/bin/env python3
"""장부 관문 — 배치가 **자기가 방금 쓴 기록**을 커밋 전에 검사한다 (감사 255).

왜 필요한가
    2026-08-15 새벽 배치가 100만원 계좌의 자산을 **7,249만원(+7,150%)**으로
    기록했다. 그 값이 틀렸다는 것은 이미 저장소 안의 검사가 알고 있었다 —
    `test_no_implausible_equity_jumps`는 하루 ±50% 초과 변동을 잡는다.
    그런데 **그 검사는 그 기록을 한 번도 못 봤다.**

    배치 커밋은 전부 `[skip actions]`를 단다. 이유는 정당하다 — 장중 감시는
    15분마다 돌아 하루 96번 전체 검사를 돌릴 수는 없고, `[skip ci]`를 쓰면
    Cloudflare 배포까지 멈춘다(2026-08-10 사고). 그 결과 **배치가 만든
    기록에는 아무 검사도 걸리지 않는 구멍**이 생겼고, 그 구멍으로 7,150%가
    반나절을 살아남았다. 다음 PR이 열릴 때까지 아무도 몰랐다.

무엇을 하는가
    커밋 **직전에** 장부 무결성 검사만 돌린다. 전체 검사(3,300개, 수 분)가
    아니라 장부를 보는 것만 — 실측 0.9초다. 비용 때문에 못 한다는 말은
    이제 성립하지 않는다.

실패하면
    **커밋하지 않는다.** 오염된 기록은 그날의 성적표일 뿐 아니라 **내일의
    출발 상태**다 — 커밋하면 다음 배치가 그 위에서 굴러간다(META 85.9주가
    그렇게 다음 날로 넘어갈 뻔했다). 안 쓰면 장부는 어제에 멈추고, 그
    멈춤은 데드맨 스위치가 다음 날 아침에 잡는다. **조용히 틀리느니
    시끄럽게 멈춘다.**

여기에 검사 규칙을 적지 않는다
    무엇이 '말이 되는 장부'인지는 tests/ 가 이미 정의한다. 이 파일은 그
    목록만 갖는다 — 규칙을 두 곳에 적으면 언젠가 갈라진다(FROZEN_IDEAS ①).
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 장부가 말이 되는지 보는 검사들. 여기 이름만 두고, 판정은 저 파일들이 한다.
LEDGER_CHECKS = (
    "tests/test_ledger_integrity.py",          # 자산 급변·원금+손익 일치 등
    "tests/test_ledger_fields_reach_the_screen.py",   # 장부에만 있고 화면엔 없는 필드
    "tests/test_one_account_cannot_hold_two_currencies.py",  # 통화 혼재(감사 254)
)


def run() -> int:
    missing = [c for c in LEDGER_CHECKS if not (ROOT / c).exists()]
    if missing:
        # 검사 파일이 사라졌는데 관문이 초록을 주면, 그게 가장 나쁜 상태다.
        print(f"❌ 장부 관문: 검사 파일이 없다 {missing} — 관문이 무의미하다")
        return 2
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
         *LEDGER_CHECKS],
        cwd=ROOT, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"✅ 장부 관문 통과 ({len(LEDGER_CHECKS)}개 검사)")
        return 0
    print("❌ 장부 관문 실패 — 이 기록은 커밋하지 않는다.")
    print("   오염된 기록은 그날의 성적표이자 **내일의 출발 상태**다.")
    print("   장부는 어제에 멈추고, 그 멈춤은 데드맨 스위치가 잡는다.")
    print(proc.stdout[-4000:])
    print(proc.stderr[-2000:])
    return 1


if __name__ == "__main__":
    sys.exit(run())
