"""실적 발표 캘린더 가드 — 예고된 종목별 이벤트 창에서 비중을 줄인다.

FOMC 가드(quant/events)와 같은 원리를 종목 단위로: 실적 발표일 전후는
갭 위험이 평소의 몇 배라, 하루짜리 방향 모델의 엣지가 가장 약한 날이다.
발표 ±pad_days 창에서는 비중을 절반으로 줄인다(관망이 아니라 절반 —
발표가 좋은 쪽일 확률도 절반이므로 전면 회피는 과잉 반응이다).

재현성: 조회한 발표일은 state/earnings.json에 캐시되어 그날의 판단 근거가
파일로 남고, 일별 기록에도 어떤 날짜로 가드가 발동했는지 함께 적힌다 —
"그날 왜 비중이 절반이었나"를 장부만으로 답할 수 있다.

야후(yfinance) 캘린더는 미국 주식만 안정적이다 — 한국 주식·코인은 조회가
비어 그냥 가드 미발동(무해). 조회 실패도 미발동(실패가 매매를 막으면 안 됨).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from quant.utils.logging import get_logger

log = get_logger("data.earnings")

CACHE_FILE = "earnings.json"
REFRESH_DAYS = 7          # 캐시 신선도 — 발표일은 주 단위로만 움직인다
GUARD_FACTOR = 0.5        # 가드 발동 시 비중 배수
PAD_DAYS = 1              # 발표일 ±N일 창


def _fetch_dates(symbol: str) -> list[str]:
    """야후에서 (미래 포함) 실적 발표일 목록을 ISO 문자열로 받는다."""
    import yfinance as yf
    df = yf.Ticker(symbol).get_earnings_dates(limit=8)
    if df is None or df.empty:
        return []
    out = []
    for ts in df.index:
        try:
            out.append(ts.date().isoformat())
        except AttributeError:
            continue
    return sorted(set(out))


def _known_dates(symbol: str, today: _dt.date, state_dir: str,
                 fetch) -> list[_dt.date]:
    """캐시(필요 시 갱신)에 있는 실적 발표일 전체 — 과거·미래 모두.

    state/earnings.json에 심볼별 {dates, fetched}로 캐시하고 REFRESH_DAYS마다
    갱신한다 — 하루 20종목 순회가 야후를 반복 호출하지 않게, 그리고 그날
    판단에 쓴 캘린더가 파일로 남게(재현성).
    """
    path = os.path.join(state_dir, CACHE_FILE)
    cache: dict = {}
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    entry = cache.get(symbol)
    fresh = False
    if entry and entry.get("fetched"):
        try:
            age = (today - _dt.date.fromisoformat(entry["fetched"])).days
            fresh = 0 <= age <= REFRESH_DAYS
        except ValueError:
            fresh = False
    if not fresh:
        ok = True
        try:
            dates = fetch(symbol)
        except Exception as exc:  # noqa: BLE001
            # ⚠️ **실패를 '오늘 받아온 것'으로 도장 찍으면 안 된다**(감사 191).
            #    예전에는 실패해도 `fetched`에 오늘을 적었다. 그러면 다음
            #    실행에서 `fresh`가 참이 되어 **7일 동안 재시도를 안 한다.**
            #    첫 조회가 실패했다면 `dates`는 빈 목록이므로, 그 일주일은
            #    "이 종목엔 실적 발표가 없다"로 굳는다 — 실측:
            #
            #        08-12 조회 실패 → 캐시 {dates: [], fetched: 08-12}
            #        08-13 (실제 발표일) 조회 정상인데 부르지도 않음 → 가드 1.0
            #
            #    가드가 지키려는 바로 그 날에 꺼져 있다. 발표일은 갭이 가장
            #    큰 날이라 이건 '무해한 미발동'이 아니다.
            #
            #    실패했으면 **옛 날짜(fetched)를 그대로 둔다** — 그래야 내일
            #    다시 시도한다. 옛 캐시의 dates는 살려 쓰되 신선하다고
            #    말하지 않는다. '못 받았다'와 '없다'는 다르다.
            ok = False
            log.warning("실적 캘린더 조회 실패 %s: %s", symbol, exc)
            dates = (entry or {}).get("dates", [])   # 옛 캐시라도 쓴다
            err = f"{type(exc).__name__}: {exc}"[:160]
        else:
            err = ""
        # ⚠️ **왜 비어 있는지를 남긴다**(2026-08-19 감사 289). 예전에는
        #    `dates`가 비면 그걸로 끝이었다 — "이 종목엔 발표가 없다"와
        #    "받아오지 못했다"가 파일에서 똑같이 `[]`로 보였다.
        #    실제로 lxml이 없어서 조회가 통째로 실패하고 있었고, 캐시는
        #    6종목 전부 `dates: []`였으며, 장부의 earnings_guard는 매일
        #    비어 있었다. **가드가 한 번도 발동한 적이 없는데 화면은
        #    조용한 날과 구별되지 않았다.**
        #    모르는 것과 아닌 것은 다르다 — 이 저장소의 규칙 그대로다.
        entry = {"dates": dates, "error": err,
                 "fetched": today.isoformat() if ok
                 else (entry or {}).get("fetched", "")}
        cache[symbol] = entry
        try:
            from quant.utils.jsonio import atomic_write_json
            atomic_write_json(path, cache)
        except Exception:  # noqa: BLE001 — 캐시 실패가 판단을 막으면 안 된다
            pass
    out: list[_dt.date] = []
    for iso in entry.get("dates", []):
        try:
            out.append(_dt.date.fromisoformat(iso))
        except ValueError:
            continue
    return sorted(out)


def next_earnings_date(symbol: str, today: _dt.date,
                       state_dir: str = "state",
                       fetch=_fetch_dates) -> _dt.date | None:
    """오늘 이후(오늘 포함) 가장 가까운 실적 발표일. 모르면 None."""
    for d in _known_dates(symbol, today, state_dir, fetch):
        if d >= today:
            return d
    return None


def nearest_earnings_date(symbol: str, today: _dt.date,
                          state_dir: str = "state",
                          fetch=_fetch_dates) -> _dt.date | None:
    """오늘과 가장 가까운 실적 발표일 — **과거도 포함**한다.

    ⚠️ 왜 따로 필요한가(2026-08-11 감사): 가드는 "발표 ±N일"이라고 문서에도
    사이트에도 적혀 있는데, 미래 날짜만 찾다 보니 실제로는 **발표 전만**
    작동했다. 발표 다음 날은 갭과 변동성이 가장 큰 구간인데 가드가 이미
    꺼진 상태였다 — 문서가 약속한 보호의 절반이 없었다.
    """
    dates = _known_dates(symbol, today, state_dir, fetch)
    return min(dates, key=lambda d: abs((d - today).days)) if dates else None


def calendar_health(symbols, state_dir: str = "state") -> dict:
    """실적 캘린더가 **지금 무엇을 알고 있는가** — 캐시만 읽는다(감사 289).

    가드는 발표일을 알아야 발동한다. 아무 날짜도 모르면 가드는 매일
    1.0을 돌려주고, 그 화면은 '발표가 없는 조용한 날'과 똑같이 보인다.
    그 둘을 구별할 수 있게 숫자로 남긴다.

    반환: {"symbols": 물어본 수, "known": 발표일을 아는 종목 수,
           "errors": {심볼: 마지막 오류}, "checked": 캐시에 있는 종목 수}
    아무 문제가 없으면 빈 dict — 장부에 잡음을 남기지 않는다.
    """
    path = os.path.join(state_dir, CACHE_FILE)
    cache: dict = {}
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    syms = [str(s) for s in (symbols or [])]
    known, errors, checked = 0, {}, 0
    for sym in syms:
        entry = cache.get(sym)
        if entry is None:
            continue
        checked += 1
        if entry.get("dates"):
            known += 1
        if entry.get("error"):
            errors[sym] = entry["error"]
    if not syms:
        return {}
    out = {"symbols": len(syms), "checked": checked, "known": known}
    if errors:
        out["errors"] = errors
    return out


def earnings_guard_factor(symbol: str, asof: _dt.date,
                          state_dir: str = "state",
                          pad_days: int = PAD_DAYS,
                          fetch=_fetch_dates) -> tuple[float, str | None]:
    """(비중 배수, 발동 사유 날짜) — 발표 ±pad_days 창이면 (0.5, 날짜)."""
    try:
        # 가장 가까운 발표일(과거 포함) — 발표 '다음 날'도 창 안이다
        d = nearest_earnings_date(symbol, asof, state_dir, fetch=fetch)
    except Exception as exc:  # noqa: BLE001
        log.warning("실적 가드 판단 실패 %s: %s", symbol, exc)
        return 1.0, None
    if d is not None and abs((d - asof).days) <= pad_days:
        return GUARD_FACTOR, d.isoformat()
    return 1.0, None


def attach_earnings_days(df, symbol: str, state_dir: str = "state"):
    """실적 발표일 표식 컬럼(earn_day)을 붙인다 — **캐시만 읽는다.**

    PEAD 도전자(quant/strategies/pead.py)의 재료다. 네트워크를 부르지
    않는 이유: 오디션 백테스트는 오프라인 스냅샷으로 돌고, 발표일은
    바뀌지 않는 과거 사실이라 매주 갱신되는 이 캐시로 충분하다.

    캐시에 이 종목이 없으면 **컬럼을 붙이지 않는다** — 0으로 채우면
    "발표가 없었다"와 "몰랐다"가 같아진다. 컬럼이 없으면 PEAD는 관망한다
    (수급 없는 시장의 supply_som과 같은 규약).

    이름이 `x_` 접두가 **아닌** 이유: ml._features()는 x_ 컬럼을 전부
    ML 입력으로 자동 포함한다. 이 컬럼은 PEAD 전용 신호 재료이지 ML
    거시 피처가 아니다 — x_를 붙이면 기존 ML 챔피언 전원의 피처 집합이
    가설 없이 조용히 바뀐다(그 자체가 등록 안 된 시행이 된다).
    """
    try:
        path = os.path.join(state_dir, CACHE_FILE)
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
        dates = set((cache.get(symbol) or {}).get("dates") or [])
        if not dates:
            return df
        df = df.copy()
        idx_days = [str(d)[:10] for d in df.index.date] if hasattr(
            df.index, "date") else [str(i)[:10] for i in df.index]
        df["earn_day"] = [1.0 if d in dates else 0.0 for d in idx_days]
        return df
    except (OSError, ValueError, AttributeError) as exc:
        log.warning("발표일 컬럼 부착 실패(%s) — 생략: %s", symbol, exc)
        return df


# ── 한국 발표일 — DART 전자공시 (2026-08-23, 키 조건부) ─────────────
#
# 왜: PEAD(실적 발표 후 표류)는 발표일을 아는 시장에서만 움직인다. 야후
# 캘린더는 한국 주식에서 비어 있어 한국은 전부 관망이었다. DART(금융감독원
# 전자공시)는 공식·무료 소스지만 **인증키 등록**이 필요하다.
#
# 키 규약(보안):
#   · 키는 환경변수(DART_API_KEY)에만 산다 — 저장소·캐시·로그 어디에도
#     키 값이 적히지 않는다. HTTP 오류 메시지의 URL은 공용 헬퍼가
#     crtfc_key를 가린다(quant/utils/http.py).
#   · 키가 없으면 **조용히 아무것도 하지 않는다** — 매일 경고를 찍으면
#     '키 없음'이 소음이 되어 진짜 고장을 가린다. 키가 들어오는 순간
#     다음 배치부터 자동으로 수집이 시작된다(코드 변경 불필요).
#
# 발표일의 정의(대용치, 숨기지 않는다): DART **정기공시(사업·반기·분기
# 보고서) 접수일**을 발표일로 쓴다. 원문 정의는 잠정실적 공시일이지만
# 공시 유형이 회사마다 달라 기계 판별이 불안정하고, 잠정공시가 없는
# 회사에서는 정기보고서가 곧 첫 공개다. ETF는 실적 공시가 없어 목록이
# 비는 것이 정상이다(그 종목은 PEAD가 관망 — 사실과 일치).
DART_KEY_ENV = "DART_API_KEY"
DART_HOST = "https://opendart.fss.or.kr"
CORP_CODE_FILE = "dart_corp_codes.json"
CORP_CODE_REFRESH_DAYS = 30       # 상장사 코드표는 거의 안 변한다
DART_FROM = "20200101"            # PEAD 백테스트 창 시작과 맞춘다
DART_MAX_PAGES = 5                # 정기공시 4건/년 × 7년 ≪ 100건/쪽


def dart_key() -> str | None:
    """DART 인증키 — 환경변수에만 산다. 값은 어디에도 기록하지 않는다."""
    k = os.environ.get(DART_KEY_ENV, "").strip()
    return k or None


def _corp_codes(state_dir: str, today: _dt.date) -> dict:
    """{6자리 종목코드: DART corp_code} — 30일 캐시, 실패 시 옛 캐시.

    실패를 '오늘 받아온 것'으로 도장 찍지 않는다(_known_dates와 같은 규칙).
    """
    path = os.path.join(state_dir, CORP_CODE_FILE)
    cache: dict = {}
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    fresh = False
    if cache.get("fetched"):
        try:
            age = (today - _dt.date.fromisoformat(cache["fetched"])).days
            fresh = 0 <= age <= CORP_CODE_REFRESH_DAYS
        except ValueError:
            fresh = False
    if not fresh:
        try:
            import io
            import xml.etree.ElementTree as ET
            import zipfile

            from quant.utils.http import get_bytes
            raw = get_bytes(f"{DART_HOST}/api/corpCode.xml"
                            f"?crtfc_key={dart_key()}", timeout=60)
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                xml_bytes = zf.read(zf.namelist()[0])
            codes = {}
            for el in ET.fromstring(xml_bytes).iter("list"):
                sc = (el.findtext("stock_code") or "").strip()
                cc = (el.findtext("corp_code") or "").strip()
                if sc and cc:
                    codes[sc] = cc
            if not codes:
                raise RuntimeError("코드표가 비어 있다(형식 변경?)")
            cache = {"fetched": today.isoformat(), "codes": codes}
            from quant.utils.jsonio import atomic_write_json
            atomic_write_json(path, cache)
        except Exception as exc:  # noqa: BLE001 — 옛 캐시로 계속, 내일 재시도
            log.warning("DART 코드표 갱신 실패(옛 캐시 사용): %s", exc)
    return cache.get("codes") or {}


def _fetch_dates_dart(symbol: str, state_dir: str) -> list[str]:
    """DART 정기공시 접수일 목록(ISO) — 키가 없으면 예외(호출측이 키로 가드)."""
    key = dart_key()
    if key is None:
        raise RuntimeError("DART_API_KEY 미설정")
    from quant.utils.http import get_json

    today = _dt.date.today()
    code = str(symbol).split(".")[0]
    cc = _corp_codes(state_dir, today).get(code)
    if cc is None:
        # 코드표에 없다 = DART에 정기공시 주체가 아니다(주로 ETF) —
        # '발표가 없다'가 사실이므로 빈 목록이 맞다.
        return []
    out: set[str] = set()
    page = 1
    while page <= DART_MAX_PAGES:
        js = get_json(
            f"{DART_HOST}/api/list.json?crtfc_key={key}&corp_code={cc}"
            f"&bgn_de={DART_FROM}&end_de={today:%Y%m%d}&pblntf_ty=A"
            f"&page_no={page}&page_count=100", timeout=30)
        status = str(js.get("status"))
        if status == "013":            # 조회 결과 없음 — 공시가 없는 회사
            break
        if status != "000":
            # ⚠️ 서버 메시지가 키를 되울릴 수 있다("등록되지 않은 키 ○○") —
            #    URL을 가려도 메시지로 새면 같은 유출이다(감사 170의 재림).
            msg = str(js.get("message", ""))[:120].replace(key, "***")
            raise RuntimeError(f"DART 응답 오류 status={status} {msg}")
        for row in js.get("list") or []:
            rd = str(row.get("rcept_dt") or "")
            if len(rd) == 8 and rd.isdigit():
                out.add(f"{rd[:4]}-{rd[4:6]}-{rd[6:]}")
        if page >= int(js.get("total_page") or 1):
            break
        page += 1
    return sorted(out)


def dart_fetcher(state_dir: str = "state"):
    """_known_dates의 fetch 자리에 꽂는 한국용 조회 함수를 만든다."""
    def _fetch(symbol: str) -> list[str]:
        return _fetch_dates_dart(symbol, state_dir)
    return _fetch
