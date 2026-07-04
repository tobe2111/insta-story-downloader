"""국내주식 실거래 브로커 (한국투자증권 KIS Open API).

⚠️ 실제 자금이 오갑니다. 반드시 모의투자(paper=True)로 충분히 검증 후 사용하세요.
환경변수:
    KIS_APP_KEY, KIS_APP_SECRET
    KIS_CANO            계좌번호 앞 8자리
    KIS_ACNT_PRDT_CD    계좌상품코드 (보통 '01')
문서: https://apiportal.koreainvestment.com/

종목코드는 6자리 숫자를 사용한다. 예) 삼성전자 = '005930'
"""
from __future__ import annotations

import os
import time

from quant.broker.base import Broker, Order, Position
from quant.utils.http import get_json, post_json
from quant.utils.logging import get_logger

log = get_logger("broker.kr_live")


class KISBroker(Broker):
    REAL_URL = "https://openapi.koreainvestment.com:9443"
    PAPER_URL = "https://openapivts.koreainvestment.com:29443"

    # 거래 tr_id (실전/모의 구분)
    _TR_BUY = {"real": "TTTC0802U", "paper": "VTTC0802U"}
    _TR_SELL = {"real": "TTTC0801U", "paper": "VTTC0801U"}
    _TR_BALANCE = {"real": "TTTC8434R", "paper": "VTTC8434R"}

    def __init__(self, paper: bool = True):
        self.paper = paper
        self.env = "paper" if paper else "real"
        self.base = self.PAPER_URL if paper else self.REAL_URL
        self.appkey = os.getenv("KIS_APP_KEY", "")
        self.appsecret = os.getenv("KIS_APP_SECRET", "")
        self.cano = os.getenv("KIS_CANO", "")
        self.acnt = os.getenv("KIS_ACNT_PRDT_CD", "01")
        if not all([self.appkey, self.appsecret, self.cano]):
            raise RuntimeError(
                "환경변수 KIS_APP_KEY / KIS_APP_SECRET / KIS_CANO 가 필요합니다."
            )
        if not paper:
            log.warning("⚠️ KIS 실거래(REAL) 모드입니다. 실제 자금이 사용됩니다.")
        self._token: str | None = None
        self._token_expiry = 0.0        # epoch초; 지나면 재발급
        self._balance_cache: dict | None = None
        self._balance_ts = 0.0
        self._balance_ttl = 3.0         # 한 사이클 내 중복 조회만 합치는 짧은 TTL

    # --- 인증 ---
    def _get_token(self) -> str:
        # KIS 토큰은 약 24시간 뒤 만료된다. 무기한 캐시하면 장기 실행 시 만료된
        # 토큰으로 주문이 실패하므로, 만료 시각을 추적해 자동 재발급한다.
        if self._token and time.time() < self._token_expiry:
            return self._token
        res = post_json(
            f"{self.base}/oauth2/tokenP",
            {"content-type": "application/json"},
            {
                "grant_type": "client_credentials",
                "appkey": self.appkey,
                "appsecret": self.appsecret,
            },
        )
        self._token = res["access_token"]
        # 응답의 expires_in(초)에서 5분 여유를 빼 조기 갱신. 값이 없으면 23시간.
        try:
            ttl = float(res.get("expires_in", 82800))
        except (TypeError, ValueError):
            ttl = 82800.0
        self._token_expiry = time.time() + max(60.0, ttl - 300.0)
        return self._token

    def _hashkey(self, body: dict) -> str:
        res = post_json(
            f"{self.base}/uapi/hashkey",
            {"content-type": "application/json", "appkey": self.appkey, "appsecret": self.appsecret},
            body,
        )
        return res.get("HASH", "")

    def _headers(self, tr_id: str, body: dict | None = None) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": tr_id,
        }
        if body is not None:
            headers["hashkey"] = self._hashkey(body)
        return headers

    # --- 계좌 조회 ---
    def _balance(self) -> dict:
        # get_cash와 get_position이 각각 잔고를 조회하면 한 사이클에 API를 두 번
        # 호출한다. 아주 짧은 TTL 캐시로 같은 사이클의 중복 호출만 합쳐 레이트리밋
        # 부담을 줄인다(다음 사이클에는 만료되어 다시 최신 잔고를 받는다).
        now = time.time()
        if self._balance_cache is not None and now - self._balance_ts < self._balance_ttl:
            return self._balance_cache
        params = (
            f"?CANO={self.cano}&ACNT_PRDT_CD={self.acnt}&AFHR_FLPR_YN=N"
            "&OFL_YN=&INQR_DVSN=02&UNPR_DVSN=01&FUND_STTL_ICLD_YN=N"
            "&FNCG_AMT_AUTO_RDPT_YN=N&PRCS_DVSN=00&CTX_AREA_FK100=&CTX_AREA_NK100="
        )
        url = f"{self.base}/uapi/domestic-stock/v1/trading/inquire-balance{params}"
        data = get_json(url, self._headers(self._TR_BALANCE[self.env]))
        self._balance_cache, self._balance_ts = data, now
        return data

    def get_cash(self) -> float:
        data = self._balance()
        summary = data.get("output2", [{}])
        if summary:
            return float(summary[0].get("dnca_tot_amt", 0.0))  # 예수금 총액
        return 0.0

    def get_position(self, symbol: str) -> Position:
        data = self._balance()
        for item in data.get("output1", []):
            if item.get("pdno") == symbol:
                return Position(
                    symbol,
                    float(item.get("hldg_qty", 0.0)),      # 보유수량
                    float(item.get("pchs_avg_pric", 0.0)), # 매입평균가격
                )
        return Position(symbol, 0.0, 0.0)

    # --- 주문 ---
    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        qty = int(quantity)  # 국내주식은 정수 수량
        if qty <= 0:
            return Order(symbol, side, 0.0, price, status="skipped")
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt,
            "PDNO": symbol,
            "ORD_DVSN": "01",          # 01 = 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",           # 시장가는 0
        }
        tr_id = (self._TR_BUY if side == "buy" else self._TR_SELL)[self.env]
        url = f"{self.base}/uapi/domestic-stock/v1/trading/order-cash"
        log.warning("[KIS] %s %s %d주 시장가 주문 전송", side.upper(), symbol, qty)
        res = post_json(url, self._headers(tr_id, body), body)
        status = "filled" if res.get("rt_cd") == "0" else res.get("msg1", "unknown")
        return Order(symbol, side, float(qty), price, status=status)
