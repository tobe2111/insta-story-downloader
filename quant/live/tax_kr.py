"""원화 계좌의 **환전 비용**과 **세금** — 장부가 세전·환전 전 숫자만 말하던 구멍 (감사 339).

사장님(2026-10-10): "투자 성공을 위해서 개선할 것" → "응 다 진행해줘"

■ 환전 비용
  본 계좌는 원화인데 미국 자산을 사고팔 때 원↔달러 환전 비용을 한 번도 안
  물렸다(미국 주식 비용은 수수료 1bp + 슬리피지 5bp뿐). 실제 증권사는 환전에
  스프레드를 받는다 — 기본 약 1%에서 우대율만큼 깎아 준다.

  ⚠️ **매매 금액 전체에 물리지 않는다.** 미국 종목끼리 갈아타면 달러는 계좌
     안에 머문다. 원화로 바뀌는 것은 그날 미국 자산의 **순매수·순매도**뿐이다
     (`fx_charge`). 매매마다 물리면 회전이 많은 날 비용을 몇 배로 부풀린다.

  기본값 편도 0.25%(우대 75% 가정)는 **보수적인 쪽**이다 — 사장님이 쓸 증권사
  우대율을 모르는 동안의 값이고, `state/engine.json`의 `fx_spread`로 실제
  값을 넣으면 그것이 우선한다.

■ 세금(추정 — 장부의 자산에서 빼지는 않는다)
  세금은 다음 해 5월에 낸다. 그래서 자산에서 바로 빼면 그날의 사실이 아니게
  되고, 안 보이면 세전 숫자가 세후처럼 읽힌다. 그래서 **따로 적는다** —
  올해 실현 손익과 그에 붙을 세금 추정(`estimate`).

  | 구분 | 규칙(2026년 개인 · 대주주 아님 가정) |
  |---|---|
  | 해외 주식·해외 ETF | 연간 실현 손익 합산, **250만원 공제 후 22%** |
  | 국내 상장 비(非)국내주식형 ETF(나스닥·금·채권 등) | 매매차익 **15.4%**(배당소득) — 공제 없음, 손실 상계 없음 |
  | 국내 주식·국내주식형 ETF | 매매차익 비과세(대주주 아님) |
  | 가상자산 | 2026년 비과세 — 과세는 2027-01-01부터(250만원 공제 후 22%) |

  ⚠️ 근사다: 배당 원천징수, 해외 ETF 분배금, 국내 ETF 과표기준가(차익 중
  과세 대상 몫), 금융소득 종합과세(2천만원 초과)는 빠져 있다. 100만원 계좌에서
  가장 큰 항목(해외 250만원 공제)은 들어 있다 — **이 규모에서는 해외 주식
  세금이 사실상 0**이라는 것이 이 표가 말하는 가장 중요한 사실이다.
"""
from __future__ import annotations

import json
import os

FX_SPREAD_DEFAULT = 0.0025          # 편도 — 환전 우대 75% 가정(보수적)
FX_MARKETS = ("us_stock",)          # 원화 계좌에서 달러로 바꿔야 사는 시장
FOREIGN_DEDUCTION_KRW = 2_500_000
FOREIGN_RATE = 0.22
KR_ETF_RATE = 0.154
# 국내주식형 ETF — 매매차익 비과세. 나머지 국내 ETF는 15.4%.
KR_DOMESTIC_EQUITY_ETF = {"069500.KS", "228790.KS"}
CRYPTO_TAX_FROM = "2027-01-01"


def fx_spread(state_dir: str) -> float:
    try:
        with open(os.path.join(state_dir, "engine.json"), encoding="utf-8") as f:
            v = (json.load(f) or {}).get("fx_spread")
        if v is not None and 0.0 <= float(v) < 0.05:
            return float(v)
    except (OSError, ValueError, TypeError):
        pass
    return FX_SPREAD_DEFAULT


def fx_charge(fills: list, spread: float) -> tuple[float, float]:
    """그날 체결 중 **원화↔달러로 실제 바뀌는 금액**과 그 환전 비용(원).

    반환: (순 환전 금액, 비용). 매수는 원화→달러, 매도는 달러→원화.
    """
    net = 0.0
    for f in fills or []:
        if str(f.get("key", "")).split(":", 1)[0] not in FX_MARKETS:
            continue
        amt = float(f.get("amount") or 0.0)
        net += amt if f.get("side") == "buy" else -amt
    return abs(net), abs(net) * float(spread)


def tax_class(key: str) -> str:
    market, sym = (key.split(":", 1) + [""])[:2]
    if market == "us_stock":
        return "foreign"
    if market == "crypto":
        return "crypto"
    if market == "kr_stock":
        from quant.live.daily import is_etf
        if is_etf("kr_stock", sym) and sym not in KR_DOMESTIC_EQUITY_ETF:
            return "kr_etf_taxed"
        return "exempt"
    return "exempt"


def estimate(realized: dict, year: str) -> dict:
    """올해 실현 손익 {종목: 원} → 세금 추정."""
    g = {"foreign": 0.0, "kr_etf_taxed": 0.0, "exempt": 0.0, "crypto": 0.0}
    kr_etf_tax = 0.0
    for key, gain in (realized or {}).items():
        c = tax_class(key)
        g[c] += float(gain)
        if c == "kr_etf_taxed" and gain > 0:
            # 매도 건별 과세 — 손실과 상계하지 않는다. 종목별 연 합계로 근사.
            kr_etf_tax += float(gain) * KR_ETF_RATE
    foreign_tax = max(0.0, g["foreign"] - FOREIGN_DEDUCTION_KRW) * FOREIGN_RATE
    crypto_tax = 0.0
    if year >= CRYPTO_TAX_FROM[:4]:
        crypto_tax = max(0.0, g["crypto"] - FOREIGN_DEDUCTION_KRW) * FOREIGN_RATE
    total = foreign_tax + kr_etf_tax + crypto_tax
    return {"year": year,
            "realized": {k: round(v, 2) for k, v in g.items()},
            "foreign_deduction": FOREIGN_DEDUCTION_KRW,
            "tax": {"foreign": round(foreign_tax, 2),
                    "kr_etf": round(kr_etf_tax, 2),
                    "crypto": round(crypto_tax, 2)},
            "total": round(total, 2),
            "note": "추정 — 다음 해 5월 납부분. 자산에서 빼지 않고 따로 적는다"}
