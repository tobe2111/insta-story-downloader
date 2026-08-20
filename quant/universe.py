"""규칙 유니버스 — 종목 선정을 사람 손에서 규칙으로.

2026-08-18 외부 검토의 최대 지적("지금 살아남은 대형주를 사람이 고른 것 —
생존 편향")에 대한 반영이자, 실효 독립 베팅 수(14종목≈9.5개)가 보여준
분산 부족의 처방이다. 사장님 지시("앞으로는 리셋하지 말고 모두 개선")에
따라 본 계좌에 직접 적용되며, 변경은 판정 시계의 버전 이력으로 공개된다.

규칙 (사전 등록):
  · 리밸런스는 **매월 1회** — 그 달의 첫 재계산 시점(기준일을 스냅샷에 기록).
  · crypto: 시장 대표 BTC·ETH 고정 + 24시간 거래대금(USDT) 상위 3
    (거래소 공개 티커 — 무료·공개라 재현 가능).
  · kr_stock: 시장 지수 ETF(KODEX 200) 고정 + 기준일 시가총액 상위 6
    (KRX 공개 통계, pykrx — 우선주 제외).
  · us_stock: 지수 ETF(SPY·QQQ) 고정 + 기준일 시가총액 상위 6
    (나스닥 공개 스크리너, NASDAQ·NYSE 합산 — 무료·공개. 2026-08-18 부착;
    그 전에는 순위 소스가 없어 "현행 유지"를 규칙으로 명시했었다).
    점(.)·캐럿(^)이 든 심볼(복수 클래스·워런트 표기)은 제외한다 —
    같은 회사를 두 번 세지 않기 위해서이고, 시세 소스 심볼 규약과도 맞다.
  · 산출에 쓴 순위표를 스냅샷(state/universe.json)에 저장 — 언제 다시
    봐도 같은 근거를 볼 수 있다.

실패 원칙: 어떤 시장의 순위 조회가 실패하면 그 시장은 **직전 구성 유지**
+ 실패 사유 기록. 데이터가 없다고 종목을 즉흥적으로 고르지 않는다.

기록 원칙: 유니버스에서 빠진 종목의 장부는 지우지 않는다 — 기록은 남고
매매만 멈춘다(선택 편향 없는 공개 실험의 연장).
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from quant.utils.logging import get_logger

log = get_logger("universe")

FILE = "universe.json"
RULE_VERSION = "2026-08-19"       # 자산군 코어 확대(아래 사유)

# ⚠️ 왜 코어를 늘렸나 (2026-08-19, 사장님 지시 "자산군 최대한 많이").
#
#    이전 20종목은 수가 아니라 **성격**이 문제였다: 코인·미국주식·한국주식이
#    전부 위험자산 한 덩어리라, 시장이 빠지는 날 스무 개가 같이 빠졌다.
#    통계로 보면 20개의 독립 관측이 아니라 사실상 두세 개에 가깝다 — 비슷한
#    종목을 더 넣어 봐야 정보는 안 늘고 다중검정 문턱만 올라간다.
#
#    그래서 늘린 것은 **종목 수가 아니라 자산군**이다: 금·은·국채·회사채·
#    원자재·에너지·달러·리츠·방어섹터·해외시장. 이것들은 주식이 빠질 때
#    다르게 움직여서 **진짜 새 정보**를 준다. 정보가 실제로 늘었는지는
#    주장하지 않고 상관 기반 실효 표본 수로 잰다(quant/live/breadth.py).
#
# ⚠️ 왜 새로 넣는 것이 대부분 ETF인가 — 돈 문제다. 100만원 계좌를 N종목으로
#    나누면 종목당 100만/N원인데, 한국 개별주는 한 주가 17만~27만원이라
#    20종목 시점에 이미 세 종목이 "1주도 못 산다"로 기록됐다(2026-08-19
#    장부 lot_infeasible). 종목을 늘리면 그 문제가 커지므로, 새로 넣는
#    것은 한 주 값이 싸고 쪼갤 수 있는 ETF·코인 위주로 고른다.
#
# ⚠️ 판정 시계는 이것 때문에 리셋되지 않는다. 세대는 ①피처셋 ②실행구조
#    ③실측 피처 구성 세 축으로만 갈린다(daily.generation_days). 유니버스는
#    원래 매달 규칙으로 회전하던 것이고, 그때도 시계는 멈추지 않았다.
CRYPTO_CORE = ["BTC/USDT", "ETH/USDT"]
CRYPTO_TOP = 8                    # 5 → 10종목(코어 2 + 상위 8)

KR_CORE = ["069500.KS"]           # KODEX 200 — 시장 전체 대표
# 한국 자산군 코어 — 전부 ETF다(개별주는 한 주 값 때문에 못 담는다).
KR_ASSET_CORE = [
    "133690.KS",   # TIGER 미국나스닥100 — 환노출 해외주식
    "132030.KS",   # KODEX 골드선물(H) — 금
    "148070.KS",   # KOSEF 국고채10년 — 한국 장기금리
    "228790.KS",   # TIGER 화장품 → 섹터 분산(경기소비)
    "273130.KS",   # KODEX 종합채권(AA-이상) — 종합채권
]
KR_TOP = 6

US_CORE = ["SPY", "QQQ"]
# 미국 자산군 코어 — 위험자산과 다르게 움직이는 것들을 모은다.
# (변동성 ETF(VXX류)는 구조적으로 장기 손실이 나는 상품이라 넣지 않는다 —
#  '자산군을 늘린다'는 말로 알려진 손실 상품을 담으면 안 된다.)
US_ASSET_CORE = [
    "GLD",   # 금
    "SLV",   # 은
    "TLT",   # 미국 장기국채(20년+)
    "IEF",   # 미국 중기국채(7~10년)
    "LQD",   # 투자등급 회사채
    "TIP",   # 물가연동국채
    "DBC",   # 원자재 바스켓
    "XLE",   # 에너지 섹터
    "XLU",   # 유틸리티(방어)
    "XLP",   # 필수소비재(방어)
    "VNQ",   # 리츠(부동산)
    "UUP",   # 달러 인덱스
    "EWJ",   # 일본
    "VGK",   # 유럽
    "EEM",   # 신흥국
]
US_TOP = 6


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, FILE)


def load(state_dir: str = "state") -> dict | None:
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("targets") else None
    except (OSError, ValueError):
        return None


def active_targets(state_dir: str = "state") -> list[tuple[str, str]]:
    """지금 운용할 (시장, 종목) 목록 — 스냅샷이 없으면 기존 고정 목록."""
    from quant.markets import AUTO_TARGETS
    snap = load(state_dir)
    if not snap:
        return list(AUTO_TARGETS)
    return [tuple(t) for t in snap["targets"]]


def due(state_dir: str = "state", today: _dt.date | None = None) -> bool:
    """재계산할 때인가 — 달이 바뀌었거나 **규칙이 바뀌었거나**.

    ⚠️ 규칙 조건이 없어서 확장이 12일 늦을 뻔했다 (2026-08-20 감사 296).
       2026-08-19에 자산군 코어를 넣어 규칙을 20종목 → 45종목으로 바꿨는데,
       이 함수가 **달만** 보고 있어서 스냅샷(같은 달 08-19)이 그대로 남았다.
       코드는 45종목이라 말하고 계좌는 20종목으로 돌았다. 사장님이 "자산군
       늘려라"라고 하신 결과가 9월 1일에야 적용될 참이었다.

       규칙을 바꾸는 것은 사람이 의도적으로 하는 일이고, 그 의도가 다음
       달까지 기다릴 이유가 없다. 스냅샷은 자기를 만든 규칙 버전을 이미
       적고 있었다 — 그것을 보기만 하면 됐다.

    매월 1회라는 원칙은 그대로다. 규칙이 그대로면 이 함수는 예전과 똑같이
    달만 본다(잦은 회전은 그 자체가 비용이다).
    """
    today = today or _dt.date.today()
    snap = load(state_dir)
    if not snap:
        return True
    if str(snap.get("rule_version", "")) != RULE_VERSION:
        log.info("규칙 버전이 바뀌었습니다(%s → %s) — 유니버스를 다시 계산합니다",
                 snap.get("rule_version"), RULE_VERSION)
        return True
    return str(snap.get("asof", ""))[:7] != today.isoformat()[:7]


# ── 시장별 순위 (전부 무료·공개 소스) ────────────────────────────────

def _rank_crypto() -> list[str]:
    """USDT 마켓 24시간 거래대금 상위 — 거래소 공개 티커."""
    import urllib.request as _rq
    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    with _rq.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    rows = []
    for t in data.get("data", []):
        inst = str(t.get("instId", ""))
        if not inst.endswith("-USDT"):
            continue
        try:
            vol = float(t.get("volCcy24h") or 0) * float(t.get("last") or 0)
        except (TypeError, ValueError):
            continue
        rows.append((inst.replace("-", "/"), vol))
    rows.sort(key=lambda x: -x[1])
    return [s for s, _v in rows]


def _rank_kr(asof: str) -> list[str]:
    """기준일 시가총액 상위 — KRX 공개 통계(pykrx). 우선주 제외."""
    from pykrx import stock
    raw = stock.get_market_cap_by_ticker(asof.replace("-", ""), market="KOSPI")
    if raw is None or len(raw) == 0:
        raise RuntimeError(f"KRX 시총 표가 비어 있다(기준일 {asof})")
    col = next((c for c in raw.columns if "시가총액" in str(c)), None)
    if col is None:
        raise RuntimeError(f"시가총액 컬럼이 없다 — 받은 컬럼: {list(raw.columns)[:5]}")
    ranked = raw.sort_values(col, ascending=False)
    out = []
    for code in ranked.index:
        code = str(code)
        # 우선주(끝자리 0이 아닌 코드) 제외 — 보통주와 같은 회사의 사본이라
        # 유니버스에 두 번 세면 분산이 명목만 늘어난다.
        if not code.endswith("0"):
            continue
        out.append(f"{code}.KS")
    return out


def _fetch_us_screener_rows() -> list[dict]:
    """나스닥 공개 스크리너 — NASDAQ·NYSE 상장 주식 전체(시총 포함).

    무료·공개 JSON이라 재현 가능하다. 실패는 예외로 올라가고, rebuild가
    '직전 구성 유지 + 사유'로 처리한다(즉흥 선정 금지 원칙 그대로).
    """
    import urllib.request as _rq
    rows: list[dict] = []
    for ex in ("nasdaq", "nyse"):
        url = ("https://api.nasdaq.com/api/screener/stocks"
               f"?tableonly=true&download=true&exchange={ex}")
        req = _rq.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; quant-universe)",
            "Accept": "application/json"})
        with _rq.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows += ((data.get("data") or {}).get("rows") or [])
    return rows


def _rank_us(fetch_rows=_fetch_us_screener_rows) -> list[str]:
    """기준일 시가총액 상위 — 나스닥 공개 스크리너. 파싱은 결정적.

    점(.)·캐럿(^)·슬래시(/)가 든 심볼은 제외한다: 복수 클래스(BRK.A 등)·
    워런트·우선 표기라 같은 회사를 두 번 세게 되고, 시세 소스(야후) 심볼
    규약과도 어긋난다 — KR의 우선주 제외와 같은 원리다.
    """
    scored: list[tuple[str, float]] = []
    for row in fetch_rows():
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym or any(ch in sym for ch in "^./ "):
            continue
        cap_raw = str(row.get("marketCap", "")).replace(",", "").replace("$", "")
        try:
            cap = float(cap_raw)
        except ValueError:
            continue
        if cap > 0:
            scored.append((sym, cap))
    if not scored:
        raise RuntimeError("나스닥 스크리너가 시총 있는 종목을 하나도 안 줬다")
    scored.sort(key=lambda x: -x[1])
    seen: set[str] = set()
    out = []
    for sym, _cap in scored:            # 두 거래소 목록의 중복 제거(첫 순위 유지)
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def rebuild(state_dir: str = "state",
            today: _dt.date | None = None,
            rank_crypto=_rank_crypto, rank_kr=_rank_kr,
            rank_us=_rank_us) -> dict:
    """규칙대로 유니버스를 다시 계산해 스냅샷으로 저장한다.

    시장별로 독립 실패한다 — 한 시장의 조회 실패가 다른 시장의 갱신을
    막지 않고, 실패한 시장은 직전 구성을 유지하며 사유가 기록된다.
    """
    from quant.markets import AUTO_TARGETS
    from quant.utils.jsonio import atomic_write_json
    today = today or _dt.date.today()
    asof = today.isoformat()
    prev = load(state_dir)
    prev_by_market: dict[str, list[str]] = {}
    for mk, sym in (tuple(t) for t in (prev or {}).get("targets", AUTO_TARGETS)):
        prev_by_market.setdefault(mk, []).append(sym)

    rationale: dict = {}
    markets: dict[str, list[str]] = {}

    # ⚠️ **고정 코어는 순위가 아니다** (2026-08-20 감사 296).
    #    예전에는 순위 조회가 실패하면 그 시장 전체를 '직전 유지'로 떨어뜨렸다.
    #    그래서 금·국채·리츠처럼 **순위와 무관하게 규칙으로 박아 둔 종목**까지
    #    함께 버려졌다. 2026-08-19 밤 실측: 코인 403, 한국 pykrx 컬럼 변경 —
    #    두 시장이 통째로 옛 구성으로 남았고, 새로 넣은 자산군은 하나도 안
    #    들어왔다. 조회가 깨진 것은 **순위**뿐인데 대가는 확장 전체였다.
    #    이제 코어는 언제나 들어가고, 실패하면 순위로 뽑는 꼬리만 직전 것을 쓴다.
    def _market(name: str, core: list[str], top: int, rank, rule_text: str):
        try:
            ranked = list(rank())
        except Exception as exc:  # noqa: BLE001 — 순위만 실패한다
            prev = prev_by_market.get(name, [])
            extra = [s for s in prev if s not in core][:top]
            markets[name] = core + extra
            rationale[name] = {
                "core_applied": True,          # 코어는 들어갔다
                "ranking_failed": True,        # 못 받은 것은 순위뿐
                "kept_previous_tail": extra,
                "reason": f"{type(exc).__name__}: {exc}"}
            return
        extra = [s for s in ranked if s not in core][:top]
        markets[name] = core + extra
        rationale[name] = {"rule": rule_text, "top10": ranked[:10]}

    _market("crypto", CRYPTO_CORE, CRYPTO_TOP, rank_crypto,
            f"BTC·ETH 고정 + 거래대금 상위 {CRYPTO_TOP}")
    _market("kr_stock", KR_CORE + KR_ASSET_CORE, KR_TOP, lambda: rank_kr(asof),
            f"KODEX200·자산군 ETF {len(KR_ASSET_CORE)}종 고정 + 시총 상위 {KR_TOP}"
            " (우선주 제외)")
    _market("us_stock", US_CORE + US_ASSET_CORE, US_TOP, rank_us,
            f"지수 ETF(SPY·QQQ)+자산군 ETF {len(US_ASSET_CORE)}종 고정 + 시총 상위 {US_TOP}"
            " (나스닥 공개 스크리너, 복수클래스·워런트 표기 제외)")

    targets = ([("crypto", s) for s in markets["crypto"]]
               + [("us_stock", s) for s in markets["us_stock"]]
               + [("kr_stock", s) for s in markets["kr_stock"]])

    old_set = {tuple(t) for t in (prev or {}).get("targets", [])}
    changed = old_set != set(targets) if prev else False
    hist = list((prev or {}).get("history", []))
    if prev is None or changed:
        added = sorted({f"{m}:{s}" for m, s in targets} -
                       {f"{m}:{s}" for m, s in old_set})
        removed = sorted({f"{m}:{s}" for m, s in old_set} -
                         {f"{m}:{s}" for m, s in targets})
        hist.append({"on": asof, "added": added, "removed": removed,
                     "rule_version": RULE_VERSION})
    snap = {"asof": asof, "rule_version": RULE_VERSION,
            "targets": [list(t) for t in targets],
            "rationale": rationale, "history": hist[-60:]}
    os.makedirs(state_dir, exist_ok=True)
    atomic_write_json(_path(state_dir), snap)
    log.info("유니버스 재계산 — %d종목 (변경 %s)", len(targets),
             "있음" if changed or prev is None else "없음")
    return snap


def version_entries(state_dir: str = "state",
                    after: str = "") -> list[dict]:
    """유니버스 변경 이력 → 판정 시계 버전 이력 재료(리셋 없음, 공개만)."""
    snap = load(state_dir)
    if not snap:
        return []
    out = []
    for h in snap.get("history", []):
        on = str(h.get("on", ""))
        if not on or on <= after:
            continue
        n_add, n_rm = len(h.get("added", [])), len(h.get("removed", []))
        out.append({"on": on, "axis": "유니버스",
                    "what": f"편입 {n_add} · 제외 {n_rm} (규칙 {h.get('rule_version')})"})
    return out
