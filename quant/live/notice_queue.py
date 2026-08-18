"""**저장된 것만 방송한다** — 알림을 커밋 뒤로 미루는 대기열 (감사 283).

⚠️ 왜 이 파일이 생겼나 (2026-08-18). 사장님이 디스코드 화면을 보여 주셨다.

    07:52  📦 통합 분산 계좌: 자산 999,078 (-0.09%)
    08:23  🔁 챔피언 교체: us_stock:SPY, us_stock:QQQ
    08:23  🚨 [Quant] 'Nightly Retrain' 실패 (2026-08-17)

앞의 둘은 **저장되지 않았다.** 장부는 그날도 2026-08-15에 멈춰 있고,
``state/champions.json``의 마지막 수정은 08-16이다. 계산은 됐지만 그 뒤
장부 관문이 죽어 커밋이 막혔기 때문이다(감사 280).

배치의 순서가 이랬다.

    ① 계산 → ② **알림 전송** → ③ 장부 관문 → ④ 커밋

③에서 죽으면 ②는 이미 나간 뒤다. 그래서 사장님 폰에는 **일어나지 않은
일**이 사실처럼 남았다. 같은 메시지 아래에 실패 경보가 함께 있었지만,
위의 숫자를 먼저 읽으면 반대로 읽힌다 — 그리고 사람은 위부터 읽는다.

이 저장소가 반복해서 지켜 온 규칙과 정면으로 어긋난다: **모르는 것과
아닌 것은 다르다.** "저장될 예정"과 "저장됐다"도 다르다.

고침: ``QUANT_DEFER_NOTICE=1``이면 알림을 보내지 않고 **여기 쌓아 둔다.**
커밋과 푸시가 끝난 뒤 워크플로가 ``quant notify --flush``를 불러 그때
내보낸다. 관문에서 죽으면 대기열은 그대로 버려지고(러너와 함께 사라진다),
실패 경보만 나간다 — **조용히 틀리느니 시끄럽게 멈춘다**의 알림판이다.
"""

from __future__ import annotations

import json
import os
import pathlib

# 러너와 함께 사라지는 자리에 둔다. `.gitignore`에도 있어서 커밋에 섞이지
# 않는다 — 알림 대기열이 장부에 남으면 그것대로 혼란이다.
DEFAULT_PATH = "state/.notice_queue.jsonl"
ENV_DEFER = "QUANT_DEFER_NOTICE"
ENV_PATH = "QUANT_NOTICE_QUEUE"


def queue_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get(ENV_PATH) or DEFAULT_PATH)


def deferring() -> bool:
    """지금 알림을 미뤄야 하는가."""
    return str(os.environ.get(ENV_DEFER) or "").strip().lower() in (
        "1", "true", "yes", "on")


def stage(message: str) -> None:
    """나중에 보낼 알림을 쌓아 둔다.

    ⚠️ 쌓기가 실패해도 배치를 죽이지 않는다 — 알림은 옵션이고 장부가
       본체다. 다만 조용히 넘어가지는 않는다(콘솔에 남긴다).
    """
    p = queue_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"message": message}, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"(알림 대기열 기록 실패: {exc})")


def pending() -> list[str]:
    """쌓여 있는 알림. 파일이 없거나 깨졌으면 빈 목록."""
    p = queue_path()
    if not p.is_file():
        return []
    out: list[str] = []
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line).get("message")
        except json.JSONDecodeError:
            continue                       # 한 줄이 깨져도 나머지는 보낸다
        if isinstance(msg, str) and msg:
            out.append(msg)
    return out


def discard() -> None:
    """대기열을 버린다 — 보내지 않기로 한 경우."""
    try:
        queue_path().unlink(missing_ok=True)
    except OSError as exc:
        print(f"(알림 대기열 정리 실패: {exc})")


def flush(send) -> int:
    """쌓인 알림을 **지금** 내보낸다. 보낸 건수를 돌려준다.

    ``send``는 문자열 하나를 받는 함수다(테스트에서 갈아 끼운다).

    ⚠️ 보낸 뒤에 지운다. 먼저 지우면 전송이 실패했을 때 그 사실이 통째로
       사라진다 — 이 저장소가 여러 번 잡은 '조용한 소실'이다.
    """
    msgs = pending()
    for m in msgs:
        send(m)
    discard()
    return len(msgs)
