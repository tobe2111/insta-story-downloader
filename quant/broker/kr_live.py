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

from quant.broker.base import Broker, Order, Position, safe_amount
from quant.broker.specs import MarketSpec
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
            return safe_amount(summary[0].get("dnca_tot_amt", 0.0))  # 예수금 총액
        return 0.0

    def get_position(self, symbol: str) -> Position:
        """계좌의 해당 종목 보유수량을 포지션으로 본다.

        ⚠️ 크립토와 같은 한계(2026-08-11 감사에서 명시): 봇이 산 몫과 사장님이
        원래 들고 있던 몫을 구분하지 않는다. 이미 보유 중인 종목이 운용
        유니버스(AUTO_TARGETS)에 있으면 그 물량도 목표 비중 맞추기의 대상이
        된다. 실거래는 **이 봇 전용 계좌**에서만 쓸 것.
        """
        data = self._balance()
        for item in data.get("output1", []):
            if item.get("pdno") == symbol:
                return Position(
                    symbol,
                    safe_amount(item.get("hldg_qty", 0.0)),        # 보유수량
                    safe_amount(item.get("pchs_avg_pric", 0.0)),   # 매입평균가격
                )
        return Position(symbol, 0.0, 0.0)

    # --- 주문 규격 ---
    def market_spec(self, symbol: str) -> MarketSpec:
        """국내주식 주문 규격 — 정수 주만, 최소 1주 (감사 148).

        감사 139에서 `RobustBroker._spec_for()`가 브로커에게 규격을 묻도록
        고쳤는데, 정작 **답할 줄 아는 브로커가 코인 하나뿐이었다.** 주식
        브로커 둘은 이 메서드가 없어 `min_qty=qty_step=0`인 기본 규격으로
        떨어졌다 — 즉 주식 쪽은 규격 검사가 여전히 꺼져 있었다.

        규격이 없으면 0.4주짜리 주문이 그대로 브로커까지 내려가고, 여기서
        `int(0.4)=0`으로 잘려 'skipped'로 돌아온다. 사고는 아니지만 **왜
        안 샀는지가 한 단계 늦게, 다른 이름으로** 드러난다. 규격을 선언하면
        RobustBroker가 주문 전에 걸러 이유를 남긴다.

        가격 틱(호가단위)은 0으로 둔다 — 시장가 주문은 ORD_UNPR=0이라
        틱이 의미 없고, 잘못 선언하면 오히려 지정가 확장 때 발목을 잡는다.
        """
        return MarketSpec(min_qty=1.0, qty_step=1.0)

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
        # ⚠️ rt_cd=="0"은 '주문 접수 성공'이지 '체결'이 아니다. 주식 시장가는
        # 접수 후 체결까지 시차가 있고, 유동성 부족·장 상황에 따라 부분체결·미체결도
        # 된다. 접수를 'filled'로 위조하면 상위 로직이 완료로 오판한다(us_live·
        # crypto_live와 동일 규약: 실제 체결은 별도로 확인). 접수는 'accepted'로
        # 보고하고 filled_quantity=0을 둔다 — 실제 체결은 RobustBroker의
        # 포지션 변화 확인(confirm_fills)이 측정한다.
        accepted = res.get("rt_cd") == "0"
        out = res.get("output") or {}
        odno = str(out.get("ODNO", "")) if isinstance(out, dict) else ""
        status = "accepted" if accepted else str(res.get("msg1", "rejected"))
        return Order(symbol, side, float(qty), price, status=status,
                     filled_quantity=0.0, order_id=odno)
