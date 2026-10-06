"""저명 투자자 13F 공시 — '겹쳐 담기'를 확신 오버레이의 재료로만 쓴다.

사장님 지시(2026-09-22): *"13F 같은 유명 투자자들 공시를 최대한 정보
활용하는 것도 필요할텐데."*

맞는 방향이다. 다만 13F는 **신호로 쓰면 자기기만에 빠지기 쉬운** 데이터라,
이 파일은 그것을 신호가 아니라 '참고'로만 다룬다. 세 가지 한계를 코드가
먼저 알고 있어야 한다:

  ① **최대 4.5개월 묵었다.** 13F는 분기말 후 45일 안에만 내면 된다. 그래서
     우리가 보는 순간 그 매수는 지난 분기 일이고, 그새 다 팔았을 수도 있다.
     "지금 사라"가 아니라 "지난 분기에 들고 있었다"이다.
  ② **롱·미국주식만 보인다.** 공매도·옵션·현금·해외자산은 안 나온다. 유명한
     '풋 베팅'이 13F엔 명목가 매수처럼 찍혀 정반대로 오해를 부른 적도 있다.
  ③ **분기 1회 후행 스냅샷** — 타이밍 신호가 원리상 아니다.

그래서 이 파일이 뽑는 것은 오직 하나다: **여러 저명 투자자가 같은 종목을
동시에 들고 있는가(cluster)**. 금액·비중은 표시용으로만 남기고, 판단에는
'몇 명이 겹쳤나'라는 개수만 쓴다 — 13F의 금액 단위가 제출 시기에 따라
'달러'와 '천 달러'로 갈리는 오래된 함정(개수는 그 함정을 안 탄다)을 피하고,
겹쳐 담기라는 약하게나마 문서화된 신호의 본질에 집중하기 위해서다.

정직한 한계(코드로 강제):
  · 개수만 쓴다 — 금액 순위로 베팅하지 않는다.
  · 오버레이는 **이미 모델이 사겠다고 한 신호만** 키운다(quant/live/
    thirteenf_overlay). 관망(0)을 매수로 바꾸지 않는다 — 단독 트리거가 아니다.
  · **실데이터를 못 받으면 그냥 빈 결과**다. 겹쳐 담기가 없으면 오버레이도
    없다(배수 1.0). 못 받은 것을 '아무도 안 샀다'로 지어내지 않는다.
  · EDGAR 접근 실패·형식 변경·시간 초과는 전부 조용히 빈 결과로 떨어진다.
    참고 데이터 하나가 죽어서 실험 회차 전체가 멈추면 안 된다.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time

from quant.utils.logging import get_logger

log = get_logger("data.thirteenf")

CACHE_FILE = "thirteenf.json"
# 13F는 분기 단위 데이터다 — 하루에도 몇 번 도는 실험이 매 회차 EDGAR를
# 두드릴 이유가 없다. 20일이면 분기 안에서 새 제출을 놓치지 않으면서도
# 조회를 아낀다(제출 자체가 분기당 한 번뿐이다).
REFRESH_DAYS = 20

# EDGAR 공정접근 정책은 요청자를 밝히는 User-Agent("이름 연락처")를 요구한다.
# 연락처는 사장님이 직접 지정한 **회사 업무 주소**다(2026-10-01: "jiwon@ur-team.com
# 으로 남겨줘"). 공개 저장소라 이 주소는 공개된다 — 그 점을 알고 정한 값이다.
# 다른 주소로 바꾸려면 환경변수 EDGAR_UA가 이 값보다 우선한다.
# 값이 무엇이든 접근 실패는 아래에서 세어 장부에 적는다(감사 331).
_DEFAULT_UA = "UR-TEAM quant-research jiwon@ur-team.com"

# 겹쳐 담기를 셀 저명 투자자들. CIK는 EDGAR의 제출자 식별자다.
#
# ⚠️ **CIK는 이름으로 검증한다**(감사 333). 예전 주석은 "운영자가 확장·검증
#    한다"였지만 이 컨테이너는 EDGAR가 막혀 CIK를 눈으로 확인할 수 없다. 그래서
#    확인을 **코드에** 맡긴다: 조회한 제출 목록의 공식 이름(`name`)에
#    `FILER_VERIFY`의 낱말이 없으면 그 제출자는 **통째로 빼고** 조회 기록의
#    `unverified`에 이름을 남긴다. 틀린 CIK가 다른 회사를 가리켜도 그 회사의
#    보유가 '저명 투자자'로 섞이는 일은 구조상 없다.
#
# 사장님 지시(2026-10-06): *"13F 최대한 모든 데이터를 적용시키는 것이 중요"*
# — 6명에서 넓혔다. 기준은 **'종목을 고르는' 투자자**다(지수를 사는 큰손은
# 겹쳐 담기에 아무 정보를 더하지 않는다). 확인이 안 되는 이름은 위 장치가
# 저절로 걸러 낸다.
FILERS = {
    "0001067983": "Berkshire Hathaway (Buffett)",
    "0001649339": "Scion Asset Mgmt (Burry)",
    "0001336528": "Pershing Square (Ackman)",
    "0001350694": "Bridgewater Associates (Dalio)",
    "0001037389": "Renaissance Technologies",
    "0001061768": "Baupost Group (Klarman)",
    "0001656456": "Appaloosa (Tepper)",
    "0001536411": "Duquesne Family Office (Druckenmiller)",
    "0001040273": "Third Point (Loeb)",
    "0001079114": "Greenlight Capital (Einhorn)",
    "0001167483": "Tiger Global Management",
    "0001061165": "Lone Pine Capital",
    "0001103804": "Viking Global Investors",
    "0001135730": "Coatue Management",
    "0001029160": "Soros Fund Management",
    "0000921669": "Icahn Enterprises (Icahn)",
    "0001709323": "Himalaya Capital (Li Lu)",
    "0001112520": "Akre Capital Management",
    "0001418814": "ValueAct Capital",
    "0001569205": "Fundsmith (Terry Smith)",
}

# 제출 목록의 공식 이름(대문자)에 **반드시 들어 있어야 하는 낱말**.
FILER_VERIFY = {
    "0001067983": "BERKSHIRE HATHAWAY",
    "0001649339": "SCION ASSET",
    "0001336528": "PERSHING SQUARE",
    "0001350694": "BRIDGEWATER",
    "0001037389": "RENAISSANCE TECHNOLOGIES",
    "0001061768": "BAUPOST",
    "0001656456": "APPALOOSA",
    "0001536411": "DUQUESNE",
    "0001040273": "THIRD POINT",
    "0001079114": "GREENLIGHT",
    "0001167483": "TIGER GLOBAL",
    "0001061165": "LONE PINE",
    "0001103804": "VIKING GLOBAL",
    "0001135730": "COATUE",
    "0001029160": "SOROS",
    "0000921669": "ICAHN",
    "0001709323": "HIMALAYA",
    "0001112520": "AKRE",
    "0001418814": "VALUEACT",
    "0001569205": "FUNDSMITH",
}

# 마지막 공시가 이보다 오래되면 그 투자자의 보유는 **세지 않는다**(감사 333).
# 13F는 분기마다 45일 안에 내야 하므로 정상 제출자의 간격은 길어야 ~135일이다.
# 200일이면 한 분기를 건너뛴 것까지 봐준다. 실측(2026-10-04): Scion의 마지막
# 공시는 2025-11-03 — 거의 1년 전 보유가 '지금 들고 있다'로 세어지고 있었다.
STALE_DAYS = 200

# 보유량이 이만큼 넘게 변하면 '늘렸다/줄였다'로 센다(그 아래는 반올림 잡음).
FLOW_MIN_CHANGE = 0.05

# 우리 미국 유니버스의 개별 종목 ↔ 13F가 쓰는 식별자(발행사명·CUSIP).
#   · 지수 ETF(SPY·QQQ·TLT·IEF)는 일부러 뺐다 — 저명 '종목 선택자'의 확신은
#     개별 기업 이야기지, 지수를 들고 있는 것은 선택 신호가 아니다.
#   · 매칭은 **CUSIP을 먼저**, 안 맞으면 발행사명으로 본다. 어느 쪽도 안
#     맞으면 가점 없음(안전) — 엉뚱한 종목에 붙지 않는다.
#   · ⚠️ 알파벳은 주식이 둘이다(A주 GOOGL · C주 GOOG). 예전엔 둘 다 GOOGL로
#     셌고, 유니버스에 있는 GOOG에는 **아무 재료도** 안 갔다(감사 333). 이름이
#     같으므로 이름으로 볼 때는 주식 종류(`titleOfClass`)로 가른다.
SYMBOL_ISSUERS = {
    "AAPL":  {"names": ["APPLE"],                      "cusips": ["037833100"]},
    "NVDA":  {"names": ["NVIDIA"],                     "cusips": ["67066G104"]},
    "MSFT":  {"names": ["MICROSOFT"],                  "cusips": ["594918104"]},
    "GOOGL": {"names": ["ALPHABET"],                   "cusips": ["02079K305"],
              "share_class": "A"},
    "GOOG":  {"names": ["ALPHABET"],                   "cusips": ["02079K107"],
              "share_class": "C"},
    "AMZN":  {"names": ["AMAZON"],                     "cusips": ["023135106"]},
    "META":  {"names": ["META PLATFORMS", "FACEBOOK"], "cusips": ["30303M102"]},
    "TSLA":  {"names": ["TESLA"],                      "cusips": ["88160R101"]},
}

_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"


def _norm_name(s: str) -> str:
    """발행사명을 비교용으로 다듬는다 — 대문자·영숫자·공백만 남긴다."""
    up = re.sub(r"[^A-Z0-9 ]+", " ", str(s or "").upper())
    return re.sub(r"\s+", " ", up).strip()


def _norm_cusip(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def parse_information_table(xml_text: str) -> list[dict]:
    """13F 정보표 XML → [{issuer, cusip, value, shares}]. 실패는 빈 목록.

    네임스페이스는 제출 연도마다 달라서, 태그는 접미(로컬 이름)로만 맞춘다.
    금액 단위(달러/천 달러)는 제출 시기마다 다르지만 **우리는 개수만 쓰므로**
    여기서 통일하지 않는다 — value는 표시용으로만 그대로 싣는다.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except Exception:  # noqa: BLE001 — 깨진 XML은 빈 결과다(회차를 못 죽인다)
        return []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    out: list[dict] = []
    for node in root.iter():
        if local(node.tag) != "infoTable":
            continue
        row: dict = {"issuer": "", "cusip": "", "value": None, "shares": None,
                     "put_call": "", "title": ""}
        for child in node.iter():
            name = local(child.tag)
            text = (child.text or "").strip()
            if name == "nameOfIssuer":
                row["issuer"] = text
            elif name == "cusip":
                row["cusip"] = text
            elif name == "value" and text:
                try:
                    row["value"] = float(text)
                except ValueError:
                    pass
            elif name == "putCall":
                row["put_call"] = text.upper()
            elif name == "titleOfClass":
                row["title"] = text
            elif name == "sshPrnamt" and text:
                try:
                    row["shares"] = float(text)
                except ValueError:
                    pass
        if row["issuer"] or row["cusip"]:
            out.append(row)
    return out


def _share_class(title: str) -> str | None:
    """'CAP STK CL A' · 'CLASS C' 같은 주식 종류 표기에서 A/C를 읽는다."""
    t = " " + _norm_name(title) + " "
    for c in ("A", "C"):
        if f" CL {c} " in t or f" CLASS {c} " in t:
            return c
    return None


def is_option(holding: dict) -> bool:
    """옵션 포지션인가 — 풋·콜은 **주식 보유가 아니다**(감사 333).

    13F의 `putCall` 칸이 비어 있지 않으면 그 줄은 기초자산의 명목가로 찍힌
    옵션이다. 유명한 '풋 베팅'(하락에 거는 것)이 매수처럼 세어지면 정반대의
    신호가 된다 — 이 모듈 첫머리가 경고해 두고도 코드가 그 칸을 안 읽고 있었다.
    """
    return bool(str((holding or {}).get("put_call") or "").strip())


def _match_symbol(holding: dict) -> str | None:
    """이 13F 보유 항목이 우리 유니버스의 어느 종목인가. 안 맞으면(또는 옵션이면) None."""
    if is_option(holding):
        return None
    iss = _norm_name(holding.get("issuer"))
    cus = _norm_cusip(holding.get("cusip"))
    if cus:
        for sym, spec in SYMBOL_ISSUERS.items():
            if cus in {_norm_cusip(c) for c in spec.get("cusips", [])}:
                return sym
    klass = _share_class(holding.get("title") or "")
    for sym, spec in SYMBOL_ISSUERS.items():
        want_class = spec.get("share_class")
        if want_class and klass and klass != want_class:
            continue
        if want_class == "C" and klass is None:
            continue                 # 종류를 모르면 A주(GOOGL)로 본다
        for want in spec.get("names", []):
            w = _norm_name(want)
            # 발행사명은 접두 일치로 본다: "APPLE INC" 는 "APPLE" 로 시작한다.
            if w and (iss == w or iss.startswith(w + " ")):
                return sym
    return None


def stock_shares(holdings: list) -> dict:
    """{심볼: 주식 수 합} — 옵션 줄은 빼고, 한 종목이 여러 줄이면 더한다."""
    out: dict = {}
    for h in holdings or []:
        sym = _match_symbol(h)
        if sym is None:
            continue
        try:
            n = float(h.get("shares") or 0.0)
        except (TypeError, ValueError):
            n = 0.0
        out[sym] = out.get(sym, 0.0) + max(0.0, n)
    return out


def flows(prev: dict | None, cur: dict) -> dict:
    """직전 공시 대비 {심볼: +1(새로 사거나 늘림) | -1(줄이거나 다 팖)}.

    직전 공시가 없으면(첫 공시) 흐름을 모른다 — 빈 dict. '새로 산 것'으로
    세면 첫 공시의 모든 보유가 매수로 둔갑한다.
    """
    if prev is None:
        return {}
    # 들고 있느냐는 **목록에 있느냐**로 본다 — 주식 수 칸이 빈 공시도 있다.
    # 수량 비교는 양쪽 수량을 다 알 때만 한다.
    out: dict = {}
    for sym in set(prev) | set(cur):
        if sym not in prev:
            out[sym] = 1                             # 새로 샀다
        elif sym not in cur:
            out[sym] = -1                            # 다 팔았다
        else:
            a, b = float(prev[sym]), float(cur[sym])
            if a > 0 and b > 0 and abs(b - a) / a > FLOW_MIN_CHANGE:
                out[sym] = 1 if b > a else -1
    return out


def _days_between(a: str, b: str) -> int:
    try:
        return (_dt.date.fromisoformat(str(b)[:10])
                - _dt.date.fromisoformat(str(a)[:10])).days
    except ValueError:
        return 0


# ⚠️ **EDGAR 공정접근 — 초당 10회 이하**(2026-10-01, 감사 331 실측).
#    야간 배치 로그에 `HTTP Error 429: Too Many Requests`가 **수백 줄** 찍혀
#    있었다. 조회기가 쉼 없이 두드려(초당 수십 회) SEC가 막았고, 막힌 뒤에도
#    제출을 1999년까지 거슬러 하나씩 두드렸다. 그래서 이력이 **0점**이었고,
#    홈페이지의 13F 칸은 출시 이후 한 번도 채워진 적이 없었다 — 그리고 어디에도
#    빨간불이 없었다(실패를 전부 '빈 결과'로 흡수하도록 짰기 때문이다).
#    간격은 여유를 둔 초당 약 6.7회다.
MIN_INTERVAL_S = 0.15
# 막혔다는 응답(429)과 일시 불가(503)만 다시 시도한다. 404 같은 '없음'을
# 되풀이하면 예산만 쓴다.
RETRY_STATUSES = (429, 503)
MAX_ATTEMPTS = 3
RETRY_CAP_S = 10.0
MAX_CONSECUTIVE_FAILURES = 3
_last_call = [0.0]


def _retry_delay(retry_after, attempt: int) -> float:
    """다시 두드리기 전에 쉴 초. SEC가 Retry-After를 주면 그것을 따른다."""
    try:
        sec = float(retry_after)
    except (TypeError, ValueError):
        sec = float(2 ** (attempt + 1))        # 2초 · 4초
    return max(0.0, min(sec, RETRY_CAP_S))


def _urllib_fetch(url: str, timeout: float = 12.0, *, sleep=time.sleep,
                  clock=time.monotonic, opener=None) -> str:
    """기본 조회기 — 표준 라이브러리만 쓴다(새 의존성 없음).

    요청 사이 간격을 지키고(MIN_INTERVAL_S), 429·503이면 물러났다가 다시
    시도한다(최대 MAX_ATTEMPTS번). 그래도 막히면 예외를 그대로 올린다 —
    부르는 쪽이 그 실패를 **세어서** 장부에 적는다(아래 refresh_history).
    """
    import urllib.error
    import urllib.request

    open_url = opener or urllib.request.urlopen
    ua = os.environ.get("EDGAR_UA") or _DEFAULT_UA
    for attempt in range(MAX_ATTEMPTS):
        wait = MIN_INTERVAL_S - (clock() - _last_call[0])
        if wait > 0:
            sleep(wait)
        _last_call[0] = clock()
        req = urllib.request.Request(url, headers={"User-Agent": ua,
                                                   "Accept-Encoding": "identity"})
        try:
            with open_url(req, timeout=timeout) as resp:  # noqa: S310
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS - 1:
                raise
            hdrs = getattr(exc, "headers", None)
            sleep(_retry_delay(hdrs.get("Retry-After") if hdrs else None,
                               attempt))
    raise RuntimeError("unreachable")  # pragma: no cover


def latest_holdings(cik: str, fetch=_urllib_fetch) -> tuple[str | None, list]:
    """한 제출자의 가장 최근 13F 보유 목록 (보고 기준일, [보유...]).

    실패(네트워크·형식·미제출)는 (None, [])다. 부르는 쪽이 이걸 '없음'으로
    안전하게 흡수한다.
    """
    cik10 = str(cik).zfill(10)
    try:
        subs = json.loads(fetch(_SUBMISSIONS.format(cik=cik10)))
    except Exception as exc:  # noqa: BLE001
        log.info("13F 제출 목록 조회 실패 cik=%s: %s", cik, exc)
        return None, []
    if not verify_filer(cik, subs):
        log.warning("13F 제출자 cik=%s — 공식 이름 확인 실패, 뺀다", cik)
        return None, []
    recent = (((subs or {}).get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    accns = recent.get("accessionNumber") or []
    reports = recent.get("reportDate") or []
    idx = None
    for i, form in enumerate(forms):
        if str(form).strip() == "13F-HR":      # 원 공시만(정정은 부분 공시일 수 있다)
            idx = i
            break
    if idx is None:
        return None, []
    acc = str(accns[idx]).replace("-", "")
    report = reports[idx] if idx < len(reports) else None
    folder = _ARCHIVE.format(cik=str(int(cik10)), acc=acc)
    try:
        listing = json.loads(fetch(folder + "/index.json"))
    except Exception as exc:  # noqa: BLE001
        log.info("13F 폴더 조회 실패 cik=%s: %s", cik, exc)
        return report, []
    items = ((listing or {}).get("directory") or {}).get("item") or []
    for it in items:
        fname = str(it.get("name") or "")
        # 표지(primary_doc.xml)가 아니라 정보표 XML을 고른다.
        if fname.lower().endswith(".xml") and "primary_doc" not in fname.lower():
            try:
                rows = parse_information_table(fetch(folder + "/" + fname))
            except Exception as exc:  # noqa: BLE001
                log.info("13F 정보표 조회 실패 cik=%s: %s", cik, exc)
                continue
            if rows:
                return report, rows
    return report, []


def _holdings_for_accession(cik10: str, acc: str, fetch) -> list:
    """한 제출(accession)의 정보표 보유 목록. 실패는 빈 목록."""
    folder = _ARCHIVE.format(cik=str(int(cik10)), acc=str(acc).replace("-", ""))
    try:
        listing = json.loads(fetch(folder + "/index.json"))
    except Exception as exc:  # noqa: BLE001
        log.info("13F 폴더 조회 실패 acc=%s: %s", acc, exc)
        return []
    items = ((listing or {}).get("directory") or {}).get("item") or []
    for it in items:
        fname = str(it.get("name") or "")
        if fname.lower().endswith(".xml") and "primary_doc" not in fname.lower():
            try:
                rows = parse_information_table(fetch(folder + "/" + fname))
            except Exception as exc:  # noqa: BLE001
                log.info("13F 정보표 조회 실패 acc=%s: %s", acc, exc)
                continue
            if rows:
                return rows
    return []


def verify_filer(cik: str, subs: dict) -> bool:
    """조회한 제출 목록이 **그 투자자의 것인가** — 공식 이름에 확인 낱말이 있나.

    확인 낱말이 등록되지 않은 CIK(검사·주입)는 통과시킨다 — 이 장치는 우리가
    적은 목록의 오기를 잡는 것이지, 낯선 입력을 막는 것이 아니다.
    """
    want = FILER_VERIFY.get(str(cik).zfill(10))
    if not want:
        return True
    got = _norm_name((subs or {}).get("name") or "")
    return _norm_name(want) in got


def filings_history(cik: str, fetch=_urllib_fetch, max_filings: int = 12,
                    report: dict | None = None) -> list:
    """한 제출자의 **지난 13F-HR 제출들** — 최신부터 max_filings개.

    각 항목: {"filed": 제출일(공개된 날), "report": 보고 기준일, "holdings": [...]}.
    ⚠️ point-in-time의 핵심은 **filed(제출일)**다 — 그 날에야 세상이 이 보유를
       알 수 있었다. 백테스트가 report(기준일)로 앞당겨 보면 미래를 훔쳐본다.
    """
    cik10 = str(cik).zfill(10)
    try:
        subs = json.loads(fetch(_SUBMISSIONS.format(cik=cik10)))
    except Exception as exc:  # noqa: BLE001
        log.info("13F 제출 이력 조회 실패 cik=%s: %s", cik, exc)
        return []
    if not verify_filer(cik, subs):
        got = str((subs or {}).get("name") or "?")[:80]
        log.warning("13F 제출자 cik=%s — 공식 이름 '%s'에 확인 낱말 '%s'가 없다. "
                    "CIK가 틀렸다고 보고 뺀다.", cik, got,
                    FILER_VERIFY.get(str(cik).zfill(10)))
        if report is not None:
            report.setdefault("unverified", []).append(
                {"cik": cik10, "expected": FILERS.get(cik10, cik10), "got": got})
        return []
    recent = (((subs or {}).get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    accns = recent.get("accessionNumber") or []
    reports = recent.get("reportDate") or []
    fileds = recent.get("filingDate") or []
    out: list = []
    tried = 0
    fails = 0
    for i, form in enumerate(forms):
        # 정정 공시(13F-HR/A)는 뺀다(감사 333) — 상당수가 '추가 보유분'만 담은
        # 부분 공시라, 그것을 그 분기의 보유 전체로 읽으면 나머지 보유가 모두
        # '다 팔았다'로 둔갑한다. 원 공시만 쓴다.
        if str(form).strip() != "13F-HR":
            continue
        # ⚠️ **두드리는 횟수에 상한을 건다**(감사 331). 예전에는 성공한 제출만
        #    세어서, 막힌 날에는 성공이 영영 0이라 제출 목록을 1999년까지 전부
        #    두드렸다(제출자 하나에 수십 번) — 그 자체가 차단을 더 길게 만든다.
        if tried >= max_filings + 2:
            break
        tried += 1
        rows = _holdings_for_accession(cik10, accns[i], fetch)
        if not rows:
            fails += 1
            # 연달아 실패하면 이 제출자는 오늘 접는다. 막힌 서버를 계속
            # 두드리는 것은 다음 제출자까지 막히게 할 뿐이다.
            if fails >= MAX_CONSECUTIVE_FAILURES:
                log.warning("13F 제출자 cik=%s — 연속 %d회 실패, 오늘은 접는다",
                            cik, fails)
                break
            continue
        fails = 0
        out.append({"filed": (fileds[i] if i < len(fileds) else None),
                    "report": (reports[i] if i < len(reports) else None),
                    "holdings": rows})
        if len(out) >= max_filings:
            break
    return out


def build_cluster_history(filings_by_cik: dict, until: str | None = None) -> list:
    """{cik: [filings_history 항목...]} → point-in-time 겹쳐 담기 시계열.

    반환: [{"as_of": 날짜, "cluster": {심볼: {count, filers}},
            "flow": {심볼: {buy, sell}}}] — 날짜 오름차순.

    각 시점은 **그 날까지 공개된 각 제출자의 가장 최근 보유**로 만든다. 감사
    333에서 세 가지를 더했다:
      · 옵션 줄은 보유가 아니다(`stock_shares`가 뺀다).
      · 마지막 공시가 `STALE_DAYS`보다 오래된 제출자는 **세지 않는다** — 그
        만료일에도 줄을 만든다(안 만들면 다음 공시 때까지 옛 보유가 남는다).
      · flow = 각 제출자의 최신 공시가 **직전 공시보다** 늘렸나(buy)·줄였나(sell).
    until: 이 날짜 뒤의 만료 줄은 만들지 않는다(아직 오지 않은 날).
    """
    from datetime import timedelta

    if until is None:                  # 아직 오지 않은 날의 만료는 만들지 않는다
        until = _dt.date.today().isoformat()
    events: list[tuple] = []           # (날짜, 순서, cik, 보유 dict | None)
    for cik, filings in (filings_by_cik or {}).items():
        c10 = str(cik).zfill(10)
        dated = sorted((f for f in (filings or []) if f.get("filed")),
                       key=lambda f: str(f["filed"]))
        for i, f in enumerate(dated):
            filed = str(f["filed"])[:10]
            events.append((filed, 0, c10, stock_shares(f.get("holdings"))))
            nxt = str(dated[i + 1]["filed"])[:10] if i + 1 < len(dated) else None
            expire = (_dt.date.fromisoformat(filed)
                      + timedelta(days=STALE_DAYS)).isoformat()
            if (nxt is None or nxt > expire) and (until is None or expire <= until):
                events.append((expire, 1, c10, None))      # 만료 표시
    events.sort(key=lambda e: (e[0], e[1]))
    latest: dict[str, dict] = {}        # cik → 최신 보유(주식 수)
    flow_by: dict[str, dict] = {}       # cik → 최신 공시의 흐름
    alive: dict[str, bool] = {}
    history: list = []
    for day, kind, cik, shares in events:
        if kind == 1:
            alive[cik] = False
        else:
            flow_by[cik] = flows(latest.get(cik), shares)
            latest[cik] = shares
            alive[cik] = True
        counts: dict[str, dict] = {}
        flow: dict[str, dict] = {}
        for c, held in latest.items():
            if not alive.get(c):
                continue
            name = FILERS.get(c, FILERS.get(str(int(c)), c))
            for sym in held:
                slot = counts.setdefault(sym, {"count": 0, "filers": []})
                slot["count"] += 1
                slot["filers"].append(name)
            for sym, d in (flow_by.get(c) or {}).items():
                slot = flow.setdefault(sym, {"buy": 0, "sell": 0})
                slot["buy" if d > 0 else "sell"] += 1
        row = {"as_of": day, "cluster": counts, "flow": flow}
        # 같은 날 여러 사건이면 마지막 것만 남긴다(같은 as_of 하나).
        if history and history[-1]["as_of"] == day:
            history[-1] = row
        else:
            history.append(row)
    return history


def cluster_asof_row(history: list, date: str) -> dict:
    """그 날짜에 공개돼 있던 가장 최근 줄 전체(cluster·flow). 없으면 {}."""
    d = str(date)[:10]
    got: dict = {}
    for row in (history or []):
        if str(row.get("as_of"))[:10] <= d:
            got = row
        else:
            break
    return got


def cluster_asof(history: list, date: str) -> dict:
    """그 날짜에 **공개돼 있던** 가장 최근 겹쳐 담기(point-in-time). 없으면 {}."""
    d = str(date)[:10]
    got: dict = {}
    for row in (history or []):
        if str(row.get("as_of"))[:10] <= d:
            got = row.get("cluster") or {}
        else:
            break                          # history는 오름차순이다
    return got


HISTORY_FILE = "thirteenf_history.json"


def _filer_summary(cik: str, filings: list, today: str | None = None) -> dict:
    """제출자 한 명의 공개 요약 — 화면이 "누가 언제 무엇을"을 말하게.

    가장 최근 제출(제출일 기준)의 보유 중 **우리 유니버스 종목**만 싣고,
    직전 제출 대비 늘린 종목·줄인 종목, 뺀 옵션 줄 수, 공시가 멈췄는지를 함께.
    """
    name = FILERS.get(str(cik).zfill(10), str(cik))
    if not filings:
        return {"cik": str(cik).zfill(10), "name": name, "filings": 0,
                "filed": None, "report": None, "holds": [], "bought": [],
                "sold": [], "options_excluded": 0, "stale": False}
    dated = sorted(filings, key=lambda f: str(f.get("filed") or ""))
    latest = dated[-1]
    cur = stock_shares(latest.get("holdings"))
    prev = stock_shares(dated[-2].get("holdings")) if len(dated) > 1 else None
    fl = flows(prev, cur)
    opts = sum(1 for h in (latest.get("holdings") or []) if is_option(h))
    stale = bool(today and latest.get("filed")
                 and _days_between(latest["filed"], today) > STALE_DAYS)
    return {"cik": str(cik).zfill(10), "name": name, "filings": len(filings),
            "filed": latest.get("filed"), "report": latest.get("report"),
            "holds": sorted(cur),
            "bought": sorted(k for k, d in fl.items() if d > 0),
            "sold": sorted(k for k, d in fl.items() if d < 0),
            "options_excluded": opts, "stale": stale}


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def refresh_history(state_dir: str = "state", *, fetch=_urllib_fetch,
                    filers: dict | None = None, max_filings: int = 12,
                    today: str | None = None) -> list:
    """point-in-time 이력을 EDGAR에서 받아 state/thirteenf_history.json에 캐시.

    같은 조회로 **오늘의 겹쳐 담기 스냅샷**(state/thirteenf.json)도 쓴다 —
    장중 회차가 EDGAR를 다시 두드리지 않게(감사 331: 장중 러너는 그 캐시를
    커밋하지 않아, 15분마다 처음부터 두드리며 차단을 연장하고 있었다).

    ⚠️ **못 받은 날은 어제 것을 지우지 않는다.** 조회 오류가 있었고 새로 본
       제출자가 저장된 것보다 적으면, 저장된 이력을 그대로 두고 조회 결과만
       `fetch`에 적는다. 막힌 하룻밤이 쌓아 둔 이력을 빈 목록으로 덮으면,
       "못 쟀다"가 "아무도 안 샀다"로 둔갑한다.
    """
    use = filers if filers is not None else FILERS
    report = {"requests": 0, "errors": 0, "last_error": None, "unverified": []}

    def counted(url):
        report["requests"] += 1
        try:
            return fetch(url)
        except Exception as exc:  # noqa: BLE001 — 세고 그대로 올린다
            report["errors"] += 1
            report["last_error"] = str(exc)[:160]
            raise

    by_cik: dict = {}
    for cik in use:
        hist = filings_history(cik, fetch=counted, max_filings=max_filings,
                               report=report)
        if hist:
            by_cik[cik] = hist
    day = str(today or _dt.date.today().isoformat())[:10]
    hist_path = os.path.join(state_dir, HISTORY_FILE)
    prev = _read_json(hist_path)
    prev_seen = int(((prev.get("fetch") or {}).get("filers_seen")) or 0)
    if not prev_seen and prev.get("history"):
        prev_seen = len(use)               # 옛 모양(조회 기록 없음)은 온전하다고 본다
    clean = report["errors"] == 0
    keep_old = (not clean) and len(by_cik) < prev_seen
    history = ((prev.get("history") or []) if keep_old
               else build_cluster_history(by_cik, until=day))
    fetch_info = {
        "on": day,
        "ok": clean,
        "kept_previous": keep_old,
        "filers_total": len(use),
        "filers_seen": (prev_seen if keep_old else len(by_cik)),
        "seen_today": len(by_cik),
        **report,
    }
    filers_out = (prev.get("filers") or []) if keep_old else [
        _filer_summary(c, by_cik.get(c) or [], today=day) for c in use]
    try:
        os.makedirs(state_dir, exist_ok=True)
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(hist_path, {"history": history,
                                      "filers_total": len(use),
                                      "filers": filers_out,
                                      "fetch": fetch_info})
        if not keep_old and by_cik:
            latest = {}
            for cik, fl in by_cik.items():
                seen = sorted((f for f in fl if str(f.get("filed") or "") <= day),
                              key=lambda f: str(f.get("filed") or ""))
                # 공시가 멈춘 투자자는 오늘의 겹쳐 담기에서 뺀다(STALE_DAYS).
                if seen and _days_between(seen[-1]["filed"], day) <= STALE_DAYS:
                    latest[cik] = (seen[-1].get("report"),
                                   seen[-1].get("holdings") or [])
            cluster = cluster_from_filings(latest)
            today_flow = (cluster_asof_row(history, day) or {}).get("flow") or {}
            for sym, slot in cluster.items():
                fl = today_flow.get(sym) or {}
                slot["buy"] = int(fl.get("buy") or 0)
                slot["sell"] = int(fl.get("sell") or 0)
            atomic_write_json(_cache_path(state_dir), {
                "cluster": cluster,
                "flow": today_flow,
                "fetched_on": day,
                "filers_total": len(use),
                "filers_seen": len(latest),
            })
    except Exception as exc:  # noqa: BLE001
        log.info("13F 이력 캐시 저장 실패(무해): %s", exc)
    if report["errors"]:
        log.warning("13F 조회 %d건 중 %d건 실패 (마지막: %s)%s",
                    report["requests"], report["errors"], report["last_error"],
                    " — 저장된 이력을 유지" if keep_old else "")
    return history


def load_fetch_report(state_dir: str = "state") -> dict:
    """마지막 EDGAR 조회의 결과(요청·실패 수, 본 제출자 수)와 제출자 요약."""
    d = _read_json(os.path.join(state_dir, HISTORY_FILE))
    return {"fetch": d.get("fetch") or {}, "filers": d.get("filers") or [],
            "points": len(d.get("history") or [])}


def load_history(state_dir: str = "state") -> list:
    """캐시된 point-in-time 이력. 없으면 빈 목록."""
    try:
        with open(os.path.join(state_dir, HISTORY_FILE),
                  encoding="utf-8") as f:
            return (json.load(f) or {}).get("history") or []
    except (OSError, ValueError):
        return []


def cluster_from_filings(filings: dict) -> dict:
    """{cik: (기준일, [보유...])} → {심볼: {count, filers, as_of, ...}}.

    count는 **그 종목을 든 저명 투자자 수**다. 금액이 아니라 개수 — 겹쳐
    담기의 본질이고, 금액 단위 함정을 안 탄다.
    """
    hits: dict[str, dict] = {}
    for cik, pair in (filings or {}).items():
        as_of, rows = pair if isinstance(pair, tuple) else (None, pair)
        seen: set[str] = set()
        for h in (rows or []):
            sym = _match_symbol(h)
            if sym is None or sym in seen:
                continue                    # 한 제출자가 한 종목을 여러 줄에 적어도 1표
            seen.add(sym)
            slot = hits.setdefault(sym, {"count": 0, "filers": [], "as_of": []})
            slot["count"] += 1
            slot["filers"].append(FILERS.get(str(cik).zfill(10),
                                             FILERS.get(str(cik), str(cik))))
            if as_of:
                slot["as_of"].append(str(as_of))
    for sym, slot in hits.items():
        # 가장 오래된 기준일을 대표로 — "이 참고가 얼마나 묵었나"는 최악을 본다.
        slot["as_of"] = min(slot["as_of"]) if slot["as_of"] else None
    return hits


def _cache_path(state_dir: str) -> str:
    return os.path.join(state_dir, CACHE_FILE)


def _is_fresh(cached: dict, now: _dt.date) -> bool:
    stamp = (cached or {}).get("fetched_on")
    if not stamp:
        return False
    try:
        got = _dt.date.fromisoformat(str(stamp)[:10])
    except ValueError:
        return False
    return (now - got).days < REFRESH_DAYS


def refresh(state_dir: str = "state", *, now=None, fetch=_urllib_fetch,
            filers: dict | None = None) -> dict:
    """겹쳐 담기 스냅샷을 돌려준다. 캐시가 신선하면 조회하지 않는다.

    반환: {"cluster": {심볼: {...}}, "fetched_on": "YYYY-MM-DD", "filers_total": n}
    실패·전무는 빈 cluster다(오버레이가 전부 1.0이 된다).
    """
    today = _resolve_today(now)
    path = _cache_path(state_dir)
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        cached = {}
    if _is_fresh(cached, today) and isinstance(cached.get("cluster"), dict):
        return cached

    use = filers if filers is not None else FILERS
    filings: dict = {}
    for cik in use:
        as_of, rows = latest_holdings(cik, fetch=fetch)
        if rows:
            filings[cik] = (as_of, rows)
    snapshot = {
        "cluster": cluster_from_filings(filings),
        "fetched_on": today.isoformat(),
        "filers_total": len(use),
        "filers_seen": len(filings),
    }
    try:
        os.makedirs(state_dir, exist_ok=True)
        from quant.utils.jsonio import atomic_write_json
        atomic_write_json(path, snapshot)
    except Exception as exc:  # noqa: BLE001 — 캐시 실패가 판단을 막지 않는다
        log.info("13F 캐시 저장 실패(무해): %s", exc)
    return snapshot


def _resolve_today(now) -> _dt.date:
    if now is None:
        return _dt.date.today()
    if isinstance(now, _dt.date) and not isinstance(now, _dt.datetime):
        return now
    try:
        s = str(now).replace("Z", "+00:00")
        return _dt.datetime.fromisoformat(s).date()
    except ValueError:
        return _dt.date.today()
