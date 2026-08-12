"""국내주식 실거래 브로커 — 키움증권 REST API (베타).

⚠️ 실제 자금이 오갑니다. 반드시 모의투자(paper=True)로 충분히 검증 후 사용하세요.

⚠️ 베타 주의: 키움 REST API의 엔드포인트·api-id·응답 필드명은 개정될 수 있습니다.
   이 클래스는 그 값들을 '오버라이드 가능한 속성'으로 두었습니다. 실제 사용 전
   최신 키움 문서(https://apiportal.kiwoom.com/)로 tr-id와 응답 필드명을 확인하고,
   다르면 생성자 인자나 속성으로 조정하세요. 인증·주문 라우팅·수량 처리 로직은
   가짜 API로 단위 테스트되어 있습니다.

환경변수:
    KIWOOM_APP_KEY, KIWOOM_SECRET
    KIWOOM_ACCOUNT      계좌번호(종합계좌번호)
"""
from __future__ import annotations

import os
import time

from quant.broker.base import Broker, Order, Position, safe_amount
from quant.broker.specs import MarketSpec
from quant.utils.http import get_json, post_json  # noqa: F401  (get_json: 대칭성)
from quant.utils.logging import get_logger

log = get_logger("broker.kiwoom_live")


class KiwoomBroker(Broker):
    REAL_URL = "https://api.kiwoom.com"
    MOCK_URL = "https://mockapi.kiwoom.com"

    # api-id (키움 문서 기준 기본값 — 개정 시 오버라이드)
    TR_BUY = "kt10000"        # 주식 매수주문
    TR_SELL = "kt10001"       # 주식 매도주문
    TR_BALANCE = "kt00018"    # 계좌평가잔고내역요청

    # 응답 필드명 (문서 개정 시 오버라이드) — 잔고 파싱용
    HOLDINGS_KEY = "acnt_evlt_remn_indv_tot"  # 종목별 보유 리스트 키
    CODE_FIELD = "stk_cd"       # 종목코드
    QTY_FIELD = "rmnd_qty"      # 보유수량
    AVG_FIELD = "pur_pric"      # 매입단가
    CASH_FIELD = "prsm_dpst_aset_amt"  # 추정예수자산(예수금)

    def __init__(self, paper: bool = True, base: str | None = None):
        self.paper = paper
        self.base = base or (self.MOCK_URL if paper else self.REAL_URL)
        self.appkey = os.getenv("KIWOOM_APP_KEY", "")
        self.secret = os.getenv("KIWOOM_SECRET", "")
        self.account = os.getenv("KIWOOM_ACCOUNT", "")
        if not all([self.appkey, self.secret, self.account]):
            raise RuntimeError(
                "환경변수 KIWOOM_APP_KEY / KIWOOM_SECRET / KIWOOM_ACCOUNT 가 필요합니다."
            )
        if not paper:
            log.warning("⚠️ 키움 실거래(REAL) 모드입니다. 실제 자금이 사용됩니다.")
        self._token: str | None = None
        self._token_expiry = 0.0
        self._balance_cache: dict | None = None
        self._balance_ts = 0.0
        self._balance_ttl = 3.0

    # --- 인증 ---
    def _get_token(self) -> str:
        # 키움 토큰도 만료된다(대개 24시간). 무기한 캐시 대신 만료 추적 후 재발급.
        if self._token and time.time() < self._token_expiry:
            return self._token
        res = post_json(
            f"{self.base}/oauth2/token",
            {"content-type": "application/json;charset=UTF-8"},
            {"grant_type": "client_credentials",
             "appkey": self.appkey, "secretkey": self.secret},
        )
        # 문서 버전에 따라 'token' 또는 'access_token'
        self._token = res.get("token") or res.get("access_token", "")
        try:
            ttl = float(res.get("expires_in", 82800))
        except (TypeError, ValueError):
            ttl = 82800.0
        self._token_expiry = time.time() + max(60.0, ttl - 300.0)
        return self._token

    def _headers(self, api_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.appkey,
            "secretkey": self.secret,
            "api-id": api_id,
        }

    # --- 계좌 조회 ---
    def _balance(self) -> dict:
        # 같은 사이클의 get_cash+get_position 중복 조회만 합치는 짧은 TTL 캐시.
        now = time.time()
        if self._balance_cache is not None and now - self._balance_ts < self._balance_ttl:
            return self._balance_cache
        body = {"qry_tp": "1", "dmst_stex_tp": "KRX"}
        data = post_json(f"{self.base}/api/dostk/acnt",
                         self._headers(self.TR_BALANCE), body)
        self._balance_cache, self._balance_ts = data, now
        return data

    def get_cash(self) -> float:
        """예수금. **필드가 없으면 0이 아니라 오류다**(감사 182).

        이 클래스는 첫 줄부터 "응답 필드명은 개정될 수 있다"고 적어 두고
        필드명을 오버라이드 가능한 속성으로 뒀다. 즉 **이름이 어긋나는 일이
        실제로 일어난다는 전제**로 만들어졌다. 그런데 어긋났을 때의 답이
        `0`이었다.

        현금 0은 '보수적'으로 보이지만 그렇지 않다 — 상위 로직은 현금으로
        평가금액을 만들고 거기에 목표 비중을 곱한다. 현금이 0으로 읽히면
        평가금액이 쪼그라들어 **보유분을 팔라는 지시**가 나온다. 필드명
        하나가 바뀐 날 계좌가 통째로 청산될 수 있다.

        '모름'은 숫자가 아니다. 그대로 올려보내 호출부가 매매를 건너뛰게 한다.
        """
        data = self._balance()
        if self.CASH_FIELD not in data:
            raise RuntimeError(
                f"잔고 응답에 예수금 필드({self.CASH_FIELD})가 없습니다 — "
                f"키움 API 개정 가능성. 받은 키: {sorted(data)[:20]}")
        # 콤마 제거 후 안전 변환(inf/nan/음수 방어).
        return safe_amount(str(data.get(self.CASH_FIELD, 0)).replace(",", ""))

    def get_position(self, symbol: str) -> Position:
        """보유 수량. **보유 목록 키가 없으면 '0주'가 아니라 오류다**(감사 182).

        ⚠️ 이건 감사 55와 **같은 결함**이다. 그때는 us_live가 401·429·500·
           타임아웃을 전부 '0주 보유'로 읽었다. 여기서는 응답은 멀쩡히 왔는데
           **보유 목록 키 이름이 달라졌을 때** 같은 일이 벌어진다.

           실거래에서 보유를 0으로 읽으면 상위 로직은 목표 비중만큼 **다시
           사서** 포지션이 두 배가 된다. 20종목이면 스무 번.

        키가 **있는데** 그 안에 이 종목이 없으면 그건 진짜로 '보유 없음'이다.
        """
        data = self._balance()
        if self.HOLDINGS_KEY not in data:
            raise RuntimeError(
                f"잔고 응답에 보유목록 키({self.HOLDINGS_KEY})가 없습니다 — "
                f"키움 API 개정 가능성. 받은 키: {sorted(data)[:20]}")
        for item in data.get(self.HOLDINGS_KEY) or []:
            code = str(item.get(self.CODE_FIELD, "")).lstrip("A")  # 'A005930' → '005930'
            if code == symbol:
                qty = safe_amount(str(item.get(self.QTY_FIELD, 0)).replace(",", ""))
                avg = safe_amount(str(item.get(self.AVG_FIELD, 0)).replace(",", ""))
                return Position(symbol, qty, avg)
        return Position(symbol, 0.0, 0.0)

    # --- 주문 ---
    def market_spec(self, symbol: str) -> MarketSpec:
        """국내주식 주문 규격 — 정수 주만, 최소 1주 (감사 148).

        KIS와 같은 시장(KRX)이므로 같은 규격이다. 형제를 둘 다 고친다 —
        증권사를 갈아탄 날 한쪽만 규격이 살아 있으면 그게 더 나쁘다(⑭).
        """
        return MarketSpec(min_qty=1.0, qty_step=1.0)

    def market_order(self, symbol: str, side: str, quantity: float, price: float) -> Order:
        # ⚠️ **모르는 방향의 기본값이 '매도'였다**(감사 182). 예전에는
        #    `self.TR_BUY if side == "buy" else self.TR_SELL` 한 줄이라,
        #    "BUY"·"Buy"·"long"·오타 — 정확히 "buy"가 아닌 **무엇이든**
        #    조용히 매도 주문이 되어 나갔다. 사는 줄 알고 팔린다.
        #
        #    기본값은 절대 파괴적인 쪽이면 안 된다. 대소문자는 받아 주되,
        #    아는 두 방향이 아니면 주문을 만들지 않고 거절한다.
        side = str(side).strip().lower()
        if side not in ("buy", "sell"):
            raise ValueError(f"알 수 없는 주문 방향: {side!r} (buy/sell만 허용)")
        qty = int(quantity)  # 국내주식은 정수 수량
        if qty <= 0:
            return Order(symbol, side, 0.0, price, status="skipped")
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd": symbol,
            "ord_qty": str(qty),
            "ord_uv": "",          # 시장가는 단가 비움
            "trde_tp": "3",        # 3 = 시장가
            "cond_uv": "",
        }
        api_id = self.TR_BUY if side == "buy" else self.TR_SELL
        log.warning("[KIWOOM] %s %s %d주 시장가 주문 전송", side.upper(), symbol, qty)
        res = post_json(f"{self.base}/api/dostk/ordr", self._headers(api_id), body)
        rc = res.get("return_code", res.get("rt_cd"))
        accepted = rc in (0, "0")
        # KIS와 동일: return_code 0은 '접수 성공'이지 '체결'이 아니다. 접수를
        # 체결로 위조하지 않고 'accepted'로 보고한다(실제 체결은 포지션 변화로 확인).
        odno = str(res.get("ord_no", res.get("odno", "")))
        status = "accepted" if accepted else str(
            res.get("return_msg", res.get("msg1", "rejected")))
        return Order(symbol, side, float(qty), price, status=status,
                     filled_quantity=0.0, order_id=odno)
