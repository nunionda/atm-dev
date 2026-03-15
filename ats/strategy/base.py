"""
전략 추상 클래스 (플러그인 인터페이스)
문서: ATS-SAD-001 §5.2
확장성: NFR-E01 전략 추가 용이
"""

from abc import ABC, abstractmethod
from typing import List

import pandas as pd

from common.types import ExitSignal, Signal


class BaseStrategy(ABC):
    """
    전략 추상 클래스.
    새로운 매매 전략을 추가할 때 이 인터페이스를 구현한다.
    """

    @abstractmethod
    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: dict[str, pd.DataFrame],
        current_prices: dict,
    ) -> List[Signal]:
        """
        매수 시그널을 스캔한다 (UC-02).
        Returns: 시그널 강도 내림차순 정렬된 Signal 리스트
        """
        ...

    @abstractmethod
    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: dict[str, pd.DataFrame],
        current_prices: dict,
    ) -> List[ExitSignal]:
        """
        청산 시그널을 스캔한다 (UC-04).
        Returns: ExitSignal 리스트 (우선순위대로 하나만 반환)
        """
        ...

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표를 계산하여 DataFrame에 컬럼을 추가한다."""
        ...
