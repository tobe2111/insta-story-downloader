#!/usr/bin/env python3
"""재현성 감사 결과를 읽고 **경보할지 판단한다** (감사 103).

왜 스크립트로 뺐는가
────────────────────
전에는 이 판단이 워크플로 YAML 안의 heredoc 파이썬이었다. 그래서 검사를
쓸 수 없었고, 실제로 이런 결함이 몇 주간 살아 있었다:

    bad = [ln for ln in lines if "불일치" in ln or "재현 실패" in ln]

`verify` 출력의 **통과** 줄은 이렇게 생겼다:

    ✔ crypto:BTC/USDT: 재현 일치 — … · 주의: 실행 환경이 기록과 다름
      (기록 pd2.3.3 vs 현재 pd3.0.5) — **불일치** 시 조작이 아니라
      라이브러리 버전 차이일 수 있음

즉 경보문이 자기 설명문에 걸렸다. 통과(✔)한 줄을 보고 "재현 불일치"라며
매일 밤 경보를 울린다. pandas가 3.0으로 올라가 환경 지문이 달라진 순간부터는
**매일** 울린다.

이건 시끄러운 정도의 문제가 아니다. 이 경보는 "장부는 조작할 수 없다"는
주장을 지키는 유일한 장치다. 매일 헛울리면 사장님이 무시하게 되고, 진짜
불일치가 난 날에도 똑같이 무시된다 — **경보를 끄는 가장 확실한 방법은
경보를 계속 울리는 것이다.**

판단 규칙
─────────
산문을 뒤지지 않는다. `verify`가 이미 줄마다 ✔/✘로 판정을 찍는다.

    ✘ 이면서 아래 '옛 기록의 한계'가 아니면  → 진짜 사건(경보 + 실패)
    ✘ 이면서 옛 기록의 한계면               → 알리되 실패시키지 않음
    ✔/✘ 줄이 하나도 없으면                  → 감사가 돌지 않은 것(실패)
"""

from __future__ import annotations

import sys

# 옛 기록의 정상적 한계 — 결정이 달라진 게 아니다.
BENIGN = ("스냅샷 없음", "구버전 기록", "champion_before 없음")

VERDICT = ("✔", "✘")


def classify(lines: list[str]) -> dict:
    """출력 줄들을 판정별로 나눈다."""
    passed, benign, bad = [], [], []
    for ln in lines:
        if not any(v in ln for v in VERDICT):
            continue
        if "✔" in ln:
            passed.append(ln.strip())
        elif any(b in ln for b in BENIGN):
            benign.append(ln.strip())
        else:
            bad.append(ln.strip())
    return {"passed": passed, "benign": benign, "bad": bad}


def env_drifted(lines: list[str]) -> bool:
    """실행 환경이 기록과 다른가 — 알릴 값이지 실패시킬 값은 아니다."""
    return any("실행 환경이 기록과 다름" in ln for ln in lines)


def decide(text: str, *, notify=None, log=print) -> int:
    """종료코드를 돌려준다. notify(msg)가 있으면 진짜 사건일 때만 부른다."""
    lines = text.splitlines()
    got = classify(lines)

    if not (got["passed"] or got["benign"] or got["bad"]):
        # 결과 줄이 하나도 없으면 감사가 '조용히 죽은' 것이다.
        # 통과로 읽으면 안 된다 — 돌지 않은 검증은 검증이 아니다.
        log("❌ 재현 감사 출력 없음 — verify가 실행되지 못했다")
        log(text[-2000:])
        return 1

    if env_drifted(lines):
        log("ℹ️ 실행 환경이 기록과 다릅니다(라이브러리 버전 등). 재현 판정 "
            "자체는 아래 ✔/✘를 따릅니다 — 이 사실만으로는 경보하지 않습니다.")
    if got["benign"]:
        log(f"ℹ️ 옛 기록의 한계로 검증 대상에서 빠진 항목 {len(got['benign'])}건:")
        for ln in got["benign"]:
            log("   " + ln)

    if not got["bad"]:
        extra = f" · 대상 외 {len(got['benign'])}건" if got["benign"] else ""
        log(f"✅ 재현 감사 통과 — 일치 {len(got['passed'])}건{extra}")
        return 0

    msg = ("🚨 재현성 감사 불일치 — 같은 스냅샷·같은 코드로 어제 결정이 "
           "재현되지 않았습니다. 장부의 '조작 불가능' 주장이 걸린 문제라 "
           "즉시 확인이 필요합니다.\n" + "\n".join(got["bad"][:10]))
    log(msg)
    if notify is not None:
        notify(msg)
    return 1


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "verify.txt"
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        print(f"❌ {path} 없음 — 재현 감사가 실행되지 않았다")
        return 1

    def _notify(msg: str) -> None:
        try:
            from quant.live.notifications import get_notifier
            get_notifier().send(msg)
        except Exception as exc:  # noqa: BLE001 — 알림 실패가 판정을 바꾸지 않는다
            print(f"(알림 전송 실패: {exc})")

    return decide(text, notify=_notify)


if __name__ == "__main__":
    raise SystemExit(main())
