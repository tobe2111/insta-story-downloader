"""이 봉 묶음으로 매매해도 되는가 — 주문 경로가 공유하는 단 하나의 문.

⚠️ 왜 한 곳인가(2026-08-11 감사 85): 같은 판정이 실행 경로마다 따로 적혀
있었고, 결과는 이랬다.

    daily.py       ✅ 합성 폴백 거부 · 무결성 게이트
    daily_live.py  ✅ 합성 폴백 거부
    engine.py      ❌ 둘 다 없음   ← quant live --real
    multi.py       ❌ 둘 다 없음   ← quant live --real (다종목)

거래소 API가 전부 실패하면 `CryptoDataProvider._fallback`이 **GBM 난수
걷기**(시작가 100.0)를 돌려주고 `synthetic_fallback` 표식을 단다. 새벽
배치는 그걸 보고 매매를 거부한다 — 사이트가 "실데이터로만 판단한다"고
말하는 근거다. 그런데 연속 실행 루프는 그 표식을 읽지 않았다.

실제 BTC가 6천만 원인데 폴백 시세는 100이다. 주문 수량은
`비중 × 자산 ÷ 가격`이므로 **60만 배** 틀린다. 즉 '조금 나쁜 데이터로
매매한다'가 아니라 **존재하지 않는 시장에 대고 매매한다**는 뜻이다.

⚠️ 표식은 **실패한 실조회**에만 붙는다. 사용자가 일부러 고른 합성 시장
   (`--market synthetic`)에는 붙지 않으므로 그쪽은 계속 정상 동작한다.
"""
from __future__ import annotations


def unusable_reason(df, *, require_real_data: bool = True,
                    check_quality: bool = True) -> str | None:
    """매매하면 안 되는 이유를 돌려준다. 매매해도 되면 None.

    이유를 문자열로 주는 것은 호출부가 **왜 건너뛰었는지 장부에 남길 수
    있게** 하기 위해서다. 조용히 건너뛴 사이클은 나중에 설명할 수 없다.
    """
    if df is None or len(df) == 0:
        return "데이터 없음"
    attrs = getattr(df, "attrs", None) or {}
    if require_real_data and attrs.get("synthetic_fallback"):
        return "합성 폴백 시세(거래소 조회 실패) — 진짜 시장이 아님"
    if check_quality:
        try:
            from quant.data.quality import is_severe, scan_ohlcv
            q = scan_ohlcv(df)
        except Exception:  # noqa: BLE001 — 점검 자체가 매매를 막지는 않는다
            return None
        if is_severe(q):
            bad = {k: v for k, v in (q or {}).items() if v}
            return f"데이터 무결성 위반: {bad}"
    return None
