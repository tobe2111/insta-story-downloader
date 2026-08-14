"""외부 데이터 소스가 **왜** 실패했는지를 데이터에 실어 나른다.

⚠️ 왜 필요한가 (2026-08-14). 선택 피처 5개(코인 펀딩·펀딩변화·미결제약정,
한국 외국인·기관 수급)가 **전 종목에서 한 번도 붙지 않고 있었다.** 계측기는
"이 다섯이 빠졌다"까지는 말해 줬지만 **왜**는 말하지 못했다 — 부착 함수들이
전부 `except`로 삼키고 `log.warning` 한 줄만 남긴 뒤 원본을 돌려주기
때문이다. 그 로그는 GitHub Actions 실행 로그에만 있고, 며칠 지나면 사라진다.

그래서 몇 주 동안 아무도 원인을 좁히지 못했다. 네트워크 차단인지, 심볼이
바뀐 건지, 라이브러리가 없는 건지, 응답이 빈 건지 — 전부 다르게 대응해야
하는데 장부에는 똑같이 "없음"으로만 남았다.

이 모듈은 실패 사유를 df.attrs에 실어 daily 장부까지 흘려보낸다. 고치는
장치가 아니라 **고칠 수 있게 만드는** 장치다.

원칙:
  · 실패해도 본류를 막지 않는다(선택 피처는 '있으면 쓰는' 맥락이다)
  · 다만 **조용히 넘어가지는 않는다** — 이유가 장부에 남는다
  · 사유 문자열은 짧게 자른다(장부가 스택트레이스로 부풀지 않게)
"""
from __future__ import annotations

ATTR_KEY = "feature_source_errors"
MAX_REASON = 200


def note_source_failure(df, source: str, reason: str) -> None:
    """이 프레임에 '이 소스가 이래서 실패했다'를 적어 둔다(제자리 수정).

    df가 None이거나 attrs를 못 쓰는 객체여도 조용히 넘어간다 — 기록 장치가
    본류를 죽이면 안 된다.
    """
    try:
        errs = dict(df.attrs.get(ATTR_KEY) or {})
        errs[str(source)] = str(reason)[:MAX_REASON]
        df.attrs[ATTR_KEY] = errs
    except Exception:  # noqa: BLE001  # pragma: no cover
        pass


def note_exception(df, source: str, exc: BaseException) -> None:
    """예외를 '타입: 메시지' 한 줄로 요약해 적는다."""
    note_source_failure(df, source, f"{type(exc).__name__}: {exc}")


def source_errors(df) -> dict:
    """이 프레임에 쌓인 소스별 실패 사유. 없으면 빈 dict."""
    try:
        return dict(df.attrs.get(ATTR_KEY) or {})
    except Exception:  # noqa: BLE001  # pragma: no cover
        return {}
