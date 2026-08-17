"""파생 지표(펀딩비·미결제약정)를 **시세와 같은 거래소 사다리**로 받는다.

⚠️ 무슨 일이 있었나 (감사 270)

    코인 5종목의 선택 피처 3개 — 펀딩비(`x_funding`), 펀딩 변화
    (`x_funding_chg`), 미결제약정 변화(`x_oi_chg5`) — 가 **한 번도 붙지
    않은 채** 몇 주가 지났다. 장부의 계측기는 "이 셋이 전 종목에서
    빠졌다"까지만 말했고, 왜인지는 아무도 몰랐다.

    이유는 단순했다. 시세를 받는 쪽은 바이낸스가 막히면 okx → kucoin →
    kraken 순으로 내려가는 **사다리**를 갖고 있었고 실제로 okx에서 받아
    왔다. 그런데 펀딩비와 미결제약정은 `binance` / `binanceusdm`이 코드에
    **그대로 박혀** 있었다. 즉 시세는 폴백하는데 부가 지표는 폴백하지
    않았고, 막힌 문을 매일 두드리고 있었다.

    같은 규칙(어느 거래소에 물어보는가)이 **두 곳에 따로 적혀** 있었기
    때문에 생긴 일이다 — FROZEN_IDEAS ①이 말하는 바로 그 병이다.

무엇을 하는가

    사다리의 정본은 `quant.data.crypto.spot_ladder()` 하나다. 이 모듈은
    그 순서를 그대로 따라가되, **현물과 파생의 거래소 이름이 다른 곳**만
    대응표로 옮긴다(바이낸스는 현물과 선물이 아예 다른 접속처다).

정직한 한계

    · 사다리를 다 내려가도 못 받을 수 있다(지역 차단·상장 없음·점검).
      그때는 조용히 넘어가지 않고 **거래소별 실패 사유**를 장부에 남긴다.
    · 거래소마다 펀딩 정산 주기와 미결제약정 집계 방식이 조금씩 다르다.
      okx에서 받은 펀딩과 바이낸스에서 받은 펀딩은 같은 값이 아니다.
      그래서 **어느 거래소에서 받았는지를 함께 기록**한다 — 나중에 값이
      튀면 제공처가 바뀐 날을 먼저 의심할 수 있어야 한다.
"""
from __future__ import annotations

from quant.data.crypto import spot_ladder

# 현물 거래소 이름 → 파생(무기한 선물) 거래소 이름.
#
# 여기에는 **이름 대응만** 적는다. 순서는 적지 않는다 — 순서를 여기에도
# 적는 순간 사다리가 두 벌이 되고, 한쪽만 고쳐지는 날이 온다.
#
# okx는 하나의 접속처가 현물과 스왑을 함께 다루므로 이름이 같다.
_SPOT_TO_DERIV = {
    "binance": "binanceusdm",
    "okx": "okx",
    "kucoin": "kucoinfutures",
    "kraken": "krakenfutures",
}


def deriv_ladder(preferred: str | None = None) -> tuple[str, ...]:
    """펀딩·미결제약정을 물어볼 거래소 순서 — 시세 사다리를 그대로 따라간다.

    preferred: 그 종목 **시세를 실제로 준** 현물 거래소 이름(장부의
    `data_source`). 시세와 같은 곳에서 부가 지표를 받는 것이 첫 선택이다.

    현물에는 있는데 파생 대응이 없는 거래소는 조용히 건너뛴다 — 없는 것을
    물어보는 것은 실패가 아니라 애초에 해당 없음이다.
    """
    out: list[str] = []
    for spot in spot_ladder(preferred):
        deriv = _SPOT_TO_DERIV.get(spot)
        if deriv and deriv not in out:
            out.append(deriv)
    return tuple(out)


def perp_symbol(symbol: str) -> str:
    """현물 심볼을 무기한 선물 심볼로 바꾼다: `BTC/USDT` → `BTC/USDT:USDT`.

    ⚠️ 이것도 감사 270에서 드러난 절반이다. 거래소를 okx로 바꿔도
    `BTC/USDT`를 그대로 물어보면 okx는 그걸 **현물 시장**으로 읽고
    "펀딩비 없음"을 돌려준다. 통합 라이브러리(ccxt)에서 무기한 선물은
    `기초/결제:담보` 형식으로 따로 부른다.

    이미 `:`가 들어 있으면 그대로 둔다(호출자가 명시한 것이다).
    """
    s = str(symbol or "")
    if ":" in s or "/" not in s:
        return s
    return f"{s}:{s.split('/', 1)[1]}"


# 거래소가 그 지표를 **애초에 제공하지 않는** 경우를 실패와 섞지 않기 위한
# 표식. 예: 크라켄 선물은 펀딩비는 주지만 미결제약정 '이력'은 주지 않는다.
UNSUPPORTED = "그 거래소가 제공하지 않는 지표"


_SUPPORTS_CACHE: dict[tuple[str, str], bool | None] = {}


def supports(exchange: str, capability: str) -> bool | None:
    """그 거래소가 이 지표를 제공한다고 **스스로 밝히는가**.

    통합 라이브러리(ccxt)가 거래소별로 갖고 있는 기능표를 읽을 뿐이라
    네트워크를 쓰지 않는다. 라이브러리가 없으면 None(모름) — 모름을
    '아니오'로 바꾸지 않는다. 물어보지도 않고 포기하는 쪽이 더 나쁘다.

    기능표는 프로그램이 도는 동안 바뀌지 않으므로 한 번만 읽는다(종목마다
    지표마다 다시 만들면 배치가 그만큼 느려지고, 느린 장치는 언젠가 꺼진다).
    """
    key = (exchange, capability)
    if key not in _SUPPORTS_CACHE:
        try:
            import ccxt
            _SUPPORTS_CACHE[key] = bool(
                getattr(ccxt, exchange)().has.get(capability))
        except Exception:  # noqa: BLE001 — 라이브러리 없음/알 수 없는 거래소
            _SUPPORTS_CACHE[key] = None
    return _SUPPORTS_CACHE[key]


def walk_ladder(preferred: str | None, symbol: str, fetch_one,
                capability: str | None = None):
    """사다리를 내려가며 처음으로 값을 준 거래소에서 멈춘다.

    fetch_one(선물심볼, 거래소) → Series(빈 것일 수 있음)
    capability: ccxt 기능표 이름(예: "fetchOpenInterestHistory"). 주면
    제공하지 않는 거래소는 **물어보지 않고** 건너뛴다.

    반환: (series | None, 성공한 거래소 | None, {거래소: 실패사유})

    빈 응답도 실패로 센다 — '연결은 됐지만 줄 게 없다'와 '값이 있다'를
    같게 두면 사다리가 첫 칸에서 멈춘 채 매일 빈손으로 돌아온다.
    """
    psym = perp_symbol(symbol)
    tried: dict[str, str] = {}
    for ex in deriv_ladder(preferred):
        if capability and supports(ex, capability) is False:
            # 차단된 것과 없는 것은 다른 사건이다 — 같은 말로 적으면
            # 다음 사람이 방화벽을 뒤지다 하루를 버린다.
            tried[ex] = UNSUPPORTED
            continue
        try:
            s = fetch_one(psym, ex)
        except Exception as exc:  # noqa: BLE001 — 다음 거래소로 계속 간다
            tried[ex] = f"{type(exc).__name__}: {exc}"[:80]
            continue
        if s is not None and len(s) > 0:
            return s, ex, tried
        tried[ex] = "빈 응답"
    return None, None, tried


def ladder_reason(tried: dict[str, str]) -> str:
    """사다리를 다 내려가고도 못 받았을 때 장부에 남길 한 줄.

    거래소 이름을 빼면 "없음"만 남아 다음 사람이 다시 처음부터 조사한다.
    """
    if not tried:
        return "물어볼 거래소가 없음(파생 대응표에 아무것도 없다)"
    parts = ", ".join(f"{ex}={why}" for ex, why in tried.items())
    return f"거래소 {len(tried)}곳 모두 실패 — {parts}"
