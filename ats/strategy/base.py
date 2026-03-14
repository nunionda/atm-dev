"""
전략 추상 인터페이스
모든 매매 전략은 이 인터페이스를 상속한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

import pandas as pd

from common.types import ExitSignal, PriceData, Signal


class BaseStrategy(ABC):

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """OHLCV DataFrame에 기술적 지표를 추가한다."""
        ...

    @abstractmethod
    def scan_entry_signals(
        self,
        universe_codes: List[str],
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[Signal]:
        """매수/매도 진입 시그널을 스캔한다."""
        ...

    @abstractmethod
    def scan_exit_signals(
        self,
        positions: list,
        ohlcv_data: Dict[str, pd.DataFrame],
        current_prices: Dict[str, PriceData],
    ) -> List[ExitSignal]:
        """보유 포지션의 청산 시그널을 스캔한다."""
        ...
