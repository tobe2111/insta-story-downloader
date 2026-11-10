"""지나간 기록은 고쳐지지 않는다 — 그 약속을 **커밋 전에 기계가 확인한다** (감사 378).

이 제품의 규칙: *"옛 기록은 고치지 않는다."* 그런데 그 규칙을 지키는 것은 지금까지
사람의 기억이었다. 배치의 결함 하나가 지난달 줄을 조용히 바꿔도 장부 관문은 '오늘
장부가 말이 되는가'만 보므로 통과한다.

■ 규칙

  직전 커밋(HEAD)의 장부와 방금 쓴 장부를 견준다. HEAD의 **마지막 날짜보다 앞선**
  줄은 새 장부에 **글자 그대로** 있어야 한다.

  허용되는 것(전부 설계된 동작):
    · 마지막 날짜의 줄은 다시 계산될 수 있다(되돌림 — 재료가 늦게 온 날).
    · 보존 한도로 **앞에서** 잘려 나가는 줄.
    · 사이에 새 날짜가 끼어드는 것(빠진 봉 복구).

  실측(2026-10-08~11-10 본 계좌 장부의 커밋 이력): 위반 0건.
"""
from __future__ import annotations


def rewritten_past(prev: list[dict], cur: list[dict], key: str = "date") -> list[dict]:
    """HEAD 장부(`prev`)의 지난 줄 중 새 장부(`cur`)에서 바뀌었거나 사라진 것."""
    rows = [r for r in prev or [] if r.get(key)]
    if not rows or not cur:
        return [] if not rows else [{"date": str(r[key])[:10], "what": "gone"}
                                    for r in rows[:-1]]
    last = max(str(r[key]) for r in rows)
    cur_by = {}
    for r in cur:
        if r.get(key):
            cur_by.setdefault(str(r[key]), []).append(r)
    first = min(cur_by) if cur_by else None
    out = []
    for r in rows:
        d = str(r[key])
        if d >= last:
            continue                      # 마지막 날은 되돌림으로 다시 쓸 수 있다
        if first is not None and d < first:
            continue                      # 앞에서 잘린 줄(보존 한도)
        same = cur_by.get(d)
        if not same:
            out.append({"date": d[:10], "what": "gone"})
        elif r not in same:
            diff = sorted(k for k in set(r) | set(same[-1]) if r.get(k) != same[-1].get(k))
            out.append({"date": d[:10], "what": "changed", "fields": diff[:8]})
    return out
