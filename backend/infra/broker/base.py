"""
브로커 추상 클래스 (어댑터 인터페이스)
문서: ATS-SAD-001 §5.5
확장성: NFR-E02 증권사 교체 대비
"""

from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd

from common.types import (
    Balance,
    OrderRequest,
    OrderResult,
    OrderStatusResponse,
    PriceData,
)


class BaseBroker(ABC):
    """
    브로커 추상 클래스.
    한투 API 외에 다른 증권사로 교체할 경우 이 인터페이스를 구현한다.
    """

    @abstractmethod
    def authenticate(self) -> str:
        """인증 토큰을 발급받는다. 반환값: 토큰 문자열"""
        ...

    @abstractmethod
    def is_token_valid(self) -> bool:
        """현재 토큰이 유효한지 확인한다."""
        ...

    @abstractmethod
    def get_price(self, stock_code: str) -> PriceData:
        """현재가를 조회한다."""
        ...

    @abstractmethod
    def get_ohlcv(self, stock_code: str, period: int = 60) -> pd.DataFrame:
        """
        일봉 OHLCV 데이터를 조회한다.
        Returns: DataFrame (columns: date, open, high, low, close, volume)
        """
        ...

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult:
        """매수/매도 주문을 전송한다."""
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """주문을 취소한다."""
        ...

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> OrderStatusResponse:
        """주문 체결 상태를 조회한다."""
        ...

    @abstractmethod
    def get_balance(self) -> Balance:
        """계좌 잔고를 조회한다."""
        ...
