"""거래 비용 모델 — 백테스트를 실전에 가깝게.

고정 수수료+슬리피지만 반영하면 백테스트가 실전보다 낙관적이다. 현실에는:
    - 변동성 비례 슬리피지: 요동칠수록 체결이 불리해진다
    - 시장충격(market impact): 주문이 그 봉 거래대금에서 차지하는 비중이
      클수록 체결가가 불리해진다 (제곱근 법칙 근사)
    - 공매도 차입 비용: 숏 포지션 보유에 드는 비용
    - 펀딩비: 무기한 선물(perp) 보유에 주기적으로 드는 비용
이들을 반영하면 '백테스트에서만 좋은' 고회전·고레버리지 전략의 환상이 걷힌다.

기본값은 모두 0(또는 기존 수수료·슬리피지)이라, 지정하지 않으면 기존과 동일하게 동작한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# 시장별 현실 비용 프리셋 (편도, 회전율 대비 비율). 출처·가정을 주석으로 남긴다.
# '몰라서 낙관적인' 백테스트를 막는 게 목적이며, 정확한 값은 본인 브로커 기준으로
# overrides 하라. 특히 한국주식은 거래세 때문에 왕복 비용이 코인의 ~2배다.
# 숏 보유 비용(대차료) — **봉(일)당** |비중| 대비. 연율을 252거래일로 나눈다.
# ⚠️ 2026-08-16까지 전 시장이 0.0이었다(감사 260). 숏을 공짜로 무한정 들고
#    있을 수 있다는 뜻이고, 그러면 오디션이 실전에 없는 전략을 뽑는다.
#    아래는 **보수적 하한 근사**다 — 실제 대차료는 종목·수급에 따라 훨씬
#    높고(하드투보로우는 연 수십 %), 개인은 대주 자체가 막히는 경우가 많다.
_BORROW_US = 0.0025 / 252      # 미국 대형주 일반 대차 ~연 0.25%
_BORROW_KR = 0.025 / 252       # 한국 개인 대주 ~연 2.5% (가능할 때)
_BORROW_CRYPTO = 0.05 / 365    # 코인 마진 차입 ~연 5% (24/7이라 365로 나눈다)

MARKET_COST_PRESETS: dict[str, dict] = {
    # 바이낸스 현물 테이커 0.1% + 슬리피지
    "crypto": {"fee": 0.001, "slippage": 0.0005,
               "short_borrow": _BORROW_CRYPTO},
    # 업비트 0.05% + 슬리피지 (원화마켓)
    "crypto_upbit": {"fee": 0.0005, "slippage": 0.0005,
                     "short_borrow": _BORROW_CRYPTO},
    # 미국주식: 무수수료 브로커 일반화 + SEC/TAF 미미 → 슬리피지가 주 비용
    "us_stock": {"fee": 0.0001, "slippage": 0.0005,
                 "short_borrow": _BORROW_US},
    # 한국주식: 위탁수수료 ~0.015% + 증권거래세(매도 시 ~0.15%, 2025 기준)를
    # 편도당 절반(0.075%)으로 근사 배분. 왕복 합계는 실제와 일치.
    #
    # ⚠️ **ETF·ETN은 이 거래세를 안 낸다**(2026-09-03에 발견). 증권거래세는
    #    주권 양도에 붙는 세금이고 ETF는 수익증권이라 매도 시 비과세다.
    #    그런데 이 표는 시장만 보고 세금을 물려, 운용 중인 한국 12종목 중
    #    **ETF 6종목**(KODEX 200 · 나스닥100 · 금 · 국고채10년 · 화장품 ·
    #    종합채권)이 내지 않는 세금을 왕복 15bp씩 물고 있었다.
    #
    #    조용한 오류였고 방향이 '보수적'이라 더 늦게 잡혔다. 그런데 보수적인
    #    것과 옳은 것은 다르고, 여기서는 세 가지가 함께 틀어진다:
    #      ① 한국 성적이 실제보다 나빠 보인다.
    #      ② **리밸런스 밴드가 비용에 비례**한다 — 비용을 2배로 잡으면
    #         밴드가 넓어져 기계가 고쳐 잡아야 할 자리를 안 고친다.
    #      ③ 오디션이 고회전 한국 후보를 부당하게 떨어뜨린다.
    "kr_stock": {"fee": 0.00015 + 0.00075, "slippage": 0.0005,
                 "short_borrow": _BORROW_KR},
    # 한국 ETF — 위탁수수료만. 거래세 없음(위 주석 참조).
    "kr_stock_etf": {"fee": 0.00015, "slippage": 0.0005,
                     "short_borrow": _BORROW_KR},
    # 합성 데이터: 기본값 그대로 (검증용)
    "synthetic": {"fee": 0.001, "slippage": 0.0005},
}


@dataclass
class CostModel:
    fee: float = 0.001          # 편도 수수료 (회전율 대비)
    slippage: float = 0.0005    # 기본 슬리피지 (회전율 대비)
    impact_coef: float = 0.0    # 변동성 비례 슬리피지 계수 (× 최근 변동성)
    short_borrow: float = 0.0   # 숏 보유 비용 (봉당, |비중| 대비)
    funding: float = 0.0        # 펀딩비 (봉당, |비중| 대비, 롱·숏 모두 부과하는 보수적 고정치)
    # 시장충격(제곱근 법칙): 체결비용률 = market_impact_coef × √participation.
    # participation = (주문 명목금액 / 그 봉 거래대금). 기본 0 = 미사용(기존과 동일).
    # ⚠️ 근사 모델이며 실제 호가창 깊이·유동성 공백을 대체하지 못한다.
    #    소형주·저유동 코인에서 실제 충격은 이보다 훨씬 클 수 있다.
    market_impact_coef: float = 0.0
    participation_cap: float = 1.0   # participation 상한(거래대금보다 큰 주문의 폭주 방지)
    # 봉 타임스탬프→펀딩률 실데이터 시리즈(pd.Series). 지정 시 고정 funding 대신
    # 그 봉 타임스탬프에 '정확히 일치'하는 정산액만 부과한다(룩어헤드 없음).
    # 봉 인덱스와 맞추려면 quant.data.funding.align_funding_to_bars 를 쓸 것.
    # 부호 규약: 양수=롱이 지불(숏은 수취). None(기본)=기존 고정 funding 사용.
    funding_series: Any = field(default=None, repr=False)
    # 어느 시장인가 — **호가 단위(틱) 하한**을 계산하는 데만 쓴다.
    # 빈 값이면 하한 없음(예전과 완전히 동일하게 동작한다).
    market: str = ""
    # 이 종목이 ETF인가 — KRX는 ETF·ETN 호가 단위가 전 가격대 5원으로
    # 주식과 다르다. 잘못 보면 KODEX 200에 20배를 물린다.
    is_etf: bool = False

    @classmethod
    def for_market(cls, market: str, **overrides) -> "CostModel":
        """시장별 '현실적' 비용 프리셋으로 CostModel을 만든다.

        모르는 시장이면 기본값(fee 0.1%+슬리피지 0.05%)을 쓴다. overrides로
        개별 필드를 덮어쓸 수 있다. ⚠️ 근사치다 — 브로커·등급·체결 방식에 따라
        실제 비용은 다르며, 특히 한국주식 거래세는 '매도에만' 붙지만 이 모델은
        방향을 모르므로 편도당 절반으로 나눠 근사한다(왕복 합계는 정확).
        """
        # ⚠️ ETF는 같은 시장이어도 **세금이 다르다**(한국 거래세 비과세).
        #    프리셋을 고를 때 그 사실을 반영한다 — 안 하면 ETF가 내지 않는
        #    세금을 왕복 15bp 물고, 그 값이 밴드·오디션·성적으로 다 흘러간다.
        key = market.lower()
        if overrides.get("is_etf") and f"{key}_etf" in MARKET_COST_PRESETS:
            p = MARKET_COST_PRESETS[f"{key}_etf"]
        else:
            p = MARKET_COST_PRESETS.get(key)
        base = dict(p) if p else {}
        base.setdefault("market", market)      # 틱 하한이 시장을 알아야 한다
        base.update(overrides)
        return cls(**base)

    def total_one_way(self) -> float:
        """편도 한 번의 비용률(수수료 + 슬리피지).

        이 합을 손으로 쓰는 자리가 네 곳이었다(본 계좌 체결, 장중 코인,
        장중 미국, 그냥 보유 기준선). 같은 식을 여러 곳에 두면 언젠가
        갈라진다(FROZEN_IDEAS ①) — 한 자리로 모은다.
        """
        return float(self.fee + self.slippage)

    def slippage_floor(self, price=None) -> float:
        """**이보다 싸게 체결될 수 없다** — 호가 한 칸의 절반 (2026-08-14).

        가정 슬리피지 5bp는 국내 대형주에서 물리적으로 불가능한 값이었다.
        실측(이 저장소 운영 종목):

            삼성전자 236,000원 → 호가 500원 → 편도 하한 10.6bp (가정의 2.1배)
            LG화학  275,500원 → 호가 500원 → 편도 하한  9.1bp (가정의 1.8배)

        낼 수 없는 비용으로 백테스트를 돌리면 고회전 전략이 부당하게 유리해지고
        그 전략이 오디션을 이겨 챔피언이 된다. 이것은 **추정이 아니라 하한**이라,
        가정을 대체하지 않고 바닥으로만 쓴다(가정이 더 크면 가정을 둔다).
        """
        if not self.market or price is None:
            return 0.0
        from quant.backtest.tick import spread_floor
        return spread_floor(self.market, price, self.is_etf)

    def turnover_cost(self, turnover: float, vol: float = 0.0,
                      price=None) -> float:
        """회전율(포지션 변경량)에 따른 거래 비용 비율.

        `price`를 주면 호가 단위 하한이 적용된다 — 안 주면 예전과 동일.
        """
        slip = max(self.slippage, self.slippage_floor(price))
        return (self.fee + slip + self.impact_coef * vol) * turnover

    def market_impact_cost(
        self, turnover: float, equity: float, dollar_volume: float | None
    ) -> float:
        """제곱근 법칙 시장충격 비용 비율 (자본 대비).

        participation = (turnover × equity) / 봉 거래대금.
        자본 대비 비용 = market_impact_coef × √participation × turnover.
        거래대금 정보가 없으면 0을 반환한다(과소추정임을 인지할 것).
        """
        if self.market_impact_coef <= 0.0 or turnover <= 0.0 or equity <= 0.0:
            return 0.0
        if dollar_volume is None or not (dollar_volume > 0.0) \
                or not math.isfinite(dollar_volume):
            return 0.0
        participation = min((turnover * equity) / dollar_volume,
                            self.participation_cap)
        return self.market_impact_coef * math.sqrt(participation) * turnover

    # 봉당 펀딩률 절대값 상한. 실제 펀딩은 극단 시장에서도 8시간당 ±0.75% 수준이라
    # 이 값을 넘는 데이터는 오염(단위 오류·API 이상)으로 보고 잘라낸다. 클램프가
    # 없으면 |rate|>=1 인 오염 값 하나가 cash_equity *= 1-hold 에서 자본 부호를
    # 뒤집어 백테스트 전체를 조용히 망가뜨린다.
    _FUNDING_RATE_CAP = 0.05

    def _funding_rate_at(self, ts) -> float:
        """funding_series에서 ts 시점의 펀딩률을 읽는다(없거나 비유한이면 0)."""
        try:
            v = float(self.funding_series.get(ts, 0.0))
        except (TypeError, ValueError, AttributeError):
            return 0.0
        if not math.isfinite(v):
            return 0.0
        return max(-self._FUNDING_RATE_CAP, min(self._FUNDING_RATE_CAP, v))

    def holding_cost(self, position: float, vol: float = 0.0, ts=None) -> float:
        """봉당 포지션 보유 비용 비율 (펀딩 + 숏 차입). 음수 = 수취(펀딩 크레딧).

        funding_series 지정 시 실데이터 부호를 따른다(양수 rate → 롱 지불·숏 수취).
        미지정 시 기존처럼 |비중|에 고정 funding을 보수적으로 부과한다.
        """
        if self.funding_series is not None and ts is not None:
            cost = self._funding_rate_at(ts) * position
        else:
            cost = self.funding * abs(position)
        if position < 0:
            cost += self.short_borrow * abs(position)
        return cost
