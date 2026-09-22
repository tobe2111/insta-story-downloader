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

from quant.utils.logging import get_logger

log = get_logger("data.thirteenf")

CACHE_FILE = "thirteenf.json"
# 13F는 분기 단위 데이터다 — 하루에도 몇 번 도는 실험이 매 회차 EDGAR를
# 두드릴 이유가 없다. 20일이면 분기 안에서 새 제출을 놓치지 않으면서도
# 조회를 아낀다(제출 자체가 분기당 한 번뿐이다).
REFRESH_DAYS = 20

# EDGAR 공정접근 정책은 요청자를 밝히는 User-Agent를 요구한다. **개인 이메일을
# 박지 않는다** — 운영자가 환경변수로 자기 연락처를 넣게 하고, 없으면 중립
# 문자열을 쓴다. 값이 무엇이든 접근 실패는 아래에서 빈 결과로 떨어진다.
_DEFAULT_UA = "quant-research (set EDGAR_UA env for contact)"

# 겹쳐 담기를 셀 저명 투자자들. CIK는 EDGAR의 제출자 식별자다. 이 목록은
# 편집 가능하며, **닿지 않는 CIK는 그냥 0을 보탠다**(빈 결과) — 목록이 틀려도
# 엉뚱한 종목에 가점이 가는 일은 구조상 없다(아래 매칭 참조).
FILERS = {
    "0001067983": "Berkshire Hathaway (Buffett)",
    "0001649339": "Scion Asset Mgmt (Burry)",
    "0001336528": "Pershing Square (Ackman)",
}

# 우리 미국 유니버스의 개별 종목 ↔ 13F가 쓰는 식별자(발행사명·CUSIP).
#   · 지수 ETF(SPY·QQQ·TLT·IEF)는 일부러 뺐다 — 저명 '종목 선택자'의 확신은
#     개별 기업 이야기지, 지수를 들고 있는 것은 선택 신호가 아니다.
#   · 발행사명은 사람이 눈으로 검증하기 쉽다(CUSIP보다). 매칭은 이름 OR CUSIP
#     이고, **어느 쪽도 안 맞으면 가점 없음**(안전). CUSIP이 조금 틀려도
#     이름으로 잡히거나, 최악이라도 '가점 없음'이지 엉뚱한 종목에 붙지 않는다.
SYMBOL_ISSUERS = {
    "AAPL":  {"names": ["APPLE"],                      "cusips": ["037833100"]},
    "NVDA":  {"names": ["NVIDIA"],                     "cusips": ["67066G104"]},
    "MSFT":  {"names": ["MICROSOFT"],                  "cusips": ["594918104"]},
    "GOOGL": {"names": ["ALPHABET"],                   "cusips": ["02079K305",
                                                                  "02079K107"]},
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
        row: dict = {"issuer": "", "cusip": "", "value": None, "shares": None}
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
            elif name == "sshPrnamt" and text:
                try:
                    row["shares"] = float(text)
                except ValueError:
                    pass
        if row["issuer"] or row["cusip"]:
            out.append(row)
    return out


def _match_symbol(holding: dict) -> str | None:
    """이 13F 보유 항목이 우리 유니버스의 어느 종목인가. 안 맞으면 None."""
    iss = _norm_name(holding.get("issuer"))
    cus = _norm_cusip(holding.get("cusip"))
    for sym, spec in SYMBOL_ISSUERS.items():
        if cus and cus in {_norm_cusip(c) for c in spec.get("cusips", [])}:
            return sym
        for want in spec.get("names", []):
            w = _norm_name(want)
            # 발행사명은 접두 일치로 본다: "APPLE INC" 는 "APPLE" 로 시작한다.
            if w and (iss == w or iss.startswith(w + " ") or iss == w):
                return sym
    return None


def _urllib_fetch(url: str, timeout: float = 12.0) -> str:
    """기본 조회기 — 표준 라이브러리만 쓴다(새 의존성 없음)."""
    import urllib.request

    ua = os.environ.get("EDGAR_UA") or _DEFAULT_UA
    req = urllib.request.Request(url, headers={"User-Agent": ua,
                                               "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


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
    recent = (((subs or {}).get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    accns = recent.get("accessionNumber") or []
    reports = recent.get("reportDate") or []
    idx = None
    for i, form in enumerate(forms):
        if str(form).startswith("13F-HR"):     # 13F-HR / 13F-HR/A 둘 다
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
