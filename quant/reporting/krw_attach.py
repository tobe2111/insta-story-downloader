"""공개 장부에 원화 환산을 **덧붙이는 뒷단계**.

사장님 지시(2026-08-24): *"각 페이지 당 최종 수익 결과 한국돈으로도
알려줘."*

■ 왜 트랙 모듈 안에서 안 하고 여기서 하나 (이게 이 파일의 존재 이유다)

처음에는 세 트랙의 리포트 작성기 안에서 환산했다. 그러자 기존 검사
(`test_the_currency_never_mixes`)가 즉시 걸렸다 — **트레이딩 모듈은
환율을 알아서는 안 된다**는 하드 경계다.

그 경계는 감사 254가 남긴 것이다. 그때 META를 달러 시가(596.98)로 사고
원화 종가(832,868)로 평가하는 바람에 **100만원 계좌가 7,249만원으로
찍혔다(+7,150%)**. 환산이 필요한 자리를 두 군데에 나눠 적으면 반드시 한
곳이 빠진다 — 그래서 아예 **체결·평가가 도는 모듈은 원화라는 말을 모르게**
두기로 한 것이다.

검사가 맞았다. 그래서 환산은 장부가 다 쓰이고 **난 뒤에**, 공개용 JSON에만
덧붙인다. 이 순서면:

  · 체결·평가·손익 계산은 원래 통화 안에서만 돈다 (경계 유지)
  · 화면은 여전히 자기 계산을 하지 않는다 (감사 197 유지)
  · 원화는 읽기 편하라고 옆에 적는 값이라는 성격이 파일 구조로 드러난다

■ 실패해도 아무것도 망가뜨리지 않는다

환율을 못 받으면 `krw`를 안 붙이고 끝낸다. 원본 JSON은 그대로다 —
참고 값 하나 때문에 그날 기록이 사라지면 안 된다.
"""
from __future__ import annotations

import json
import os

# 어느 공개 장부에 붙일 것인가 → (파일, 그 계좌의 통화)
TARGETS = {
    "intraday.json": "USDT",        # 코인 단타
    "intraday_us.json": "USD",      # 미국주식 단타
    "futures.json": "USDT",         # 코인 선물
}


def attach(docs_dir: str = "docs", *, rate=None, fetch=None) -> dict:
    """공개 장부들에 `krw` 블록을 덧붙인다. 돌려주는 것은 파일별 결과.

    ⚠️ 계좌의 `equity`·`start_cash`는 **건드리지 않는다.** 원화는 별도 칸에
       들어가고, 화면이 '환산'이라고 말한다.
    """
    from quant.live.krw import krw_view
    out = {}
    for name, currency in sorted(TARGETS.items()):
        path = os.path.join(docs_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            out[name] = "장부 없음"       # 아직 안 돈 트랙 — 정상일 수 있다
            continue
        # 장부가 스스로 밝힌 통화를 우선한다. 없으면 위 표를 쓴다.
        cur = str(d.get("currency") or currency)
        k = krw_view(d.get("equity"), d.get("start_cash"), cur,
                     rate=rate, fetch=fetch)
        if k is None:
            out[name] = "환율 없음 — 건너뜀"
            continue
        d["krw"] = k
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(path, d)
        out[name] = f"{k['equity']:,.0f}원 (환율 {k['rate']:,.2f})"
    return out
