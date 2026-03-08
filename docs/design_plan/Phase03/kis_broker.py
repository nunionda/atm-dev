"""
한국투자증권 REST API 구현체
문서: ATS-SAD-001 §5.5, §11
API Rate Limit: 초당 5건 (NFR-P03)
토큰 만료: 24시간 (자동 갱신)
"""

from __future__ import annotations

import time
import threading
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

from common.enums import OrderSide, OrderType
from common.exceptions import (
    AuthenticationError,
    BrokerError,
    OrderError,
    OrderRejectedError,
    RateLimitError,
)
from common.types import (
    Balance,
    BalancePosition,
    OrderRequest,
    OrderResult,
    OrderStatusResponse,
    PriceData,
)
from infra.broker.base import BaseBroker
from infra.logger import get_logger

logger = get_logger("kis_broker")


class RateLimiter:
    """초당 호출 횟수를 제한하는 Rate Limiter (NFR-P03)."""

    def __init__(self, max_calls: int = 5, period: float = 1.0):
        self.max_calls = max_calls
        self.period = period
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self):
        """호출 가능할 때까지 대기한다."""
        with self._lock:
            now = time.monotonic()
            # 기간 밖의 오래된 호출 제거
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) >= self.max_calls:
                sleep_time = self.period - (now - self._calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self._calls = self._calls[1:]

            self._calls.append(time.monotonic())


class KISBroker(BaseBroker):
    """
    한국투자증권 Open API 구현체.
    
    지원 모드:
    - 모의투자 (paper): https://openapivts.koreainvestment.com:29443
    - 실전투자 (live):  https://openapi.koreainvestment.com:9443
    """

    LIVE_URL = "https://openapi.koreainvestment.com:9443"
    PAPER_URL = "https://openapivts.koreainvestment.com:29443"

    # 거래 ID (tr_id) 매핑 — 실전 / 모의 구분
    TR_IDS = {
        "token": "N/A",
        "price": "FHKST01010100",
        "daily_price": "FHKST01010400",
        "buy_order": {"live": "TTTC0802U", "paper": "VTTC0802U"},
        "sell_order": {"live": "TTTC0801U", "paper": "VTTC0801U"},
        "cancel_order": {"live": "TTTC0803U", "paper": "VTTC0803U"},
        "order_status": {"live": "TTTC8001R", "paper": "VTTC8001R"},
        "balance": {"live": "TTTC8434R", "paper": "VTTC8434R"},
    }

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        is_paper: bool = True,
    ):
        self.app_key = app_key
        self.app_secret = app_secret

        # 계좌번호 분리: "12345678-01" → ("12345678", "01")
        parts = account_no.split("-")
        self.cano = parts[0]
        self.acnt_prdt_cd = parts[1] if len(parts) > 1 else "01"

        self.is_paper = is_paper
        self.base_url = self.PAPER_URL if is_paper else self.LIVE_URL
        self.mode = "paper" if is_paper else "live"

        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._rate_limiter = RateLimiter(max_calls=5, period=1.0)

        logger.info(
            "KISBroker initialized | mode=%s | account=%s-**",
            self.mode,
            self.cano[:4],
        )

    # ──────────────────────────────────────
    # 인증
    # ──────────────────────────────────────

    def authenticate(self) -> str:
        """OAuth 토큰을 발급받는다. (SAD §11.1 /oauth2/tokenP)"""
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        try:
            resp = requests.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            self._token = data["access_token"]
            # 토큰 유효시간: 약 24시간, 1시간 전 여유를 둔다
            expires_in = int(data.get("expires_in", 86400))
            self._token_expires = datetime.now() + timedelta(seconds=expires_in - 3600)

            logger.info("Token issued | expires_at=%s", self._token_expires.isoformat())
            return self._token

        except requests.RequestException as e:
            logger.error("Token issuance failed: %s", e)
            raise AuthenticationError(f"토큰 발급 실패: {e}") from e

    def is_token_valid(self) -> bool:
        """토큰 유효성을 확인한다."""
        if self._token is None or self._token_expires is None:
            return False
        return datetime.now() < self._token_expires

    def _ensure_token(self):
        """토큰이 없거나 만료 임박이면 자동 갱신한다."""
        if not self.is_token_valid():
            logger.info("Token expired or missing, re-authenticating...")
            self.authenticate()

    def _get_headers(self, tr_id: str) -> dict:
        """공통 API 헤더를 생성한다. (SAD §11.2)"""
        self._ensure_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _get_tr_id(self, key: str) -> str:
        """모드(실전/모의)에 따른 거래ID를 반환한다."""
        tr = self.TR_IDS[key]
        if isinstance(tr, dict):
            return tr[self.mode]
        return tr

    def _request(
        self, method: str, path: str, tr_id: str,
        params: dict = None, body: dict = None,
    ) -> dict:
        """API 호출 공통 메서드 (Rate Limit 적용)."""
        self._rate_limiter.acquire()
        url = f"{self.base_url}{path}"
        headers = self._get_headers(tr_id)

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=params, timeout=10)
            else:
                resp = requests.post(url, headers=headers, json=body, timeout=10)

            resp.raise_for_status()
            data = resp.json()

            # 한투 API 에러 코드 체크
            rt_cd = data.get("rt_cd", "0")
            if rt_cd != "0":
                msg = data.get("msg1", "Unknown error")
                logger.error("API error | tr_id=%s | rt_cd=%s | msg=%s", tr_id, rt_cd, msg)
                raise BrokerError(f"API 에러 [{rt_cd}]: {msg}")

            return data

        except requests.RequestException as e:
            logger.error("HTTP request failed | url=%s | error=%s", url, e)
            raise BrokerError(f"HTTP 요청 실패: {e}") from e

    # ──────────────────────────────────────
    # 시세 조회
    # ──────────────────────────────────────

    def get_price(self, stock_code: str) -> PriceData:
        """현재가를 조회한다. (SAD §11.1 inquire-price)"""
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식
            "FID_INPUT_ISCD": stock_code,
        }
        data = self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            self._get_tr_id("price"),
            params=params,
        )
        output = data["output"]

        return PriceData(
            stock_code=stock_code,
            stock_name=output.get("hts_kor_isnm", ""),
            current_price=float(output["stck_prpr"]),
            open_price=float(output.get("stck_oprc", 0)),
            high_price=float(output.get("stck_hgpr", 0)),
            low_price=float(output.get("stck_lwpr", 0)),
            prev_close=float(output.get("stck_sdpr", 0)),
            volume=int(output.get("acml_vol", 0)),
            change_pct=float(output.get("prdy_ctrt", 0)),
            timestamp=datetime.now().isoformat(),
        )

    def get_ohlcv(self, stock_code: str, period: int = 60) -> pd.DataFrame:
        """일봉 OHLCV를 조회한다. (SAD §11.1 inquire-daily-price)"""
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": (datetime.now() - timedelta(days=period * 2)).strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": datetime.now().strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",  # 일봉
            "FID_ORG_ADJ_PRC": "0",      # 수정주가 미반영
        }
        data = self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            self._get_tr_id("daily_price"),
            params=params,
        )

        rows = []
        for item in data.get("output2", []):
            if not item.get("stck_bsop_date"):
                continue
            rows.append({
                "date": item["stck_bsop_date"],
                "open": float(item["stck_oprc"]),
                "high": float(item["stck_hgpr"]),
                "low": float(item["stck_lwpr"]),
                "close": float(item["stck_clpr"]),
                "volume": int(item["acml_vol"]),
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df

    # ──────────────────────────────────────
    # 주문
    # ──────────────────────────────────────

    def place_order(self, order: OrderRequest) -> OrderResult:
        """매수/매도 주문을 전송한다. (SAD §11.1 order-cash)"""
        is_buy = order.side == OrderSide.BUY.value

        tr_id = self._get_tr_id("buy_order" if is_buy else "sell_order")

        # 주문 유형 코드
        if order.order_type == OrderType.MARKET.value:
            ord_dvsn = "01"  # 시장가
            ord_unpr = "0"
        else:
            ord_dvsn = "00"  # 지정가
            ord_unpr = str(int(order.price)) if order.price else "0"

        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": order.stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": ord_unpr,
        }

        try:
            data = self._request(
                "POST",
                "/uapi/domestic-stock/v1/trading/order-cash",
                tr_id,
                body=body,
            )
            output = data.get("output", {})
            broker_order_id = output.get("ODNO", "")

            logger.info(
                "Order placed | side=%s | stock=%s | qty=%d | price=%s | broker_id=%s",
                order.side, order.stock_code, order.quantity, ord_unpr, broker_order_id,
            )

            return OrderResult(
                success=True,
                order_id=order.order_id,
                broker_order_id=broker_order_id,
            )

        except BrokerError as e:
            if "잔고" in str(e) or "부족" in str(e):
                raise OrderRejectedError(f"주문 거부: {e}") from e
            raise OrderError(f"주문 실패: {e}") from e

    def cancel_order(self, broker_order_id: str) -> bool:
        """주문을 취소한다. (SAD §11.1 order-rvsecncl)"""
        tr_id = self._get_tr_id("cancel_order")
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": broker_order_id,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 취소
            "ORD_QTY": "0",  # 전량 취소
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }

        try:
            self._request(
                "POST",
                "/uapi/domestic-stock/v1/trading/order-rvsecncl",
                tr_id,
                body=body,
            )
            logger.info("Order cancelled | broker_id=%s", broker_order_id)
            return True
        except BrokerError as e:
            logger.error("Cancel failed | broker_id=%s | error=%s", broker_order_id, e)
            return False

    def get_order_status(self, broker_order_id: str) -> OrderStatusResponse:
        """체결 상태를 조회한다. (SAD §11.1 inquire-daily-ccld)"""
        tr_id = self._get_tr_id("order_status")
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "INQR_STRT_DT": datetime.now().strftime("%Y%m%d"),
            "INQR_END_DT": datetime.now().strftime("%Y%m%d"),
            "SLL_BUY_DVSN_CD": "00",  # 전체
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": broker_order_id,
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        data = self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id,
            params=params,
        )

        for item in data.get("output1", []):
            if item.get("odno") == broker_order_id:
                filled_qty = int(item.get("tot_ccld_qty", 0))
                ord_qty = int(item.get("ord_qty", 0))

                if filled_qty == 0:
                    status = "SUBMITTED"
                elif filled_qty >= ord_qty:
                    status = "FILLED"
                else:
                    status = "PARTIALLY_FILLED"

                return OrderStatusResponse(
                    broker_order_id=broker_order_id,
                    status=status,
                    filled_quantity=filled_qty,
                    filled_price=float(item.get("avg_prvs", 0)),
                    filled_amount=float(item.get("tot_ccld_amt", 0)),
                )

        # 주문 내역에서 찾지 못한 경우
        return OrderStatusResponse(
            broker_order_id=broker_order_id,
            status="SUBMITTED",
        )

    # ──────────────────────────────────────
    # 잔고
    # ──────────────────────────────────────

    def get_balance(self) -> Balance:
        """계좌 잔고를 조회한다. (SAD §11.1 inquire-balance)"""
        tr_id = self._get_tr_id("balance")
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        data = self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            params=params,
        )

        output2 = data.get("output2", [{}])[0] if data.get("output2") else {}

        positions = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty", 0))
            if qty <= 0:
                continue
            positions.append(BalancePosition(
                stock_code=item.get("pdno", ""),
                stock_name=item.get("prdt_name", ""),
                quantity=qty,
                avg_price=float(item.get("pchs_avg_pric", 0)),
                current_price=float(item.get("prpr", 0)),
                eval_amount=float(item.get("evlu_amt", 0)),
                pnl=float(item.get("evlu_pfls_amt", 0)),
                pnl_pct=float(item.get("evlu_pfls_rt", 0)),
            ))

        return Balance(
            cash=float(output2.get("dnca_tot_amt", 0)),
            total_eval=float(output2.get("scts_evlu_amt", 0)),
            total_pnl=float(output2.get("evlu_pfls_smtl_amt", 0)),
            total_pnl_pct=float(output2.get("tot_evlu_pfls_rt", 0)),
            positions=positions,
        )
